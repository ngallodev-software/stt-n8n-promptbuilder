# T-04 Builder Sketch

## Goal

Pure backend manifest derivation for the Kanban harness.

## Scope

- input: one `PromptGenerationRecord`
- output: one Kanban import `v1` manifest plus preflight diagnostics
- no network I/O
- no Kanban client calls
- no settings mutation

## Module Shape

Suggested package: `promptforge_services/kanban_manifest_builder.py`

### Public surface

- `build_kanban_import_manifest(source: PromptGenerationRecord, binding: KanbanWorkspaceBinding) -> KanbanImportBuildResult`
- `derive_external_task_key(prompt_generation_id: str) -> str`
- `validate_kanban_binding(binding: KanbanWorkspaceBinding) -> list[KanbanManifestPreflightError]`

### Core data types

- `KanbanWorkspaceBinding`
  - `kanban_base_url: str`
  - `kanban_workspace_id: str`
- `KanbanImportBuildResult`
  - `ok: bool`
  - `manifest: KanbanImportManifest | None`
  - `errors: list[KanbanManifestPreflightError]`
- `KanbanImportManifest`
  - `version: "v1"`
  - `tasks: list[KanbanImportTask]`
  - `startTaskExternalKeys: list[str] | None`
- `KanbanImportTask`
  - `externalTaskKey: str`
  - `prompt: str`
  - `title: str | None` is intentionally omitted in v1 first cut
  - optional Kanban fields omitted in v1 first cut unless a PF source exists
- `KanbanManifestPreflightError`
  - `code: str`
  - `message: str`
  - `field: str | None`

## Data Boundaries

### Source boundary

- one `prompt_generation.id` maps to one Kanban task in v1
- `externalTaskKey` must be derived only from immutable source identity
- do not derive keys from rendered prompt text, title text, or UI state

### Manifest boundary

- builder returns plain data only
- caller owns persistence, transport, and retry
- builder must never infer extra Kanban fields from absent Prompt Forge data

## Mapping Rules

- `version` -> constant `v1`
- `tasks[0].externalTaskKey` -> `pf:pg:<prompt_generation.id>`
- `tasks[0].prompt` -> `prompt_generation.final_prompt_markdown.trim()`
- `tasks[0].title` -> omitted in v1 first cut
- `tasks[0].startInPlanMode` -> omitted in v1 first cut
- `tasks[0].autoReviewEnabled` -> omitted in v1 first cut
- `tasks[0].autoReviewMode` -> omitted in v1 first cut
- `tasks[0].images` -> omitted in v1 first cut
- `tasks[0].agentId` -> omitted in v1 first cut
- `tasks[0].clineSettings` -> omitted in v1 first cut
- `tasks[0].baseRef` -> omitted in v1 first cut
- `links` -> omitted / empty in v1
- `startTaskExternalKeys` -> omitted unless explicit harness option is added later

## Preflight Errors

Builder should fail closed before any transport path can run.

Required checks:

- missing `prompt_generation` -> `prompt_generation_not_found`
- empty trimmed `final_prompt_markdown` -> `kanban_manifest_missing_prompt`
- missing `kanbanBaseUrl` -> `kanban_binding_missing_base_url`
- missing `kanbanWorkspaceId` -> `kanban_binding_missing_workspace_id`

Optional future checks:

- source status gate once T-03 or later locks it down
- explicit unsupported-field errors only for fields the builder is actually asked to source

## Test Cases

### Determinism

- same `prompt_generation.id` yields same `externalTaskKey`
- same source record yields byte-stable manifest payload
- replay with unchanged source and binding yields identical output

### Mapping

- prompt body is trimmed, preserved, and placed in `tasks[0].prompt`
- title is absent in v1 first cut
- no optional Kanban fields appear without a real Prompt Forge source
- one source record produces exactly one task

### Preflight

- empty prompt fails closed
- missing workspace binding fields fail closed
- unknown or unsupported source-backed field requests do not get mislabeled as Kanban unsupported; they are simply omitted in v1 first cut

### Regression

- `derive_external_task_key()` does not depend on rendered prompt text
- builder does not mutate input objects
- builder does not read settings beyond the explicit binding object

## Notes

- `ConsoleRuntimeSettings` does not yet carry `kanbanBaseUrl` and `kanbanWorkspaceId`; keep this sketch aligned with T-03 as a prerequisite.
- v1 should stay one prompt generation to one Kanban task. Multi-task fanout belongs in a later ticket.
