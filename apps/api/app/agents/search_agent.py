"""Tenant search agent (backend plan §13). One graph run per chat turn, checkpointed by thread:

    parse_query ─▶ [clarify] ─▶ search ─▶ [relax] ─▶ enrich ─▶ rank ─▶ respond

Two model calls per searching turn (parse, respond); everything else is code. The thread's filters
and last result IDs live on the `chats` row, so follow-ups patch the last search and "the 2nd one"
resolves against what was shown. Events are pushed to `emit` as they are ready (SSE in the router).
"""

from __future__ import annotations

import logging
import operator
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from typing import Annotated, Any, TypedDict
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from psycopg.types.json import Jsonb

from app.agents import common
from app.core.db import Tx
from app.domain import relax as relax_mod
from app.domain.filters import Commute, FilterChange, SearchFilters, SearchUpdate, apply_slang, chips, merge
from app.llm import tracing
from app.llm.prompts.search import NoteFacts, RespondInput, RespondOutput, ResultFacts, SearchParseInput
from app.llm.wrapper import deadline_in
from app.pipeline import citations, hybrid
from app.pipeline.redact import strip_contacts
from app.services import localities
from app.services import search_results as res
from app.services.embeddings import get_embedder

log = logging.getLogger("rentfit.search")
_REF_TOKEN = re.compile(r"\s*[(\[]\s*[LN]\d+(?:\s*,\s*[LN]\d+)*\s*[)\]]|\b[LN]\d+\b:?\s*")  # "(L1)", "[L1, N2]", "L1:"

Emit = Callable[[str, dict[str, Any]], Awaitable[None]]
RESULTS_KEPT = 20  # ids remembered for ordinals and pins
CARDS = 8
FOR_MODEL = 5
DEFAULT_COMMUTE_MIN = 45
FURN = {"unfurnished": "unfurnished", "semi": "semi-furnished", "full": "fully furnished"}
TENANTS = {"any": "families or bachelors", "family": "families", "bachelors": "bachelors"}


class SearchChatState(TypedDict, total=False):
    messages: Annotated[list[dict[str, Any]], operator.add]
    asked: list[str]
    last_question: str | None


# ------------------------------------------------------------------ helpers


async def adjacent(tx: Tx, ids: list[UUID]) -> list[tuple[UUID, str]]:
    rows = await tx.fetchall(
        """
        select distinct b.id, b.name from localities a join localities b
          on b.city = a.city and b.id <> a.id and st_dwithin(a.boundary, b.boundary, 150)
        where a.id = any(%s) order by b.name
        """, (ids,))
    return [(r["id"], r["name"]) for r in rows]


def _metro_text(card: res.ListingCard) -> str | None:
    if not card.metro:
        return None
    d = card.metro.metres
    return f"{card.metro.name} metro, {d} m" if d < 1000 else f"{card.metro.name} metro, {d / 1000:.1f} km"


def _commute_text(c: res.CommuteInfo | None) -> str | None:
    if c is None:
        return None
    mode = {"car": "by car", "two_wheeler": "by two-wheeler", "walk": "on foot"}[c.mode]
    return f"{c.minutes} min {mode} to {c.to}" + (" (estimate)" if c.provider == "haversine" else "")


def facts(ref: str, card: res.ListingCard, description: str) -> ResultFacts:
    return ResultFacts(
        ref=ref, locality=card.locality, bhk=card.bhk, rent=card.rent, deposit=card.deposit,
        furnishing=FURN.get(card.furnishing, card.furnishing), tenant_pref=TENANTS.get(card.tenant_pref, ""),
        available_from=card.available_from.isoformat() if card.available_from else None,
        amenities=[a.replace("_", " ") for a in card.amenities], commute=_commute_text(card.commute),
        metro=_metro_text(card), description=strip_contacts(description or "")[:300],
    )


