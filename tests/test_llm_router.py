from __future__ import annotations

import unittest
from unittest.mock import patch

from promptforge_services.llm.config import LLMSettings, normalize_provider_name
from promptforge_services.llm.providers import (
    LLMGenerationResult,
    LLMProviderHealth,
    LLMProviderUnavailableError,
    LLMReviewResult,
    OpenAICompatibleProvider,
    OllamaProvider,
)
from promptforge_services.llm.router import LLMRouter


class DummyProvider:
    def __init__(
        self,
        provider_name: str,
        *,
        provider_family: str = "dummy",
        configured: bool = True,
        model_name: str | None = "dummy-model",
        base_url: str | None = "http://example.test",
    ) -> None:
        self.provider_name = provider_name
        self.provider_family = provider_family
        self._configured = configured
        self.model_name = model_name
        self.base_url = base_url
        self.review_calls: list[str] = []
        self.inference_calls: list[str] = []

    def configured(self) -> bool:
        return self._configured

    def supports(self, task_kind: str) -> bool:
        return True

    def health_check(self) -> LLMProviderHealth:
        return LLMProviderHealth(
            provider_name=self.provider_name,
            provider_family=self.provider_family,
            configured=self._configured,
            available=self._configured,
            model_name=self.model_name,
            base_url=self.base_url,
        )

    def review_prompt(self, prompt_markdown: str, *, context: dict | None = None) -> LLMReviewResult:
        self.review_calls.append(prompt_markdown)
        return LLMReviewResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            summary=f"review:{self.provider_name}",
            findings=("dummy-finding",),
        )

    def generate_structured(
        self,
        prompt_markdown: str,
        *,
        schema_name: str,
        context: dict | None = None,
    ) -> LLMGenerationResult:
        self.inference_calls.append(prompt_markdown)
        return LLMGenerationResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            structured_payload={"schema_name": schema_name, "provider": self.provider_name},
        )


