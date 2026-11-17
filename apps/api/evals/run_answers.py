"""Answer eval (backend plan §15.2): grounded replies, real model.

Each query runs the agent's own steps (parse → merge → hybrid search → cards → respond →
citations.check) in system context. Metrics:
- unsupported_claim_rate: claims the checker dropped (a number not in the cited items, or an unknown
  ref) over all claims the model wrote. Target ≤ 2%.
- cited_share: kept claims that cite at least one listing or note.
"""

from __future__ import annotations

from typing import Any

from app.agents import search_agent
from app.core.db import system_claims, transaction
from app.domain.filters import SearchFilters
from app.llm.prompts import PROMPTS
from app.pipeline import citations
from app.services import search_results as res
from evals.common import Timer, load, write_report
from evals.run_search import parse


async def answers() -> None:
    cases: list[dict[str, Any]] = []
    total = dropped = cited = kept = 0
    real_check = citations.check
    seen: dict[str, Any] = {}

    def spy(claims: Any, sources: Any) -> citations.Checked:
        seen["out"] = real_check(claims, sources)
        return seen["out"]

    async def emit(_name: str, _data: Any) -> None:
        return None

    citations.check = spy  # type: ignore[assignment]
    for q in load("answers"):
        seen.clear()
        hits: list[Any] = []
        _, f, _ = await parse(q, SearchFilters())
        with Timer() as t:
            try:
                async with transaction(system_claims()) as tx:  # the agent's own search → relax → rank
                    found = await search_agent.find(tx, f, [])
                    hits = found.hits
                    ids = found.ranked[:search_agent.CARDS]
                    rows = await res.card_rows(tx, ids)
                    shown = await res.cards(tx, ids, found.commutes, rows)
                    reply = await search_agent.respond(tx, emit, q, found.searched, found.relaxed, len(hits), shown,
                                                       {i: r["description"] or "" for i, r in rows.items()})
            except Exception as exc:  # noqa: BLE001
                print("  failed:", type(exc).__name__, str(exc)[:120])
                reply = {"intro": "", "claims": []}
        chk = seen.get("out")
        n_kept = len(chk.kept) if chk else 0
        n_drop = len(chk.dropped) if chk else 0
        total += n_kept + n_drop
        dropped += n_drop
        kept += n_kept
        cited += sum(1 for c in reply["claims"] if c["refs"])
        cases.append({"q": q, "results": len(hits), "intro": reply["intro"],
                      "claims": reply["claims"], "dropped": [(c.text, why) for c, why in (chk.dropped if chk else [])],
                      "seconds": t.s})
        print(f"{'✓' if not n_drop else '✗'} {q[:50]:50} kept={n_kept} dropped={n_drop} {t.s}s")
    citations.check = real_check  # type: ignore[assignment]
    write_report("answers", f"search_respond-v{PROMPTS['search_respond'].version}",
                 {"unsupported_claim_rate": round(dropped / total, 3) if total else None,
                  "cited_share": round(cited / kept, 3) if kept else None, "claims": total, "cases": len(cases)},
                 {"unsupported_claim_rate": "<=0.02", "cited_share": ">=0.90"}, cases)
