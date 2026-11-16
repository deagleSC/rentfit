-- LLM cache, budget and throttle; background job status (backend plan §9, §10).

create table llm_cache (
  key_hash        text primary key,
  response        jsonb not null,
  model_id        text not null,
  prompt_id       text not null,
  prompt_version  int not null,
  created_at      timestamptz not null default now()
);
create index llm_cache_prompt_idx on llm_cache (prompt_id, prompt_version);

-- One row per UTC day and model. model_id '*' is the account-wide counter for LLM_DAILY_CAP;
-- per-model rows record which model actually served each call.
create table llm_budget (
  day            date not null,
  model_id       text not null,
  requests_used  int not null default 0 check (requests_used >= 0),
  primary key (day, model_id)
);

-- Request-path calls only (chats). Inngest throttles background calls.
create table llm_rpm (
  minute_bucket  timestamptz primary key,
  requests       int not null default 0 check (requests >= 0)
);

create table job_runs (
  id              uuid primary key default gen_random_uuid(),
  type            text not null,
  entity          text not null,
  entity_id       uuid not null,
  owner_id        uuid references profiles (id) on delete cascade,
  status          text not null default 'queued'
                    check (status in ('queued', 'running', 'deferred_budget', 'done', 'failed')),
  attempts        int not null default 0,
  inngest_run_id  text,
  last_error      text,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);
create index job_runs_entity_idx on job_runs (entity, entity_id);
create index job_runs_status_idx on job_runs (status, updated_at);

create table rate_limits (
  key           text not null,
  window_start  timestamptz not null,
  count         int not null default 0,
  primary key (key, window_start)
);
