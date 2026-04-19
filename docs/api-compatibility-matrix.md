# API Compatibility Matrix

This document inventories the current HTTP surface of `promptforge_services` as implemented in:

- `promptforge_services/api.py`
- `promptforge_services/console_api.py`
- `promptforge_services/models.py`
- `promptforge_services/pipeline.py`
- `promptforge_services/llm/router.py`

It is an implementation snapshot, not an aspirational contract.

## Error Semantics

Across the API, there are three error classes to account for:

1. FastAPI request validation
   - Invalid JSON, missing required fields, or wrong field types return `422 Unprocessable Entity`.
   - The body is FastAPI's standard validation payload, with a `detail` array of validation errors.

2. Explicit `HTTPException` responses
   - These return the configured status code and a JSON body of the form `{"detail": "<string>"}`.
   - The code uses stable string codes for many console errors.

3. Uncaught runtime errors
   - Some helper-layer failures are not converted into `HTTPException`.
   - Those bubble up as generic `500 Internal Server Error` responses with no stable application-level detail body.

## Public API

| Method | Path | Request shape | Success response shape | Explicit error semantics |
| --- | --- | --- | --- | --- |
| `GET` | `/_healthz` | None | `{ "ok": true }` | No explicit application errors |
| `GET` | `/health` | None | `{ "ok": true, "supported_contracts": ["agent_task_v1"] }` | No explicit application errors |
| `GET` | `/providers/health` | None | `LLMProvidersHealthResponse` | Standard `422` only if framework-level routing/serialization fails |
| `POST` | `/preprocess` | `PreprocessRequest` | `PreprocessResponse` | `422` on request validation; uncaught runtime errors bubble as `500` |
| `POST` | `/validate` | `ValidateRequest` | `ValidateResponse` | `400` on `ValueError` from pipeline; `422` on request validation; uncaught runtime errors bubble as `500` |
| `POST` | `/render` | `RenderRequest` | `RenderResponse` | `400` on `ValueError` from pipeline; `422` on request validation; uncaught runtime errors bubble as `500` |
| `POST` | `/prepare-delivery` | `PrepareDeliveryRequest` | `PrepareDeliveryResponse` | `400` on `ValueError` from pipeline; `422` on request validation; uncaught runtime errors bubble as `500` |

### Public Request / Response Shapes

#### `PreprocessRequest`

```json
{
  "frontmatter": {},
  "control_text": null,
  "transcript_text": "string",
  "known_projects": ["inbox", "the-tax-machine", "promptforge"]
}
```

#### `PreprocessResponse`

```json
{
  "resolved_project": "string",
  "resolved_prompt_type": "general | coding-cli | delegation | planning | review",
  "resolved_destination": "chat | cli | obsidian_note | queue_only",
  "target_identifier": "string | null",
  "mode": "draft | queue | auto_dispatch",
  "requires_review": false,
  "warnings": ["string"],
  "normalized_transcript": "string",
  "parsed_directives": {
    "project": "string | null",
    "prompt_type": "string | null",
    "destination": "string | null",
    "target_identifier": "string | null",
    "mode": "string | null",
    "priority": "string | null",
    "requires_review": "boolean | null",
    "warnings": ["string"]
  },
  "draft_structured_output": {
    "contract_name": "agent_task_v1",
    "requires_review": false,
    "notes": ["string"],
    "intent": "agent_task",
    "project_slug": "string",
    "prompt_type": "general | coding-cli | delegation | planning | review",
    "destination": "chat | cli | obsidian_note | queue_only",
    "target_identifier": "string | null",
    "mode": "draft | queue | auto_dispatch",
    "final_prompt_markdown": "string"
  }
}
```

Notes:

- `draft_structured_output` is an `AgentTaskV1`.
- If the transcript is routed to `cli` without a `target_identifier`, the pipeline rewrites it to `queue_only`, sets `requires_review = true`, and appends a warning.

