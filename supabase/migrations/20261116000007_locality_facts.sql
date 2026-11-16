-- OSM-derived counts per locality (schools, parks, supermarkets, hospitals), used for locality notes.
alter table localities add column facts jsonb not null default '{}';
