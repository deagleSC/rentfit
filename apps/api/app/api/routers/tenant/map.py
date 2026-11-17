"""Map pins for tenants (backend plan §7.3). Phase 2: every published listing in a city.
Phase 3 replaces the query with `map_listings(bbox, filters)` over the `public_listings` view."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.auth import PrincipalDep, require_role, user_tx
from app.core.errors import ERROR_RESPONSES, AppError, Ok, ok

router = APIRouter(prefix="/v1/tenant", tags=["tenant"], responses=ERROR_RESPONSES)

MAX_PINS = 2000


class MapPin(BaseModel):
    id: UUID
    location: tuple[float, float]  # (lng, lat)
    bhk: int
    rent: int
    furnishing: str
    locality: str


@router.get("/map/listings", response_model=Ok[list[MapPin]])
async def map_listings(city: str, principal: PrincipalDep) -> Ok[list[MapPin]]:
    async with user_tx(principal) as (tx, user):
        require_role(user, "tenant")
        if await tx.fetchone("select 1 from cities where slug = %s", (city,)) is None:
            raise AppError(404, "unknown_city", "That city is not supported.")
        rows = await tx.fetchall(
            """
            select l.id, st_x(l.location::geometry) as lng, st_y(l.location::geometry) as lat,
                   l.bhk, l.rent, l.furnishing, loc.name as locality
            from listings l join localities loc on loc.id = l.locality_id
            where l.status = 'published' and l.city = %s
            order by l.published_at desc limit %s
            """,
            (city, MAX_PINS),
        )
    return ok([MapPin(id=r["id"], location=(r["lng"], r["lat"]), bhk=r["bhk"], rent=r["rent"],
                      furnishing=r["furnishing"], locality=r["locality"]) for r in rows])
