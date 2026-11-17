# 6. Embeddings from a Supabase Edge Function (gte-small)

**Status:** accepted (Phase 2)

## Context
Search needs text embeddings for 100+ listings and every query, at no cost and without another
provider key.

## Decision
A Supabase Edge Function (`embed`) runs gte-small with Supabase's built-in inference (384 dims,
normalised), behind a shared secret. Listings are chunked (a summary from the fields, then title and
description) and re-embedded by an Inngest job when a published listing changes; unchanged chunks
keep their vectors. Tests use a deterministic hashing embedder.

## Consequences
- Free, same project as the data, ~0.5-2 s per call (cold starts add more; the client retries 5xx).
- gte-small is English-first; Hinglish queries rely more on the full-text side and on the parser.
