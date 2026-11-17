"""Write search chunks (backend plan §9). Runs in system context, from the embed jobs and the seed.

Chunks whose text did not change keep their stored embedding, so an edit to the rent re-embeds
only the summary chunk.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg

from app.core.db import Tx
from app.pipeline.chunk import content_hash, listing_chunks, split
from app.services.embeddings import Embedder, get_embedder, to_pgvector


async def _embed_reusing(tx: Tx, table: str, key: str, key_id: UUID, texts: list[str],
                         embedder: Embedder) -> list[str]:
    """Vectors (as pgvector text) for `texts`, reusing stored ones with the same content hash."""
    hashes = [content_hash(t) for t in texts]
    rows = await tx.fetchall(
        f"select content_hash, embedding::text as e from {table} where {key} = %s and content_hash = any(%s)",
        (key_id, hashes),
    )
    known = {r["content_hash"]: r["e"] for r in rows}
    todo = [t for t, h in zip(texts, hashes, strict=True) if h not in known]
    fresh = iter(await embedder.embed(todo)) if todo else iter(())
    return [known[h] if h in known else to_pgvector(next(fresh)) for h in hashes]


async def index_listing(tx: Tx, listing_id: UUID, embedder: Embedder | None = None) -> int:
    """Rewrite a listing's chunks; delete them if it is not published. Returns the chunk count."""
    row = await tx.fetchone(
        """
        select l.*, loc.name as locality_name from listings l
        left join localities loc on loc.id = l.locality_id where l.id = %s
        """,
        (listing_id,),
    )
    if row is None or row["status"] != "published":
        await tx.conn.execute("delete from listing_chunks where listing_id = %s", (listing_id,))
        return 0
    texts = listing_chunks(dict(row))
    vectors = await _embed_reusing(tx, "listing_chunks", "listing_id", listing_id, texts, embedder or get_embedder())
    await tx.conn.execute("delete from listing_chunks where listing_id = %s", (listing_id,))
    try:
        async with tx.conn.transaction():  # savepoint: the listing may be deleted while we embedded
            await _insert(tx, "listing_chunks", ["listing_id"], [listing_id], texts, vectors)
    except psycopg.errors.ForeignKeyViolation:
        return 0
    return len(texts)


async def index_locality_note(tx: Tx, note_id: UUID, embedder: Embedder | None = None) -> int:
    note = await tx.fetchone("select id, locality_id, body from locality_notes where id = %s", (note_id,))
    if note is None:
        return 0
    texts = split(note["body"])
    vectors = await _embed_reusing(tx, "locality_chunks", "note_id", note_id, texts, embedder or get_embedder())
    await tx.conn.execute("delete from locality_chunks where note_id = %s", (note_id,))
    await _insert(tx, "locality_chunks", ["note_id", "locality_id"], [note_id, note["locality_id"]], texts, vectors)
    return len(texts)


async def _insert(tx: Tx, table: str, cols: list[str], vals: list[Any], texts: list[str], vectors: list[str]) -> None:
    if not texts:
        return
    names = ", ".join([*cols, "chunk_index", "content", "content_hash", "embedding"])
    marks = ", ".join(["%s"] * (len(cols) + 3) + ["%s::extensions.vector"])
    async with tx.conn.cursor() as cur:
        await cur.executemany(
            f"insert into {table} ({names}) values ({marks})",
            [(*vals, i, t, content_hash(t), v) for i, (t, v) in enumerate(zip(texts, vectors, strict=True))],
        )
