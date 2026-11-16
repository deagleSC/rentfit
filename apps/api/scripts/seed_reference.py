"""Load cities, localities and POIs from scripts/seed_data/ into the database (backend plan §14.1).

    uv run python -m scripts.seed_reference

Idempotent (upserts by slug / osm_id). Connects as rentfit_api with system claims, so RLS applies.
Median rents are hand-set estimates: a city base per bhk times a locality tier (no open source
exists); they are only used as the fallback for rent suggestions.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

import psycopg

from scripts.setup_roles import load_env

DATA = Path(__file__).resolve().parent / "seed_data"

# Monthly rent in INR for a mid-tier locality, by bhk.
CITY_BASE = {
    "bangalore": {"1": 16000, "2": 26000, "3": 38000},
    "mumbai": {"1": 30000, "2": 52000, "3": 85000},
}
PREMIUM = {
    "bangalore": {"koramangala", "indiranagar", "hsr layout", "jayanagar", "whitefield", "malleswaram",
                  "sadashivanagar", "frazer town", "richmond town", "bellandur", "domlur", "hebbal"},
    "mumbai": {"bandra", "bandra west", "khar", "juhu", "worli", "powai", "lower parel", "colaba", "andheri west",
               "santacruz", "prabhadevi", "dadar", "malabar hill", "cuffe parade"},
}
TIER = {"premium": 1.45, "mid": 1.0}


def median_rent(city: str, name: str) -> dict[str, int]:
    mult = TIER["premium"] if name.lower() in PREMIUM[city] else TIER["mid"]
    return {bhk: int(round(v * mult, -3)) for bhk, v in CITY_BASE[city].items()}


def dedupe_pois(features: list[dict[str, Any]], radius_m: float = 300) -> list[dict[str, Any]]:
    """Merge POIs of the same kind within `radius_m` (e.g. each building of a tech-park campus),
    keeping the shortest name, which is usually the campus name."""
    kept: list[dict[str, Any]] = []
    for f in sorted(features, key=lambda f: len(f["properties"]["name"])):
        name, kind = f["properties"]["name"].lower(), f["properties"]["kind"]
        if any(x in name for x in ("(u/c)", "society", "residency", "substation", "foundation", "infosystems",
                                   "=>", "dharmashala")) or name.startswith("bus "):  # not workplaces
            continue
        r = 800 if kind == "tech_park" else radius_m  # tech-park campuses spread wide
        lng, lat = f["geometry"]["coordinates"]
        near = any(
            k["properties"]["kind"] == kind and _metres(lng, lat, *k["geometry"]["coordinates"]) < r
            for k in kept
        )
        if not near:
            kept.append(f)
    return kept


def _metres(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    dx = (lng2 - lng1) * 111_320 * math.cos(math.radians((lat1 + lat2) / 2))
    dy = (lat2 - lat1) * 110_574
    return math.hypot(dx, dy)


def main() -> None:
    url = os.environ.get("DATABASE_URL") or load_env()["DATABASE_URL"]
    with psycopg.connect(url, prepare_threshold=None) as conn:
        conn.execute("""select set_config('app.claims', '{"role":"system"}', true)""")
        for d in sorted(p for p in DATA.iterdir() if p.is_dir()):
            city = json.loads((d / "city.json").read_text())
            slug = city["slug"]
            lng, lat = city["center"]
            conn.execute(
                """insert into cities (slug, name, center) values (%s, %s, st_point(%s, %s, 4326)::geography)
                   on conflict (slug) do update set name = excluded.name, center = excluded.center""",
                (slug, city["name"], lng, lat),
            )
            locs = json.loads((d / "localities.geojson").read_text())["features"]
            for f in locs:
                p = f["properties"]
                conn.execute(
                    """insert into localities (city, name, osm_id, boundary, centroid, median_rent, facts)
                       values (%s, %s, %s, st_geomfromgeojson(%s)::geography,
                               st_point(%s, %s, 4326)::geography, %s, %s)
                       on conflict (osm_id) do update set name = excluded.name, boundary = excluded.boundary,
                         centroid = excluded.centroid, median_rent = excluded.median_rent, facts = excluded.facts""",
                    (slug, p["name"], p["osm_id"], json.dumps(f["geometry"]), *p["centroid"],
                     json.dumps(median_rent(slug, p["name"])), json.dumps(p["facts"])),
                )
            pois = dedupe_pois(json.loads((d / "pois.geojson").read_text())["features"])
            for f in pois:
                p = f["properties"]
                conn.execute(
                    """insert into pois (city, name, kind, osm_id, location)
                       values (%s, %s, %s, %s, st_point(%s, %s, 4326)::geography)
                       on conflict (osm_id) do update set name = excluded.name, kind = excluded.kind,
                         location = excluded.location""",
                    (slug, p["name"], p["kind"], p["osm_id"], *f["geometry"]["coordinates"]),
                )
            print(f"{slug}: {len(locs)} localities, {len(pois)} pois")
        conn.commit()


if __name__ == "__main__":
    main()
