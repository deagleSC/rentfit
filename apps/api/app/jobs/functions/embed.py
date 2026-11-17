"""Embedding jobs (backend plan §9). Events carry IDs only; the text is read from the database.

- embed-listing: on publish, on edits to a published listing, and on pause/let (which removes the
  listing's chunks). A listing is in SQL filters and on the map as soon as it is published; it joins
  vector/full-text results when this finishes.
- embed-locality-notes: when a locality note is written (seed scripts).
"""

from __future__ import annotations

from uuid import UUID

import inngest

from app.core.db import system_claims, transaction
from app.jobs import runs
from app.jobs.client import inngest_client
from app.jobs.functions.common import mark_failed_on_failure, run_id_of
from app.services import retrieval_index


async def index_listing(listing_id: str) -> int:
    async with transaction(system_claims()) as tx:
        return await retrieval_index.index_listing(tx, UUID(listing_id))


async def index_note(note_id: str) -> int:
    async with transaction(system_claims()) as tx:
        return await retrieval_index.index_locality_note(tx, UUID(note_id))


@inngest_client.create_function(
    fn_id="embed-listing",
    trigger=inngest.TriggerEvent(event="listing/changed"),
    concurrency=[inngest.Concurrency(limit=4)],
    retries=3,
    on_failure=mark_failed_on_failure,
)
async def embed_listing(ctx: inngest.Context) -> int:
    run_id = run_id_of(ctx)
    if not await ctx.step.run("mark_running", runs.mark_running, run_id, ctx.run_id):
        return 0
    n = await ctx.step.run("index", index_listing, str(ctx.event.data["entity_id"]))
    await ctx.step.run("mark_done", runs.mark_done, run_id)
    return n


@inngest_client.create_function(
    fn_id="embed-locality-notes",
    trigger=inngest.TriggerEvent(event="locality_notes/changed"),
    concurrency=[inngest.Concurrency(limit=2)],
    retries=3,
    on_failure=mark_failed_on_failure,
)
async def embed_locality_notes(ctx: inngest.Context) -> int:
    run_id = run_id_of(ctx)
    if not await ctx.step.run("mark_running", runs.mark_running, run_id, ctx.run_id):
        return 0
    n = await ctx.step.run("index", index_note, str(ctx.event.data["entity_id"]))
    await ctx.step.run("mark_done", runs.mark_done, run_id)
    return n
