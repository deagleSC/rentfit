# 1. One production Supabase project, no local database

**Status:** accepted (Phase 0)

## Context
The plan assumed local Postgres for dev and tests. Running Docker locally was not wanted, and a second
hosted project doubles setup and secrets for a solo project.

## Decision
Dev, tests and production share one Supabase project.
- Tests never commit: each opens one owner connection, starts a transaction, switches to the
  `rentfit_api` role with `set local role` (so RLS applies exactly as for the API), and rolls back.
  The app's `transaction()` is patched to use savepoints on that connection, and a guard fails any
  test that touches the real connection pool.
- Seed and eval data is real data, cleaned up by the scripts that create it.

## Consequences
- Tests exercise the real schema, extensions and RLS; no drift between local and hosted Postgres.
- Database tests do not run in CI (no credentials there, by design).
- A buggy test could, in principle, write to production; the rollback fixture and pool guard are
  the protection, and `test_rls_audit` checks the roles cannot bypass RLS.
