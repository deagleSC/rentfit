"""listing_update: one model call per landlord chat turn (backend plan §11).

The same prompt reads the first free-text description and later edits ("make deposit 2 months",
"bachelors also ok"). It returns only what the message says; code turns that into patches,
resolves the locality, and decides what to ask next.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.domain.listing import Amenity, Furnishing, Parking, TenantPref
from app.llm.prompts import UNTRUSTED_RULE, Prompt, register, untrusted
from app.pipeline.normalise import heuristic_extract

Clearable = Literal["maintenance", "sqft", "floor", "total_floors", "pets", "parking", "gated", "no_brokerage",
                    "title", "description"]


class ListingUpdateInput(BaseModel):
    message: str  # contacts already removed
    current: dict[str, Any]  # what the listing says now (no contact details)
    today: date
    last_question: str | None = None


class ListingUpdate(BaseModel):
    bhk: int | None = Field(default=None, ge=1, le=6)
    rent: int | None = Field(default=None, ge=1000, le=2_000_000, description="Monthly rent in INR")
    deposit: int | None = Field(default=None, ge=0, description="Deposit amount in INR")
    deposit_months: float | None = Field(default=None, ge=0, le=12,
                                         description="Deposit given as months of rent, e.g. 2")
    maintenance: int | None = Field(default=None, ge=0, description="Monthly maintenance in INR")
    furnishing: Furnishing | None = None
    sqft: int | None = Field(default=None, ge=100, le=20000)
    floor: int | None = Field(default=None, ge=-2, le=120)
    total_floors: int | None = Field(default=None, ge=1, le=120)
    tenant_pref: TenantPref | None = None
    pets: bool | None = None
    parking: Parking | None = None
    gated: bool | None = None
    no_brokerage: bool | None = None
    available_from: date | None = None
    available_now: bool | None = Field(default=None, description="True for 'immediately' / 'ready to move'")
    city: Literal["bangalore", "mumbai"] | None = None
    locality_name: str | None = Field(default=None, description="Area name as written, e.g. 'Koramangala'")
    title: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=2000,
                                    description="Only when the landlord asks to set or rewrite the description")
    add_amenities: list[Amenity] = Field(default_factory=list)
    remove_amenities: list[Amenity] = Field(default_factory=list)
    clear: list[Clearable] = Field(default_factory=list, description="Fields the landlord asked to remove")


SYSTEM = (
    "You help a landlord in India create a rental listing by chat. Read the landlord's latest message and "
    "return ONLY the listing facts it states or changes. Leave every other field empty; never guess, and "
    "never repeat values that are already in the current listing unless the message changes them.\n"
    "Rules: amounts are monthly INR; '35k' = 35000, '1.2L' or '1.2 lakh' = 120000. If the deposit is given "
    "in months ('2 months deposit'), set deposit_months, not deposit. 'Semi' = semi, 'fully furnished' = "
    "full. 'Bachelors also ok' / 'anyone' = tenant_pref any; 'family only' = family. 'Immediately' / "
    "'ready to move' = available_now. Dates are relative to today. Bangalore/Bengaluru = bangalore. "
    "'Remove the gym' / 'no lift' means remove_amenities. Use `clear` ONLY for a field the landlord explicitly "
    "asks to delete (e.g. 'remove the maintenance amount'); otherwise leave `clear` empty. "
    "If the message answers the assistant's last question, read it as that answer (e.g. a bare '2' after "
    "'How many bedrooms?' is bhk 2). Ignore phone numbers, emails and links.\n" + UNTRUSTED_RULE
)


def _user(data: ListingUpdateInput) -> str:
    last = f"Assistant's last question: {data.last_question}\n" if data.last_question else ""
    return (f"Today: {data.today.isoformat()}\nCurrent listing: {data.current}\n{last}"
            f"Landlord's message:\n{untrusted(data.message)}")


LISTING_UPDATE = register(
    Prompt(
        id="listing_update",
        version=2,
        system=SYSTEM,
        input=ListingUpdateInput,
        output=ListingUpdate,
        user=_user,
        description="Submit only the listing fields the landlord's message states or changes.",
        fake=lambda data: heuristic_extract(data.message),
    )
)
