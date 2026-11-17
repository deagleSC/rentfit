"""Listing and locality text → chunks for embedding and full-text search (backend plan §9).

Chunk 0 of a listing is a plain-English summary built from its fields, so structured facts
("semi-furnished", "near metro" via the locality, "bachelors") are searchable even when the
landlord wrote no description. The title and description follow, split on sentence boundaries.
Contacts are stripped again here: chunks are shown back to tenants and sent to the embedder.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from app.pipeline.redact import strip_contacts

MAX_CHARS = 800
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")

FURNISHING = {"unfurnished": "unfurnished", "semi": "semi-furnished", "full": "fully furnished"}
TENANTS = {"any": "open to families and bachelors", "family": "for families", "bachelors": "for bachelors"}
PARKING = {"bike": "bike parking", "car": "car parking", "both": "car and bike parking"}
CITY = {"bangalore": "Bengaluru (Bangalore)", "mumbai": "Mumbai"}


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def split(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    """Greedy sentence packing; a single over-long sentence is cut at a word boundary."""
    out: list[str] = []
    cur = ""
    for sent in (s.strip() for s in _SENTENCE.split(text) if s and s.strip()):
        while len(sent) > max_chars:
            cut = sent.rfind(" ", 0, max_chars)
            cut = cut if cut > max_chars // 2 else max_chars
            if cur:
                out.append(cur)
                cur = ""
            out.append(sent[:cut].strip())
            sent = sent[cut:].strip()
        if cur and len(cur) + 1 + len(sent) > max_chars:
            out.append(cur)
            cur = sent
        else:
            cur = f"{cur} {sent}".strip()
    if cur:
        out.append(cur)
    return out


def listing_summary(row: dict[str, Any]) -> str:
    """One paragraph from the listing's fields. `row` has listing columns plus `locality_name`."""
    parts = [f"{row['bhk']} BHK" if row.get("bhk") else "Flat"]
    if row.get("furnishing"):
        parts.append(FURNISHING[row["furnishing"]])
    where = ", ".join(x for x in (row.get("locality_name"), CITY.get(row.get("city") or "", row.get("city")))
                      if x)
    head = " ".join(parts) + " flat for rent" + (f" in {where}" if where else "") + "."
    s = [head]
    if row.get("rent"):
        s.append(f"Rent ₹{row['rent']:,} a month.")
    if row.get("deposit") is not None:
        s.append(f"Deposit ₹{row['deposit']:,}.")
    if row.get("maintenance"):
        s.append(f"Maintenance ₹{row['maintenance']:,}.")
    if row.get("sqft"):
        s.append(f"{row['sqft']} sq ft.")
    if row.get("floor") is not None:
        fl = "Ground floor" if row["floor"] == 0 else f"Floor {row['floor']}"
        s.append(fl + (f" of {row['total_floors']}." if row.get("total_floors") else "."))
    if row.get("tenant_pref"):
        s.append(TENANTS[row["tenant_pref"]].capitalize() + ".")
    if row.get("pets"):
        s.append("Pets allowed.")
    extras = []
    if row.get("gated"):
        extras.append("gated society")
    if row.get("no_brokerage"):
        extras.append("no brokerage")
    if row.get("parking") in PARKING:
        extras.append(PARKING[row["parking"]])
    extras += [a.replace("_", " ") for a in row.get("amenities") or []]
    if extras:
        s.append("Has " + ", ".join(extras) + ".")
    return " ".join(s)


def listing_chunks(row: dict[str, Any]) -> list[str]:
    chunks = [listing_summary(row)]
    text = "\n".join(x for x in (row.get("title"), row.get("description")) if x)
    if text.strip():
        chunks += split(strip_contacts(text))
    return chunks