#### `ValidateRequest`

```json
{
  "contract_name": "agent_task_v1",
  "payload": {}
}
```

#### `ValidateResponse`

```json
{
  "contract_name": "agent_task_v1",
  "valid": true,
  "warnings": ["string"],
  "payload": {
    "contract_name": "agent_task_v1",
    "requires_review": false,
    "notes": ["string"],
    "intent": "agent_task",
    "project_slug": "string",
    "prompt_type": "general | coding-cli | delegation | planning | review",
    "destination": "chat | cli | obsidian_note | queue_only",
    "target_identifier": "string | null",
    "mode": "draft | queue | auto_dispatch",
    "final_prompt_markdown": "string"
  }
}
```

Notes:

- The pipeline normalizes aliases for `prompt_type`, `destination`, `mode`, and `target_identifier`.
- If `destination == "cli"` and no target is present, it rewrites to `queue_only`, sets `requires_review = true`, and adds `cli_target_missing` to `warnings`.
- The handler only converts `ValueError` to `400`. Other validation failures in nested model construction are not explicitly wrapped.

#### `RenderRequest`

```json
{
  "contract_name": "agent_task_v1",
  "payload": {}
}
```

#### `RenderResponse`

```json
{
  "contract_name": "agent_task_v1",
  "template_name": "string",
  "final_prompt_markdown": "string",
  "payload": {
    "contract_name": "agent_task_v1",
    "requires_review": false,
    "notes": ["string"],
    "intent": "agent_task",
    "project_slug": "string",
    "prompt_type": "general | coding-cli | delegation | planning | review",
    "destination": "chat | cli | obsidian_note | queue_only",
    "target_identifier": "string | null",
    "mode": "draft | queue | auto_dispatch",
    "final_prompt_markdown": "string"
  }
}
```

Notes:

- `template_name` is `coding-cli-default` for `prompt_type == "coding-cli"` and `generic-default` otherwise.
- The rendered markdown is normalized by `mdformat` when available, otherwise trimmed.

#### `PrepareDeliveryRequest`

```json
{
  "contract_name": "agent_task_v1",
  "payload": {},
  "priority": "normal"
}
```

#### `PrepareDeliveryResponse`

```json
{
  "contract_name": "agent_task_v1",
  "delivery": {
    "destination": "chat | cli | obsidian_note | queue_only",
    "target_type": "none | chat_session | claude_session | codex_session | obsidian_note | generic_queue",
    "target_identifier": "string",
    "mode": "draft | queue | auto_dispatch",
    "status": "queued",
    "priority": "low | normal | high | urgent",
    "requires_review": false
  },
  "payload": {
    "contract_name": "agent_task_v1",
    "requires_review": false,
    "notes": ["string"],
    "intent": "agent_task",
    "project_slug": "string",
    "prompt_type": "general | coding-cli | delegation | planning | review",
    "destination": "chat | cli | obsidian_note | queue_only",
    "target_identifier": "string | null",
    "mode": "draft | queue | auto_dispatch",
    "final_prompt_markdown": "string"
  }
}
```

Notes:

- `priority` defaults to `normal`.
- `destination` is mapped to a target class:
  - `cli` -> `claude_session` or `codex_session` depending on the target identifier prefix.
  - `chat` -> `chat_session`
  - `obsidian_note` -> `obsidian_note`
  - anything else -> `generic_queue`

#### `LLMProvidersHealthResponse`

```json
{
  "enabled": true,
  "mode": "deterministic_only | deterministic_plus_review | llm_inference_optional",
  "review_provider": "string | null",
  "inference_provider": "string | null",
  "providers": [
    {
      "provider_name": "string",
      "provider_family": "string",
      "configured": true,
      "available": true,
      "model_name": "string | null",
      "base_url": "string | null",
      "detail": "string | null"
    }
  ]
}
```

Notes:

- A provider that is not configured reports `configured = false`, `available = false`, and `detail = "provider_not_configured"`.

