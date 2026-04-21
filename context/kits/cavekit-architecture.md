# Cavekit: Architecture & Ownership

## Scope

Defines the simplified runtime architecture for phase 2. Covers workflow ownership, entrypoint boundaries, delivery state machine ownership, and what gets deleted or deferred.

## Requirements

### R1: Python Is Sole Workflow Owner

**Description:** All intake, parse, compile, validate, generate, deliver, retry, and canonical state transitions are owned by Python. No other system initiates or arbitrates these transitions.

**Acceptance Criteria:**
- [ ] No n8n workflow triggers delivery dispatch directly
- [ ] No n8n workflow writes to `deliveries`, `delivery_attempts`, or lifecycle columns
- [ ] Watcher module owns the intake→compile→persist path without external orchestration
- [ ] Console API owns operator-triggered delivery dispatch (retry, reroute, dispatch)
- [ ] n8n may only react to webhook events fired by Python after canonical state is written

### R2: Watcher and API Are Two Entrypoints to One Python Core

**Description:** The watcher (file-watch daemon) and the API (HTTP service) share the same pipeline, repository, and delivery logic. They are entrypoints, not separate services with separate ownership.

**Acceptance Criteria:**
- [ ] `promptforge_watcher` and `promptforge_services` import shared pipeline/repository code
- [ ] No duplicate delivery dispatch logic exists across watcher and API
- [ ] A module-level docstring or comment in both `promptforge_watcher/__init__.py` and `promptforge_services/__init__.py` references the shared core (grep-verifiable)

### R3: Postgres Is Canonical Truth

**Description:** Postgres holds all durable state. Obsidian files are intake surface and output surface only — not canonical history.

**Acceptance Criteria:**
- [ ] No doc or comment describes vault files as canonical or immutable source of truth
- [ ] After writeback, the canonical record of what was processed is in Postgres, not the vault file
- [ ] All lineage queries read from Postgres, not vault filesystem

### R4: n8n Is Optional Reactive Sidecar Only

**Description:** n8n may exist as an outbound automation adapter. It reacts to events Python fires. It does not own workflow, queue semantics, retries, or canonical state.

**Acceptance Criteria:**
- [ ] n8n workflows are not required for PromptForge to process and deliver notes
- [ ] n8n is documented as optional, not as a required architecture layer
- [ ] Removing n8n does not break core compile/queue/delivery flow
- [ ] All docs updated to reflect reactive-only role

### R5: Live-Session Delivery Is Removed from Phase 2 Scope

**Description:** tmux live-session delivery is cut. The target type, dispatch path, session registry, and tests for live-session delivery are removed or disabled for phase 2.

**Acceptance Criteria:**
- [ ] `delivery_session_registry` table is dropped or migration exists to drop it
- [ ] Live-session target type produces a clear "not supported in phase 2" error if attempted
- [ ] `test_delivery_dispatch_live_sessions.py` is deleted or all tests marked skip with explanation
- [ ] No live-session dispatch code paths remain in active `delivery_dispatch.py`

### R6: Role/Auth Headers Removed Entirely

**Description:** The caller-supplied role header mechanism and any default-admin fallback are deleted. Phase 2 is single-user local-only. No auth model is needed.

**Acceptance Criteria:**
- [ ] No `X-Role` or equivalent header parsing exists in console_api.py
- [ ] No `default_role` or `admin_fallback` logic exists anywhere in services
- [ ] Removing auth headers does not require replacing them with any other auth mechanism
- [ ] All tests referencing role headers are updated to remove role header setup

### R7: Architecture Docs Match Runtime Truth

**Description:** The architecture document, MVP plan, and any diagram describe the actual system — Python-owned workflow, Postgres canonical truth, n8n as optional sidecar, vault as intake/output.

**Acceptance Criteria:**
- [ ] `docs/promptforge-system-architecture.md` updated to describe actual runtime
- [ ] `docs/planning/promptforge_mvp_master_plan.md` updated or archived; no false claims
- [ ] No doc claims n8n orchestrates workflow
- [ ] No doc claims vault files are immutable canonical history

### R8: LLM Assist Is Explicit Opt-In Only

**Description:** LLM-powered features (prompt enhancement, auto-suggest, etc.) are never invoked automatically as part of intake, compile, or delivery. They require explicit operator opt-in per-operation. The `/llm/assist` endpoint stays gated behind an opt-in flag.

**Acceptance Criteria:**
- [ ] No LLM call is made during intake, parse, compile, or queue phases without operator action
- [ ] `/llm/assist` endpoint requires an explicit opt-in parameter or setting to be active; returns 501 if not opted in
- [ ] LLM assist, if invoked, does not alter canonical DB state — output is advisory only
- [ ] No default-on LLM assist path exists in any code path

## Out of Scope

- Multi-user support
- Auth/authz system design
- Remote/network-safe deployment
- Adding new delivery target types
- Expanding n8n beyond reactive sidecar
- Performance optimization beyond correctness

## Cross-References

- Depends on: cavekit-data-model.md R1 (delivery attempts backing append-only history)
- Depends on: cavekit-console.md R1 (console limited to operator surface)
- See also: cavekit-intake-writeback.md (vault write semantics)
- See also: cavekit-ops-baseline.md (localhost-only posture)
