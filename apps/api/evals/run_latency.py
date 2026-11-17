"""Latency on the deployed API (backend plan §15.2), real model.

    uv run python -m evals.run_latency [https://rentfit-api.vercel.app]

Signs in as the e2e tenant, times reference/map/detail endpoints (no model), then a set of fresh
search turns (each a new budget, so nothing is served from the model cache): time to the first
event, to the cards, and to `done`. Deletes the chats it created.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from statistics import median
from typing import Any

import httpx

from evals.common import write_report
from scripts.seed import _dotenv

API = sys.argv[1] if len(sys.argv) > 1 else "https://rentfit-api.vercel.app"
QUERIES = ["2 BHK in Koramangala under {k}k", "1bhk for bachelors in HSR Layout below {k}k",
           "family flat in Powai, 3 bedrooms, budget {k}k", "Andheri West 1 BHK furnished under {k}k",
           "semi furnished 2bhk in Whitefield under {k}k with a gym",
           "Bengaluru mein 2 bhk {k} hazaar tak metro ke paas"]


def pct(xs: list[float], p: float) -> float:
    s = sorted(xs)
    return round(s[min(len(s) - 1, int(round(p * (len(s) - 1))))], 2)


async def token(client: httpx.AsyncClient) -> str:
    url, anon = _dotenv("SUPABASE_URL"), _dotenv("SUPABASE_ANON_KEY")
    r = await client.post(f"{url}/auth/v1/token?grant_type=password", headers={"apikey": anon},
                          json={"email": _dotenv("E2E_TENANT_EMAIL"), "password": _dotenv("E2E_TENANT_PASSWORD")})
    r.raise_for_status()
    return str(r.json()["access_token"])


async def timed_get(client: httpx.AsyncClient, path: str, n: int) -> list[float]:
    out = []
    for _ in range(n):
        t = time.monotonic()
        r = await client.get(path)
        r.raise_for_status()
        out.append(time.monotonic() - t)
    return out


async def search_turn(client: httpx.AsyncClient, message: str) -> dict[str, Any]:
    t0 = time.monotonic()
    marks: dict[str, float] = {}
    chat_id = None
    async with client.stream("POST", "/v1/tenant/search/chat", json={"message": message}, timeout=120) as r:
        r.raise_for_status()
        buf = ""
        async for chunk in r.aiter_text():
            buf += chunk
            while "\n\n" in buf:
                block, buf = buf.split("\n\n", 1)
                name = next((ln[7:] for ln in block.split("\n") if ln.startswith("event: ")), "")
                marks.setdefault(name, round(time.monotonic() - t0, 2))
                if name == "done":
                    chat_id = json.loads(block.split("data: ", 1)[1])["chat_id"]
                if name == "error":
                    marks["error_detail"] = block  # type: ignore[assignment]
    return {"message": message, "first_event_s": min(v for k, v in marks.items() if isinstance(v, float)),
            "cards_s": marks.get("cards"), "done_s": marks.get("done"), "chat_id": chat_id,
            "error": marks.get("error_detail")}


async def main() -> None:
    async with httpx.AsyncClient(base_url=API, timeout=60) as client:
        client.headers["Authorization"] = f"Bearer {await token(client)}"
        listing = (await client.get("/v1/tenant/map/listings?city=bangalore")).json()["data"][0]["id"]
        reads = {
            "health": await timed_get(client, "/health", 20),
            "cities": await timed_get(client, "/v1/cities", 20),
            "map_listings": await timed_get(client, "/v1/tenant/map/listings?city=bangalore", 20),
            "listing_detail": await timed_get(client, f"/v1/listings/{listing}", 20),
        }
        stamp = int(time.time()) % 7  # a different budget per run keeps the model cache cold
        turns = []
        for i, q in enumerate(QUERIES * 2):
            msg = q.format(k=31 + stamp + i * 2)
            turns.append(await search_turn(client, msg))
            err = turns[-1]["error"]
            print(f"{turns[-1]['done_s']}s  {msg}" + (f"  ERROR {err[:120]}" if err else ""))
    from app.core.db import close_pool, system_claims, transaction

    ids = [t["chat_id"] for t in turns if t["chat_id"]]
    async with transaction(system_claims()) as tx:  # remove the eval's chats and their checkpoints
        threads = [r["thread_id"] for r in await tx.fetchall("select thread_id from chats where id = any(%s)", (ids,))]
        for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
            await tx.conn.execute(f"delete from {table} where thread_id = any(%s)", (threads,))
        await tx.conn.execute("delete from chats where id = any(%s)", (ids,))
    await close_pool()
    ok = [t for t in turns if t["done_s"]]
    done = [t["done_s"] for t in ok]
    metrics: dict[str, Any] = {f"{k}_p50_s": pct(v, 0.5) for k, v in reads.items()}
    metrics |= {f"{k}_p95_s": pct(v, 0.95) for k, v in reads.items()}
    metrics |= {"search_first_event_p50_s": round(median(t["first_event_s"] for t in ok), 2),
                "search_cards_p50_s": round(median(t["cards_s"] for t in ok if t["cards_s"]), 2),
                "search_done_p50_s": pct(done, 0.5), "search_done_p95_s": pct(done, 0.95),
                "search_turns": len(turns), "search_errors": len(turns) - len(ok)}
    write_report("latency", "prod", metrics, {"search_done_p95_s": "<=15", "map_listings_p95_s": "<=1.0"},
                 turns, {"api": API})


if __name__ == "__main__":
    asyncio.run(main())
