-- Phase 0 extensions. pgvector is added in Phase 2 with the retrieval tables.
-- Supabase convention: extensions live in the `extensions` schema.
create schema if not exists extensions;
create extension if not exists postgis  with schema extensions;
create extension if not exists pg_trgm  with schema extensions;
create extension if not exists pgcrypto with schema extensions;
