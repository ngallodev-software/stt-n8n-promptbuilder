# PromptForge Multi-Agent Red Team Review

## 1. Blunt system summary

PromptForge is a local ingestion-and-compilation system with a swollen admin surface, optional LLM garnish, and an unresolved workflow-owner problem. It keeps saying "monolith-first local tool," but the design already acts like a platform: watcher runtime, API runtime, console control plane, n8n sidecar, live-session delivery, schema-heavy lineage, and an expanding settings surface.

The core product is smaller than the architecture around it. The real system today is: Obsidian note intake -> Python watcher -> deterministic compile path -> Postgres -> optional delivery/write-back. Everything else is either support tooling, partial scaffolding, or future-proofing theater.

Selected evidence:
- Architecture narrative: [docs/promptforge-system-architecture.md](./docs/promptforge-system-architecture.md:3)
- MVP plan still treating n8n as central orchestration: [docs/planning/promptforge_mvp_master_plan.md](./docs/planning/promptforge_mvp_master_plan.md:7)
- Actual watcher-owned runtime path: [promptforge_watcher/watcher.py](./promptforge_watcher/watcher.py:90)
- Console/API surface size: `40` console routes / `3263` LOC in [console_api.py](./promptforge_services/console_api.py:1) vs `7` core API routes / `118` LOC in [api.py](./promptforge_services/api.py:1)

## 2. Independent agent findings

### Agent 1 — Systems Architect Red Teamer

Top criticisms:
- The documented boundary is false. The docs frame "backend services" as the workflow owner and `n8n` as orchestration support, but the watcher already imports pipeline code directly, builds delivery, dispatches, and writes back. This is one Python monolith with multiple entrypoints, not a clean backend/watcher split.
- The architecture keeps talking like raw note files are immutable source artifacts, but successful write-back rewrites frontmatter, moves the note, and deletes the original source file. The canonical truth is Postgres, not the vault file.
- "Monolith-first" is being used as comforting language while conceptual fragmentation is already happening: watcher runtime, API runtime, console runtime, n8n flows, tmux live sessions, and admin settings are all treated like quasi-subsystems.

Architectural risks:
- Phase 2 will build on false boundaries and make them harder to unwind.
- More delivery targets will force a redesign because current abstractions mix transport selection, queue semantics, review semantics, and runtime execution state.
- Documentation drift is already real: some docs still say live sessions are partial or unsupported, while code and tests already implement tmux-backed live dispatch.

Complexity smells:
- Boundary by directory name rather than by ownership.
- Architecture docs describing an intended system instead of the actual one.
- Optional subsystems already treated like they are mandatory architecture layers.

Hidden assumptions:
- The system can keep accreting surfaces without paying coordination cost.
- "Local-first" will continue covering for weak identity, trust, and recovery stories.
- A single user means architecture discipline does not matter yet.

Likely failure modes:
- Team optimizes the wrong boundary and creates duplicated workflow logic.
- Live delivery and admin control expand faster than core compile reliability.
- Phase 2 inherits a platform-shaped vocabulary for a still-small product.

Concrete better alternatives:
- Tell the truth: PromptForge is one Python core with watcher and API façades, Postgres as canonical state, and n8n as optional reactive automation.
- Narrow delivery into a small canonical state machine plus adapters.
- Treat Obsidian as intake and output surface, not durable canonical history.

What to remove or simplify:
- Remove n8n from the critical-path narrative unless it actually owns workflow.
- Stop describing the vault as immutable source-of-truth.
- Collapse "backend services" and "watcher" language into one runtime authority with two entrypoints.

1. What is overengineered? The conceptual service split and the n8n orchestration story.
2. What is underdesigned? Delivery semantics, recovery, and truthful state ownership.
3. What is misleadingly named or framed? "Backend services," "n8n orchestration," and "raw captured text is immutable."
4. What will become painful in phase 2 if left as-is? Delivery expansion and boundary drift.
5. What would you change first? Rewrite the architecture around the real runtime path before adding anything else.

