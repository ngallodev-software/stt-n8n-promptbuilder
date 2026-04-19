from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from promptforge_services.llm.config import (
    DEFAULT_FALLBACK_PROVIDERS,
    LLMSettings,
    normalize_provider_name,
)
from promptforge_services.llm.providers import (
    AnthropicProvider,
    CodexExecProvider,
    LLMGenerationResult,
    LLMProvider,
    LLMProviderUnavailableError,
    LLMReviewResult,
    OpenAICompatibleProvider,
    OpenAIProvider,
    OllamaProvider,
)
from promptforge_services.models import LLMProviderHealth, LLMProvidersHealthResponse, LLMTaskKind


class LLMRouter:
    def __init__(
        self,
        settings: LLMSettings | None = None,
        providers: Mapping[str, LLMProvider] | None = None,
    ) -> None:
        self.settings = settings or LLMSettings.from_env()
        self._providers = dict(providers) if providers is not None else self._build_providers(self.settings)

    @property
    def enabled(self) -> bool:
        return self.settings.enabled and self.settings.mode != "deterministic_only"

    def supports(self, task_kind: LLMTaskKind) -> bool:
        if not self.enabled:
            return False
        if self.settings.mode == "deterministic_plus_review":
            return task_kind == "review"
        return True

    def select_provider(self, task_kind: LLMTaskKind) -> LLMProvider | None:
        if not self.supports(task_kind):
            return None

        preferred = (
            self.settings.review_provider if task_kind == "review" else self.settings.inference_provider
        )
        selection_order = self._selection_order(preferred)
        for provider_name in selection_order:
            provider = self._providers.get(provider_name)
            if provider is not None and provider.configured() and provider.supports(task_kind):
                return provider
        return None

    def review_prompt(
        self,
        prompt_markdown: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> LLMReviewResult | None:
        provider = self.select_provider("review")
        if provider is None:
            return None
        try:
            return provider.review_prompt(prompt_markdown, context=context)
        except (LLMProviderUnavailableError, ValueError):
            return None

    def generate_structured(
        self,
        prompt_markdown: str,
        *,
        schema_name: str,
        context: dict[str, Any] | None = None,
    ) -> LLMGenerationResult | None:
        provider = self.select_provider("inference")
        if provider is None:
            return None
        try:
            return provider.generate_structured(
                prompt_markdown,
                schema_name=schema_name,
                context=context,
            )
        except (LLMProviderUnavailableError, ValueError):
            return None

    def health_report(self) -> LLMProvidersHealthResponse:
        providers = [provider.health_check() for provider in self._providers.values()]
        providers.sort(key=lambda item: (item.provider_family, item.provider_name))
        return LLMProvidersHealthResponse(
            enabled=self.settings.enabled,
            mode=self.settings.mode,
            review_provider=self.settings.review_provider,
            inference_provider=self.settings.inference_provider,
            providers=providers,
        )

    def _selection_order(self, preferred: str | None) -> list[str]:
        normalized_preferred = normalize_provider_name(preferred)
        fallback = [normalize_provider_name(name) for name in self.settings.fallback_providers]
        selection_order: list[str] = []
        for candidate in (normalized_preferred, *fallback):
            if candidate and candidate not in selection_order:
                selection_order.append(candidate)
        for candidate in DEFAULT_FALLBACK_PROVIDERS:
            if candidate not in selection_order:
                selection_order.append(candidate)
        return selection_order

    @staticmethod
    def _build_providers(settings: LLMSettings) -> dict[str, LLMProvider]:
        providers: dict[str, LLMProvider] = {}
        providers["openai"] = OpenAIProvider.from_settings(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model_name=settings.openai_model or settings.default_model,
            timeout_seconds=settings.timeout_seconds,
            max_retries=settings.max_retries,
        )
        providers["anthropic"] = AnthropicProvider.from_settings(
            api_key=settings.anthropic_api_key,
            base_url=settings.anthropic_base_url,
            model_name=settings.anthropic_model or settings.default_model,
            timeout_seconds=settings.timeout_seconds,
            max_retries=settings.max_retries,
        )
        providers["openai_compatible"] = OpenAICompatibleProvider.from_settings(
            provider_name="openai_compatible",
            base_url=settings.openai_compat_base_url,
            api_key=settings.openai_compat_api_key,
            model_name=settings.openai_compat_model or settings.default_model,
            timeout_seconds=settings.timeout_seconds,
            max_retries=settings.max_retries,
        )
        providers["ollama"] = OllamaProvider.from_settings(
            base_url=settings.ollama_base_url,
            api_key=settings.ollama_api_key,
            model_name=settings.ollama_model or settings.default_model,
            timeout_seconds=settings.timeout_seconds,
            max_retries=settings.max_retries,
        )
        providers["codex_exec"] = CodexExecProvider.from_settings(
            binary=settings.codex_binary,
            model_name=settings.codex_model,
            reasoning_effort=settings.codex_reasoning_effort,
            timeout_seconds=settings.timeout_seconds,
            max_retries=settings.max_retries,
        )
        return providers


def get_llm_router(settings: LLMSettings | None = None) -> LLMRouter:
    return LLMRouter(settings=settings)


def llm_health_report(settings: LLMSettings | None = None) -> LLMProvidersHealthResponse:
    return get_llm_router(settings=settings).health_report()
