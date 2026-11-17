"""Search evals (backend plan §15.2), real model.

    uv run python -m evals.run_search parsing     # filter parsing incl. Hinglish and follow-ups
    uv run python -m evals.run_search answers     # end-to-end turns: claim support and citation validity

parsing runs the agent's own pipeline: search_parse → slang rules → locality lookup → merge into the
previous filters. Score = share of gold fields right.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date
from typing import Any

from evals.common import REPORTS, Timer, load, log_to, use_real_model, write_report

use_real_model()

from app.core.db import close_pool, system_claims, transaction  # noqa: E402
from app.domain.filters import SearchFilters, SearchUpdate, apply_slang, chips, merge  # noqa: E402
from app.llm.prompts import PROMPTS, load_all  # noqa: E402
from app.llm.prompts.search import SearchParseInput  # noqa: E402
from app.llm.wrapper import call_structured, deadline_in  # noqa: E402
from app.services import localities  # noqa: E402

TODAY = date(2026, 11, 17)


async def parse(message: str, prev: SearchFilters) -> tuple[SearchUpdate, SearchFilters, float]:
    with Timer() as t:
        try:
            upd = (await call_structured(
                "structured", "search_parse",
                SearchParseInput(message=message, current_filters=[c["label"] for c in chips(prev)],
                                 results_shown=8 if prev.city else 0, today=TODAY),
                deadline=deadline_in(150))).value
        except Exception as exc:  # noqa: BLE001
            print("  call failed:", type(exc).__name__, str(exc)[:120])
            upd = SearchUpdate()
    upd = apply_slang(message, upd, prev)
    found = []
    async with transaction(system_claims()) as tx:
        for name in upd.locality_names[:5]:
            m = await localities.find(tx, name, upd.city or prev.city)
            if m:
                found.append((m.id, m.name))
    f, _ = merge(prev, upd, localities=found, commute=None)
    return upd, f, t.s


def check(key: str, want: Any, upd: SearchUpdate, f: SearchFilters) -> bool:
    if key == "intent":
        return upd.intent == want
    if key == "result_number":
        return upd.result_number == want
    if key == "intent_not":  # an injection must not turn into a search with invented filters
        return upd.intent != "search" or f.rent_max is None and not f.bhk
    if key == "localities":
        return sorted(f.locality_names) == sorted(want)
    if key == "localities_include":
        return set(want) <= set(f.locality_names)
    if key == "furnishing_include":
        return set(want) <= set(f.furnishing)
    if key == "amenities":
        return set(want) <= set(f.amenities)
    if key == "soft_any":
        text = " ".join(f.soft + [f.semantic_query]).lower()
        return any(w in text for w in want)
    if key == "commute_to":
        return bool(upd.commute_to) and want in upd.commute_to.lower()
    if key == "commute_minutes":
        return upd.commute_minutes == want
    if key == "bhk":
        return sorted(f.bhk) == sorted(want)
    return getattr(f, key) == want


async def parsing() -> None:
    cases, right, total = [], 0, 0
    for c in load("parsing"):
        prev = SearchFilters.model_validate(c.get("prev") or {})
        upd, f, secs = await parse(c["message"], prev)
        res = {k: check(k, v, upd, f) for k, v in c["want"].items()}
        right += sum(res.values())
        total += len(res)
        wrong = {k: {"want": c["want"][k], "got": _got(k, upd, f)} for k, ok in res.items() if not ok}
        cases.append({"message": c["message"], "prev": c.get("prev"), "wrong": wrong, "seconds": secs})
        print(("✓" if not wrong else "✗"), c["message"][:60], wrong or "")
    secs = sorted(x["seconds"] for x in cases)
    write_report("filter_parsing", f"search_parse-v{PROMPTS['search_parse'].version}",
                 {"field_accuracy": round(right / total, 3), "fields": total, "cases": len(cases),
                  "p50_s": secs[len(secs) // 2]},
                 {"field_accuracy": ">=0.92"}, cases)


def _got(key: str, upd: SearchUpdate, f: SearchFilters) -> Any:
    if key in ("intent", "result_number", "commute_to", "commute_minutes"):
        return getattr(upd, key)
    if key.startswith("localities"):
        return f.locality_names
    if key == "soft_any":
        return f.soft
    if key == "furnishing_include":
        return f.furnishing
    return getattr(f, key, None)


async def main(which: str) -> None:
    log_to(REPORTS / "run_search.log")
    load_all()
    try:
        if which == "parsing":
            await parsing()
        elif which == "answers":
            from evals.run_answers import answers

            await answers()
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "parsing"))
