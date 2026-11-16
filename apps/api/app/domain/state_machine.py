"""Listing status transitions and publish checks (backend plan §8.3, §12).

    draft ──publish──▶ published ──pause──▶ paused ──resume──▶ published
                          └──let──▶ let

`check_publish` is plain code (no model): screening is out of scope for v1.
"""

from __future__ import annotations

from typing import Literal

from app.domain.listing import PHOTOS_MAX, PHOTOS_MIN, ListingDraft, Status, missing_fields
from app.pipeline.redact import has_contacts

Action = Literal["publish", "pause", "resume", "let"]

TRANSITIONS: dict[Action, tuple[tuple[Status, ...], Status]] = {
    "publish": (("draft",), "published"),
    "pause": (("published",), "paused"),
    "resume": (("paused",), "published"),
    "let": (("published", "paused"), "let"),
}


class TransitionError(ValueError):
    pass


def next_status(current: Status, action: Action) -> Status:
    allowed, target = TRANSITIONS[action]
    if current not in allowed:
        raise TransitionError(f"Cannot {action} a listing that is {current}.")
    return target


def check_publish(draft: ListingDraft, photo_count: int, *, pin_in_city: bool) -> list[str]:
    """Reasons the listing cannot be published yet; empty means it can."""
    reasons = [f"missing:{f}" for f in missing_fields(draft)]
    if photo_count < PHOTOS_MIN:
        reasons.append(f"photos:at_least_{PHOTOS_MIN}")
    if photo_count > PHOTOS_MAX:
        reasons.append(f"photos:at_most_{PHOTOS_MAX}")
    if draft.location is not None and not pin_in_city:
        reasons.append("location:outside_city")
    if draft.rent is not None and draft.rent < 2000:
        reasons.append("rent:too_low")  # almost always a typo (a missing zero)
    if draft.description and has_contacts(draft.description):
        reasons.append("description:contains_contact_details")
    return reasons
