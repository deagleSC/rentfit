from datetime import date
from uuid import uuid4

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.listing import AMENITIES, LatLng, ListingDraft, missing_fields
from app.domain.listing_patches import (
    AddAmenity,
    PatchError,
    RemoveAmenity,
    SetField,
    apply_patches,
    patches_from_form,
)
from app.domain.state_machine import TransitionError, check_publish, next_status

FULL = ListingDraft(city="bangalore", locality_id=uuid4(), location=LatLng(lat=12.93, lng=77.62), bhk=2, rent=35000,
                    deposit=70000, furnishing="semi", tenant_pref="any", available_from=date(2026, 12, 1))


def test_missing_fields_in_priority_order() -> None:
    assert missing_fields(ListingDraft(bhk=2)) == ["city", "locality_id", "location", "rent", "deposit", "furnishing",
                                                   "tenant_pref", "available_from"]
    assert missing_fields(FULL) == []


def test_apply_patches_returns_diff_and_strips_contacts() -> None:
    new, changes = apply_patches(ListingDraft(), [
        SetField(field="rent", value=30000),
        SetField(field="description", value="Nice flat. Call 9876543210"),
        AddAmenity(amenity="lift"),
        AddAmenity(amenity="lift"),
    ])
    assert new.rent == 30000 and new.amenities == ["lift"]
    assert "9876543210" not in (new.description or "")
    assert {c.field for c in changes} == {"rent", "description", "amenities"}


def test_invalid_result_is_rejected_whole() -> None:
    with pytest.raises(PatchError):
        apply_patches(ListingDraft(rent=10000), [SetField(field="deposit", value=500000)])
    with pytest.raises(PatchError):
        apply_patches(ListingDraft(), [SetField(field="bhk", value=9)])


def test_state_machine() -> None:
    assert next_status("draft", "publish") == "published"
    assert next_status("published", "pause") == "paused"
    assert next_status("paused", "resume") == "published"
    assert next_status("paused", "let") == "let"
    for current, action in [("draft", "pause"), ("let", "resume"), ("published", "publish"), ("let", "publish")]:
        with pytest.raises(TransitionError):
            next_status(current, action)  # type: ignore[arg-type]


def test_publish_checks() -> None:
    assert check_publish(FULL, 3, pin_in_city=True) == []
    assert "photos:at_least_3" in check_publish(FULL, 2, pin_in_city=True)
    assert "location:outside_city" in check_publish(FULL, 3, pin_in_city=False)
    assert "rent:too_low" in check_publish(FULL.model_copy(update={"rent": 350, "deposit": 0}), 3, pin_in_city=True)
    assert check_publish(ListingDraft(), 0, pin_in_city=False)[0] == "missing:city"


# ---- property: any valid edit sequence yields a valid draft, and form diffs replay exactly

values = {
    "bhk": st.integers(1, 6), "rent": st.integers(5000, 200000), "furnishing": st.sampled_from(["unfurnished", "semi", "full"]),
    "tenant_pref": st.sampled_from(["any", "family", "bachelors"]), "pets": st.booleans(), "gated": st.booleans(),
    "parking": st.sampled_from(["none", "bike", "car", "both"]), "sqft": st.integers(100, 5000),
}
set_ops = st.one_of(*[v.map(lambda x, f=f: SetField(field=f, value=x)) for f, v in values.items()])
amenity_ops = st.sampled_from(AMENITIES).flatmap(
    lambda a: st.sampled_from([AddAmenity(amenity=a), RemoveAmenity(amenity=a)]))  # type: ignore[arg-type]


@given(st.lists(st.one_of(set_ops, amenity_ops), max_size=20))
def test_any_valid_patch_sequence_gives_valid_draft(ops: list) -> None:  # type: ignore[type-arg]
    new, _ = apply_patches(ListingDraft(), ops)
    ListingDraft.model_validate(new.model_dump())


@given(st.lists(st.one_of(set_ops, amenity_ops), max_size=20))
def test_form_diff_replays_to_the_same_draft(ops: list) -> None:  # type: ignore[type-arg]
    target, _ = apply_patches(ListingDraft(), ops)
    replayed, _ = apply_patches(ListingDraft(), patches_from_form(ListingDraft(), target))
    assert replayed == target


def test_backfill_only_adds_what_patterns_see() -> None:
    from app.agents.listing_agent import backfill
    from app.llm.prompts.listing import ListingUpdate

    upd = ListingUpdate(bhk=2, deposit_months=6, locality_name="HSR Layout")
    got = backfill(upd, "HSR Layout sector 2 mein 2bhk hai, rent 28k, 6 mahine ka deposit. Sirf family.")
    assert got.rent == 28000 and got.tenant_pref == "family" and got.deposit_months == 6 and got.deposit is None
    kept = backfill(ListingUpdate(rent=30000), "rent 28k")
    assert kept.rent == 30000  # the model's value wins


def test_lenient_listing_values() -> None:
    from app.llm.prompts.listing import ListingUpdate

    u = ListingUpdate.model_validate({"city": "Thane", "parking": "car parking", "tenant_pref": "Bachelor"})
    assert u.city is None and u.parking == "car" and u.tenant_pref == "bachelors"
    assert ListingUpdate.model_validate({"city": "Bengaluru", "parking": "bike and car"}).parking == "both"
