"""Seed published listings (backend plan §14.2). No model calls.

    uv run python -m scripts.seed                     # 50 listings, committed
    uv run python -m scripts.seed --count 600 --dry-run   # build + verify each, then roll back

Each listing is generated in code (fields around the locality's median rent, a pin inside the
locality, a description from varied templates, some Hinglish), then written through the same
services as the API: create_draft → apply_patches/save_draft → set_location → photos → publish.
Publishing queues embed-listing; here that job runs in the same transaction, so a listing that
fails to embed is never committed.

Seed landlords (seed-landlord-NN@rentfit.test) and tenants are created once through the Supabase
admin API with SEED_PASSWORD and reused. A committed run first removes the seed landlords' earlier
listings, so re-running replaces the set rather than adding to it. `--dry-run` uploads no photos.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx

from app.agents.listing_agent import as_draft
from app.core.config import get_settings
from app.core.db import Tx, close_pool, system_claims, transaction
from app.domain.listing import AMENITIES, LatLng, ListingDraft
from app.domain.listing_patches import apply_patches, patches_from_form
from app.jobs import dispatcher as dispatcher_module
from app.jobs.runs import JobRefs
from app.services import geo, retrieval_index
from app.services import listings as repo
from app.services.embeddings import Embedder, get_embedder
from app.services.storage import get_storage

PHOTOS = Path(__file__).resolve().parent / "seed_data" / "photos"
LANDLORDS = 10
TENANTS = 3
NAMES = ["Anita Rao", "Rohit Mehta", "Priya Nair", "Sanjay Kulkarni", "Farah Khan", "Vikram Shetty",
         "Meera Iyer", "Arjun Desai", "Kavya Reddy", "Imran Sheikh", "Neha Joshi", "Rahul Pillai", "Divya Menon"]

BHK_WEIGHTS = {1: 30, 2: 42, 3: 22, 4: 6}
DEPOSIT_MONTHS = {"bangalore": (3, 4, 5, 6, 8, 10), "mumbai": (2, 3, 4, 6)}
OPENERS = [
    "Spacious {bhk} BHK {furn} flat in {loc}.",
    "Well-maintained {bhk} BHK in a quiet lane of {loc}.",
    "Bright {bhk} BHK apartment in {loc}, good ventilation and natural light.",
    "{loc} mein {bhk} BHK {furn} flat available.",
    "Newly painted {bhk} BHK in {loc}, ready to move in.",
    "Corner {bhk} BHK flat in {loc} with cross ventilation.",
]
MIDDLES = [
    "Close to shops, schools and the main road.",
    "Markets and bus stops are a short walk away.",
    "Society has {amen}.",
    "Building has {amen}.",
    "Sab kuch paas mein hai, market aur bus stop walking distance par.",
    "Peaceful neighbourhood, good for working professionals.",
    "Ideal for a small family.",
]
CLOSERS = {
    "family": ["Family preferred.", "Only families please.", "Sirf family ko denge."],
    "bachelors": ["Bachelors welcome.", "Working bachelors preferred.", "Bachelors chalega."],
    "any": ["Families and bachelors both welcome.", "Open to all tenants.", "Family ya bachelors, dono chalega."],
}
FURN_WORDS = {"unfurnished": "unfurnished", "semi": "semi-furnished", "full": "fully furnished"}


# ------------------------------------------------------------------ generation (pure)


def generate(rng: random.Random, loc: dict[str, Any], today: date) -> dict[str, Any]:
    """Form fields for one listing in `loc` ({id, city, name, median_rent})."""
    bhk = rng.choices(list(BHK_WEIGHTS), weights=list(BHK_WEIGHTS.values()))[0]
    medians = {int(k): v for k, v in (loc["median_rent"] or {}).items()}
    base = medians.get(bhk) or (medians.get(3, 30000) * 1.5 if bhk >= 4 else 25000)
    rent = int(round(base * rng.uniform(0.75, 1.25) / 500) * 500)
    deposit = rent * rng.choice(DEPOSIT_MONTHS.get(loc["city"], (3,)))
    furnishing = rng.choices(["unfurnished", "semi", "full"], weights=[25, 50, 25])[0]
    tenant_pref = rng.choices(["any", "family", "bachelors"], weights=[45, 35, 20])[0]
    total = rng.choice([3, 4, 4, 5, 7, 12, 14, 20, 25])
    amenities = sorted(rng.sample(AMENITIES, rng.randint(2, 7)))
    sqft = int(round((350 + 450 * bhk) * rng.uniform(0.85, 1.25), -1))
    fields: dict[str, Any] = {
        "city": loc["city"], "locality_id": loc["id"], "bhk": bhk, "rent": rent, "deposit": deposit,
        "furnishing": furnishing, "tenant_pref": tenant_pref, "sqft": sqft,
        "floor": rng.randint(0, total), "total_floors": total, "amenities": amenities,
        "available_from": today + timedelta(days=rng.choice([0, 0, 7, 15, 30, 45])),
        "pets": rng.random() < 0.3, "gated": rng.random() < 0.55, "no_brokerage": rng.random() < 0.6,
        "parking": rng.choice(["none", "bike", "car", "both"]),
    }
    if rng.random() < 0.6:
        fields["maintenance"] = int(round(rent * rng.uniform(0.04, 0.1), -2))
    fields["title"] = f"{bhk} BHK {FURN_WORDS[furnishing]} flat in {loc['name']}"
    fields["description"] = describe(rng, fields, loc["name"])
    return fields


def describe(rng: random.Random, f: dict[str, Any], loc_name: str) -> str:
    amen = ", ".join(a.replace("_", " ") for a in f["amenities"][:3])
    words = {"bhk": f["bhk"], "furn": FURN_WORDS[f["furnishing"]], "loc": loc_name, "amen": amen}
    parts = [rng.choice(OPENERS), *rng.sample(MIDDLES, 2), rng.choice(CLOSERS[f["tenant_pref"]])]
    if f.get("pets"):
        parts.insert(-1, "Pets are okay.")
    return " ".join(p.format(**words) for p in parts)


# ------------------------------------------------------------------ accounts


class SeedAccounts:
    """Get-or-create seed users through the Supabase admin API (needs SUPABASE_SERVICE_KEY)."""

    def __init__(self, base_url: str, service_key: str, password: str):
        self.base = base_url.rstrip("/") + "/auth/v1/admin/users"
        self.headers = {"apikey": service_key, "Authorization": f"Bearer {service_key}"}
        self.password = password

    async def ensure(self, email: str, role: str, name: str) -> UUID:
        async with httpx.AsyncClient(timeout=30) as client:
            res = await client.post(self.base, headers=self.headers, json={
                "email": email, "password": self.password, "email_confirm": True,
                "user_metadata": {"role": role, "name": name}})
            if res.status_code in (200, 201):
                uid = UUID(res.json()["id"])
            else:  # already registered: find it
                page = await client.get(self.base, headers=self.headers, params={"per_page": 1000})
                page.raise_for_status()
                uid = next(UUID(u["id"]) for u in page.json()["users"] if u.get("email") == email)
        async with transaction({"sub": str(uid)}) as tx:
            if await tx.fetchone("select 1 from profiles where id = %s", (uid,)) is None:
                await tx.fetchone("select app.create_profile(%s, %s)", (role, name))
        return uid


# ------------------------------------------------------------------ writing


class _Rollback(Exception):
    pass


class IndexNow:
    """Stands in for the job dispatcher: embed-listing's work runs in the publishing transaction."""

    def __init__(self, embedder: Embedder):
        self.embedder = embedder

    async def enqueue(self, tx: Tx, type: str, refs: JobRefs, params: dict[str, Any] | None = None) -> UUID:
        assert type == "embed-listing"
        async with tx.as_system():
            await retrieval_index.index_listing(tx, refs.entity_id, self.embedder)
        return uuid4()

    async def resend(self, run: dict[str, object]) -> None:  # pragma: no cover
        raise NotImplementedError


