"""Rent suggestion against real localities, rolled back."""

from __future__ import annotations

from tests.db.test_listings import locality, user


async def make(db, landlord_sub: str, kor: dict, rent: int, *, bhk: int = 2, offset: float = 0.0,  # type: ignore[no-untyped-def,type-arg]
               furnishing: str = "semi") -> None:
    await db.as_owner()
    await db.conn.execute(
        """insert into listings (landlord_id, status, published_at, city, locality_id, location, bhk, rent, furnishing)
           values (%s, 'published', now(), 'bangalore', %s, st_point(%s, %s, 4326)::geography, %s, %s, %s)""",
        (landlord_sub, kor["id"], kor["lng"] + offset, kor["lat"], bhk, rent, furnishing))


async def test_comparables_then_fallback(db, api) -> None:  # type: ignore[no-untyped-def]
    h = await user(db, api, "landlord")
    other = await db.auth_user()
    await db.as_role({"sub": str(other)})
    await db.conn.execute("select app.create_profile('landlord', 'Other')")
    kor = await locality(db, "Koramangala")

    lid = (await api.post("/v1/landlord/listings", json={"city": "bangalore"}, headers=h)).json()["data"]["id"]
    await api.patch(f"/v1/landlord/listings/{lid}", headers={**h, "If-Match": "1"}, json=[
        {"op": "set", "field": "bhk", "value": 2}, {"op": "set", "field": "rent", "value": 50000},
        {"op": "set", "field": "furnishing", "value": "semi"}])
    res = (await api.get(f"/v1/landlord/listings/{lid}/rent-suggestion", headers=h)).json()["data"]
    assert res["basis"] == "not_enough_info"

    await api.put(f"/v1/landlord/listings/{lid}/location", json={"lat": kor["lat"], "lng": kor["lng"]}, headers=h)
    # Clear out any real listings nearby so the numbers below are exact.
    await db.as_owner()
    await db.conn.execute("update listings set status = 'paused' where status = 'published' and city = 'bangalore'")
    res = (await api.get(f"/v1/landlord/listings/{lid}/rent-suggestion", headers=h)).json()["data"]
    assert res["basis"] == "locality_estimate" and "estimate" in res["text"]

    for rent in (30000, 32000, 34000, 36000, 38000):
        await make(db, str(other), kor, rent, offset=0.002)
    await make(db, str(other), kor, 99000, bhk=3)          # different bhk
    await make(db, str(other), kor, 99000, furnishing="unfurnished", offset=0.001)  # one step from semi: counts
    await make(db, str(other), kor, 99000, offset=0.2)     # ~20 km away
    res = (await api.get(f"/v1/landlord/listings/{lid}/rent-suggestion", headers=h)).json()["data"]
    assert res["basis"] == "comparables" and res["radius_m"] == 1500
    assert res["count"] == 6  # five semi + one unfurnished (one step from semi)
    assert res["p50"] == 35000 and res["position"] == "above"
    assert "₹" in res["text"] and len(res["comparable_ids"]) == 6
