"""RLS matrix for Phase 0 tables (backend plan §4.4), rolled back (see conftest)."""

import psycopg
import pytest


async def _profile(db, role: str) -> str:  # type: ignore[no-untyped-def]
    uid = await db.auth_user()
    await db.as_role({"sub": str(uid)})
    await db.conn.execute("select app.create_profile(%s, 'X')", (role,))
    await db.as_owner()
    return str(uid)


async def test_users_see_only_their_own_profile(db) -> None:  # type: ignore[no-untyped-def]
    a = await _profile(db, "landlord")
    b = await _profile(db, "landlord")
    await db.as_role({"sub": a, "role": "landlord"})
    rows = await db.fetchall("select id::text from profiles")
    assert [r["id"] for r in rows] == [a]
    cur = await db.conn.execute("update profiles set name = 'hacked' where id = %s", (b,))
    assert cur.rowcount == 0


async def test_role_is_immutable(db) -> None:  # type: ignore[no-untyped-def]
    a = await _profile(db, "tenant")
    await db.as_role({"sub": a, "role": "tenant"})
    with pytest.raises(psycopg.Error):
        await db.conn.execute("update profiles set role = 'landlord' where id = %s", (a,))


async def test_internal_tables_hidden_from_users(db) -> None:  # type: ignore[no-untyped-def]
    a = await _profile(db, "tenant")
    await db.as_role({"sub": a, "role": "tenant"})
    assert await db.fetchall("select * from llm_budget") == []
    with pytest.raises(psycopg.Error):
        await db.conn.execute("insert into llm_budget (day, model_id) values (current_date, 'x')")


async def test_reference_tables_read_only_for_users(db) -> None:  # type: ignore[no-untyped-def]
    a = await _profile(db, "tenant")
    await db.as_role({"sub": a, "role": "tenant"})
    await db.fetchall("select * from cities")
    with pytest.raises(psycopg.Error):
        await db.conn.execute(
            "insert into cities (slug, name, center) values ('x', 'X', 'POINT(77 12)'::geography)"
        )


async def test_anon_and_authenticated_cannot_read_profiles(db) -> None:  # type: ignore[no-untyped-def]
    for role in ("anon", "authenticated"):
        await db.as_owner()
        await db.conn.execute("savepoint s")
        await db.conn.execute(f"set local role {role}")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            await db.conn.execute("select * from profiles")
        await db.conn.execute("rollback to savepoint s")
