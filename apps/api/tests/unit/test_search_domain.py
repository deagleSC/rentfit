"""Phase 3 pure code: filter merge + slang, query heuristics, relax ladder, RRF, citations, commute."""

from __future__ import annotations

from uuid import uuid4

from hypothesis import given
from hypothesis import strategies as st

from app.domain.filters import Commute, SearchFilters, SearchUpdate, apply_slang, chips, merge
from app.domain.relax import steps
from app.llm.prompts.search import Claim
from app.pipeline import citations
from app.pipeline.hybrid import or_tsquery, rrf, where
from app.pipeline.query_heuristics import heuristic_search
from app.services.commute import estimate, geohash, haversine_km

KOR, HSR = uuid4(), uuid4()


def test_follow_up_patches_previous_filters() -> None:
    f, ch = merge(SearchFilters(), SearchUpdate(city="bangalore", bhk=[2], rent_max=40000),
                  localities=[(KOR, "Koramangala")], commute=None)
    assert f.locality_ids == [KOR] and {c.field for c in ch} == {"city", "bhk", "rent_max", "locality_ids"}
    g, ch = merge(f, apply_slang("thoda sasta yaar", SearchUpdate(), f), localities=[], commute=None)
    assert g.rent_max == 36000 and [c.field for c in ch] == ["rent_max"] and g.bhk == [2]
    h, _ = merge(g, SearchUpdate(replace_localities=True), localities=[(HSR, "HSR Layout")], commute=None)
    assert h.locality_ids == [HSR] and h.locality_names == ["HSR Layout"]
    i, _ = merge(h, SearchUpdate(), localities=[(KOR, "Koramangala")], commute=None)
    assert i.locality_ids == [HSR, KOR]  # "also Koramangala" adds
    j, _ = merge(i, SearchUpdate(clear=["rent_max", "locality_ids", "landlord_id"]), localities=[], commute=None)
    assert j.rent_max is None and j.locality_ids == [] and j.locality_names == [] and j.bhk == [2]
    k, _ = merge(j, SearchUpdate(city="mumbai"), localities=[], commute=None)
    assert k == SearchFilters(city="mumbai")  # a new city starts clean
    assert apply_slang("flats near the metro please", SearchUpdate(), k).near_metro is True


def test_chips_cover_filters() -> None:
    c = Commute(poi_id=uuid4(), poi_name="Manyata Tech Park", max_minutes=30)
    labels = [x["label"] for x in chips(SearchFilters(city="bangalore", bhk=[1, 2], rent_max=35000,
                                                      near_metro_m=1000, commute=c, pets=True))]
    assert labels == ["1/2 BHK", "Up to ₹35k", "Pets OK", "Metro ≤ 1 km", "≤ 30 min to Manyata Tech Park"]


def test_heuristics() -> None:
    p = heuristic_search("2bhk in HSR Layout under 35k, semi furnished, family, 30 min to Manyata")
    assert p["bhk"] == [2] and p["rent_max"] == 35000 and p["furnishing"] == ["semi"]
    assert p["locality_names"] == ["hsr layout"] and p["tenant_type"] == "family"
    assert p["commute_minutes"] == 30 and p["commute_to"] == "manyata"
    assert heuristic_search("what's the commute for the 2nd one?")["result_number"] == 2
    assert heuristic_search("thanks!")["intent"] == "chitchat"
    assert heuristic_search("Bengaluru mein 1.2L tak 3 bhk")["city"] == "bangalore"


def test_relax_ladder_order() -> None:
    c = Commute(poi_id=uuid4(), poi_name="ITPB", max_minutes=30)
    f = SearchFilters(rent_max=30000, locality_ids=[KOR], locality_names=["Koramangala"], commute=c,
                      near_metro_m=1000, amenities=["gym", "pool"])
    got = steps(f, lambda ids: [(HSR, "HSR Layout")])
    assert [r.step for _, r in got] == ["budget", "adjacent", "commute", "metro", "amenity"]
    last = got[-1][0]
    assert last.rent_max == 33000 and last.locality_ids == [KOR, HSR] and last.commute and \
        last.commute.max_minutes == 40 and last.near_metro_m == 2000 and last.amenities == ["gym"]
    assert got[0][1].message == "raised the budget to ₹33,000"
    assert steps(SearchFilters(), lambda ids: []) == []
    kept = steps(f, lambda ids: [(HSR, "HSR Layout")], skip={"rent_max", "near_metro_m"})
    assert [r.step for _, r in kept] == ["adjacent", "commute", "amenity"] and kept[-1][0].rent_max == 30000


def test_rrf_and_text_query() -> None:
    a, b, c = uuid4(), uuid4(), uuid4()
    s = rrf([a, b], [b, c])
    assert max(s, key=lambda k: s[k]) == b and s[a] > s[c]
    assert or_tsquery("2 BHK near metro with balcony and gym") == "metro | balcony | gym"
    cond, args = where(SearchFilters(city="mumbai", tenant_type="family", amenities=["lift"]))
    assert "p.tenant_pref in ('any', %s)" in cond and args == ["mumbai", "family", ["lift"]]


def test_citations_drop_unsupported_numbers() -> None:
    sources = {"L1": {"rent": 35000, "locality": "HSR Layout", "metro": "HSR metro, 600 m"},
               "N1": {"text": "OpenStreetMap lists 12 schools within the area."}}
    claims = [Claim(text="L1 rents for ₹35,000 in HSR Layout.", cites=["L1"]),
              Claim(text="It's 35k with metro 600 m away.", cites=["L1"]),
              Claim(text="Rent is ₹32,000.", cites=["L1"]),  # wrong number
              Claim(text="The area has 12 schools.", cites=["N1"]),
              Claim(text="It has 3 parks.", cites=["N1"]),  # not in the note
              Claim(text="Great for families.", cites=["L9"]),  # unknown ref
              Claim(text="Try a nearby area.", cites=[]),
              Claim(text="Most are under 40k.", cites=[])]  # numbers without a source
    checked = citations.check(claims, sources)
    assert [c.text for c in checked.kept] == ["L1 rents for ₹35,000 in HSR Layout.", "It's 35k with metro 600 m away.",
                                             "The area has 12 schools.", "Try a nearby area."]


@given(st.floats(-60, 60), st.floats(-170, 170))
def test_geohash_length_and_alphabet(lat: float, lng: float) -> None:
    h = geohash(lat, lng)
    assert len(h) == 7 and set(h) <= set("0123456789bcdefghjkmnpqrstuvwxyz")


def test_commute_estimate() -> None:
    assert geohash(57.64911, 10.40744) == "u4pruyd"  # the reference example
    km = haversine_km(12.9352, 77.6245, 13.0450, 77.6200)  # Koramangala → Manyata, ~12 km
    assert 11.5 < km < 12.8
    assert estimate(km, "bangalore", "car") > estimate(km, "bangalore", "two_wheeler")


def test_nonsense_budget_ignored() -> None:
    f, ch = merge(SearchFilters(rent_max=30000), SearchUpdate(rent_max=1), localities=[], commute=None)
    assert f.rent_max == 30000 and ch == []


def test_ref_tokens_are_removed_from_claim_text() -> None:
    from app.agents.search_agent import _REF_TOKEN

    text = "In Haralur, a 2 BHK for ₹29,000 (L1) is 4.0 km from the metro [L1, N2]. L3: also good."
    assert _REF_TOKEN.sub("", text) == "In Haralur, a 2 BHK for ₹29,000 is 4.0 km from the metro. also good."
