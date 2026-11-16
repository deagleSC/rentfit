"""JobDispatcher, run status and housekeeping without Inngest (backend plan §5, §9), rolled back."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
import pytest

from app.core import db as db_module
from app.jobs import runs
from app.jobs.dispatcher import InngestDispatcher
from app.jobs.functions import housekeeping
from app.jobs.runs import JobRefs


class FakeInngest:
    def __init__(self, fail: bool = False):
        self.sent: list[Any] = []
        self.fail = fail

    async def send(self, event: Any) -> list[str]:
        if self.fail:
            raise ConnectionError("inngest down")
        self.sent.append(event)
        return [event.id]


async def landlord(db) -> dict[str, str]:  # type: ignore[no-untyped-def]
    uid = await db.auth_user()
    await db.as_role({"sub": str(uid)})
    await db.conn.execute("select app.create_profile('landlord', 'Jo')")
    await db.as_owner()
    return {"sub": str(uid), "role": "landlord"}


def refs(claims: dict[str, str]) -> JobRefs:
    return JobRefs(entity="listing", entity_id=uuid.uuid4(), owner_id=uuid.UUID(claims["sub"]))


def assert_ids_only(data: dict[str, str]) -> None:
    for key, value in data.items():
        if key == "entity":
            assert value.isidentifier()
            continue
        assert key.endswith("_id"), key
        uuid.UUID(value)


async def test_event_is_sent_only_after_commit(db) -> None:  # type: ignore[no-untyped-def]
    claims = await landlord(db)
    fake = FakeInngest()
    d = InngestDispatcher(fake)  # type: ignore[arg-type]
    r = refs(claims)
    async with db_module.transaction(claims) as tx:
        run_id = await d.enqueue(tx, "selftest", r)
        assert fake.sent == []  # still inside the transaction
    assert len(fake.sent) == 1
    event = fake.sent[0]
    assert event.name == "selftest/requested" and event.id == str(run_id)
    assert event.data == {"entity": "listing", "entity_id": str(r.entity_id), "owner_id": claims["sub"],
                          "job_run_id": str(run_id)}
    assert_ids_only(dict(event.data))
    assert (await runs.get(run_id))["status"] == "queued"  # type: ignore[index]


async def test_rollback_sends_nothing_and_leaves_no_run(db) -> None:  # type: ignore[no-untyped-def]
    claims = await landlord(db)
    fake = FakeInngest()
    d = InngestDispatcher(fake)  # type: ignore[arg-type]
    run_id = None
    with pytest.raises(RuntimeError):
        async with db_module.transaction(claims) as tx:
            run_id = await d.enqueue(tx, "selftest", refs(claims))
            raise RuntimeError("request failed after queuing")
    assert fake.sent == [] and await runs.get(run_id) is None  # type: ignore[arg-type]


async def test_enqueue_restores_the_callers_claims(db) -> None:  # type: ignore[no-untyped-def]
    claims = await landlord(db)
    async with db_module.transaction(claims) as tx:
        await InngestDispatcher(FakeInngest()).enqueue(tx, "selftest", refs(claims))  # type: ignore[arg-type]
        row = await tx.fetchone("select app.current_role() as role")
        assert row is not None and row["role"] == "landlord"


async def test_failed_send_keeps_the_run_queued(db) -> None:  # type: ignore[no-untyped-def]
    claims = await landlord(db)
    async with db_module.transaction(claims) as tx:
        run_id = await InngestDispatcher(FakeInngest(fail=True)).enqueue(tx, "selftest", refs(claims))  # type: ignore[arg-type]
    assert (await runs.get(run_id))["status"] == "queued"  # type: ignore[index]


async def test_unknown_job_type_is_rejected(db) -> None:  # type: ignore[no-untyped-def]
    claims = await landlord(db)
    with pytest.raises(ValueError):
        async with db_module.transaction(claims) as tx:
            await InngestDispatcher(FakeInngest()).enqueue(tx, "no-such-job", refs(claims))  # type: ignore[arg-type]


async def test_owner_can_read_but_not_write_runs(db) -> None:  # type: ignore[no-untyped-def]
    claims = await landlord(db)
    async with db_module.transaction(claims) as tx:
        run_id = await InngestDispatcher(FakeInngest()).enqueue(tx, "selftest", refs(claims))  # type: ignore[arg-type]
    await db.as_role(claims)
    assert [str(r["id"]) for r in await db.fetchall("select id from job_runs")] == [str(run_id)]
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        await db.conn.execute("insert into job_runs (type, entity, entity_id) values ('selftest', 'x', %s)",
                              (uuid.uuid4(),))


async def test_run_status_transitions(db) -> None:  # type: ignore[no-untyped-def]
    claims = await landlord(db)
    async with db_module.transaction(claims) as tx:
        run_id = await runs.create(tx, "selftest", refs(claims))
    assert await runs.mark_running(str(run_id), "inngest-run-1") is True
    assert await runs.mark_running(str(run_id), "inngest-run-2") is False  # a duplicate cannot restart it
    row = await runs.get(run_id)
    assert row is not None and (row["status"], row["attempts"], row["inngest_run_id"]) == ("running", 1, "inngest-run-1")
    await runs.mark_failed(str(run_id), "boom")
    row = await runs.get(run_id)
    assert row is not None and (row["status"], row["last_error"]) == ("failed", "boom")


async def test_housekeeping_resends_stuck_and_resumes_deferred(db, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    claims = await landlord(db)
    fake = FakeInngest()
    monkeypatch.setattr(housekeeping, "dispatcher", InngestDispatcher(fake))  # type: ignore[arg-type]
    await db.as_owner()
    await db.conn.execute("update job_runs set status = 'done' where status in ('queued', 'deferred_budget')")

    async def insert(status: str, updated: datetime) -> str:
        cur = await db.conn.execute(
            "insert into job_runs (type, entity, entity_id, owner_id, status, updated_at)"
            " values ('selftest', 'listing', %s, %s, %s, %s) returning id",
            (uuid.uuid4(), claims["sub"], status, updated))
        row = await cur.fetchone()
        return str(row["id"])

    now = datetime.now(UTC)
    stuck = await insert("queued", now - timedelta(minutes=10))
    await insert("queued", now)  # fresh: not stuck yet
    deferred = await insert("deferred_budget", now - timedelta(days=1))
    await insert("deferred_budget", now)  # deferred today: budget not reset yet

    assert await housekeeping.resend_stuck_runs() == 1
    assert await housekeeping.resume_budget_deferred() == 1
    sent = [e.id for e in fake.sent]
    assert sorted(i.split(":")[0] for i in sent) == sorted([stuck, deferred])
    assert all(":" in i for i in sent)  # every re-send has a fresh id
    for e in fake.sent:
        assert_ids_only(dict(e.data))
