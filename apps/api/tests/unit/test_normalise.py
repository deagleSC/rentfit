import pytest

from app.pipeline.normalise import deposit_from_months, heuristic_extract, parse_amount


@pytest.mark.parametrize(("text", "value"), [("35k", 35000), ("1.2L", 120000), ("35,000", 35000), ("Rs 18000", 18000),
                                             ("2 lakh", 200000)])
def test_parse_amount(text: str, value: int) -> None:
    assert parse_amount(text) == value


def test_deposit_months() -> None:
    assert deposit_from_months(2, 35000) == 70000


def test_heuristic_extract_first_description() -> None:
    out = heuristic_extract("2BHK in Koramangala, rent 35k, 2 months deposit, semi furnished, family only, lift and gym. "
                            "No brokerage. Ready to move.")
    assert out["bhk"] == 2 and out["rent"] == 35000 and out["deposit_months"] == 2
    assert out["furnishing"] == "semi" and out["tenant_pref"] == "family" and out["no_brokerage"] is True
    assert out["locality_name"] == "Koramangala" and out["available_now"] is True
    assert set(out["add_amenities"]) == {"lift", "gym"}


def test_heuristic_extract_edits() -> None:
    assert heuristic_extract("bachelors also ok")["tenant_pref"] == "any"
    assert heuristic_extract("make deposit 3 months")["deposit_months"] == 3
    assert heuristic_extract("fully furnished now")["furnishing"] == "full"
