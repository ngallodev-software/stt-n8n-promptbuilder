# PromptForge Phase 2 Simplification Brief

This document is a compact, decision-locked brief for planning and executing a phase-2 simplification, cleanup, and focusing pass on PromptForge.

It is intended to be used as a prompt/context artifact for Claude using Cavekit design/planning skills.

Primary reference:
- [docs/promptforge-multi-agent-red-team-review.md](/lump/apps/prompt-forge/docs/promptforge-multi-agent-red-team-review.md:1)

## Purpose

Phase 2 is not an expansion phase.

It is a reduction phase.

The goal is to remove architectural drag, tighten workflow ownership, simplify the product surface, eliminate fake future-proofing, and make PromptForge coherent around its actual job.

This phase should aggressively prefer deletion, collapse, narrowing, and hardening over feature growth.

## Final Product Framing

PromptForge is a local-first deterministic prompt compiler/router with a small operator console and optional outbound automation adapters.

## Core Phase-2 Intent

Phase 2 should:
- simplify the architecture around the real runtime path
- eliminate multi-user and auth-role baggage
- make Python the sole workflow owner
- make Postgres the sole canonical truth
- make delivery history append-only and trustworthy
- shrink the console to a minimal operator surface
- remove unsupported or misleading product surface
- tighten the intake contract for determinism
- preserve useful local-first behavior without pretending local-first is a security model

Phase 2 should not:
- expand PromptForge into a platform
- add new orchestration layers
- broaden the control plane
- add new target types
- deepen LLM dependence
- preserve weak subsystems just because code or docs already exist

## Decision-Locked Constraints

### 1. Single-user only

PromptForge is a single-user application.

Implications:
- eliminate multi-user concepts from frontend and backend
- remove auth and role concepts from product architecture
- remove role-header behavior entirely
- remove ghost traces of future multi-user auth if they are not required for a strictly local single-user runtime

### 2. Local-only runtime posture

Phase 2 assumes strict local-only operation.

Required posture:
- bind to localhost by default
- no role headers
- no remote exposure story
- clearly document that the application is not safe for network exposure
- fail loudly if configured for broader exposure unless explicitly overridden

This is not real security.
It is a constrained operating assumption.
The system should describe it honestly.

### 3. Workflow ownership

Python owns:
- intake
- parsing
- deterministic processing
- validation
- prompt generation
- delivery state transitions
- retry semantics
- canonical persistence

n8n does not own:
- workflow
- queue semantics
- retries
- canonical state

n8n may survive only as an optional outbound automation sidecar reacting to canonical events.

### 4. Canonical truth

Postgres is the sole canonical system of record.

Obsidian is intake and output surface only.

Do not describe the vault as immutable canonical history.

### 5. Delivery model

Adopt append-only delivery attempts as the source of delivery history.

Rules:
- do not mutate prior attempts in place
- current/latest state may be projected for operator convenience
- attempt history must be explicitly drillable
- retry and reroute must create new attempts or equivalent append-only records

### 6. Queue/review semantics

`queue_only` means:
- compile
- persist
- do not auto-deliver
- wait for explicit operator dispatch

For phase 2:
- leave no auto-delivery path for any target

### 7. Phase-2 delivery targets

Keep:
- `queue_only`
- `obsidian_note` writeback
- optional `webhook` / `n8n` outbound sidecar target

Cut or defer:
- tmux live session delivery
- broader live session/runtime target matrix

### 8. Writeback semantics

Writeback is a delivery action, not an automatic post-compile side effect.

Rules:
- writeback happens only after operator approval/dispatch from queue
- move unchanged original source note into archive/processed
- write rendered/generated output as a separate file
- do not rewrite the original source note with metadata

### 9. Intake contract

Phase 2 should require strict note structure and reject heuristic fallback behavior.

Required sections:
- `## Control`
- `## Transcript`

Rules:
- fail fast if required structure is absent
- fail fast if required structure is malformed
- optimize for determinism, not rescue heuristics

### 10. LLM policy

LLM features are allowed only as explicit manual/operator opt-in.

Rules:
- no automatic LLM invocation in default processing
- no implication that LLM is part of the core path
- default processing remains deterministic-only