async def respond(tx: Tx, emit: Emit, request: str, f: SearchFilters, relaxed: list[str], total: int,
                  shown: list[res.ListingCard], descriptions: dict[UUID, str], question: str | None = None
                  ) -> dict[str, Any]:
    """The answer: model reply checked against its sources. Returns the stored assistant message."""
    top = shown[:FOR_MODEL]
    refs = {f"L{n}": c for n, c in enumerate(top, 1)}
    results = [facts(r, c, descriptions.get(c.id, "")) for r, c in refs.items()]
    notes_rows: list[dict[str, Any]] = []
    if top:
        notes_rows = await _notes_for(tx, top)
    notes = [NoteFacts(ref=f"N{n}", locality=r["locality"], text=r["content"]) for n, r in enumerate(notes_rows, 1)]
    out: RespondOutput = (await common.call_structured(
        "chat", "search_respond",
        RespondInput(request=request, filters=[c["label"] for c in chips(f)], relaxed=relaxed, total=total,
                     results=results, notes=notes, question=question),
        deadline=deadline_in(40), sync=True,
    )).value
    sources: dict[str, Any] = {r.ref: r.model_dump() for r in results} | {n.ref: n.model_dump() for n in notes}
    checked = citations.check(out.claims, sources)
    for claim, why in checked.dropped:
        log.info("dropped claim (%s): %s", why, claim.text[:200])
    ref_ids: dict[str, dict[str, str]] = {r: {"kind": "listing", "id": str(c.id), "label": f"{c.bhk} BHK, {c.locality}"}
                                          for r, c in refs.items()}
    for n, row in zip(notes, notes_rows, strict=True):
        ref_ids[n.ref] = {"kind": "note", "id": str(row["id"]), "label": f"About {row['locality']}",
                          "text": row["content"]}
    claims = [{"text": _REF_TOKEN.sub("", c.text).strip(), "refs": [ref_ids[r] for r in c.cites]}
              for c in checked.kept]
    await emit("token", {"text": out.intro})
    await emit("citations", {"claims": claims})
    return {"intro": out.intro, "claims": claims}


async def _notes_for(tx: Tx, cards: list[res.ListingCard]) -> list[dict[str, Any]]:
    rows = await tx.fetchall("select id, locality_id from public_listings where id = any(%s)", ([c.id for c in cards],))
    by = {r["id"]: r["locality_id"] for r in rows}
    return (await res.locality_notes(tx, [by[c.id] for c in cards if c.id in by]))[:3]


async def resolve_names(tx: Tx, upd: SearchUpdate, prev: SearchFilters
                        ) -> tuple[SearchUpdate, list[tuple[UUID, str]], Commute | None, list[str]]:
    """Area and place names → IDs. A matched area also sets the city when none is known yet."""
    upd = upd.model_copy(deep=True)
    city = upd.city or prev.city
    notes: list[str] = []
    found: list[tuple[UUID, str]] = []
    for name in upd.locality_names[:5]:
        m = await localities.find(tx, name, city)
        if m is None:
            notes.append(f"I couldn't find an area called \"{name}\".")
        else:
            found.append((m.id, m.name))
            city = city or m.city
            if upd.city is None and prev.city is None:
                upd.city = m.city  # type: ignore[assignment]
    commute: Commute | None = None
    if upd.commute_to:
        poi = await res.find_poi(tx, upd.commute_to, city)
        if poi is None:
            notes.append(f"I couldn't find \"{upd.commute_to}\" on the map, so I left out the commute.")
        else:
            commute = Commute(poi_id=poi["id"], poi_name=poi["name"],
                              max_minutes=upd.commute_minutes or DEFAULT_COMMUTE_MIN, mode=upd.commute_mode or "car")
            if upd.city is None and prev.city is None:
                upd.city = poi["city"]
    return upd, found, commute, notes


@dataclass
class Found:
    hits: list[hybrid.Hit]
    commutes: dict[UUID, res.CommuteInfo]
    searched: SearchFilters  # what produced the results (the tenant's filters, maybe loosened)
    relaxed: list[str]
    ranked: list[UUID]


