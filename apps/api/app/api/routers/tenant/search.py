"""Tenant search chat (backend plan §7.3, §13). POST streams Server-Sent Events:

    filters   {filters, chips, changes}     the thread's filters after this message
    question  {text}                        clarifying question; the turn ends
    relaxed   {steps, count}                what was loosened to find enough homes
    pins      {pins}                        map pins for up to 20 results
    cards     {cards}                       listing cards (up to 8)
    token     {text}                        the reply's intro
    citations {claims: [{text, refs}]}      checked claims with their sources
    done      {chat_id}                     after the turn is saved
    error     {code, message}

Role and thread checks run before the stream opens, so they fail as normal JSON errors.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from app.agents import common, search_agent
from app.core import ratelimit
from app.core.auth import Principal, PrincipalDep, require_role, user_tx
from app.core.db import Tx
from app.core.errors import ERROR_RESPONSES, AppError, Ok, ok
from app.domain.filters import CLEARABLE, Bbox, SearchFilters, chips
from app.services import search_results as res

router = APIRouter(prefix="/v1/tenant", tags=["tenant"], responses=ERROR_RESPONSES)


class SearchChatRequest(BaseModel):
    chat_id: UUID | None = None
    message: str = Field(default="", max_length=1000)
    bbox: Bbox | None = Field(default=None, description="Search this map area (west, south, east, north)")
    remove_filters: list[str] | None = Field(default=None, description="Chips removed; no message needed")
    filters: SearchFilters | None = Field(default=None, description="Start a new chat from saved filters")


class ChatSummary(BaseModel):
    id: UUID
    title: str
    chips: list[dict[str, str]]
    updated_at: datetime


class ChatMessageOut(BaseModel):
    role: str
    content: str
    claims: list[dict[str, Any]] = Field(default_factory=list)
    card_ids: list[UUID] = Field(default_factory=list)
    relaxed: list[str] = Field(default_factory=list)


class ChatDetail(BaseModel):
    id: UUID
    filters: SearchFilters
    chips: list[dict[str, str]]
    messages: list[ChatMessageOut]
    cards: list[res.ListingCard]
    pins: list[res.Pin]


async def _chat(tx: Tx, chat_id: UUID) -> dict[str, Any]:
    row = await tx.fetchone("select id, thread_id, last_filters, last_result_ids, created_at from chats"
                            " where id = %s and kind = 'search'", (chat_id,))
    if row is None:
        raise AppError(404, "thread_not_found", "This conversation does not exist or is not yours.")
    return dict(row)


def _sse(event: str, data: dict[str, Any]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n".encode()


@router.post("/search/chat", responses={200: {"content": {"text/event-stream": {}}}})
async def search_chat(body: SearchChatRequest, principal: PrincipalDep) -> StreamingResponse:
    if not body.message.strip() and body.remove_filters is None and body.filters is None and body.bbox is None:
        raise AppError(422, "empty_message", "Type what you're looking for.")
    if body.remove_filters and any(f not in CLEARABLE for f in body.remove_filters):
        raise AppError(422, "unknown_filter", "That filter can't be removed.")
    async with user_tx(principal) as (tx, user):  # fail fast, before the stream starts
        require_role(user, "tenant")
        if body.chat_id:
            await _chat(tx, body.chat_id)
    return StreamingResponse(_stream(body, principal), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


async def _stream(body: SearchChatRequest, principal: Principal) -> AsyncIterator[bytes]:
    queue: asyncio.Queue[bytes | None] = asyncio.Queue()

    async def emit(event: str, data: dict[str, Any]) -> None:
        await queue.put(_sse(event, data))

    async def work() -> None:
        try:
            chat_id: UUID | None = None
            async with common.llm_errors(), user_tx(principal) as (tx, user):
                await ratelimit.hit(tx, f"search-chat:{user.user_id}", 120, timedelta(hours=1),
                                    message="Too many searches. Try again in a while.")
                if body.chat_id:
                    chat = await _chat(tx, body.chat_id)
                else:
                    row = await tx.fetchone(
                        "insert into chats (owner_id, kind, thread_id, last_filters) values"
                        " (%s, 'search', 'search:' || gen_random_uuid(), %s) returning id",
                        (user.user_id, Jsonb(body.filters.model_dump(mode="json")) if body.filters else None))
                    assert row is not None
                    chat = await _chat(tx, row["id"])
                chat_id = chat["id"]
                remove = body.remove_filters
                if remove is None and (body.filters is not None or (body.bbox and not body.message.strip())):
                    remove = []
                await search_agent.run_turn(tx, chat, body.message, emit, user_id=user.user_id, bbox=body.bbox,
                                            remove=remove)
            await emit("done", {"chat_id": str(chat_id)})
        except AppError as exc:
            await emit("error", {"code": exc.code, "message": exc.message})
        except Exception:
            search_agent.log.exception("search chat failed")
            await emit("error", {"code": "internal", "message": "Something went wrong. Try again."})
        finally:
            await queue.put(None)

    task = asyncio.create_task(work())
    try:
        while (item := await queue.get()) is not None:
            yield item
    finally:
        await task


@router.get("/chats", response_model=Ok[list[ChatSummary]])
async def list_chats(principal: PrincipalDep) -> Ok[list[ChatSummary]]:
    async with user_tx(principal) as (tx, user):
        require_role(user, "tenant")
        rows = await tx.fetchall("select id, thread_id, last_filters, updated_at from chats where kind = 'search'"
                                 " order by updated_at desc limit 50")
        out = []
        for r in rows:
            f = SearchFilters.model_validate(r["last_filters"] or {})
            labels = chips(f)
            title = ", ".join(c["label"] for c in labels[:3]) or "New search"
            out.append(ChatSummary(id=r["id"], title=title, chips=labels, updated_at=r["updated_at"]))
        return ok(out)


@router.get("/chats/{chat_id}", response_model=Ok[ChatDetail])
async def get_chat(chat_id: UUID, principal: PrincipalDep) -> Ok[ChatDetail]:
    async with user_tx(principal) as (tx, user):
        require_role(user, "tenant")
        chat = await _chat(tx, chat_id)
        f = SearchFilters.model_validate(chat["last_filters"] or {})
        raw = await search_agent.history(tx, chat["thread_id"])
        messages = [ChatMessageOut(role=m["role"], content=m.get("content", ""), claims=m.get("claims", []),
                                   card_ids=m.get("card_ids", []), relaxed=m.get("relaxed", [])) for m in raw]
        ids = list(dict.fromkeys(i for m in messages for i in m.card_ids))
        com = await res.commutes(tx, f, ids)
        return ok(ChatDetail(id=chat["id"], filters=f, chips=chips(f), messages=messages,
                             cards=await res.cards(tx, ids, com),
                             pins=await res.pins(tx, list(chat["last_result_ids"] or []))))
