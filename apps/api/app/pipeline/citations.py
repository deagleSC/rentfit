"""Check the answer's claims against what they cite (backend plan §13 `respond`).

A claim survives only if every ref it cites exists, and every number in its text appears in the
cited items ("₹35,000" / "35k" / "35000" all count as 35000). A claim without cites survives only if
it states no numbers (general advice like "try another area"). Dropped claims are logged by the
caller; the tenant never sees them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.llm.prompts.search import Claim

_NUM = re.compile(r"(\d+(?:[.,]\d+)*)\s*(k|l|lakh|lakhs|lac)?\b", re.I)
_REF = re.compile(r"\b[LN]\d+\b")  # "L1", "N2": refs, not numbers
_MULT = {"k": 1_000, "l": 100_000, "lakh": 100_000, "lakhs": 100_000, "lac": 100_000}


def numbers(text: str) -> set[float]:
    out: set[float] = set()
    for num, unit in _NUM.findall(_REF.sub(" ", text)):
        raw = num.replace(",", "")
        try:
            v = float(raw)
        except ValueError:
            continue
        out.add(v * _MULT.get(unit.lower(), 1) if unit else v)
    return out


def _flatten(item: Any) -> str:
    if isinstance(item, dict):
        return " ".join(_flatten(v) for v in item.values())
    if isinstance(item, list | tuple):
        return " ".join(_flatten(v) for v in item)
    return str(item)


@dataclass
class Checked:
    kept: list[Claim] = field(default_factory=list)
    dropped: list[tuple[Claim, str]] = field(default_factory=list)


def check(claims: list[Claim], sources: dict[str, Any]) -> Checked:
    """`sources` maps a ref ("L1", "N2") to the data the model was given for it."""
    out = Checked()
    known = {ref: numbers(_flatten(data)) for ref, data in sources.items()}
    for c in claims:
        stated = numbers(c.text)
        if not c.cites:
            (out.kept.append(c) if not stated else out.dropped.append((c, "numbers without a citation")))
            continue
        unknown = [r for r in c.cites if r not in known]
        if unknown:
            out.dropped.append((c, f"unknown refs {unknown}"))
            continue
        pool = set().union(*(known[r] for r in c.cites))
        missing = {n for n in stated if n not in pool}
        if missing:
            out.dropped.append((c, f"numbers not in sources: {sorted(missing)}"))
            continue
        out.kept.append(c)
    return out