class LLMRouterTests(unittest.TestCase):
    def test_settings_from_env_parses_llm_contract(self) -> None:
        settings = LLMSettings.from_env(
            {
                "PROMPTFORGE_LLM_ENABLED": "true",
                "PROMPTFORGE_LLM_MODE": "llm_inference_optional",
                "PROMPTFORGE_LLM_REVIEW_PROVIDER": "ollama",
                "PROMPTFORGE_LLM_INFERENCE_PROVIDER": "anthropic",
                "PROMPTFORGE_LLM_TIMEOUT_SECONDS": "12.5",
                "PROMPTFORGE_LLM_MAX_RETRIES": "4",
                "PROMPTFORGE_LLM_FALLBACK_PROVIDERS": "openai_compatible,anthropic",
                "PROMPTFORGE_OLLAMA_BASE_URL": "http://localhost:11434",
                "PROMPTFORGE_OLLAMA_MODEL": "llama3.1",
                "PROMPTFORGE_OPENAI_COMPAT_BASE_URL": "http://localhost:11434/v1",
                "PROMPTFORGE_OPENAI_COMPAT_MODEL": "llama3.1",
            }
        )

        self.assertTrue(settings.enabled)
        self.assertEqual(settings.mode, "llm_inference_optional")
        self.assertEqual(settings.review_provider, "ollama")
        self.assertEqual(settings.inference_provider, "anthropic")
        self.assertEqual(settings.timeout_seconds, 12.5)
        self.assertEqual(settings.max_retries, 4)
        self.assertEqual(settings.fallback_providers, ("openai_compatible", "anthropic"))
        self.assertEqual(settings.ollama_base_url, "http://localhost:11434")
        self.assertEqual(settings.ollama_model, "llama3.1")
        self.assertEqual(settings.openai_compat_base_url, "http://localhost:11434/v1")
        self.assertEqual(settings.openai_compat_model, "llama3.1")
        self.assertEqual(normalize_provider_name("ollama"), "ollama")
        self.assertEqual(normalize_provider_name("llamacpp"), "openai_compatible")

    def test_router_selects_configured_provider_with_fallback(self) -> None:
        settings = LLMSettings(
            enabled=True,
            mode="llm_inference_optional",
            review_provider="ollama",
            inference_provider="openai",
            fallback_providers=("openai_compatible", "anthropic"),
            ollama_base_url="http://localhost:11434",
            ollama_model="llama3.1",
        )
        providers = {
            "openai": DummyProvider("openai", configured=False),
            "anthropic": DummyProvider("anthropic", configured=True),
            "openai_compatible": DummyProvider("openai_compatible", configured=True),
            "ollama": DummyProvider("ollama", provider_family="ollama", configured=True),
        }
        router = LLMRouter(settings=settings, providers=providers)

        review_provider = router.select_provider("review")
        inference_provider = router.select_provider("inference")

        self.assertIsNotNone(review_provider)
        self.assertEqual(review_provider.provider_name, "ollama")
        self.assertIsNotNone(inference_provider)
        self.assertEqual(inference_provider.provider_name, "openai_compatible")

        review_result = router.review_prompt("check this prompt")
        inference_result = router.generate_structured("build a draft", schema_name="agent_task_v1")

        self.assertIsNotNone(review_result)
        self.assertEqual(review_result.provider_name, "ollama")
        self.assertIsNotNone(inference_result)
        self.assertEqual(inference_result.structured_payload["schema_name"], "agent_task_v1")

        health = router.health_report()
        self.assertEqual(
            {provider.provider_name: (provider.provider_family, provider.configured) for provider in health.providers},
            {
                "anthropic": ("dummy", True),
                "ollama": ("ollama", True),
                "openai": ("dummy", False),
                "openai_compatible": ("dummy", True),
            },
        )

    def test_router_disables_task_kinds_in_deterministic_only_mode(self) -> None:
        router = LLMRouter(
            settings=LLMSettings(enabled=True, mode="deterministic_only"),
            providers={"openai_compatible": DummyProvider("openai_compatible")},
        )

        self.assertIsNone(router.select_provider("review"))
        self.assertIsNone(router.select_provider("inference"))
        self.assertIsNone(router.review_prompt("check this prompt"))
        self.assertIsNone(router.generate_structured("build a draft", schema_name="agent_task_v1"))

    def test_openai_compatible_provider_parses_review_and_structured_json(self) -> None:
        provider = OpenAICompatibleProvider.from_settings(
            provider_name="openai_compatible",
            base_url="http://localhost:11434/v1",
            api_key="test-key",
            model_name="llama3.1",
            timeout_seconds=3.0,
            max_retries=0,
        )
        responses = iter(
            [
                {
                    "message": {
                        "content": (
                            '{"summary":"Prompt is clear","findings":["tighten the target name","add one test"]}'
                        )
                    },
                    "_promptforge_latency_ms": 11,
                },
                {
                    "choices": [
                        {
                            "message": {
                                "content": (
                                    "Here is the JSON payload:\n"
                                    "```json\n"
                                    '{"contract_name":"agent_task_v1","intent":"agent_task","project_slug":"demo","prompt_type":"coding-cli","destination":"cli","target_identifier":"claude-tax-main","mode":"queue","final_prompt_markdown":"Investigate the retry state transitions.","requires_review":false,"notes":[]}'
                                    "\n```"
                                )
                            }
                        }
                    ],
                    "_promptforge_latency_ms": 18,
                },
            ]
        )

        with patch.object(provider, "_chat_completion", side_effect=lambda **_: next(responses)):
            review = provider.review_prompt("Check this prompt")
            structured = provider.generate_structured(
                "Build a draft",
                schema_name="agent_task_v1",
            )

        self.assertEqual(review.provider_name, "openai_compatible")
        self.assertEqual(review.summary, "Prompt is clear")
        self.assertEqual(review.findings, ("tighten the target name", "add one test"))
        self.assertEqual(structured.provider_name, "openai_compatible")
        self.assertEqual(structured.structured_payload["contract_name"], "agent_task_v1")
        self.assertEqual(structured.structured_payload["project_slug"], "demo")

    def test_ollama_provider_uses_native_chat_endpoint(self) -> None:
        provider = OllamaProvider.from_settings(
            base_url="http://localhost:11434",
            api_key=None,
            model_name="llama3.1",
            timeout_seconds=3.0,
            max_retries=0,
        )
        review_response = {
            "message": {
                "content": '{"summary":"Prompt is clear","findings":["tighten the target name","add one test"]}',
            },
            "_promptforge_latency_ms": 9,
        }
        structured_response = {
            "message": {
                "content": (
                    '{"contract_name":"agent_task_v1","intent":"agent_task","project_slug":"demo",'
                    '"prompt_type":"coding-cli","destination":"cli","target_identifier":"claude-tax-main",'
                    '"mode":"queue","final_prompt_markdown":"Investigate the retry state transitions.",'
                    '"requires_review":false,"notes":[]}'
                ),
            },
            "_promptforge_latency_ms": 14,
        }
        response_iter = iter([review_response, structured_response])
        post_calls: list[tuple[str, dict, dict]] = []

        def client_factory(*_: object, **__: object) -> object:
            client = unittest.mock.MagicMock()
            client.__enter__.return_value = client

            def post(url: str, *, json: dict, headers: dict) -> object:
                post_calls.append((url, json, headers))
                response = unittest.mock.MagicMock()
                response.raise_for_status.return_value = None
                response.json.return_value = next(response_iter)
                return response

            client.post.side_effect = post
            return client

        with patch("promptforge_services.llm.providers.httpx.Client", side_effect=client_factory):
            review = provider.review_prompt("Check this prompt")
            structured = provider.generate_structured("Build a draft", schema_name="agent_task_v1")

        self.assertEqual(review.provider_name, "ollama")
        self.assertEqual(review.summary, "Prompt is clear")
        self.assertEqual(review.findings, ("tighten the target name", "add one test"))
        self.assertEqual(structured.provider_name, "ollama")
        self.assertEqual(structured.structured_payload["contract_name"], "agent_task_v1")
        self.assertEqual(structured.structured_payload["project_slug"], "demo")
        self.assertEqual(
            post_calls,
            [
                (
                    "http://localhost:11434/api/chat",
                    {
                        "model": "llama3.1",
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "You are reviewing a prompt for clarity, correctness, and risk. "
                                    "Return a JSON object with keys summary (string) and findings (array of strings). "
                                    "Keep the summary concise and the findings specific."
                                ),
                            },
                            {"role": "user", "content": "Check this prompt"},
                        ],
                        "options": {"temperature": 0},
                        "stream": False,
                        "format": "json",
                    },
                    {"Content-Type": "application/json"},
                ),
                (
                    "http://localhost:11434/api/chat",
                    {
                        "model": "llama3.1",
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "You convert instructions into one valid JSON object. "
                                    "Return JSON only, with no markdown fences or commentary. "
                                    "The target schema name is agent_task_v1."
                                ),
                            },
                            {"role": "user", "content": "Build a draft"},
                        ],
                        "options": {"temperature": 0},
                        "stream": False,
                        "format": "json",
                    },
                    {"Content-Type": "application/json"},
                ),
            ],
        )

    def test_router_returns_none_when_provider_fails(self) -> None:
        class FailingProvider(DummyProvider):
            def review_prompt(self, prompt_markdown: str, *, context: dict | None = None) -> LLMReviewResult:
                raise LLMProviderUnavailableError("unavailable")

            def generate_structured(
                self,
                prompt_markdown: str,
                *,
                schema_name: str,
                context: dict | None = None,
            ) -> LLMGenerationResult:
                raise ValueError("invalid payload")

        router = LLMRouter(
            settings=LLMSettings(enabled=True, mode="llm_inference_optional"),
            providers={"openai_compatible": FailingProvider("openai_compatible")},
        )

        self.assertIsNone(router.review_prompt("check this prompt"))
        self.assertIsNone(router.generate_structured("build a draft", schema_name="agent_task_v1"))


if __name__ == "__main__":
    unittest.main()