### 11. Console scope

Phase-2 console is limited to:
- queue/review
- delivery operations
- runtime settings
- compact embedded failure/log visibility needed to operate the system

Do not expand phase-2 console into a broad admin/control plane.

### 12. Failure/log visibility

Keep only:
- actionable failures tied to queue items and deliveries
- a small recent-event feed

Do not build:
- broad observability UI
- large admin diagnostics surface

### 13. Recovery baseline

Minimum acceptable phase-2 ops story:
- documented backup/restore for Postgres and vault
- basic failure log visibility
- startup/runbook docs
- simple restore verification checklist

Do not introduce a fancy observability stack for phase 2.

### 14. Simplification aggressiveness

Plan for actual deletion where safe.

Preferred order:
1. delete dead routes, dead tables, dead code, and dead docs where migration risk is low
2. collapse duplicated or misleading boundaries
3. defer or hide only where migration risk is real

Do not preserve architectural baggage by default.

## Main Problems Phase 2 Must Fix

Phase 2 planning should directly address these weaknesses from the red-team review:

1. Workflow ownership confusion
Python and n8n have been described inconsistently. Planning must make Python the sole owner and demote n8n to reactive sidecar status only.

2. Console bloat
The console grew into an admin kitchen sink. Planning must cut it back to a minimal operator surface.

3. Fake append-only delivery history
Current lifecycle behavior and documented lineage expectations are misaligned. Planning must make delivery history truthful.

4. Overbuilt future-facing schema and routes
Schema and route surface carry multi-user, admin, session, and other future-facing baggage. Planning must remove or defer aggressively.

5. Unsafe or ambiguous delivery surface
Live-session delivery is too dangerous and too ambiguous for phase 2. Planning must remove it from active phase-2 scope.

6. Heuristic intake behavior
PromptForge currently risks clever fallback behavior where determinism is needed. Planning must make note grammar strict.

7. Destructive/unclear source-note handling
Planning must separate canonical persistence from intake/output behavior and preserve original notes in archive form.

8. Dishonest local-first framing
Planning must describe local-only assumptions honestly without pretending local-first solves trust, auth, or network safety.

## Planning Directives For Claude

Use the red-team review and the decisions above to produce a phase-2 simplification plan that is concrete, scoped, and execution-ready.

The plan should:
- prefer truth over preservation of current design language
- identify what gets deleted, what gets merged, what gets deferred, and what gets tightened
- remove platform-thinking where the product has not earned it
- define boundaries in terms of ownership, not just directories or modules
- explicitly forbid subsystems or behaviors that phase 2 should not carry forward

Do not optimize for keeping existing documents or subsystems alive.
Optimize for a smaller, truer, more operable system.

## Expected Planning Outputs

Claude should produce a compact but rigorous planning package that includes:

### 1. Simplified architecture definition

A clear statement of:
- what PromptForge is
- what it is not
- who owns workflow
- what systems are canonical vs peripheral

### 2. Boundary decisions

Explicit ownership for:
- watcher/runtime entrypoints
- core compiler logic
- delivery state machine
- console responsibilities
- webhook/n8n sidecar behavior

### 3. Deletion and deferral plan

A concrete list of:
- routes to delete
- tables to delete or defer
- modules or flows to collapse
- features to cut from phase 2
- docs that must be rewritten because they are misleading

### 4. Data model simplification plan

A concrete proposal for:
- append-only delivery attempts
- latest-state projection
- minimum viable lineage
- removal/deferment of future-facing schema baggage

### 5. Console simplification plan

A compact plan for:
- queue/review
- delivery operations
- runtime settings
- embedded failure visibility

This should explicitly reject broad admin/control-plane sprawl.

### 6. Intake and writeback contract

A strict definition of:
- required note structure
- parse failure behavior
- queue behavior
- archive behavior
- writeback behavior

### 7. Ops baseline plan

A lightweight but explicit plan for:
- localhost-only defaults
- startup/runbook documentation
- backup/restore
- restore verification
- minimal operational visibility

### 8. Execution sequencing

A recommended implementation order for simplification work, prioritizing:
- highest leverage
- lowest ambiguity
- reduction of future migration pain

