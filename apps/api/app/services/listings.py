"""Listing persistence (backend plan §8). All writes go through here; RLS scopes rows to the caller."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from app.core.db import Tx
from app.core.errors import AppError
from app.domain.listing import LatLng, Listing, ListingDraft
from app.domain.state_machine import Action, TransitionError, next_status

_COLUMNS = [f for f in ListingDraft.model_fields if f != "location"]

_SELECT = f"""
    select l.id, l.landlord_id, l.status, l.version, l.flags,
           {", ".join("l." + c for c in _COLUMNS)},
           case when l.location is null then null
                else json_build_object('lat', st_y(l.location::geometry), 'lng', st_x(l.location::geometry)) end
             as location,
           (select count(*) from listing_photos p where p.listing_id = l.id and p.confirmed) as photo_count
    from listings l
"""


def _to_listing(row: dict[str, Any]) -> Listing:
    data = dict(row)
    if isinstance(data.get("location"), str):
        data["location"] = json.loads(data["location"])
    return Listing.model_validate(data)


async def list_mine(tx: Tx, landlord_id: UUID) -> list[Listing]:
    rows = await tx.fetchall(_SELECT + " where l.landlord_id = %s order by l.updated_at desc", (landlord_id,))
    return [_to_listing(r) for r in rows]


async def get(tx: Tx, listing_id: UUID) -> Listing:
    row = await tx.fetchone(_SELECT + " where l.id = %s", (listing_id,))
    if row is None:
        raise AppError(404, "not_found", "Listing not found.")
    return _to_listing(row)


async def create_draft(tx: Tx, landlord_id: UUID, city: str | None = None) -> Listing:
    row = await tx.fetchone(
        "insert into listings (landlord_id, city) values (%s, %s) returning id", (landlord_id, city)
    )
    assert row is not None
    listing_id = row["id"]
    await tx.conn.execute(
        "insert into chats (owner_id, kind, listing_id, thread_id) values (%s, 'listing', %s, %s)",
        (landlord_id, listing_id, f"listing:{listing_id}"),
    )
    await tx.conn.execute(
        "insert into listing_events (listing_id, from_status, to_status, actor_id) values (%s, null, 'draft', %s)",
        (listing_id, landlord_id),
    )
    return await get(tx, listing_id)


async def save_draft(tx: Tx, listing: Listing, draft: ListingDraft, expected_version: int) -> Listing:
    """Write the draft fields if nobody else changed the listing since `expected_version` (409 otherwise)."""
    values = draft.model_dump(exclude={"location"})
    sets = ", ".join(f"{c} = %({c})s" for c in _COLUMNS)
    row = await tx.fetchone(
        f"update listings set {sets}, version = version + 1, updated_at = now() "
        "where id = %(id)s and version = %(version)s returning id",
        {**values, "id": listing.id, "version": expected_version},
    )
    if row is None:
        raise AppError(409, "version_conflict", "This listing changed since you opened it. Reload to see the latest.",
                       {"current_version": listing.version})
    return await get(tx, listing.id)


async def set_location(tx: Tx, listing: Listing, point: LatLng, locality_id: UUID, city: str,
                       mismatch: dict[str, Any] | None) -> Listing:
    flags = dict(listing.flags)
    if mismatch:
        flags["locality_mismatch"] = mismatch
    else:
        flags.pop("locality_mismatch", None)
    await tx.conn.execute(
        """
        update listings set location = st_point(%s, %s, 4326)::geography, city = %s,
               locality_id = coalesce(%s, locality_id), flags = %s,
               version = version + 1, updated_at = now()
        where id = %s
        """,
        (point.lng, point.lat, city, None if mismatch else locality_id, Jsonb(flags), listing.id),
    )
    return await get(tx, listing.id)


async def pin_in_city(tx: Tx, listing: Listing) -> bool:
    if listing.location is None or listing.city is None:
        return False
    row = await tx.fetchone(
        """
        select exists (select 1 from localities
                       where city = %s and st_dwithin(boundary, st_point(%s, %s, 4326)::geography, 500)) as ok
        """,
        (listing.city, listing.location.lng, listing.location.lat),
    )
    return bool(row and row["ok"])


async def transition(tx: Tx, listing: Listing, action: Action, actor_id: UUID, reason: str | None = None) -> Listing:
    try:
        target = next_status(listing.status, action)
    except TransitionError as exc:
        raise AppError(409, "invalid_transition", str(exc), {"status": listing.status}) from exc
    await tx.conn.execute(
        """
        update listings set status = %s, version = version + 1, updated_at = now(),
               published_at = case when %s = 'published' then coalesce(published_at, now()) else published_at end
        where id = %s
        """,
        (target, target, listing.id),
    )
    await tx.conn.execute(
        "insert into listing_events (listing_id, from_status, to_status, actor_id, reason) values (%s, %s, %s, %s, %s)",
        (listing.id, listing.status, target, actor_id, reason),
    )
    return await get(tx, listing.id)
