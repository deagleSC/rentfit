"""Reference data: cities, localities, POIs (backend plan §7.3). Signed-in users only."""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.core.auth import PrincipalDep, user_tx
from app.core.errors import ERROR_RESPONSES, AppError, Ok, ok

router = APIRouter(prefix="/v1", tags=["reference"], responses=ERROR_RESPONSES)

PoiKind = Literal["tech_park", "metro_station", "rail_station", "hospital", "college", "other"]


class City(BaseModel):
    slug: str
    name: str
    center: tuple[float, float]  # (lng, lat)
    default_zoom: float


class Locality(BaseModel):
    id: UUID
    city: str
    name: str
    centroid: tuple[float, float]
    median_rent: dict[str, int]
    boundary: dict[str, Any] | None = None  # GeoJSON MultiPolygon, only with ?geometry=true


class Poi(BaseModel):
    id: UUID
    city: str
    name: str
    kind: PoiKind
    location: tuple[float, float]


async def _check_city(tx: Any, city: str) -> None:
    if await tx.fetchone("select 1 from cities where slug = %s", (city,)) is None:
        raise AppError(404, "unknown_city", "That city is not supported.")


@router.get("/cities", response_model=Ok[list[City]])
async def list_cities(principal: PrincipalDep) -> Ok[list[City]]:
    async with user_tx(principal) as (tx, _):
        rows = await tx.fetchall(
            "select slug, name, st_x(center::geometry) as lng, st_y(center::geometry) as lat, default_zoom "
            "from cities order by name"
        )
    return ok([City(slug=r["slug"], name=r["name"], center=(r["lng"], r["lat"]), default_zoom=r["default_zoom"])
               for r in rows])


@router.get("/localities", response_model=Ok[list[Locality]], response_model_exclude_none=True)
async def list_localities(
    principal: PrincipalDep, city: str, geometry: bool = False
) -> Ok[list[Locality]]:
    async with user_tx(principal) as (tx, _):
        await _check_city(tx, city)
        rows = await tx.fetchall(
            "select id, city, name, median_rent, st_x(centroid::geometry) as lng, st_y(centroid::geometry) as lat, "
            "case when %s then st_asgeojson(boundary, 5) end as boundary "
            "from localities where city = %s order by name",
            (geometry, city),
        )
    return ok([
        Locality(id=r["id"], city=r["city"], name=r["name"], centroid=(r["lng"], r["lat"]),
                 median_rent=r["median_rent"], boundary=json.loads(r["boundary"]) if r["boundary"] else None)
        for r in rows
    ])


@router.get("/pois", response_model=Ok[list[Poi]])
async def list_pois(
    principal: PrincipalDep, city: str, kind: Annotated[list[PoiKind] | None, Query()] = None
) -> Ok[list[Poi]]:
    async with user_tx(principal) as (tx, _):
        await _check_city(tx, city)
        rows = await tx.fetchall(
            "select id, city, name, kind, st_x(location::geometry) as lng, st_y(location::geometry) as lat "
            "from pois where city = %s and (%s::text[] is null or kind = any(%s)) order by kind, name",
            (city, kind, kind),
        )
    return ok([Poi(id=r["id"], city=r["city"], name=r["name"], kind=r["kind"], location=(r["lng"], r["lat"]))
               for r in rows])
