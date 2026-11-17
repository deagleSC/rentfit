"""Shared eval plumbing (backend plan §15.2): reports and settings.

Every runner writes `evals/reports/<eval>/<timestamp>_<version>.json` with its metrics, target, the
models and prompt versions used, and per-case details. `python -m evals.readme_results` renders the
README table from the latest report of each eval.
"""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
REPORTS = ROOT / "reports"


def use_real_model() -> None:
    """Evals measure the real model: override the dev default before settings are read."""
    os.environ["LLM_PROVIDER"] = "openrouter"
    os.environ["JOB_DISPATCHER"] = "inline"


def load(name: str) -> list[dict[str, Any]]:
    return json.loads((DATA / f"{name}.json").read_text())


def write_report(eval_name: str, version: str, metrics: dict[str, Any], target: dict[str, Any],
                 cases: list[dict[str, Any]], meta: dict[str, Any] | None = None) -> Path:
    from app.core.config import get_settings

    s = get_settings()
    out = REPORTS / eval_name
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = out / f"{stamp}_{version}.json"
    report = {
        "eval": eval_name, "version": version, "at": stamp, "metrics": metrics, "target": target,
        "met": {k: _meets(metrics.get(k), t) for k, t in target.items()},
        "models": s.llm_structured_models, "provider": s.llm_provider, **(meta or {}), "cases": cases,
    }
    path.write_text(json.dumps(report, indent=1, default=str, ensure_ascii=False))
    summary = ", ".join(f"{k}={v}" for k, v in metrics.items())
    print(f"\n{eval_name}: {summary}\n→ {path.relative_to(ROOT.parent)}")
    return path


def _meets(value: Any, target: Any) -> bool | None:
    """Targets are strings like '>=0.95' or '<=0.02'."""
    if value is None:
        return None
    op, num = target[:2], float(target[2:])
    return value >= num if op == ">=" else value <= num


class Timer:
    def __enter__(self) -> Timer:
        self.t = time.monotonic()
        return self

    def __exit__(self, *a: object) -> None:
        self.s = round(time.monotonic() - self.t, 2)


def log_to(path: Path) -> None:
    """Model-call logs (retries, fallbacks, rate limits) to a file, so slow runs can be explained."""
    import logging

    path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=path, level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    for name in ("httpx", "httpcore", "psycopg", "openai"):
        logging.getLogger(name).setLevel(logging.WARNING)
