"""Retrieval eval (backend plan §15.2): vector vs full-text vs hybrid, on the seeded listings.

    uv run python -m evals.run_retrieval

Each query runs over every published listing in its city (no hard filters: this measures how well
the text side ranks). A listing is relevant when its structured data matches the query's predicate
(e.g. "gym and pool" → both amenities), so relevance does not depend on any model. No LLM calls;
the query is embedded by the same embedder as production (gte-small via the Edge Function).
"""

from __future__ import annotations

import asyncio
import math
from typing import Any
from uuid import UUID

from app.core.db import Tx, close_pool, system_claims, transaction
from app.domain.filters import SearchFilters
from app.pipeline import hybrid
from app.services.embeddings import get_embedder, to_pgvector
from evals.common import load, write_report

K = 10


def ndcg(ranked: list[UUID], rel: set[UUID], k: int = K) -> float:
    dcg = sum(1 / math.log2(i + 2) for i, x in enumerate(ranked[:k]) if x in rel)
    ideal = sum(1 / math.log2(i + 2) for i in range(min(k, len(rel))))
    return dcg / ideal if ideal else 0.0


def recall(ranked: list[UUID], rel: set[UUID], k: int = K) -> float:
    return len(set(ranked[:k]) & rel) / min(k, len(rel)) if rel else 0.0


async def vector_only(tx: Tx, ids: list[UUID], vec: list[float]) -> list[UUID]:
    rows = await tx.fetchall("select listing_id from listing_chunks where listing_id = any(%s) group by listing_id"
                             " order by min(embedding <=> %s::extensions.vector)", (ids, to_pgvector(vec)))
    return [r["listing_id"] for r in rows]


async def text_only(tx: Tx, ids: list[UUID], q: str) -> list[UUID]:
    tsq = hybrid.or_tsquery(q)
    if not tsq:
        return []
    rows = await tx.fetchall("select listing_id from listing_chunks where listing_id = any(%s)"
                             " and tsv @@ to_tsquery('simple', %s) group by listing_id"
                             " order by max(ts_rank(tsv, to_tsquery('simple', %s))) desc", (ids, tsq, tsq))
    return [r["listing_id"] for r in rows]


async def main() -> None:
    embedder = get_embedder()
    print("embedder:", embedder.name)
    cases: list[dict[str, Any]] = []
    scores: dict[str, dict[str, list[float]]] = {m: {"ndcg": [], "recall": []} for m in ("vector", "text", "hybrid")}
    try:
        for c in load("retrieval"):
            async with transaction(system_claims()) as tx:
                f = SearchFilters(city=c["city"], semantic_query=c["q"])
                ids = await hybrid.candidates(tx, f)
                rel_rows = await tx.fetchall(f"select id from public_listings where city = %s and ({c['rel']})",
                                             (c["city"],))
                rel = {r["id"] for r in rel_rows}
                [vec] = await embedder.embed([c["q"]])
                runs = {
                    "vector": await vector_only(tx, ids, vec),
                    "text": await text_only(tx, ids, c["q"]),
                    "hybrid": [h.id for h in await hybrid.search(tx, f, embedder, vectors={c["q"]: vec})],
                }
            row: dict[str, Any] = {"city": c["city"], "q": c["q"], "relevant": len(rel), "of": len(ids)}
            for m, ranked in runs.items():
                n, r = ndcg(ranked, rel), recall(ranked, rel)
                scores[m]["ndcg"].append(n)
                scores[m]["recall"].append(r)
                row[m] = {"ndcg@10": round(n, 3), "recall@10": round(r, 3)}
            cases.append(row)
            print(f"{c['city'][:3]} {c['q'][:40]:40} rel={len(rel):3}  " +
                  "  ".join(f"{m}={row[m]['ndcg@10']:.2f}" for m in runs))
    finally:
        await close_pool()
    mean = {m: {k: round(sum(v) / len(v), 3) for k, v in s.items()} for m, s in scores.items()}
    # Base rate: what a random ordering scores on average (relevant share of the city's listings).
    base = round(sum(c["relevant"] / c["of"] for c in cases) / len(cases), 3)
    write_report("retrieval", f"{embedder.name}-rrf{hybrid.RRF_K}",
                 {"ndcg@10_vector": mean["vector"]["ndcg"], "ndcg@10_text": mean["text"]["ndcg"],
                  "ndcg@10_hybrid": mean["hybrid"]["ndcg"], "recall@10_vector": mean["vector"]["recall"],
                  "recall@10_text": mean["text"]["recall"], "recall@10_hybrid": mean["hybrid"]["recall"],
                  "relevant_share": base, "queries": len(cases)},
                 {"ndcg@10_hybrid": ">=0.70"}, cases)


if __name__ == "__main__":
    asyncio.run(main())
