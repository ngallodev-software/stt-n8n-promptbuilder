# PromptForge Multi-Provider LLM Support Plan

## Goal

Add optional LLM-backed text/prompt review and inference to PromptForge while preserving deterministic baseline behavior.

Support providers:

- Local/LAN-hosted: Ollama, LM Studio, llama.cpp server (OpenAI-compatible), and other OpenAI-compatible endpoints.
- Hosted APIs: OpenAI and Anthropic.

## Non-Goals (Phase 1)

- Replacing deterministic preprocess/validate path as default.
- Building a full prompt orchestration UI.
- Fine-tuning or model hosting automation.

## Product Modes

PromptForge should support three execution modes:

1. `deterministic_only` (default): current behavior.
2. `deterministic_plus_review`: deterministic output + optional LLM critique/review metadata.
3. `llm_inference_optional`: LLM assists generation, then contract validation gate still enforces schema.

## Architecture Changes

## 1) Provider Abstraction

Introduce provider-neutral interface in new module, e.g. `promptforge_services/llm/`:

- `LLMProvider` protocol/interface
- `generate_structured(...)`
- `review_prompt(...)`
- `health_check(...)`

Implementations:

- `OpenAIProvider`
- `AnthropicProvider`
- `OpenAICompatibleProvider` (base for Ollama/LM Studio/llama.cpp HTTP endpoints)

## 2) Runtime Router

Add `LLMRouter` that selects provider based on config:

- provider name
- task kind (`review` or `inference`)
- fallback order
- timeout and retry policy

## 3) Pipeline Integration

Add optional hooks in pipeline stages:

- post-render review hook (`review_prompt`) for quality/risk feedback
- optional inference hook to produce initial structured payload prior to deterministic validation

Contract validator remains hard gate.

## 4) Data Model Extensions

Extend storage records (or add companion tables) for traceability:

- provider id/name
- model id
- request mode (`review`/`inference`)
- latency ms
- token usage (if available)
- fallback chain used
- review findings summary

## Configuration Contract

Add environment config (example names):

- `PROMPTFORGE_LLM_ENABLED=false`
- `PROMPTFORGE_LLM_MODE=deterministic_only|deterministic_plus_review|llm_inference_optional`
- `PROMPTFORGE_LLM_REVIEW_PROVIDER=openai|anthropic|ollama|lmstudio|llamacpp|openai_compatible`
- `PROMPTFORGE_LLM_INFERENCE_PROVIDER=...`
- `PROMPTFORGE_LLM_TIMEOUT_SECONDS=30`
- `PROMPTFORGE_LLM_MAX_RETRIES=2`

Provider-specific:

- OpenAI:
  - `OPENAI_API_KEY`
  - `OPENAI_BASE_URL` (optional)
  - `OPENAI_MODEL`
- Anthropic:
  - `ANTHROPIC_API_KEY`
  - `ANTHROPIC_MODEL`
- OpenAI-compatible local endpoints (Ollama, LM Studio, llama.cpp server):
  - `PROMPTFORGE_OPENAI_COMPAT_BASE_URL`
  - `PROMPTFORGE_OPENAI_COMPAT_API_KEY` (optional)
  - `PROMPTFORGE_OPENAI_COMPAT_MODEL`
- Ollama native or bridged:
  - `PROMPTFORGE_OLLAMA_BASE_URL` (defaults to `http://localhost:11434`)
  - `PROMPTFORGE_OLLAMA_API_KEY` (optional, for proxy setups)
  - `PROMPTFORGE_OLLAMA_MODEL`

## Provider Mapping Notes

- Ollama: use the native provider by default; it still speaks OpenAI-compatible `/v1` when pointed at a bridge endpoint.
- LM Studio: supports OpenAI-compatible API; use `OpenAICompatibleProvider`.
- llama.cpp server: use OpenAI-compatible API mode if enabled.

## Reliability + Safety

- Keep deterministic path as baseline fallback.
- If LLM fails, continue with deterministic-only flow unless hard-required by selected mode.
- Validate all LLM outputs against existing `agent_task_v1` contract before persist/delivery.
- Log prompt/output hashes and redact secrets in logs.

## API Surface Additions (Proposed)

Optional endpoints:

- `POST /review` for prompt review results
- `POST /inference` for optional structured draft generation
- `GET /providers/health` for provider reachability checks

## Testing Strategy

- Unit tests for provider adapters and router fallback behavior.
- Contract tests for OpenAI-compatible provider using mocked HTTP responses.
- Integration tests with feature flags off/on.
- Regression tests ensuring deterministic-only mode unchanged.

## Rollout Plan

1. Add abstraction + config scaffolding with feature flags disabled by default.
2. Implement OpenAI + OpenAI-compatible adapter.
3. Implement Anthropic adapter.
4. Add review-mode pipeline hook.
5. Add optional inference-mode hook with strict validation gate.
6. Add persistence fields + observability.
7. Update docs and examples for local LAN deployments.

## Acceptance Criteria

- Deterministic mode remains default and backwards compatible.
- At least one local provider (OpenAI-compatible endpoint) works end-to-end.
- OpenAI + Anthropic adapters pass integration tests.
- Review mode produces stored review metadata without breaking existing delivery flow.
- Inference mode cannot bypass schema validation.
