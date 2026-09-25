# Phase 6 Prompt: Runtime/Compose + Smoke Validation

```text
Phase 6 objective:
Ensure containerized runtime is stable with backend + frontend + dependencies, and add repeatable smoke verification.

Primary repo:
- .

Secondary repo (if needed for container tweaks):
- prompt-forge-console

Parallel packets:

Packet A (Compose/runtime owner)
- Verify docker-compose service graph:
  - postgres
  - n8n
  - promptforge-api
  - promptforge-watcher
  - promptforge-console
- Confirm healthchecks and startup ordering.
- Verify env defaults and docs are aligned.

Packet B (Smoke script owner)
- Create a script that validates:
  - API health endpoint
  - console HTTP availability
  - /console/bootstrap
  - at least one list/read endpoint
  - at least one mutation roundtrip
- Script should fail fast with useful diagnostics.

Packet C (Operational docs owner)
- Update runbook docs with:
  - startup command
  - smoke command
  - common failure triage

Constraints:
- No hardcoded secrets.
- Localhost-only host bindings for dev safety unless explicitly configured.

Phase gate:
- `docker compose up -d --build` reaches healthy state.
- smoke script passes end-to-end.
- docs include exact commands and expected outcomes.
```