## Cavekit-Oriented Guidance

When converting this brief into Cavekit design/planning artifacts:
- write specs around behaviors and boundaries, not implementation nostalgia
- define what must be true in testable terms
- mark out-of-scope items aggressively
- avoid preserving current fake modularity
- create explicit acceptance criteria for deletion, narrowing, and hardening work

Useful Cavekit framing:
- WHAT must survive
- WHAT must be removed
- WHAT must be stricter
- WHAT must be deferred
- HOW phase 2 proves the system is simpler and more coherent than phase 1

## Explicit Cavekit Workflow Instructions

Claude should use Cavekit as an end-to-end operating method, not as a vague planning style.

Recommended Cavekit skills and roles for this phase:
- `ck:methodology` for phase structure and gate discipline
- `ck:cavekit-writing` for implementation-agnostic simplification kits
- `ck:validation-first` for acceptance criteria and completion gates
- `ck:impl-tracking` for living implementation tracking documents
- `ck:revision` whenever implementation or review exposes a spec/design gap
- `ck:peer-review` and `ck:peer-review-loop` for adversarial review at planning and implementation checkpoints

Claude should treat this work as a lightweight-to-full Cavekit effort with explicit stage outputs:

### Stage 1: Draft the simplification kits

Claude should create a compact Cavekit set for phase 2 under a repo-local context structure, for example:
- `context/kits/cavekit-overview.md`
- `context/kits/cavekit-architecture-simplification.md`
- `context/kits/cavekit-data-model-simplification.md`
- `context/kits/cavekit-console-simplification.md`
- `context/kits/cavekit-intake-writeback.md`
- `context/kits/cavekit-ops-local-runtime.md`

Each kit must:
- define scope and boundaries
- include numbered requirements
- include testable acceptance criteria
- include explicit out-of-scope statements
- cross-reference related kits where needed

This phase should bias toward fewer kits with sharper boundaries, not over-decomposition.

### Stage 2: Produce implementation plans

Claude should translate the kits into concrete implementation plans under a repo-local plan area, for example:
- `context/plans/plan-phase2-simplification.md`
- `context/plans/plan-schema-cleanup.md`
- `context/plans/plan-console-reduction.md`
- `context/plans/plan-delivery-attempt-ledger.md`

Plans should:
- map each task to specific Cavekit requirements
- define ownership boundaries and write sets
- define sequencing and dependencies
- identify delete vs defer vs rewrite work explicitly
- include verification commands and pass conditions

### Stage 3: Track implementation continuously

Claude should create and maintain implementation tracking documents using `ck:impl-tracking`, for example:
- `context/impl/impl-phase2-simplification.md`
- `context/impl/impl-schema-cleanup.md`

Tracking documents must be updated throughout execution with:
- task status
- files created/modified/deleted
- validation outcomes
- dead ends and failed approaches
- open issues
- follow-up work

Dead ends are mandatory. If a simplification attempt fails, the failure and root cause must be recorded so the next iteration does not repeat it.

### Stage 4: Revise specs when reality disagrees

If implementation, peer review, or delegated work exposes:
- missing requirements
- contradictory constraints
- invalid assumptions
- hidden migration risk
- missing validation criteria

Claude must use `ck:revision` logic:
- update the relevant Cavekit kit first
- update plans second
- only then continue implementation

Do not patch around spec gaps in code without fixing the upstream Cavekit artifacts.

### Stage 5: Use peer review intentionally

Claude should use `ck:peer-review` or `ck:peer-review-loop` at these checkpoints:
- after first draft of simplification kits
- after architecture/boundary plan is written
- after major implementation waves
- before declaring phase-2 planning or execution complete

Peer review should specifically attack:
- preserved complexity
- fake modularity
- unowned boundaries
- incomplete deletion plans
- weak acceptance criteria
- hidden migration pain

## Explicit Delegation Instructions Using `codex-job`

