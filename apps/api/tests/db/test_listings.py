"""Landlord listing endpoints against the real database, rolled back (see conftest)."""

from __future__ import annotations

import psycopg

from tests.conftest import auth_header


async def user(db, api, role: str) -> dict[str, str]:  # type: ignore[no-untyped-def]
    uid = await db.auth_user()
    h = auth_header(uid)
    assert (await api.post("/v1/me/profile", json={"role": role, "name": role.title()}, headers=h)).status_code == 200
    return h


async def locality(db, name: str) -> dict:  # type: ignore[no-untyped-def,type-arg]
    rows = await db.fetchall(
        "select id::text, city, st_y(centroid::geometry) as lat, st_x(centroid::geometry) as lng "
        "from localities where name = %s", (name,))
    assert rows, f"seed data missing {name}"
    return rows[0]


async def add_photos(db, listing_id: str, n: int) -> None:  # type: ignore[no-untyped-def]
    await db.as_owner()
    for i in range(n):
        await db.conn.execute(
            "insert into listing_photos (listing_id, storage_path, thumb_path, bytes, position, confirmed)"
            " values (%s, %s, %s, 1000, %s, true)", (listing_id, f"t/{listing_id}/{i}.webp", f"t/{listing_id}/{i}_t.webp", i))


async def test_create_patch_locate_publish(db, api) -> None:  # type: ignore[no-untyped-def]
    h = await user(db, api, "landlord")
    res = await api.post("/v1/landlord/listings", json={"city": "bangalore"}, headers=h)
    assert res.status_code == 201, res.text
    listing = res.json()["data"]
    lid, v = listing["id"], listing["version"]
    assert listing["status"] == "draft" and listing["city"] == "bangalore"

    # If-Match is required, and must match.
    assert (await api.patch(f"/v1/landlord/listings/{lid}", json=[], headers=h)).status_code == 428
    res = await api.patch(f"/v1/landlord/listings/{lid}", headers={**h, "If-Match": str(v + 5)},
                          json=[{"op": "set", "field": "rent", "value": 30000}])
    assert res.status_code == 409 and res.json()["error"]["code"] == "version_conflict"

    patches = [
        {"op": "set", "field": "bhk", "value": 2},
        {"op": "set", "field": "rent", "value": 35000},
        {"op": "set", "field": "deposit", "value": 70000},
        {"op": "set", "field": "furnishing", "value": "semi"},
        {"op": "set", "field": "tenant_pref", "value": "any"},
        {"op": "set", "field": "available_from", "value": "2026-12-01"},
        {"op": "set", "field": "description", "value": "Sunny 2BHK. Call 9876543210."},
        {"op": "add_amenity", "amenity": "lift"},
    ]
    res = await api.patch(f"/v1/landlord/listings/{lid}", json=patches, headers={**h, "If-Match": str(v)})
    assert res.status_code == 200, res.text
    body = res.json()["data"]
    assert body["listing"]["version"] == v + 1
    assert "9876543210" not in body["listing"]["description"]
    assert {c["field"] for c in body["changes"]} >= {"bhk", "rent", "amenities", "description"}

    # Invalid result is rejected whole.
    res = await api.patch(f"/v1/landlord/listings/{lid}", headers={**h, "If-Match": str(v + 1)},
                          json=[{"op": "set", "field": "deposit", "value": 10_000_000}])
    assert res.status_code == 422 and res.json()["error"]["code"] == "invalid_patch"

    # Not ready: no locality, no pin, no photos.
    res = await api.post(f"/v1/landlord/listings/{lid}/publish", headers=h)
    assert res.status_code == 422
    reasons = res.json()["error"]["details"]["reasons"]
    assert "missing:locality_id" in reasons and "missing:location" in reasons and "photos:at_least_3" in reasons

    # Drop a pin in Koramangala: the locality is filled in.
    kor = await locality(db, "Koramangala")
    res = await api.put(f"/v1/landlord/listings/{lid}/location", json={"lat": kor["lat"], "lng": kor["lng"]}, headers=h)
    assert res.status_code == 200, res.text
    loc = res.json()["data"]
    assert loc["locality_name"] == "Koramangala" and not loc["mismatch"]
    assert loc["listing"]["locality_id"] == kor["id"]

    await add_photos(db, lid, 3)
    res = await api.post(f"/v1/landlord/listings/{lid}/publish", headers=h)
    assert res.status_code == 200, res.text
    assert res.json()["data"]["status"] == "published"

    # Lifecycle.
    assert (await api.post(f"/v1/landlord/listings/{lid}/publish", headers=h)).status_code == 409
    assert (await api.post(f"/v1/landlord/listings/{lid}/pause", headers=h)).json()["data"]["status"] == "paused"
    assert (await api.post(f"/v1/landlord/listings/{lid}/resume", headers=h)).json()["data"]["status"] == "published"
    assert (await api.post(f"/v1/landlord/listings/{lid}/let", headers=h)).json()["data"]["status"] == "let"
    cur = (await api.get(f"/v1/landlord/listings/{lid}", headers=h)).json()["data"]
    res = await api.patch(f"/v1/landlord/listings/{lid}", headers={**h, "If-Match": str(cur["version"])},
                          json=[{"op": "set", "field": "rent", "value": 1}])
    assert res.status_code == 409 and res.json()["error"]["code"] == "listing_closed"

    events = await db.fetchall("select from_status, to_status from listing_events where listing_id = %s order by id", (lid,))
    assert [e["to_status"] for e in events] == ["draft", "published", "paused", "published", "let"]


