# RentFit v2: Backend Implementation Plan

This plan is for building the RentFit v2 backend: a FastAPI service on Vercel, Supabase for the database, auth, storage and embeddings, and Inngest for background jobs. It turns [PLAN.md](../../PLAN.md) (the "product plan") into a build-ready plan. Section references such as "§6" point to that file. The frontend plan, [frontend-implementation-plan.md](./frontend-implementation-plan.md), uses the API defined in [§7 API surface](#7-api-surface).

RentFit v1 ([rentfit-meta](https://github.com/deagleSC/rentfit-meta): Express + MongoDB API, Next.js app, marketing site) is **not** migrated. Only the MapLibre map component is carried over (frontend plan §6). Cities, the `{ success, data }` envelope, and the OpenRouter provider stay the same as v1.

Libraries the product plan does not name are marked **(chosen here)**. Each one can be swapped without changing the architecture.

---

## 1. Scope and principles

The backend owns every rule, every database read and write, and every model call. No frontend app queries the database directly.

| Principle | What it means in the backend |
| --- | --- |
| API is the only gateway; RLS is the backstop | The API connects as `rentfit_api` (no `BYPASSRLS`), sets claims per transaction, and every table has policies |
| Models reason, code calculates | Models produce `ListingDraft`, `SearchFilters`, patches and wording. Rent ranges, RRF, relaxation, commute minutes and ranking weights are plain Python or SQL |
| One edit path | Chat edits and form edits both end at `domain/listing_patches.apply_patches()` |
| Every claim cites, code verifies | `pipeline/citations.py` checks each cited value against the listing row or locality note; a failing claim is dropped and logged |
| Contact details never reach a model | `pipeline/redact.py` strips phones, emails and URLs from every description write; phone lives only in `profiles` and is never returned by any endpoint |
| Relaxation is explicit | `relax` returns the list of loosened constraints, and the response must state them |
| Cost-aware | All model calls go through `call_structured()` (cache, daily cap, RPM throttle, fallback) |

**Decisions (2026-11-16):** login is required in both apps (no anonymous search); listings are assumed legitimate (no scam/injection screening, no moderation); enquiries are in-app only and contact details are never revealed.

Out of scope for v1: payments, rent agreements, KYC, mobile apps, admin/moderation app, saved-search alerts, WhatsApp bot, Hindi voice input (each tracked as a GitHub issue).

---

## 2. Stack

| Concern | Choice | Source |
| --- | --- | --- |
| Runtime | Python 3.12, FastAPI + Pydantic v2, on Vercel Python runtime (Dockerfile kept ready) | plan + decision |
| Package manager | `uv` with lockfile, exported to `requirements.txt` | plan |
| DB driver | `psycopg` 3 async + `psycopg_pool`, `prepare_threshold=None` for the transaction pooler | chosen here (as Hirevine) |
| Database | One Supabase project (production); local Supabase / Postgres for dev and tests | decision |
| Migrations | Plain SQL in `supabase/migrations/`, Supabase CLI | plan |
| Geo | PostGIS `geography` columns; `ST_Contains` for pin → locality, `ST_DWithin` for comparables and bbox | chosen here |
| Locality data | OpenStreetMap (boundaries + facts), fetched once via Overpass, committed as GeoJSON/JSON (ODbL attribution) | decision |
| AI orchestration | LangGraph + `langgraph-checkpoint-postgres`, only for the listing and search conversations | plan |
| LLM client | `openai` SDK → OpenRouter | plan |
| Embeddings | Edge Function `embed` (`gte-small`, 384-d); `HashingEmbedder` offline | plan |
| Full text | Postgres `tsvector` (`simple` config, so Hinglish tokens survive) + `pg_trgm` for locality names | chosen here |
| Rerank | Model rerank via `call_structured` (listwise, top 20) | chosen here |
| Commute | `CommuteProvider`: `OrsProvider` (OpenRouteService Matrix API) with `HaversineProvider` fallback | decision |
| Jobs | Inngest Python SDK mounted at `/api/inngest`, `job_runs` table | plan |
| Tracing / errors | Langfuse, Sentry | plan |
| Tests / evals | pytest, `pytest-asyncio`, `hypothesis`, `scikit-learn` metrics, `locust` for latency | plan + chosen here |
| Lint / types | ruff, mypy (strict on `domain/`, `llm/`, `pipeline/`) | plan |

---

## 3. Repository layout

Repo: `github.com/deagleSC/rentfit`.

```
rentfit/
├─ apps/
│  ├─ landlord/ tenant/ marketing/     # Next.js (frontend plan)
│  └─ api/
│     ├─ api/index.py                  # Vercel entry
│     ├─ app/
│     │  ├─ main.py
│     │  ├─ core/        config.py, auth.py, db.py, errors.py, ratelimit.py, monitoring.py
│     │  ├─ api/routers/
│     │  │  ├─ landlord/ listings.py, chat.py, photos.py, enquiries.py
│     │  │  ├─ tenant/   search.py, chats.py, shortlists.py, saved_searches.py, enquiries.py
│     │  │  ├─ public.py # listings/{id}, map/listings, cities, localities, pois (auth required)
│     │  │  └─ me.py
│     │  ├─ domain/
│     │  │  ├─ listing.py          # ListingDraft, Listing, enums, required-field rules
│     │  │  ├─ listing_patches.py  # Patch ops, apply, diff, undo
│     │  │  ├─ state_machine.py    # transition(listing, to, actor)
│     │  │  ├─ filters.py          # SearchFilters, FilterPatch, merge, slang map
│     │  │  ├─ relax.py            # relaxation ladder
│     │  │  └─ scoring.py          # RRF, soft-preference weights, rent percentiles
│     │  ├─ llm/         wrapper.py, models.py, cache.py, budget.py, tracing.py, fake.py, prompts/, prompts.lock.json
│     │  ├─ agents/      common.py, listing_agent.py, search_agent.py
│     │  ├─ pipeline/    normalise.py, redact.py, chunk.py, hybrid.py, rerank.py, citations.py
│     │  ├─ services/    geo.py, commute.py, retrieval.py, storage.py, embedder.py, rent_suggestion.py
│     │  └─ jobs/        client.py, dispatcher.py, runs.py, functions/
│     ├─ evals/          datasets/, runners/, reports/, readme_results.py
│     ├─ scripts/        db_local.py, fetch_osm.py, seed.py, seed_data/
│     ├─ tests/          unit/, property/, api/, rls/
│     ├─ pyproject.toml, uv.lock, vercel.json, Dockerfile
├─ supabase/  config.toml, migrations/, functions/embed/index.ts
└─ packages/api-client/   # generated from OpenAPI
```

---

## 4. Data model and migrations

Status, ownership, geo and anything filtered on live in columns. Amenities are a text array; free-form extras use JSONB validated by Pydantic.

### 4.1 Migration order

Migrations are named `<timestamp>_<name>.sql` and added by the phase that needs them (never inserted before an applied file).

| Phase | File | Contents |
| --- | --- | --- |
| 0 | `extensions` | `postgis`, `pg_trgm`, `pgcrypto` (`vector` added in phase 2) |
| 0 | `app_schema` | `app` schema, claim helpers (4.3), roles `rentfit_api`, `rentfit_jobs` |
| 0 | `reference` | `cities`, `localities` (polygon `geography`, `osm_id`, `median_rent jsonb` by bhk), `pois` |
| 0 | `profiles` | `profiles` + trigger creating a row on `auth.users` insert (role from signup metadata) |
| 0 | `ai_infra` | `llm_cache`, `llm_budget`, `llm_rpm`, `job_runs` |
| 0 | `rls_base` | RLS on the above |
| 1 | `listings` | `listings`, `listing_photos`, `listing_events`, `chats`; RLS |
| 1 | `langgraph_checkpoints` | tables from `PostgresSaver.setup()`, committed as SQL |
| 2 | `retrieval` | `vector` extension, `listing_chunks` (HNSW on embedding, GIN on tsv), `locality_notes`, `locality_chunks` |
| 3 | `tenant` | `shortlists`, `saved_searches`, `enquiries`, `enquiry_messages`, `commute_cache`; RLS |
| 3 | `map_views` | `public_listings` view (published only, no landlord fields), `map_listings(bbox, filters)` SQL function |

### 4.2 Tables (additions to §5)

- `listings`: `location geography(Point)` generated from `lat/lng`; `flags jsonb` holds only `{locality_mismatch}`; `version int` for optimistic concurrency; `published_at`.
- `listing_photos`: `storage_path`, `thumb_path`, `bytes`, `sha256`, `order`.
- `listing_events`: append-only (no update/delete grant).
- `chats`: `thread_id` = LangGraph thread; `listing_id` nullable (listing chats); `last_filters jsonb`, `last_result_ids uuid[]` for search chats.
- `locality_notes`: `source` = `osm` or `wikipedia`, `source_url`, `facts jsonb` (for OSM-derived notes, the numbers the text states).
- `commute_cache`: key `(origin_geohash7, poi_id, mode)`, `minutes`, `provider` (`ors`/`haversine`), `expires_at` 30 days.

### 4.3 RLS helpers and roles

Same shape as Hirevine: `app.claims()`, `app.current_user_id()`, `app.current_role()` read `current_setting('app.claims')`, which `core/db.py` sets with `set_config(..., true)` inside each request transaction. `rentfit_api` and `rentfit_jobs` are login roles without `BYPASSRLS`.

### 4.4 RLS policy matrix

| Table | Landlord | Tenant |
| --- | --- | --- |
| `listings` | all where `landlord_id = uid` | select where `status = 'published'` |
| `listing_photos` | all via own listing | select via published listing |
| `listing_events` | select own | none |
| `enquiries`, `enquiry_messages` | select/insert where `landlord_id = uid` | select/insert where `tenant_id = uid` |
| `shortlists`, `saved_searches` | none | all own |
| `chats` | all own | all own |
| `profiles` | select/update own | select/update own |
| reference tables, `locality_notes` | select | select |
| `llm_*`, `job_runs`, chunks, `commute_cache` | none (API-internal / `rentfit_jobs`) | none |

Anonymous requests are rejected by the API before reaching the DB. `tests/rls/` asserts every cell, including: a tenant cannot read a `draft` or `paused` listing; landlord A cannot read landlord B's listings or enquiries; nobody can read another user's `profiles.phone`.

---

## 5. Database access and request context

`core/db.py` exposes `user_tx(user)` (sets claims, one transaction per request) and `jobs_tx()` (role `rentfit_jobs`, used only inside Inngest functions). Events to Inngest are queued on the transaction and sent **after commit**.

## 6. Auth

Same as Hirevine: Supabase Auth with **email + password and magic link**. `core/auth.py` verifies the JWT with JWKS (`pyjwt`), loads `profiles.role`, and provides `CurrentUser`, `require_landlord`, `require_tenant`. Every route except `/health` and `/api/inngest` requires a user. Role is chosen at signup and immutable. Apps send `Authorization: Bearer` (no cookies, unlike v1).

---

## 7. API surface

### 7.1 Conventions

- Prefix `/v1`. Envelope `{ success, data }` / `{ success, error: { code, message, details } }` (kept from v1).
- SSE for chat: events `token`, `card` (listing card), `pins` (map pins), `patch` (draft diff), `question`, `relaxed`, `citations`, `done`, `error`.
- Long work returns `202 { job_run_id }`; clients poll `GET /v1/job-runs/{id}`.
- `PATCH` on listings requires `If-Match: <version>`; mismatch → `409`.
- Rate limits: chat 20/min per user, other writes 60/min per user.

### 7.2 Landlord (`/v1/landlord`)

| Method | Path | Notes |
| --- | --- | --- |
| GET/POST | `/listings` | POST creates an empty draft + chat thread |
| GET/PATCH | `/listings/{id}` | PATCH body is `list[Patch]` (same path as chat edits) |
| POST | `/listings/{id}/chat` | SSE; runs `listing_agent` |
| POST | `/listings/{id}/photos` | `{content_type, bytes}` → signed upload URLs (full + thumb); rejects > 5 MB or > 15 photos; `POST …/photos/{pid}/confirm` checks the object and registers it |
| PATCH/DELETE | `/listings/{id}/photos/{pid}` | reorder / remove |
| PUT | `/listings/{id}/location` | `{lat, lng}` → locality lookup, mismatch flag |
| GET | `/listings/{id}/rent-suggestion` | p25/p50/p75 + cited comparable IDs |
| POST | `/listings/{id}/publish` `…/pause` `…/resume` `…/let` | state machine transitions |
| GET | `/enquiries`, `/enquiries/{id}` | inbox |
| POST | `/enquiries/{id}/messages` | reply |

### 7.3 Tenant (`/v1/tenant`) and shared (`/v1`)

| Method | Path | Notes |
| --- | --- | --- |
| POST | `/tenant/search/chat` | SSE; body `{chat_id?, message, bbox?}` |
| GET | `/tenant/chats`, `/tenant/chats/{id}` | history incl. last filters and results |
| GET/PUT/DELETE | `/tenant/shortlists[/{listing_id}]` | |
| GET/POST/DELETE | `/tenant/saved-searches` | stores `SearchFilters` (no alerts in v1) |
| GET/POST | `/tenant/enquiries`, `/tenant/enquiries/{id}/messages` | one enquiry per tenant per listing |
| GET | `/listings/{id}` | published listing, photos as signed URLs |
| GET | `/map/listings?bbox=&filters=` | pins only (id, lat, lng, rent, bhk), max 500 |
| GET | `/cities`, `/localities?city=`, `/pois?city=&kind=` | reference |
| GET/PATCH | `/me` | |
| GET | `/health` | no auth |

---

## 8. Listing domain

### 8.1 `ListingDraft`

Pydantic model mirroring the `listings` columns, every field optional. `REQUIRED_TO_PUBLISH = [city, locality_id, location, bhk, rent, deposit, furnishing, tenant_pref, available_from]` + 3–15 photos. `missing_fields(draft)` returns them in a fixed priority order, which drives `ask_missing`.

**Photo limits:** JPEG, PNG, WebP or HEIC; **5 MB max per uploaded file** (enforced by the signed-upload policy and re-checked on confirm). The browser converts to WebP before upload: full 1600 px long edge, thumbnail 480 px. HEIC is converted client-side.

### 8.2 Patches

Discriminated union: `set(field, value)`, `add_amenity`, `remove_amenity`, `set_description`. `apply_patches(listing, patches, actor)` validates the result, runs `redact.strip_contacts` on description changes, bumps `version`, writes a `listing_events` row for status changes, and returns a diff. Editing a `published` listing's text or location sends `listing/updated`, which re-embeds it; the listing stays published.

### 8.3 State machine

```
draft ──publish──▶ published ──pause──▶ paused
                      ▲  │                │
                      │  └──let──▶ let    │
                      └─────resume────────┘
```

`transition()` is the only writer of `status`; illegal moves raise `409`. `publish` succeeds only when `missing_fields` is empty; otherwise `422` with the list. There is no screening step (see §12).

---

## 9. Background jobs (Inngest)

Rules as in Hirevine: events carry IDs only; side effects only in `step.run`; steps idempotent; each function writes `job_runs`; logic lives in `pipeline/`/`services/`, not in the function.

| Function | Trigger | Steps | Settings |
| --- | --- | --- | --- |
| `embed-listing` | `listing/published`, `listing/updated` | `load`, `chunk`, `embed`, `upsert_chunks_tsv` | concurrency 4, retries 3 |
| `embed-locality-notes` | `locality_notes/changed` | `chunk`, `embed` | concurrency 2 |
| `notify-enquiry` | `enquiry/message_created` | in-app notification row | — |
| `housekeeping` | cron `*/30 * * * *` | DB ping, resend stuck runs, purge expired `commute_cache` | — |

A published listing is visible to SQL filters and the map immediately; it joins vector/full-text results once `embed-listing` finishes (seconds). `JOB_DISPATCHER=inline` runs functions synchronously in-process (tests, e2e, seed), same code path.

---

## 10. LLM layer

Copied from Hirevine `apps/api/app/llm/` and renamed:

- `models.py`: ordered model lists from env (OpenRouter falls back down the list):
  - `LLM_STRUCTURED_MODELS=["google/gemma-4-26b-a4b-it","google/gemma-4-31b-it"]` (extract, edit, parse, rerank)
  - `LLM_CHAT_MODELS=["google/gemma-4-26b-a4b-it","google/gemma-4-31b-it"]` (questions, answers, wording)
- Caps: `LLM_DAILY_CAP=300`, `LLM_RPM_CAP=20`, `LLM_SYNC_RPM_CAP=10`. A search turn costs 3 calls (parse, rerank, respond), a listing turn 1–2.
- `call_structured(prompt_id, inputs, schema, deadline)`: cache lookup by hash(prompt version, inputs, model) → budget check → RPM throttle → call → schema validate → 1 retry with the error → next model → Langfuse span with retrieved chunk IDs and scores.
- `prompts/`: one module per prompt (`ID`, `VERSION`, template, schema). `prompts.lock.json` stores a hash per version; `tests/unit/test_prompt_lock.py` fails on change without a bump.
- `fake.py` `FakeModel`: deterministic responses keyed by prompt ID + input fixture, selected with `LLM_PROVIDER=fake` (dev default, tests, e2e, CI).
- Phase 0 smoke test confirms both models are available on OpenRouter and records latency, schema-pass rate and price per 1K calls, as in Hirevine; swap models if they fail.

Prompts: `listing_extract`, `listing_edit`, `listing_question`, `rent_wording`, `search_parse`, `search_clarify`, `rerank`, `search_respond`.

---

## 11. Listing agent (`agents/listing_agent.py`)

LangGraph graph, checkpointed per `chats.thread_id`.

```
route ─▶ extract ────┐
      ─▶ apply_edit ─┼─▶ validate ─▶ ask_missing | preview ─▶ END
      ─▶ locate ─────┘
```

- `route`: code decides by state: empty draft → `extract`; draft exists → `apply_edit`; location event from UI → `locate`.
- `extract`: `listing_extract` → `ListingDraft`; `pipeline/normalise.py` then fixes Indian units and Hinglish in code (`"35k"`, `"1.2L"`, `"2 months deposit"` → months × rent, `"semi"` → semi-furnished).
- `apply_edit`: `listing_edit` → patches → `apply_patches` (same function as the form).
- `locate`: `services/geo.locality_for(point)` (`ST_Contains` on OSM polygons, nearest polygon within 500 m if none); typed locality ≠ polygon locality → `flags.locality_mismatch`, and the agent asks which is right.
- `ask_missing`: first item of `missing_fields`; one question per turn.
- Contact stripping: `redact.strip_contacts()` (Indian mobiles incl. `+91` and spaced digits, emails, URLs, "call/WhatsApp me") runs on the user message before the model sees it and on every description write.
- Stream: `patch` events carry the diff for the live preview.

### 11.1 Rent suggestion (`services/rent_suggestion.py`)

SQL: published listings, same city and bhk, `ST_DWithin(location, :pt, 1500)` widened to 3000 m if < 5 results, furnishing within one step, last 180 days. Code computes p25/p50/p75. If still < 5 comparables, it falls back to `localities.median_rent` (cited as the locality, labelled "locality estimate"). One `rent_wording` call phrases it; `citations.py` checks every number in the wording matches a computed value.

---

## 12. Publish checks (replaces screening)

Screening (scam rules, injection scan, review queue) is **dropped for v1**; listings are assumed legitimate. What remains on publish, all in code, no model:

1. `missing_fields` is empty, photos 3–15.
2. Rent, deposit and maintenance are positive and deposit ≤ 12 × rent (catches unit mistakes like a missing zero).
3. Pin is inside the listing's city.
4. Description has passed `strip_contacts`.

Pass → `published` + `listing/published` event. Fail → `422` with reasons, shown in the chat and the form. Bringing screening back later means adding a `screening` state between `draft` and `published`, which is tracked in the admin-app issue.

---

## 13. Search agent (`agents/search_agent.py`)

```
parse_query ─▶ [clarify] ─▶ search ─▶ [relax] ─▶ enrich ─▶ rerank ─▶ respond
```

| Node | Implementation |
| --- | --- |
| `parse_query` | `search_parse` returns either `SearchFilters` (first turn) or `FilterPatch` (follow-up), plus `semantic_query` and `intent` (`search` / `ask_about_result` / `chitchat`). Code then resolves: locality names → IDs via `pg_trgm`, POI names → IDs, slang map in `domain/filters.py` ("thoda sasta" → rent_max × 0.9, "near metro" → station ≤ 1 km, "family" → tenant_pref family). A map bbox from the request overrides localities |
| `clarify` | if `city` or `rent_max` missing and not asked before in this thread → one question, END. City defaults to `profiles.city` when set |
| `search` (`pipeline/hybrid.py`) | SQL hard filters on `public_listings` → candidate IDs; vector top 50 on `listing_chunks`; `ts_rank` top 50; RRF (`k=60`) in Python → top 50. Listings not yet embedded are appended by SQL order |
| `relax` (`domain/relax.py`) | if < 5 results: budget +10% → adjacent localities (touching polygons) → commute +10 min → drop one soft amenity; one step at a time, stop at ≥ 5; record what changed |
| `enrich` | top 20 in parallel: commute minutes from `services/commute.py`; locality notes = top 3 `locality_chunks` for the result's locality, matched to the user's concerns (metro, schools, hospitals, main roads, parks) |
| `rerank` | `rerank` prompt (listwise, IDs only out) blended with soft-preference weights: `0.6 × rerank + 0.4 × soft_score`; commute filter applied after enrichment |
| `respond` | `search_respond` gets only structured fields and redacted descriptions; output `{text, claims[{text, cites[listing_id|chunk_id], field?}]}`; `citations.py` checks each claim and drops failures; emits `card`, `pins`, `relaxed`, `citations` |

`ask_about_result` ("the 2nd one's commute?") resolves ordinal references against `chats.last_result_ids`, skips search, and answers from enrich data.

### 13.1 Commute (`services/commute.py`)

- `OrsProvider`: OpenRouteService **Matrix API**, one request per search (up to 20 listing origins × 1 POI), profiles `driving-car`, `cycling-regular`, `foot-walking`. Free tier ~500 matrix requests/day and 40/min: verify current limits in phase 3. Key in `ORS_API_KEY`.
- `HaversineProvider`: straight-line km × 1.4 ÷ city speed table (car/two-wheeler/walk, peak hours). Used when `ORS_API_KEY` is unset (dev, tests), when the quota is exhausted (429), or on timeout > 3 s.
- Cache in `commute_cache` by `(geohash7 of origin, poi_id, mode)` for 30 days; each answer reports which provider produced it.
- ORS has no public-transit profile; "by metro" commutes use walk-to-station + haversine on the line, labelled as an estimate.

---

## 14. Reference and seed data

### 14.1 OpenStreetMap (`scripts/fetch_osm.py`, run once, output committed)

- **Localities:** Overpass query per city for `boundary=administrative` (ward / neighbourhood admin levels) and `place=suburb|neighbourhood` polygons. Pick the level that gives roughly 20–40 named areas per city; simplify geometry (Douglas-Peucker ~20 m) → `seed_data/<city>/localities.geojson`. Coverage differs by city; points without polygons get a 1 km buffer.
- **POIs:** `office=*` / `landuse=commercial` tech parks (curated name list per city), `railway=station` + `station=subway` (metro), suburban rail stations (Mumbai, Kolkata), hospitals, colleges.
- **Locality notes (source `osm`):** computed in code per locality and turned into text by template: nearest metro and distance, counts of schools, hospitals, parks and supermarkets within the polygon, main roads crossing it. The numbers are kept in `facts` so citations can be checked.
- **Median rents:** hand-set per locality and bhk in `seed_data/<city>/rents.csv` (no reliable open source); used only for fallback rent suggestions.
- Attribution "© OpenStreetMap contributors" in the map and footer.

### 14.2 Listings (`scripts/seed.py`, no model calls)

1. Reference data from `seed_data/` (cities, localities, POIs, notes).
2. Synthetic landlords: 10 accounts, synthetic tenants: 3 accounts (password logins for dev).
3. Listings generated **in code**: random but plausible fields per locality (bhk distribution, rent around locality median ± 25%, furnishing, tenant preference, amenities), a random pin inside the locality polygon, and a description from varied templates (some Hinglish). Placeholder photos from a small committed set.
4. Each listing is inserted through `apply_patches` + `transition(publish)`, then `embed-listing` runs inline.
5. `--count` (default **50**, spread over the three cities) and `--seed` for repeatable output.

**Count:** 50 is the dev default. Evals and demos use a scratch DB seeded with `--count 600` (still free), because with 50 most localities have no listings, rent suggestions fall back to medians, and retrieval metrics are meaningless.

---

## 15. Testing and evals

### 15.1 Test layers

| Layer | Covers |
| --- | --- |
| unit | redact (phone formats), normaliser, slang map, RRF, relax ladder, citations, rent percentiles, publish checks, state machine, haversine, prompt lock |
| property (`hypothesis`) | any valid patch sequence yields a valid draft; undo restores; filter patches merge consistently |
| api | every router against local Postgres (`scripts/db_local.py`), `FakeModel`, inline jobs |
| rls | the §4.4 matrix, connecting as `rentfit_api` with forged claims |
| e2e | Playwright (frontend plan §10) |

### 15.2 Evals (`evals/`)

| Eval | Dataset | Metric (target) |
| --- | --- | --- |
| Listing extraction | 60 hand-written landlord descriptions with gold fields | field accuracy (≥ 95%) |
| Listing edits by chat | 40 edit requests | same patch as hand edit (≥ 90%) |
| Filter parsing | 150 queries incl. Hinglish + follow-ups | per-field accuracy (≥ 92%) |
| Retrieval | 100 queries with relevant IDs, on the 600-listing scratch DB | nDCG@10, recall@10: vector vs hybrid vs hybrid+rerank |
| Answers | 100 conversations | unsupported-claim rate (≤ 2%), citation validity |
| Latency | `locust` | p50 / p95 per endpoint: fake model in dev, real model after deployment |

Each runner writes `reports/<eval>/<timestamp>_<prompt_version>.json`; `readme_results.py` renders the README table from the latest report per eval.

---

## 16. Deployment

- Vercel project, Root Directory `apps/api`; Inngest app synced on each deploy (CI step).
- One Supabase project: migrations via `supabase db push` in CI on `main`; Edge Function deployed with `supabase functions deploy embed`. Dev and tests use local Postgres + PostGIS + pgvector.
- Env vars: §14 of the product plan, plus `LLM_PROVIDER` (`openrouter`/`fake`), `LLM_STRUCTURED_MODELS`, `LLM_CHAT_MODELS`, `LLM_RPM_CAP`, `JOB_DISPATCHER` (`inngest`/`inline`), `DATABASE_URL_JOBS`, `ORS_API_KEY` (replaces `COMMUTE_PROVIDER`/`COMMUTE_API_KEY`), `PHOTO_BUCKET`.

---

## 17. Build phases

Each phase is done when its exit check passes. No dates. Each phase adds an **As built** note under the relevant section of this file when it closes.

| # | Phase | Backend tasks | Exit check |
| --- | --- | --- | --- |
| 0 | Foundation | `apps/api` skeleton, config, envelope, `/health`; phase-0 migrations, `app` helpers, roles; auth (password + magic link JWTs), `/me`, profile trigger; `fetch_osm.py` + reference seed + `/cities` `/localities` `/pois`; LLM layer (wrapper, cache, budget, fallback, Langfuse, FakeModel, prompt lock, smoke test); Inngest client + dispatcher + `job_runs` + `housekeeping`; Dockerfile; CI (ruff, mypy, pytest, gitleaks, Inngest sync); Vercel deploy | RLS tests show two landlords cannot read each other's rows; `/cities` returns 3 centers and `/localities` returns OSM polygons for each city; a test Inngest function retries a failed step without repeating finished ones; the budget blocks calls at the cap; smoke test records numbers for both models |
| 1 | Landlord | Listing migrations, `ListingDraft`, patches, state machine, publish checks, listing CRUD with `If-Match`, photos (signed upload, 5 MB limit), `PUT /location` + PostGIS lookup, `listing_agent` (extract, ask missing, edit, locate, contact stripping) with SSE, checkpoint tables, rent suggestion | An API test creates a listing from one free-text message plus answers, edits it by chat, and the chat patch equals the form patch for the same change; publish rejects an incomplete listing with reasons; extraction eval ≥ 95% on the first 20 descriptions |
| 2 | Search data | `retrieval` migration, Edge Function `embed`, `HashingEmbedder`, `embed-listing`, OSM locality notes + `embed-locality-notes`, `seed.py` with `--count` | `seed.py --count 50` and `--count 600` both finish with every listing published and embedded, with no model calls |
| 3 | Tenant | Tenant migrations, `SearchFilters` + slang map, `hybrid.py`, `relax.py`, commute service (ORS + haversine) + cache, locality notes retrieval, rerank, `citations.py`, `search_agent` with SSE + ordinal follow-ups, `public_listings` + `/map/listings`, shortlists, saved searches, enquiries + `notify-enquiry` | An API test runs a 4-turn conversation (initial, "cheaper", "the 2nd one's commute?", "near metro instead") with correct filter patches, a reported relaxation, cards, pins and only valid citations; an enquiry reaches the landlord inbox, and no model input contains a phone number or email (asserted on the FakeModel log) |
| 4 | Quality | All eval suites and datasets, `readme_results.py`, latency run (real model, deployed), trace review, RLS review, ADRs in `docs/adr/`, README | README results table is generated from reports; every target is met or the gap is written down with the next step |
| 5 | Marketing | Backend support only if the marketing site needs it (e.g. public city/locality counts) | — |

Phase 3's map endpoint can start once phase 2 seeds listings, in parallel with the search agent.

---

## 18. Open questions and verify list

- Verify OSM boundary coverage per city in phase 0 (which admin level or `place=*` set gives usable localities for Bangalore, Mumbai, Kolkata).
- Verify OpenRouteService free-tier limits and the India road network quality in phase 3.
- Verify `tsvector` `simple` vs `english` config on the Hinglish filter-parsing set.
- Verify the Gemma models' schema-pass rate on `listing_extract` and `search_parse` in the phase 0 smoke test; swap if below 95%.

Tracked as GitHub issues (out of scope for v1): admin/moderation app (incl. bringing back screening), saved-search alerts, WhatsApp bot, Hindi voice input.
