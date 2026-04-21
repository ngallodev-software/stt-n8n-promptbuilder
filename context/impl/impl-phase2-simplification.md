# Implementation Tracking: Phase 2 Simplification

## Status: IN_PROGRESS

**Last Updated:** 2026-04-20 (Wave 1-4 delegation run)  
**Current Phase:** Execution — Wave 1-4 delegated; validation needed  
**Blocking Issues:** W2-T2, W3-T1/T2, W4-T5 agents completed but produced no changes — need re-delegation with more precise entry points

---

## Task Status

| Task ID | Task | Status | Notes |
|---------|------|--------|-------|
| W1-T1 | Remove 3 CUT routes (purge, secrets PATCH, dictionary upsert) | DONE | Validated: no route decorators remain |
| W1-T2 | Remove role/auth header logic | DONE | Validated: no X-Role refs in services |
| W1-T3 | Drop live-session delivery code | DONE | Validated: no tmux/live_session refs |
| W1-T4 | Rewrite architecture docs | DONE | Validated: arch doc correct, no false claims |
| W1-T5 | Drop delivery_session_registry table | DONE | Migration file created |
| W1-T6 | Drop console_admin_audit_log and console_secret_settings | DONE | Source clean; migration file created |
| W1-T7 | Gate LLM assist behind opt-in setting | DONE | Agent completed; needs spot-check |
| W2-T1 | Watcher per-note failure isolation | DONE | try/except present in watcher.py |
| W2-T2 | Vault path containment check | NEEDS_RERUN | Agent completed but no is_relative_to found — delivery_dispatch.py may lack obsidian write path |
| W2-T3 | Strict intake note parser | DONE | Agent completed; needs spot-check |
| W2-T4 | Delivery safety metadata enforcement | DONE | Agent completed; needs spot-check |
| W2-T5 | Enforce webhook/n8n targets as queue-only | DONE | Agent completed; needs spot-check |
| W3-T1 | Create delivery_attempts table + W3-T2 retry/reroute append-only | NEEDS_RERUN | Agent completed but migration file not found; console_api has no delivery_attempts refs |
| W3-T3 | Archive original note + separate output file | DONE | Agent completed; needs spot-check |
| W4-T1 | Compact bootstrap payload | DONE | Agent completed; needs spot-check |
| W4-T2 | Remove deferred routes from console UI | NOT_STARTED | Low priority; deferred routes already hidden |
| W4-T3 | Compact metrics (queue-depth only) | DONE | Agent completed; needs spot-check |
| W4-T4 | Failure visibility in console | DONE | Agent completed; needs spot-check |
| W4-T5 | Runbook and ops docs | NEEDS_RERUN | RUNBOOK.md not found at repo root |
| W4-T6 | Health endpoint truthful status | DONE | Agent completed; needs spot-check |

### Task Dependencies
- W2-T1 through W2-T4 blocked by W1 complete (cleaner codebase to harden)
- W3-T1 requires human review of migration SQL before execution
- W3-T2 blocked by W3-T1
- W4-T1 benefits from W3-T1 complete (attempt history in bootstrap)
- W4-T4 requires W2-T1 complete (error records schema must exist)

---

## Inventory Results (from Haiku run 2026-04-20)

Route classification from Haiku inventory:
- **KEEP (31):** delivery ops (8), queue ops (6), settings (2), rules (4), templates (5), dictionary read (1), prompts (1), projects (1), metrics queue-depth (1), llm assist opt-in (1), bootstrap (1)
- **CUT (3):** `/admin/purge-archived-notes`, `/settings/secrets` PATCH, `/dictionary/upsert` POST
- **DEFER (5):** `/lineage/{id}`, `/metrics/throughput`, `/metrics/sla`, `/metrics/error-fingerprints`, `/processing/failed`

Note: `/logs` GET also DEFER (missed in count, add to deferred surface).

Table classification:
- **DELETE:** `delivery_session_registry`, `console_admin_audit_log`, `console_secret_settings`
- **KEEP:** all others in canonical compiler graph

Table drop safety (from Explore agent verification run 2026-04-20):
- `delivery_session_registry` — SAFE, zero code refs; migration only
- `console_admin_audit_log` — requires code cleanup first: stub inserts at secrets_migration.py:48, console_api.py:510; delete dependent test assertions
- `console_secret_settings` — requires code cleanup first: stub secrets_migration.py:18,34; stub _safe_fetch_settings_rows SELECT at console_api.py:443; delete/skip test fixtures in test_console_settings.py and test_secrets_migration.py

---

## Files Created

