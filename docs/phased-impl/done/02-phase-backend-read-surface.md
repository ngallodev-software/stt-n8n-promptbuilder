# Phase 2 Prompt: Backend Read Surface + Typed Schemas

```text
Phase 2 objective:
Implement dedicated backend read endpoints with typed response schemas and server-side pagination/filtering.

Repo:
- /lump/apps/prompt-forge

Parallel packets:

Packet A (Schema + models owner)
- Own files: promptforge_services/models* (new console models module allowed), api wiring.
- Define strict Pydantic response models for:
  - projects
  - intake list/detail
  - lineage payload
  - prompts list
  - deliveries list
  - rulesets/rules
  - dictionary
  - templates
  - targets
  - logs
  - summary metrics

Packet B (Read endpoint owner)
- Own files: promptforge_services/console_api.py and supporting query module(s).
- Implement read endpoints:
  - /console/projects
  - /console/intake
  - /console/intake/{id}
  - /console/lineage/{intakeNoteId}
  - /console/prompts
  - /console/deliveries
  - /console/processing/failed
  - /console/rulesets
  - /console/rules
  - /console/dictionary
  - /console/templates
  - /console/targets
  - /console/logs
  - /console/metrics/queue-depth
  - /console/metrics/throughput
  - /console/metrics/sla
  - /console/metrics/error-fingerprints
- Must support pagination + filtering as query params.

Packet C (Bootstrap compatibility owner)
- Keep `/console/bootstrap` backward-compatible.
- Refactor bootstrap to call shared query functions so logic is not duplicated.

Constraints:
- Parameterized SQL only.
- Explicit 400/404/503 behavior.
- Keep existing endpoints unchanged unless additive.
- Do not break existing `/preprocess`, `/validate`, `/render`, `/prepare-delivery`.

Validation:
- Add tests for each read endpoint (happy + invalid params + DB unavailable).
- Keep tests deterministic.

Phase gate:
- All new read endpoints return typed responses.
- `/console/bootstrap` remains functional and uses shared read/query path.
- Test suite for new read endpoints passes.
```
