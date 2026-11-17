"""Enquiries between tenants and landlords (backend plan §7.3), and in-app notifications.

One enquiry per tenant per listing. Message text is contact-stripped: the product shows no phone
numbers or emails in v1. Each new message queues notify-enquiry for the other party.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field

from app.core import ratelimit
from app.core.auth import CurrentUser, PrincipalDep, require_role, user_tx
from app.core.db import Tx
from app.core.errors import ERROR_RESPONSES, AppError, Ok, ok
from app.jobs.runs import JobRefs
from app.pipeline.redact import strip_contacts

router = APIRouter(prefix="/v1", tags=["enquiries"], responses=ERROR_RESPONSES)


class EnquiryStart(BaseModel):
    listing_id: UUID
    message: str = Field(min_length=1, max_length=2000)


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class EnquiryMessage(BaseModel):
    id: int
    mine: bool
    body: str
    created_at: datetime


class EnquirySummary(BaseModel):
    id: UUID
    listing_id: UUID
    listing_title: str
    locality: str
    rent: int
    other_name: str  # the landlord for tenants, the tenant for landlords
    last_message: str
    last_message_at: datetime
    unread: int


class EnquiryThread(BaseModel):
    enquiry: EnquirySummary
    messages: list[EnquiryMessage]


class Notification(BaseModel):
    id: int
    kind: str
    entity_id: UUID
    created_at: datetime
    read: bool


_SUMMARY = """
    select e.id, e.listing_id, coalesce(l.title, l.bhk || ' BHK') as listing_title, loc.name as locality, l.rent,
           case when e.tenant_id = app.current_user_id() then lp.name else tp.name end as other_name,
           (select body from enquiry_messages m where m.enquiry_id = e.id order by m.id desc limit 1) as last_message,
           e.last_message_at,
           (select count(*) from notifications n where n.user_id = app.current_user_id() and n.entity_id = e.id
             and n.read_at is null) as unread
    from enquiries e
    join listings l on l.id = e.listing_id
    join localities loc on loc.id = l.locality_id
    join profiles lp on lp.id = e.landlord_id
    join profiles tp on tp.id = e.tenant_id
