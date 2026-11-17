"""Phase 3 exit check (backend plan §17): a 4-turn search conversation, and an enquiry that reaches
the landlord with no contact details anywhere a model could see them. Fake model, inline jobs,
rolled back (see conftest). Production's seeded listings are visible too, so assertions check
properties of the results rather than exact sets."""

from __future__ import annotations

import json
import re
from typing import Any

import pytest

from app.agents import common
from tests.conftest import auth_header
from tests.db.test_listings import user
from tests.db.test_retrieval_index import published

PHONE = re.compile(r"\d{5}\s?\d{5}|@\w+\.\w+")


def events(text: str) -> list[tuple[str, dict[str, Any]]]:
    out = []
    for block in text.strip().split("\n\n"):
        name = re.search(r"^event: (.+)$", block, re.M)
        data = re.search(r"^data: (.+)$", block, re.M)
        if name and data:
            out.append((name.group(1), json.loads(data.group(1))))
    return out


async def say(api, h, message: str = "", **body: Any) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    res = await api.post("/v1/tenant/search/chat", json={"message": message, **body}, headers=h)
    assert res.status_code == 200, res.text
    ev = events(res.text)
    names = [n for n, _ in ev]
    assert names[-1] == "done", ev[-1]
    got: dict[str, Any] = {"first_filters": next((d for n, d in ev if n == "filters"), None)}
    for n, d in ev:
        got[n] = d  # the last of each kind (filters is re-sent after relaxing)
    return got


