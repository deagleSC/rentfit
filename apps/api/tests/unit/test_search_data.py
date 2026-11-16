"""Phase 2 pure code: chunking, locality note text, hashing embedder, seed generator."""

from __future__ import annotations

import math
import random
import re
from datetime import date
from uuid import uuid4

from hypothesis import given
from hypothesis import strategies as st

from app.domain.listing import ListingDraft
from app.pipeline.chunk import listing_chunks, listing_summary, split
from app.pipeline.locality_notes import note_facts, note_text
from app.services.embeddings import DIM, HashingEmbedder
from scripts.seed import generate


@given(st.text(min_size=1, max_size=5000))
def test_split_bounds_and_keeps_words(text: str) -> None:
    parts = split(text, 200)
    assert all(0 < len(p) <= 200 for p in parts)
    assert "".join(text.split()) == "".join("".join(parts).split())


def test_summary_and_chunks() -> None:
    row = {"bhk": 2, "furnishing": "semi", "city": "bangalore", "locality_name": "HSR Layout", "rent": 32000,
           "deposit": 96000, "floor": 0, "total_floors": 4, "tenant_pref": "bachelors", "pets": True,
           "amenities": ["power_backup", "lift"], "title": "Nice flat",
           "description": "Near the lake. WhatsApp 98765 43210 for visits."}
    s = listing_summary(row)
    assert s.startswith("2 BHK semi-furnished flat for rent in HSR Layout, Bengaluru (Bangalore).")
    assert "Rent ₹32,000 a month." in s and "Ground floor of 4." in s and "For bachelors." in s
    assert "Pets allowed." in s and "power backup" in s
    chunks = listing_chunks(row)
    assert len(chunks) == 2 and "98765" not in chunks[1]
    assert listing_chunks({"bhk": 1}) == ["1 BHK flat for rent."]


def test_note_states_only_its_facts() -> None:
    facts = note_facts({"schools": 3, "parks": 1, "hospitals": 0},
                       {"metro_station": {"name": "Trinity", "metres": 640.4}, "rail_station": None,
                        "hospital": {"name": "City Hospital", "metres": 1820.0}},
                       [{"name": "Bagmane", "metres": 2500.0}])
    text = note_text("Ulsoor", "bangalore", facts)
    assert "Trinity, about 640 m" in text and "3 schools and 1 park" in text
    assert "City Hospital, about 1.8 km" in text and "Bagmane (2.5 km)" in text
    # Every number in the text appears in the facts (citation check in Phase 3 relies on this).
    stated = {float(n) for n in re.findall(r"\d+(?:\.\d+)?", text)}
    known = {3.0, 1.0, 640.0, 1.8, 2.5, 5.0}
    assert stated <= known
    assert "no metro" in note_text("X", "mumbai", note_facts({}, {}, []))


def test_hashing_embedder() -> None:
    e = HashingEmbedder()
    a, b, c = (e.embed_one(t) for t in ("2 bhk near metro", "2 bhk close to metro", "sea facing studio"))
    dot = lambda x, y: sum(p * q for p, q in zip(x, y, strict=True))  # noqa: E731
    assert len(a) == DIM and math.isclose(dot(a, a), 1.0, rel_tol=1e-9)
    assert dot(a, b) > dot(a, c)
    assert e.embed_one("same") == e.embed_one("same")


def test_seed_generator_is_valid_and_repeatable() -> None:
    loc = {"id": uuid4(), "city": "mumbai", "name": "Powai", "median_rent": {"1": 30000, "2": 52000, "3": 85000}}
    rng = random.Random(1)
    rows = [generate(rng, loc, date(2026, 11, 17)) for _ in range(300)]
    for r in rows:
        ListingDraft.model_validate(r)  # every generated listing passes the domain rules
        assert r["rent"] % 500 == 0 and "Powai" in r["description"]
    assert {r["bhk"] for r in rows} == {1, 2, 3, 4}
    twos = [r["rent"] for r in rows if r["bhk"] == 2]
    assert 52000 * 0.74 <= min(twos) and max(twos) <= 52000 * 1.26
    assert generate(random.Random(1), loc, date(2026, 11, 17)) == rows[0]
