"""Listing cards and enrichment for search results (backend plan §13 `enrich`)."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.core.db import Tx
from app.domain.filters import SearchFilters
from app.services import commute as commute_svc
from app.services.storage import StorageError, get_storage


class CommuteInfo(BaseModel):
    minutes: int
    provider: str  # "ors" | "haversine" (an estimate)
    mode: str
    to: str


class MetroInfo(BaseModel):
    name: str
    metres: int


class ListingCard(BaseModel):
    id: UUID
    title: str | None
    locality: str
    city: str
    bhk: int
    rent: int
    deposit: int | None
    furnishing: str
    tenant_pref: str
    available_from: date | None
    amenities: list[str]
    location: tuple[float, float]  # (lng, lat)
    thumb_url: str | None = None
    metro: MetroInfo | None = None
    commute: CommuteInfo | None = None
    shortlisted: bool = False


class Pin(BaseModel):
    id: UUID
    location: tuple[float, float]
    rent: int
    bhk: int
    locality: str


_CARD_SQL = """
    select p.id, p.title, loc.name as locality, p.city, p.bhk, p.rent, p.deposit, p.furnishing, p.tenant_pref,
           p.available_from, p.amenities, p.description,
           st_x(p.location::geometry) as lng, st_y(p.location::geometry) as lat,
           (select ph.thumb_path from listing_photos ph where ph.listing_id = p.id and ph.confirmed
            order by ph.position limit 1) as thumb_path,
           m.name as metro_name, m.metres as metro_m,
           exists (select 1 from shortlists s where s.listing_id = p.id and s.tenant_id = app.current_user_id())
             as shortlisted
    from public_listings p
    join localities loc on loc.id = p.locality_id
    left join lateral (
      select name, st_distance(location, p.location) as metres from pois
      where city = p.city and kind = 'metro_station' and st_dwithin(location, p.location, 5000)
      order by location <-> p.location limit 1) m on true
    where p.id = any(%s)
"""


async def card_rows(tx: Tx, ids: list[UUID]) -> dict[UUID, dict[str, Any]]:
    if not ids:
        return {}
    rows = await tx.fetchall(_CARD_SQL, (ids,))
    return {r["id"]: dict(r) for r in rows}


async def cards(tx: Tx, ids: list[UUID], commutes: dict[UUID, CommuteInfo] | None = None,
                rows: dict[UUID, dict[str, Any]] | None = None) -> list[ListingCard]:
    """Cards in the order of `ids` (unpublished ones silently left out)."""
    rows = rows if rows is not None else await card_rows(tx, ids)
    paths = [r["thumb_path"] for r in rows.values() if r["thumb_path"]]
    try:
        urls = await get_storage().signed_downloads(paths)
    except StorageError:
        urls = {}
    out = []
    for i in ids:
        r = rows.get(i)
        if r is None:
            continue
        out.append(ListingCard(
            id=r["id"], title=r["title"], locality=r["locality"], city=r["city"], bhk=r["bhk"], rent=r["rent"],
            deposit=r["deposit"], furnishing=r["furnishing"], tenant_pref=r["tenant_pref"],
            available_from=r["available_from"], amenities=r["amenities"], location=(r["lng"], r["lat"]),
            thumb_url=urls.get(r["thumb_path"] or ""),
            metro=MetroInfo(name=r["metro_name"], metres=round(r["metro_m"])) if r["metro_name"] else None,
            commute=(commutes or {}).get(i), shortlisted=r["shortlisted"],
        ))
    return out


async def pins(tx: Tx, ids: list[UUID]) -> list[Pin]:
    if not ids:
        return []
    rows = await tx.fetchall(
        "select p.id, st_x(p.location::geometry) as lng, st_y(p.location::geometry) as lat, p.rent, p.bhk,"
        " loc.name as locality from public_listings p join localities loc on loc.id = p.locality_id"
        " where p.id = any(%s)", (ids,))
    by_id = {r["id"]: r for r in rows}
    return [Pin(id=i, location=(by_id[i]["lng"], by_id[i]["lat"]), rent=by_id[i]["rent"], bhk=by_id[i]["bhk"],
                locality=by_id[i]["locality"]) for i in ids if i in by_id]


async def commutes(tx: Tx, f: SearchFilters, ids: list[UUID]) -> dict[UUID, CommuteInfo]:
    if f.commute is None or not ids:
        return {}
    rows = await tx.fetchall(
        "select id, st_y(location::geometry) as lat, st_x(location::geometry) as lng from public_listings"
        " where id = any(%s)", (ids,))
    got = await commute_svc.minutes_to(tx, {r["id"]: (r["lat"], r["lng"]) for r in rows}, f.commute.poi_id,
                                       f.commute.mode)
    return {i: CommuteInfo(minutes=m.minutes, provider=m.provider, mode=f.commute.mode, to=f.commute.poi_name)
            for i, m in got.items()}


async def soft_scores(tx: Tx, soft: list[str], ids: list[UUID]) -> dict[UUID, float]:
    """Share of soft preferences each listing's text or amenities mention (0..1)."""
    if not soft or not ids:
        return {}
    rows = await tx.fetchall(
        """
        select p.id, lower(coalesce(p.description, '') || ' ' || coalesce(p.title, '') || ' ' ||
                           array_to_string(p.amenities, ' ')) as text
        from public_listings p where p.id = any(%s)
        """, (ids,))
    terms = [s.lower() for s in soft]
    return {r["id"]: sum(1 for t in terms if any(w in r["text"] for w in t.replace("_", " ").split())) / len(terms)
            for r in rows}


async def locality_notes(tx: Tx, locality_ids: list[UUID]) -> list[dict[str, Any]]:
    """The OSM note chunk for each locality, in the given order."""
    if not locality_ids:
        return []
    rows = await tx.fetchall(
        "select distinct on (c.locality_id) c.id, c.locality_id, l.name as locality, c.content"
        " from locality_chunks c join localities l on l.id = c.locality_id"
        " where c.locality_id = any(%s) order by c.locality_id, c.chunk_index", (locality_ids,))
    by = {r["locality_id"]: dict(r) for r in rows}
    return [by[i] for i in dict.fromkeys(locality_ids) if i in by]


async def find_poi(tx: Tx, name: str, city: str | None) -> dict[str, Any] | None:
    row = await tx.fetchone(
        """
        select id, name, city, extensions.similarity(lower(name), lower(%(q)s)) as sim from pois
        where (%(city)s::text is null or city = %(city)s)
          and (lower(name) like '%%' || lower(%(q)s) || '%%'
               or extensions.similarity(lower(name), lower(%(q)s)) >= 0.35)
        order by kind = 'tech_park' desc, lower(name) = lower(%(q)s) desc, sim desc limit 1
        """,
        {"q": name.strip(), "city": city},
    )
    return dict(row) if row else None
