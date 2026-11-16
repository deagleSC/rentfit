-- Reference data: cities, OSM localities, POIs (backend plan §4.1, §14.1). Written only by seed scripts.

create table cities (
  slug        text primary key check (slug ~ '^[a-z-]+$'),
  name        text not null,
  center      geography(Point, 4326) not null,
  default_zoom real not null default 11
);

create table localities (
  id           uuid primary key default gen_random_uuid(),
  city         text not null references cities (slug),
  name         text not null,
  osm_id       bigint unique,
  boundary     geography(MultiPolygon, 4326) not null,
  centroid     geography(Point, 4326) not null,
  -- {"1": 18000, "2": 28000, "3": 42000}: monthly rent in INR by bhk, hand-set (§14.1)
  median_rent  jsonb not null default '{}',
  unique (city, name)
);
create index localities_boundary_idx on localities using gist (boundary);
create index localities_name_trgm_idx on localities using gin (name extensions.gin_trgm_ops);

create table pois (
  id        uuid primary key default gen_random_uuid(),
  city      text not null references cities (slug),
  name      text not null,
  kind      text not null check (kind in ('tech_park', 'metro_station', 'rail_station', 'hospital', 'college', 'other')),
  osm_id    bigint unique,
  location  geography(Point, 4326) not null
);
create index pois_city_kind_idx on pois (city, kind);
create index pois_location_idx on pois using gist (location);
create index pois_name_trgm_idx on pois using gin (name extensions.gin_trgm_ops);
