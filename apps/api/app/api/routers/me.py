"""Shared by both apps: who am I, create my profile after sign-up, update it."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.auth import CurrentUser, PrincipalDep, user_tx
from app.core.db import Tx
from app.core.errors import ERROR_RESPONSES, AppError, Ok, ok

router = APIRouter(prefix="/v1/me", tags=["me"], responses=ERROR_RESPONSES)


class Me(BaseModel):
    id: UUID
    email: str | None
    role: Literal["landlord", "tenant"]
    name: str
    city: str | None
    has_phone: bool  # the number itself is never returned


class ProfileCreate(BaseModel):
    role: Literal["landlord", "tenant"]
    name: str = Field(min_length=1, max_length=200)


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    city: str | None = None
    phone: str | None = Field(default=None, pattern=r"^\+91[6-9][0-9]{9}$")


_PROFILE_ERRORS = {
    "Z1001": (409, "role_conflict", "This account already has a different role."),
    "23503": (422, "unknown_city", "That city is not supported."),
}


async def _load_me(tx: Tx, user: CurrentUser) -> Me:
    row = await tx.fetchone("select role, name, city, phone is not null as has_phone from profiles where id = %s",
                            (user.user_id,))
    if row is None:
        raise AppError(404, "profile_missing", "Finish creating your account first.")
    return Me(id=user.user_id, email=user.email, role=row["role"], name=row["name"], city=row["city"],
              has_phone=row["has_phone"])


async def _guarded(tx: Tx, query: str, params: tuple[object, ...]) -> None:
    try:
        async with tx.conn.transaction():  # savepoint, so a raised error leaves tx usable
            await tx.conn.execute(query, params)
    except psycopg.Error as exc:
        mapped = _PROFILE_ERRORS.get(exc.sqlstate or "")
        if mapped:
            raise AppError(*mapped) from exc
        raise


@router.get("", response_model=Ok[Me])
async def get_me(principal: PrincipalDep) -> Ok[Me]:
    async with user_tx(principal) as (tx, user):
        return ok(await _load_me(tx, user))


@router.post("/profile", response_model=Ok[Me])
async def create_profile(body: ProfileCreate, principal: PrincipalDep) -> Ok[Me]:
    """Create the caller's profile. Idempotent; the role is fixed once set."""
    async with user_tx(principal) as (tx, user):
        await _guarded(tx, "select app.create_profile(%s, %s)", (body.role, body.name))
        user = user.model_copy(update={"role": body.role})
        await tx.set_claims(user.claims())
        return ok(await _load_me(tx, user))


@router.patch("", response_model=Ok[Me])
async def update_me(body: ProfileUpdate, principal: PrincipalDep) -> Ok[Me]:
    async with user_tx(principal) as (tx, user):
        if user.role is None:
            raise AppError(404, "profile_missing", "Finish creating your account first.")
        fields = body.model_dump(exclude_unset=True)
        if fields:
            sets = ", ".join(f"{k} = %s" for k in fields)  # keys come from the model, not the client
            await _guarded(tx, f"update profiles set {sets} where id = %s", (*fields.values(), user.user_id))
        return ok(await _load_me(tx, user))
