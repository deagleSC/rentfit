"""FastAPI application: the only gateway to the database and the only caller of models."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import inngest.fast_api
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.api.routers import dev_storage, me, reference
from app.api.routers.landlord import chat as landlord_chat
from app.api.routers.landlord import listings as landlord_listings
from app.api.routers.landlord import photos as landlord_photos
from app.core import monitoring
from app.core.config import get_settings
from app.core.db import close_pool
from app.core.errors import Ok, install_error_handlers, ok
from app.jobs.client import inngest_client
from app.jobs.functions import all_functions
from app.llm import tracing

log = logging.getLogger("rentfit")


class Health(BaseModel):
    ok: bool
    version: str


VERSION = "0.1.0"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    tracing.flush()
    await close_pool()


def create_app() -> FastAPI:
    settings = get_settings()
    monitoring.init(settings)
    app = FastAPI(title="RentFit API", version=VERSION, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=False,  # bearer tokens, no cookies
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type", "If-Match"],
    )
    install_error_handlers(app)

    @app.get("/health", response_model=Ok[Health], tags=["health"])
    async def health() -> Ok[Health]:
        return ok(Health(ok=True, version=VERSION))

    app.include_router(me.router)
    app.include_router(reference.router)
    app.include_router(landlord_listings.router)
    app.include_router(landlord_photos.router)
    app.include_router(landlord_chat.router)
    if settings.is_dev and not settings.supabase_service_key:
        app.include_router(dev_storage.router)

    # Inngest calls this endpoint to run function steps; it verifies request signatures in production.
    # Without a signing key in production, skip the endpoint rather than take the API down.
    if settings.is_dev or settings.inngest_signing_key:
        inngest.fast_api.serve(app, inngest_client, all_functions(), serve_path="/api/inngest")
    else:
        log.warning("INNGEST_SIGNING_KEY is not set: /api/inngest is disabled and background jobs will not run")
    for route in app.router.routes:  # internal transport, not part of the public API or generated client
        if getattr(route, "path", None) == "/api/inngest":
            route.include_in_schema = False  # type: ignore[attr-defined]
    app.openapi_schema = None
    return app


app = create_app()
