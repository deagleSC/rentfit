"""Landlord listing endpoints (backend plan §7.2): CRUD, patches, location, status transitions."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Header
from pydantic import BaseModel

from app.core.auth import PrincipalDep, require_role, user_tx
from app.core.errors import ERROR_RESPONSES, AppError, Ok, ok
from app.domain.listing import LatLng, Listing, ListingDraft
from app.domain.listing_patches import Change, Patch, PatchError, apply_patches
from app.domain.state_machine import Action, check_publish
from app.services import geo
from app.services import listings as repo

router = APIRouter(prefix="/v1/landlord/listings", tags=["landlord"], responses=ERROR_RESPONSES)


class ListingCreate(BaseModel):
    city: str | None = None


class PatchResult(BaseModel):
    listing: Listing
    changes: list[Change]


class LocationResult(BaseModel):
    listing: Listing
    locality_name: str
    mismatch: bool


CONFLICT = "This listing changed since you opened it. Reload to see the latest."


def as_draft(listing: Listing) -> ListingDraft:
    return ListingDraft.model_validate(listing.model_dump(include=set(ListingDraft.model_fields)))


def _if_match(value: str | None) -> int:
    if value is None:
        raise AppError(428, "version_required", "Send the listing version in If-Match.")
    try:
        return int(value.strip('"W/ '))
    except ValueError as exc:
        raise AppError(400, "bad_if_match", "If-Match must be the listing version number.") from exc


@router.get("", response_model=Ok[list[Listing]])
async def list_listings(principal: PrincipalDep) -> Ok[list[Listing]]:
    async with user_tx(principal) as (tx, user):
        require_role(user, "landlord")
        return ok(await repo.list_mine(tx, user.user_id))


@router.post("", response_model=Ok[Listing], status_code=201)
async def create_listing(principal: PrincipalDep, body: ListingCreate | None = None) -> Ok[Listing]:
    async with user_tx(principal) as (tx, user):
        require_role(user, "landlord")
        city = body.city if body else None
        if city and await tx.fetchone("select 1 from cities where slug = %s", (city,)) is None:
            raise AppError(422, "unknown_city", "That city is not supported.")
        return ok(await repo.create_draft(tx, user.user_id, city))


@router.get("/{listing_id}", response_model=Ok[Listing])
async def get_listing(listing_id: UUID, principal: PrincipalDep) -> Ok[Listing]:
    async with user_tx(principal) as (tx, user):
        require_role(user, "landlord")
        return ok(await repo.get(tx, listing_id))


@router.patch("/{listing_id}", response_model=Ok[PatchResult])
async def patch_listing(
    listing_id: UUID,
    patches: list[Patch],
    principal: PrincipalDep,
    if_match: Annotated[str | None, Header()] = None,
) -> Ok[PatchResult]:
    """Apply typed edits. The same function handles chat edits (backend plan §8.2)."""
    expected = _if_match(if_match)
    async with user_tx(principal) as (tx, user):
        require_role(user, "landlord")
        listing = await repo.get(tx, listing_id)
        if listing.status == "let":
            raise AppError(409, "listing_closed", "This listing is marked as let and can no longer be edited.")
        if listing.version != expected:
            raise AppError(409, "version_conflict", CONFLICT, {"current_version": listing.version})
        try:
            draft, changes = apply_patches(as_draft(listing), patches)
        except PatchError as exc:
            raise AppError(422, "invalid_patch", str(exc), {"errors": exc.details}) from exc
        await _check_refs(tx, draft)
        updated = await repo.save_draft(tx, listing, draft, expected) if changes else listing
        return ok(PatchResult(listing=updated, changes=changes))


async def _check_refs(tx: Any, draft: ListingDraft) -> None:
    if draft.city and await tx.fetchone("select 1 from cities where slug = %s", (draft.city,)) is None:
        raise AppError(422, "unknown_city", "That city is not supported.")
    if draft.locality_id:
        row = await tx.fetchone("select city from localities where id = %s", (draft.locality_id,))
        if row is None:
            raise AppError(422, "unknown_locality", "That locality is not known.")
        if draft.city and row["city"] != draft.city:
            raise AppError(422, "locality_city_mismatch", "That locality is in a different city.")


@router.put("/{listing_id}/location", response_model=Ok[LocationResult])
async def set_location(listing_id: UUID, point: LatLng, principal: PrincipalDep) -> Ok[LocationResult]:
    """Drop a pin: look up the locality; if the landlord already named a different one, flag it."""
    async with user_tx(principal) as (tx, user):
        require_role(user, "landlord")
        listing = await repo.get(tx, listing_id)
        hit = await geo.locality_for(tx, point.lat, point.lng)
        if hit is None:
            raise AppError(422, "outside_coverage", "That pin is outside the cities RentFit covers.")
        mismatch = None
        if listing.locality_id and listing.locality_id != hit.locality_id:
            mismatch = {"typed": str(listing.locality_id), "pin": str(hit.locality_id), "pin_name": hit.name}
        updated = await repo.set_location(tx, listing, point, hit.locality_id, hit.city, mismatch)
        return ok(LocationResult(listing=updated, locality_name=hit.name, mismatch=mismatch is not None))


async def _transition(listing_id: UUID, principal: Any, action: Action) -> Ok[Listing]:
    async with user_tx(principal) as (tx, user):
        require_role(user, "landlord")
        listing = await repo.get(tx, listing_id)
        if action == "publish":
            reasons = check_publish(listing, listing.photo_count, pin_in_city=await repo.pin_in_city(tx, listing))
            if reasons:
                raise AppError(422, "not_ready", "This listing is not ready to publish yet.", {"reasons": reasons})
        return ok(await repo.transition(tx, listing, action, user.user_id))


@router.post("/{listing_id}/publish", response_model=Ok[Listing])
async def publish(listing_id: UUID, principal: PrincipalDep) -> Ok[Listing]:
    return await _transition(listing_id, principal, "publish")


@router.post("/{listing_id}/pause", response_model=Ok[Listing])
async def pause(listing_id: UUID, principal: PrincipalDep) -> Ok[Listing]:
    return await _transition(listing_id, principal, "pause")


@router.post("/{listing_id}/resume", response_model=Ok[Listing])
async def resume(listing_id: UUID, principal: PrincipalDep) -> Ok[Listing]:
    return await _transition(listing_id, principal, "resume")


@router.post("/{listing_id}/let", response_model=Ok[Listing])
async def mark_let(listing_id: UUID, principal: PrincipalDep) -> Ok[Listing]:
    return await _transition(listing_id, principal, "let")