## Console API

All console routes are mounted under `/console`.

| Method | Path | Request shape | Success response shape | Explicit error semantics |
| --- | --- | --- | --- | --- |
| `GET` | `/console/bootstrap` | None | Bootstrap snapshot object | Never raises `database_unconfigured`; returns an empty degraded snapshot when the DB URL is missing |
| `POST` | `/console/deliveries/{delivery_id}/retry` | None | `{ "ok": true, "message": "Retry queued" }` | `503` `database_unconfigured`; `404` `delivery_not_found`; `422` on malformed path/body |
| `POST` | `/console/deliveries/{delivery_id}/reroute` | `DeliveryRerouteRequest` | `{ "ok": true }` | `503` `database_unconfigured`; `404` `target_not_found`; `404` `delivery_not_found`; `422` on request validation |
| `PATCH` | `/console/deliveries/{delivery_id}/status` | `DeliveryStatusRequest` | `{ "ok": true }` | `503` `database_unconfigured`; `404` `delivery_not_found`; `422` on request validation |
| `PATCH` | `/console/rules/{rule_id}` | `RulePatchRequest` | `{ "ok": true }` | `503` `database_unconfigured`; `404` `rule_not_found`; `422` on request validation |
| `POST` | `/console/dictionary/upsert` | `DictionaryUpsertRequest` | `{ "ok": true, "payload": <echoed dictionary record> }` | `503` `database_unconfigured`; `400` `source_term_required`; `422` on request validation |
| `POST` | `/console/templates/{template_id}/activate` | `TemplateActivateRequest` | `{ "ok": true }` | `503` `database_unconfigured`; `404` `template_not_found`; `422` on request validation |
| `POST` | `/console/prompts/{prompt_generation_id}/force-review` | None | `{ "ok": true }` | `503` `database_unconfigured`; `404` `prompt_generation_not_found`; `422` on malformed path/body |
| `POST` | `/console/prompts/{prompt_generation_id}/clone` | None | `{ "ok": true, "newId": "string" }` | `503` `database_unconfigured`; `404` `prompt_generation_not_found`; `422` on malformed path/body |
| `PATCH` | `/console/prompts/{prompt_generation_id}/priority` | `PromptPriorityRequest` | `{ "ok": true }` | `503` `database_unconfigured`; `404` `delivery_for_prompt_not_found`; `422` on request validation |
| `PATCH` | `/console/intake/{intake_note_id}/archive` | None | `{ "ok": true }` | `503` `database_unconfigured`; `404` `intake_note_not_found`; `422` on malformed path/body |

### Console Request / Response Shapes

#### `DeliveryRerouteRequest`

```json
{
  "targetId": "string"
}
```

#### `DeliveryStatusRequest`

```json
{
  "status": "string"
}
```

Notes:

- The route layer does not validate allowed delivery statuses.
- Invalid status strings can still fail later at the database enum cast and bubble up as a runtime error.

#### `RulePatchRequest`

```json
{
  "enabled": true,
  "priority": 10
}
```

Notes:

- Both fields are optional.
- The handler reads the existing rule, applies request-provided overrides, and writes the merged result.

#### `DictionaryUpsertRequest`

```json
{
  "id": "string | null",
  "scope": "string | null",
  "project_id": "string | null",
  "source_term": "string | null",
  "normalized_term": "string | null",
  "description": "string | null"
}
```

Notes:

- `scope` defaults to `global`.
- `normalized_term` defaults to `source_term` when omitted.
- `source_term` must be non-empty after trimming or the endpoint returns `400 source_term_required`.
- If `id` is present, the endpoint updates the existing row and echoes the request payload.
- If `id` is absent, the endpoint inserts or upserts a row and returns the echoed payload plus an `id` field.

#### `TemplateActivateRequest`

```json
{
  "family": "string"
}
```

#### `PromptPriorityRequest`

```json
{
  "priority": "string"
}
```

