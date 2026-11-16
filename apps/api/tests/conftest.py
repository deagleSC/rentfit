"""Shared test fixtures.

Database tests run against the production Supabase database (no local DB, by decision), so they
never commit: each test gets one connection as the database owner (TEST_ADMIN_DATABASE_URL), opens
a transaction, and rolls it back at the end. Inside it:

- `db.auth_user()` inserts a throwaway auth.users row (visible only inside the transaction),
- `db.as_role(claims)` switches to `rentfit_api` with `set local role`, so RLS applies exactly as
  for the API,
- the app's `transaction()` is patched to reuse this connection, so API tests through the
  TestClient also run inside the same rolled-back transaction (nested blocks become savepoints).

Without TEST_ADMIN_DATABASE_URL the `db` tests are skipped.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import jwt
import psycopg
import pytest
from psycopg.rows import DictRow, dict_row

JWT_SECRET = "test-jwt-secret-at-least-32-bytes-long!!"

os.environ["APP_ENV"] = "test"
os.environ["SUPABASE_JWT_SECRET"] = JWT_SECRET
os.environ["SUPABASE_URL"] = ""
os.environ["LLM_PROVIDER"] = "fake"
os.environ["JOB_DISPATCHER"] = "inline"
os.environ["LANGFUSE_PUBLIC_KEY"] = ""
os.environ["LANGFUSE_SECRET_KEY"] = ""
os.environ["SENTRY_DSN"] = ""

def _from_dotenv(key: str) -> str:
    env = Path(__file__).resolve().parents[1] / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip()
    return ""


ADMIN_URL = os.environ.get("TEST_ADMIN_DATABASE_URL") or _from_dotenv("TEST_ADMIN_DATABASE_URL")


def make_token(user_id: uuid.UUID, email: str = "t@example.com", exp_in: int = 3600) -> str:
    return jwt.encode(
        {"sub": str(user_id), "email": email, "aud": "authenticated", "exp": int(time.time()) + exp_in},
        JWT_SECRET,
        algorithm="HS256",
    )


def auth_header(user_id: uuid.UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(user_id)}"}


class RollbackDb:
    def __init__(self, conn: psycopg.AsyncConnection[DictRow]):
        self.conn = conn

    async def auth_user(self, email: str | None = None) -> uuid.UUID:
        uid = uuid.uuid4()
        await self.as_owner()
        await self.conn.execute(
            "insert into auth.users (id, email, aud, role) values (%s, %s, 'authenticated', 'authenticated')",
            (uid, email or f"test-{uid}@example.com"),
        )
        return uid

    async def as_owner(self) -> None:
        await self.conn.execute("reset role")

    async def as_role(self, claims: dict[str, Any], role: str = "rentfit_api") -> None:
        await self.conn.execute(f"set local role {role}")
        await self.conn.execute("select set_config('app.claims', %s, true)", (json.dumps(claims),))

    async def fetchall(self, query: str, params: Any = None) -> list[DictRow]:
        cur = await self.conn.execute(query, params)
        return await cur.fetchall()


@pytest.fixture
async def db(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[RollbackDb]:
    if not ADMIN_URL:
        pytest.skip("TEST_ADMIN_DATABASE_URL not set")
    conn = await psycopg.AsyncConnection.connect(ADMIN_URL, row_factory=dict_row, prepare_threshold=None)
    try:
        await conn.execute("begin")
        await conn.execute("set local search_path = public, extensions")
        rdb = RollbackDb(conn)

        from app.core import auth as auth_module
        from app.core import db as db_module

        @asynccontextmanager
        async def rolled_back(claims: dict[str, Any]) -> AsyncIterator[db_module.Tx]:
            tx = db_module.Tx(conn)
            async with conn.transaction():  # savepoint inside the outer transaction
                await conn.execute("set local role rentfit_api")
                await tx.set_claims(claims)
                yield tx
            await conn.execute("reset role")
            for callback in tx._after_commit:
                await callback()

        monkeypatch.setattr(db_module, "transaction", rolled_back)
        monkeypatch.setattr(auth_module, "transaction", rolled_back)
        yield rdb
    finally:
        await conn.execute("rollback")
        await conn.close()


@pytest.fixture
async def api() -> AsyncIterator[httpx.AsyncClient]:
    """In-process client on the test's event loop (so it can share the rollback connection)."""
    from app.main import create_app

    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
