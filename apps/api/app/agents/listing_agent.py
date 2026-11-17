"""Landlord listing agent (backend plan §11): understand → apply → ask. One graph run per chat turn,
checkpointed by the listing's chat thread.

- understand: one model call (`listing_update`) on the landlord's message, contacts already removed.
- apply: code turns the update into patches (deposit months → amount, locality name → id) and applies
  them through `apply_patches`, the same path as form edits, with the listing's version check.
- ask: code picks the first missing field and asks for it from a fixed template (no model call).

The listing row is the source of truth; the checkpoint holds the conversation only.
"""

from __future__ import annotations

import operator
from datetime import date
from typing import Annotated, Any, Literal, TypedDict
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from app.agents import common
from app.core.db import Tx
from app.domain.listing import PHOTOS_MIN, Listing, ListingDraft, missing_fields
from app.domain.listing_patches import AddAmenity, Change, PatchError, RemoveAmenity, SetField, apply_patches
from app.llm import tracing
from app.llm.prompts.listing import ListingUpdate, ListingUpdateInput
from app.llm.wrapper import deadline_in
from app.pipeline.normalise import deposit_from_months, heuristic_extract
from app.pipeline.redact import strip_contacts
from app.services import listings as repo
from app.services import localities

QUESTIONS: dict[str, str] = {
    "city": "Which city is the flat in: Bengaluru or Mumbai?",
    "locality_id": "Which area is it in? For example Koramangala or Andheri West.",
    "location": "Drop a pin on the map so tenants can see exactly where it is.",
    "bhk": "How many bedrooms (BHK) does it have?",
    "rent": "What is the monthly rent?",
    "deposit": "How much is the deposit? You can say it in months, like \"2 months\".",
    "furnishing": "Is it unfurnished, semi-furnished or fully furnished?",
    "tenant_pref": "Who can rent it: families, bachelors, or anyone?",
    "available_from": "From when is it available?",
}
PHOTOS_QUESTION = f"Add at least {PHOTOS_MIN} photos so tenants can see the flat."
READY = "Everything needed is there. Review the preview and publish when you're ready."

def inr(v: int) -> str:
    """Indian digit grouping: 126000 → '1,26,000'."""
    s = str(v)
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    groups: list[str] = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    return ",".join([head, *groups, tail]) if head else ",".join([*groups, tail])


LABELS: dict[str, str] = {
    "bhk": "{} BHK", "rent": "rent ₹{}", "deposit": "deposit ₹{}", "maintenance": "maintenance ₹{}",
    "furnishing": "{}", "sqft": "{} sq ft", "floor": "floor {}", "total_floors": "{} floors",
    "tenant_pref": "{}", "available_from": "available from {}", "city": "in {}",
}
WORDS: dict[str, dict[Any, str]] = {
    "city": {"bangalore": "Bengaluru", "mumbai": "Mumbai"},
    "furnishing": {"unfurnished": "unfurnished", "semi": "semi-furnished", "full": "fully furnished"},
    "tenant_pref": {"any": "open to anyone", "family": "families only", "bachelors": "bachelors only"},
}


def _pretty(field: str, value: Any) -> Any:
    if field in ("rent", "deposit", "maintenance") and isinstance(value, int):
        return inr(value)
    if field == "available_from" and isinstance(value, str):
        d = date.fromisoformat(value)
        return "now" if d <= date.today() else d.strftime("%-d %b %Y")
    return WORDS.get(field, {}).get(value, value)


class ListingChatState(TypedDict, total=False):
    messages: Annotated[list[dict[str, str]], operator.add]
    last_question: str | None


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class TurnResult(BaseModel):
    messages: list[ChatMessage]
    listing: Listing
    changes: list[Change]
    missing: list[str]
    next: str | None  # the field asked about next, "photos", or None when ready


def as_draft(listing: Listing) -> ListingDraft:
    return ListingDraft.model_validate(listing.model_dump(include=set(ListingDraft.model_fields)))


def current_view(listing: Listing) -> dict[str, Any]:
    """What the model sees of the listing: set fields only, nothing private."""
    d = as_draft(listing).model_dump(mode="json", exclude_none=True, exclude={"locality_id", "location"})
    if not d.get("amenities"):
        d.pop("amenities", None)
    return d


