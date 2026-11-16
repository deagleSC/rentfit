"""embed-listing through the API (inline jobs, hashing embedder), rolled back (see conftest)."""

from __future__ import annotations

from tests.conftest import auth_header
from tests.db.test_listings import add_photos, locality, user


async def published(db, api) -> tuple[dict[str, str], str]:  # type: ignore[no-untyped-def]
    h = await user(db, api, "landlord")
    lid = (await api.post("/v1/landlord/listings", json={"city": "bangalore"}, headers=h)).json()["data"]["id"]
    patches = [
        {"op": "set", "field": "bhk", "value": 2}, {"op": "set", "field": "rent", "value": 35000},
        {"op": "set", "field": "deposit", "value": 70000}, {"op": "set", "field": "furnishing", "value": "semi"},
        {"op": "set", "field": "tenant_pref", "value": "any"},
        {"op": "set", "field": "available_from", "value": "2026-12-01"},
        {"op": "set", "field": "description", "value": "Sunny flat near the park. Call 9876543210."},
    ]
    assert (await api.patch(f"/v1/landlord/listings/{lid}", json=patches, headers={**h, "If-Match": "1"})).status_code == 200
    kor = await locality(db, "Koramangala")
    await api.put(f"/v1/landlord/listings/{lid}/location", json={"lat": kor["lat"], "lng": kor["lng"]}, headers=h)
    await add_photos(db, lid, 3)
    res = await api.post(f"/v1/landlord/listings/{lid}/publish", headers=h)
    assert res.status_code == 200, res.text
    return h, lid


async def chunks(db, lid: str) -> list[dict]:  # type: ignore[type-arg,no-untyped-def]
    await db.as_owner()
    return [dict(r) for r in await db.fetchall(
        "select chunk_index, content, content_hash, embedding::text as e from listing_chunks"
        " where listing_id = %s order by chunk_index", (lid,))]


async def test_publish_indexes_and_pause_removes(db, api) -> None:  # type: ignore[no-untyped-def]
    h, lid = await published(db, api)
    rows = await chunks(db, lid)
    assert len(rows) == 2
    assert rows[0]["content"].startswith("2 BHK semi-furnished flat for rent in Koramangala, Bengaluru")
    assert "9876543210" not in rows[1]["content"]
    runs = await db.fetchall("select status from job_runs where entity_id = %s and type = 'embed-listing'", (lid,))
    assert [r["status"] for r in runs] == ["done"]

    assert (await api.post(f"/v1/landlord/listings/{lid}/pause", headers=h)).status_code == 200
    assert await chunks(db, lid) == []
    assert (await api.post(f"/v1/landlord/listings/{lid}/resume", headers=h)).status_code == 200
    assert len(await chunks(db, lid)) == 2


async def test_edit_reembeds_only_changed_chunks(db, api) -> None:  # type: ignore[no-untyped-def]
    h, lid = await published(db, api)
    before = await chunks(db, lid)
    version = (await api.get(f"/v1/landlord/listings/{lid}", headers=h)).json()["data"]["version"]
    res = await api.patch(f"/v1/landlord/listings/{lid}", headers={**h, "If-Match": str(version)},
                          json=[{"op": "set", "field": "rent", "value": 32000}])
    assert res.status_code == 200
    after = await chunks(db, lid)
    assert "₹32,000" in after[0]["content"] and after[0]["e"] != before[0]["e"]
    assert after[1]["e"] == before[1]["e"]  # description unchanged: same vector, not re-embedded


async def test_chunk_rls(db, api) -> None:  # type: ignore[no-untyped-def]
    h, lid = await published(db, api)
    tenant = await db.auth_user()
    await api.post("/v1/me/profile", json={"role": "tenant", "name": "T"}, headers=auth_header(tenant))
    other = await db.auth_user()

    await db.as_role({"sub": str(tenant), "role": "tenant"})
    assert len(await db.fetchall("select 1 from listing_chunks where listing_id = %s", (lid,))) == 2
    await db.conn.execute("delete from listing_chunks where listing_id = %s", (lid,))  # no policy: deletes nothing
    assert len(await db.fetchall("select 1 from listing_chunks where listing_id = %s", (lid,))) == 2
    await db.as_role({"sub": str(other), "role": "landlord"})
    await db.fails("insert into listing_chunks (listing_id, chunk_index, content, content_hash, embedding)"
                   " values (%s, 9, 'x', 'x', array_fill(0, array[384])::extensions.vector)", (lid,))
    assert len(await db.fetchall("select 1 from locality_notes limit 1")) == 1


async def test_map_pins_for_tenants_only(db, api) -> None:  # type: ignore[no-untyped-def]
    h, lid = await published(db, api)
    t = await user(db, api, "tenant")
    res = await api.get("/v1/tenant/map/listings?city=bangalore", headers=t)
    assert res.status_code == 200, res.text
    pin = next(p for p in res.json()["data"] if p["id"] == lid)
    assert pin["locality"] == "Koramangala" and pin["rent"] == 35000
    assert (await api.get("/v1/tenant/map/listings?city=bangalore", headers=h)).status_code == 403
    assert (await api.get("/v1/tenant/map/listings?city=nowhere", headers=t)).status_code == 404
    await api.post(f"/v1/landlord/listings/{lid}/pause", headers=h)
    res = await api.get("/v1/tenant/map/listings?city=bangalore", headers=t)
    assert lid not in {p["id"] for p in res.json()["data"]}
