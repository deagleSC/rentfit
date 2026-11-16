-- Request settings a job reads from its row (events carry IDs only), and an append-only audit log.
alter table job_runs add column params jsonb not null default '{}';

create table events (
  id          bigserial primary key,
  actor_id    uuid,
  type        text not null,
  entity      text not null,
  entity_id   uuid,
  payload     jsonb not null default '{}',
  created_at  timestamptz not null default now()
);
create index events_entity_idx on events (entity, entity_id);

alter table events enable row level security;
create policy events_system_read   on events for select to rentfit_api, rentfit_jobs using (app.is_role('system'));
create policy events_system_insert on events for insert to rentfit_api, rentfit_jobs with check (app.is_role('system'));
-- Append-only: no update/delete policy, and no grant.
revoke update, delete on events from rentfit_api, rentfit_jobs;
revoke all on events from anon, authenticated;
