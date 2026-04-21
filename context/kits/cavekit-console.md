# Cavekit: Console Simplification

## Scope

Defines the simplified operator console for phase 2. The console has exactly three jobs: queue/review, delivery operations, and runtime settings. All other surface is removed or hidden. Based on route inventory from Haiku analysis (2026-04-20).

## Requirements

### R1: Console Scope Is Three Jobs Only

**Description:** The console serves queue/review, delivery operations, and runtime settings. No other surface is part of the phase 2 console.

**Acceptance Criteria:**
- [ ] Navigation/routing exposes only: queue/intake view, delivery view, settings view
- [ ] No admin, audit, lineage detail, or metrics dashboard navigation exists in phase 2 UI
- [ ] Hidden routes (if technically present) return 404 or are unreachable from UI

### R2: Routes CUT — Remove from console_api.py

**Description:** The following routes are removed entirely. Stubs returning 501 are also removed (not preserved as dead surface).

Routes to delete:
- `POST /admin/purge-archived-notes` — admin purge, out of scope
- `PATCH /settings/secrets` — secret rotation stubbed 501, not in scope  
- `POST /dictionary/upsert` — stubbed 501, not in scope

**Acceptance Criteria:**
- [ ] No `@router` decorator for any of the 3 routes above exists in `console_api.py`
- [ ] No tests reference these routes except to confirm 404
- [ ] No frontend code calls these endpoints

### R3: Routes DEFER — Hidden, Not Removed

**Description:** These routes exist in code but are not exposed to the UI or included in bootstrap. They may be implemented later if needed.

Routes to defer:
- `GET /lineage/{intakeNoteId}` — full genealogy, defer pending ops confirmation
- `GET /metrics/throughput` — project throughput, defer
- `GET /metrics/sla` — on-time rate, defer
- `GET /metrics/error-fingerprints` — error aggregation, defer
- `GET /processing/failed` — failed run list, defer
- `GET /logs` — full log query, defer

**Acceptance Criteria:**
- [ ] Deferred routes remain in code but are not included in console navigation
- [ ] Bootstrap payload does not preload data for deferred routes
- [ ] UI does not render any navigation to deferred routes

### R4: Bootstrap Payload Is Compact

**Description:** `/bootstrap` returns only what the three-job console needs on load: current queue summary, recent deliveries, active targets, and settings block. No raw table dumps.

**Acceptance Criteria:**
- [ ] Bootstrap response does not include raw `utterances`, `transcript_revisions`, `prompt_generations`, `llm_runs`, `rulesets`, `rules`, `dictionary`, `templates`, `logs`, `processing_runs` as flat arrays
- [ ] Bootstrap includes: queue depth count, recent intake notes (paginated, last 20), recent deliveries (last 20), active targets list, runtime settings, health status
- [ ] Bootstrap response time < 500ms with up to 1000 notes in DB (Gate 4)
- [ ] Detailed data (rules, templates, lineage, logs) available on-demand via existing endpoints, not preloaded

### R5: Metrics Endpoint Is Compact Ops Summary Only

**Description:** The only metrics route kept is `GET /metrics/queue-depth`. It returns a compact ops summary: queued count, dispatching count, failed count (recent).

**Acceptance Criteria:**
- [ ] `GET /metrics/queue-depth` returns: `queued`, `dispatching`, `failed_last_24h`
- [ ] No other metrics endpoints are included in the phase 2 console navigation
- [ ] Deferred metrics routes (`/throughput`, `/sla`, `/error-fingerprints`) are not linked from UI

### R6: Delivery Safety Metadata Enforced

**Description:** `requires_confirmation` and `is_auto_dispatch_safe` fields on delivery targets govern dispatch behavior. Console enforces these before dispatching.

**Acceptance Criteria:**
- [ ] `POST /targets/{id}/dispatch` checks `is_auto_dispatch_safe` before proceeding
- [ ] If `requires_confirmation=true`, dispatch requires an explicit confirmation parameter in the request body
- [ ] If `is_auto_dispatch_safe=false` and confirmation not provided, dispatch returns 400 with a clear error
- [ ] Integration test: dispatch to a target with `requires_confirmation=true` without confirmation → 400

### R7: Watcher Failure Isolation

**Description:** Per-note processing failures in the watcher do not kill the watcher loop. One bad note, webhook failure, or parse error does not stop intake.

**Acceptance Criteria:**
- [ ] `_process_note_path()` (or equivalent) is wrapped in per-note exception handling
- [ ] Watcher loop continues processing the next note after a per-note failure
- [ ] Failed note processing writes a `workflow_error_records` row
- [ ] Integration test: inject a malformed note → watcher logs error, continues, next valid note processes successfully

### R8: Vault Path Containment Enforced

**Description:** All delivery targets that write to the filesystem are validated to stay within the configured vault root. Absolute paths and path traversal are rejected.

**Acceptance Criteria:**
- [ ] `delivery_dispatch.py` resolves target folder relative to vault root
- [ ] `resolved_path.is_relative_to(vault_root)` check applied before any write
- [ ] Absolute target folder paths are rejected with a clear error
- [ ] Path traversal (`../../`) sequences are rejected
- [ ] Integration test: configure target with `../../../tmp` path → dispatch returns error, no file written

### R9: Webhook and n8n Outbound Targets Are Operator-Dispatched Only

**Description:** Webhook delivery targets and n8n outbound calls are treated as delivery targets — queued like any other target, dispatched only by explicit operator action from the console. No automatic webhook fire on intake or compile.

**Acceptance Criteria:**
- [ ] `webhook` target type produces a `deliveries` row with `status=queued` after compile; no automatic HTTP call
- [ ] Operator must dispatch from console queue to trigger the outbound webhook HTTP request
- [ ] n8n webhook calls, if configured, are a delivery target variant — subject to the same queue + dispatch flow
- [ ] Integration test: process note with webhook target → no outbound HTTP call until operator dispatches

## Out of Scope

- Broad admin/control plane
- Secrets rotation UX
- Dictionary mutation UI
- Audit log viewer
- Multi-user permission UX
- Large observability dashboard
- LLM auto-assist in any non-opt-in context

## Cross-References

- Depends on: cavekit-architecture.md R6 (no auth/role headers)
- Depends on: cavekit-data-model.md R1 (delivery ops show attempt history)
- Depends on: cavekit-architecture.md R4 (n8n is optional reactive sidecar)
- See also: cavekit-ops-baseline.md R3 (failure log visibility)