Claude should actively look for work packets that are implementation-ready and delegate them using the installed user-level skill:
- skill doc: [/home/nate/.claude/skills/codex-job/SKILL.md](/home/nate/.claude/skills/codex-job/SKILL.md:1)
- runtime scripts: [/home/nate/.claude/skills/codex-job/scripts](/home/nate/.claude/skills/codex-job/scripts:1)
- source repo for the skill/runtime: [/lump/apps/invoke-codex-from-claude](/lump/apps/invoke-codex-from-claude:1)

Delegation should happen only after:
- requirements are clear
- acceptance criteria are clear
- write set is bounded
- validation strategy is explicit

Do not delegate unresolved architecture.
Do not delegate vague cleanup.
Do delegate well-scoped implementation packets.

### Delegation model policy

Use Claude for:
- orchestration
- kit writing
- boundary decisions
- plan generation
- revision
- final synthesis

Use Haiku via `codex-job` for:
- fast bounded drafting or inventory tasks
- small deterministic cleanup packets
- migration inventory and delete-list preparation
- compact refactors with low ambiguity

Use Codex via `codex-job` for:
- implementation packets with multiple coordinated file changes
- schema/data-model changes with explicit acceptance criteria
- route consolidation and deletion work
- delivery-attempt model implementation
- validation and hardening passes against already-decided designs

### Recommended delegation mapping

Recommended mappings based on the installed `codex-job` model registry:
- Haiku path: `--provider anthropic --tier low` -> `claude-haiku-4-5`
- Default Codex path: `--provider openai --tier medium` -> `gpt-5.4-mini`
- Higher-complexity Codex path: `--provider openai --tier high` -> `gpt-5.3-codex` or `gpt-5.4`

High-tier Codex use should be reserved for tasks that cannot be cleanly split further.

### Example: delegate a small Haiku inventory packet

Example command shape:

```text
/codex-job --repo /lump/apps/prompt-forge --provider anthropic --tier low --task "
Task: inventory and classify all frontend/backend auth-role remnants for deletion.

Scope:
- promptforge_services/
- tests/
- docs/

Deliverables:
- list every role/auth header codepath
- identify exact files/functions/routes affected
- propose delete vs rewrite classification
- do not implement changes

Acceptance criteria:
- inventory covers backend, tests, and docs
- every finding includes file path and why it exists
- output distinguishes safe-delete from migration-risk items
- no files modified
"
```

Use this pattern for inventory, classification, and bounded analysis packets.

### Example: delegate a medium Codex implementation packet

```text
/codex-job --repo /lump/apps/prompt-forge --provider openai --tier medium --task "
Task: implement append-only delivery attempts and remove in-place retry mutation.

Write set:
- promptforge_services/
- tests/
- docs/

Required context:
- Postgres remains canonical truth
- retry/reroute must append new attempts, not mutate prior attempts
- UI may still present latest-state projection separately

Acceptance criteria:
- retry creates a new append-only attempt record
- prior attempts remain unchanged
- tests cover retry and reroute behavior
- docs updated to match runtime truth
- no live-session code introduced
"
```

Use this pattern for implementation packets with explicit write sets and acceptance criteria.

### Example: delegate a Codex hardening packet

```text
/codex-job --repo /lump/apps/prompt-forge --provider openai --tier medium --task "
Task: remove role-header behavior and enforce strict single-user local-only runtime defaults.

Write set:
- promptforge_services/
- promptforge_watcher/
- tests/
- docs/

Acceptance criteria:
- no role-header auth path remains
- localhost/default local-only behavior documented and enforced
- docs clearly state not safe for network exposure
- tests cover local-only defaults where practical
"
```

## Delegation Tracking And Feedback Rules

Every delegated run should feed back into the repo-local Cavekit workflow.

Claude should:
- capture the delegated task purpose in implementation tracking
- record model/provider/tier used
- record result status
- record validation outcome
- record dead ends or surprises

If delegated work succeeds:
- merge the result into the active plan/tracking docs
- update task status
- update remaining work

If delegated work fails:
- classify the failure as environmental, spec, or execution
- record the failure in the implementation tracking doc
- either narrow/resume the task or revise the upstream kit/plan

Do not silently retry the same bad prompt.
Failure must produce a recorded learning artifact.

## Mandatory Rule: `codex-job` Weaknesses Become Planned Source-Repo Work

