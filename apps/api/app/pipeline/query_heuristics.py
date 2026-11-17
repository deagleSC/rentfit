"""Pattern parser for tenant queries: the fake model's `search_parse` (dev, tests, e2e).
Deliberately simple; the real model handles the long tail."""

from __future__ import annotations

import re
from typing import Any

from app.pipeline.normalise import _AMOUNT, amount

ORDINALS = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "4th": 4,
            "fifth": 5, "5th": 5, "last": 5}
AMENITY_WORDS = {"gym": "gym", "pool": "pool", "swimming": "pool", "lift": "lift", "elevator": "lift",
                 "power backup": "power_backup", "balcony": "balcony", "wifi": "wifi", "ac": "ac"}
SOFT_WORDS = ("quiet", "peaceful", "sunny", "spacious", "park", "green", "new", "airy")
_STOP_PLACE = r"(?=\s+(?:under|below|within|budget|for|with|and|near|by|max|upto|up to|around)\b|[,.?!]|$)"


def heuristic_search(message: str) -> dict[str, Any]:
    t = message.lower().replace(",", "")
    out: dict[str, Any] = {"intent": "search"}

    m = re.search(r"\b(?:the\s+)?(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|last)\s+(?:one|listing|flat)"
                  r"|#\s*(\d)\b|\bnumber\s+(\d)\b", t)
    if m:
        out["intent"] = "ask_about_result"
        out["result_number"] = ORDINALS.get(m.group(1) or "", 0) or int(m.group(2) or m.group(3))
        out["question"] = message.strip()
        if c := re.search(r"commute|how far|kitna door|distance", t):
            out["question"] = f"commute ({c.group(0)})"
        return out
    if re.fullmatch(r"\s*(hi|hello|hey|thanks|thank you|ok|okay)\W*", t):
        return {"intent": "chitchat"}

    if re.search(r"\b(start over|new search|reset)\b", t):
        out["new_search"] = True
    if re.search(r"\b(bangalore|bengaluru|blr)\b", t):
        out["city"] = "bangalore"
    elif re.search(r"\b(mumbai|bombay)\b", t):
        out["city"] = "mumbai"
    if bhks := re.findall(r"(\d)\s*-?\s*bhk", t):
        out["bhk"] = sorted({int(x) for x in bhks})
    if m := re.search(r"(?:under|below|upto|up to|max|within|budget(?: of| is)?|less than|<)\s*(?:rs\.?|₹)?\s*"
                      + _AMOUNT, t):
        out["rent_max"] = amount(m.group(1), m.group(2))
    if m := re.search(r"(?:above|over|more than|min(?:imum)?)\s*(?:rs\.?|₹)?\s*" + _AMOUNT, t):
        out["rent_min"] = amount(m.group(1), m.group(2))
    if "semi" in t:
        out["furnishing"] = ["semi"]
    elif re.search(r"\bfully furnished|\bfurnished\b", t) and "unfurnished" not in t:
        out["furnishing"] = ["full"]
    elif "unfurnished" in t:
        out["furnishing"] = ["unfurnished"]
    if re.search(r"\bfamil(?:y|ies)\b", t):
        out["tenant_type"] = "family"
    elif re.search(r"\bbachelors?\b", t):
        out["tenant_type"] = "bachelors"
    if re.search(r"\bpets?\b|\bdog\b|\bcat\b", t):
        out["pets"] = True
    if re.search(r"\bparking\b", t):
        out["parking"] = True
    if re.search(r"\bgated\b", t):
        out["gated"] = True
    if re.search(r"no brokerage|without broker|no broker", t):
        out["no_brokerage"] = True
    out["amenities"] = sorted({v for k, v in AMENITY_WORDS.items() if re.search(rf"\b{k}\b", t)})
    if m := re.search(r"(\d{1,3})\s*min(?:ute)?s?\s*(?:commute\s*)?(?:to|from)\s+([a-z][a-z .'-]{2,40}?)" + _STOP_PLACE,
                      t):
        out["commute_minutes"], out["commute_to"] = int(m.group(1)), m.group(2).strip()
    elif m := re.search(r"(?:commute|office|work)\s*(?:to|at|near)\s+([a-z][a-z .'-]{2,40}?)" + _STOP_PLACE, t):
        out["commute_to"] = m.group(1).strip()
    if m := re.search(r"\b(?:in|at|around)\s+([a-z][a-z .'-]{2,40}?)" + _STOP_PLACE, t):
        place = m.group(1).strip()
        if place not in ("bangalore", "bengaluru", "mumbai", "bombay") and not place.endswith("metro"):
            out["locality_names"] = [p.strip() for p in re.split(r"\s+or\s+|\s*/\s*", place) if p.strip()]
            out["replace_localities"] = "instead" in t
    out["soft"] = [w for w in SOFT_WORDS if re.search(rf"\b{w}\b", t)]
    out["semantic_query"] = message.strip()[:200]
    return out
