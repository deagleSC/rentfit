"""Phase 0 exit check, in-process: a queued job runs to completion, and a failing step is retried
without repeating finished steps. `Replayer` mimics Inngest: each attempt re-runs the handler, and
steps that already returned are served from memo instead of running again."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

from app.core import db as db_module
from app.jobs import runs
from app.jobs.functions import selftest
from app.jobs.runs import JobRefs


class Replayer:
    def __init__(self) -> None:
        self.memo: dict[str, Any] = {}

    async def run(self, step_id: str, fn: Any, *args: Any) -> Any:
        if step_id in self.memo:
            return self.memo[step_id]
        out = await fn(*args)
        self.memo[step_id] = out
        return out


async def test_failed_step_retries_without_repeating_finished_steps(db) -> None:  # type: ignore[no-untyped-def]
    async with db_module.transaction({"role": "system"}) as tx:
        run_id = await runs.create(tx, "selftest", JobRefs(entity="selftest", entity_id=uuid.uuid4()))
    step = Replayer()
    ctx = SimpleNamespace(event=SimpleNamespace(data={"job_run_id": str(run_id)}), run_id="r1", step=step)

    attempts = 0
    result = None
    while result is None and attempts < 3:
        attempts += 1
        try:
            result = await selftest.selftest._handler(ctx)  # type: ignore[arg-type]
        except RuntimeError:
            pass

    assert result == "first-done+flaky-done" and attempts == 2
    rows = await db.fetchall(
        "select payload->>'step' as step, count(*) as n from events where entity_id = %s group by 1", (run_id,))
    assert {r["step"]: r["n"] for r in rows} == {"first": 1, "flaky": 2, "last": 1}
    run = await runs.get(run_id)
    assert run is not None and run["status"] == "done"
