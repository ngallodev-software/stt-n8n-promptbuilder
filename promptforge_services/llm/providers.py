from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from promptforge_services.models import LLMProviderHealth, LLMTaskKind


class LLMProviderUnavailableError(RuntimeError):
    pass


@dataclass(slots=True)
class LLMReviewResult:
    provider_name: str
    model_name: str | None
    summary: str
    findings: tuple[str, ...] = ()
    latency_ms: int | None = None
    fallback_chain: tuple[str, ...] = ()
    raw_response: dict[str, Any] | None = None


@dataclass(slots=True)
class LLMGenerationResult:
    provider_name: str
    model_name: str | None
    structured_payload: dict[str, Any]
    latency_ms: int | None = None
    fallback_chain: tuple[str, ...] = ()
    raw_response: dict[str, Any] | None = None


class LLMProvider(Protocol):
    provider_name: str
    provider_family: str
    model_name: str | None
    base_url: str | None

    def health_check(self) -> LLMProviderHealth: ...

    def review_prompt(
        self,
        prompt_markdown: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> LLMReviewResult: ...

    def generate_structured(
        self,
        prompt_markdown: str,
        *,
        schema_name: str,
        context: dict[str, Any] | None = None,
    ) -> LLMGenerationResult: ...

    def supports(self, task_kind: LLMTaskKind) -> bool: ...


class BaseLLMProvider:
    def __init__(
        self,
        provider_name: str,
        provider_family: str,
        model_name: str | None,
        base_url: str | None,
        api_key: str | None = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        self.provider_name = provider_name
        self.provider_family = provider_family
        self.model_name = model_name
        self.base_url = base_url
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    def configured(self) -> bool:
        raise NotImplementedError

    def supports(self, task_kind: LLMTaskKind) -> bool:
        return True

    def health_check(self) -> LLMProviderHealth:
        configured = self.configured()
        detail = None if configured else "provider_not_configured"
        return LLMProviderHealth(
            provider_name=self.provider_name,
            provider_family=self.provider_family,
            configured=configured,
            available=configured,
            model_name=self.model_name,
            base_url=self.base_url,
            detail=detail,
        )

    def review_prompt(
        self,
        prompt_markdown: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> LLMReviewResult:
        raise LLMProviderUnavailableError(f"{self.provider_name} review is not wired yet")

    def generate_structured(
        self,
        prompt_markdown: str,
        *,
        schema_name: str,
        context: dict[str, Any] | None = None,
    ) -> LLMGenerationResult:
        raise LLMProviderUnavailableError(f"{self.provider_name} generation is not wired yet")


class OpenAIProvider(BaseLLMProvider):
    @classmethod
    def from_settings(
        cls,
        *,
        api_key: str | None,
        base_url: str | None,
        model_name: str | None,
        timeout_seconds: float,
        max_retries: int,
    ) -> "OpenAIProvider":
        return cls(
            provider_name="openai",
            provider_family="openai",
            model_name=model_name,
            base_url=base_url,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )

    def configured(self) -> bool:
        return bool(self.api_key and self.model_name and self.base_url)


class AnthropicProvider(BaseLLMProvider):
    @classmethod
    def from_settings(
        cls,
        *,
        api_key: str | None,
        base_url: str | None,
        model_name: str | None,
        timeout_seconds: float,
        max_retries: int,
    ) -> "AnthropicProvider":
        return cls(
            provider_name="anthropic",
            provider_family="anthropic",
            model_name=model_name,
            base_url=base_url,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )

    def configured(self) -> bool:
        return bool(self.api_key and self.model_name and self.base_url)


class OpenAICompatibleProvider(BaseLLMProvider):
    @classmethod
    def from_settings(
        cls,
        *,
        provider_name: str,
        base_url: str | None,
        api_key: str | None,
        model_name: str | None,
        timeout_seconds: float,
        max_retries: int,
    ) -> "OpenAICompatibleProvider":
        return cls(
            provider_name=provider_name,
            provider_family="openai_compatible",
            model_name=model_name,
            base_url=base_url,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )

    def configured(self) -> bool:
        return bool(self.base_url and self.model_name)

    def review_prompt(
        self,
        prompt_markdown: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> LLMReviewResult:
        response = self._chat_completion(
            messages=self._build_review_messages(prompt_markdown, context=context),
            json_mode=True,
        )
        content = self._extract_message_content(response)
        parsed = self._extract_json_object(content)
        if isinstance(parsed, dict):
            summary = self._stringify_review_summary(parsed) or content.strip()
            findings = self._normalize_findings(parsed.get("findings"))
        else:
            summary, findings = self._fallback_review_from_text(content)
        return LLMReviewResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            summary=summary,
            findings=findings,
            latency_ms=self._response_latency_ms(response),
            raw_response=response,
        )

    def generate_structured(
        self,
        prompt_markdown: str,
        *,
        schema_name: str,
        context: dict[str, Any] | None = None,
    ) -> LLMGenerationResult:
        response = self._chat_completion(
            messages=self._build_generation_messages(
                prompt_markdown,
                schema_name=schema_name,
                context=context,
            ),
            json_mode=True,
        )
        content = self._extract_message_content(response)
        payload = self._extract_json_object(content)
        if not isinstance(payload, dict):
            raise LLMProviderUnavailableError(
                f"{self.provider_name} did not return a JSON object for schema {schema_name}"
            )
        return LLMGenerationResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            structured_payload=payload,
            latency_ms=self._response_latency_ms(response),
            raw_response=response,
        )

    def _chat_completion(
        self,
        *,
        messages: list[dict[str, str]],
        json_mode: bool,
    ) -> dict[str, Any]:
        if not self.base_url or not self.model_name:
            raise LLMProviderUnavailableError(f"{self.provider_name} is not configured")

        url = self._chat_endpoint()
        payload: dict[str, Any]
        if self._uses_openai_compatibility():
            payload = {
                "model": self.model_name,
                "messages": messages,
                "temperature": 0,
                "stream": False,
            }
        else:
            payload = {
                "model": self.model_name,
                "messages": messages,
                "options": {"temperature": 0},
                "stream": False,
            }
            if json_mode:
                payload["format"] = "json"

        headers = self._request_headers()
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            start = time.monotonic()
            try:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.post(url, json=payload, headers=headers)
                    response.raise_for_status()
                    result = response.json()
                    if isinstance(result, dict):
                        result.setdefault("_promptforge_latency_ms", self._elapsed_ms(start))
                        return result
                    raise LLMProviderUnavailableError(
                        f"{self.provider_name} returned a non-object response"
                    )
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                time.sleep(self._retry_delay_seconds(attempt))
            except ValueError as exc:
                raise LLMProviderUnavailableError(
                    f"{self.provider_name} returned invalid JSON"
                ) from exc

        raise LLMProviderUnavailableError(
            f"{self.provider_name} request failed after {self.max_retries + 1} attempts"
        ) from last_error

    def _build_review_messages(
        self,
        prompt_markdown: str,
        *,
        context: dict[str, Any] | None,
    ) -> list[dict[str, str]]:
        user_content = prompt_markdown.strip()
        if context:
            user_content = "\n\n".join(
                [user_content, f"Context:\n{json.dumps(context, ensure_ascii=False, sort_keys=True)}"]
            )
        return [
            {
                "role": "system",
                "content": (
                    "You are reviewing a prompt for clarity, correctness, and risk. "
                    "Return a JSON object with keys summary (string) and findings (array of strings). "
                    "Keep the summary concise and the findings specific."
                ),
            },
            {"role": "user", "content": user_content},
        ]

    def _build_generation_messages(
        self,
        prompt_markdown: str,
        *,
        schema_name: str,
        context: dict[str, Any] | None,
    ) -> list[dict[str, str]]:
        user_content = prompt_markdown.strip()
        if context:
            user_content = "\n\n".join(
                [user_content, f"Context:\n{json.dumps(context, ensure_ascii=False, sort_keys=True)}"]
            )
        return [
            {
                "role": "system",
                "content": (
                    "You convert instructions into one valid JSON object. "
                    "Return JSON only, with no markdown fences or commentary. "
                    f"The target schema name is {schema_name}."
                ),
            },
            {"role": "user", "content": user_content},
        ]

    def _request_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _chat_endpoint(self) -> str:
        assert self.base_url is not None
        base_url = self.base_url.rstrip("/")
        if self._uses_openai_compatibility():
            return f"{base_url}/chat/completions"
        if base_url.endswith("/api"):
            return f"{base_url}/chat"
        return f"{base_url}/api/chat"

    def _uses_openai_compatibility(self) -> bool:
        assert self.base_url is not None
        return self.base_url.rstrip("/").endswith("/v1")

    @staticmethod
    def _elapsed_ms(start_time: float) -> int:
        return max(0, int((time.monotonic() - start_time) * 1000))

    def _response_latency_ms(self, response: dict[str, Any]) -> int | None:
        raw_latency = response.get("_promptforge_latency_ms")
        return int(raw_latency) if isinstance(raw_latency, int) else None

    def _retry_delay_seconds(self, attempt: int) -> float:
        return min(0.5 * (2**attempt), 2.0)

    @staticmethod
    def _extract_message_content(response: dict[str, Any]) -> str:
        if "choices" in response:
            choices = response.get("choices") or []
            if choices:
                first = choices[0] or {}
                message = first.get("message") or {}
                content = message.get("content")
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    return "".join(
                        part.get("text", "") for part in content if isinstance(part, dict)
                    )
        message = response.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                return content
        content = response.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(part.get("text", "") for part in content if isinstance(part, dict))
        return ""

    @staticmethod
    def _extract_json_object(text: str) -> dict[str, Any] | None:
        stripped = text.strip()
        if not stripped:
            return None

        fence_match = re.search(r"```(?:json)?\s*(?P<body>\{.*\})\s*```", stripped, re.DOTALL)
        if fence_match:
            candidate = fence_match.group("body").strip()
            parsed = OpenAICompatibleProvider._parse_json_candidate(candidate)
            if isinstance(parsed, dict):
                return parsed

        parsed = OpenAICompatibleProvider._parse_json_candidate(stripped)
        if isinstance(parsed, dict):
            return parsed

        for match in re.finditer(r"\{", stripped):
            candidate = stripped[match.start() :]
            parsed = OpenAICompatibleProvider._parse_json_candidate(candidate)
            if isinstance(parsed, dict):
                return parsed
        return None

    @staticmethod
    def _parse_json_candidate(candidate: str) -> Any:
        decoder = json.JSONDecoder()
        try:
            parsed, _ = decoder.raw_decode(candidate.lstrip())
        except json.JSONDecodeError:
            return None
        return parsed

    @staticmethod
    def _stringify_review_summary(parsed: dict[str, Any]) -> str:
        for key in ("summary", "review", "result", "message"):
            value = parsed.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        findings = OpenAICompatibleProvider._normalize_findings(parsed.get("findings"))
        if findings:
            return findings[0]
        return ""

    @staticmethod
    def _normalize_findings(value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            text = value.strip()
            return (text,) if text else ()
        if isinstance(value, list):
            findings: list[str] = []
            for item in value:
                if isinstance(item, str):
                    text = item.strip()
                else:
                    text = str(item).strip()
                if text:
                    findings.append(text)
            return tuple(findings)
        return (str(value).strip(),) if str(value).strip() else ()

    @staticmethod
    def _fallback_review_from_text(text: str) -> tuple[str, tuple[str, ...]]:
        cleaned = text.strip()
        if not cleaned:
            return "", ()

        lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
        findings = tuple(
            line.lstrip("-* ").strip()
            for line in lines[1:]
            if line.startswith(("-", "*"))
        )
        if findings:
            findings = tuple(item for item in findings if item)
        summary = lines[0] if lines else cleaned
        return summary, findings


class OllamaProvider(OpenAICompatibleProvider):
    @classmethod
    def from_settings(
        cls,
        *,
        base_url: str | None,
        api_key: str | None,
        model_name: str | None,
        timeout_seconds: float,
        max_retries: int,
    ) -> "OllamaProvider":
        return cls(
            provider_name="ollama",
            provider_family="ollama",
            model_name=model_name,
            base_url=base_url,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )

    def configured(self) -> bool:
        return bool(self.base_url and self.model_name)
