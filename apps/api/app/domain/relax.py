"""Relax ladder (backend plan §13): with too few results, loosen one constraint at a time and say
what changed. Pure: the caller supplies adjacent localities (a DB lookup) and re-runs the search."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from app.domain.filters import SearchFilters

MIN_RESULTS = 5


@dataclass
class Relaxation:
    step: str
    message: str


def _inr(v: int) -> str:
    return f"₹{v:,}"


def steps(f: SearchFilters, adjacent: Callable[[list[UUID]], list[tuple[UUID, str]]],
          skip: frozenset[str] | set[str] = frozenset()
          ) -> list[tuple[SearchFilters, Relaxation]]:
    """Every applicable loosening, each applied on top of the previous ones, in ladder order.
    Fields in `skip` (changed by the tenant's latest message) are never loosened."""
    out: list[tuple[SearchFilters, Relaxation]] = []
    cur = f
    if cur.rent_max is not None and "rent_max" not in skip:
        new = int(round(cur.rent_max * 1.1, -2))
        cur = cur.model_copy(update={"rent_max": new})
        out.append((cur, Relaxation("budget", f"raised the budget to {_inr(new)}")))
    if cur.locality_ids and "locality_ids" not in skip:
        extra = [(i, n) for i, n in adjacent(cur.locality_ids) if i not in cur.locality_ids]
        if extra:
            cur = cur.model_copy(update={"locality_ids": cur.locality_ids + [i for i, _ in extra],
                                         "locality_names": cur.locality_names + [n for _, n in extra]})
            names = ", ".join(n for _, n in extra[:4]) + (" and more" if len(extra) > 4 else "")
            out.append((cur, Relaxation("adjacent", f"added nearby areas ({names})")))
    if cur.commute is not None and "commute" not in skip:
        c = cur.commute.model_copy(update={"max_minutes": cur.commute.max_minutes + 10})
        cur = cur.model_copy(update={"commute": c})
        out.append((cur, Relaxation("commute", f"allowed up to {c.max_minutes} min to {c.poi_name}")))
    if cur.near_metro_m and cur.near_metro_m < 2000 and "near_metro_m" not in skip:
        cur = cur.model_copy(update={"near_metro_m": 2000})
        out.append((cur, Relaxation("metro", "widened the metro distance to 2 km")))
    if cur.amenities and "amenities" not in skip:
        dropped = cur.amenities[-1]
        cur = cur.model_copy(update={"amenities": cur.amenities[:-1]})
        out.append((cur, Relaxation("amenity", f"dropped the {dropped.replace('_', ' ')} requirement")))
    return out
