-- Phase 3: tenant data (backend plan §4.1): shortlists, saved searches, enquiries, notifications,
-- commute cache, and the public listing view used by search and the map.

create table shortlists (
  tenant_id   uuid not null references profiles (id) on delete cascade,
  listing_id  uuid not null references listings (id) on delete cascade,
  created_at  timestamptz not null default now(),
  primary key (tenant_id, listing_id)
);

create table saved_searches (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references profiles (id) on delete cascade,
  name        text not null check (length(name) between 1 and 80),
  filters     jsonb not null,
  created_at  timestamptz not null default now()
);
create index saved_searches_tenant_idx on saved_searches (tenant_id, created_at desc);

-- One enquiry per tenant per listing; messages are contact-stripped by the API.
create table enquiries (
  id               uuid primary key default gen_random_uuid(),
  listing_id       uuid not null references listings (id) on delete cascade,
  tenant_id        uuid not null references profiles (id) on delete cascade,
  landlord_id      uuid not null references profiles (id) on delete cascade,
  last_message_at  timestamptz not null default now(),
  created_at       timestamptz not null default now(),
  unique (listing_id, tenant_id)
);
create index enquiries_tenant_idx on enquiries (tenant_id, last_message_at desc);
create index enquiries_landlord_idx on enquiries (landlord_id, last_message_at desc);

create table enquiry_messages (
  id          bigserial primary key,
  enquiry_id  uuid not null references enquiries (id) on delete cascade,
  sender_id   uuid not null references profiles (id) on delete cascade,
  body        text not null check (length(body) between 1 and 2000),
  created_at  timestamptz not null default now()
);
create index enquiry_messages_enquiry_idx on enquiry_messages (enquiry_id, id);

-- In-app notifications (notify-enquiry).
create table notifications (
  id          bigserial primary key,
  user_id     uuid not null references profiles (id) on delete cascade,
  kind        text not null check (kind in ('enquiry_message')),
  entity_id   uuid not null,
  created_at  timestamptz not null default now(),
  read_at     timestamptz
);
create index notifications_user_idx on notifications (user_id, created_at desc);

create table commute_cache (
  origin_geohash  text not null,
  poi_id          uuid not null references pois (id) on delete cascade,
  mode            text not null check (mode in ('car', 'two_wheeler', 'walk')),
  minutes         real not null,
  provider        text not null check (provider in ('ors', 'haversine')),
  expires_at      timestamptz not null,
  primary key (origin_geohash, poi_id, mode)
);

-- Published listings without landlord-only columns (landlord_id, flags, version). security_invoker
-- keeps the caller's RLS: tenants see published rows.
create view public_listings with (security_invoker = true) as
  select id, city, locality_id, location, bhk, rent, deposit, maintenance, furnishing, sqft, floor,
         total_floors, tenant_pref, pets, parking, gated, no_brokerage, available_from, amenities,
         title, description, published_at
  from listings where status = 'published';

-- ------------------------------------------------------------------ RLS
alter table shortlists       enable row level security;
alter table saved_searches   enable row level security;
alter table enquiries        enable row level security;
alter table enquiry_messages enable row level security;
alter table notifications    enable row level security;
alter table commute_cache    enable row level security;

create or replace function app.in_enquiry(p_enquiry uuid) returns boolean
  language sql stable security definer set search_path = public, pg_temp
as $$ select exists (select 1 from enquiries where id = p_enquiry
                     and app.current_user_id() in (tenant_id, landlord_id)) $$;

create policy shortlists_own on shortlists for all to rentfit_api
  using (app.is_role('tenant') and tenant_id = app.current_user_id())
  with check (app.is_role('tenant') and tenant_id = app.current_user_id() and app.listing_is_published(listing_id));

create policy saved_searches_own on saved_searches for all to rentfit_api
  using (app.is_role('tenant') and tenant_id = app.current_user_id())
  with check (app.is_role('tenant') and tenant_id = app.current_user_id());

-- Tenants open enquiries on published listings; both parties read them.
create policy enquiries_read on enquiries for select to rentfit_api
  using (app.current_user_id() in (tenant_id, landlord_id));
create policy enquiries_tenant_insert on enquiries for insert to rentfit_api
  with check (app.is_role('tenant') and tenant_id = app.current_user_id() and app.listing_is_published(listing_id));
create policy enquiries_system on enquiries for all to rentfit_api, rentfit_jobs
  using (app.is_role('system')) with check (app.is_role('system'));

create policy enquiry_messages_read on enquiry_messages for select to rentfit_api
  using (app.in_enquiry(enquiry_id));
create policy enquiry_messages_insert on enquiry_messages for insert to rentfit_api
  with check (app.in_enquiry(enquiry_id) and sender_id = app.current_user_id());
create policy enquiry_messages_system on enquiry_messages for all to rentfit_api, rentfit_jobs
  using (app.is_role('system')) with check (app.is_role('system'));
revoke update, delete on enquiry_messages from rentfit_api;

create policy notifications_own_read on notifications for select to rentfit_api
  using (user_id = app.current_user_id());
create policy notifications_own_update on notifications for update to rentfit_api
  using (user_id = app.current_user_id()) with check (user_id = app.current_user_id());
create policy notifications_system on notifications for all to rentfit_api, rentfit_jobs
  using (app.is_role('system')) with check (app.is_role('system'));

create policy commute_cache_system on commute_cache for all to rentfit_api, rentfit_jobs
  using (app.is_role('system')) with check (app.is_role('system'));

revoke all on shortlists, saved_searches, enquiries, enquiry_messages, notifications, commute_cache,
  public_listings from anon, authenticated;
grant select on public_listings to rentfit_api, rentfit_jobs;