async def test_pin_mismatch_is_flagged_not_overwritten(db, api) -> None:  # type: ignore[no-untyped-def]
    h = await user(db, api, "landlord")
    lid = (await api.post("/v1/landlord/listings", json={"city": "bangalore"}, headers=h)).json()["data"]["id"]
    wf, kor = await locality(db, "Whitefield"), await locality(db, "Koramangala")
    await api.patch(f"/v1/landlord/listings/{lid}", headers={**h, "If-Match": "1"},
                    json=[{"op": "set", "field": "locality_id", "value": wf["id"]}])
    res = await api.put(f"/v1/landlord/listings/{lid}/location", json={"lat": kor["lat"], "lng": kor["lng"]}, headers=h)
    data = res.json()["data"]
    assert data["mismatch"] is True and data["locality_name"] == "Koramangala"
    assert data["listing"]["locality_id"] == wf["id"]  # the typed locality is kept until the landlord decides
    assert data["listing"]["flags"]["locality_mismatch"]["pin"] == kor["id"]

    # Choosing the pin's area clears the warning.
    res = await api.patch(f"/v1/landlord/listings/{lid}", headers={**h, "If-Match": str(data["listing"]["version"])},
                          json=[{"op": "set", "field": "locality_id", "value": kor["id"]}])
    after = res.json()["data"]["listing"]
    assert after["locality_id"] == kor["id"] and "locality_mismatch" not in after["flags"]


async def test_pin_outside_coverage(db, api) -> None:  # type: ignore[no-untyped-def]
    h = await user(db, api, "landlord")
    lid = (await api.post("/v1/landlord/listings", headers=h)).json()["data"]["id"]
    res = await api.put(f"/v1/landlord/listings/{lid}/location", json={"lat": 28.61, "lng": 77.21}, headers=h)  # Delhi
    assert res.status_code == 422 and res.json()["error"]["code"] == "outside_coverage"


async def test_access_rules(db, api) -> None:  # type: ignore[no-untyped-def]
    a, b, t = await user(db, api, "landlord"), await user(db, api, "landlord"), await user(db, api, "tenant")
    lid = (await api.post("/v1/landlord/listings", headers=a)).json()["data"]["id"]
    assert (await api.get(f"/v1/landlord/listings/{lid}", headers=b)).status_code == 404
    assert (await api.get("/v1/landlord/listings", headers=b)).json()["data"] == []
    res = await api.get("/v1/landlord/listings", headers=t)
    assert res.status_code == 403 and res.json()["error"]["code"] == "wrong_app"
    assert (await api.post("/v1/landlord/listings", headers=t)).status_code == 403


async def test_rls_tenants_see_only_published(db) -> None:  # type: ignore[no-untyped-def]
    landlord, tenant = await db.auth_user(), await db.auth_user()
    for uid, role in ((landlord, "landlord"), (tenant, "tenant")):
        await db.as_role({"sub": str(uid)})
        await db.conn.execute("select app.create_profile(%s, 'X')", (role,))
    await db.as_owner()
    rows = await db.fetchall(
        "insert into listings (landlord_id, status, published_at) values (%s, 'draft', null), (%s, 'published', now())"
        " returning id::text, status", (landlord, landlord))
    published = next(r["id"] for r in rows if r["status"] == "published")
    await db.as_role({"sub": str(tenant), "role": "tenant"})
    assert [r["id"] for r in await db.fetchall("select id::text from listings where landlord_id = %s", (landlord,))] == [published]
    cur = await db.conn.execute("update listings set rent = 1 where id = %s", (published,))
    assert cur.rowcount == 0
    await db.fails("insert into listing_events (listing_id, to_status) values (%s, 'let')", (published,),
                   psycopg.errors.InsufficientPrivilege)
    # Landlords cannot rewrite history.
    await db.as_role({"sub": str(landlord), "role": "landlord"})
    await db.fails("delete from listing_events", error=psycopg.errors.InsufficientPrivilege)
