"""Enable login for the restricted DB roles and set their passwords (run once per environment).

    uv run python -m scripts.setup_roles

Reads TEST_ADMIN_DATABASE_URL (owner connection), RENTFIT_API_DB_PASSWORD and RENTFIT_JOBS_DB_PASSWORD
from apps/api/.env. Passwords are never in migrations. Also lets `postgres` `set role` into both
roles, which the rolled-back DB tests use.
"""

from __future__ import annotations

from pathlib import Path

import psycopg
from psycopg import sql


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for line in (Path(__file__).resolve().parents[1] / ".env").read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def main() -> None:
    env = load_env()
    with psycopg.connect(env["TEST_ADMIN_DATABASE_URL"], autocommit=True, prepare_threshold=None) as conn:
        for role, key in (("rentfit_api", "RENTFIT_API_DB_PASSWORD"), ("rentfit_jobs", "RENTFIT_JOBS_DB_PASSWORD")):
            conn.execute(sql.SQL("alter role {} with login password {}").format(
                sql.Identifier(role), sql.Literal(env[key])))
            conn.execute(sql.SQL("grant {} to postgres").format(sql.Identifier(role)))
            print(f"{role}: login enabled")


if __name__ == "__main__":
    main()
