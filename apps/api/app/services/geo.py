"""Pin → locality (backend plan §11 `locate`)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.core.db import Tx

NEAREST_WITHIN_M = 500  # a pin just outside every polygon (e.g. on the coast) snaps to the nearest one


class LocalityHit(BaseModel):
    locality_id: UUID
    name: str
    city: str
    inside: bool  # False when snapped to the nearest locality


async def locality_for(tx: Tx, lat: float, lng: float) -> LocalityHit | None:
    row: Any = await tx.fetchone(
        """
        with pt as (select st_point(%(lng)s, %(lat)s, 4326)::geography as g)
        select l.id, l.name, l.city, st_covers(l.boundary, pt.g) as inside
        from localities l, pt
        where st_dwithin(l.boundary, pt.g, %(within)s)
        order by st_covers(l.boundary, pt.g) desc, st_distance(l.boundary, pt.g)
        limit 1
        """,
        {"lat": lat, "lng": lng, "within": NEAREST_WITHIN_M},
    )
    if row is None:
        return None
    return LocalityHit(locality_id=row["id"], name=row["name"], city=row["city"], inside=row["inside"])
