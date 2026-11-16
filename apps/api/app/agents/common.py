"""Shared plumbing for agents: checkpointer, thread ownership, LLM error mapping."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.core.db import Tx
from app.core.errors import AppError
from app.llm import wrapper
from app.llm.errors import BudgetExhausted, LLMNotConfigured, NeedsReview, RateLimited, TimeBudgetExceeded

# Indirection so tests can swap the model call without touching the graphs.
call_structured: Callable[..., Any] = wrapper.call_structured


@asynccontextmanager
async def checkpointer(tx: Tx) -> AsyncIterator[AsyncPostgresSaver]:
    """A saver bound to the request transaction, in system context (checkpoint tables are
    system-only). Callers check thread ownership in `chats` before using it."""
    async with tx.as_system():
        yield AsyncPostgresSaver(tx.conn)


async def listing_thread(tx: Tx, listing_id: UUID) -> str:
    """The listing's chat thread id, or 404. RLS on `chats` limits rows to the caller."""
    row = await tx.fetchone("select thread_id from chats where kind = 'listing' and listing_id = %s", (listing_id,))
    if row is None:
        raise AppError(404, "thread_not_found", "This conversation does not exist or is not yours.")
    return str(row["thread_id"])


@asynccontextmanager
async def llm_errors() -> AsyncIterator[None]:
    """Model failures as API errors the frontend can show."""
    try:
        yield
    except RateLimited as exc:
        raise AppError(429, "model_busy", "The AI is busy right now. Try again in a minute.",
                       {"retry_after": round(exc.retry_after)}) from exc
    except BudgetExhausted as exc:
        raise AppError(429, "daily_ai_limit", "Today's AI limit is used up. It resets at midnight UTC.") from exc
    except (NeedsReview, TimeBudgetExceeded) as exc:
        raise AppError(502, "agent_failed", "The AI could not understand that. Try rephrasing.") from exc
    except LLMNotConfigured as exc:
        raise AppError(503, "ai_not_configured", "AI features are not configured on this server.") from exc
