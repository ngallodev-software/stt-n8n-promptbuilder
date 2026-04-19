# Backend Settings Support Prompt

You are working in the backend repo at `/lump/apps/prompt-forge`.

Goal
- Add backend settings support for the frontend console Settings page in `/lump/apps/prompt-forge-console`.
- Preserve existing API behavior where possible.
- Implement real server-side settings reads/writes for backend-owned runtime configuration and admin actions.
- Do not redesign the frontend. Build the backend contract the frontend now expects.

Frontend state after the current console changes
- The Settings page now has two editable browser-persisted sections that remain frontend-only:
  - local console connectivity: `apiBaseUrl`, `bootstrapPath`
  - local operator preferences: `theme`, `role`, `workspace`, `environment`, `debug`, `pollingMs`
- These frontend-only values must not move to the backend in this task.
- The frontend now treats the following settings as backend-managed and read-only until the backend exists:
  - `obsidianVaultPath`
  - `webhookUrl`
  - `llmMode`
  - `codexBinary`
  - `codexReasoningEffort`
  - `openaiBaseUrl`
  - `anthropicBaseUrl`
- The frontend also shows backend-managed secret placeholders for:
  - `OPENAI_API_KEY`
  - `ANTHROPIC_API_KEY`
  - `PROMPTFORGE_OPENAI_COMPAT_API_KEY`
  - `PROMPTFORGE_OLLAMA_API_KEY`
- The frontend removed a fake admin action. "Purge archived notes" is now explicitly blocked until a real backend endpoint exists with audit logging.

Primary backend deliverables
1. Add a persisted settings model for backend-managed runtime settings.
2. Add read APIs so the frontend can fetch runtime settings and masked secret status.
3. Add write APIs for admins to update runtime settings and rotate secrets.
4. Add a real admin endpoint for purging archived notes.
5. Expose the settings payload through bootstrap if that is the cleanest way to hydrate the console.

Required persistence model
- Add a durable settings store for console/backend runtime configuration.
- Support `scope` with the same vocabulary already used elsewhere where practical:
  - `global`
  - `project`
- Support `project_id nullable`.
- Store non-secret settings as plain validated config values.
- Store secret settings separately from plain settings. Do not store raw secrets in the same response shape as plain settings.

Recommended schema
- Table `console_runtime_settings`
  - `id`
  - `scope` enum or constrained text: `global | project`
  - `project_id nullable`
  - `key`
  - `value_json` or typed value columns
  - `updated_by_user_id nullable`
  - `updated_at`
  - unique on `(scope, project_id, key)`
- Table `console_secret_settings`
  - `id`
  - `scope` enum or constrained text: `global | project`
  - `project_id nullable`
  - `key`
  - `secret_ref` or encrypted secret payload, depending on existing secret-handling conventions in the repo
  - `configured boolean`
  - `last_rotated_at nullable`
  - `updated_by_user_id nullable`
  - `updated_at`
  - unique on `(scope, project_id, key)`
- If the repo already has a preferred config or secret storage pattern, use it instead of inventing a second system. Preserve the same semantics above.

Runtime settings that must be supported
- `obsidianVaultPath`
- `webhookUrl`
- `llmMode`
- `codexBinary`
- `codexReasoningEffort`
- `openaiBaseUrl`
- `anthropicBaseUrl`

Validation rules
- `obsidianVaultPath`
  - required
  - non-empty string
  - absolute path expected
  - max length 1024
- `webhookUrl`
  - required
  - absolute `https://` URL unless existing deployment conventions explicitly allow local `http://` in development
  - max length 2048
- `llmMode`
  - enum:
    - `deterministic_only`
    - `deterministic_plus_review`
    - `llm_inference_optional`
- `codexBinary`
  - required
  - non-empty string
  - path or executable name
  - max length 512
- `codexReasoningEffort`
  - enum:
    - `low`
    - `medium`
    - `high`
  - if the backend already supports a broader enum, document and expose that explicitly
- `openaiBaseUrl`
  - required
  - absolute `http://` or `https://` URL
  - max length 2048
- `anthropicBaseUrl`
  - required
  - absolute `http://` or `https://` URL
  - max length 2048
- Secret keys
  - accept non-empty string writes
  - trim surrounding whitespace only if that matches existing secret-handling practice
  - never echo raw secret values in read responses or logs

Required API endpoints
1. `GET /console/settings`
- Returns backend-managed runtime settings plus secret metadata.
- Accept optional query params:
  - `scope=global|project`
  - `project_id`
- Response shape should be explicit and stable, for example:

```json
{
  "scope": "global",
  "project_id": null,
  "runtime": {
    "obsidianVaultPath": "/srv/promptforge/vault",
    "webhookUrl": "https://hooks.internal/promptforge",
    "llmMode": "deterministic_plus_review",
    "codexBinary": "codex",
    "codexReasoningEffort": "medium",
    "openaiBaseUrl": "https://api.openai.com/v1",
    "anthropicBaseUrl": "https://api.anthropic.com"
  },
  "secrets": {
    "OPENAI_API_KEY": { "configured": true, "last_rotated_at": "2026-04-19T12:00:00Z" },
    "ANTHROPIC_API_KEY": { "configured": false, "last_rotated_at": null },
    "PROMPTFORGE_OPENAI_COMPAT_API_KEY": { "configured": false, "last_rotated_at": null },
    "PROMPTFORGE_OLLAMA_API_KEY": { "configured": true, "last_rotated_at": "2026-04-18T10:00:00Z" }
  },
  "permissions": {
    "can_update_runtime": true,
    "can_rotate_secrets": true,
    "can_purge_archived_notes": true
  },
  "updated_at": "2026-04-19T12:00:00Z"
}
```