async def find(tx: Tx, f: SearchFilters, changes: list[FilterChange]) -> Found:
    """Hybrid search with the commute filter, the relax ladder and soft-preference ranking."""
    embedder = get_embedder()
    vectors: dict[str, list[float]] = {}  # one embedding call per turn, however many relax steps run

    async def run(fl: SearchFilters) -> tuple[list[hybrid.Hit], dict[UUID, res.CommuteInfo]]:
        hits = await hybrid.search(tx, fl, embedder, vectors=vectors)
        com = await res.commutes(tx, fl, [h.id for h in hits])
        if fl.commute:
            hits = [h for h in hits if h.id in com and com[h.id].minutes <= fl.commute.max_minutes]
        return hits, com

    hits, com = await run(f)
    relaxed: list[str] = []
    searched = f  # the thread keeps the tenant's own filters
    if len(hits) < relax_mod.MIN_RESULTS:
        near = await adjacent(tx, f.locality_ids) if f.locality_ids else []
        # A refinement in this message ("cheaper", "near metro instead") is never undone by relaxing.
        refined = {c.field for c in changes if c.before not in (None, [], {})}
        for loosened, step in relax_mod.steps(f, lambda _ids: near, skip=refined):
            more, more_com = await run(loosened)
            relaxed.append(step.message)
            if len(more) > len(hits):
                hits, com, searched = more, more_com, loosened
            if len(hits) >= relax_mod.MIN_RESULTS:
                break
    ids = [h.id for h in hits]
    soft = await res.soft_scores(tx, searched.soft, ids)
    score = {h.id: (0.6 * h.score + 0.4 * soft.get(h.id, 0.0)) if searched.soft else h.score for h in hits}
    ranked = sorted(ids, key=lambda i: -score[i])[:RESULTS_KEPT]
    return Found(hits, com, searched, relaxed, ranked)


# ------------------------------------------------------------------ the turn


async def turn(state: SearchChatState, config: RunnableConfig) -> SearchChatState:
    ctx: dict[str, Any] = (config.get("configurable") or {})["turn"]
    tx: Tx = ctx["tx"]
    emit: Emit = ctx["emit"]
    chat: dict[str, Any] = ctx["chat"]
    message: str = state["messages"][-1]["content"]
    prev = SearchFilters.model_validate(chat["last_filters"] or {})
    last_ids: list[UUID] = list(chat["last_result_ids"] or [])
    asked: list[str] = list(state.get("asked") or [])

    if ctx.get("remove") is not None:  # a chip removed, a saved search reopened, or "search this area"
        upd = SearchUpdate(clear=ctx["remove"])
    else:
        upd = (await common.call_structured(
            "structured", "search_parse",
            SearchParseInput(message=message, current_filters=[c["label"] for c in chips(prev)],
                             last_question=state.get("last_question"), results_shown=len(last_ids), today=date.today()),
            deadline=deadline_in(30), sync=True,
        )).value
        upd = apply_slang(message, upd, prev)

    def done(reply: dict[str, Any], **extra: Any) -> SearchChatState:
        msg = {"role": "assistant", "content": reply.get("intro", ""), **reply, **extra}
        return {"messages": [msg], "asked": asked, "last_question": extra.get("question")}

    # ---- chitchat / question about a shown result
    if upd.intent == "chitchat":
        text = "Tell me what you're looking for, like \"2 BHK in Indiranagar under 40k, near metro\"."
        await emit("token", {"text": text})
        return done({"intro": text, "claims": []})
    if upd.intent == "ask_about_result":
        n = upd.result_number or 1
        if not last_ids or n > len(last_ids):
            text = (f"I've only shown {len(last_ids)} results so far." if last_ids
                    else "Search first, then ask me about a result.")
            await emit("token", {"text": text})
            return done({"intro": text, "claims": []})
        lid = last_ids[n - 1]
        com = await res.commutes(tx, prev, [lid])
        rows = await res.card_rows(tx, [lid])
        shown = await res.cards(tx, [lid], com, rows)
        if not shown:
            text = "That listing is no longer available."
            await emit("token", {"text": text})
            return done({"intro": text, "claims": []})
        await emit("cards", {"cards": [c.model_dump(mode="json") for c in shown]})
        reply = await respond(tx, emit, message, prev, [], 1, shown, {lid: rows[lid]["description"] or ""},
                              question=upd.question or message)
        return done(reply, card_ids=[str(lid)])

    # ---- resolve names, merge into the thread's filters
    upd, found, commute, notes = await resolve_names(tx, upd, prev)
    f, changes = merge(prev, upd, localities=found, commute=commute)
    if ctx.get("bbox"):
        f = f.model_copy(update={"bbox": ctx["bbox"], "locality_ids": [], "locality_names": []})
    await emit("filters", {"filters": f.model_dump(mode="json"), "chips": chips(f),
                           "changes": [c.model_dump(mode="json") for c in changes]})
    chat["last_filters"] = f.model_dump(mode="json")

    # ---- clarify (each question once per thread)
    missing = [k for k, ok in (("city", f.city), ("budget", f.rent_max)) if not ok and k not in asked]
    if missing:
        asked += missing
        q = {("city",): "Which city are you looking in: Bengaluru or Mumbai?",
             ("budget",): "What's your monthly budget?",
             ("city", "budget"): "Which city (Bengaluru or Mumbai), and what's your monthly budget?"}[tuple(missing)]
        text = " ".join([*notes, q])
        await emit("question", {"text": text})
        return done({"intro": text, "claims": []}, question=q)

    # ---- search, filter by commute, relax, rank
    found_ = await find(tx, f, changes)
    if found_.relaxed:
        await emit("relaxed", {"steps": found_.relaxed, "count": len(found_.hits)})
    hits, com, searched, relaxed, ranked = found_.hits, found_.commutes, found_.searched, found_.relaxed, found_.ranked
    chat["last_result_ids"] = ranked

    await emit("pins", {"pins": [p.model_dump(mode="json") for p in await res.pins(tx, ranked)]})
    rows = await res.card_rows(tx, ranked[:CARDS])
    shown = await res.cards(tx, ranked[:CARDS], com, rows)
    await emit("cards", {"cards": [c.model_dump(mode="json") for c in shown]})
    reply = await respond(tx, emit, message, searched, relaxed, len(hits), shown,
                          {i: r["description"] or "" for i, r in rows.items()})
    if notes:
        reply["intro"] = " ".join([*notes, reply["intro"]])
    return done(reply, card_ids=[str(c.id) for c in shown], relaxed=relaxed, total=len(hits))


