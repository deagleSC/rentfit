"""Write an OSM note for every locality and embed it (backend plan §14.1).

    uv run python -m scripts.build_locality_notes [--city bangalore]

Idempotent: upserts one `osm` note per locality, then indexes it (unchanged chunks keep their
embeddings). Runs after `scripts.seed_reference`. No model calls.
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

from psycopg.types.json import Jsonb

from app.core.db import Tx, close_pool, system_claims, transaction
from app.pipeline.locality_notes import note_facts, note_text
from app.services import retrieval_index
from app.services.embeddings import get_embedder

NEAREST_KINDS = ("metro_station", "rail_station", "hospital")


async def _nearest(tx: Tx, loc: dict[str, Any], kind: str) -> dict[str, Any] | None:
    return await tx.fetchone(
        """
        select name, st_distance(location, %s::geography) as metres from pois
        where city = %s and kind = %s and st_dwithin(location, %s::geography, 15000)
        order by location <-> %s::geography limit 1
        """,
        (loc["centroid"], loc["city"], kind, loc["centroid"], loc["centroid"]),
    )


async def build(tx: Tx, loc: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    nearest = {k: await _nearest(tx, loc, k) for k in NEAREST_KINDS}
    parks = await tx.fetchall(
        """
        select name, st_distance(location, %s::geography) as metres from pois
        where city = %s and kind = 'tech_park' and st_dwithin(location, %s::geography, 5000)
        order by 2 limit 5
        """,
        (loc["centroid"], loc["city"], loc["centroid"]),
    )
    facts = note_facts(loc["facts"] or {}, {k: dict(v) if v else None for k, v in nearest.items()},
                       [dict(p) for p in parks])
    return note_text(loc["name"], loc["city"], facts), facts


async def main(city: str | None) -> None:
    embedder = get_embedder()
    print(f"embedder: {embedder.name}")
    try:
        async with transaction(system_claims()) as tx:
            locs = await tx.fetchall(
                "select id, city, name, facts, centroid::text as centroid from localities"
                " where %s::text is null or city = %s order by city, name",
                (city, city),
            )
        done = 0
        for loc in locs:
            async with transaction(system_claims()) as tx:  # one commit per locality: resumable
                body, facts = await build(tx, dict(loc))
                row = await tx.fetchone(
                    """
                    insert into locality_notes (locality_id, source, source_url, body, facts)
                    values (%s, 'osm', 'https://www.openstreetmap.org/copyright', %s, %s)
                    on conflict (locality_id, source) do update
                      set body = excluded.body, facts = excluded.facts, updated_at = now()
                    returning id
                    """,
                    (loc["id"], body, Jsonb(facts)),
                )
                assert row is not None
                await retrieval_index.index_locality_note(tx, row["id"], embedder)
            done += 1
            if done % 25 == 0:
                print(f"  {done}/{len(locs)}")
        print(f"{done} locality notes written and embedded")
    finally:
        await close_pool()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--city")
    asyncio.run(main(ap.parse_args().city))
