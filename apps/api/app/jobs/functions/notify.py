"""notify-enquiry (backend plan §9): an in-app notification for the other party of a new message."""

from __future__ import annotations

import inngest

from app.core.db import system_claims, transaction
from app.jobs import runs
from app.jobs.client import inngest_client
from app.jobs.functions.common import mark_failed_on_failure, run_id_of


async def notify(run_id: str) -> bool:
    run = await runs.get(run_id)
    if run is None:
        return False
    async with transaction(system_claims()) as tx:
        row = await tx.fetchone(
            """
            insert into notifications (user_id, kind, entity_id)
            select case when m.sender_id = e.tenant_id then e.landlord_id else e.tenant_id end,
                   'enquiry_message', e.id
            from enquiry_messages m join enquiries e on e.id = m.enquiry_id
            where m.id = %s and e.id = %s
            returning id
            """, (run["params"].get("message_id"), run["entity_id"]))
    return row is not None


@inngest_client.create_function(
    fn_id="notify-enquiry",
    trigger=inngest.TriggerEvent(event="enquiry/message_created"),
    retries=3,
    on_failure=mark_failed_on_failure,
)
async def notify_enquiry(ctx: inngest.Context) -> bool:
    run_id = run_id_of(ctx)
    if not await ctx.step.run("mark_running", runs.mark_running, run_id, ctx.run_id):
        return False
    sent = await ctx.step.run("notify", notify, run_id)
    await ctx.step.run("mark_done", runs.mark_done, run_id)
    return sent
