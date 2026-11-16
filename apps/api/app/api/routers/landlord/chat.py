"""Listing chat (backend plan §7.2, §11). The reply is composed in code from the applied changes and
the next missing field, so it is returned whole rather than streamed token by token."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.agents import common, listing_agent
from app.core.auth import PrincipalDep, require_role, user_tx
from app.core.errors import ERROR_RESPONSES, AppError, Ok, ok
from app.domain.listing import missing_fields
from app.services import listings as repo

router = APIRouter(prefix="/v1/landlord/listings", tags=["landlord"], responses=ERROR_RESPONSES)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class ChatHistory(BaseModel):
    messages: list[listing_agent.ChatMessage]
    missing: list[str]
    next: str | None
    prompt: str  # what the assistant is waiting for now


@router.get("/{listing_id}/chat", response_model=Ok[ChatHistory])
async def get_chat(listing_id: UUID, principal: PrincipalDep) -> Ok[ChatHistory]:
    async with user_tx(principal) as (tx, user):
        require_role(user, "landlord")
        listing = await repo.get(tx, listing_id)
        thread = await common.listing_thread(tx, listing_id)
        messages = await listing_agent.history(tx, thread)
        field, question = listing_agent.next_step(listing)
        return ok(ChatHistory(messages=messages, missing=missing_fields(listing_agent.as_draft(listing)),
                              next=field, prompt=question))


@router.post("/{listing_id}/chat", response_model=Ok[listing_agent.TurnResult])
async def post_chat(listing_id: UUID, body: ChatRequest, principal: PrincipalDep) -> Ok[listing_agent.TurnResult]:
    async with user_tx(principal) as (tx, user):
        require_role(user, "landlord")
        listing = await repo.get(tx, listing_id)
        if listing.status == "let":
            raise AppError(409, "listing_closed", "This listing is marked as let and can no longer be edited.")
        thread = await common.listing_thread(tx, listing_id)
        async with common.llm_errors():
            result = await listing_agent.run_turn(tx, listing, thread, body.message, user_id=user.user_id)
        return ok(result)
