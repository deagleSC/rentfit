"""Locality name → id (backend plan §11): fuzzy match on OSM names with pg_trgm."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from app.core.db import Tx

MIN_SIMILARITY = 0.45


class LocalityMatch(BaseModel):
    id: UUID
    name: str
    city: str
    similarity: float


async def find(tx: Tx, name: str, city: str | None = None) -> LocalityMatch | None:
    row = await tx.fetchone(
        """
        select id, name, city, extensions.similarity(lower(name), lower(%(q)s)) as sim
        from localities
        where (%(city)s::text is null or city = %(city)s)
          and (lower(name) = lower(%(q)s) or extensions.similarity(lower(name), lower(%(q)s)) >= %(min)s)
        order by lower(name) = lower(%(q)s) desc, sim desc
        limit 1
        """,
        {"q": name.strip(), "city": city, "min": MIN_SIMILARITY},
    )
    if row is None:
        return None
    return LocalityMatch(id=row["id"], name=row["name"], city=row["city"], similarity=float(row["sim"]))
