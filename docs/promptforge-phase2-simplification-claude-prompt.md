# PromptForge Phase 2 Simplification Prompt For Claude

Use the following prompt as-is with Claude.

```text
You are planning PromptForge phase 2 as a simplification, cleanup, and focus pass, not a feature expansion pass.

Read these two documents fully before doing anything else:
1. ./docs/promptforge-multi-agent-red-team-review.md
2. ./docs/promptforge-phase2-simplification-brief.md

Treat the simplification brief as the current decision-locked source of truth.
Treat the red-team review as the critique and problem inventory that phase 2 must resolve.

Your job:
- use Cavekit design/planning skills to produce a compact but rigorous planning package for phase 2
- design the simplified target architecture
- define what gets deleted, what gets merged, what gets deferred, and what gets made stricter
- define concrete implementation sequencing
- define acceptance criteria that make the simplification work testable and enforceable
- create implementation tracking artifacts so execution can proceed cleanly

Operating rules:
- optimize for architectural truth, reduced complexity, and operational clarity
- do not preserve future-proofing theater, fake modularity, or broad control-plane scope
- do not treat existing docs, routes, tables, or modules as sacred
- prefer deletion where safe
- prefer narrowing over adding
- prefer explicit boundaries over flexible language
- if implementation reality exposes a spec gap, revise the Cavekit artifacts first
- if delegated work exposes a weakness in codex-job, create a concrete follow-up plan in invoke-codex-from-claude for codex-job to implement later

Execution method requirements:
- use Cavekit intentionally, not cosmetically
- use cavekit-writing discipline for implementation-agnostic requirements
- use validation-first discipline for acceptance criteria
- use impl-tracking documents as living records
- use revision when implementation or review exposes upstream gaps
- actively delegate bounded implementation-ready packets using codex-job where appropriate
- use Haiku-tier delegation for small bounded inventory/classification packets
- use Codex medium-tier delegation for implementation packets with explicit write sets and acceptance criteria
- keep Claude responsible for orchestration, spec writing, boundary decisions, revision, and synthesis

What to produce:

1. A simplified architecture definition
- what PromptForge is
- what PromptForge is not
- canonical workflow owner
- canonical system of record
- phase-2 product boundary

2. A compact Cavekit set for phase 2
- domain kits with numbered requirements
- explicit scope and out-of-scope statements
- cross-references where needed
- testable acceptance criteria

3. A concrete implementation plan
- task breakdown
- sequencing
- dependencies
- write-set-aware work packets
- delete vs defer vs rewrite decisions

4. Implementation tracking artifacts
- active task tracking
- dead ends and failed approaches
- validation status
- open issues

5. A deletion and simplification inventory
- routes to remove
- schema/tables to delete or defer
- modules/flows to collapse
- docs that must be rewritten because they are misleading

6. A data-model simplification plan
- append-only delivery attempts
- latest-state projection
- minimum viable lineage
- removal/deferment of future-facing schema baggage

7. A console simplification plan
- queue/review
- delivery operations
- runtime settings
- compact embedded failure visibility

8. An intake and writeback contract
- strict note shape
- parse failure behavior
- queue semantics
- archive behavior
- explicit writeback behavior

9. A lightweight ops baseline plan
- localhost-only defaults
- startup/runbook docs
- backup/restore
- restore verification
- minimal operational visibility

10. Delegation-ready implementation packets
- specific packets suitable for codex-job
- recommended model tier/provider for each packet
- acceptance criteria for each packet
- clear ownership boundaries

Important constraints:
- PromptForge is single-user only in phase 2
- remove auth/role concepts from frontend and backend
- Postgres is sole canonical truth
- Obsidian is intake/output surface only
- n8n is optional reactive outbound sidecar only
- no auto-delivery path exists in phase 2
- queue_only means compile and persist, then wait for operator dispatch
- keep only queue_only, obsidian_note writeback, and optional webhook/n8n sidecar targets
- cut/defer tmux live-session delivery
- writeback happens only after operator approval/dispatch
- move unchanged original notes into archive/processed
- write generated output as separate file
- require strict ## Control and ## Transcript sections
- fail fast on malformed or missing structure
- LLM remains explicit manual opt-in only, never part of default processing
- console scope is narrow and must not regrow into a broad admin surface
- keep only actionable failures and a small recent-event feed
- local-only runtime posture must be documented honestly as not safe for network exposure

Definition of success:
- PromptForge becomes smaller, truer, and easier to operate
- architecture docs match runtime truth
- Python is sole workflow owner
- delivery history is append-only and trustworthy
- queue/review becomes center of operator control
- dead code and dead schema are actually removed where safe
- implementation can proceed through small, validated, delegation-ready packets

Start by producing:
1. a short blunt summary of the simplified target system
2. the proposed Cavekit breakdown
3. the phase-2 implementation plan
4. the first implementation tracking document

Then continue into the full planning package.
```