def build_graph() -> StateGraph[SearchChatState]:
    g = StateGraph(SearchChatState)
    g.add_node("turn", turn)
    g.add_edge(START, "turn")
    g.add_edge("turn", END)
    return g


GRAPH = build_graph()


async def run_turn(tx: Tx, chat: dict[str, Any], message: str, emit: Emit, *, user_id: UUID,
                   bbox: tuple[float, float, float, float] | None = None, remove: list[str] | None = None) -> None:
    """Run one turn and persist the thread's filters and results on `chats`."""
    clean = strip_contacts(message)[:1000] or ("Remove " + ", ".join(remove) if remove else "Show results")
    ctx: dict[str, Any] = {"tx": tx, "emit": emit, "chat": chat, "bbox": bbox, "remove": remove}
    async with common.checkpointer(tx) as saver:
        graph = GRAPH.compile(checkpointer=saver)
        config: Any = {"configurable": {"thread_id": chat["thread_id"], "turn": ctx}}
        with tracing.trace("chat-search", input=clean, user_id=str(user_id), session_id=chat["thread_id"],
                           tags=["search"]) as t:
            state = await graph.ainvoke({"messages": [{"role": "user", "content": clean}]}, config, durability="sync")
            t.update(output=state["messages"][-1].get("content"))
    await tx.conn.execute(
        "update chats set last_filters = %s, last_result_ids = %s, updated_at = now() where id = %s",
        (Jsonb(chat["last_filters"]), chat["last_result_ids"], chat["id"]))


async def history(tx: Tx, thread_id: str) -> list[dict[str, Any]]:
    async with common.checkpointer(tx) as saver:
        snap = await GRAPH.compile(checkpointer=saver).aget_state({"configurable": {"thread_id": thread_id}})
    return list((snap.values or {}).get("messages", []))