If, during PromptForge phase-2 planning or implementation, Claude discovers weaknesses in the `codex-job` skill or runtime, those weaknesses must not be left as vague notes.

They must translate into concrete planned work in the `codex-job` source repo:
- source repo: [/lump/apps/invoke-codex-from-claude](/lump/apps/invoke-codex-from-claude:1)

Examples of `codex-job` weaknesses that should trigger source-repo planning:
- poor delegation ergonomics
- weak failure classification
- missing resume guidance
- noisy or low-signal summaries
- missing metrics
- bad guardrail defaults
- missing model-selection clarity
- output that makes orchestration harder
- inability to cleanly pass acceptance criteria or write-set constraints

When this happens, Claude should:
1. record the weakness in PromptForge implementation tracking if it blocked or degraded work
2. create a concrete plan artifact in the `codex-job` source repo describing the needed fix
3. ensure the plan is implementation-ready enough for later `codex-job` execution

Suggested source-repo plan locations:
- `/lump/apps/invoke-codex-from-claude/agent-notes/`
- `/lump/apps/invoke-codex-from-claude/docs/`

Suggested artifact names:
- `agent-notes/codex-job-followup-<topic>.md`
- `docs/codex-job-hardening-plan-<topic>.md`

Each such plan should include:
- problem statement
- observed failure or weakness
- why it matters operationally
- proposed fix
- acceptance criteria
- recommended validation

This rule is important:
PromptForge simplification work should improve PromptForge, but it should also surface improvements needed in the delegation toolchain itself.
If `codex-job` is part of the execution method, its failures are not external noise. They are actionable engineering inputs.

## Example Delegation Feedback Loop

Good operating loop:
1. Claude writes or revises Cavekit kits.
2. Claude writes implementation plan and tracking doc.
3. Claude delegates a bounded packet to Haiku or Codex using `/codex-job`.
4. Claude inspects result, updates tracking, and either merges or revises.
5. If delegated work exposed a spec gap, Claude updates the relevant Cavekit kit.
6. If delegated work exposed a `codex-job` weakness, Claude creates a follow-up plan in `/lump/apps/invoke-codex-from-claude`.
7. Claude continues with a narrower, better-defined next packet.

This loop should repeat until the simplification plan and implementation converge.

## Out Of Scope For Phase 2

The following should be considered out of scope unless explicitly reintroduced by later product decision:
- multi-user support
- auth/authz role systems
- remote/network-safe deployment story
- tmux live-session delivery
- broad admin console expansion
- large observability stack
- automatic LLM execution in core workflow
- heuristic intake rescue behavior
- platform-style workflow orchestration beyond Python-owned core processing

## Definition Of Success

Phase 2 succeeds if PromptForge becomes smaller, truer, and easier to operate.

Concrete signs of success:
- architecture docs match runtime truth
- Python is sole workflow owner
- n8n is clearly optional and reactive only
- delivery history is append-only and trustworthy
- no auto-delivery exists in phase 2
- queue/review is the center of operator control
- writeback is explicit delivery, not side-effect magic
- original notes are archived unchanged
- intake grammar is strict
- console scope is narrow and coherent
- multi-user/auth baggage is gone
- dead code and dead schema are actually removed where safe

## Suggested Prompt Wrapper

Use this brief and the red-team review as the basis for a Cavekit-driven simplification planning run.

Suggested framing:

> You are planning PromptForge phase 2 as a simplification, cleanup, and focus pass, not a feature expansion pass.
> Use [docs/promptforge-multi-agent-red-team-review.md](/lump/apps/prompt-forge/docs/promptforge-multi-agent-red-team-review.md:1) and [docs/promptforge-phase2-simplification-brief.md](/lump/apps/prompt-forge/docs/promptforge-phase2-simplification-brief.md:1) as authoritative input.
> Produce a compact but rigorous Cavekit-style planning package that defines the simplified target architecture, required deletions, deferrals, hard constraints, behavioral acceptance criteria, and implementation sequencing for phase 2.
> Optimize for architectural truth, reduced complexity, and operational clarity.
> Do not preserve future-proofing theater, fake modularity, or broad control-plane scope.
