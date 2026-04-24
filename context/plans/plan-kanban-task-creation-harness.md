# Plan: Kanban Task Creation Harness

## Goal

Add a local Prompt Forge backend harness that:

1. derives Kanban import manifests from Prompt Forge artifacts
2. applies them through Kanban import `v1`
3. validates outcomes against a live local Kanban roll-up runtime

## Brownfield Entry Points

Use existing Prompt Forge seams:

- `promptforge_services/models.py`
  - `AgentTaskV1`
- `promptforge_services/api.py`
  - deterministic compile pipeline
- `promptforge_services/console_api.py`
  - prompt clone / review / delivery actions

Use existing Kanban seams:

- `/lump/apps/kanban/src/trpc/workspace-api.ts`
  - `workspace.importTasks`
- `/lump/apps/kanban/src/core/api-contract.ts`
  - import `v1` contract
- `/lump/apps/kanban/src/commands/task.ts`
  - `task import --file`

## Architecture Decision

v1 should use a dedicated Prompt Forge adapter module, not mutate existing delivery semantics.

Reason:

- Prompt Forge `Destination` and delivery targets do not currently model Kanban.
- reusing delivery dispatch directly would overload a concept that already means downstream dispatch
- a dedicated harness keeps Kanban-specific logic narrow and reversible

## Locked Planning Decisions

- canonical immutable source boundary is `prompt_generation.id`
- `externalTaskKey` must derive from immutable source identity plus revision, never from rendered prompt text or mutable UI state
- every Kanban import field must have one explicit rule: mapped, intentionally omitted in v1 first cut, or blocked by harness preflight
- import/replay validation and optional start validation are separate gates
- v1 must bind to one explicit local Kanban workspace identity
- workspace binding source is planned Prompt Forge project-scoped runtime settings: `kanbanBaseUrl` + `kanbanWorkspaceId`
- v1 must fail fast when workspace binding missing; no implicit workspace creation
- preview payload must be backend-owned; UI cannot reconstruct the manifest independently

## Detailed Tickets

### T-01 Brownfield seam audit write-up

- model: `gpt-5.4-mini low`
- goal: capture exact file anchors and current invariants before code changes
- deliverable:
  - update `context/impl/impl-kanban-task-creation-harness.md`
- validation:
  - all target files and seams referenced with paths

### T-02 Define Prompt Forge -> Kanban manifest mapping

- model: `gpt-5.4-mini low`
- goal: specify deterministic mapping from Prompt Forge records to Kanban import `v1`
- scope:
  - canonical immutable source artifact choice: `prompt_generation.id`
  - `externalTaskKey` derivation rule
  - mapping or explicit preflight failure for every Kanban import field
  - workspace binding rule from project-scoped runtime settings
  - import-vs-start status model
- deliverable:
  - mapping section in impl doc or dedicated backend helper doc
- validation:
  - every required Kanban field has one source or one explicit failure rule
  - one workspace binding rule is documented
  - `prompt_generation.id` is documented as the immutable identity boundary

### T-03 Add Kanban workspace binding settings fields

- model: `gpt-5.4-mini low`
- goal: add planned Prompt Forge runtime settings fields needed for harness binding
- scope:
  - `kanbanBaseUrl`
  - `kanbanWorkspaceId`
  - backend settings model + API
  - console typed settings surface needed to read/edit them
- validation:
  - settings contract documents both keys
  - missing binding remains a preflight failure
  - no implicit workspace create behavior added

### T-04 Add backend manifest builder module

- model: `gpt-5.4-mini medium`
- goal: implement pure manifest derivation code
- likely files:
  - `promptforge_services/`
- constraints:
  - no network side effects
  - deterministic output
- validation:
  - unit tests for mapping and failure cases
  - unit tests for stable `externalTaskKey` replay
  - unit tests for unsupported-field preflight failure

### T-05 Add Kanban client adapter module

- model: `gpt-5.4-mini medium`
- goal: implement one narrow local client for Kanban import
- choices to keep explicit:
  - direct HTTP/tRPC-compatible JSON call preferred
  - CLI fallback allowed only if direct call cannot be made safely
- validation:
  - adapter tests for success, structured failure, network failure
  - adapter requires explicit workspace binding input
  - adapter tests missing `kanbanBaseUrl`
  - adapter tests missing `kanbanWorkspaceId`

### T-06 Add apply/reconcile service

- model: `gpt-5.4-mini medium`
- goal: combine builder + client + response reconciliation
- scope:
  - submit manifest
  - capture apply result
  - surface failure/ambiguity
- validation:
  - tests for idempotent replay and fail-closed errors
  - tests that distinguish import failure from start failure
  - apply record captures `ok`, `applied`, `taskMappings`, `linkResults`, `startResults`, and source artifact identity

### T-07 Add local harness command or script

- model: `gpt-5.4-mini low`
- goal: make local dogfood repeatable
- examples:
  - script that takes prompt id or intake note id and applies to Kanban
- validation:
  - one documented command path runs end to end locally

### T-08 Live validation against Kanban roll-up

- model: `gpt-5.4-medium`
- goal: prove real integration behavior
- must validate:
  - task creation
  - link realization
  - replay/idempotency
  - optional start behavior
  - realized state matches response
  - explicit workspace reuse
  - fail-closed error codes
- validation:
  - integration script or test doc with exact commands

### T-09 Final doc pass

- model: `gpt-5.4-mini low`
- goal: close tracking, cavekit, and operator notes
- validation:
  - tracking doc reflects done/pending state

## Validation Gates

### Gate A: Mapping gate

- manifest derivation is deterministic
- stable external keys proven in tests
- every Kanban import field is mapped or explicitly rejected

### Gate B: Adapter gate

- Kanban client can submit import `v1`
- failure payloads preserved without lossy translation
- workspace binding is explicit and tested

### Gate C: Reconcile gate

- apply captures authoritative Kanban mappings
- replay does not create duplicates
- import failure and start failure remain distinguishable in stored results

### Gate D: Live local gate

- local Kanban roll-up accepts manifest
- realized state matches expected created graph
- replay hits the same workspace and same realized tasks
- known import error codes are exercised at least once

## Non-Goals

- Kanban production deployment support
- remote Kanban discovery
- generalized target registry for Kanban instances
- bidirectional sync from Kanban back into Prompt Forge