async def _random_point(tx: Tx, locality_id: UUID, seed: int) -> LatLng:
    row = await tx.fetchone(
        """
        select st_y(p) as lat, st_x(p) as lng from (
          select (st_dump(st_generatepoints(st_buffer(boundary::geometry, -0.002), 1, %s))).geom as p
          from localities where id = %s) g
        """,
        (seed, locality_id),
    )
    if row is None:  # polygon too thin for the inner buffer: use its centroid
        row = await tx.fetchone("select st_y(centroid::geometry) as lat, st_x(centroid::geometry) as lng"
                                " from localities where id = %s", (locality_id,))
    assert row is not None
    return LatLng(lat=row["lat"], lng=row["lng"])


async def write_listing(landlord: UUID, fields: dict[str, Any], seed: int, *, upload: bool,
                        dry_run: bool) -> tuple[int, int]:
    """One listing in one transaction. Returns (photos, chunks)."""
    photos = sorted(p for p in PHOTOS.glob("*.webp") if not p.stem.endswith("_thumb"))
    rng = random.Random(seed)
    chosen = rng.sample(photos, rng.randint(3, len(photos)))
    try:
        async with transaction({"sub": str(landlord), "role": "landlord"}) as tx:
            listing = await repo.create_draft(tx, landlord, fields["city"])
            before = as_draft(listing)
            after = ListingDraft.model_validate({**before.model_dump(), **fields})
            draft, _ = apply_patches(before, patches_from_form(before, after))
            listing = await repo.save_draft(tx, listing, draft, listing.version)
            point = await _random_point(tx, fields["locality_id"], seed)
            hit = await geo.locality_for(tx, point.lat, point.lng)
            assert hit is not None and hit.locality_id == fields["locality_id"], "pin fell outside its locality"
            listing = await repo.set_location(tx, listing, point, hit.locality_id, hit.city, None)
            for i, p in enumerate(chosen):
                path = f"{landlord}/{listing.id}/seed-{i}{p.suffix}"
                thumb = f"{landlord}/{listing.id}/seed-{i}_thumb{p.suffix}"
                if upload:
                    await _upload(path, p.read_bytes())
                    await _upload(thumb, p.with_name(p.stem + "_thumb" + p.suffix).read_bytes())
                await tx.conn.execute(
                    "insert into listing_photos (listing_id, storage_path, thumb_path, bytes, position, confirmed)"
                    " values (%s, %s, %s, %s, %s, true)",
                    (listing.id, path, thumb, p.stat().st_size, i),
                )
            listing = await repo.transition(tx, listing, "publish", landlord, reason="seed")
            async with tx.as_system():
                row = await tx.fetchone("select count(*) as n from listing_chunks where listing_id = %s",
                                        (listing.id,))
            chunks = int(row["n"]) if row else 0
            if listing.status != "published" or chunks == 0:
                raise RuntimeError(f"listing {listing.id} not published and embedded")
            if dry_run:
                raise _Rollback
    except _Rollback:
        pass
    return len(chosen), chunks


