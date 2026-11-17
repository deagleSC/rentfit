"""Indian rental phrasing → numbers, in code (backend plan §11 `extract`).

Used after the model (deposit in months → amount) and by the fake model, which extracts with
patterns so the listing chat works in dev without a network model.
"""

from __future__ import annotations

import re
from typing import Any

_AMOUNT = r"(\d+(?:\.\d+)?)\s*(k|thousand|hazaar|hazar|hajar|l|lac|lakh|lakhs|cr)?\b"
_MULT = {None: 1, "k": 1_000, "thousand": 1_000, "hazaar": 1_000, "hazar": 1_000, "hajar": 1_000,
         "l": 100_000, "lac": 100_000, "lakh": 100_000, "lakhs": 100_000, "cr": 10_000_000}


def amount(num: str, unit: str | None) -> int:
    return int(round(float(num) * _MULT[(unit or "").lower() or None]))


def parse_amount(text: str) -> int | None:
    """'35k' → 35000, '1.2L' → 120000, '35,000' → 35000, 'Rs 35000' → 35000."""
    m = re.search(_AMOUNT, text.replace(",", ""), re.I)
    return amount(m.group(1), m.group(2)) if m else None


def deposit_from_months(months: float, rent: int) -> int:
    return int(round(months * rent))


FURNISHING = {"unfurnished": "unfurnished", "un-furnished": "unfurnished", "bare": "unfurnished",
              "semi": "semi", "semi-furnished": "semi", "semifurnished": "semi", "semi furnished": "semi",
              "fully furnished": "full", "full furnished": "full", "furnished": "full", "full": "full"}


_NOT_RENT = re.compile(r"\s*(?:months?|mahine|maintenance|sq|bhk)", re.I)  # "rent, 6 months"


def _rent(t: str) -> int | None:
    """'22k rent' or 'rent 22k' / 'rent is ₹22,000', never the deposit that follows 'rent'."""
    before = re.search(r"(?:rs\.?|₹|inr)?\s*" + _AMOUNT
                       + r"\s*(?:rs\.?\s*)?(?:rent|kiraya|per month|/month|pm|a month)\b", t)
    if before and before.group(1):
        v = amount(before.group(1), before.group(2))
        if v >= 1000:
            return v
    for m in re.finditer(r"(?:rent|rental|kiraya)\s*(?:is|of|:)?\s*(?:rs\.?|₹|inr)?\s*" + _AMOUNT, t):
        if _NOT_RENT.match(t, m.end()):
            continue
        v = amount(m.group(1), m.group(2))
        if v >= 1000:
            return v
    return None


def heuristic_extract(message: str) -> dict[str, Any]:
    """Pattern extraction for the fake model. Deliberately simple; the real model does the rest."""
    t = message.lower().replace(",", "")
    out: dict[str, Any] = {}
    if m := re.search(r"(\d)\s*-?\s*bhk", t):
        out["bhk"] = int(m.group(1))
    if (rent := _rent(t)) is not None:
        out["rent"] = rent
    months = r"(\d+(?:\.\d+)?)\s*months?\s*(?:deposit|advance)|deposit\s*(?:of|is|:)?\s*(\d+(?:\.\d+)?)\s*months?"
    if m := re.search(months, t):
        out["deposit_months"] = float(m.group(1) or m.group(2))
    elif m := re.search(r"deposit\s*(?:is|of|:)?\s*(?:rs\.?|₹|inr)?\s*" + _AMOUNT, t):
        out["deposit"] = amount(m.group(1), m.group(2))
    if m := re.search(r"maintenance\s*(?:is|of|:)?\s*(?:rs\.?|₹|inr)?\s*" + _AMOUNT, t):
        out["maintenance"] = amount(m.group(1), m.group(2))
    for phrase, value in sorted(FURNISHING.items(), key=lambda kv: -len(kv[0])):
        if phrase in t:
            out["furnishing"] = value
            break
    if m := re.search(r"(\d{3,5})\s*(?:sq\.?\s*ft|sqft|square feet)", t):
        out["sqft"] = int(m.group(1))
    if re.search(r"\bfamil(?:y|ies)\b", t) and not re.search(r"bachelor", t):
        out["tenant_pref"] = "family"
    elif re.search(r"bachelors?\s*(?:also|too)?\s*(?:ok|allowed|welcome|fine)|anyone|any tenant", t):
        out["tenant_pref"] = "any"
    elif re.search(r"\bbachelors?\b", t):
        out["tenant_pref"] = "bachelors"
    if re.search(r"no pets|pets not allowed", t):
        out["pets"] = False
    elif re.search(r"pets? (?:allowed|ok|friendly|welcome)|pet[- ]friendly", t):
        out["pets"] = True
    if re.search(r"no brokerage|zero brokerage|without broker|direct owner|no broker", t):
        out["no_brokerage"] = True
    if re.search(r"gated", t):
        out["gated"] = True
    if re.search(r"immediate|ready to move|available now", t):
        out["available_now"] = True
    if m := re.search(r"\bin ([a-z][a-z .]+?)(?:,|\.|$| near| for| with| rent| bangalore| bengaluru| mumbai)",
                      message.lower()):
        out["locality_name"] = m.group(1).strip().title()
    amenities = {"lift": r"\blift|elevator", "power_backup": r"power back ?up|generator", "gym": r"\bgym",
                 "pool": r"swimming pool|\bpool", "security": r"security|guard", "balcony": r"balcony",
                 "modular_kitchen": r"modular kitchen", "cctv": r"cctv", "water_24x7": r"24x7 water|24/7 water"}
    found = [a for a, rx in amenities.items() if re.search(rx, t)]
    if found:
        out["add_amenities"] = found
    return out