Selected evidence:
- Claimed ownership: [docs/promptforge-system-architecture.md](./docs/promptforge-system-architecture.md:12)
- Actual watcher path: [promptforge_watcher/watcher.py](./promptforge_watcher/watcher.py:145)
- Source note mutation/delete: [promptforge_watcher/writeback.py](./promptforge_watcher/writeback.py:14)
- Live session implementation: [promptforge_services/delivery_dispatch.py](./promptforge_services/delivery_dispatch.py:376), [tests/test_delivery_dispatch_live_sessions.py](./tests/test_delivery_dispatch_live_sessions.py:32)

### Agent 2 — Backend / Workflow Red Teamer

Top criticisms:
- The watcher is brittle. Import is committed first, webhook is posted afterward, and per-note processing is not isolated from the watcher main loop. One bad webhook or dispatch failure can kill the daemon after partial success.
- Retry/reroute semantics are wrong. The docs describe append-only retry as "retry as new row," but the console mutates the same delivery row in place.
- Queue processing ownership is muddy. n8n queue logic polls Postgres and marks rows dispatching, while the watcher also dispatches directly for some targets. That is two execution models over the same lifecycle.

Architectural risks:
- Double dispatch and race conditions between console actions, watcher dispatch, and n8n queue processing.
- Delivery history that cannot be trusted because it is overwritten instead of appended.
- Operationally confusing failure states: imported in DB, note not written back, webhook not sent, watcher dead.

Complexity smells:
- One lifecycle, three control points: watcher, console, n8n.
- Queue semantics mixed with direct dispatch semantics.
- Documented state machine and implemented state machine diverging.

Hidden assumptions:
- Delivery failures are rare enough that crude recovery is acceptable.
- n8n can "help" without becoming a conflicting owner.
- In-place status edits are close enough to true attempt history.

Likely failure modes:
- A failed network call to webhook or target stops intake for all later notes.
- Retry fixes the latest visible state while destroying the historical one.
- A queue processor run races a reroute or retry and dispatches stale target data.

Concrete better alternatives:
- One workflow owner: Python.
- One delivery execution path: create attempt, claim attempt atomically, dispatch, append result.
- n8n only reacts to completed canonical events or dead-letter notifications.

What to remove or simplify:
- Remove n8n from dispatch ownership.
- Remove in-place retry/status mutation.
- Remove dual meaning of `queue_only` as both destination class and special mutability loophole.

1. What is overengineered? n8n queue orchestration for a system already dispatching in Python.
2. What is underdesigned? Failure isolation, atomic work claiming, and retry history.
3. What is misleadingly named or framed? "Append-only" delivery lifecycle.
4. What will become painful in phase 2 if left as-is? Delivery races, untrustworthy history, and brittle recovery.
5. What would you change first? Make retry/reroute append a new attempt row and keep Python as sole dispatcher.

Selected evidence:
- Watcher loop and per-note processing: [promptforge_watcher/watcher.py](./promptforge_watcher/watcher.py:71)
- Webhook after commit: [promptforge_watcher/watcher.py](./promptforge_watcher/watcher.py:97), [promptforge_watcher/webhook.py](./promptforge_watcher/webhook.py:50)
- In-place retry mutation: [promptforge_services/console_api.py](./promptforge_services/console_api.py:2599)
- n8n workflow runtime assumptions: [docs/planning/n8n_workflows/README.md](./docs/planning/n8n_workflows/README.md:27)

### Agent 3 — Frontend / Control Plane Red Teamer

Top criticisms:
- The console is not a control plane. It is an admin kitchen sink.
- The bootstrap payload is absurdly broad. It preloads projects, intake notes, utterances, transcript revisions, prompt generations, deliveries, delivery history, processing runs, llm runs, rulesets, rules, dictionary, templates, targets, logs, settings, and health in one contract.
- The permission model is dishonest. Most mutation endpoints are effectively unauthenticated, while only a subset of settings/admin paths use the admin guard.
- The UI contract is being stabilized around denormalized server-side view models instead of task-specific workflows.

Architectural risks:
- The frontend becomes permanently coupled to mega-bootstrap and giant response shapes.
- Auth retrofitting later will be painful because current route design assumes broad operator power.
- UI will expose capabilities that are still stubbed or inconsistent.

Complexity smells:
- `console_api.py` is already bigger than the core product API by an order of magnitude.
- Lineage, metrics, settings, dispatch, templates, rules, and LLM assist all share one module and one mental model.
- Safety metadata exists but is not enforced during dispatch.