MIN_RENT = 3000
# Fields the pattern extractor reads only from explicit cues ("rent 28k", "6 months deposit", "family").
BACKFILL = ("bhk", "rent", "deposit", "deposit_months", "maintenance", "furnishing", "sqft", "tenant_pref")


def backfill(upd: ListingUpdate, message: str) -> ListingUpdate:
    """Fill fields the model left empty from the precise pattern extractor. The small model sometimes
    drops a value it plainly saw (rent, "sirf family"); the patterns never guess, so they only add."""
    if upd.rent is not None and upd.rent < MIN_RENT:  # "set rent to 1": no flat in these cities rents for that
        upd = upd.model_copy(update={"rent": None})
    found = heuristic_extract(message)
    extra = {f: found[f] for f in BACKFILL if f in found and getattr(upd, f) is None}
    if "deposit" in extra and upd.deposit_months is not None or "deposit_months" in extra and upd.deposit is not None:
        extra.pop("deposit", None)
        extra.pop("deposit_months", None)
    return upd.model_copy(update=extra) if extra else upd


async def to_patches(tx: Tx, listing: Listing, upd: ListingUpdate, today: date,
                     message: str = "") -> tuple[list[Any], list[str]]:
    """Model output → patches. Returns (patches, notes for the reply)."""
    upd = backfill(upd, message)
    patches: list[Any] = []
    notes: list[str] = []
    simple = ("bhk", "rent", "maintenance", "furnishing", "sqft", "floor", "total_floors", "tenant_pref", "pets",
              "parking", "gated", "no_brokerage", "title", "description")
    for f in simple:
        v = getattr(upd, f)
        if v is not None:
            patches.append(SetField(field=f, value=v))
    rent = upd.rent if upd.rent is not None else listing.rent
    if upd.deposit is not None:
        patches.append(SetField(field="deposit", value=upd.deposit))
    elif upd.deposit_months is not None:
        if rent is None:
            notes.append("Tell me the rent too, so I can work out the deposit.")
        else:
            patches.append(SetField(field="deposit", value=deposit_from_months(upd.deposit_months, rent)))
    if upd.available_now:
        patches.append(SetField(field="available_from", value=today))
    elif upd.available_from is not None:
        patches.append(SetField(field="available_from", value=upd.available_from))
    city = upd.city or listing.city
    if upd.city and upd.city != listing.city:
        patches.append(SetField(field="city", value=upd.city))
    if upd.locality_name:
        match = await localities.find(tx, upd.locality_name, city)
        if match is None:
            notes.append(f"I couldn't find \"{upd.locality_name}\". Try a nearby area name, or drop a pin.")
        else:
            patches.append(SetField(field="locality_id", value=match.id))
            if match.city != listing.city and not upd.city:
                patches.append(SetField(field="city", value=match.city))
    patches += [AddAmenity(amenity=a) for a in upd.add_amenities]
    patches += [RemoveAmenity(amenity=a) for a in upd.remove_amenities]
    patches += [SetField(field=f, value=None) for f in upd.clear if mentions(message, f)]
    return patches, notes


# A model may over-reach with `clear`; only clear a field the message actually names.
CLEAR_WORDS: dict[str, tuple[str, ...]] = {
    "maintenance": ("maintenance",), "sqft": ("sqft", "sq ft", "area", "size"), "floor": ("floor",),
    "total_floors": ("floors", "storey"), "pets": ("pet",), "parking": ("parking",), "gated": ("gated",),
    "no_brokerage": ("brokerage", "broker"), "title": ("title",), "description": ("description",),
}


def mentions(message: str, field: str) -> bool:
    m = message.lower()
    return any(w in m for w in CLEAR_WORDS.get(field, (field,)))


def describe(changes: list[Change], locality_name: str | None) -> str:
    parts: list[str] = []
    for c in changes:
        if c.field == "locality_id":
            if locality_name:
                parts.append(f"in {locality_name}")
        elif c.field in LABELS and c.after is not None:
            parts.append(LABELS[c.field].format(_pretty(c.field, c.after)))
        elif c.field == "amenities":
            parts.append("amenities updated")
        elif c.field == "description":
            parts.append("description updated")
        elif c.after is None:
            parts.append(f"{c.field.replace('_', ' ')} removed")
        elif isinstance(c.after, bool):
            parts.append(f"{c.field.replace('_', ' ')}: {'yes' if c.after else 'no'}")
        else:
            parts.append(f"{c.field.replace('_', ' ')}: {c.after}")
    return ", ".join(parts)


