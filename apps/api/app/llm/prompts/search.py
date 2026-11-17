"""Tenant search prompts (backend plan §13).

- search_parse: the tenant's message → `SearchUpdate` (only what it says; code merges and resolves).
- search_respond: a short answer over results the code already found, as claims that each cite
  listing refs (L1..) or locality-note refs (N1..). `pipeline/citations.py` drops any claim whose
  numbers are not in what it cites.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.domain.filters import SearchUpdate
from app.llm.prompts import UNTRUSTED_RULE, Prompt, register, untrusted
from app.pipeline.query_heuristics import heuristic_search

# ------------------------------------------------------------------ parse


class SearchParseInput(BaseModel):
    message: str  # contacts removed
    current_filters: list[str]  # chip labels of the thread's filters, e.g. ["Koramangala", "Up to ₹35k"]
    last_question: str | None = None
    results_shown: int = 0
    today: date


PARSE_SYSTEM = (
    "You read a tenant's message in a rental search chat in India and return ONLY what it states or changes. "
    "Leave other fields empty; never guess.\n"
    "Amounts are monthly INR: '35k' = 35000, '1.2L' = 120000. 'Under 40k' = rent_max 40000. "
    "Cities: Bangalore/Bengaluru = bangalore, Mumbai/Bombay = mumbai. Area names go in locality_names as "
    "written; set replace_localities for 'X instead'. A workplace or place to commute to goes in commute_to "
    "with commute_minutes if given ('30 min from Manyata' = commute_to 'Manyata', 30). 'Near metro' = "
    "near_metro true. 'Family' = tenant_type family; 'bachelor(s)' = bachelors. Nice-to-haves that should "
    "not exclude anything ('quiet', 'sunny', 'near a park') go in soft. 'Remove the budget' / 'any area' "
    "goes in clear with the filter name (rent_max, locality_ids, bhk, furnishing, amenities, commute, "
    "near_metro_m, tenant_type, pets, parking, gated, no_brokerage, deposit_max, soft). "
    "A follow-up refines the current filters; set new_search only when the tenant clearly starts over. "
    "Questions about a result already shown ('the 2nd one', 'first flat') are intent ask_about_result with "
    "result_number and question. Greetings and thanks are chitchat. semantic_query is the descriptive part "
    "of the request in English, without numbers and area names.\n" + UNTRUSTED_RULE
)


def _parse_user(d: SearchParseInput) -> str:
    q = f"Assistant's last question: {d.last_question}\n" if d.last_question else ""
    return (f"Today: {d.today.isoformat()}\nCurrent filters: {d.current_filters or 'none'}\n"
            f"Results shown so far: {d.results_shown}\n{q}Tenant's message:\n{untrusted(d.message)}")


SEARCH_PARSE = register(
    Prompt(
        id="search_parse",
        version=1,
        system=PARSE_SYSTEM,
        input=SearchParseInput,
        output=SearchUpdate,
        user=_parse_user,
        description="Submit only the search filters the tenant's message states or changes.",
        fake=lambda d: heuristic_search(d.message),
    )
)

# ------------------------------------------------------------------ respond


class ResultFacts(BaseModel):
    ref: str  # "L1"
    locality: str
    bhk: int
    rent: int
    deposit: int | None
    furnishing: str
    tenant_pref: str
    available_from: str | None
    amenities: list[str]
    commute: str | None = None  # "24 min by car to Manyata Tech Park (estimate)"
    metro: str | None = None  # "Indiranagar metro, 600 m"
    description: str = ""  # redacted, trimmed


class NoteFacts(BaseModel):
    ref: str  # "N1"
    locality: str
    text: str


class RespondInput(BaseModel):
    request: str  # the tenant's message (redacted)
    filters: list[str]
    relaxed: list[str]
    total: int
    results: list[ResultFacts]
    notes: list[NoteFacts]
    question: str | None = None  # set for ask_about_result


_REFS = re.compile(r"\b[LN]\d+\b")


class Claim(BaseModel):
    text: str = Field(description="One short sentence")
    cites: list[str] = Field(description="Refs this sentence relies on, e.g. ['L1'] or ['L2', 'N1']")

    @model_validator(mode="before")
    @classmethod
    def _lenient(cls, v: object) -> object:
        """A small model sometimes writes a claim as a bare string "… ₹28,000 (L2)." or {"claim": …}.
        Read the refs from the text; the citation check still drops anything unsupported."""
        if isinstance(v, str):
            return {"text": v, "cites": list(dict.fromkeys(_REFS.findall(v)))}
        if isinstance(v, dict) and "text" not in v:
            text = next((v[k] for k in ("claim", "sentence", "statement") if isinstance(v.get(k), str)), None)
            if text is not None:
                cites = v.get("cites") or v.get("refs") or v.get("citations") or _REFS.findall(text)
                return {"text": text, "cites": list(dict.fromkeys(cites))}
        return v


class RespondOutput(BaseModel):
    intro: str = Field(description="One sentence with no facts about specific listings")
    claims: list[Claim] = Field(default_factory=list, max_length=6)


RESPOND_SYSTEM = (
    "You are RentFit's search assistant. Write a short reply to the tenant about the results below.\n"
    "intro: one friendly sentence summarising the search (no numbers about specific listings). "
    "claims: 2-4 short sentences, each about specific results or areas, each citing the refs it relies on "
    "(L1.. for listings, N1.. for area notes). Use ONLY facts in the given data; every number you write must "
    "appear in the cited items. Do not invent amenities, distances or prices. Highlight why the top results "
    "fit the request, and mention any trade-off (higher deposit, longer commute). If `question` is set, answer "
    "it about the given listing only. If there are no results, say so and suggest one change. Write in the "
    "tenant's language style (English or Hinglish). Never include phone numbers, emails or links.\n"
    + UNTRUSTED_RULE
)


def _respond_user(d: RespondInput) -> str:
    rows = "\n".join(r.model_dump_json(exclude_none=True) for r in d.results)
    notes = "\n".join(n.model_dump_json() for n in d.notes)
    q = f"Question about the result: {d.question}\n" if d.question else ""
    return (f"Tenant's request:\n{untrusted(d.request)}\n{q}Filters: {d.filters}\nRelaxed: {d.relaxed or 'nothing'}\n"
            f"Total matches: {d.total}\nResults:\n{untrusted(rows, 'listings')}\n"
            f"Area notes:\n{untrusted(notes, 'notes')}")


def fake_respond(d: RespondInput) -> dict[str, Any]:
    if not d.results:
        return {"intro": "I couldn't find homes matching all of that.",
                "claims": [{"text": "Try a higher budget or another area.", "cites": []}]}
    if d.question:
        r = d.results[0]
        bits = [f"It's a {r.bhk} BHK in {r.locality} at ₹{r.rent:,} a month."]
        if r.commute:
            bits.append(f"The commute is {r.commute}.")
        if r.metro:
            bits.append(f"Nearest metro: {r.metro}.")
        return {"intro": "Here's what I know about that one.", "claims": [{"text": b, "cites": [r.ref]} for b in bits]}
    claims = [{"text": f"{r.bhk} BHK in {r.locality} for ₹{r.rent:,}" + (f", {r.commute}" if r.commute else "") + ".",
               "cites": [r.ref]} for r in d.results[:3]]
    if d.notes:
        n = d.notes[0]
        claims.append({"text": n.text.split(". ")[1].rstrip(".") + "." if ". " in n.text else n.text,
                       "cites": [n.ref]})
    return {"intro": f"I found {d.total} {'home' if d.total == 1 else 'homes'} that match.", "claims": claims}


SEARCH_RESPOND = register(
    Prompt(
        id="search_respond",
        version=1,
        system=RESPOND_SYSTEM,
        input=RespondInput,
        output=RespondOutput,
        user=_respond_user,
        description="Submit the reply as an intro and cited claims.",
        fake=fake_respond,
    )
)
