"""RLS review (backend plan §17 phase 4), as a test so new tables can't skip it."""

from __future__ import annotations

# Tables Supabase or LangGraph own, or that hold no user data and are only reached in system context.
EXEMPT = {"spatial_ref_sys"}


async def test_every_public_table_has_rls(db) -> None:  # type: ignore[no-untyped-def]
    await db.as_owner()
    rows = await db.fetchall(
        "select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace"
        " where n.nspname = 'public' and c.relkind = 'r' and not c.relrowsecurity")
    assert {r["relname"] for r in rows} - EXEMPT == set()


async def test_anon_and_authenticated_have_no_table_privileges(db) -> None:  # type: ignore[no-untyped-def]
    """The browser's anon key reaches PostgREST; every read goes through the API instead."""
    await db.as_owner()
    rows = await db.fetchall(
        "select table_name, grantee, privilege_type from information_schema.role_table_grants"
        " where table_schema = 'public' and grantee in ('anon', 'authenticated') and table_name <> all(%s)",
        (list(EXEMPT),))
    assert rows == []


async def test_api_roles_cannot_bypass_rls(db) -> None:  # type: ignore[no-untyped-def]
    await db.as_owner()
    rows = await db.fetchall("select rolname, rolbypassrls, rolsuper from pg_roles"
                             " where rolname in ('rentfit_api', 'rentfit_jobs')")
    assert len(rows) == 2 and not any(r["rolbypassrls"] or r["rolsuper"] for r in rows)