Hidden assumptions:
- Single user means least privilege can wait.
- Operators need broad data dumps more than job-specific screens.
- It is okay for the backend to compose most UI state.

Likely failure modes:
- Bootstrap slows down and gets brittle as data grows.
- UI ships actions that users can click but backend only partially supports.
- Sensitive targets get dispatched because the control plane ignores `requires_confirmation` and `is_auto_dispatch_safe`.

Concrete better alternatives:
- Reduce console to three jobs: queue/review, delivery operations, settings.
- Break bootstrap into smaller task-specific queries.
- Hide unsupported actions instead of formalizing them into the control plane contract.
- Enforce safety metadata before any dispatch.

What to remove or simplify:
- Remove raw lineage detail from bootstrap.
- Defer dictionary editing and prompt cloning if they are not phase-2 critical.
- Collapse metrics into a compact operations summary.

1. What is overengineered? The bootstrap payload and route breadth.
2. What is underdesigned? Auth/authz, actor identity, and task-focused UX boundaries.
3. What is misleadingly named or framed? "Control plane" and "bootstrap."
4. What will become painful in phase 2 if left as-is? Frontend contract drift and permission retrofits.
5. What would you change first? Cut the console scope to queue/review, delivery ops, and settings.

Selected evidence:
- Bootstrap contract shape: [tests/test_console_read_endpoints.py](./tests/test_console_read_endpoints.py:66)
- Role default/admin fallback: [promptforge_services/console_api.py](./promptforge_services/console_api.py:247)
- Dispatch ignoring safety metadata: [promptforge_services/console_api.py](./promptforge_services/console_api.py:1166), [promptforge_services/console_api.py](./promptforge_services/console_api.py:1936)

### Agent 4 — Data / Lineage / Schema Red Teamer

Top criticisms:
- The schema is more elaborate than the reliably stored facts.
- "Append-only" is true for some text revisions, not for lifecycle history overall.
- Lineage is reconstructed from current table snapshots and selective projections, not backed by a dedicated immutable attempt ledger.
- The model already carries single-user MVP baggage for multi-user scope, live sessions, admin settings, secret rotation, and audit tables.

Architectural risks:
- Operators believe they have a replayable lineage chain when they mostly have current state plus timestamps.
- The data model keeps expanding to represent aspiration rather than runtime need.
- Schema complexity rises faster than operational certainty.

Complexity smells:
- `18` tables for a local-first single-user MVP, including `delivery_session_registry`, `console_runtime_settings`, `console_secret_settings`, and `console_admin_audit_log`.
- Separate concepts in docs like `parsed`, `attempts`, and `logs` are folded inconsistently into JSONB columns, projections, and mutable rows.
- Delivery session registry exists even though live-session dispatch currently resolves tmux state directly at runtime.

Hidden assumptions:
- Modeling future scope now is cheaper than adding it later.
- JSONB plus projections are "good enough" substitutes for a tighter event model.
- Mutable current-state rows will not undermine future audit expectations.

Likely failure modes:
- Phase 2 spends time reconciling schema intent with actual runtime behavior.
- Delivery history becomes analytically confusing because retry/reroute/status edits mutate current rows.
- More tables and projections appear to compensate for missing event history instead of fixing it cleanly.

Concrete better alternatives:
- Keep only the canonical compiler graph: intake note, utterance, text revisions, prompt generation, delivery attempt, workflow error.
- If append-only matters, add a real `delivery_attempts` ledger and stop pretending `deliveries` already serves that role.
- Defer session registry and broader settings schema until there is a real multi-session or multi-user problem.

What to remove or simplify:
- Defer `delivery_session_registry` unless phase 2 truly commits to live-session delivery as first-class.
- Remove lineage claims that the data model does not enforce.
- Collapse admin settings tables if runtime config remains single-operator and local-only.

1. What is overengineered? The schema's future-facing admin and live-session surface.
2. What is underdesigned? Immutable delivery history and trustworthy lineage projection.
3. What is misleadingly named or framed? "Append-only" and "attempt history."
4. What will become painful in phase 2 if left as-is? Schema drag and audit confusion.
5. What would you change first? Decide whether phase 2 wants true event history or just current state; then model only that.

