"""Fetch reference data from OpenStreetMap once and write it to scripts/seed_data/ (backend plan §14.1).

    uv run python scripts/fetch_osm.py [bangalore mumbai kolkata]

Localities: OSM `place=suburb` nodes (the names renters use). OSM admin boundaries are inconsistent
across the three cities (Bengaluru wards are villages, Mumbai/Kolkata have few polygons), so each
locality's polygon is its Voronoi cell, clipped to 3 km around the points and to the city bbox:
every pin then maps to the nearest named locality, with no gaps.

POIs: metro stations, suburban rail stations, hospitals, colleges, tech parks.
Facts (for locality notes, Phase 2): counts of schools, parks, supermarkets per locality.

Output is committed. Data © OpenStreetMap contributors, ODbL.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from shapely import MultiPoint, MultiPolygon, Point, Polygon, box
from shapely.geometry import mapping, shape
from shapely.ops import unary_union, voronoi_diagram

OVERPASS = "https://overpass-api.de/api/interpreter"
OUT = Path(__file__).resolve().parent / "seed_data"
HEADERS = {"User-Agent": "rentfit-seed/0.1"}

# (south, west, north, east)
CITIES: dict[str, dict[str, Any]] = {
    "bangalore": {"name": "Bengaluru", "bbox": (12.83, 77.45, 13.14, 77.78), "center": (77.5946, 12.9716)},
    "mumbai": {"name": "Mumbai", "bbox": (18.89, 72.77, 19.28, 72.99), "center": (72.8777, 19.0760)},
    "kolkata": {"name": "Kolkata", "bbox": (22.45, 88.25, 22.66, 88.45), "center": (88.3639, 22.5726)},
}

MIN_SPACING_DEG = 0.006  # ~650 m: merge suburb nodes closer than this
CLIP_BUFFER_DEG = 0.027  # ~3 km around the points
TECH_PARK = re.compile(r"tech ?park|it ?park|(^| )sez( |$)|tech ?village|business ?park|software ?park|"
                       r"technology ?park|knowledge ?park|infopark|cyber ?city|manyata|bagmane|mindspace|"
                       r"ecospace|ecoworld|electronic city phase|global village|nirlon|seepz|sector v", re.I)

# Rental localities that OSM tags as neighbourhood/quarter/village/town rather than suburb.
EXTRA_LOCALITIES: dict[str, list[str]] = {
    "bangalore": ["Electronic City", "Electronics City", "Sarjapur", "Sarjapura", "Thanisandra", "Bellandur",
                  "Brookefield", "Kundalahalli", "Bommanahalli", "Hulimavu", "Begur", "Bannerghatta",
                  "Kaggadasapura", "Nagavara", "Hennur", "Yelahanka New Town", "Sahakar Nagar", "RR Nagar",
                  "Rajarajeshwari Nagar", "Varthur", "Panathur", "Domlur", "Ejipura", "Wilson Garden"],
    "mumbai": ["Powai", "Andheri West", "Andheri East", "Bandra West", "Bandra East", "Lower Parel", "Worli",
               "Goregaon East", "Goregaon West", "Malad West", "Malad East", "Kandivali West", "Kandivali East",
               "Borivali West", "Borivali East", "Chembur", "Ghatkopar", "Mulund", "Vikhroli", "Kurla", "Juhu",
               "Santacruz", "Khar", "Dadar", "Matunga", "Sion", "Colaba", "Bhandup", "Jogeshwari", "Versova"],
    "kolkata": ["Salt Lake", "Bidhannagar", "New Town", "Rajarhat", "Ballygunge", "Alipore", "Tollygunge",
                "Behala", "Garia", "Jadavpur", "Dum Dum", "Lake Town", "Gariahat", "Park Circus", "Kasba",
                "Bhowanipore", "Howrah", "Sector V"],
}


def overpass(query: str) -> list[dict[str, Any]]:
    for attempt in range(5):
        res = httpx.post(OVERPASS, data={"data": query}, headers=HEADERS, timeout=180)
        if res.status_code == 200:
            return list(res.json()["elements"])
        time.sleep(10 * (attempt + 1))
    res.raise_for_status()
    return []


def lnglat(el: dict[str, Any]) -> tuple[float, float]:
    if "lon" in el:
        return float(el["lon"]), float(el["lat"])
    return float(el["center"]["lon"]), float(el["center"]["lat"])


def osm_key(el: dict[str, Any]) -> int:
    """Node ids as-is, ways negative, relations offset: one bigint key across element types."""
    i = int(el["id"])
    return {"node": i, "way": -i, "relation": -(10**12 + i)}[str(el["type"])]


def name_of(el: dict[str, Any]) -> str | None:
    tags = el.get("tags", {})
    return tags.get("name:en") or tags.get("name")


def fetch_city(slug: str) -> None:
    cfg = CITIES[slug]
    s, w, n, e = cfg["bbox"]
    bb = f"({s},{w},{n},{e})"
    city_box = box(w, s, e, n)

    # ---- localities
    extra = "|".join(EXTRA_LOCALITIES.get(slug, []))
    nodes = overpass(f"[out:json][timeout:120];(node[place=suburb]{bb};"
                     f'node[place~"^(neighbourhood|quarter|village|town)$"][name~"^({extra})$",i]{bb};);out;')
    points: list[tuple[str, int, Point]] = []
    for el in sorted(nodes, key=lambda x: x["id"]):
        nm = name_of(el)
        if not nm or not re.fullmatch(r"[A-Za-z0-9 .'()-]+", nm):
            continue
        p = Point(lnglat(el))
        if any(p.distance(q) < MIN_SPACING_DEG or nm.lower() == m.lower() for m, _, q in points):
            continue
        points.append((nm, int(el["id"]), p))

    hull = unary_union([p for _, _, p in points]).buffer(CLIP_BUFFER_DEG).intersection(city_box)
    cells = voronoi_diagram(MultiPoint([p for _, _, p in points]), envelope=city_box)
    features = []
    for nm, osm_id, p in points:
        cell = next(c for c in cells.geoms if c.contains(p))
        geom = cell.intersection(hull).simplify(0.0002)
        if isinstance(geom, Polygon):
            geom = MultiPolygon([geom])
        features.append({"type": "Feature", "geometry": mapping(geom),
                         "properties": {"name": nm, "osm_id": osm_id, "centroid": [p.x, p.y], "facts": {}}})

    # ---- facts: counts per locality
    fact_queries = {
        "schools": "nwr[amenity=school]",
        "parks": "nwr[leisure=park]",
        "supermarkets": "nwr[shop=supermarket]",
        "hospitals": "nwr[amenity=hospital]",
    }
    shapes = [(f, shape(f["geometry"])) for f in features]
    for key, sel in fact_queries.items():
        time.sleep(3)
        els = overpass(f"[out:json][timeout:120];{sel}{bb};out center;")
        for f, _ in shapes:
            f["properties"]["facts"][key] = 0
        for el in els:
            pt = Point(lnglat(el))
            for f, shp in shapes:
                if shp.contains(pt):
                    f["properties"]["facts"][key] += 1
                    break

    # ---- POIs
    time.sleep(3)
    poi_query = f"""[out:json][timeout:180];
    (node[railway=station][station=subway]{bb};node[railway=station][subway=yes]{bb};
     node[railway=station][network~"Metro",i]{bb};)->.metro;
    .metro out;
    node[railway=station]{bb}->.rail;
    (.rail; - .metro;)->.suburban;
    .suburban out;
    nwr[amenity=hospital][name]{bb};out center;
    nwr[amenity=university][name]{bb};out center;
    nwr[name~"{TECH_PARK.pattern}",i][~"^(landuse|office|building)$"~"."]{bb};out center;
    """
    metro_ids: set[int] = set()
    pois: dict[tuple[str, str], dict[str, Any]] = {}
    els = overpass(poi_query)
    for el in els:
        nm = name_of(el)
        tags = el.get("tags", {})
        if not nm:
            continue
        if tags.get("railway") == "station":
            is_metro = (tags.get("station") == "subway" or tags.get("subway") == "yes"
                        or "metro" in tags.get("network", "").lower())
            if is_metro:
                metro_ids.add(el["id"])
                kind = "metro_station"
            else:
                kind = "rail_station"
        elif tags.get("amenity") == "hospital":
            if el["type"] == "node":  # clinics are mostly nodes; mapped areas are the larger hospitals
                continue
            kind = "hospital"
        elif tags.get("amenity") == "university":
            kind = "college"
        elif TECH_PARK.search(nm) and el["type"] != "node":
            kind = "tech_park"
        else:
            continue
        key = (kind, nm.lower())
        if key in pois:
            continue
        lng, lat = lnglat(el)
        pois[key] = {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lng, lat]},
                     "properties": {"name": nm, "kind": kind, "osm_id": osm_key(el)}}

    d = OUT / slug
    d.mkdir(parents=True, exist_ok=True)
    meta = {"slug": slug, "name": cfg["name"], "center": list(cfg["center"]), "bbox": list(cfg["bbox"])}
    (d / "city.json").write_text(json.dumps(meta, indent=2) + "\n")
    (d / "localities.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": features}) + "\n")
    (d / "pois.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": list(pois.values())}) + "\n")
    kinds: dict[str, int] = {}
    for p in pois.values():
        kinds[p["properties"]["kind"]] = kinds.get(p["properties"]["kind"], 0) + 1
    print(f"{slug}: {len(features)} localities, pois {kinds}")


if __name__ == "__main__":
    for slug in sys.argv[1:] or list(CITIES):
        fetch_city(slug)
        time.sleep(5)
