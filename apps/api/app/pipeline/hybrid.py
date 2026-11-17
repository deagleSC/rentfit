"""Hybrid search (backend plan §13): SQL hard filters → vector + full-text ranks → RRF.

Hard filters decide what can be shown; text only orders it. Listings that match the filters but
are not embedded yet (published seconds ago) are appended after the ranked ones.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.core.db import Tx
from app.domain.filters import SearchFilters
from app.services.embeddings import Embedder, to_pgvector

RRF_K = 60
TOP = 50
MAX_CANDIDATES = 2000
_WORD = re.compile(r"[a-z0-9]{2,}")
STOP = {"bhk", "flat", "flats", "for", "in", "near", "with", "and", "the", "rent", "want", "need", "looking",
        "chahiye", "mein", "ka", "ki", "ke", "a", "an", "to", "of", "me", "i", "under", "below", "around"}


def where(f: SearchFilters) -> tuple[str, list[Any]]:
    """SQL conditions over `public_listings p` for the hard filters."""
    c: list[str] = []
    a: list[Any] = []
    if f.city:
        c.append("p.city = %s")
        a.append(f.city)
    if f.locality_ids:
        c.append("p.locality_id = any(%s)")
        a.append(f.locality_ids)
    if f.bbox:
        c.append("st_intersects(p.location, st_makeenvelope(%s, %s, %s, %s, 4326)::geography)")
        a.extend(f.bbox)
    if f.bhk:
        c.append("p.bhk = any(%s)")
        a.append(f.bhk)
    if f.rent_min is not None:
        c.append("p.rent >= %s")
        a.append(f.rent_min)
    if f.rent_max is not None:
        c.append("p.rent <= %s")
        a.append(f.rent_max)
    if f.deposit_max is not None:
        c.append("p.deposit <= %s")
        a.append(f.deposit_max)
    if f.furnishing:
        c.append("p.furnishing = any(%s)")
        a.append(f.furnishing)
    if f.tenant_type:
        c.append("p.tenant_pref in ('any', %s)")
        a.append(f.tenant_type)
    if f.pets:
        c.append("p.pets")
    if f.parking:
        c.append("p.parking in ('bike', 'car', 'both')")
    if f.gated:
        c.append("p.gated")
    if f.no_brokerage:
        c.append("p.no_brokerage")
    if f.amenities:
        c.append("p.amenities @> %s::text[]")
        a.append(f.amenities)
    if f.near_metro_m:
        c.append("exists (select 1 from pois m where m.city = p.city and m.kind = 'metro_station'"
                 " and st_dwithin(m.location, p.location, %s))")
        a.append(f.near_metro_m)
    if f.available_by:
        c.append("p.available_from <= %s")
        a.append(f.available_by)
    return (" and ".join(c) or "true"), a


def text_query(f: SearchFilters) -> str:
    return " ".join([f.semantic_query, *f.soft]).strip()


def or_tsquery(text: str) -> str:
    words = [w for w in _WORD.findall(text.lower()) if w not in STOP]
    return " | ".join(dict.fromkeys(words))


def rrf(*rankings: list[UUID], k: int = RRF_K) -> dict[UUID, float]:
    scores: dict[UUID, float] = {}
    for ranking in rankings:
        for rank, lid in enumerate(ranking, start=1):
            scores[lid] = scores.get(lid, 0.0) + 1.0 / (k + rank)
    return scores


@dataclass
class Hit:
    id: UUID
    score: float  # 0..1, relative within this result set


async def candidates(tx: Tx, f: SearchFilters) -> list[UUID]:
    cond, args = where(f)
    rows = await tx.fetchall(
        f"select p.id from public_listings p where {cond} order by p.published_at desc limit %s",
        (*args, MAX_CANDIDATES),
    )
    return [r["id"] for r in rows]


async def search(tx: Tx, f: SearchFilters, embedder: Embedder, top: int = TOP,
                 vectors: dict[str, list[float]] | None = None) -> list[Hit]:
    """`vectors` caches query embeddings across calls (the relax ladder re-searches the same text)."""
    ids = await candidates(tx, f)
    if not ids:
        return []
    q = text_query(f)
    if not q:
        return [Hit(i, 1.0 - n / len(ids)) for n, i in enumerate(ids[:top])]
    cache = vectors if vectors is not None else {}
    if q not in cache:
        [cache[q]] = await embedder.embed([q])
    vec = cache[q]
    vrows = await tx.fetchall(
        """
        select listing_id, min(embedding <=> %s::extensions.vector) as d from listing_chunks
        where listing_id = any(%s) group by listing_id order by d limit %s
        """,
        (to_pgvector(vec), ids, top),
    )
    tsq = or_tsquery(q)
    trows = await tx.fetchall(
        """
        select listing_id, max(ts_rank(tsv, to_tsquery('simple', %s))) as r from listing_chunks
        where listing_id = any(%s) and tsv @@ to_tsquery('simple', %s)
        group by listing_id order by r desc limit %s
        """,
        (tsq, ids, tsq, top),
    ) if tsq else []
    fused = rrf([r["listing_id"] for r in vrows], [r["listing_id"] for r in trows])
    ranked = sorted(fused, key=lambda i: -fused[i])
    if len(ranked) < top:  # filter matches not embedded yet (just published), newest first
        ranked += [i for i in ids if i not in fused][: top - len(ranked)]
    best = max(fused.values(), default=1.0)
    return [Hit(i, fused.get(i, 0.0) / best) for i in ranked[:top]]
