# Plan: Phase 2 Simplification

**Status:** ACTIVE  
**Kit references:** cavekit-overview.md, cavekit-architecture.md, cavekit-data-model.md, cavekit-console.md, cavekit-intake-writeback.md, cavekit-ops-baseline.md

---

## Sequencing Rationale

Phase 2 work falls into four ordered waves:

1. **Delete & Demote** — Remove dead code, dead routes, dead tables, dead docs. No migration risk, pure reduction.
2. **Harden Core** — Fix watcher isolation, vault path safety, delivery safety metadata. Behavioral correctness.
3. **Rebuild Delivery History** — Replace in-place mutation with append-only attempts. Data model truth.
4. **Narrow Console** — Compact bootstrap, cut deferred routes from UI, failure visibility.

Do not start wave N+1 until wave N tasks are validated. Waves 2–4 have real migration risk.

---

## Wave 1: Delete & Demote (low risk, high leverage)

### W1-T1: Remove 3 CUT routes from console_api.py
**Kit:** cavekit-console.md R2  
**Write set:** `promptforge_services/console_api.py`, `tests/`  
**Action:** Delete `POST /admin/purge-archived-notes`, `PATCH /settings/secrets`, `POST /dictionary/upsert`  
**Validation:** `grep -n "purge-archived\|secrets.*patch\|dictionary/upsert" console_api.py` → no results  
**Delegation:** Haiku (`--provider anthropic --tier low`)

### W1-T2: Remove role/auth header logic
**Kit:** cavekit-architecture.md R6  
**Write set:** `promptforge_services/console_api.py`, `promptforge_services/api.py`, `tests/`  
**Action:** Delete all role-header parsing, default-admin fallback, role guard decorators  
**Validation:** `grep -n "X-Role\|x-role\|default_role\|admin_fallback\|get_role" *.py` → no results  
**Delegation:** Haiku (`--provider anthropic --tier low`)

### W1-T3: Drop live-session delivery code
**Kit:** cavekit-architecture.md R5  
**Write set:** `promptforge_services/delivery_dispatch.py`, `tests/test_delivery_dispatch_live_sessions.py`  
**Action:** Remove tmux dispatch path from `delivery_dispatch.py`; delete or skip-all `test_delivery_dispatch_live_sessions.py`  
**Validation:** `grep -n "tmux\|live_session\|send-keys" delivery_dispatch.py` → no results  
**Delegation:** Haiku (`--provider anthropic --tier low`)

### W1-T4: Rewrite architecture docs
**Kit:** cavekit-architecture.md R4, R7  
**Write set:** `docs/promptforge-system-architecture.md`, `docs/planning/promptforge_mvp_master_plan.md`  
**Action:** Rewrite system architecture doc; archive or update MVP plan; remove false n8n orchestration claims; remove vault-as-canonical claims  
**Validation:** `grep -n "n8n.*orchestrat\|vault.*canonical\|immutable.*source" docs/*.md` → no results  
**Delegation:** Claude Sonnet (`--provider anthropic --tier medium`) — requires careful rewrite

### W1-T5: Drop `delivery_session_registry` table
**Kit:** cavekit-data-model.md R2  
**Write set:** `docs/planning/` (migration SQL)  
**Action:** Write migration to drop `delivery_session_registry`; zero code references exist — migration only  
**Validation:** `grep -rn "delivery_session_registry" .` → no results except migration file  
**Note:** Verified zero code refs in 2026-04-20 table inventory. Drop is safe without code changes.  
**Delegation:** Haiku (`--provider anthropic --tier low`)

### W1-T6: Drop `console_admin_audit_log` and `console_secret_settings` tables
**Kit:** cavekit-data-model.md R3  
**Write set:** `docs/planning/` (migration SQL), `promptforge_services/secrets_migration.py`, `promptforge_services/console_api.py`, `tests/test_secrets_migration.py`, `tests/test_console_settings.py`  
**Action:**
1. Stub `backfill_console_secret_rows()` in `secrets_migration.py` to return 0 early (no DB calls)
2. Make audit log inserts in `console_api.py:510` and `secrets_migration.py:48` silent no-ops (delete or wrap in try/except that eats the error)
3. Make `_safe_fetch_settings_rows()` return empty secrets list (remove console_secret_settings SELECT)
4. Skip or delete `test_secrets_migration.py` and secrets-table-dependent tests in `test_console_settings.py`
5. Write migration to drop both tables  
**Validation:** `grep -rn "console_admin_audit_log\|console_secret_settings" .` → migration file only  
**Note:** Table inventory confirmed active refs: secrets_migration.py:18,34,48; console_api.py:406,443,510,915; test_console_settings.py:48,177,281,297; test_secrets_migration.py:29,42,57. All must be cleaned before migration runs.  
**Delegation:** Haiku (`--provider anthropic --tier low`)

