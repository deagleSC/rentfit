"""Search filters (backend plan §13): what a tenant asked for, as data.

The parser model returns a `SearchUpdate` (only what the latest message says). Code merges it into
the thread's previous `SearchFilters`, so a follow-up ("cheaper", "near metro instead") is a patch
on the last search, not a new one. Slang is resolved here, in code, on the raw message too, so it
works the same whatever the model returns.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.listing import Amenity, Furnishing

TenantType = Literal["family", "bachelors"]
CommuteMode = Literal["car", "two_wheeler", "walk"]
Bbox = tuple[float, float, float, float]  # (west, south, east, north)


class Commute(BaseModel):
    poi_id: UUID
    poi_name: str
    max_minutes: int = Field(ge=5, le=180)
    mode: CommuteMode = "car"


class SearchFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    city: str | None = None
    locality_ids: list[UUID] = Field(default_factory=list)
    locality_names: list[str] = Field(default_factory=list)  # for display, parallel to locality_ids
    bbox: Bbox | None = None
    bhk: list[int] = Field(default_factory=list)
    rent_min: int | None = Field(default=None, ge=0)
    rent_max: int | None = Field(default=None, ge=0)
    deposit_max: int | None = Field(default=None, ge=0)
    furnishing: list[Furnishing] = Field(default_factory=list)
    tenant_type: TenantType | None = None  # a family sees listings for families or anyone
    pets: bool | None = None
    parking: bool | None = None
    gated: bool | None = None
    no_brokerage: bool | None = None
    amenities: list[Amenity] = Field(default_factory=list)  # hard
    near_metro_m: int | None = Field(default=None, ge=200, le=5000)
    commute: Commute | None = None
    available_by: date | None = None
    soft: list[str] = Field(default_factory=list)  # preferences that rank, never exclude
    semantic_query: str = ""


MIN_RENT = 1000

# Fields a chip can remove, and what removing it means.
CLEARABLE = ("locality_ids", "bbox", "bhk", "rent_min", "rent_max", "deposit_max", "furnishing", "tenant_type",
             "pets", "parking", "gated", "no_brokerage", "amenities", "near_metro_m", "commute", "available_by",
             "soft")


class SearchUpdate(BaseModel):
    """Parser output: only what the latest message states or changes."""

    intent: Literal["search", "ask_about_result", "chitchat"] = "search"
    new_search: bool = Field(default=False, description="True when the tenant starts over, not refining")
    city: Literal["bangalore", "mumbai"] | None = None
    locality_names: list[str] = Field(default_factory=list)
    replace_localities: bool = Field(default=False, description="True for 'X instead' rather than 'also X'")
    bhk: list[int] = Field(default_factory=list)
    rent_min: int | None = Field(default=None, ge=0)
    rent_max: int | None = Field(default=None, ge=0)
    deposit_max: int | None = Field(default=None, ge=0)
    furnishing: list[Furnishing] = Field(default_factory=list)
    tenant_type: TenantType | None = None
    pets: bool | None = None
    parking: bool | None = None
    gated: bool | None = None
    no_brokerage: bool | None = None
    amenities: list[Amenity] = Field(default_factory=list)
    near_metro: bool | None = None
    commute_to: str | None = Field(default=None, description="Workplace or place name for a commute limit")
    commute_minutes: int | None = Field(default=None, ge=5, le=180)
    commute_mode: CommuteMode | None = None
    soft: list[str] = Field(default_factory=list, description="Nice-to-haves, e.g. 'quiet', 'sunny', 'park nearby'")
    clear: list[str] = Field(default_factory=list, description="Filters the tenant asked to drop")
    result_number: int | None = Field(default=None, ge=1, le=20,
                                      description="For ask_about_result: 1 for 'the first one', 2 for 'the 2nd'")
    question: str | None = Field(default=None, description="For ask_about_result: what they want to know")
    semantic_query: str = Field(default="", description="The descriptive part of the request, for text search")

    @field_validator("tenant_type", "commute_mode", "commute_to", "city", mode="before")
    @classmethod
    def _blank(cls, v: object) -> object:  # "" means not said
        return None if isinstance(v, str) and not v.strip() else v

    @field_validator("pets", "parking", "gated", "no_brokerage", "near_metro", mode="before")
    @classmethod
    def _yes(cls, v: object) -> object:  # "dog", "car" → yes; "no", "" → not said / no
        if isinstance(v, str):
            t = v.strip().lower()
            return None if not t else t not in ("no", "false", "none", "not allowed")
        return v

    @field_validator("city", mode="before")
    @classmethod
    def _city(cls, v: object) -> object:  # "Mumbai" / "Bengaluru" → the slug, instead of a retry
        from app.llm.prompts.listing import CITY_ALIASES

        return CITY_ALIASES.get(v.strip().lower()) if isinstance(v, str) else v  # a city we don't cover → unset


# ------------------------------------------------------------------ slang (code, not the model)

CHEAPER = re.compile(r"\b(cheaper|thoda sasta|sasta|less expensive|lower budget|kam budget)\b", re.I)
PRICIER = re.compile(r"\b(bigger budget|can stretch|thoda zyada|more budget)\b", re.I)
NEAR_METRO = re.compile(
    r"\b(near|close to|walking distance (?:to|from)|paas)\b.{0,15}\bmetro\b|\bmetro\b.{0,10}\b(paas|nearby|near)\b",
    re.I,
)


ANY_AREA = re.compile(r"\b(any area|anywhere|any locality|koi bhi (?:area|jagah))\b", re.I)


def apply_slang(message: str, upd: SearchUpdate, prev: SearchFilters) -> SearchUpdate:
    from app.pipeline.query_heuristics import heuristic_search

    u = upd.model_copy(deep=True)
    if ANY_AREA.search(message) and "locality_ids" not in u.clear:
        u.clear.append("locality_ids")
    u.clear = ["locality_ids" if c in ("locality_names", "localities", "locality") else c for c in u.clear]
    found = heuristic_search(message)
    if u.intent == "ask_about_result" and u.result_number is None:  # "the 2nd one" read in code too
        u.result_number = found.get("result_number")
    if u.intent == "search":  # fields the model left empty but the message plainly states
        for name in ("bhk", "rent_max", "rent_min", "tenant_type", "pets", "parking", "gated", "no_brokerage"):
            if found.get(name) not in (None, []) and getattr(u, name) in (None, []):
                setattr(u, name, found[name])
    if u.intent == "search" and not u.locality_names and found.get("locality_names"):  # "what about X instead"
        u.locality_names = found["locality_names"]
        u.replace_localities = u.replace_localities or bool(found.get("replace_localities"))
        if u.replace_localities and "locality_ids" in u.clear:
            u.clear.remove("locality_ids")
    if CHEAPER.search(message) and u.rent_max is None and prev.rent_max:
        u.rent_max = int(round(prev.rent_max * 0.9, -2))
    if PRICIER.search(message) and u.rent_max is None and prev.rent_max:
        u.rent_max = int(round(prev.rent_max * 1.1, -2))
    if NEAR_METRO.search(message):
        u.near_metro = True
    return u


# ------------------------------------------------------------------ merge


class FilterChange(BaseModel):
    field: str
    before: Any = None
    after: Any = None


def merge(prev: SearchFilters, upd: SearchUpdate, *, localities: list[tuple[UUID, str]],
          commute: Commute | None) -> tuple[SearchFilters, list[FilterChange]]:
    """Apply an update. `localities` and `commute` are already resolved by the caller (DB lookups)."""
    base = SearchFilters(city=prev.city) if upd.new_search else prev
    f = base.model_copy(deep=True)
    if upd.city and upd.city != f.city:
        f = SearchFilters(city=upd.city)  # another city: earlier places and commutes no longer apply
    for name in upd.clear:
        if name in CLEARABLE:
            default = SearchFilters.model_fields[name].get_default(call_default_factory=True)
            setattr(f, name, default)
            if name == "locality_ids":
                f.locality_names = []
    if localities:
        ids = [i for i, _ in localities]
        names = [n for _, n in localities]
        if upd.replace_localities or upd.new_search:
            f.locality_ids, f.locality_names = ids, names
        else:
            for i, n in zip(ids, names, strict=True):
                if i not in f.locality_ids:
                    f.locality_ids.append(i)
                    f.locality_names.append(n)
        f.bbox = None
    for name in ("rent_min", "rent_max", "deposit_max", "tenant_type", "pets", "parking", "gated", "no_brokerage"):
        v = getattr(upd, name)
        if name in ("rent_min", "rent_max") and v is not None and v < MIN_RENT:
            continue  # "rent under 1" is not a real budget
        if v is not None:
            setattr(f, name, v)
    if f.rent_min is not None and f.rent_max is not None and f.rent_min > f.rent_max:
        f.rent_min = None
    if upd.bhk:
        f.bhk = sorted(set(upd.bhk))
    if upd.furnishing:
        f.furnishing = list(dict.fromkeys(upd.furnishing))
    for a in upd.amenities:
        if a not in f.amenities:
            f.amenities.append(a)
    if upd.near_metro is True:
        f.near_metro_m = f.near_metro_m or 1000
    elif upd.near_metro is False:
        f.near_metro_m = None
    if commute is not None:
        f.commute = commute
    elif f.commute and upd.commute_minutes:
        f.commute = f.commute.model_copy(update={"max_minutes": upd.commute_minutes})
    for s in upd.soft:
        if s.lower() not in (x.lower() for x in f.soft):
            f.soft.append(s)
    if upd.semantic_query.strip():
        f.semantic_query = upd.semantic_query.strip()[:300]
    return f, diff(prev, f)


def diff(a: SearchFilters, b: SearchFilters) -> list[FilterChange]:
    da, db = a.model_dump(mode="json"), b.model_dump(mode="json")
    return [FilterChange(field=k, before=da[k], after=db[k]) for k in da
            if da[k] != db[k] and k not in ("locality_names", "semantic_query")]


# ------------------------------------------------------------------ display

FURN = {"unfurnished": "unfurnished", "semi": "semi-furnished", "full": "fully furnished"}


def _inr(v: int) -> str:
    return f"₹{v / 100_000:g}L" if v >= 100_000 else f"₹{v / 1000:g}k"


def chips(f: SearchFilters) -> list[dict[str, str]]:
    """Removable filter chips: {field, label}. Removing one clears that field."""
    out: list[dict[str, str]] = []
    if f.locality_names:
        names = f.locality_names
        label = ", ".join(names) if len(names) <= 3 else f"{', '.join(names[:2])} +{len(names) - 2} more"
        out.append({"field": "locality_ids", "label": label})
    if f.bbox:
        out.append({"field": "bbox", "label": "Map area"})
    if f.bhk:
        out.append({"field": "bhk", "label": "/".join(str(b) for b in f.bhk) + " BHK"})
    if f.rent_max is not None:
        out.append({"field": "rent_max", "label": f"Up to {_inr(f.rent_max)}"})
    if f.rent_min is not None:
        out.append({"field": "rent_min", "label": f"From {_inr(f.rent_min)}"})
    if f.deposit_max is not None:
        out.append({"field": "deposit_max", "label": f"Deposit ≤ {_inr(f.deposit_max)}"})
    if f.furnishing:
        out.append({"field": "furnishing", "label": " or ".join(FURN[x] for x in f.furnishing)})
    if f.tenant_type:
        out.append({"field": "tenant_type", "label": "For families" if f.tenant_type == "family" else
                    "Bachelors OK"})
    for name, label in (("pets", "Pets OK"), ("parking", "Parking"), ("gated", "Gated"),
                        ("no_brokerage", "No brokerage")):
        if getattr(f, name):
            out.append({"field": name, "label": label})
    if f.amenities:
        out.append({"field": "amenities", "label": ", ".join(a.replace("_", " ") for a in f.amenities)})
    if f.near_metro_m:
        out.append({"field": "near_metro_m", "label": f"Metro ≤ {f.near_metro_m / 1000:g} km"})
    if f.commute:
        out.append({"field": "commute", "label": f"≤ {f.commute.max_minutes} min to {f.commute.poi_name}"})
    if f.available_by:
        out.append({"field": "available_by", "label": f"Available by {f.available_by:%-d %b}"})
    if f.soft:
        out.append({"field": "soft", "label": "Prefers " + ", ".join(f.soft)})
    return out
