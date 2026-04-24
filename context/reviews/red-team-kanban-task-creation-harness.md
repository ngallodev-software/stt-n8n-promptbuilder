# Red Team Review: Kanban Task Creation Harness

## Executive Verdict

The plan is directionally correct, but it is not yet safe to build against. The largest gaps are identity, field coverage, and partial-success handling. As written, the harness can still fail closed on harmless source edits, silently omit contract fields that Kanban uses for replay compatibility, and blur the difference between "import applied" and "task start succeeded."

## Findings

### High: Source identity and `externalTaskKey` strategy are not locked down enough

The spec says Prompt Forge should define one stable `externalTaskKey` rule, but it does not pin the canonical source artifact or version boundary that key comes from. That is a problem because Kanban import replay is strict: existing tasks are only considered compatible when every imported field matches, not just the external key. See the Kanban import schema and replay check in [`/lump/apps/kanban/src/core/api-contract.ts`](/lump/apps/kanban/src/core/api-contract.ts#L309) and [`/lump/apps/kanban/src/trpc/workspace-api.ts`](/lump/apps/kanban/src/trpc/workspace-api.ts#L656).

Risk:
- Any key derived from mutable rendered text, title, or review-state fields will break replay on routine Prompt Forge edits.
- The plan currently leaves `source artifact choice` open, which means two builders could pick different identity boundaries and both still think they are compliant.

Suggested change:
- Define one immutable source boundary for v1, such as prompt generation id plus revision, intake bundle id plus revision, or a content-addressed artifact hash.
- Derive `externalTaskKey` from that immutable boundary, not from rendered prompt text or mutable UI state.
- Persist the apply record with both the source artifact reference and the returned Kanban mappings.

### High: The manifest mapping is incomplete relative to the real Kanban contract

The docs only require mapping for prompt text, title, baseRef, links, and start keys. The actual Kanban import contract also carries `startInPlanMode`, `autoReviewEnabled`, `autoReviewMode`, `images`, `agentId`, and `clineSettings`. Those fields are part of the imported task schema in [`/lump/apps/kanban/src/core/api-contract.ts`](/lump/apps/kanban/src/core/api-contract.ts#L309), and the replay compatibility check compares them all in [`/lump/apps/kanban/src/trpc/workspace-api.ts`](/lump/apps/kanban/src/trpc/workspace-api.ts#L656).

Risk:
- If Prompt Forge omits any of those fields without an explicit failure rule, replay will fail closed later as `conflicting_task_intent`.
- The plan currently allows "one deterministic mapping layer" without stating whether unsupported fields are rejected or normalized.

Suggested change:
- Expand the mapping spec to cover every import field, even if the answer is "unsupported and must fail before apply."
- Make unsupported fields an explicit preflight error, not a silent drop.
- Add test cases for every field that Kanban compares during compatibility checks.

### High: Validation ignores partial-success semantics on start

Kanban import does not behave like an all-or-nothing transaction once `startTaskExternalKeys` is used. The response can come back with `applied: true` while `ok: false` if task start later fails, and `startResults` can contain per-task failures even after the import itself has already been committed. See the start path in [`/lump/apps/kanban/src/trpc/workspace-api.ts`](/lump/apps/kanban/src/trpc/workspace-api.ts#L818).

Risk:
- The plan currently treats failure as a single harness-level apply failure, which hides the distinction between import failure and start failure.
- If start behavior is included in the first validation gate, tests may become flaky because they depend on live session managers and runtime task state, not just the import contract.

Suggested change:
- Split validation into two phases: pure import/replay, then optional start behavior.
- Treat start failures as partial success with a separate status, not as proof that the import itself failed.
- Record the full import response, including `applied`, `ok`, and all `startResults`, in the apply log.

### Medium: The local target workspace binding is underspecified

Kanban import is workspace-scoped. The CLI wrapper does not magically provide a global target; it resolves a workspace, ensures runtime workspace state, and then calls `workspace.importTasks` with an `x-kanban-workspace-id` header. See [`/lump/apps/kanban/src/commands/task.ts`](/lump/apps/kanban/src/commands/task.ts#L762) and the tRPC client setup in the same file.

Risk:
- "One local Kanban runtime target" is not enough unless the plan also defines which workspace that target is.
- Without a stable workspace identity, replay tests can drift across new workspaces or new runtime instances, making idempotency claims meaningless.

Suggested change:
- Define one workspace binding for v1, including how it is created, re-used, and identified.
- Require the harness to target a fixed local workspace path or explicit workspace id.
- Make accidental auto-creation an explicit decision, not an implicit side effect.

### Medium: The UI plan can drift unless preview is backend-owned and source-bound

The console plan allows previewing raw manifest JSON or a summary, but it does not require the preview payload to come from the backend service layer. It also recommends `Prompts.tsx` as the default entry point, while `IntakeDetail.tsx` is the stronger lineage boundary. See [`/lump/apps/prompt-forge-console/context/kits/cavekit-kanban-task-creation-harness-ui.md`](/lump/apps/prompt-forge-console/context/kits/cavekit-kanban-task-creation-harness-ui.md#L22) and [`/lump/apps/prompt-forge-console/context/plans/plan-kanban-task-creation-harness-ui.md`](/lump/apps/prompt-forge-console/context/plans/plan-kanban-task-creation-harness-ui.md#L16).

Risk:
- A prompt detail surface can be context-rich, but it is not necessarily the canonical source artifact.
- If preview is assembled in the client instead of returned from a backend preview call, the UI can drift from the actual apply path.

Suggested change:
- Make preview a backend-returned artifact with an explicit source reference and source revision.
- Prefer the lineage-rich surface for the first cut, or require the UI to show the exact source artifact id/revision before apply.
- Do not let the page reconstruct Kanban mapping rules.

### Low: The plan is missing explicit coverage for import failure codes

Kanban import has specific fail-closed error modes: `duplicate_task_key`, `conflicting_task_intent`, `missing_link_task`, `invalid_link`, and `invalid_start_task`. Those are the cases most likely to catch harness bugs early, but the plan only says "failure or ambiguity" in general.

Risk:
- A happy-path-only integration can pass while still missing the cases that actually prove the harness is safe.

Suggested change:
- Add explicit tests for each import error code.
- Validate that failure payloads are preserved without lossy translation.
- Include at least one replay case, one link-missing case, and one compatibility conflict case in the live validation plan.

## Residual Risks After Fixes

- The harness will still be coupled to live Kanban runtime state, so environment drift can break integration tests even when the manifest logic is correct.
- Start behavior will remain the most brittle path because it depends on task state, session services, and runtime execution services outside the pure import contract.
- If Prompt Forge source records are frequently edited after initial creation, the team will need a clear policy for when a changed source should create a new Kanban identity versus intentionally replaying an existing one.

## Bottom Line

This is a workable local integration plan, but only if identity, field mapping, and partial-success semantics are tightened before implementation. Without those changes, the harness will look deterministic in docs and still fail on realistic replay and evolution cases.