Selected evidence:
- Schema table count and session registry: [docs/planning/promptforge_postgres_schema.sql](./docs/planning/promptforge_postgres_schema.sql:486)
- Mutable delivery state: [promptforge_services/console_api.py](./promptforge_services/console_api.py:2599)
- Current-state lineage projection: [promptforge_services/console_api.py](./promptforge_services/console_api.py:2141)

### Agent 5 — Security / Reliability / Ops Red Teamer

Top criticisms:
- There is no real auth boundary. Caller-supplied headers decide role, and missing role defaults to admin.
- Obsidian note delivery can write outside the vault because target folders are joined to vault path without containment checks.
- Live-session dispatch can paste arbitrary payloads into the wrong tmux pane and press `Enter`.
- n8n setup is manual and fragile. Workflows import inactive and require manual credential wiring.
- Backup/recovery and post-failure verification are barely described.

Architectural risks:
- Any network exposure immediately turns the API into an unsafe mutation surface.
- A misconfigured target row becomes arbitrary filesystem write capability.
- Live-session transport can turn prompt delivery into command execution against the wrong terminal.
- Local-first trust assumptions mask real operational fragility.

Complexity smells:
- Security language in docs is mostly future tense.
- Secrets rotation exists in schema and settings UX but is stubbed in implementation.
- Ops story depends on one human remembering manual steps.

Hidden assumptions:
- Service will stay inside a trusted LAN forever.
- Operators will never misconfigure target paths or session mappings.
- Manual bootstrap is good enough for recovery.

Likely failure modes:
- Unauthorized local client triggers destructive or expensive actions.
- Misrouted live dispatch sends text into an active shell or wrong agent session.
- Human operator cannot quickly rebuild or verify a broken stack.

Concrete better alternatives:
- Fail closed: no header, no admin.
- Require vault containment checks for every filesystem target.
- Only allow live dispatch to explicitly registered dedicated agent panes.
- Write and test backup/recovery procedures before pretending the local-first story is operationally mature.

What to remove or simplify:
- Remove the implied "safe by local-first" framing.
- Remove or disable live-session dispatch unless phase 2 is willing to harden it properly.
- Hide secrets rotation until it works.

1. What is overengineered? Partial secrets/settings UX without real auth and recovery.
2. What is underdesigned? Trust boundaries, path safety, and disaster recovery.
3. What is misleadingly named or framed? "Local trusted environment" as if that were a security model.
4. What will become painful in phase 2 if left as-is? Exposure risk, unsafe live delivery, and manual incident response.
5. What would you change first? Fail closed on auth and add vault/path safety checks immediately.

Selected evidence:
- Role header default admin: [promptforge_services/console_api.py](./promptforge_services/console_api.py:247)
- Obsidian note path write: [promptforge_services/delivery_dispatch.py](./promptforge_services/delivery_dispatch.py:502)
- tmux live dispatch: [promptforge_services/delivery_dispatch.py](./promptforge_services/delivery_dispatch.py:263)
- Manual n8n import/activation: [docs/planning/n8n_workflows/README.md](./docs/planning/n8n_workflows/README.md:24)

### Agent 6 — Simplification / Leverage Teamer

Top criticisms:
- Too many optional branches already act like first-class architecture.
- n8n is still described like a required workflow engine even though the real system can already run without it.
- The system keeps adding surfaces before locking the main loop.
- The note contract is not strict enough; parsing still has heuristic fallback behavior where phase 2 needs determinism.

Architectural risks:
- Phase 2 spends effort expanding architecture instead of tightening the compiler loop.
- Every partial subsystem survives because it already has docs, routes, and tables.
- More time goes into scaffolding than into reliable compile/delivery behavior.

Complexity smells:
- Product smaller than platform.
- Stubbed endpoints already formalized.
- Schema and console shaped for future scale instead of present leverage.

Hidden assumptions:
- Future-proofing now costs less than change later.
- Users need all target types and admin workflows soon.
- Flexibility in note parsing is worth ambiguity.

Likely failure modes:
- Architecture becomes hard to simplify because too many weak subsystems have public contracts.
- Phase 2 turns into plumbing and dashboard work instead of compiler hardening.
- Optional LLM and live-session work erode the deterministic boundary by convenience.

