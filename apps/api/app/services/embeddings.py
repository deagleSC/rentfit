"""Text embeddings (backend plan §9).

- `EdgeEmbedder`: the Supabase Edge Function `embed` (gte-small, 384 dims, normalised).
- `HashingEmbedder`: dev/test when EMBED_FUNCTION_URL is unset. Deterministic, no network: word and
  word-pair hashes into 384 buckets, normalised. Texts sharing words get a positive cosine, which is
  enough for tests and offline seeding; it is not a semantic model.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import re
from typing import Any, Protocol

import httpx

from app.core.config import get_settings

DIM = 384
BATCH = 32
RETRIES = 4
_WORD = re.compile(r"[a-z0-9]+")


class Embedder(Protocol):
    name: str

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class EmbedError(RuntimeError):
    pass


class HashingEmbedder:
    name = "hashing"

    def embed_one(self, text: str) -> list[float]:
        words = _WORD.findall(text.lower())
        vec = [0.0] * DIM
        for tok in words + [f"{a} {b}" for a, b in zip(words, words[1:], strict=False)]:
            h = hashlib.blake2b(tok.encode(), digest_size=8).digest()
            vec[int.from_bytes(h[:4], "big") % DIM] += 1.0 if h[4] & 1 else -1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_one(t) for t in texts]


class EdgeEmbedder:
    name = "gte-small"

    def __init__(self, url: str, key: str, timeout: float = 60.0):
        self.url, self.key, self.timeout = url, key, timeout

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for i in range(0, len(texts), BATCH):
                batch = texts[i:i + BATCH]
                vecs = (await self._post(client, batch)).get("embeddings")
                if not isinstance(vecs, list) or len(vecs) != len(batch) or any(len(v) != DIM for v in vecs):
                    raise EmbedError("embed function returned an unexpected shape")
                out += vecs
        return out

    async def _post(self, client: httpx.AsyncClient, batch: list[str]) -> dict[str, Any]:
        """Edge Functions return the odd 5xx (cold start, 520): retry those and network errors."""
        for attempt in range(RETRIES):
            try:
                res = await client.post(self.url, json={"inputs": batch}, headers={"x-embed-key": self.key})
            except httpx.TransportError as exc:
                if attempt == RETRIES - 1:
                    raise EmbedError(f"embed function unreachable: {exc}") from exc
            else:
                if res.status_code == 200:
                    return dict(res.json())
                if res.status_code < 500 or attempt == RETRIES - 1:
                    raise EmbedError(f"embed function returned {res.status_code}")
            await asyncio.sleep(2**attempt)
        raise EmbedError("unreachable")


def get_embedder() -> Embedder:
    s = get_settings()
    if s.embed_function_url:
        return EdgeEmbedder(s.embed_function_url, s.embed_function_key)
    return HashingEmbedder()


def to_pgvector(vec: list[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in vec) + "]"