"""


async def _summaries(tx: Tx, where: str, args: tuple[Any, ...]) -> list[EnquirySummary]:
    async with tx.as_system():  # joins read the other party's name and the listing (even if paused)
        rows = await tx.fetchall(_SUMMARY.replace("app.current_user_id()", "%(me)s") + f" where {where}"
                                 " order by e.last_message_at desc", args[0] | {"me": args[1]})
    return [EnquirySummary(**dict(r)) for r in rows]


async def _post(tx: Tx, user: CurrentUser, enquiry_id: UUID, body: str) -> None:
    from app.jobs.dispatcher import dispatcher

    text = strip_contacts(body).strip()
    if not text:
        raise AppError(422, "empty_message", "Write a message first. Contact details are removed.")
    await ratelimit.hit(tx, f"enquiry-msg:{user.user_id}", 60, timedelta(hours=1),
                        message="Too many messages. Try again in a while.")
    row = await tx.fetchone("insert into enquiry_messages (enquiry_id, sender_id, body) values (%s, %s, %s)"
                            " returning id", (enquiry_id, user.user_id, text))
    assert row is not None
    async with tx.as_system():
        await tx.conn.execute("update enquiries set last_message_at = now() where id = %s", (enquiry_id,))
    await dispatcher.enqueue(tx, "notify-enquiry", JobRefs(entity="enquiry", entity_id=enquiry_id),
                             {"message_id": row["id"]})


async def _thread(tx: Tx, user: CurrentUser, enquiry_id: UUID) -> EnquiryThread:
    found = await _summaries(tx, "e.id = %(id)s and %(me)s in (e.tenant_id, e.landlord_id)",
                             ({"id": enquiry_id}, user.user_id))
    if not found:
        raise AppError(404, "not_found", "Enquiry not found.")
    rows = await tx.fetchall("select id, sender_id, body, created_at from enquiry_messages where enquiry_id = %s"
                             " order by id", (enquiry_id,))
    async with tx.as_system():
        await tx.conn.execute("update notifications set read_at = now() where user_id = %s and entity_id = %s"
                              " and read_at is null", (user.user_id, enquiry_id))
    return EnquiryThread(enquiry=found[0].model_copy(update={"unread": 0}),
                         messages=[EnquiryMessage(id=r["id"], mine=r["sender_id"] == user.user_id, body=r["body"],
                                                  created_at=r["created_at"]) for r in rows])


@router.post("/tenant/enquiries", response_model=Ok[EnquiryThread], status_code=201)
async def start_enquiry(body: EnquiryStart, principal: PrincipalDep) -> Ok[EnquiryThread]:
    """Open an enquiry on a published listing, or add to the existing one."""
    async with user_tx(principal) as (tx, user):
        require_role(user, "tenant")
        listing = await tx.fetchone("select id, landlord_id from listings where id = %s and status = 'published'",
                                    (body.listing_id,))
        if listing is None:
            raise AppError(404, "not_found", "This home is no longer listed.")
        row = await tx.fetchone(
            "insert into enquiries (listing_id, tenant_id, landlord_id) values (%s, %s, %s)"
            " on conflict (listing_id, tenant_id) do nothing returning id",
            (body.listing_id, user.user_id, listing["landlord_id"]))
        if row is None:
            row = await tx.fetchone("select id from enquiries where listing_id = %s and tenant_id = %s",
                                    (body.listing_id, user.user_id))
        assert row is not None
        await _post(tx, user, row["id"], body.message)
        return ok(await _thread(tx, user, row["id"]))


@router.get("/tenant/enquiries", response_model=Ok[list[EnquirySummary]])
async def tenant_enquiries(principal: PrincipalDep) -> Ok[list[EnquirySummary]]:
    async with user_tx(principal) as (tx, user):
        require_role(user, "tenant")
        return ok(await _summaries(tx, "e.tenant_id = %(me)s", ({}, user.user_id)))


@router.get("/landlord/enquiries", response_model=Ok[list[EnquirySummary]])
async def landlord_enquiries(principal: PrincipalDep) -> Ok[list[EnquirySummary]]:
    async with user_tx(principal) as (tx, user):
        require_role(user, "landlord")
        return ok(await _summaries(tx, "e.landlord_id = %(me)s", ({}, user.user_id)))


@router.get("/enquiries/{enquiry_id}", response_model=Ok[EnquiryThread])
async def get_enquiry(enquiry_id: UUID, principal: PrincipalDep) -> Ok[EnquiryThread]:
    async with user_tx(principal) as (tx, user):
        if user.role is None:
            raise AppError(403, "profile_missing", "Finish creating your account first.")
        return ok(await _thread(tx, user, enquiry_id))


@router.post("/enquiries/{enquiry_id}/messages", response_model=Ok[EnquiryThread], status_code=201)
async def post_message(enquiry_id: UUID, body: MessageIn, principal: PrincipalDep) -> Ok[EnquiryThread]:
    async with user_tx(principal) as (tx, user):
        if user.role is None:
            raise AppError(403, "profile_missing", "Finish creating your account first.")
        if await tx.fetchone("select 1 from enquiries where id = %s", (enquiry_id,)) is None:
            raise AppError(404, "not_found", "Enquiry not found.")
        await _post(tx, user, enquiry_id, body.body)
        return ok(await _thread(tx, user, enquiry_id))


@router.get("/notifications", response_model=Ok[list[Notification]])
async def notifications(principal: PrincipalDep) -> Ok[list[Notification]]:
    async with user_tx(principal) as (tx, _):
        rows = await tx.fetchall("select id, kind, entity_id, created_at, read_at is not null as read"
                                 " from notifications order by id desc limit 50")
        return ok([Notification(**dict(r)) for r in rows])


@router.post("/notifications/read", status_code=204)
async def mark_read(principal: PrincipalDep) -> Response:
    async with user_tx(principal) as (tx, _):
        await tx.conn.execute("update notifications set read_at = now() where read_at is null")
    return Response(status_code=204)
