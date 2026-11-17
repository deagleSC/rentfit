# 5. Relaxing a search reports what changed but keeps the tenant's filters

**Status:** accepted (Phase 3, revised after the first browser run)

## Context
With few matches the agent loosens one constraint at a time (budget +10%, nearby areas, commute
+10 min, metro distance, an amenity). The first version saved the loosened filters as the thread's
state. In a browser run, "cheaper" then cut the *relaxed* budget, the next relax raised it again and
added 13 more areas: the search drifted away from what the tenant asked.

## Decision
The thread keeps the tenant's own filters (the chips). Each turn says what it loosened in a notice
and searches with the loosened copy. A field the tenant refined in the same message ("cheaper",
"near metro instead") is never loosened back.

## Consequences
- Chips always match what the tenant said; follow-ups refine their request, not ours.
- Results can include homes outside the chips; the notice says why.