2. `PATCH /console/settings/runtime`
- Admin-only.
- Accepts partial updates for runtime settings.
- Validate each field independently.
- Reject unknown keys.
- Return the normalized full runtime settings payload after write.

3. `PATCH /console/settings/secrets`
- Admin-only.
- Accepts one or more secret updates.
- Input example:

```json
{
  "scope": "global",
  "project_id": null,
  "secrets": {
    "OPENAI_API_KEY": "sk-...",
    "ANTHROPIC_API_KEY": "..."
  }
}
```

- Persist securely.
- Response must return metadata only, never raw values.

4. `POST /console/admin/purge-archived-notes`
- Admin-only.
- Requires an explicit confirmation field in the request body so the action cannot be triggered accidentally.
- Example request:

```json
{
  "confirm": "purge archived notes"
}
```

- Behavior:
  - permanently delete archived intake notes and dependent lineage records, or invoke the repo’s canonical archival purge job if one already exists
  - return counts by table/resource deleted
  - emit audit logs

Bootstrap integration
- If `/console/bootstrap` already exists as the console hydration path, include a `settings` block in the bootstrap payload instead of forcing an extra round trip.
- Keep bootstrap backward compatible:
  - existing consumers must not break if they ignore the new `settings` field
- Recommended bootstrap addition:

```json
{
  "settings": {
    "scope": "global",
    "project_id": null,
    "runtime": { "...": "..." },
    "secrets": { "...": { "configured": true, "last_rotated_at": null } },
    "permissions": {
      "can_update_runtime": true,
      "can_rotate_secrets": true,
      "can_purge_archived_notes": true
    }
  }
}
```

Read/write semantics
- Frontend-only values that must stay local and must not be moved to backend storage in this task:
  - `apiBaseUrl`
  - `bootstrapPath`
  - `theme`
  - `role`
  - `workspace`
  - `environment`
  - `debug`
  - `pollingMs`
- Non-secret runtime settings:
  - readable by authenticated users who can load the console
  - writable by admins only
- Secret settings:
  - read responses return metadata only
  - writes allowed for admins only
  - raw values must never be returned after write
- Purge action:
  - executable by admins only
  - must require explicit confirmation

Permission rules
- Preserve existing auth and role guard conventions in the backend repo.
- Minimum required behavior:
  - viewer: may read runtime settings and masked secret metadata if the console already permits Settings page access
  - operator: may read runtime settings and masked secret metadata
  - admin: may read, update runtime settings, rotate secrets, and purge archived notes
- If the backend already has a stricter authorization model, keep it, but the response payload must still tell the frontend which actions are currently allowed.

Audit logging requirements
- Log every runtime settings mutation with:
  - actor
  - scope
  - project_id
  - keys changed
  - previous value hash or redacted summary
  - resulting value hash or redacted summary
  - timestamp
- Log every secret rotation with:
  - actor
  - scope
  - project_id
  - secret keys changed
  - timestamp
- Log every purge request with:
  - actor
  - confirmation status
  - deleted record counts
  - timestamp
- Never log raw secret values.

Compatibility and rollout notes
- Preserve existing endpoints and payloads unless a change is strictly required.
- Do not break `/console/bootstrap`; add fields compatibly.
- If no settings record exists yet, serve sensible defaults derived from existing backend config so the frontend can render immediately.
- Migrations must be safe for existing environments.
- If project-scoped overrides are not implemented immediately, support `global` first but design the schema and handlers so `project` can be added without another breaking change.

Test coverage requirements
- Migration tests or schema verification for new settings tables.
- API tests for:
  - `GET /console/settings` default/global path
  - project-scoped read if supported
  - `PATCH /console/settings/runtime` success and validation failures
  - `PATCH /console/settings/secrets` success and permission failures
  - secret reads never returning raw values
  - `POST /console/admin/purge-archived-notes` success, permission failure, and confirmation failure
  - bootstrap payload including compatible `settings` block
- Authorization tests for viewer/operator/admin behavior.
- Audit-log tests for runtime updates, secret rotation, and purge.

Acceptance criteria
- The backend exposes real runtime settings and masked secret metadata for the console.
- Admins can update runtime settings through a dedicated endpoint.
- Admins can rotate secret settings through a dedicated endpoint without raw secrets leaking in responses or logs.
- The archived-notes purge action is implemented as a real admin endpoint with confirmation and audit logging.
- `/console/bootstrap` or equivalent hydration can include the new settings payload without breaking existing clients.
- Frontend-only local settings remain frontend-only and are not moved into backend persistence.
- Tests cover validation, permissions, audit logging, and backward compatibility.

Implementation notes
- Favor small explicit handlers and typed serializers over generic unbounded config blobs.
- Reuse existing validation, auth, audit, and secret-storage infrastructure in the backend repo where available.
- Do not change unrelated frontend-facing contracts.