async def _upload(path: str, data: bytes) -> None:
    up = await get_storage().signed_upload(path)
    async with httpx.AsyncClient(timeout=60) as client:
        res = await client.put(up.url, content=data, headers={"content-type": "image/webp"})
        res.raise_for_status()


async def clear_previous(landlords: list[UUID]) -> int:
    async with transaction(system_claims()) as tx:
        rows = await tx.fetchall(
            "select p.storage_path, p.thumb_path from listing_photos p join listings l on l.id = p.listing_id"
            " where l.landlord_id = any(%s)", (landlords,))
        gone = await tx.fetchall("delete from listings where landlord_id = any(%s) returning id", (landlords,))
    storage = get_storage()
    for r in rows:
        for path in (r["storage_path"], r["thumb_path"]):
            try:
                await storage.delete(path)
            except Exception as exc:  # a missing object is fine
                print(f"  could not delete {path}: {exc}", flush=True)
    return len(gone)


async def main(count: int, seed: int, dry_run: bool) -> None:
    s = get_settings()
    password = os.environ.get("SEED_PASSWORD") or _dotenv("SEED_PASSWORD")
    if not (s.supabase_url and s.supabase_service_key and password):
        raise SystemExit("SUPABASE_URL, SUPABASE_SERVICE_KEY and SEED_PASSWORD are required")
    embedder = get_embedder()
    dispatcher_module.dispatcher = IndexNow(embedder)
    print(f"{'dry run' if dry_run else 'seeding'}: {count} listings, seed {seed}, embedder {embedder.name}", flush=True)
    started = time.monotonic()
    try:
        accounts = SeedAccounts(s.supabase_url, s.supabase_service_key, password)
        landlords = [await accounts.ensure(f"seed-landlord-{i:02d}@rentfit.test", "landlord", NAMES[i - 1])
                     for i in range(1, LANDLORDS + 1)]
        for i in range(1, TENANTS + 1):
            await accounts.ensure(f"seed-tenant-{i}@rentfit.test", "tenant", NAMES[LANDLORDS + i - 1])
        if not dry_run:
            print(f"removed {await clear_previous(landlords)} earlier seed listings", flush=True)
        async with transaction(system_claims()) as tx:
            locs = [dict(r) for r in await tx.fetchall(
                "select id, city, name, median_rent from localities order by city, name")]
        by_city: dict[str, list[dict[str, Any]]] = {}
        for loc in locs:
            by_city.setdefault(loc["city"], []).append(loc)
        rng = random.Random(seed)
        today = date.today()
        cities = sorted(by_city)
        photos = chunks = 0
        for n in range(count):
            loc = rng.choice(by_city[cities[n % len(cities)]])  # spread evenly over cities
            fields = generate(rng, loc, today)
            p, c = await write_listing(landlords[n % LANDLORDS], fields, seed * 100_000 + n,
                                       upload=not dry_run, dry_run=dry_run)
            photos, chunks = photos + p, chunks + c
            if (n + 1) % 25 == 0:
                print(f"  {n + 1}/{count}  ({time.monotonic() - started:.0f}s)", flush=True)
        verb = "built, verified and rolled back" if dry_run else "published"
        print(f"{count} listings {verb}: {photos} photos, {chunks} chunks embedded,"
              f" {time.monotonic() - started:.0f}s, 0 model calls")
    finally:
        await close_pool()


def _dotenv(key: str) -> str:
    env = Path(__file__).resolve().parents[1] / ".env"
    for line in env.read_text().splitlines() if env.exists() else []:
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return ""


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=50)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    asyncio.run(main(a.count, a.seed, a.dry_run))
