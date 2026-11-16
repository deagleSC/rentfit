"""/v1/me against the real database, rolled back (see conftest)."""

from tests.conftest import auth_header


async def test_profile_lifecycle(db, api) -> None:  # type: ignore[no-untyped-def]
    uid = await db.auth_user()
    h = auth_header(uid)

    res = await api.get("/v1/me", headers=h)
    assert res.status_code == 404 and res.json()["error"]["code"] == "profile_missing"

    res = await api.post("/v1/me/profile", json={"role": "landlord", "name": "Asha"}, headers=h)
    assert res.status_code == 200, res.text
    assert res.json()["data"]["role"] == "landlord"

    # Idempotent with the same role, conflict with another.
    assert (await api.post("/v1/me/profile", json={"role": "landlord", "name": "Asha"}, headers=h)).status_code == 200
    res = await api.post("/v1/me/profile", json={"role": "tenant", "name": "Asha"}, headers=h)
    assert res.status_code == 409 and res.json()["error"]["code"] == "role_conflict"

    res = await api.patch("/v1/me", json={"phone": "+919876543210"}, headers=h)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["has_phone"] is True and "phone" not in data

    res = await api.patch("/v1/me", json={"phone": "12345"}, headers=h)
    assert res.status_code == 422
