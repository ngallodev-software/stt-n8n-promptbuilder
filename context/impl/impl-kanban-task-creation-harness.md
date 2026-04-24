# Impl Tracking: Kanban Task Creation Harness

## Status

- phase: complete
- branch: `fork/feature-request/kanban-task-creation-harness`
- implementation: complete

## Confirmed Facts

- Prompt Forge already has deterministic artifact contracts in `promptforge_services/models.py`.
- Prompt Forge already has compile endpoints in `promptforge_services/api.py`.
- Kanban roll-up already has `workspace.importTasks`.
- Kanban roll-up already has CLI wrapper `task import --file`.

## Planning Decisions Locked

- local-only harness first
- Prompt Forge remains planning truth
- Kanban remains execution truth
- direct Kanban import `v1` is target contract
- no broad state replacement
- no production networking assumptions
- backend owns manifest preview payload
- import status and start status must be tracked separately
- explicit local Kanban workspace binding is required
- canonical source artifact is `prompt_generation.id`
- workspace binding source for harness v1 will be project-scoped Prompt Forge runtime settings after those fields are added
- required runtime settings keys for harness v1: `kanbanBaseUrl`, `kanbanWorkspaceId`
- v1 must not auto-create Kanban workspaces
- v1 maps one `prompt_generation.id` to one Kanban task
- linked multi-task chains are out of scope for first harness cut

## Red-Team Changes Absorbed

- Manifest mapping must cover every field Kanban compares during replay compatibility checks, not only `title`, `prompt`, `baseRef`, links, and start keys.
- Unsupported Kanban import fields must fail in preflight. Silent field drop is forbidden.
- `externalTaskKey` must derive from one immutable Prompt Forge source boundary plus revision.
- Apply logs must persist `ok`, `applied`, `taskMappings`, `linkResults`, `startResults`, source artifact identity, and workspace binding.
- Validation must cover known fail-closed Kanban errors and separate pure import/replay from optional task start behavior.

## Open Questions For Implementation

- Whether local Kanban adapter should speak direct HTTP JSON only, or support CLI fallback from day one

## Required Before Coding

- document the workspace binding rule
- document handling for each optional Kanban import field
- define the apply record shape that stores partial-success start results

## T-02 Mapping Spec

### Source Boundary

- canonical source artifact: `prompt_generation.id`
- v1 unit of import: exactly one `PromptGenerationRecord`
- one apply operation may submit one Kanban task in v1

### Workspace Binding

- source for harness v1 target binding: project-scoped Prompt Forge runtime settings
- required keys:
  - `kanbanBaseUrl`
  - `kanbanWorkspaceId`
- current state:
  - these keys do not exist yet in `ConsoleRuntimeSettings`
  - implementation must add them before apply path can ship
- preflight failure:
  - missing `kanbanBaseUrl` -> `kanban_binding_missing_base_url`
  - missing `kanbanWorkspaceId` -> `kanban_binding_missing_workspace_id`

### Kanban Import Field Mapping

| Kanban field | Source | Rule |
| --- | --- | --- |
| `version` | constant | always `v1` |
| `tasks[0].externalTaskKey` | `prompt_generation.id` | `pf:pg:<prompt_generation.id>` |
| `tasks[0].title` | none in current PF source model | omit in v1 first cut unless explicit stable title source is added |
| `tasks[0].prompt` | `prompt_generation.final_prompt_markdown` | must be non-empty after trim |
| `tasks[0].startInPlanMode` | supported by Kanban contract, no PF source field yet | omit in v1 first cut; future override path may map from harness settings |
| `tasks[0].autoReviewEnabled` | supported by Kanban contract, no PF source field yet | omit in v1 first cut; future override path may map from harness settings |
| `tasks[0].autoReviewMode` | supported by Kanban contract, no PF source field yet | omit in v1 first cut; future override path may map from harness settings |
| `tasks[0].images` | supported by Kanban contract, no PF source field yet | omit in v1 first cut; future override path may map from source metadata |
| `tasks[0].agentId` | supported by Kanban contract, no PF source field yet | omit in v1 first cut; future override path may map from project/runtime settings |
| `tasks[0].clineSettings` | supported by Kanban contract, no PF source field yet | omit in v1 first cut; future override path may map from project/runtime settings |
| `tasks[0].baseRef` | supported by Kanban contract, no PF source field yet | omit in v1 first cut; future override path may map from project settings |
| `links[]` | none in v1 | always empty/omitted |
| `startTaskExternalKeys[]` | explicit harness option only | optional; when enabled, contains `tasks[0].externalTaskKey` |

