"""Role → ordered model list (backend plan §10)."""

from __future__ import annotations

from typing import Literal

from app.core.config import Settings, get_settings
from app.llm.errors import LLMNotConfigured

ModelRole = Literal["structured", "chat"]


def models_for(role: ModelRole, settings: Settings | None = None) -> list[str]:
    """Models for a role, first choice first. OpenRouter falls back down the list."""
    s = settings or get_settings()
    models = list(s.llm_structured_models if role == "structured" else s.llm_chat_models)
    if not models:
        raise LLMNotConfigured(f"No models configured for role '{role}'")
    return models


def provider_prefs() -> dict[str, object]:
    """OpenRouter provider routing: never send prompts to hosts that may train on them."""
    return {"allow_fallbacks": True, "data_collection": "deny"}