| File | Purpose | Kit Reference |
|------|---------|---------------|
| `context/kits/cavekit-overview.md` | Kit index | All kits |
| `context/kits/cavekit-architecture.md` | Architecture & ownership | architecture.md |
| `context/kits/cavekit-data-model.md` | Schema simplification | data-model.md |
| `context/kits/cavekit-console.md` | Console reduction | console.md |
| `context/kits/cavekit-intake-writeback.md` | Intake & writeback contract | intake-writeback.md |
| `context/kits/cavekit-ops-baseline.md` | Ops baseline | ops-baseline.md |
| `context/plans/plan-phase2-simplification.md` | Implementation plan | All kits |
| `context/impl/impl-phase2-simplification.md` | This document | — |

## Files Modified

None yet.

---

## Issues & TODOs

- [ ] **TODO:** W3-T1 migration SQL needs human review before execution against live DB
- [ ] **TODO:** Confirm whether `/logs` GET should be DEFER or CUT — likely DEFER
- [ ] **TODO:** Confirm whether `llm/assist` route stays under strict opt-in gate (currently KEEP with conditional 501)
- [ ] **TODO:** Frontend route config path not yet identified — needed for W4-T2

---

## Dead Ends & Failed Approaches

### DE-1: codex-job with `--provider anthropic --tier low` initially routed to Codex CLI
**What was attempted:** Delegation to Haiku via `--provider anthropic --tier low`  
**Root cause of failure:** `run_codex_task.sh` hardcoded `codex exec` regardless of provider; `invoke_codex_with_review.sh` checked for Codex session ID (not present in claude output) and for log size > 100 lines (claude -p produces much shorter logs)  
**What was fixed:** Updated both installed and source scripts: binary check, command construction, session ID check, log size check all now branch on `MODEL_PROVIDER=anthropic`  
**Verdict:** Fixed. Haiku delegation via claude CLI now works. Log: 35s run completed successfully.

---

## Delegation Log

| Run | Model | Task | Status | Notes |
|-----|-------|------|--------|-------|
| 2026-04-20 | claude-haiku-4-5 | Route inventory and classification | SUCCESS (35s) | Output captured in impl doc above |

---

## codex-job Weaknesses Discovered

Logged per simplification brief mandate:

1. **Provider routing not implemented in runner** — `--provider anthropic` was accepted as a flag but did not change which CLI was invoked. Fixed in this session.
2. **Session ID check Codex-specific** — `invoke_codex_with_review.sh` failed claude runs because it expected a Codex UUID session ID. Fixed.
3. **Log size check Codex-specific** — 100-line minimum log check failed claude -p runs which produce short logs. Fixed.
4. **SKILL.md had stale model `gpt-5.1-codex-mini`** — no longer in registry. Fixed to `gpt-5.4-mini`.

Follow-up planned in `/lump/apps/invoke-codex-from-claude/agent-notes/`.

---

## Test Health

| Suite | Passing | Failing | Notes |
|-------|---------|---------|-------|
| Unit/integration | Unknown | Unknown | Not run yet; will baseline after W1 complete |

---

## Session Log

### Session 2 (2026-04-20, continued)
- Applied advisor fixes: resolved R1/R2 contradiction in intake-writeback kit
- Added R8 (LLM opt-in policy) to cavekit-architecture.md
- Added R9 (webhook/n8n queue-only) to cavekit-console.md
- Ran table inventory (Explore agent): delivery_session_registry safe to drop; audit/secrets tables need code cleanup
- Ran peer review (cavekit-reviewer agent): 3 WARNINGs + 3 SUGGESTIONs — all resolved
- Fixed dangling cross-ref in data-model (R3→R1)
- Fixed untestable AC in architecture R2
- Fixed "or equivalent" ambiguity in ops-baseline R3
- Fixed Out of Scope collision-handling wording in intake-writeback
- Added 3 missing plan tasks: W1-T7 (LLM gate), W2-T5 (webhook queue-only), W4-T6 (health endpoint)
- Expanded W1-T6 write set with specific file+line cleanup targets from table inventory
- Plan now covers all 29 kit requirements; 21 tasks across 4 waves

### Session 1 (2026-04-20)
- Read red-team review and simplification brief
- Surveyed codebase: 44 console routes, 18 tables, 3263 LOC console_api.py
- Fixed codex-job Anthropic provider support (3 files in both installed and source)
- Ran Haiku route inventory delegation (success, 35s)
- Wrote 5 domain kits + overview
- Wrote implementation plan (4 waves, 18 tasks)
- Wrote this tracking document
