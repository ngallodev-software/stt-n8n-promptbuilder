from __future__ import annotations

import os
from typing import Mapping

from pydantic import BaseModel, Field

from promptforge_services.models import LLMMode

DEFAULT_FALLBACK_PROVIDERS: tuple[str, ...] = ("openai_compatible", "openai", "anthropic")

OPENAI_COMPATIBLE_ALIASES = {
    "openai-compatible": "openai_compatible",
    "openai compatible": "openai_compatible",
    "lmstudio": "openai_compatible",
    "llamacpp": "openai_compatible",
}


def _string_or_none(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _env_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    text = value.strip()
    return int(text) if text else default


def _env_float(value: str | None, default: float) -> float:
    if value is None:
        return default
    text = value.strip()
    return float(text) if text else default


def _split_csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())


def normalize_provider_name(provider_name: str | None) -> str | None:
    if provider_name is None:
        return None
    normalized = provider_name.strip().lower()
    if not normalized:
        return None
    return OPENAI_COMPATIBLE_ALIASES.get(normalized, normalized)


class LLMSettings(BaseModel):
    enabled: bool = False
    mode: LLMMode = "deterministic_only"
    review_provider: str | None = None
    inference_provider: str | None = None
    fallback_providers: tuple[str, ...] = Field(default_factory=lambda: DEFAULT_FALLBACK_PROVIDERS)
    timeout_seconds: float = 30.0
    max_retries: int = 2
    default_model: str | None = None
    openai_api_key: str | None = None
    openai_base_url: str | None = "https://api.openai.com/v1"
    openai_model: str | None = None
    anthropic_api_key: str | None = None
    anthropic_base_url: str | None = "https://api.anthropic.com"
    anthropic_model: str | None = None
    openai_compat_base_url: str | None = None
    openai_compat_api_key: str | None = None
    openai_compat_model: str | None = None
    ollama_base_url: str | None = "http://localhost:11434"
    ollama_api_key: str | None = None
    ollama_model: str | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "LLMSettings":
        source = os.environ if env is None else env
        fallback_providers = _split_csv(source.get("PROMPTFORGE_LLM_FALLBACK_PROVIDERS"))
        return cls(
            enabled=_env_bool(source.get("PROMPTFORGE_LLM_ENABLED"), default=False),
            mode=source.get("PROMPTFORGE_LLM_MODE", "deterministic_only").strip()
            or "deterministic_only",
            review_provider=_string_or_none(source.get("PROMPTFORGE_LLM_REVIEW_PROVIDER")),
            inference_provider=_string_or_none(source.get("PROMPTFORGE_LLM_INFERENCE_PROVIDER")),
            fallback_providers=fallback_providers or DEFAULT_FALLBACK_PROVIDERS,
            timeout_seconds=_env_float(source.get("PROMPTFORGE_LLM_TIMEOUT_SECONDS"), default=30.0),
            max_retries=_env_int(source.get("PROMPTFORGE_LLM_MAX_RETRIES"), default=2),
            default_model=_string_or_none(source.get("PROMPTFORGE_DEFAULT_MODEL")),
            openai_api_key=_string_or_none(source.get("OPENAI_API_KEY")),
            openai_base_url=_string_or_none(source.get("OPENAI_BASE_URL")) or "https://api.openai.com/v1",
            openai_model=_string_or_none(source.get("OPENAI_MODEL")),
            anthropic_api_key=_string_or_none(source.get("ANTHROPIC_API_KEY")),
            anthropic_base_url=_string_or_none(source.get("ANTHROPIC_BASE_URL")) or "https://api.anthropic.com",
            anthropic_model=_string_or_none(source.get("ANTHROPIC_MODEL")),
            openai_compat_base_url=_string_or_none(source.get("PROMPTFORGE_OPENAI_COMPAT_BASE_URL")),
            openai_compat_api_key=_string_or_none(source.get("PROMPTFORGE_OPENAI_COMPAT_API_KEY")),
            openai_compat_model=_string_or_none(source.get("PROMPTFORGE_OPENAI_COMPAT_MODEL")),
            ollama_base_url=_string_or_none(source.get("PROMPTFORGE_OLLAMA_BASE_URL")) or "http://localhost:11434",
            ollama_api_key=_string_or_none(source.get("PROMPTFORGE_OLLAMA_API_KEY")),
            ollama_model=_string_or_none(source.get("PROMPTFORGE_OLLAMA_MODEL")),
        )
