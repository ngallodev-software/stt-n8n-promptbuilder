# Cavekit: Kanban Task Creation Harness

## Scope

This cavekit defines a local-only Prompt Forge backend harness that turns Prompt Forge-generated artifacts into Kanban import manifests and applies them to a locally running Kanban roll-up instance.

It covers:

- manifest derivation from existing Prompt Forge data
- a narrow Kanban client adapter
- apply and reconcile behavior
- local validation against the live Kanban roll-up branch

It does not cover:

- production deployment
- remote auth/authz
- generalized multi-target orchestration
- replacing Prompt Forge delivery or Kanban execution ownership

## Requirements

### R1: Prompt Forge remains source of planning truth

**Description:** Prompt Forge owns prompt generation, review context, lineage, and manifest derivation. Kanban owns created task cards and execution state after import.

**Acceptance Criteria:**
- [ ] Prompt Forge stores or computes the import manifest from existing Prompt Forge records, not from Kanban readback.
- [ ] No Prompt Forge feature assumes Kanban is canonical for prompt text, lineage, or review state.
- [ ] Apply/reconcile code treats Kanban as execution truth only after import succeeds.

### R2: Harness uses Kanban import `v1`, not broad state mutation

**Description:** The harness submits only the narrow Kanban import contract already available on roll-up.

**Acceptance Criteria:**
- [ ] Kanban writes use `workspace.importTasks` or the equivalent local CLI wrapper.
- [ ] Harness does not call Kanban `saveState` as the primary write path.
- [ ] Harness request body matches the Kanban import `v1` schema exactly.

### R3: Manifest derivation is explicit and deterministic

**Description:** Prompt Forge must translate its canonical records into a Kanban import manifest through one deterministic mapping layer.

**Acceptance Criteria:**
- [ ] One function/module owns conversion from Prompt Forge artifact(s) to Kanban manifest `v1`.
- [ ] Mapping of every Kanban import field is documented: `externalTaskKey`, `title`, `prompt`, `startInPlanMode`, `autoReviewEnabled`, `autoReviewMode`, `images`, `agentId`, `clineSettings`, `baseRef`, `links`, and `startTaskExternalKeys`.
- [ ] Every Kanban import field has one documented rule: mapped from Prompt Forge, intentionally omitted in v1 first cut, or blocked by a harness-level preflight rule.
- [ ] Missing required Kanban fields fail before any Kanban write.

### R4: External identity is stable

**Description:** Prompt Forge must emit stable `externalTaskKey` values for replay safety.

**Acceptance Criteria:**
- [ ] The immutable source boundary is `prompt_generation.id`.
- [ ] `externalTaskKey` is derived from immutable source identity, not rendered prompt text, title, or mutable UI state.
- [ ] Re-running the same apply against the same `prompt_generation.id` yields the same `externalTaskKey` values.
- [ ] If stable identity cannot be derived, the harness refuses to apply.

### R5: Apply is reconcile-first

**Description:** The harness must treat Kanban response mappings as authoritative for realized task identity and link identity.

**Acceptance Criteria:**
- [ ] Apply response is captured and persisted or logged as an apply record.
- [ ] Reconcile step checks `taskMappings`, `linkResults`, and `startResults`.
- [ ] Import failure and start failure are recorded as separate states. Start failure is not misreported as import failure.
- [ ] Failure or ambiguity is surfaced as a Prompt Forge-side apply failure, not hidden.

### R6: Local validation uses live Kanban

**Description:** The planning target is a local dogfood loop against `kanban` roll-up, not mock-only validation.

**Acceptance Criteria:**
- [ ] Validation plan includes one live Kanban runtime path.
- [ ] Validation proves task creation, link realization, replay behavior, and optional start behavior.
- [ ] Validation explicitly covers Kanban fail-closed error codes: `duplicate_task_key`, `conflicting_task_intent`, `missing_link_task`, `invalid_link`, and `invalid_start_task`.
- [ ] Validation is split into import/replay validation first, then optional start validation.
- [ ] Validation checks live response plus realized Kanban state.

### R7: v1 stays narrow

**Description:** First implementation is a local harness, not a productized distributed integration layer.

**Acceptance Criteria:**
- [ ] v1 supports one explicitly bound local Kanban workspace target.
- [ ] Workspace binding comes from Prompt Forge project-scoped runtime settings after those fields are added.
- [ ] Required binding fields are `kanbanBaseUrl` and `kanbanWorkspaceId`.
- [ ] Harness refuses apply when either field is missing.
- [ ] Harness does not auto-create Kanban workspaces in v1.
- [ ] The workspace binding rule is documented, including how the workspace is identified and reused across replays.
- [ ] v1 does not add generalized remote target management.
- [ ] v1 does not alter unrelated Prompt Forge delivery semantics.

## Out of Scope

- Kanban board-state import beyond `workspace.importTasks`
- multi-user coordination
- background auto-dispatch into Kanban
- full operator reconciliation UI
- automatic repair when identity is ambiguous

## Residual Risks

- Start behavior remains less deterministic than pure import because it depends on live Kanban runtime/session services.
- Revisions to Prompt Forge source artifacts must follow one explicit identity policy or replay will fail closed by design.
- Local workspace drift can invalidate replay tests if the harness targets the wrong workspace or re-creates workspaces implicitly.

## Cross-References

- `context/refs/kanban-local-harness.md`
- `kanban-integration-idea/docs/Phase2/013-minimal-kanban-integration-feature.md`
