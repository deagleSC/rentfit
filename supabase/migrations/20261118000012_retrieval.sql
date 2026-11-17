-- Phase 2: retrieval data (backend plan §4.1, §9, §14.1).
-- Embeddings are gte-small (384 dimensions, normalised), from the `embed` Edge Function.

create extension if not exists vector with schema extensions;

-- One row per chunk of a listing's text. Rows exist only while the listing is published;
-- embed-listing rewrites them on every change and deletes them when the listing leaves search.
create table listing_chunks (
  id            bigserial primary key,
  listing_id    uuid not null references listings (id) on delete cascade,
  chunk_index   smallint not null,
  content       text not null,
  content_hash  text not null,
  embedding     extensions.vector(384) not null,
  tsv           tsvector generated always as (to_tsvector('simple', content)) stored,
  created_at    timestamptz not null default now(),
  unique (listing_id, chunk_index)
);
create index listing_chunks_embedding_idx on listing_chunks using hnsw (embedding extensions.vector_cosine_ops);
create index listing_chunks_tsv_idx on listing_chunks using gin (tsv);

-- Text about a locality with its source. OSM notes are written by template from counted facts;
-- `facts` holds the numbers the text states, so citations can be checked.
create table locality_notes (
  id           uuid primary key default gen_random_uuid(),
  locality_id  uuid not null references localities (id) on delete cascade,
  source       text not null check (source in ('osm', 'wikipedia')),
  source_url   text,
  body         text not null,
  facts        jsonb not null default '{}',
  updated_at   timestamptz not null default now(),
  unique (locality_id, source)
);

create table locality_chunks (
  id            bigserial primary key,
  note_id       uuid not null references locality_notes (id) on delete cascade,
  locality_id   uuid not null references localities (id) on delete cascade,
  chunk_index   smallint not null,
  content       text not null,
  content_hash  text not null,
  embedding     extensions.vector(384) not null,
  tsv           tsvector generated always as (to_tsvector('simple', content)) stored,
  unique (note_id, chunk_index)
);
create index locality_chunks_embedding_idx on locality_chunks using hnsw (embedding extensions.vector_cosine_ops);
create index locality_chunks_tsv_idx on locality_chunks using gin (tsv);
create index locality_chunks_locality_idx on locality_chunks (locality_id);

-- ------------------------------------------------------------------ RLS
alter table listing_chunks  enable row level security;
alter table locality_notes  enable row level security;
alter table locality_chunks enable row level security;

-- Listing chunks: anyone signed in may read chunks of published listings (search); landlords their own.
create policy listing_chunks_read on listing_chunks for select to rentfit_api
  using (app.listing_is_published(listing_id)
         or (app.is_role('landlord') and app.owns_listing(listing_id)));
create policy listing_chunks_system on listing_chunks for all to rentfit_api, rentfit_jobs
  using (app.is_role('system')) with check (app.is_role('system'));

-- Locality text is public reference data.
create policy locality_notes_read  on locality_notes  for select to rentfit_api, rentfit_jobs using (true);
create policy locality_chunks_read on locality_chunks for select to rentfit_api, rentfit_jobs using (true);
create policy locality_notes_system on locality_notes for all to rentfit_api, rentfit_jobs
  using (app.is_role('system')) with check (app.is_role('system'));
create policy locality_chunks_system on locality_chunks for all to rentfit_api, rentfit_jobs
  using (app.is_role('system')) with check (app.is_role('system'));

revoke all on listing_chunks, locality_notes, locality_chunks from anon, authenticated;
