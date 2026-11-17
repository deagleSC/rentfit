"""OSM locality notes (backend plan §14.1): facts computed in code, turned into text by template.

No model writes these. Every number in the text is also in `facts`, so an answer citing a note
can be checked against the numbers it states.
"""

from __future__ import annotations

from typing import Any

CITY = {"bangalore": "Bengaluru", "mumbai": "Mumbai"}
COUNTED = (("schools", "school"), ("hospitals", "hospital"), ("parks", "park"), ("supermarkets", "supermarket"))


def _distance(m: float) -> str:
    return f"{round(m)} m" if m < 1000 else f"{m / 1000:.1f} km"


def _count(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def note_facts(counts: dict[str, int], nearest: dict[str, dict[str, Any] | None],
               tech_parks: list[dict[str, Any]]) -> dict[str, Any]:
    """The facts a note states. `nearest` maps poi kind → {name, metres} or None."""
    facts: dict[str, Any] = {k: int(counts.get(k, 0)) for k, _ in COUNTED}
    for kind, hit in nearest.items():
        if hit is not None:
            facts[f"nearest_{kind}"] = {"name": hit["name"], "metres": int(round(hit["metres"]))}
    facts["tech_parks_within_5km"] = [{"name": t["name"], "metres": int(round(t["metres"]))} for t in tech_parks]
    return facts


def note_text(name: str, city: str, facts: dict[str, Any]) -> str:
    s = [f"{name} is a locality in {CITY.get(city, city)}."]
    metro = facts.get("nearest_metro_station")
    if metro:
        s.append(f"The nearest metro station is {metro['name']}, about {_distance(metro['metres'])} "
                 "from the centre of the area.")
    else:
        s.append("There is no metro station mapped nearby.")
    rail = facts.get("nearest_rail_station")
    if rail and rail["metres"] <= 3000:
        s.append(f"{rail['name']} railway station is about {_distance(rail['metres'])} away.")
    counted = [_count(facts[k], w) for k, w in COUNTED if facts.get(k)]
    if counted:
        s.append("OpenStreetMap lists " + ", ".join(counted[:-1]) + (" and " if len(counted) > 1 else "")
                 + counted[-1] + " within the area.")
    hosp = facts.get("nearest_hospital")
    if hosp and not facts.get("hospitals"):
        s.append(f"The nearest hospital is {hosp['name']}, about {_distance(hosp['metres'])} away.")
    parks = facts.get("tech_parks_within_5km") or []
    if parks:
        named = ", ".join(f"{t['name']} ({_distance(t['metres'])})" for t in parks[:3])
        s.append(f"Office hubs within 5 km: {named}.")
    s.append("Source: OpenStreetMap contributors.")
    return " ".join(s)
