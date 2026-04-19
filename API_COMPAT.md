# API Compatibility Contract

This document defines the minimum compatibility expectations between:

- Backend: `stt-n8n-promptbuilder` (this repo)
- Frontend: `prompt-forge-console`

## Goals

- Keep frontend and backend in separate repos while preventing contract drift.
- Define stable API behavior for core PromptForge operations.
- Make breaking changes explicit and versioned.

## Current Service Endpoints

The backend currently exposes:

- `GET /_healthz`
- `GET /health`
- `GET /providers/health`
- `POST /preprocess`
- `POST /validate`
- `POST /render`
- `POST /prepare-delivery`

## Core Contract

Primary contract: `agent_task_v1`

Key domain values (must remain synchronized with frontend types):

- destination: `chat | cli | obsidian_note | queue_only`
- mode: `draft | queue | auto_dispatch`
- target_type: `none | chat_session | claude_session | codex_session | obsidian_note | generic_queue`
- delivery_status: `not_started | queued | dispatching | delivered | acked | failed`

If any enum/domain changes, update both repos in a single coordinated change.

## Request/Response Expectations

### `POST /preprocess`
- Input: `frontmatter`, `control_text`, `transcript_text`, optional `known_projects`
- Output: resolved routing fields, warnings, normalized transcript, parsed directives, draft structured output

### `POST /validate`
- Input: `contract_name=agent_task_v1`, payload object
- Output: normalized/validated `agent_task_v1` payload and warnings

### `POST /render`
- Input: same contract envelope
- Output: `template_name`, `final_prompt_markdown`, normalized payload

### `POST /prepare-delivery`
- Input: same contract envelope + `priority`
- Output: delivery target/type/identifier/mode/status/priority

## Compatibility Rules

1. Additive changes are preferred.
- Adding new optional fields is non-breaking.
- Removing or renaming existing fields is breaking.

2. Enum evolution.
- Adding enum values is potentially breaking for frontend filters/forms.
- Any new enum values require frontend updates before release.

3. Error shape.
- Validation failures should remain HTTP `400` with human-readable detail.

4. Health semantics.
- `/_healthz` should remain lightweight and stable for probes.
- `/health` may include richer metadata.

## Versioning Policy

Use semantic API compatibility labels in release notes/PRs:

- `api:patch` – no contract changes
- `api:minor` – additive non-breaking changes
- `api:major` – breaking request/response/domain changes

When `api:major` occurs, coordinate frontend merge before deployment.

## Database Read Surface for Frontend

The frontend requires diagnostics/ops query surfaces not yet exposed as REST in this backend.

Interim approach:
- Frontend can develop against typed mocks.
- Query catalog from planning docs is source-of-truth for upcoming read APIs.

Planned work:
- Add read endpoints for dashboard, intake explorer, pipeline trace, review queue, delivery operations, and rules/template editors.

## Security/Operational Guardrails

- Do not expose secrets in API responses.
- Preserve idempotency where practical for retryable operations.
- Prefer explicit mutation endpoints over overloaded action parameters.
- Keep audit fields (`*_id`, timestamps, statuses) available for traceability.
