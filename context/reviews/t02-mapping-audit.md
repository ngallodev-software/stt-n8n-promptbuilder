# T-02 Mapping Audit

## Findings

1. **High: the spec maps `tasks[0].title` to a non-existent source identity rule.**
   - The spec says the Kanban title is derived from `prompt_generation.id + prompt_type` and must not use rendered text as identity.
   - In the live Kanban contract, `title` is optional and replay compatibility normalizes it with `resolveTaskTitle(title, prompt)`; if omitted, it falls back to prompt-derived text, not `prompt_generation.id` or `prompt_type`.
   - I did not find any Kanban-side field or helper that can consume `prompt_generation.id` directly. The proposed title mapping is therefore not grounded in the actual import contract.

2. **High: the spec incorrectly treats several Kanban import fields as unsupported.**
   - The spec says `startInPlanMode`, `autoReviewEnabled`, `autoReviewMode`, `images`, `agentId`, `clineSettings`, and `baseRef` should be omitted and fail preflight if requested.
   - The live Kanban import schema explicitly accepts all of those fields, and `workspace.importTasks` passes them through into `addTaskToColumn`.
   - That means the spec’s “unsupported field” and fail-closed rules are not aligned with the current code; they would reject valid import payloads.

3. **Medium: the spec’s source-status gate and runtime binding claims are not implemented in the referenced code.**
   - The spec allows only `rendered` prompt generations, but `PromptGenerationStatus` in Prompt Forge still includes `created`, `preprocessed`, `transforming`, `structured_validating`, `rendered`, and `failed`, and I found no import-time gate here enforcing the narrower rule.
   - The spec also requires project runtime settings keys `kanbanBaseUrl` and `kanbanWorkspaceId`, but `ConsoleRuntimeSettings` does not define those fields.
   - If these are intended future additions, they need explicit implementation and tests; as written, they are aspirational, not grounded in the current model.

## Residual Risks

- The import error codes in the spec do match the live Kanban codes (`duplicate_task_key`, `conflicting_task_intent`, `missing_link_task`, `invalid_link`, `invalid_start_task`), so the failure-name layer is consistent.
- `startTaskExternalKeys` currently produces no `startResults` during the import mutation itself; start handling is a separate post-import phase. The spec should keep that distinction explicit.
