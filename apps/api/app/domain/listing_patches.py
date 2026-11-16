"""Typed edits to a listing (backend plan §8.2). Chat edits and form edits both end here.

A patch list is applied all-or-nothing: the result must validate as a ListingDraft.
Location is not patchable: it goes through PUT /location, which also looks up the locality.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from app.domain.listing import Amenity, ListingDraft
from app.pipeline.redact import strip_contacts

PATCHABLE: tuple[str, ...] = tuple(f for f in ListingDraft.model_fields if f not in ("location", "amenities"))


class SetField(BaseModel):
    op: Literal["set"] = "set"
    field: Literal[
        "city", "locality_id", "bhk", "rent", "deposit", "maintenance", "furnishing", "sqft", "floor",
        "total_floors", "tenant_pref", "pets", "parking", "gated", "no_brokerage", "available_from",
        "title", "description",
    ]
    value: Any = Field(description="New value; null clears the field")


class AddAmenity(BaseModel):
    op: Literal["add_amenity"] = "add_amenity"
    amenity: Amenity


class RemoveAmenity(BaseModel):
    op: Literal["remove_amenity"] = "remove_amenity"
    amenity: Amenity


Patch = Annotated[SetField | AddAmenity | RemoveAmenity, Field(discriminator="op")]
PatchList = TypeAdapter(list[Patch])


class PatchError(ValueError):
    def __init__(self, message: str, details: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.details = details or []


class Change(BaseModel):
    field: str
    before: Any
    after: Any


def apply_patches(draft: ListingDraft, patches: list[Any]) -> tuple[ListingDraft, list[Change]]:
    """Return the patched draft and the field-level diff. Raises PatchError if the result is invalid."""
    data = draft.model_dump()
    amenities: list[str] = list(data["amenities"])
    for p in patches:
        if isinstance(p, SetField):
            value = p.value
            if p.field == "description" and isinstance(value, str):
                value = strip_contacts(value)
            if p.field == "title" and isinstance(value, str):
                value = strip_contacts(value).strip() or None
            data[p.field] = value
        elif isinstance(p, AddAmenity):
            if p.amenity not in amenities:
                amenities.append(p.amenity)
        elif isinstance(p, RemoveAmenity):
            amenities = [a for a in amenities if a != p.amenity]
    data["amenities"] = amenities
    try:
        new = ListingDraft.model_validate(data)
    except ValidationError as exc:
        details = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
        raise PatchError("These changes are not valid.", details) from exc
    return new, diff(draft, new)


def diff(before: ListingDraft, after: ListingDraft) -> list[Change]:
    a, b = before.model_dump(mode="json"), after.model_dump(mode="json")
    return [Change(field=k, before=a[k], after=b[k]) for k in a if a[k] != b[k]]


def patches_from_form(before: ListingDraft, after: ListingDraft) -> list[Any]:
    """The minimal patch list that turns `before` into `after` (used by tests for chat/form parity)."""
    out: list[Any] = []
    for field in PATCHABLE:
        if getattr(before, field) != getattr(after, field):
            out.append(SetField(field=field, value=getattr(after, field)))
    for a in after.amenities:
        if a not in before.amenities:
            out.append(AddAmenity(amenity=a))
    for a in before.amenities:
        if a not in after.amenities:
            out.append(RemoveAmenity(amenity=a))
    return out
