"""Photo upload flow with the in-memory store (backend plan §8.1), rolled back."""

from __future__ import annotations

from app.services.storage import MemoryStorage, get_storage
from tests.db.test_listings import user

REQ = {"content_type": "image/webp", "bytes": 300_000, "thumb_bytes": 30_000}


def store() -> MemoryStorage:
    s = get_storage()
    assert isinstance(s, MemoryStorage)
    return s


def path_of(url: str) -> str:
    return url.split("/v1/dev/storage/", 1)[1].split("?", 1)[0]


async def upload(api, h, lid: str, size: int = 300_000, ctype: str = "image/webp") -> str:  # type: ignore[no-untyped-def]
    res = await api.post(f"/v1/landlord/listings/{lid}/photos", json=REQ, headers=h)
    assert res.status_code == 201, res.text
    up = res.json()["data"]
    store().put(path_of(up["upload_url"]), b"x" * size, ctype)
    store().put(path_of(up["thumb_upload_url"]), b"x" * 1000, ctype)
    return str(up["photo_id"])


async def test_upload_confirm_reorder_delete(db, api) -> None:  # type: ignore[no-untyped-def]
    h = await user(db, api, "landlord")
    lid = (await api.post("/v1/landlord/listings", headers=h)).json()["data"]["id"]

    # Confirm before the upload finished.
    res = await api.post(f"/v1/landlord/listings/{lid}/photos", json=REQ, headers=h)
    early = res.json()["data"]["photo_id"]
    res = await api.post(f"/v1/landlord/listings/{lid}/photos/{early}/confirm", headers=h)
    assert res.status_code == 409 and res.json()["error"]["code"] == "upload_incomplete"

    ids = [await upload(api, h, lid) for _ in range(3)]
    for pid in ids:
        res = await api.post(f"/v1/landlord/listings/{lid}/photos/{pid}/confirm", headers=h)
        assert res.status_code == 200, res.text
    photos = res.json()["data"]
    assert [p["id"] for p in photos] == ids and [p["position"] for p in photos] == [0, 1, 2]
    assert (await api.get(f"/v1/landlord/listings/{lid}", headers=h)).json()["data"]["photo_count"] == 3

    res = await api.put(f"/v1/landlord/listings/{lid}/photos/order", json={"photo_ids": ids[::-1]}, headers=h)
    assert [p["id"] for p in res.json()["data"]] == ids[::-1]
    res = await api.put(f"/v1/landlord/listings/{lid}/photos/order", json={"photo_ids": ids[:2]}, headers=h)
    assert res.status_code == 422

    res = await api.delete(f"/v1/landlord/listings/{lid}/photos/{ids[0]}", headers=h)
    assert res.status_code == 200 and len(res.json()["data"]) == 2


async def test_size_and_type_limits(db, api) -> None:  # type: ignore[no-untyped-def]
    h = await user(db, api, "landlord")
    lid = (await api.post("/v1/landlord/listings", headers=h)).json()["data"]["id"]
    res = await api.post(f"/v1/landlord/listings/{lid}/photos", json={**REQ, "bytes": 6 * 1024 * 1024}, headers=h)
    assert res.status_code == 413
    res = await api.post(f"/v1/landlord/listings/{lid}/photos", json={**REQ, "content_type": "application/pdf"},
                         headers=h)
    assert res.status_code == 422

    # Declared small, uploaded big: rejected on confirm and removed.
    pid = await upload(api, h, lid, size=6 * 1024 * 1024)
    res = await api.post(f"/v1/landlord/listings/{lid}/photos/{pid}/confirm", headers=h)
    assert res.status_code == 422 and res.json()["error"]["code"] == "photo_rejected"
    # Not an image.
    pid = await upload(api, h, lid, ctype="text/html")
    res = await api.post(f"/v1/landlord/listings/{lid}/photos/{pid}/confirm", headers=h)
    assert res.status_code == 422


async def test_other_landlords_cannot_touch_photos(db, api) -> None:  # type: ignore[no-untyped-def]
    a, b = await user(db, api, "landlord"), await user(db, api, "landlord")
    lid = (await api.post("/v1/landlord/listings", headers=a)).json()["data"]["id"]
    assert (await api.post(f"/v1/landlord/listings/{lid}/photos", json=REQ, headers=b)).status_code == 404
    assert (await api.get(f"/v1/landlord/listings/{lid}/photos", headers=b)).status_code == 404
