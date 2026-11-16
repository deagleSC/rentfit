"""All runtime configuration, read from environment variables (backend plan §16)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["dev", "test", "prod"] = "dev"

    # Supavisor transaction-mode URL in production, user rentfit_api (never the service role).
    database_url: str = "postgresql://rentfit_api:dev@localhost:54322/postgres"
    # Inngest functions connect as rentfit_jobs.
    database_url_jobs: str = "postgresql://rentfit_jobs:dev@localhost:54322/postgres"
    db_pool_max: int = 5

    # Token verification: JWKS from SUPABASE_URL; legacy projects also set SUPABASE_JWT_SECRET.
    supabase_url: str = ""
    supabase_jwt_secret: str = ""
    supabase_jwt_aud: str = "authenticated"

    # Landlord :3000, tenant :3001, marketing :3002 (marketing does not call the API).
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000", "http://localhost:3001"])
    # Extra allowed origins as a regex, e.g. Vercel preview deployments of the two apps.
    cors_origin_regex: str | None = None

    # Supabase Storage: the service key is used only for signed photo URLs, never for the database.
    supabase_service_key: str = ""
    photo_bucket: str = "listing-photos"
    photo_max_bytes: int = 5 * 1024 * 1024
    # This API's own URL as browsers reach it (dev/test in-memory storage serves uploads from here).
    public_api_url: str = "http://127.0.0.1:8000"
    photos_min: int = 3
    photos_max: int = 15

    # Background jobs: "inline" (dev/test) runs each function in-process right after commit.
    job_dispatcher: Literal["inngest", "inline"] = "inngest"
    inngest_event_key: str = ""
    inngest_signing_key: str = ""

    # Embeddings Edge Function. Without a URL (dev/test), a deterministic hashing embedder.
    embed_function_url: str = ""
    embed_function_key: str = ""

    # LLM (backend plan §10). "fake" (dev default, tests, e2e) never calls a network model.
    llm_provider: Literal["openrouter", "fake"] = "fake"
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_structured_models: list[str] = Field(
        default_factory=lambda: ["google/gemma-4-26b-a4b-it", "google/gemma-4-31b-it"]
    )
    llm_chat_models: list[str] = Field(
        default_factory=lambda: ["google/gemma-4-26b-a4b-it", "google/gemma-4-31b-it"]
    )
    llm_daily_cap: int = 300
    llm_rpm_cap: int = 20
    llm_sync_rpm_cap: int = 10
    llm_request_timeout_s: float = 60.0

    # Commute (backend plan §13.1). Without a key, the haversine estimate is used.
    ors_api_key: str = ""

    # Tracing and errors: off unless set.
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = Field(
        default="https://cloud.langfuse.com", validation_alias=AliasChoices("LANGFUSE_BASE_URL", "LANGFUSE_HOST")
    )
    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 0.1
    release: str = Field(default="", validation_alias=AliasChoices("VERCEL_GIT_COMMIT_SHA", "RELEASE"))

    @property
    def is_dev(self) -> bool:
        return self.app_env in ("dev", "test")

    @property
    def jwks_url(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"

    @property
    def jwt_issuer(self) -> str | None:
        return f"{self.supabase_url.rstrip('/')}/auth/v1" if self.supabase_url else None


@lru_cache
def get_settings() -> Settings:
    return Settings()