def next_step(listing: Listing) -> tuple[str | None, str]:
    missing = missing_fields(as_draft(listing))
    if missing:
        return missing[0], QUESTIONS[missing[0]]
    if listing.photo_count < PHOTOS_MIN:
        return "photos", PHOTOS_QUESTION
    return None, READY


# --------------------------------------------------------------------- graph


async def understand_apply_ask(state: ListingChatState, config: RunnableConfig) -> ListingChatState:
    ctx: dict[str, Any] = (config.get("configurable") or {})["turn"]  # shared holder; LangGraph may copy the config
    tx: Tx = ctx["tx"]
    listing: Listing = ctx["listing"]
    message: str = state["messages"][-1]["content"]
    today = date.today()

    res = await common.call_structured(
        "structured", "listing_update",
        ListingUpdateInput(message=message, current=current_view(listing), today=today,
                           last_question=state.get("last_question")),
        deadline=deadline_in(45), sync=True,
    )
    upd: ListingUpdate = res.value
    patches, notes = await to_patches(tx, listing, upd, today, message)

    changes: list[Change] = []
    if patches:
        try:
            draft, changes = apply_patches(as_draft(listing), patches)
        except PatchError as exc:
            notes.append("Some of that didn't add up (" + "; ".join(d["msg"] for d in exc.details[:2]) + ").")
        else:
            if changes:
                listing = await repo.save_draft(tx, listing, draft, listing.version)
    ctx["listing"], ctx["changes"] = listing, changes

    field, question = next_step(listing)
    ctx["next"] = field
    said = describe(changes, await _locality_name(tx, listing) if any(c.field == "locality_id" for c in changes)
                    else None)
    lead = f"Got it: {said}." if said else ("" if notes else "I didn't catch any listing details there.")
    reply = " ".join(p for p in [lead, *notes, question] if p)
    return {"messages": [{"role": "assistant", "content": reply}], "last_question": question}


async def _locality_name(tx: Tx, listing: Listing) -> str | None:
    if listing.locality_id is None:
        return None
    row = await tx.fetchone("select name from localities where id = %s", (listing.locality_id,))
    return str(row["name"]) if row else None


def build_graph() -> StateGraph[ListingChatState]:
    g = StateGraph(ListingChatState)
    g.add_node("turn", understand_apply_ask)
    g.add_edge(START, "turn")
    g.add_edge("turn", END)
    return g


GRAPH = build_graph()


async def run_turn(tx: Tx, listing: Listing, thread_id: str, message: str, *, user_id: UUID) -> TurnResult:
    clean = strip_contacts(message)[:2000]
    ctx: dict[str, Any] = {"tx": tx, "listing": listing}
    async with common.checkpointer(tx) as saver:
        graph = GRAPH.compile(checkpointer=saver)
        config: Any = {"configurable": {"thread_id": thread_id, "turn": ctx}}
        with tracing.trace("chat-listing", input=clean, user_id=str(user_id), session_id=thread_id,
                           tags=["listing"]) as t:
            # Checkpoints share the request connection with the node's queries: write them synchronously.
            state = await graph.ainvoke({"messages": [{"role": "user", "content": clean}]}, config, durability="sync")
            t.update(output=state["messages"][-1]["content"])
    final: Listing = ctx["listing"]
    return TurnResult(
        messages=[ChatMessage.model_validate(m) for m in state["messages"]],
        listing=final, changes=ctx.get("changes", []),
        missing=missing_fields(as_draft(final)), next=ctx.get("next"),
    )


async def history(tx: Tx, thread_id: str) -> list[ChatMessage]:
    async with common.checkpointer(tx) as saver:
        snap = await GRAPH.compile(checkpointer=saver).aget_state({"configurable": {"thread_id": thread_id}})
    return [ChatMessage.model_validate(m) for m in (snap.values or {}).get("messages", [])]
