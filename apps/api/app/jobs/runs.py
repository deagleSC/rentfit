"""job_runs status writes (backend plan §9). The UI reads job status from here, not Inngest.

All writes run in system context: users may read their own runs but never write them.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb
from pydantic import BaseModel

from app.core.db import Tx, system_claims, transaction


class JobRefs(BaseModel):
    """The only data a job carries: IDs (backend plan §9: never listing text or chat messages)."""

    entity: str  # e.g. "listing"
    entity_id: UUID
    owner_id: UUID | None = None  # the user who may poll this run

    def event_data(self, job_run_id: UUID) -> dict[str, str]:
        data = {"entity": self.entity, "entity_id": str(self.entity_id), "job_run_id": str(job_run_id)}
        if self.owner_id:
            data["owner_id"] = str(self.owner_id)
        return data


async def create(tx: Tx, type: str, refs: JobRefs, params: dict[str, Any] | None = None) -> UUID:
    """Insert a queued run inside the caller's transaction. `params` are request settings the
    function reads from the row (events carry IDs only)."""
    async with tx.as_system():
        row = await tx.fetchone(
            "insert into job_runs (type, entity, entity_id, owner_id, params) values (%s, %s, %s, %s, %s) returning id",
            (type, refs.entity, refs.entity_id, refs.owner_id, Jsonb(params or {})),
        )
    assert row is not None
    return UUID(str(row["id"]))


async def _update(run_id: str | UUID, sql: str, params: tuple[Any, ...] = ()) -> None:
    async with transaction(system_claims()) as tx:
        await tx.conn.execute(f"update job_runs set {sql}, updated_at = now() where id = %s", (*params, run_id))


async def mark_running(run_id: str, inngest_run_id: str) -> bool:
    """Claim a queued run. False when it is already running or finished: the event was a duplicate
    (re-sends get fresh event ids, so this guard, not Inngest's id dedupe, stops a second start)."""
    async with transaction(system_claims()) as tx:
        row = await tx.fetchone(
            """
            update job_runs set status = 'running', attempts = attempts + 1, inngest_run_id = %s,
                                updated_at = now()
            where id = %s and status = 'queued' returning id
            """,
            (inngest_run_id, run_id),
        )
    return row is not None


async def mark_done(run_id: str) -> None:
    await _update(run_id, "status = 'done', last_error = null")


async def mark_deferred_budget(run_id: str) -> None:
    await _update(run_id, "status = 'deferred_budget'")


async def mark_failed(run_id: str, error: str) -> None:
    await _update(run_id, "status = 'failed', last_error = %s", (error[:2000],))


async def get(run_id: str | UUID) -> dict[str, Any] | None:
    async with transaction(system_claims()) as tx:
        row = await tx.fetchone("select * from job_runs where id = %s", (run_id,))
    return dict(row) if row else None


async def stuck_queued(older_than: timedelta = timedelta(minutes=5), limit: int = 100) -> list[dict[str, Any]]:
    """Runs still queued after `older_than`: their after-commit send was lost."""
    async with transaction(system_claims()) as tx:
        rows = await tx.fetchall(
            "select * from job_runs where status = 'queued' and updated_at < now() - %s order by updated_at limit %s",
            (older_than, limit),
        )
    return [dict(r) for r in rows]


async def claim_budget_deferred(limit: int = 100, *, now: datetime | None = None) -> list[dict[str, Any]]:
    """Runs deferred on an earlier UTC day: the budget has reset, so put them back in the queue."""
    midnight = (now or datetime.now(UTC)).replace(hour=0, minute=0, second=0, microsecond=0)
    async with transaction(system_claims()) as tx:
        rows = await tx.fetchall(
            """
            update job_runs set status = 'queued', updated_at = now()
            where id in (select id from job_runs where status = 'deferred_budget' and updated_at < %s
                         order by updated_at limit %s for update skip locked)
            returning *
            """,
            (midnight, limit),
        )
    return [dict(r) for r in rows]


def refs_of(run: dict[str, Any]) -> JobRefs:
    return JobRefs(entity=run["entity"], entity_id=run["entity_id"], owner_id=run.get("owner_id"))
