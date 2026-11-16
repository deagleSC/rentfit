import pytest

from app.pipeline.redact import MARK, has_contacts, strip_contacts


@pytest.mark.parametrize("text", [
    "Call 9876543210 for visit",
    "call me on +91 98765 43210",
    "ph: 098765-43210",
    "WhatsApp 98 76 54 32 10",
    "email owner@gmail.com",
    "mail owner [at] gmail [dot] com",
    "see www.example.com/flat",
    "landline 080-2345 6789",
    "0091 9876543210",
])
def test_contacts_are_removed(text: str) -> None:
    out = strip_contacts(text)
    assert MARK in out
    assert not any(c.isdigit() for c in out.replace("080", "")) or "2345" not in out
    assert "@" not in out and "gmail" not in out


@pytest.mark.parametrize("text", [
    "2BHK, 35k rent, 2 months deposit, 1200 sqft, 3rd floor of 5",
    "Rent 35000, maintenance 2500, available from 1 Dec 2026",
    "Near Whitefield metro, 10 min to ITPL",
    "Pin code 560066",
])
def test_ordinary_listing_text_is_kept(text: str) -> None:
    assert strip_contacts(text) == text
    assert not has_contacts(text)


def test_idempotent() -> None:
    once = strip_contacts("call 9876543210 or mail a@b.co")
    assert strip_contacts(once) == once
