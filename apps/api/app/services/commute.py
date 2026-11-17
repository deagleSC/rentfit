"""Commute minutes from listings to one place (backend plan §13.1).

- ORS Matrix API: one request for up to 50 origins × 1 destination, when ORS_API_KEY is set.
- Haversine estimate: straight-line km × 1.4 ÷ a peak-hour city speed. Used without a key, on 429
  (quota), on errors, or when ORS takes over 3 s. Every answer says which produced it.
- Cached in `commute_cache` by (geohash7 of the origin, poi, mode) for 30 days.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

import httpx

from app.core.config import get_settings
from app.core.db import Tx

log = logging.getLogger("rentfit.commute")

Mode = Literal["car", "two_wheeler", "walk"]
Provider = Literal["ors", "haversine"]
ORS_URL = "https://api.openrouteservice.org/v2/matrix/{profile}"
ORS_PROFILE: dict[str, str] = {"car": "driving-car", "two_wheeler": "cycling-regular", "walk": "foot-walking"}
# Peak-hour km/h; two-wheelers move faster than cars in Indian city traffic.
SPEED: dict[str, dict[str, float]] = {
    "bangalore": {"car": 17.0, "two_wheeler": 22.0, "walk": 4.5},
    "mumbai": {"car": 19.0, "two_wheeler": 24.0, "walk": 4.5},
}
DETOUR = 1.4
ORS_TIMEOUT_S = 3.0
_B32 = "0123456789bcdefghjkmnpqrstuvwxyz"


@dataclass
class Minutes:
    minutes: int
    provider: Provider


def geohash(lat: float, lng: float, precision: int = 7) -> str:
    lat_r, lng_r = [-90.0, 90.0], [-180.0, 180.0]
    out: list[str] = []
    bits, ch, even = 0, 0, True
    while len(out) < precision:
        rng, v = (lng_r, lng) if even else (lat_r, lat)
        mid = (rng[0] + rng[1]) / 2
        ch = (ch << 1) | (v > mid)
        rng[0 if v > mid else 1] = mid
        even, bits = not even, bits + 1
        if bits == 5:
            out.append(_B32[ch])
            bits, ch = 0, 0
    return "".join(out)


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def estimate(km: float, city: str, mode: Mode) -> int:
    speed = SPEED.get(city, SPEED["bangalore"])[mode]
    return max(1, round(km * DETOUR / speed * 60))


async def _ors(origins: list[tuple[float, float]], dest: tuple[float, float], mode: Mode) -> list[int] | None:
    key = get_settings().ors_api_key
    if not key:
        return None
    locations = [[lng, lat] for lat, lng in origins] + [[dest[1], dest[0]]]
    try:
        async with httpx.AsyncClient(timeout=ORS_TIMEOUT_S) as client:
            res = await client.post(
                ORS_URL.format(profile=ORS_PROFILE[mode]),
                headers={"Authorization": key},
                json={"locations": locations, "sources": list(range(len(origins))),
                      "destinations": [len(origins)], "metrics": ["duration"]},
            )
        if res.status_code != 200:
            log.info("ORS matrix returned %s; using estimates", res.status_code)
            return None
        durations = res.json()["durations"]
        return [round(row[0] / 60) if row and row[0] is not None else -1 for row in durations]
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        log.info("ORS matrix failed (%s); using estimates", exc)
        return None


async def minutes_to(tx: Tx, origins: dict[UUID, tuple[float, float]], poi_id: UUID, mode: Mode = "car"
                     ) -> dict[UUID, Minutes]:
    """Minutes from each origin (listing id → (lat, lng)) to a POI. Runs its cache writes as system."""
    poi = await tx.fetchone(
        "select city, st_y(location::geometry) as lat, st_x(location::geometry) as lng from pois where id = %s",
        (poi_id,))
    if poi is None or not origins:
        return {}
    hashes = {lid: geohash(lat, lng) for lid, (lat, lng) in origins.items()}
    out: dict[UUID, Minutes] = {}
    async with tx.as_system():
        rows = await tx.fetchall(
            "select origin_geohash, minutes, provider from commute_cache"
            " where poi_id = %s and mode = %s and origin_geohash = any(%s) and expires_at > now()",
            (poi_id, mode, list(set(hashes.values()))))
    cached = {r["origin_geohash"]: Minutes(round(r["minutes"]), r["provider"]) for r in rows}
    todo = [lid for lid, h in hashes.items() if h not in cached]
    for lid, h in hashes.items():
        if h in cached:
            out[lid] = cached[h]
    if todo:
        ors = await _ors([origins[i] for i in todo], (poi["lat"], poi["lng"]), mode)
        fresh: dict[UUID, Minutes] = {}
        for n, lid in enumerate(todo):
            if ors is not None and ors[n] >= 0:
                fresh[lid] = Minutes(ors[n], "ors")
            else:
                lat, lng = origins[lid]
                fresh[lid] = Minutes(estimate(haversine_km(lat, lng, poi["lat"], poi["lng"]), poi["city"], mode),
                                     "haversine")
        async with tx.as_system(), tx.conn.cursor() as cur:
            await cur.executemany(
                """
                insert into commute_cache (origin_geohash, poi_id, mode, minutes, provider, expires_at)
                values (%s, %s, %s, %s, %s, now() + interval '30 days')
                on conflict (origin_geohash, poi_id, mode) do update
                  set minutes = excluded.minutes, provider = excluded.provider, expires_at = excluded.expires_at
                """,
                [(hashes[lid], poi_id, mode, m.minutes, m.provider) for lid, m in fresh.items()],
            )
        out.update(fresh)
    return out