### W1-T7: Gate LLM assist behind opt-in setting
**Kit:** cavekit-architecture.md R8  
**Write set:** `promptforge_services/console_api.py` (`/llm/assist` handler), `tests/`  
**Action:** Ensure `/llm/assist` checks opt-in flag from runtime settings; return 501 if not opted in; verify no LLM calls triggered in intake/compile/queue code paths  
**Validation:** `grep -rn "llm.*assist\|openai\|anthropic" promptforge_watcher/` → no calls outside explicit opt-in path; `GET /llm/assist` without opt-in flag → 501  
**Delegation:** Haiku (`--provider anthropic --tier low`)

---

## Wave 2: Harden Core (medium risk)

### W2-T1: Watcher per-note failure isolation
**Kit:** cavekit-console.md R7  
**Write set:** `promptforge_watcher/watcher.py`  
**Action:** Wrap `_process_note_path()` call in try/except; write `workflow_error_records` on failure; continue loop  
**Validation:** Integration test — inject bad note → watcher continues, error row written  
**Delegation:** Codex medium (`--provider openai --tier medium`)

### W2-T2: Vault path containment check
**Kit:** cavekit-console.md R8  
**Write set:** `promptforge_services/delivery_dispatch.py`, `tests/`  
**Action:** Add `resolved_path.is_relative_to(vault_root)` guard before any filesystem write; reject absolute paths and traversal sequences  
**Validation:** Integration test: `../../tmp` target → 400 error, no file written  
**Delegation:** Codex medium (`--provider openai --tier medium`)

### W2-T3: Strict intake note parser
**Kit:** cavekit-intake-writeback.md R1, R2  
**Write set:** `promptforge_watcher/watcher.py` or parser module  
**Action:** Add explicit checks for `## Control` and `## Transcript` sections; fail fast with structured error; write `workflow_error_records` on failure; leave note in place  
**Validation:** Test: note missing `## Control` → `workflow_error_records` row written, note not moved/deleted  
**Delegation:** Codex medium (`--provider openai --tier medium`)

### W2-T4: Delivery safety metadata enforcement
**Kit:** cavekit-console.md R6  
**Write set:** `promptforge_services/console_api.py`, `promptforge_services/delivery_dispatch.py`, `tests/`  
**Action:** Add `requires_confirmation` and `is_auto_dispatch_safe` checks before dispatch in both dispatch routes  
**Validation:** Integration test: dispatch to `requires_confirmation=true` target without confirmation param → 400  
**Delegation:** Codex medium (`--provider openai --tier medium`)

### W2-T5: Enforce webhook/n8n targets as queue-only
**Kit:** cavekit-console.md R9  
**Write set:** `promptforge_services/delivery_dispatch.py`, `tests/`  
**Action:** Verify webhook target type creates `deliveries` row with `status=queued` and makes no outbound HTTP call during compile/intake; outbound call only on operator dispatch  
**Validation:** Integration test: process note with webhook target → no outbound HTTP call until operator dispatches; `deliveries.status=queued` row exists  
**Delegation:** Codex medium (`--provider openai --tier medium`)

---

## Wave 3: Rebuild Delivery History (high risk, schema change)

### W3-T1: Create delivery_attempts table
**Kit:** cavekit-data-model.md R1, R5  
**Write set:** `docs/planning/` (migration SQL), `promptforge_services/models.py`, `promptforge_services/console_api.py`, `tests/`  
**Action:** Create `delivery_attempts` table; add `latest_attempt_id` FK to `deliveries`; update retry/reroute to append new rows instead of mutating  
**Validation:** Integration test: retry twice → 3 attempt rows, none modified after creation  
**Delegation:** Codex high (`--provider openai --tier high`) — schema change + multiple coordinated files  
**Note:** Requires human review of migration before running against live DB

### W3-T2: Update delivery retry/reroute to append-only
**Kit:** cavekit-data-model.md R1  
**Write set:** `promptforge_services/console_api.py` (retry/reroute endpoints), `tests/`  
**Action:** Replace in-place mutation in `POST /deliveries/{id}/retry` and `POST /deliveries/{id}/reroute` with new attempt row creation  
**Validation:** Prior attempt rows unchanged after retry; `delivery_attempts` count increments  
**Delegation:** Codex medium (`--provider openai --tier medium`) — depends on W3-T1

### W3-T3: Archive original note after successful processing
**Kit:** cavekit-intake-writeback.md R4, R5, R6  
**Write set:** `promptforge_watcher/writeback.py`, `promptforge_watcher/watcher.py`, `tests/`  
**Action:** After compile+persist, move original note to `_archive/processed/`; write output as separate file; no rewrite of original  
**Validation:** Integration test: valid note processed → original in archive (unchanged), output file in output folder, no output written until dispatch  
**Delegation:** Codex medium (`--provider openai --tier medium`)

---

## Wave 4: Narrow Console (medium risk)

### W4-T1: Compact bootstrap payload
**Kit:** cavekit-console.md R4  
**Write set:** `promptforge_services/console_api.py` (`/bootstrap` handler), `promptforge_services/console_queries.py`, `tests/test_console_read_endpoints.py`  
**Action:** Replace mega-bootstrap with: queue depth, recent intake notes (20), recent deliveries (20), active targets, runtime settings, health  
**Validation:** Bootstrap response contains no raw `utterances`, `transcript_revisions`, `llm_runs`, etc.; response < 500ms  
**Delegation:** Codex medium (`--provider openai --tier medium`)