Concrete better alternatives:
- One deterministic compiler path.
- One delivery path with one attempt ledger.
- One small control plane.
- One strict intake note contract.
- Optional adapters only where they add immediate value.

What to remove or simplify:
- Remove n8n from the hot path.
- Collapse duplicated dispatch logic.
- Defer LLM assist to explicit opt-in only.
- Cut bootstrap down to phase-2 jobs.
- Require explicit `## Control` and `## Transcript` sections instead of heuristic fallback.

1. What is overengineered? n8n, bootstrap breadth, schema future-proofing, and multi-target admin surfaces.
2. What is underdesigned? The core deterministic loop and error recovery.
3. What is misleadingly named or framed? "Platform" language around a compiler/router.
4. What will become painful in phase 2 if left as-is? Too much architecture drag for too little product gain.
5. What would you change first? Cut the architecture back to one core compile-and-deliver loop.

Selected evidence:
- MVP plan centralizing n8n: [docs/planning/promptforge_mvp_master_plan.md](./docs/planning/promptforge_mvp_master_plan.md:7)
- Watcher already owning the hot path: [promptforge_watcher/watcher.py](./promptforge_watcher/watcher.py:145)
- Strict directive grammar recommended by docs: [docs/planning/promptforge_mvp_master_plan.md](./docs/planning/promptforge_mvp_master_plan.md:194)

## 3. Cross-agent challenges and disagreements

- The simplification team wants n8n pushed entirely out of the hot path. The backend/workflow team agrees on ownership, but the systems architect view is slightly narrower: n8n can survive as a reactive automation sidecar if it has zero claim over canonical workflow state. The disagreement is not whether n8n should own workflow. It should not. The disagreement is whether it should survive phase 2 at all.

- The data/schema team wants stronger immutable delivery history. The simplification team pushes back on building a full lineage subsystem. Both are right in different ways: PromptForge does need a real append-only delivery attempt ledger if it wants trustworthy history, but it does not need more projections, more views, or more lineage theater.

- The security/ops team wants live-session delivery either hardened or removed. The systems and leverage views are split: the feature is already partially real and clearly useful, but it is also a direct command-injection-shaped transport. Elegant on paper, dangerous in practice. If phase 2 keeps it, it must be stricter than every other target type, not looser.

- The frontend/control-plane team wants the console cut back hard. The schema team agrees on scope reduction, but warns that a smaller UI alone does not fix the current mutable-truth problem. A thin console over bad lifecycle data is still bad. UI simplification and delivery-history repair have to move together.

- The backend/workflow team wants append-only retry behavior. The control-plane team points out that blindly preserving every attempt without redesigning user flows can make operator UX worse. Tradeoff: history must be preserved in storage, but the UI should default to showing latest state plus explicit attempt drilldown, not flood the operator with internal history.

- The systems team says docs must be rewritten first because the architecture is lying to itself. The implementation-focused view challenges that ordering slightly: some safety and retry fixes are urgent enough that they should happen in parallel with doc cleanup. Best practical answer: fix the most dangerous behavior now, but stop adding new scope until the docs are honest.

## 4. Consolidated red team conclusions

Top systemic weaknesses:
- Workflow ownership is unclear in prose and duplicated in code.
- The console is much larger than the actual product core.
- The data model promises stronger lineage than the implementation enforces.
- Security posture depends on local trust, not actual controls.
- n8n is still given architectural weight it has not earned.

Top overengineering risks:
- Treating PromptForge like a platform before it has a stable compiler loop.
- Carrying future-facing schema and settings surfaces for problems the system does not yet have.
- Maintaining a giant control-plane contract for a single-user local tool.
- Supporting live sessions, queue orchestration, and admin mutations without first hardening core delivery semantics.

Top underbuilding risks:
- No real auth/authz.
- No trustworthy append-only delivery attempt model.
- Weak failure isolation in watcher processing.
- Weak recovery and backup story.
- Weak target-safety enforcement.

Top hidden future costs:
- Frontend/backend contract drift around mega-bootstrap.
- Delivery semantics that will be expensive to untangle later.
- Documentation that keeps rationalizing rather than describing reality.
- Schema drag from admin/live-session features that are only half-real.
- Operational dependence on one human operator's memory.