### Title Rule

- do not use title as identity input
- v1 first cut omits `title`
- Kanban replay compatibility tolerates omitted `title`; Kanban resolves display title from `title` or `prompt`
- future title support requires one explicit PF source field, not synthetic title guesswork

### Preflight Failure Rules

- empty `final_prompt_markdown` -> `kanban_manifest_missing_prompt`
- missing workspace binding -> binding error above
- source artifact not found -> `prompt_generation_not_found`
- source artifact status policy not yet locked in product code -> keep as plan decision, not current invariant

### Source Status Rule

- recommended v1 policy: allow only `rendered`
- current state: this gate does not exist yet in Prompt Forge code
- implementation must add explicit validation + tests before relying on it

### Apply Result Record

Apply record must store:

- `prompt_generation_id`
- `external_task_key`
- `kanban_base_url`
- `kanban_workspace_id`
- full request manifest
- full Kanban response
- derived status:
  - `import_failed`
  - `import_applied`
  - `start_partial_failure`
  - `start_succeeded`

## Audit Corrections

- Kanban contract supports more task fields than Prompt Forge currently sources.
- v1 first cut should omit currently unsourced optional Kanban fields instead of mislabeling them unsupported by Kanban.
- `title` should be omitted until Prompt Forge has a real stable title source.
- workspace binding keys are planned additions to Prompt Forge settings, not current model facts.

## Risks

- Prompt Forge `AgentTaskV1` is close to, but not equal to, Kanban import `v1`
- external key derivation can become unstable if based on mutable fields
- mock-friendly console behaviors can hide real backend or Kanban runtime failures
- live workspace drift can make replay checks meaningless if the target workspace is not pinned

## Implemented

- added Prompt Forge backend runtime settings support for:
  - `kanbanBaseUrl`
  - `kanbanWorkspaceId`
- added backend validation for both runtime settings keys
- added pure builder module:
  - `promptforge_services/kanban_manifest_builder.py`
- added Kanban client adapter module:
  - `promptforge_services/kanban_client.py`
- added backend-owned preview/apply routes:
  - `GET /console/prompts/{prompt_generation_id}/kanban/preview`
  - `POST /console/prompts/{prompt_generation_id}/kanban/apply`
- added focused builder tests:
  - `tests/test_kanban_manifest_builder.py`
- added focused adapter and route tests:
  - `tests/test_kanban_client.py`
  - `tests/test_console_kanban_harness.py`
- extended backend settings tests for Kanban binding persistence and validation

## Validation

- `pytest tests/test_console_settings.py tests/test_kanban_manifest_builder.py`
  - pass
- `pytest tests/test_console_settings.py tests/test_kanban_manifest_builder.py tests/test_kanban_client.py tests/test_console_kanban_harness.py`
  - pass
- `python3 -m compileall promptforge_services`
  - pass
- live local dogfood against roll-up Kanban:
  - Prompt Forge apply route returned `ok=true`, `applied=true`
  - Kanban workspace state contained one backlog card with `externalTaskKey=pf:pg:pg_live_001`
  - verified workspace id: `pf-kanban-live-hqcq0l`

## Remaining

- no multi-task chain fanout in v1
- no start-task path in v1
- no reverse sync from Kanban into Prompt Forge