@pytest.fixture
def model_log(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    seen: list[str] = []
    real = common.call_structured

    async def spy(role: str, prompt_id: str, input: Any, *a: Any, **k: Any) -> Any:
        seen.append(input.model_dump_json())
        return await real(role, prompt_id, input, *a, **k)

    monkeypatch.setattr(common, "call_structured", spy)
    return seen


async def test_four_turn_search(db, api, model_log) -> None:  # type: ignore[no-untyped-def]
    for _ in range(2):  # two listings we control: Koramangala 2 BHK at ₹35,000 (with a phone in the text)
        await published(db, api)
    t = await user(db, api, "tenant")

    # 1. initial search (few Koramangala 2 BHKs under 40k exist, so it may relax and must say so)
    r = await say(api, t, "2 BHK in Koramangala under 40k")
    chat_id = r["done"]["chat_id"]
    asked = r["first_filters"]["filters"]
    assert asked["city"] == "bangalore" and asked["bhk"] == [2] and asked["rent_max"] == 40000
    assert asked["locality_names"] == ["Koramangala"]
    f = r["filters"]["filters"]
    assert f == asked  # the thread keeps what the tenant asked for; relaxing is reported, not saved
    cards = r["cards"]["cards"]
    budget = 44000 if any("budget" in s for s in r.get("relaxed", {}).get("steps", [])) else 40000
    assert len(cards) >= 2 and all(c["bhk"] == 2 and c["rent"] <= budget for c in cards)
    assert {p["id"] for p in r["pins"]["pins"]} >= {c["id"] for c in cards}
    listing_ids = {c["id"] for c in cards}
    for claim in r["citations"]["claims"]:  # every surviving citation points at something shown
        for ref in claim["refs"]:
            assert ref["kind"] == "note" or ref["id"] in listing_ids

    # 2. "cheaper": a patch on the thread's filters, not a new search
    r = await say(api, t, "thoda sasta", chat_id=chat_id)
    assert [c["field"] for c in r["filters"]["changes"]] == ["rent_max"]
    f = r["filters"]["filters"]
    assert f["rent_max"] == 36000 and f["bhk"] == [2] and f["locality_names"] == ["Koramangala"]
    assert not any("budget" in s for s in r.get("relaxed", {}).get("steps", []))  # "cheaper" is not undone
    assert all(c["rent"] <= 36000 for c in r["cards"]["cards"])
    shown = r["cards"]["cards"]

    # 3. ordinal follow-up answers about the 2nd result without searching again
    r = await say(api, t, "what about the 2nd one?", chat_id=chat_id)
    assert "filters" not in r and len(r["cards"]["cards"]) == 1
    assert r["cards"]["cards"][0]["id"] == shown[1]["id"]

    # 4. near metro instead
    r = await say(api, t, "near metro instead", chat_id=chat_id)
    f = r["filters"]["filters"]
    assert f["near_metro_m"] == 1000
    widened = any("metro distance" in s for s in r.get("relaxed", {}).get("steps", []))
    limit = 2000 if widened else 1000
    assert all((c["metro"] or {}).get("metres", 99999) <= limit for c in r["cards"]["cards"])

    # History replays the thread
    h = (await api.get(f"/v1/tenant/chats/{chat_id}", headers=t)).json()["data"]
    assert [m["role"] for m in h["messages"]] == ["user", "assistant"] * 4
    assert h["filters"]["near_metro_m"] == f["near_metro_m"]

    # No model input carried the landlord's phone number
    assert model_log and not any(PHONE.search(s) for s in model_log)


async def test_clarify_relax_and_chip_removal(db, api) -> None:  # type: ignore[no-untyped-def]
    t = await user(db, api, "tenant")
    r = await say(api, t, "looking for a 2bhk")
    assert r["question"]["text"].startswith("Which city")
    chat_id = r["done"]["chat_id"]
    r = await say(api, t, "bangalore, budget 12k", chat_id=chat_id)  # too tight: relaxes and says so
    assert "question" not in r
    assert r["relaxed"]["steps"][0].startswith("raised the budget")
    r = await say(api, t, chat_id=chat_id, remove_filters=["bhk"])
    assert r["filters"]["filters"]["bhk"] == []
    bad = await api.post("/v1/tenant/search/chat", json={"chat_id": chat_id, "remove_filters": ["landlord_id"]},
                         headers=t)
    assert bad.status_code == 422


async def test_search_is_tenant_only_and_thread_private(db, api) -> None:  # type: ignore[no-untyped-def]
    landlord = await user(db, api, "landlord")
    assert (await api.post("/v1/tenant/search/chat", json={"message": "hi"}, headers=landlord)).status_code == 403
    a, b = await user(db, api, "tenant"), await user(db, api, "tenant")
    chat_id = (await say(api, a, "hello"))["done"]["chat_id"]
    assert (await api.get(f"/v1/tenant/chats/{chat_id}", headers=b)).status_code == 404
    assert (await api.post("/v1/tenant/search/chat", json={"chat_id": chat_id, "message": "x"},
                           headers=b)).status_code == 404


async def test_enquiry_reaches_landlord_without_contacts(db, api) -> None:  # type: ignore[no-untyped-def]
    h, lid = await published(db, api)
    t = await user(db, api, "tenant")
    res = await api.post("/v1/tenant/enquiries", headers=t,
                         json={"listing_id": lid, "message": "Is it available? Call me on 98765 43210 or a@b.com"})
    assert res.status_code == 201, res.text
    thread = res.json()["data"]
    eid = thread["enquiry"]["id"]
    assert not PHONE.search(thread["messages"][0]["body"])

    inbox = (await api.get("/v1/landlord/enquiries", headers=h)).json()["data"]
    assert [e["id"] for e in inbox] == [eid] and inbox[0]["unread"] == 1 and inbox[0]["other_name"] == "Tenant"
    res = await api.post(f"/v1/enquiries/{eid}/messages", json={"body": "Yes, come on Saturday."}, headers=h)
    assert res.status_code == 201
    assert [m["mine"] for m in res.json()["data"]["messages"]] == [False, True]
    tenant_view = (await api.get("/v1/tenant/enquiries", headers=t)).json()["data"]
    assert tenant_view[0]["unread"] == 1 and tenant_view[0]["last_message"] == "Yes, come on Saturday."
    notes = (await api.get("/v1/notifications", headers=t)).json()["data"]
    assert [n["entity_id"] for n in notes] == [eid]

    # A second start reuses the enquiry; strangers can't read it
    again = await api.post("/v1/tenant/enquiries", headers=t, json={"listing_id": lid, "message": "Saturday works"})
    assert again.json()["data"]["enquiry"]["id"] == eid
    other = await user(db, api, "tenant")
    assert (await api.get(f"/v1/enquiries/{eid}", headers=other)).status_code == 404
    assert (await api.post(f"/v1/enquiries/{eid}/messages", json={"body": "hi"}, headers=other)).status_code == 404


async def test_detail_shortlist_saved(db, api) -> None:  # type: ignore[no-untyped-def]
    h, lid = await published(db, api)
    t = await user(db, api, "tenant")
    d = (await api.get(f"/v1/listings/{lid}", headers=t)).json()["data"]
    assert d["locality"] == "Koramangala" and d["notes"] and "9876543210" not in (d["description"] or "")
    assert any(n["kind"] == "metro_station" for n in d["nearby"]) and not d["shortlisted"]
    poi = d["nearby"][0]["id"]
    d = (await api.get(f"/v1/listings/{lid}?poi_id={poi}", headers=t)).json()["data"]
    assert d["commute"]["provider"] == "haversine" and d["commute"]["minutes"] >= 1

    assert (await api.put(f"/v1/tenant/shortlists/{lid}", headers=t)).status_code == 204
    assert (await api.put(f"/v1/tenant/shortlists/{lid}", headers=t)).status_code == 204  # idempotent
    assert [c["id"] for c in (await api.get("/v1/tenant/shortlists", headers=t)).json()["data"]] == [lid]
    await api.post(f"/v1/landlord/listings/{lid}/pause", headers=h)
    assert (await api.get("/v1/tenant/shortlists", headers=t)).json()["data"] == []  # paused: hidden
    assert (await api.get(f"/v1/listings/{lid}", headers=t)).status_code == 404

    res = await api.post("/v1/tenant/saved-searches", headers=t,
                         json={"name": "Office", "filters": {"city": "bangalore", "bhk": [2], "rent_max": 40000}})
    assert res.status_code == 201 and res.json()["data"]["chips"][0]["label"] == "2 BHK"
    saved = res.json()["data"]
    r = await say(api, t, filters=saved["filters"])
    assert r["filters"]["filters"]["rent_max"] == 40000 and "cards" in r
    assert (await api.delete(f"/v1/tenant/saved-searches/{saved['id']}", headers=t)).status_code == 204
    assert (await api.get("/v1/tenant/saved-searches", headers=t)).json()["data"] == []
    assert (await api.get(f"/v1/listings/{lid}", headers=auth_header(await db.auth_user()))).status_code == 403