Best simplifications:
- Make Python the only workflow owner.
- Make Postgres the only canonical truth and say so plainly.
- Shrink the console to a few operator jobs.
- Defer or remove subsystems that are still mostly scaffolding.
- Tighten the intake contract instead of adding more fallback behavior.

Best redesign moves:
- Replace mutable delivery retry/status logic with an append-only attempt model.
- Replace mega-bootstrap with task-oriented APIs.
- Treat live-session delivery as a privileged adapter with hard constraints.
- Rewrite architecture docs to match runtime truth before phase 2 expands scope.

## 5. Part A — High-leverage changes the human should make before / for phase 2

**Freeze the product boundary**
- Recommendation: Explicitly define PromptForge as a local compiler/router with a small operator console, not a general workflow platform.
- Why it matters: The team is already paying platform complexity without platform-level product proof.
- What pain it prevents: Scope creep, fake modularity, and phase-2 architecture drag.
- Urgency: critical
- Move type: simplification

**Choose one workflow owner**
- Recommendation: Decide that Python owns intake, compile, delivery, retry semantics, and canonical transitions. n8n may only react to completed canonical events or dead-letter notifications.
- Why it matters: Two owners over one lifecycle guarantees confusion and race conditions.
- What pain it prevents: Duplicate dispatch logic, retry inconsistencies, and future integration knots.
- Urgency: critical
- Move type: redesign

**Decide whether live-session delivery is real or not**
- Recommendation: Either bless one hardened live-session adapter as a first-class phase-2 feature or cut live sessions out of phase 2 entirely.
- Why it matters: The codebase already contains tmux-backed live dispatch, but the docs and safety story do not match.
- What pain it prevents: Dangerous half-supported execution paths and architectural ambiguity.
- Urgency: high
- Move type: redesign

**Set the auth posture honestly**
- Recommendation: Decide whether phase 2 remains strictly local-trusted-only or whether any remote/operator exposure is in scope. If exposure is in scope, real auth/authz is mandatory before more console work.
- Why it matters: The current role-header approach is not a security model.
- What pain it prevents: Unsafe exposure and future permission retrofits across dozens of routes.
- Urgency: critical
- Move type: hardening

**Set the lineage standard**
- Recommendation: Decide whether PromptForge needs true append-only delivery history or only current-state operational visibility. Do not keep claiming append-only lineage unless the system actually stores it.
- Why it matters: Data model decisions ripple into retry behavior, UI design, metrics, and audits.
- What pain it prevents: Fake auditability and expensive schema churn later.
- Urgency: high
- Move type: redesign

**Cut the control-plane ambition**
- Recommendation: Limit phase 2 console scope to queue/review, delivery operations, and runtime settings. Defer lower-value admin surfaces.
- Why it matters: The console is already oversized relative to the compiler core.
- What pain it prevents: Frontend contract sprawl and backend admin bloat.
- Urgency: high
- Move type: simplification

## 6. Part B — Changes the AI agent team should make

**Rewrite the architecture docs to match runtime truth**
- Recommendation: Update the system architecture, MVP plan, and backend diagrams so they describe Python-owned workflow, Postgres canonical truth, actual live-session status, and the vault write-back reality.
- Why it matters: The current docs are masking boundary confusion.
- Implementation direction: Align docs with watcher/API code paths, remove false claims, and explicitly mark n8n as optional reactive automation if that is the chosen boundary.
- Dependency on human decision: yes
- Urgency: critical

**Slim the console bootstrap and split task-oriented read surfaces**
- Recommendation: Replace the mega-bootstrap contract with smaller responses aligned to queue/review, delivery ops, and settings.
- Why it matters: The current contract is oversized and fragile.
- Implementation direction: Keep a compact dashboard summary, move lineage/logs/details behind on-demand endpoints, and stop preloading raw domain tables by default.
- Dependency on human decision: no
- Urgency: high

**Repair delivery retry/reroute semantics**
- Recommendation: Stop mutating the same delivery row for retry/status changes when the intended behavior is append-only attempt history.
- Why it matters: Current behavior breaks the documented state story.
- Implementation direction: Introduce a minimal delivery-attempt model or create new delivery rows on retry/reroute; preserve latest-state views separately.
- Dependency on human decision: yes
- Urgency: critical

