"""Small stand-ins for listing extraction, search parsing and a chat reply, used by
evals/smoke_test.py to pick the primary model (backend plan §10) and by the LLM-layer tests.
The real prompts arrive in Phases 1 and 3."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.llm.prompts import UNTRUSTED_RULE, Prompt, register, untrusted

# ------------------------------------------------------------------ extract


class ExtractInput(BaseModel):
    description: str


class ExtractOutput(BaseModel):
    bhk: int | None = Field(default=None, ge=1, le=6)
    rent: int | None = Field(default=None, ge=1000, le=1_000_000, description="Monthly rent in INR")
    deposit_months: float | None = Field(default=None, ge=0, le=12)
    furnishing: Literal["unfurnished", "semi", "full"] | None = None
    locality: str | None = None
    pets_allowed: bool | None = None


def _extract_user(data: ExtractInput) -> str:
    return f"Listing description:\n{untrusted(data.description)}"


SMOKE_EXTRACT = register(
    Prompt(
        id="smoke_extract",
        version=1,
        system=(
            "You extract rental listing facts from a landlord's description of a flat in India. "
            "Amounts like '35k' mean 35000 and '1.2L' means 120000. Leave a field empty when the "
            "description does not say it; never guess. " + UNTRUSTED_RULE
        ),
        input=ExtractInput,
        output=ExtractOutput,
        user=_extract_user,
        description="Submit the extracted listing fields.",
        fake=lambda _: {"bhk": 2, "rent": 35000, "deposit_months": 2, "furnishing": "semi",
                        "locality": "Whitefield", "pets_allowed": None},
    )
)

# -------------------------------------------------------------------- parse


class ParseInput(BaseModel):
    query: str


class ParseOutput(BaseModel):
    city: Literal["bangalore", "mumbai"] | None = None
    bhk: list[int] = Field(default_factory=list)
    rent_max: int | None = Field(default=None, ge=1000)
    localities: list[str] = Field(default_factory=list)
    pets: bool | None = None
    no_brokerage: bool | None = None


def _parse_user(data: ParseInput) -> str:
    return f"Tenant query:\n{untrusted(data.query)}"


SMOKE_PARSE = register(
    Prompt(
        id="smoke_parse",
        version=2,
        system=(
            "You turn a tenant's rental search in India (English or Hindi-English mix) into filters. "
            "'Bangalore'/'Bengaluru' is bangalore. Amounts like '35k' mean 35000. Leave a field empty "
            "when the query does not say it. " + UNTRUSTED_RULE
        ),
        input=ParseInput,
        output=ParseOutput,
        user=_parse_user,
        description="Submit the search filters.",
        fake=lambda _: {"city": "bangalore", "bhk": [2], "rent_max": 35000, "localities": ["Whitefield"]},
    )
)

# -------------------------------------------------------------------- reply


class ReplyInput(BaseModel):
    question: str


class ReplyOutput(BaseModel):
    text: str


SMOKE_REPLY = register(
    Prompt(
        id="smoke_reply",
        version=1,
        system="You are a helpful rental assistant. Answer in one or two short sentences.",
        input=ReplyInput,
        output=ReplyOutput,
        user=lambda data: data.question,
        description="Submit the reply text.",
        fake=lambda data: {"text": f"(fake) {data.question}"},
    )
)
