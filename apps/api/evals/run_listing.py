"""Listing extraction and chat-edit evals (backend plan §15.2), real model.

    uv run python -m evals.run_listing

- extraction: one free-text description → fields. Score = share of gold fields right.
- edits: a message on an existing listing → the set of changed fields and values, after the same code
  guards the agent uses (deposit months → amount, clear only what the message names). Score = share of
  cases whose patch equals the hand edit exactly.
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

from evals.common import REPORTS, Timer, load, log_to, use_real_model, write_report

use_real_model()

from app.agents.listing_agent import backfill, mentions  # noqa: E402
from app.core.db import close_pool  # noqa: E402
from app.llm.prompts import PROMPTS, load_all  # noqa: E402
from app.llm.prompts.listing import ListingUpdate, ListingUpdateInput  # noqa: E402
from app.llm.wrapper import call_structured, deadline_in  # noqa: E402
from app.pipeline.normalise import deposit_from_months  # noqa: E402
from app.pipeline.redact import strip_contacts  # noqa: E402

TODAY = date(2026, 11, 17)
SIMPLE = ("bhk", "rent", "maintenance", "furnishing", "sqft", "floor", "total_floors", "tenant_pref", "pets",
          "parking", "gated", "no_brokerage", "city")


def resolved(upd: ListingUpdate, current: dict[str, Any], message: str) -> dict[str, Any]:
    """What the agent would write, minus DB lookups (locality kept as the written name)."""
    upd = backfill(upd, message)
    out: dict[str, Any] = {f: getattr(upd, f) for f in SIMPLE if getattr(upd, f) is not None}
    rent = upd.rent if upd.rent is not None else current.get("rent")
    if upd.deposit is not None:
        out["deposit"] = upd.deposit
    elif upd.deposit_months is not None and rent:
        out["deposit"] = deposit_from_months(upd.deposit_months, rent)
    if upd.locality_name:
        out["locality"] = upd.locality_name.lower()
    if upd.available_now:
        out["available_from"] = "now"
    elif upd.available_from:
        out["available_from"] = upd.available_from.isoformat()
    amen = set(current.get("amenities", []))
    if upd.add_amenities or upd.remove_amenities:
        new = sorted((amen | set(upd.add_amenities)) - set(upd.remove_amenities))
        if new != sorted(amen):
            out["amenities"] = new
    for f in upd.clear:
        if mentions(message, f) and current.get(f) is not None:
            out[f] = None
    return {k: v for k, v in out.items() if current.get(k) != v}


async def ask(message: str, current: dict[str, Any]) -> tuple[ListingUpdate, float]:
    """A failed call (provider timeout, invalid output twice) scores as an empty answer, not a crash."""
    with Timer() as t:
        try:
            res = await call_structured("structured", "listing_update",
                                        ListingUpdateInput(message=strip_contacts(message), current=current,
                                                           today=TODAY), deadline=deadline_in(150))
            value = res.value
        except Exception as exc:  # noqa: BLE001
            print("  call failed:", type(exc).__name__, str(exc)[:120])
            value = ListingUpdate()
    return value, t.s


def field_ok(name: str, got: Any, want: Any) -> bool:
    if name == "locality":
        return isinstance(got, str) and (want in got or got in want)
    return got == want


async def extraction() -> None:
    cases, right, total = [], 0, 0
    for c in load("extraction"):
        upd, secs = await ask(c["text"], {})
        got = resolved(upd, {}, c["text"])
        checks = {k: field_ok(k, got.get(k), v) for k, v in c["gold"].items()}
        right += sum(checks.values())
        total += len(checks)
        wrong = {k: {"want": c["gold"][k], "got": got.get(k)} for k, ok in checks.items() if not ok}
        cases.append({"text": c["text"], "wrong": wrong, "seconds": secs})
        print(("✓" if not wrong else "✗"), c["text"][:60], wrong or "")
    secs = sorted(x["seconds"] for x in cases)
    write_report("listing_extraction", f"listing_update-v{PROMPTS['listing_update'].version}",
                 {"field_accuracy": round(right / total, 3), "fields": total, "cases": len(cases),
                  "p50_s": secs[len(secs) // 2]},
                 {"field_accuracy": ">=0.95"}, cases)


async def edits() -> None:
    cases, exact = [], 0
    for c in load("edits"):
        upd, secs = await ask(c["message"], c["current"])
        got = resolved(upd, c["current"], c["message"])
        ok = all(field_ok(k, got.get(k, "∅"), v) for k, v in c["want"].items()) and set(got) == set(c["want"])
        exact += ok
        cases.append({"message": c["message"], "ok": ok, "want": c["want"], "got": got, "seconds": secs})
        print(("✓" if ok else "✗"), c["message"][:60], "" if ok else {"want": c["want"], "got": got})
    write_report("listing_edits", f"listing_update-v{PROMPTS['listing_update'].version}",
                 {"same_patch_rate": round(exact / len(cases), 3), "cases": len(cases)},
                 {"same_patch_rate": ">=0.90"}, cases)


async def main() -> None:
    log_to(REPORTS / "run_listing.log")
    load_all()
    try:
        await extraction()
        await edits()
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