**Fail closed on auth-sensitive routes**
- Recommendation: Remove the default-admin fallback and consistently enforce auth guards or explicit local-only gating on every mutating/admin route.
- Why it matters: Most of the control surface is currently too trusting.
- Implementation direction: Require authenticated context for all mutations, return forbidden by default, and hide unsupported routes from UI contracts until they are safe.
- Dependency on human decision: yes
- Urgency: critical

**Add vault containment checks for note delivery**
- Recommendation: Validate target folders against the vault root before writing any note output.
- Why it matters: Current target config can escape the vault.
- Implementation direction: Reject absolute paths, normalize path traversal, enforce `resolved_path.is_relative_to(vault_root)`, and add tests for bad target configs.
- Dependency on human decision: no
- Urgency: critical

**Harden watcher failure isolation**
- Recommendation: Isolate per-note failures so one webhook, dispatch, or parse problem does not kill the watcher loop.
- Why it matters: Intake reliability is core product value.
- Implementation direction: Wrap `_process_note_path()` in per-note exception handling, persist workflow errors, and keep the daemon alive after failures.
- Dependency on human decision: no
- Urgency: high

**Enforce target safety metadata before dispatch**
- Recommendation: Make `requires_confirmation`, `is_sensitive`, and `is_auto_dispatch_safe` actually govern dispatch behavior.
- Why it matters: Safety metadata that is not enforced is decorative.
- Implementation direction: Add policy checks in dispatch paths, expose clear operator errors, and require explicit confirmation flows where needed.
- Dependency on human decision: no
- Urgency: high

**Hide or remove stubbed control-plane actions**
- Recommendation: Remove unsupported endpoints from the effective operator surface until they are implemented.
- Why it matters: Formalizing stubs creates false product surface area.
- Implementation direction: Drop or disable secrets rotation, dictionary upsert, purge, and similar stubbed actions from bootstrap/UI navigation.
- Dependency on human decision: no
- Urgency: medium

## 7. Ruthless prioritization

Top 5 highest-leverage changes overall:
1. Make Python the sole workflow owner and demote n8n to reactive sidecar status.
2. Repair delivery history so retry/reroute are append-only and trustworthy.
3. Cut the console scope and kill mega-bootstrap.
4. Fail closed on auth and add dispatch safety checks.
5. Rewrite the architecture docs to describe the actual system instead of the aspirational one.

Top 5 things to remove, defer, or collapse:
1. n8n on the hot path.
2. The fiction that the console is a thin control plane.
3. Stubbed admin features as first-class API surface.
4. Future-facing schema and session-registry baggage that phase 2 may not need.
5. Heuristic intake parsing fallback beyond the strict directive/note contract.

Top 5 things most likely to create future pain if ignored:
1. In-place delivery mutation pretending to be append-only history.
2. Default-admin header-based auth.
3. Oversized console bootstrap contract.
4. Unsafe live-session and vault-target dispatch paths.
5. Architecture docs that keep lying about workflow ownership and source-of-truth behavior.

## 8. If we rebuilt phase 2 with less complexity

What survives:
- Obsidian-first intake.
- Python watcher.
- Deterministic preprocess/validate/render pipeline.
- Postgres as canonical state.
- Queue and note-output delivery.
- Small operator console for queue/review, delivery ops, and runtime settings.

What gets cut:
- n8n as workflow owner.
- Broad admin console sprawl.
- Stubbed control-plane features presented as real capability.
- Decorative lineage language that the storage model does not support.

What gets merged:
- Watcher/API "workflow logic" into one explicitly owned Python core.
- Delivery status and retry logic into one append-only attempt subsystem.
- Dashboard/bootstrap into a compact ops summary plus on-demand detail endpoints.

What gets deferred:
- Multi-user support.
- Broad live-session target matrix.
- Secrets-rotation UX beyond what is actually implemented and secured.
- Schema-heavy session management unless phase 2 proves it is necessary.

What gets made stricter:
- Intake note shape and directive grammar.
- Auth defaults.
- Target safety checks.
- Delivery state transitions.
- Documentation truthfulness about what is real, what is optional, and what is deferred.
