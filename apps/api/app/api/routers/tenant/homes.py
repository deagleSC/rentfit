"""Listing detail, shortlists and saved searches for tenants (backend plan §7.3)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Response
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from app.core.auth import PrincipalDep, require_role, user_tx
from app.core.errors import ERROR_RESPONSES, AppError, Ok, ok
from app.domain.filters import Commute, CommuteMode, SearchFilters, chips
from app.services import search_results as res
from app.services.storage import StorageError, get_storage

router = APIRouter(prefix="/v1", tags=["tenant"], responses=ERROR_RESPONSES)


class PhotoUrls(BaseModel):
    url: str
    thumb_url: str


class NearbyPoi(BaseModel):
    id: UUID
    name: str
    kind: str
    metres: int
    location: tuple[float, float]


class LocalityNote(BaseModel):
    chunk_id: int
    text: str
    source: str


class ListingDetail(BaseModel):
    id: UUID
    title: str | None
    description: str | None
    city: str
    locality_id: UUID
    locality: str
    location: tuple[float, float]
    bhk: int
    rent: int
    deposit: int | None
    maintenance: int | None
    furnishing: str
    sqft: int | None
    floor: int | None
    total_floors: int | None
    tenant_pref: str
    pets: bool | None
    parking: str | None
    gated: bool | None
    no_brokerage: bool | None
    available_from: date | None
    amenities: list[str]
    published_at: datetime
    photos: list[PhotoUrls]
    nearby: list[NearbyPoi]
    notes: list[LocalityNote]
    commute: res.CommuteInfo | None = None
    shortlisted: bool
    enquiry_id: UUID | None


@router.get("/listings/{listing_id}", response_model=Ok[ListingDetail])
async def listing_detail(listing_id: UUID, principal: PrincipalDep, poi_id: UUID | None = None,
                         mode: CommuteMode = "car") -> Ok[ListingDetail]:
    async with user_tx(principal) as (tx, user):
        require_role(user, "tenant")
        row = await tx.fetchone(
            """
            select p.*, loc.name as locality, st_x(p.location::geometry) as lng, st_y(p.location::geometry) as lat,
                   exists (select 1 from shortlists s where s.listing_id = p.id) as shortlisted,
                   (select e.id from enquiries e where e.listing_id = p.id and e.tenant_id = %s) as enquiry_id
            from public_listings p join localities loc on loc.id = p.locality_id where p.id = %s
            """, (user.user_id, listing_id))
        if row is None:
            raise AppError(404, "not_found", "This home is no longer listed.")
        photos = await tx.fetchall("select storage_path, thumb_path from listing_photos"
                                   " where listing_id = %s and confirmed order by position", (listing_id,))
        try:
            paths = [p for r in photos for p in (r["storage_path"], r["thumb_path"])]
            urls = await get_storage().signed_downloads(paths)
        except StorageError:
            urls = {}
        nearby = await tx.fetchall(
            """
            select id, name, kind, st_distance(location, %(g)s::geography) as metres,
                   st_x(location::geometry) as lng, st_y(location::geometry) as lat
            from pois where city = %(city)s and kind in ('metro_station', 'rail_station', 'tech_park', 'hospital')
              and st_dwithin(location, %(g)s::geography, 4000)
            order by location <-> %(g)s::geography limit 8
            """, {"g": f"SRID=4326;POINT({row['lng']} {row['lat']})", "city": row["city"]})
        notes = await tx.fetchall("select c.id, c.content, n.source from locality_chunks c join locality_notes n"
                                  " on n.id = c.note_id where c.locality_id = %s order by c.chunk_index",
                                  (row["locality_id"],))
        commute = None
        if poi_id:
            poi = await tx.fetchone("select id, name from pois where id = %s", (poi_id,))
            if poi is None:
                raise AppError(404, "unknown_poi", "That place is not on the map.")
            f = SearchFilters(commute=Commute(poi_id=poi["id"], poi_name=poi["name"], max_minutes=180, mode=mode))
            commute = (await res.commutes(tx, f, [listing_id])).get(listing_id)
        data: dict[str, Any] = {k: row[k] for k in ListingDetail.model_fields if k in row and k != "location"}
        return ok(ListingDetail(
            **data, location=(row["lng"], row["lat"]),
            photos=[PhotoUrls(url=urls[r["storage_path"]], thumb_url=urls[r["thumb_path"]]) for r in photos
                    if r["storage_path"] in urls and r["thumb_path"] in urls],
            nearby=[NearbyPoi(id=n["id"], name=n["name"], kind=n["kind"], metres=round(n["metres"]),
                              location=(n["lng"], n["lat"])) for n in nearby],
            notes=[LocalityNote(chunk_id=n["id"], text=n["content"], source=n["source"]) for n in notes],
            commute=commute,
        ))


# ------------------------------------------------------------------ shortlists


@router.get("/tenant/shortlists", response_model=Ok[list[res.ListingCard]])
async def list_shortlist(principal: PrincipalDep) -> Ok[list[res.ListingCard]]:
    async with user_tx(principal) as (tx, user):
        require_role(user, "tenant")
        rows = await tx.fetchall("select s.listing_id from shortlists s join public_listings p on p.id = s.listing_id"
                                 " order by s.created_at desc")
        return ok(await res.cards(tx, [r["listing_id"] for r in rows]))


@router.put("/tenant/shortlists/{listing_id}", status_code=204)
async def add_shortlist(listing_id: UUID, principal: PrincipalDep) -> Response:
    async with user_tx(principal) as (tx, user):
        require_role(user, "tenant")
        if await tx.fetchone("select 1 from public_listings where id = %s", (listing_id,)) is None:
            raise AppError(404, "not_found", "This home is no longer listed.")
        await tx.conn.execute("insert into shortlists (tenant_id, listing_id) values (%s, %s) on conflict do nothing",
                              (user.user_id, listing_id))
    return Response(status_code=204)


@router.delete("/tenant/shortlists/{listing_id}", status_code=204)
async def remove_shortlist(listing_id: UUID, principal: PrincipalDep) -> Response:
    async with user_tx(principal) as (tx, user):
        require_role(user, "tenant")
        await tx.conn.execute("delete from shortlists where tenant_id = %s and listing_id = %s",
                              (user.user_id, listing_id))
    return Response(status_code=204)


# ------------------------------------------------------------------ saved searches


class SavedSearchIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    filters: SearchFilters


class SavedSearch(BaseModel):
    id: UUID
    name: str
    filters: SearchFilters
    chips: list[dict[str, str]]
    created_at: datetime


def _saved(r: dict[str, Any]) -> SavedSearch:
    f = SearchFilters.model_validate(r["filters"])
    return SavedSearch(id=r["id"], name=r["name"], filters=f, chips=chips(f), created_at=r["created_at"])


@router.get("/tenant/saved-searches", response_model=Ok[list[SavedSearch]])
async def list_saved(principal: PrincipalDep) -> Ok[list[SavedSearch]]:
    async with user_tx(principal) as (tx, user):
        require_role(user, "tenant")
        rows = await tx.fetchall("select * from saved_searches order by created_at desc")
        return ok([_saved(dict(r)) for r in rows])


@router.post("/tenant/saved-searches", response_model=Ok[SavedSearch], status_code=201)
async def save_search(body: SavedSearchIn, principal: PrincipalDep) -> Ok[SavedSearch]:
    async with user_tx(principal) as (tx, user):
        require_role(user, "tenant")
        n = await tx.fetchone("select count(*) as n from saved_searches")
        if n and n["n"] >= 20:
            raise AppError(409, "too_many_saved", "You can keep up to 20 saved searches. Delete one first.")
        row = await tx.fetchone("insert into saved_searches (tenant_id, name, filters) values (%s, %s, %s) returning *",
                                (user.user_id, body.name.strip(), Jsonb(body.filters.model_dump(mode="json"))))
        assert row is not None
        return ok(_saved(dict(row)))


@router.delete("/tenant/saved-searches/{saved_id}", status_code=204)
async def delete_saved(saved_id: UUID, principal: PrincipalDep) -> Response:
    async with user_tx(principal) as (tx, user):
        require_role(user, "tenant")
        await tx.conn.execute("delete from saved_searches where id = %s", (saved_id,))
    return Response(status_code=204)
