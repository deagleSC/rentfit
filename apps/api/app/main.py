"""FastAPI application: the only gateway to the database and the only caller of models."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.errors import Ok, install_error_handlers, ok


class Health(BaseModel):
    ok: bool
    version: str


VERSION = "0.1.0"


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="RentFit API", version=VERSION)
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

    return app


app = create_app()
