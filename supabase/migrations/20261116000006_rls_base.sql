-- RLS for Phase 0 tables (backend plan §4.4). Both API roles are listed explicitly;
-- no policy grants anything to anon/authenticated.

alter table cities      enable row level security;
alter table localities  enable row level security;
alter table pois        enable row level security;
alter table profiles    enable row level security;
alter table llm_cache   enable row level security;
alter table llm_budget  enable row level security;
alter table llm_rpm     enable row level security;
alter table job_runs    enable row level security;
alter table rate_limits enable row level security;

-- Reference data: any signed-in context reads; only system writes (seed scripts).
create policy cities_read      on cities     for select to rentfit_api, rentfit_jobs using (true);
create policy localities_read  on localities for select to rentfit_api, rentfit_jobs using (true);
create policy pois_read        on pois       for select to rentfit_api, rentfit_jobs using (true);
create policy cities_system     on cities     for all to rentfit_api, rentfit_jobs
  using (app.is_role('system')) with check (app.is_role('system'));
create policy localities_system on localities for all to rentfit_api, rentfit_jobs
  using (app.is_role('system')) with check (app.is_role('system'));
create policy pois_system       on pois       for all to rentfit_api, rentfit_jobs
  using (app.is_role('system')) with check (app.is_role('system'));

-- Profiles: own row only. Inserts go through app.create_profile.
create policy profiles_self_read on profiles for select to rentfit_api
  using (id = app.current_user_id());
create policy profiles_self_update on profiles for update to rentfit_api
  using (id = app.current_user_id()) with check (id = app.current_user_id());
create policy profiles_system on profiles for all to rentfit_api, rentfit_jobs
  using (app.is_role('system')) with check (app.is_role('system'));

-- Role is immutable (backend plan §6).
create or replace function app.profiles_guard() returns trigger
  language plpgsql
as $$
begin
  if new.role <> old.role or new.id <> old.id then
    raise exception 'role is immutable' using errcode = 'Z1001';
  end if;
  new.updated_at := now();
  return new;
end
$$;
create trigger profiles_guard before update on profiles for each row execute function app.profiles_guard();

-- Internal tables: system context only.
create policy llm_cache_system   on llm_cache   for all to rentfit_api, rentfit_jobs
  using (app.is_role('system')) with check (app.is_role('system'));
create policy llm_budget_system  on llm_budget  for all to rentfit_api, rentfit_jobs
  using (app.is_role('system')) with check (app.is_role('system'));
create policy llm_rpm_system     on llm_rpm     for all to rentfit_api, rentfit_jobs
  using (app.is_role('system')) with check (app.is_role('system'));
create policy rate_limits_system on rate_limits for all to rentfit_api, rentfit_jobs
  using (app.is_role('system')) with check (app.is_role('system'));
create policy job_runs_system    on job_runs    for all to rentfit_api, rentfit_jobs
  using (app.is_role('system')) with check (app.is_role('system'));
-- Users can poll the status of their own runs.
create policy job_runs_owner_read on job_runs for select to rentfit_api
  using (owner_id = app.current_user_id());

do $$
declare r text;
begin
  foreach r in array array['anon', 'authenticated'] loop
    if exists (select 1 from pg_roles where rolname = r) then
      execute format('revoke all on all tables in schema public from %I', r);
    end if;
  end loop;
end
$$;