### W4-T2: Remove deferred routes from console UI navigation
**Kit:** cavekit-console.md R3  
**Write set:** Frontend route config (if applicable), `promptforge_services/console_api.py`  
**Action:** Deferred routes remain in code but not linked from UI navigation; not included in bootstrap  
**Validation:** UI navigation contains only queue/review, delivery ops, settings  
**Delegation:** Codex medium (`--provider openai --tier medium`)

### W4-T3: Compact metrics — queue-depth only
**Kit:** cavekit-console.md R5  
**Write set:** `promptforge_services/console_api.py` (`/metrics/queue-depth`)  
**Action:** Update `/metrics/queue-depth` to return `{ queued, dispatching, failed_last_24h }`; deferred metrics routes not surfaced  
**Validation:** `GET /metrics/queue-depth` returns 3 fields; no metrics nav beyond queue-depth  
**Delegation:** Haiku (`--provider anthropic --tier low`)

### W4-T4: Failure visibility in console
**Kit:** cavekit-ops-baseline.md R4, cavekit-console.md  
**Write set:** `promptforge_services/console_api.py`, frontend  
**Action:** Add endpoint or extend existing to surface `workflow_error_records` for last 24h; show in console  
**Validation:** Console shows workflow errors; operator can dismiss  
**Delegation:** Codex medium (`--provider openai --tier medium`)

### W4-T5: Runbook and ops docs
**Kit:** cavekit-ops-baseline.md R1, R2, R3  
**Write set:** `RUNBOOK.md`, `README.md`  
**Action:** Write `RUNBOOK.md` covering start/stop, health check, note failure triage, backup/restore, restore verification; update README with localhost-only statement  
**Validation:** RUNBOOK.md exists; contains all required sections  
**Delegation:** Claude Sonnet (`--provider anthropic --tier medium`) — doc writing

### W4-T6: Health endpoint truthful status
**Kit:** cavekit-ops-baseline.md R5  
**Write set:** `promptforge_services/console_api.py` or `promptforge_services/api.py` (`/health` handler), `tests/`  
**Action:** Update or create `/health` to return `{ "db": "ok"|"error", "vault": "ok"|"error", "watcher": "running"|"unknown" }`; DB check via `SELECT 1`; vault check via path existence; response time < 200ms  
**Validation:** `GET /health` returns all 3 fields; DB or vault outage reflected in response; response time measured  
**Delegation:** Haiku (`--provider anthropic --tier low`)

---

## Delete vs Defer vs Rewrite Summary

| Item | Decision | Rationale |
|------|----------|-----------|
| `POST /admin/purge-archived-notes` | DELETE | Admin op, out of scope |
| `PATCH /settings/secrets` | DELETE | Stubbed 501, not scope |
| `POST /dictionary/upsert` | DELETE | Stubbed 501, not scope |
| `delivery_session_registry` table | DELETE | Live-session cut |
| `console_admin_audit_log` table | DELETE | Single-user, no audit needed |
| `console_secret_settings` table | DELETE | Secrets rotation deferred |
| Live-session dispatch code | DELETE | Live-session cut |
| Role/auth header logic | DELETE | Single-user, no auth needed |
| `GET /lineage/{id}` | DEFER | Useful, not core ops |
| `GET /metrics/throughput` | DEFER | Over-build for phase 2 |
| `GET /metrics/sla` | DEFER | Over-build for phase 2 |
| `GET /metrics/error-fingerprints` | DEFER | Over-build for phase 2 |
| `GET /processing/failed` | DEFER | Scope overlap with errors |
| `GET /logs` | DEFER | Not compact ops summary |
| Bootstrap mega-payload | REWRITE | Compact + task-oriented |
| Delivery retry/reroute | REWRITE | Append-only attempts |
| Watcher main loop | REWRITE | Per-note isolation |
| Architecture docs | REWRITE | Match runtime truth |

---

## Validation Commands

```bash
# Wave 1 validation
grep -rn "X-Role\|x-role\|default_role\|admin_fallback" promptforge_services/ promptforge_watcher/
grep -rn "tmux\|live_session\|send-keys" promptforge_services/delivery_dispatch.py
grep -rn "delivery_session_registry\|console_admin_audit_log\|console_secret_settings" promptforge_services/
grep -rn "purge-archived\|dictionary/upsert" promptforge_services/console_api.py

# Wave 2 validation
python -m pytest tests/test_watcher.py -k "failure_isolation"
python -m pytest tests/ -k "vault_path_containment"
python -m pytest tests/ -k "strict_parse"

# Wave 3 validation
python -m pytest tests/ -k "delivery_attempt"
python -m pytest tests/ -k "retry_append_only"

# Wave 4 validation
python -m pytest tests/test_console_read_endpoints.py -k "bootstrap"
curl -s http://localhost:8000/api/v1/console/bootstrap | jq 'keys'
```
