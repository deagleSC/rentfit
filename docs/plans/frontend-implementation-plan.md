# RentFit v2: Frontend Implementation Plan

This plan covers the three Next.js apps (landlord, tenant, marketing) and the shared packages. It uses the API in [backend-implementation-plan.md §7](./backend-implementation-plan.md#7-api-surface) and turns [PLAN.md](../../PLAN.md) §4 and §8 into pages and components. Libraries the product plan does not name are marked **(chosen here)**.

---

## 1. Scope and principles

| Principle | What it means in the frontend |
| --- | --- |
| API only | Apps never query Supabase tables. The Supabase client is used for auth and signed photo uploads only |
| Chat and forms are equal | Every chat edit shows as a diff on the same preview the form edits; both send `list[Patch]` |
| Citations are visible | Every AI claim renders a `CitationChip` linking to the listing card or locality note |
| Map and chat stay in sync | One store owns results; chat cards and map pins read from it; hovering one highlights the other |
| No contact details anywhere | Enquiries are in-app messages only; phone/email are never shown |

---

## 2. Stack

| Concern | Choice |
| --- | --- |
| Framework | Next.js 15 App Router, React 19, TypeScript strict |
| Styling | Tailwind 4, tokens in `packages/ui`, `next-themes` |
| Data | React Query; SSE via `fetch` + `ReadableStream` parser in `packages/api-client` (chosen here) |
| Forms | react-hook-form + zod (zod schemas mirror `ListingDraft`, `SearchFilters`, `Patch`) |
| Map | MapLibre GL, ported from `rentfit-v1-web/src/components/ui/map.tsx` and `search-map-panel.tsx` |
| Client state | zustand for the search session store (chosen here) |
| Toasts | sonner |
| Tests | Vitest + Testing Library, Playwright + `@axe-core/playwright` |

---

## 3. Repository layout

```
apps/
  landlord/  app/(auth)/, app/listings/, app/listings/[id]/, app/enquiries/
  tenant/    app/(auth)/, app/search/, app/listings/[id]/, app/shortlist/, app/saved/, app/enquiries/
  marketing/ app/, app/landlords/, app/tenants/, app/legal/
packages/
  ui/
    tokens/, layout/, primitives/
    chat/        ChatThread, Composer, StreamingMessage, QuestionBubble, DiffCard
    evidence/    CitationChip, CitationPopover, RelaxedNotice
    listing/     ListingCard, ListingPreview, PhotoGrid, StatusBadge
    map/         MapProvider, Map, Markers, Clusters, Popup, PinPicker, SearchMapPanel, useMapBounds
    charts/      RentRangeBar
  api-client/   generated types + fetch wrapper + sse.ts
  config/       eslint, tsconfig
```

---

## 4. Auth and role routing

Same as Hirevine: Supabase Auth with email + password and magic link. Signup sets `role` in user metadata. Login is required for every page in both apps (no anonymous search). Middleware: landlord app requires `role=landlord`, tenant app requires `role=tenant`; a user with the wrong role is redirected to the other app with a notice. Bearer token passed to the API from the session.

## 5. API client (`packages/api-client`)

- Types generated from `/openapi.json` (`openapi-typescript`), checked in CI for drift.
- `api.get/post/patch` unwrap the envelope, throw `ApiError(code)`.
- `streamChat(url, body, handlers)` dispatches SSE events: `token`, `card`, `pins`, `patch`, `question`, `relaxed`, `citations`, `done`, `error`.
- `useJobRun(id)` polls `/job-runs/{id}` every 2 s until terminal.

---

## 6. Shared map package (`packages/ui/map`)

Port, then adapt:

1. Copy `map.tsx` (context, markers, popups, clusters) and `search-map-panel.tsx` from rentfit-v1-web; strip v1 data types and API calls.
2. Style URL from `NEXT_PUBLIC_MAP_STYLE_URL` (OpenFreeMap, e.g. `https://tiles.openfreemap.org/styles/liberty`); "© OpenStreetMap contributors" attribution; city centers from `/cities`.
3. Add `PinPicker` (draggable marker, returns `{lat,lng}`) for landlords.
4. Add `useMapBounds` (debounced 400 ms) → `bbox` for the "search this area" toggle.
5. Clusters with GeoJSON source; pin colour by rent band; selected/hover state from the search store.
6. Locality polygon overlay layer (optional, toggled) from `/localities?city=`.

`dynamic(() => import(...), { ssr: false })` for every map usage.

---

## 7. Landlord app (`apps/landlord`, :3000)

### 7.1 Listings `/listings`
Table: title, status badge, rent, views, enquiries, updated; actions pause/resume/let. "New listing" → `POST /listings` → redirect to chat.

### 7.2 Listing chat `/listings/[id]`
Three-pane on desktop (chat | preview | map+photos), tabs on mobile.
- Chat streams agent turns; `patch` events animate fields in `ListingPreview` and show a `DiffCard` with undo.
- Missing-field checklist drawn from the draft; `question` events highlight the field.
- Photos: drag-drop, 3–15 photos, JPEG/PNG/WebP/HEIC, **reject files over 5 MB** before upload; convert in the browser (HEIC via `heic2any`, chosen here) to WebP 1600 px + 480 px thumbnail, upload both to signed URLs, reorder, min-3 indicator.
- Map: `PinPicker`; on drop → `PUT /location`; locality mismatch shows a choice dialog.
- Rent suggestion card: `RentRangeBar` (p25–p75, landlord's rent marked) + cited comparables as mini cards.
- Edit form toggle: same preview becomes a form; save diffs form → patches (`diffFormToPatches`), `If-Match` version, 409 → conflict dialog.
- Publish → `POST /publish` → published, or a list of failed checks linked to their fields.

### 7.3 Enquiries `/enquiries`
Inbox list + thread; reply; listing context in header. No contact details are shown.

---

## 8. Tenant app (`apps/tenant`, :3001)

### 8.1 Search `/search` and `/search/[chatId]`
Split view: chat (40%) | map (60%); mobile: chat with a bottom-sheet map.
- Composer with example prompts (incl. Hinglish).
- Stream: text, `ListingCard`s inline, `pins` update the map, `RelaxedNotice` ("I raised your budget to ₹38.5k to find 5 more"), citation chips.
- Active filters shown as removable chips above the chat; removing one sends a filter patch.
- "Search this area" toggle sends the map bbox with the next message.
- Card ↔ pin hover sync; clicking a pin scrolls to its card.

### 8.2 Listing detail `/listings/[id]`
Photos, facts, map with nearby POIs, commute to the tenant's chosen POI, locality notes with sources, shortlist and "Send enquiry".

### 8.3 Shortlist, saved searches, enquiries
Shortlist grid with compare (rent, deposit, commute). Saved searches list (filters as chips, open → new search chat; no alerts in v1). Enquiries thread view.

---

## 9. Marketing app (`apps/marketing`, :3002)
Static pages: landing, for landlords, for tenants, privacy/terms. Links to the two apps via `NEXT_PUBLIC_*_APP_URL`. Can reuse copy from v1's `rentfit-marketing-website`.

---

**As built (Phase 5):** static Next.js site (`apps/marketing`, :3002) with landing, tenants, landlords, privacy and terms pages, and a fourth Vercel project. The copy was written fresh for v2 rather than reused from v1, and claims only what ships: two cities, sample listings, no listing verification, contacts removed from messages. The product picture is an HTML mock of a real search exchange, not screenshots. Every page passes axe; the theme's `--primary` was darkened slightly for 4.5:1 text contrast.

---

## 10. Testing

| Layer | Covers |
| --- | --- |
| Vitest | SSE parser, `diffFormToPatches`, search store reducers, filter chip ↔ patch mapping, map bounds hook, photo size check + resize |
| Playwright e2e (fake model, inline jobs) | `landlord-listing.spec`: chat → photos → pin → publish. `tenant-search.spec`: 3-turn search, pins match cards, citation popover. `enquiry.spec`: tenant enquires, landlord replies. `full-flow.spec`: the product plan §11 end-to-end |
| axe | every page in both apps, fail on serious/critical |
| Bundle budget | `scripts/check-bundle.mjs`: tenant `/search` ≤ 350 kB first-load JS (map lazy), landlord ≤ 400 kB |

---

## 11. Deployment
Three Vercel projects (Root Directory per app). `NEXT_PUBLIC_*` are build-time; changing them needs a redeploy (same as v1). Preview deployments point at a staging API.

---

## 12. Build phases

| # | Phase | Frontend tasks | Exit check |
| --- | --- | --- | --- |
| 0 | Foundation | Monorepo, `packages/config`, `packages/ui` tokens/layout/primitives, **map port** (steps 1–2 of §6), `api-client` generation, auth + role middleware in both apps, `/me`, three Vercel projects, CI (eslint, tsc, vitest) | Both apps log in; a landlord in the tenant app is redirected; the map renders the three city centers from `/cities` |
| 1 | Landlord | Listings table, listing chat page with streaming, `ListingPreview` + `DiffCard` + undo, form mode + conflict dialog, photo upload, `PinPicker`, rent suggestion card | A landlord creates and edits a listing entirely by chat in the browser; Playwright `landlord-listing.spec` up to submit is green |
| 2 | Search data | Status transitions in the listings table (pause/resume/let); seeded listings visible on the map | The 50 seeded listings appear as pins in the right cities |
| 3 | Tenant | Search split view, search store, cards ↔ pins sync, filter chips, `RelaxedNotice`, citations, bbox search, clusters, listing detail, shortlist, saved searches, enquiries in both apps | `tenant-search.spec` and `enquiry.spec` green; every citation chip opens its source |
| 4 | Quality | `full-flow.spec`, axe pass on all pages, bundle budgets, empty/error state audit, Sentry, README screenshots from e2e | e2e green in CI; axe clean; budgets enforced |
| 5 | Marketing | Marketing site: landing, for landlords, for tenants, privacy/terms (copy can reuse v1's marketing site) | Deployed and linking to both apps |

---

## 13. Open items
- Check OpenFreeMap label quality in the three cities in phase 0.
- Out of scope, tracked as GitHub issues: admin app, saved-search alerts, WhatsApp bot, Hindi voice input.