Notes:

- The route does not validate the priority against a fixed allow-list.
- Invalid values may fail inside the database update path and bubble up as a runtime error.

#### `/console/bootstrap` response shape

Top-level keys:

```json
{
  "projects": [],
  "intakeNotes": [],
  "utterances": [],
  "transcriptRevisions": [],
  "promptGenerations": [],
  "deliveries": [],
  "deliveryHistory": [],
  "processingRuns": [],
  "llmRuns": [],
  "rulesets": [],
  "rules": [],
  "termDictionary": [],
  "promptTemplates": [],
  "deliveryTargets": [],
  "logs": [],
  "healthSnapshot": {}
}
```

Representative item shapes:

- `projects[]`: `{ id, name, slug, description, created_at, updated_at }`
- `intakeNotes[]`: `{ id, project_id, note_relative_path, status, watch_eligible, source_device, body_text, frontmatter_original, frontmatter_current, metadata_json, created_at, updated_at }`
- `utterances[]`: `{ id, intake_note_id, speaker, index, created_at }`
- `transcriptRevisions[]`: `{ id, utterance_id, revision_kind, producer_type, producer_name, content_text, metadata_json, created_at }`
- `promptGenerations[]`: `{ id, intake_note_id, status, requires_review, prompt_type, ruleset_id, template_id, destination, mode, priority, structured_output_json, final_prompt_markdown, validation_warnings, created_at, updated_at }`
- `deliveries[]`: `{ id, prompt_generation_id, target_id, status, destination, mode, priority, retry_count, failure_text, ack_text, created_at, updated_at }`
- `deliveryHistory[]`: the subset of `deliveries[]` whose `status == "failed"`
- `processingRuns[]`: `{ id, intake_note_id, status, stage_name, error_text, trace_json, created_at, updated_at }`
- `llmRuns[]`: `{ id, prompt_generation_id, provider_name, model_name, mode, latency_ms, input_tokens, output_tokens, created_at }`
- `rulesets[]`: `{ id, name, scope, project_id, active, description, updated_at }`
- `rules[]`: `{ id, ruleset_id, name, rule_type, priority, enabled, pattern, replacement, description, updated_at }`
- `termDictionary[]`: `{ id, scope, project_id, source_term, normalized_term, description, created_at, updated_at }`
- `promptTemplates[]`: `{ id, name, prompt_type, scope, project_id, version, is_active, template_family_key, body, updated_at }`
- `deliveryTargets[]`: `{ id, name, target_type, destination, scope, project_id, enabled, is_sensitive, requires_confirmation, environment, validation_status, updated_at }`
- `logs[]`: `{ id, service, level, message, timestamp, intake_note_id, utterance_id, prompt_generation_id, delivery_id, fields }`
- `healthSnapshot`: `{ api, providers, db, queue_depth, failures_24h }`

`healthSnapshot` details:

- When the DB URL is configured, `api.status = "ok"` and `db.status = "ok"`.
- When the DB URL is missing, the endpoint returns the empty bootstrap shape and `healthSnapshot.api.status = "degraded"` / `healthSnapshot.db.status = "degraded"`.

### Console error detail strings

These are the explicit `HTTPException.detail` values observed in the code:

- `database_unconfigured` -> `503`
- `delivery_not_found` -> `404`
- `target_not_found` -> `404`
- `rule_not_found` -> `404`
- `source_term_required` -> `400`
- `template_not_found` -> `404`
- `prompt_generation_not_found` -> `404`
- `delivery_for_prompt_not_found` -> `404`
- `intake_note_not_found` -> `404`

## Compatibility Notes

- Public request models are narrow where possible, but console mutation routes accept several free-form strings and rely on database constraints or application logic later in the call path.
- `GET /console/bootstrap` is intentionally soft-failing when the DB is not configured.
- The API currently has no versioned prefix. Any contract-breaking change here should be treated as a compatibility event.
