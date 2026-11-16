"""Listing chat with the fake model (backend plan §11), rolled back. Phase 1 exit check:
a listing is created and edited by chat, and a chat edit equals the same form edit."""

from __future__ import annotations

from tests.db.test_listings import add_photos, locality, user


async def chat(api, h, lid: str, message: str) -> dict:  # type: ignore[no-untyped-def,type-arg]
    res = await api.post(f"/v1/landlord/listings/{lid}/chat", json={"message": message}, headers=h)
    assert res.status_code == 200, res.text
    return res.json()["data"]  # type: ignore[no-any-return]


async def test_create_and_edit_listing_by_chat(db, api) -> None:  # type: ignore[no-untyped-def]
    h = await user(db, api, "landlord")
    lid = (await api.post("/v1/landlord/listings", headers=h)).json()["data"]["id"]

    start = (await api.get(f"/v1/landlord/listings/{lid}/chat", headers=h)).json()["data"]
    assert start["messages"] == [] and start["next"] == "city"

    out = await chat(api, h, lid, "2BHK in Koramangala, rent 35k, 2 months deposit, semi furnished, family only. "
                                  "Lift and gym. Ready to move. Call me on 98765 43210.")
    listing = out["listing"]
    kor = await locality(db, "Koramangala")
    assert (listing["bhk"], listing["rent"], listing["deposit"]) == (2, 35000, 70000)
    assert listing["furnishing"] == "semi" and listing["tenant_pref"] == "family"
    assert listing["city"] == "bangalore" and listing["locality_id"] == kor["id"]
    assert set(listing["amenities"]) == {"lift", "gym"} and listing["available_from"] is not None
    assert out["next"] == "location"
    assert "Koramangala" in out["messages"][-1]["content"] and "pin" in out["messages"][-1]["content"]
    # The stored conversation never holds the phone number.
    assert "98765" not in out["messages"][0]["content"]

    out = await chat(api, h, lid, "bachelors also ok")
    assert out["listing"]["tenant_pref"] == "any"
    assert [c["field"] for c in out["changes"]] == ["tenant_pref"]

    # Pin + photos → ready.
    await api.put(f"/v1/landlord/listings/{lid}/location", json={"lat": kor["lat"], "lng": kor["lng"]}, headers=h)
    await add_photos(db, lid, 3)
    out = await chat(api, h, lid, "maintenance 2500")
    assert out["listing"]["maintenance"] == 2500 and out["next"] is None and out["missing"] == []

    hist = (await api.get(f"/v1/landlord/listings/{lid}/chat", headers=h)).json()["data"]
    assert len(hist["messages"]) == 6 and hist["next"] is None
    assert (await api.post(f"/v1/landlord/listings/{lid}/publish", headers=h)).status_code == 200


async def test_unrelated_message_changes_nothing(db, api) -> None:  # type: ignore[no-untyped-def]
    h = await user(db, api, "landlord")
    lid = (await api.post("/v1/landlord/listings", headers=h)).json()["data"]["id"]
    out = await chat(api, h, lid, "hello there")
    assert out["changes"] == [] and "didn't catch" in out["messages"][-1]["content"]
    assert out["listing"]["version"] == 1


async def test_chat_edit_equals_form_edit(db, api) -> None:  # type: ignore[no-untyped-def]
    h = await user(db, api, "landlord")
    base = "2BHK in Koramangala, rent 35k, 2 months deposit, semi furnished"
    a = (await api.post("/v1/landlord/listings", headers=h)).json()["data"]["id"]
    b = (await api.post("/v1/landlord/listings", headers=h)).json()["data"]["id"]
    await chat(api, h, a, base)
    await chat(api, h, b, base)

    via_chat = (await chat(api, h, a, "make deposit 3 months, fully furnished, bachelors also ok"))["listing"]
    cur = (await api.get(f"/v1/landlord/listings/{b}", headers=h)).json()["data"]
    res = await api.patch(f"/v1/landlord/listings/{b}", headers={**h, "If-Match": str(cur["version"])}, json=[
        {"op": "set", "field": "deposit", "value": 105000},
        {"op": "set", "field": "furnishing", "value": "full"},
        {"op": "set", "field": "tenant_pref", "value": "any"},
    ])
    via_form = res.json()["data"]["listing"]
    fields = ["bhk", "rent", "deposit", "furnishing", "tenant_pref", "locality_id", "city", "amenities"]
    assert {f: via_chat[f] for f in fields} == {f: via_form[f] for f in fields}


async def test_other_landlord_cannot_use_the_chat(db, api) -> None:  # type: ignore[no-untyped-def]
    a, b = await user(db, api, "landlord"), await user(db, api, "landlord")
    lid = (await api.post("/v1/landlord/listings", headers=a)).json()["data"]["id"]
    res = await api.post(f"/v1/landlord/listings/{lid}/chat", json={"message": "3BHK"}, headers=b)
    assert res.status_code == 404
    assert (await api.get(f"/v1/landlord/listings/{lid}/chat", headers=b)).status_code == 404
