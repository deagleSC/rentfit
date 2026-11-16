"""Contact stripping (backend plan §11, ADR: contact details never pass through the model).

Runs on every description write and on every landlord chat message before a model sees it.
Contact goes through in-app enquiries, so phones, emails, URLs and "call/WhatsApp me" phrases
are replaced with a neutral marker.
"""

from __future__ import annotations

import re

MARK = "[contact removed]"

# Indian mobiles: optional +91 / 0, then 10 digits starting 6-9, with spaces, dots or dashes anywhere.
_PHONE = re.compile(r"(?<!\d)(?:(?:\+|00)\s*91[\s.-]*|0)?[6-9](?:[\s.-]*\d){9}(?!\d)")
# Landlines with an STD code, e.g. 080-2345 6789, 022 2345 6789.
_LANDLINE = re.compile(r"(?<!\d)0\d{2,4}[\s.-]+\d{3,4}[\s.-]*\d{3,4}(?!\d)")
_EMAIL = re.compile(r"[\w.+-]+\s*(?:@|\[at\]|\(at\))\s*[\w-]+(?:\s*(?:\.|\[dot\]|\(dot\))\s*[\w-]+)+", re.I)
_URL = re.compile(r"\b(?:https?://|www\.)\S+|\b[\w-]+\.(?:com|in|co\.in|net|org|io|me|ly)(?:/\S*)?\b", re.I)
_ASK = re.compile(
    r"\b(?:call|ring|whats\s?app|wa|message|msg|text|sms|contact|reach)\s+(?:me|us|owner|landlord)?\s*(?:on|at|@)\b",
    re.I,
)


def strip_contacts(text: str) -> str:
    """Replace contact details with MARK. Idempotent."""
    out = _EMAIL.sub(MARK, text)
    out = _URL.sub(MARK, out)
    out = _PHONE.sub(MARK, out)
    out = _LANDLINE.sub(MARK, out)
    out = _ASK.sub(MARK, out)
    out = re.sub(rf"(?:{re.escape(MARK)}[\s,/;:.-]*){{2,}}", MARK + " ", out)  # collapse runs
    return out.strip()


def has_contacts(text: str) -> bool:
    return strip_contacts(text) != text.strip()
