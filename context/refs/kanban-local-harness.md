# Kanban Local Harness Reference

## Purpose

Ground Prompt Forge planning against real Kanban seams already available on local roll-up branch.

## Target Kanban Runtime

- Repo: `/lump/apps/kanban`
- Branch: `fork/feature-requests/roll-up`
- Local branch state when this ref was written:
  - build passes
  - `workspace.importTasks` exists
  - `task import --file <path>` exists

## Confirmed Kanban Import Contract

Primary seam:

- `workspace.importTasks`
  - file: `/lump/apps/kanban/src/trpc/workspace-api.ts`

CLI seam on top of same contract:

- `task import --file <path>`
  - file: `/lump/apps/kanban/src/commands/task.ts`

Contract schema:

- file: `/lump/apps/kanban/src/core/api-contract.ts`

Request shape:

- `version: "v1"`
- `tasks[]`
  - `externalTaskKey`
  - optional `title`
  - `prompt`
  - optional `startInPlanMode`
  - optional `autoReviewEnabled`
  - optional `autoReviewMode`
  - optional `images`
  - optional `agentId`
  - optional `clineSettings`
  - optional `baseRef`
- optional `links[]`
  - `fromExternalTaskKey`
  - `toExternalTaskKey`
- optional `startTaskExternalKeys[]`

Response shape:

- `version`
- `ok`
- `applied`
- `taskMappings[]`
- `linkResults[]`
- `startResults[]`
- optional `error`

## Known Kanban Constraints

- Import is workspace-scoped, not global.
- Identity is by `externalTaskKey`.
- Replay compatibility compares more than `externalTaskKey`; imported task fields must remain compatible or Kanban fails closed.
- Import can be `applied: true` while `ok: false` if optional task start fails after the graph has already been committed.
- Replay is idempotent only when Prompt Forge preserves stable external keys.
- Ambiguity fails closed.
- This is not a full board-state replace API.
- Local validation must use live Kanban behavior, not only mocked expectations.

Known fail-closed import error codes:

- `duplicate_task_key`
- `conflicting_task_intent`
- `missing_link_task`
- `invalid_link`
- `invalid_start_task`

## Prompt Forge Brownfield Facts

Existing strong seams already present:

- backend contract source:
  - `promptforge_services/models.py`
- deterministic compile surface:
  - `promptforge_services/api.py`
  - `/preprocess`
  - `/validate`
  - `/render`
  - `/prepare-delivery`
- operator/control mutations:
  - `promptforge_services/console_api.py`
  - `/prompts/{id}/clone`
  - `/prompts/{id}/force-review`
  - `/deliveries/{id}/retry`
  - `/deliveries/{id}/reroute`
  - `/targets/{id}/dispatch`

Important current limitation:

- Prompt Forge has no Kanban-specific export or delivery target today.
- `AgentTaskV1` is the closest existing canonical payload, but it is not the same contract as Kanban import `v1`.
- `prompt_generation.id` is a stable artifact boundary already exposed through console queries and records.
- cloning a prompt generation creates a new `prompt_generation.id`, which is suitable for "new logical artifact" semantics.

## Planning Implication

Minimal v1 harness should:

1. derive a Kanban import manifest from existing Prompt Forge canonical data
2. submit that manifest to local Kanban through one narrow adapter
3. verify realized state against live Kanban response and workspace state

Minimal v1 harness should not:

- broaden Prompt Forge into a generic workflow engine
- assume production-safe remote Kanban connectivity
- add Kanban-specific logic into unrelated delivery paths
- rely on CLI scraping as primary path if direct HTTP/tRPC path is available

## Planning Corrections Locked

- v1 source identity is `prompt_generation.id`.
- Workspace identity must be explicit in v1. "local Kanban target" is not enough.
- v1 workspace binding source is Prompt Forge project-scoped runtime settings: `kanbanBaseUrl` + `kanbanWorkspaceId`.
- v1 does not auto-create Kanban workspaces.
- Manifest preview must come from backend-owned derivation, not client-side reconstruction.
- Import validation and start validation must be treated as separate concerns.
