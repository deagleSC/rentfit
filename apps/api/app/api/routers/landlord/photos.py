"""Listing photos (backend plan §7.2, §8.1): signed direct uploads, confirm, reorder, delete.

Flow: POST /photos returns signed upload URLs for the full image and its thumbnail (the browser
resizes to WebP first). The browser PUTs both, then calls /confirm, which checks the objects exist,
are within the size limit and are images. Only confirmed photos count towards publishing.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core import ratelimit
from app.core.auth import PrincipalDep, require_role, user_tx
from app.core.config import get_settings
from app.core.db import Tx
from app.core.errors import ERROR_RESPONSES, AppError, Ok, ok
from app.domain.listing import PHOTOS_MAX, PHOTOS_MIN
from app.services import listings as repo
from app.services.storage import ObjectNotFound, get_storage

router = APIRouter(prefix="/v1/landlord/listings", tags=["landlord"], responses=ERROR_RESPONSES)

THUMB_MAX_BYTES = 512 * 1024
ContentType = Literal["image/webp", "image/jpeg", "image/png"]
EXT = {"image/webp": "webp", "image/jpeg": "jpg", "image/png": "png"}


class PhotoUploadRequest(BaseModel):
    content_type: ContentType
    bytes: int = Field(gt=0, description="Size of the full image after resizing in the browser")
    thumb_bytes: int = Field(gt=0, le=THUMB_MAX_BYTES)


class PhotoUpload(BaseModel):
    photo_id: UUID
    upload_url: str
    thumb_upload_url: str
    content_type: ContentType


class Photo(BaseModel):
    id: UUID
    position: int
    url: str
    thumb_url: str


class PhotoOrder(BaseModel):
    photo_ids: list[UUID] = Field(min_length=1, max_length=PHOTOS_MAX)


async def _photos(tx: Tx, listing_id: UUID) -> list[Photo]:
    rows = await tx.fetchall(
        "select id, position, storage_path, thumb_path from listing_photos"
        " where listing_id = %s and confirmed order by position, created_at",
        (listing_id,),
    )
    storage = get_storage()
    return [
        Photo(id=r["id"], position=r["position"], url=await storage.signed_download(r["storage_path"], 3600),
              thumb_url=await storage.signed_download(r["thumb_path"], 3600))
        for r in rows
    ]


@router.get("/{listing_id}/photos", response_model=Ok[list[Photo]])
async def list_photos(listing_id: UUID, principal: PrincipalDep) -> Ok[list[Photo]]:
    async with user_tx(principal) as (tx, user):
        require_role(user, "landlord")
        await repo.get(tx, listing_id)
        return ok(await _photos(tx, listing_id))


@router.post("/{listing_id}/photos", response_model=Ok[PhotoUpload], status_code=201)
async def start_upload(listing_id: UUID, body: PhotoUploadRequest, principal: PrincipalDep) -> Ok[PhotoUpload]:
    s = get_settings()
    if body.bytes > s.photo_max_bytes:
        raise AppError(413, "photo_too_large", f"Photos must be under {s.photo_max_bytes // (1024 * 1024)} MB.")
    async with user_tx(principal) as (tx, user):
        require_role(user, "landlord")
        listing = await repo.get(tx, listing_id)
        if listing.status == "let":
            raise AppError(409, "listing_closed", "This listing is marked as let.")
        await ratelimit.hit(tx, f"photo-upload:{user.user_id}", 60, timedelta(hours=1),
                            message="Too many uploads. Try again in a while.")
        row = await tx.fetchone(
            "select count(*) filter (where confirmed) as confirmed,"
            " count(*) filter (where not confirmed and created_at > now() - interval '1 hour') as pending"
            " from listing_photos where listing_id = %s",
            (listing_id,),
        )
        assert row is not None
        if row["confirmed"] + row["pending"] >= PHOTOS_MAX:
            raise AppError(409, "too_many_photos", f"A listing can have at most {PHOTOS_MAX} photos.")
        new = await tx.fetchone("select gen_random_uuid() as id")
        assert new is not None
        pid = new["id"]
        base = f"{user.user_id}/{listing_id}/{pid}"
        path, thumb = f"{base}.{EXT[body.content_type]}", f"{base}_thumb.{EXT[body.content_type]}"
        await tx.conn.execute(
            "insert into listing_photos (id, listing_id, storage_path, thumb_path, bytes) values (%s, %s, %s, %s, %s)",
            (pid, listing_id, path, thumb, body.bytes),
        )
        storage = get_storage()
        up, up_thumb = await storage.signed_upload(path), await storage.signed_upload(thumb)
        return ok(PhotoUpload(photo_id=pid, upload_url=up.url, thumb_upload_url=up_thumb.url,
                              content_type=body.content_type))


@router.post("/{listing_id}/photos/{photo_id}/confirm", response_model=Ok[list[Photo]])
async def confirm_upload(listing_id: UUID, photo_id: UUID, principal: PrincipalDep) -> Ok[list[Photo]]:
    """Check both objects are in storage, are images and within the limits; then count the photo."""
    s = get_settings()
    async with user_tx(principal) as (tx, user):
        require_role(user, "landlord")
        await repo.get(tx, listing_id)
        row = await tx.fetchone(
            "select storage_path, thumb_path, confirmed from listing_photos where id = %s and listing_id = %s",
            (photo_id, listing_id),
        )
        if row is None:
            raise AppError(404, "not_found", "Photo not found.")
        if not row["confirmed"]:
            storage = get_storage()
            try:
                full, thumb = await storage.info(row["storage_path"]), await storage.info(row["thumb_path"])
            except ObjectNotFound as exc:
                raise AppError(409, "upload_incomplete", "The photo has not finished uploading.") from exc
            bad_type = any(i.content_type and not i.content_type.startswith("image/") for i in (full, thumb))
            if full.size > s.photo_max_bytes or thumb.size > THUMB_MAX_BYTES or bad_type:
                for p in (row["storage_path"], row["thumb_path"]):
                    await storage.delete(p)
                await tx.conn.execute("delete from listing_photos where id = %s", (photo_id,))
                raise AppError(422, "photo_rejected", "That file is not an image within the size limit.")
            await tx.conn.execute(
                """
                update listing_photos set confirmed = true, bytes = %s,
                  position = (select coalesce(max(position) + 1, 0) from listing_photos
                              where listing_id = %s and confirmed)
                where id = %s
                """,
                (full.size, listing_id, photo_id),
            )
        return ok(await _photos(tx, listing_id))


@router.put("/{listing_id}/photos/order", response_model=Ok[list[Photo]])
async def reorder(listing_id: UUID, body: PhotoOrder, principal: PrincipalDep) -> Ok[list[Photo]]:
    async with user_tx(principal) as (tx, user):
        require_role(user, "landlord")
        await repo.get(tx, listing_id)
        rows = await tx.fetchall("select id from listing_photos where listing_id = %s and confirmed", (listing_id,))
        if sorted(str(r["id"]) for r in rows) != sorted(str(i) for i in body.photo_ids):
            raise AppError(422, "order_mismatch", "Send every photo of this listing exactly once.")
        for pos, pid in enumerate(body.photo_ids):
            await tx.conn.execute("update listing_photos set position = %s where id = %s", (pos, pid))
        return ok(await _photos(tx, listing_id))


@router.delete("/{listing_id}/photos/{photo_id}", response_model=Ok[list[Photo]])
async def delete_photo(listing_id: UUID, photo_id: UUID, principal: PrincipalDep) -> Ok[list[Photo]]:
    async with user_tx(principal) as (tx, user):
        require_role(user, "landlord")
        listing = await repo.get(tx, listing_id)
        row = await tx.fetchone(
            "delete from listing_photos where id = %s and listing_id = %s returning storage_path, thumb_path",
            (photo_id, listing_id),
        )
        if row is None:
            raise AppError(404, "not_found", "Photo not found.")
        remaining = await tx.fetchone(
            "select count(*) as n from listing_photos where listing_id = %s and confirmed", (listing_id,))
        if listing.status == "published" and remaining is not None and remaining["n"] < PHOTOS_MIN:
            raise AppError(409, "photos_required",
                           f"A published listing needs at least {PHOTOS_MIN} photos. Pause it first.")
        storage = get_storage()
        paths = (row["storage_path"], row["thumb_path"])

        async def remove() -> None:
            for p in paths:
                await storage.delete(p)

        tx.after_commit(remove)  # only delete the files once the row is gone for good
        return ok(await _photos(tx, listing_id))
