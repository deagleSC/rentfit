"""Rent suggestion from comparable published listings (backend plan §11.1). Plain code, no model:
percentiles are computed here and the wording is a template, so every number is a computed value.

Comparables: published, same city and bhk, within 1.5 km of the pin (widened to 3 km if fewer than
5), furnishing within one step, published in the last 180 days. Other landlords' listings are read in
system context; only their rent and id leave this function. With fewer than 5 comparables, the
locality's median rent (a hand-set estimate) is used and labelled as such.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.core.db import Tx
from app.domain.listing import Listing

MIN_COMPARABLES = 5
RADII_M = (1500, 3000)
FURNISHING_STEPS = {"unfurnished": ["unfurnished", "semi"], "semi": ["unfurnished", "semi", "full"],
                    "full": ["semi", "full"]}


class RentSuggestion(BaseModel):
    basis: Literal["comparables", "locality_estimate", "not_enough_info"]
    p25: int | None = None
    p50: int | None = None
    p75: int | None = None
    count: int = 0
    radius_m: int | None = None
    comparable_ids: list[UUID] = []
    position: Literal["below", "within", "above"] | None = None  # the listing's rent vs p25–p75
    text: str


def percentile(sorted_values: list[int], q: float) -> int:
    """Linear interpolation between closest ranks (numpy's default)."""
    if not sorted_values:
        raise ValueError("empty")
    k = (len(sorted_values) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(sorted_values) - 1)
    return int(round(sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (k - lo), -2))


def _position(rent: int | None, p25: int, p75: int) -> Literal["below", "within", "above"] | None:
    if rent is None:
        return None
    return "below" if rent < p25 else "above" if rent > p75 else "within"


def _inr(v: int) -> str:
    return f"₹{v:,}"


async def suggest(tx: Tx, listing: Listing) -> RentSuggestion:
    if listing.bhk is None or listing.location is None or listing.city is None:
        return RentSuggestion(basis="not_enough_info",
                              text="Add the BHK and drop a pin to see what similar flats nearby rent for.")
    furnishing = FURNISHING_STEPS.get(listing.furnishing or "", ["unfurnished", "semi", "full"])
    async with tx.as_system():
        for radius in RADII_M:
            rows = await tx.fetchall(
                """
                select id, rent from listings
                where status = 'published' and id <> %(id)s and city = %(city)s and bhk = %(bhk)s
                  and furnishing = any(%(furn)s) and rent is not null
                  and published_at > now() - interval '180 days'
                  and st_dwithin(location, st_point(%(lng)s, %(lat)s, 4326)::geography, %(r)s)
                order by rent
                """,
                {"id": listing.id, "city": listing.city, "bhk": listing.bhk, "furn": furnishing,
                 "lng": listing.location.lng, "lat": listing.location.lat, "r": radius},
            )
            if len(rows) >= MIN_COMPARABLES:
                rents = [int(r["rent"]) for r in rows]
                p25, p50, p75 = (percentile(rents, q) for q in (0.25, 0.5, 0.75))
                km = radius / 1000
                return RentSuggestion(
                    basis="comparables", p25=p25, p50=p50, p75=p75, count=len(rows), radius_m=radius,
                    comparable_ids=[r["id"] for r in rows], position=_position(listing.rent, p25, p75),
                    text=(f"{len(rows)} similar {listing.bhk} BHK flats within {km:g} km rent for "
                          f"{_inr(p25)}–{_inr(p75)} (median {_inr(p50)})."),
                )
        row = await tx.fetchone(
            "select name, median_rent ->> %s as median from localities where id = %s",
            (str(listing.bhk), listing.locality_id),
        ) if listing.locality_id else None
    if row and row["median"]:
        median = int(row["median"])
        p25, p75 = int(round(median * 0.85, -2)), int(round(median * 1.15, -2))
        return RentSuggestion(
            basis="locality_estimate", p25=p25, p50=median, p75=p75, position=_position(listing.rent, p25, p75),
            text=(f"Not enough similar listings yet. A typical {listing.bhk} BHK in {row['name']} rents for about "
                  f"{_inr(p25)}–{_inr(p75)} (RentFit estimate)."),
        )
    return RentSuggestion(basis="not_enough_info", text="Not enough similar listings nearby to suggest a rent yet.")
