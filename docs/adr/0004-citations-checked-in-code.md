# 4. Answers are claims with citations, checked in code

**Status:** accepted (Phase 3)

## Context
A search reply must not invent prices, distances or amenities.

## Decision
`search_respond` returns an intro plus claims, each citing listing refs (`L1..`) or locality-note
refs (`N1..`). `pipeline/citations.py` drops a claim if it cites an unknown ref, or if any number in
it is not present in the items it cites (`35k`, `₹35,000` and `35000` are the same number). The UI
shows each kept claim with numbered source chips that open the listing or the OSM note.

## Consequences
- A wrong number never reaches the tenant; the dropped rate is an eval metric.
- The check is about numbers and refs, not meaning: a claim like "great for families" passes if it
  cites a listing. The answers eval reports how often claims are dropped.
- The reply is structured, so it is sent whole rather than token by token.
