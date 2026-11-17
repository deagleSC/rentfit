"""Render the README results table from the latest report of each eval (backend plan §15.2).

    uv run python -m evals.readme_results

Replaces the text between <!-- results:start --> and <!-- results:end --> in the repo README.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evals.common import REPORTS

README = Path(__file__).resolve().parents[3] / "README.md"
START, END = "<!-- results:start -->", "<!-- results:end -->"

ROWS: list[tuple[str, str, str]] = [  # (eval, metric, label)
    ("listing_extraction", "field_accuracy", "Listing extraction: field accuracy"),
    ("listing_edits", "same_patch_rate", "Listing edits by chat: same patch as a hand edit"),
    ("filter_parsing", "field_accuracy", "Search filter parsing (incl. Hinglish, follow-ups)"),
    ("retrieval", "ndcg@10_hybrid", "Retrieval nDCG@10: hybrid"),
    ("retrieval", "ndcg@10_text", "Retrieval nDCG@10: full-text only"),
    ("retrieval", "ndcg@10_vector", "Retrieval nDCG@10: vector only"),
    ("retrieval", "recall@10_hybrid", "Retrieval recall@10: hybrid"),
    ("answers", "unsupported_claim_rate", "Answers: unsupported claims (dropped by the checker)"),
    ("answers", "cited_share", "Answers: claims with a citation"),
    ("latency", "search_done_p50_s", "Search turn, p50 (s, real model, deployed)"),
    ("latency", "search_done_p95_s", "Search turn, p95 (s)"),
    ("latency", "search_cards_p50_s", "Search turn, time to cards p50 (s)"),
    ("latency", "map_listings_p95_s", "Map pins endpoint, p95 (s)"),
]


def latest(name: str) -> dict[str, Any] | None:
    files = sorted((REPORTS / name).glob("*.json"))
    return json.loads(files[-1].read_text()) if files else None


def table() -> str:
    out = ["| Eval | Result | Target | Met | Size | Report |", "| --- | --- | --- | --- | --- | --- |"]
    for name, metric, label in ROWS:
        r = latest(name)
        if r is None:
            out.append(f"| {label} | not run | | | | |")
            continue
        v = r["metrics"].get(metric)
        target = r["target"].get(metric, "")
        met = {True: "yes", False: "**no**", None: ""}[r["met"].get(metric)] if metric in r["met"] else ""
        size = r["metrics"].get("cases") or r["metrics"].get("queries") or r["metrics"].get("search_turns") or ""
        shown = f"{v:.1%}" if isinstance(v, float) and v <= 1 and "_s" not in metric else v
        target = target.replace(">=", "≥ ").replace("<=", "≤ ")
        out.append(f"| {label} | {shown} | {target} | {met} | {size} | `{r['eval']}/{r['at']}_{r['version']}` |")
    return "\n".join(out)


def main() -> None:
    text = README.read_text()
    if START not in text:
        raise SystemExit(f"{README} has no {START} marker")
    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    README.write_text(f"{head}{START}\n{table()}\n{END}{tail}")
    print(table())


if __name__ == "__main__":
    main()
