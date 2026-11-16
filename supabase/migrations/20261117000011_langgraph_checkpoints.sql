-- LangGraph checkpoint tables (backend plan §4.1), as created by langgraph-checkpoint-postgres 3.2.0
-- migrations 0–9. System-only: the API checks thread ownership in `chats` first, then reads or writes
-- checkpoints in system context.

create table checkpoint_migrations (v integer primary key);

create table checkpoints (
  thread_id             text not null,
  checkpoint_ns         text not null default '',
  checkpoint_id         text not null,
  parent_checkpoint_id  text,
  type                  text,
  checkpoint            jsonb not null,
  metadata              jsonb not null default '{}',
  primary key (thread_id, checkpoint_ns, checkpoint_id)
);

create table checkpoint_blobs (
  thread_id      text not null,
  checkpoint_ns  text not null default '',
  channel        text not null,
  version        text not null,
  type           text not null,
  blob           bytea,
  primary key (thread_id, checkpoint_ns, channel, version)
);

create table checkpoint_writes (
  thread_id      text not null,
  checkpoint_ns  text not null default '',
  checkpoint_id  text not null,
  task_id        text not null,
  idx            integer not null,
  channel        text not null,
  type           text,
  blob           bytea not null,
  task_path      text not null default '',
  primary key (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);

create index checkpoints_thread_id_idx on checkpoints (thread_id);
create index checkpoint_blobs_thread_id_idx on checkpoint_blobs (thread_id);
create index checkpoint_writes_thread_id_idx on checkpoint_writes (thread_id);

-- Tell the library its schema is current, so it never runs DDL at runtime.
insert into checkpoint_migrations (v) select generate_series(0, 9);

alter table checkpoint_migrations enable row level security;
alter table checkpoints           enable row level security;
alter table checkpoint_blobs      enable row level security;
alter table checkpoint_writes     enable row level security;

create policy checkpoint_migrations_system on checkpoint_migrations for all to rentfit_api, rentfit_jobs
  using (app.is_role('system')) with check (app.is_role('system'));
create policy checkpoints_system on checkpoints for all to rentfit_api, rentfit_jobs
  using (app.is_role('system')) with check (app.is_role('system'));
create policy checkpoint_blobs_system on checkpoint_blobs for all to rentfit_api, rentfit_jobs
  using (app.is_role('system')) with check (app.is_role('system'));
create policy checkpoint_writes_system on checkpoint_writes for all to rentfit_api, rentfit_jobs
  using (app.is_role('system')) with check (app.is_role('system'));

revoke all on checkpoint_migrations, checkpoints, checkpoint_blobs, checkpoint_writes from anon, authenticated;
