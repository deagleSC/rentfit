"""Listing model, field rules and required fields (backend plan §8.1)."""

from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

Status = Literal["draft", "published", "paused", "let"]
Furnishing = Literal["unfurnished", "semi", "full"]
TenantPref = Literal["any", "family", "bachelors"]
Parking = Literal["none", "bike", "car", "both"]

AMENITIES: tuple[str, ...] = (
    "lift", "power_backup", "security", "cctv", "intercom", "gym", "pool", "clubhouse", "play_area",
    "water_24x7", "wifi", "ac", "geyser", "washing_machine", "fridge", "modular_kitchen", "balcony",
)
Amenity = Literal[
    "lift", "power_backup", "security", "cctv", "intercom", "gym", "pool", "clubhouse", "play_area",
    "water_24x7", "wifi", "ac", "geyser", "washing_machine", "fridge", "modular_kitchen", "balcony",
]


class LatLng(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class ListingDraft(BaseModel):
    """Every field optional: what the landlord has told us so far."""

    model_config = ConfigDict(extra="forbid")

    city: str | None = None
    locality_id: UUID | None = None
    location: LatLng | None = None
    bhk: int | None = Field(default=None, ge=1, le=6)
    rent: int | None = Field(default=None, gt=0, le=2_000_000)
    deposit: int | None = Field(default=None, ge=0)
    maintenance: int | None = Field(default=None, ge=0)
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
    amenities: list[Amenity] = Field(default_factory=list)
    title: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def _consistent(self) -> ListingDraft:
        if self.deposit is not None and self.rent is not None and self.deposit > 12 * self.rent:
            raise ValueError("deposit cannot be more than 12 months' rent")
        if self.floor is not None and self.total_floors is not None and self.floor > self.total_floors:
            raise ValueError("floor cannot be above the top floor")
        if len(set(self.amenities)) != len(self.amenities):
            raise ValueError("amenities must not repeat")
        return self


# Order matters: the agent asks for the first missing one (backend plan §11).
REQUIRED_TO_PUBLISH: tuple[str, ...] = (
    "city", "locality_id", "location", "bhk", "rent", "deposit", "furnishing", "tenant_pref", "available_from",
)
PHOTOS_MIN = 3
PHOTOS_MAX = 15


def missing_fields(draft: ListingDraft) -> list[str]:
    return [f for f in REQUIRED_TO_PUBLISH if getattr(draft, f) is None]


class Listing(ListingDraft):
    id: UUID
    landlord_id: UUID
    status: Status
    version: int
    photo_count: int = 0
    flags: dict[str, object] = Field(default_factory=dict)
