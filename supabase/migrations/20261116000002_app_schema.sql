-- RLS helper functions and the restricted roles (backend plan §4.3).
-- Policies call these helpers instead of Supabase's auth.uid(), so moving off Supabase only
-- means changing how FastAPI sets `app.claims`.

create schema if not exists app;

-- Set by FastAPI at the start of every transaction:
--   select set_config('app.claims', '{"sub": "...", "role": "landlord|tenant|system"}', true)
-- Clients never connect to the database directly, so they cannot set this.
create or replace function app.claims() returns jsonb
  language sql stable
as $$ select coalesce(nullif(current_setting('app.claims', true), ''), '{}')::jsonb $$;

create or replace function app.current_user_id() returns uuid
  language sql stable
as $$ select nullif(app.claims() ->> 'sub', '')::uuid $$;

-- 'landlord' | 'tenant' | 'system' | null (signed in, no profile yet)
create or replace function app.current_role() returns text
  language sql stable
as $$ select nullif(app.claims() ->> 'role', '') $$;

create or replace function app.is_role(p_role text) returns boolean
  language sql stable
as $$ select app.current_role() is not distinct from p_role $$;

-- rentfit_api: request path. rentfit_jobs: Inngest functions. Neither has BYPASSRLS.
-- Passwords are set outside migrations:  alter role rentfit_api with login password '...';
do $$
declare r text;
begin
  foreach r in array array['rentfit_api', 'rentfit_jobs'] loop
    if not exists (select 1 from pg_roles where rolname = r) then
      execute format('create role %I nologin noinherit', r);
    end if;
    execute format('grant usage on schema app, public, extensions to %I', r);
    execute format('grant execute on all functions in schema app to %I', r);
    execute format('alter role %I set search_path = public, extensions', r);
    -- Tables created later are usable by both roles; RLS decides which rows.
    execute format('alter default privileges in schema public grant select, insert, update, delete on tables to %I', r);
    execute format('alter default privileges in schema public grant usage, select on sequences to %I', r);
    execute format('alter default privileges in schema app grant execute on functions to %I', r);
  end loop;
end
$$;

-- New tables otherwise pick up Supabase's default grants to anon/authenticated.
-- Nothing is exposed through PostgREST: the API is the only gateway.
do $$
declare r text;
begin
  foreach r in array array['anon', 'authenticated'] loop
    if exists (select 1 from pg_roles where rolname = r) then
      execute format('alter default privileges in schema public revoke all on tables from %I', r);
      execute format('alter default privileges in schema public revoke all on sequences from %I', r);
      execute format('alter default privileges in schema public revoke all on functions from %I', r);
    end if;
  end loop;
end
$$;
