-- Phase 1: listings, photos, status history, chat threads (backend plan §4, §8).

create table listings (
  id              uuid primary key default gen_random_uuid(),
  landlord_id     uuid not null references profiles (id) on delete cascade,
  status          text not null default 'draft' check (status in ('draft', 'published', 'paused', 'let')),
  version         int not null default 1,
  city            text references cities (slug),
  locality_id     uuid references localities (id),
  location        geography(Point, 4326),
  bhk             smallint check (bhk between 1 and 6),
  rent            int check (rent > 0),
  deposit         int check (deposit >= 0),
  maintenance     int check (maintenance >= 0),
  furnishing      text check (furnishing in ('unfurnished', 'semi', 'full')),
  sqft            int check (sqft between 100 and 20000),
  floor           smallint check (floor between -2 and 120),
  total_floors    smallint check (total_floors between 1 and 120),
  tenant_pref     text check (tenant_pref in ('any', 'family', 'bachelors')),
  pets            boolean,
  parking         text check (parking in ('none', 'bike', 'car', 'both')),
  gated           boolean,
  no_brokerage    boolean,
  available_from  date,
  amenities       text[] not null default '{}',
  title           text check (length(title) <= 120),
  description     text check (length(description) <= 4000),
  flags           jsonb not null default '{}',
  published_at    timestamptz,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  check (deposit is null or rent is null or deposit <= 12 * rent),
  check (status <> 'published' or published_at is not null)
);
create index listings_landlord_idx on listings (landlord_id, updated_at desc);
create index listings_search_idx on listings (city, status, bhk, rent);
create index listings_location_idx on listings using gist (location);

create table listing_photos (
  id            uuid primary key default gen_random_uuid(),
  listing_id    uuid not null references listings (id) on delete cascade,
  storage_path  text not null unique,
  thumb_path    text not null unique,
  bytes         int not null check (bytes > 0),
  sha256        text check (sha256 ~ '^[0-9a-f]{64}$'),
  position      smallint not null default 0,
  confirmed     boolean not null default false,
  created_at    timestamptz not null default now()
);
create index listing_photos_listing_idx on listing_photos (listing_id, position);

-- Append-only status history.
create table listing_events (
  id           bigserial primary key,
  listing_id   uuid not null references listings (id) on delete cascade,
  from_status  text,
  to_status    text not null,
  actor_id     uuid,
  reason       text,
  created_at   timestamptz not null default now()
);
create index listing_events_listing_idx on listing_events (listing_id, created_at);

create table chats (
  id          uuid primary key default gen_random_uuid(),
  owner_id    uuid not null references profiles (id) on delete cascade,
  kind        text not null check (kind in ('listing', 'search')),
  listing_id  uuid references listings (id) on delete cascade,
  thread_id   text not null unique,
  last_filters     jsonb,
  last_result_ids  uuid[],
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  check ((kind = 'listing') = (listing_id is not null))
);
create unique index chats_listing_idx on chats (listing_id) where kind = 'listing';
create index chats_owner_idx on chats (owner_id, updated_at desc);

-- ------------------------------------------------------------------ RLS
alter table listings       enable row level security;
alter table listing_photos enable row level security;
alter table listing_events enable row level security;
alter table chats          enable row level security;

create or replace function app.owns_listing(p_listing uuid) returns boolean
  language sql stable security definer set search_path = public, pg_temp
as $$ select exists (select 1 from listings where id = p_listing and landlord_id = app.current_user_id()) $$;

create or replace function app.listing_is_published(p_listing uuid) returns boolean
  language sql stable security definer set search_path = public, pg_temp
as $$ select exists (select 1 from listings where id = p_listing and status = 'published') $$;

-- listings
create policy listings_landlord_all on listings for all to rentfit_api
  using (app.is_role('landlord') and landlord_id = app.current_user_id())
  with check (app.is_role('landlord') and landlord_id = app.current_user_id());
create policy listings_tenant_read on listings for select to rentfit_api
  using (app.is_role('tenant') and status = 'published');
create policy listings_system on listings for all to rentfit_api, rentfit_jobs
  using (app.is_role('system')) with check (app.is_role('system'));

-- photos
create policy photos_landlord_all on listing_photos for all to rentfit_api
  using (app.is_role('landlord') and app.owns_listing(listing_id))
  with check (app.is_role('landlord') and app.owns_listing(listing_id));
create policy photos_tenant_read on listing_photos for select to rentfit_api
  using (app.is_role('tenant') and confirmed and app.listing_is_published(listing_id));
create policy photos_system on listing_photos for all to rentfit_api, rentfit_jobs
  using (app.is_role('system')) with check (app.is_role('system'));

-- events: landlords read their own history and append through the API; never update/delete.
create policy events_landlord_read on listing_events for select to rentfit_api
  using (app.is_role('landlord') and app.owns_listing(listing_id));
create policy events_landlord_insert on listing_events for insert to rentfit_api
  with check (app.is_role('landlord') and app.owns_listing(listing_id) and actor_id = app.current_user_id());
create policy listing_events_system on listing_events for all to rentfit_api, rentfit_jobs
  using (app.is_role('system')) with check (app.is_role('system'));
revoke update, delete on listing_events from rentfit_api, rentfit_jobs;

-- chats
create policy chats_owner_all on chats for all to rentfit_api
  using (owner_id = app.current_user_id()) with check (owner_id = app.current_user_id());
create policy chats_system on chats for all to rentfit_api, rentfit_jobs
  using (app.is_role('system')) with check (app.is_role('system'));

revoke all on listings, listing_photos, listing_events, chats from anon, authenticated;
