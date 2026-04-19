# Prompt for ChatGPT Desktop (to generate final Lovable prompt)

```text
You are a senior product designer + staff frontend architect. Your task is to generate a single, production-grade prompt for Lovable.io to build a complete frontend for PromptForge.

Important: your output should be ONLY:
1) One final Lovable prompt (copy/paste ready), and
2) A short assumptions list.
No extra commentary.

========================
PROJECT CONTEXT
========================
App name: PromptForge
Purpose: Obsidian-first voice-to-prompt compiler/router with deterministic preprocessing, optional LLM stages, delivery queueing/dispatch, and deep auditability.

Frontend stack requirements:
- React
- TypeScript
- Tailwind CSS
- Responsive (mobile/tablet/desktop)
- Must support debugging, log viewing, and diagnosis of pipeline failures
- Must allow modifying workflow controls, mappings, rules, templates, targets, and operational settings safely

Backend/API currently exposed:
- GET /_healthz
- GET /health
- GET /providers/health
- POST /preprocess
- POST /validate
- POST /render
- POST /prepare-delivery

Data contract highlights:
- contract_name: "agent_task_v1"
- destinations: chat | cli | obsidian_note | queue_only
- modes: draft | queue | auto_dispatch
- target types: none | chat_session | claude_session | codex_session | obsidian_note | generic_queue
- delivery statuses: not_started | queued | dispatching | delivered | acked | failed

========================
DATABASE SCHEMA (AUTHORITATIVE)
========================
Use these Postgres entities exactly (do not invent replacements):
- projects
- intake_notes
- utterances
- transcript_revisions (append-only lineage)
- rulesets
- rules
- term_dictionary
- prompt_templates
- prompt_generations
- llm_runs
- delivery_targets
- deliveries
- processing_runs
- views: v_latest_transcript_revision, v_latest_delivery

Key enum domains:
- pf_scope: global | user | project
- pf_note_status: new | imported | processing | processed | error | archived
- pf_revision_kind: raw | directive_stripped | deterministic_preprocessed | llm_cleaned | llm_structured_source | final_rendered_prompt
- pf_producer_type: human | watcher | python | llm | renderer | system
- pf_rule_type: cleanup | expansion | routing | formatting | safety | terminology
- pf_prompt_generation_status: created | preprocessed | transforming | structured_validating | rendered | failed
- pf_llm_run_mode: review | inference
- pf_destination: chat | cli | obsidian_note | queue_only
- pf_target_type: none | chat_session | claude_session | codex_session | obsidian_note | generic_queue
- pf_delivery_mode: draft | queue | auto_dispatch
- pf_delivery_status: not_started | queued | dispatching | delivered | acked | failed
- pf_processing_status: running | completed | failed
- pf_priority: low | normal | high | urgent

Critical table behavior:
- intake_notes.note_relative_path is unique
- transcript_revisions is append-only stage history
- deliveries can have multiple rows per prompt_generation
- processing_runs.trace_json stores workflow trace
- prompt_generations stores structured_output_json + final_prompt_markdown
- write-back updates frontmatter (status, destination, prompt_type, mode, IDs, tags, etc.)

========================
UI SCOPE (MUST INCLUDE)
========================
Generate a Lovable prompt that builds all of this:

1) Global layout
- Left nav + top command/search bar + environment badge
- Workspace switcher (project/global scope)
- Responsive collapsing nav
- Dark/light support (theme details can be basic; I will iterate styling later)

2) Dashboard / Ops overview
- Health cards: API health, provider health, DB status proxy, queue depth, failures in last 24h
- Throughput charts: notes imported, rendered, delivered, failed
- “Needs attention” panels: review-required prompts, failed deliveries, failed processing runs, notes stuck in error/new
- Quick actions: re-run preprocess, re-render, retry delivery, mark archived, open trace

3) Intake explorer
- Table + detail pane for intake_notes
- Filters: status, project, watch_eligible, date range, source_device
- Full-text search on body/frontmatter-derived fields
- Compare original frontmatter vs processed frontmatter fields
- Show eligibility reasons and skip causes

4) Pipeline trace viewer (diagnostics-first)
- Per-note timeline across:
  intake_note -> utterance -> transcript_revisions -> prompt_generation -> deliveries -> processing_runs
- Stage cards with timestamps, producer_type/name, warnings, errors, metadata_json, trace_json
- Diff viewer between revision stages (raw -> directive_stripped -> deterministic_preprocessed -> final_rendered_prompt)
- JSON inspector with copy/export

5) Rules & mappings studio
- CRUD UI for rulesets, rules, term_dictionary, prompt_templates, delivery_targets
- Scope-aware editing (global/user/project) with precedence visualization
- Priority ordering UI for rules
- Rule test sandbox: input transcript/control/frontmatter -> preview preprocess/validate/render/prepare-delivery outputs
- Dry-run mode by default for risky edits

6) Prompt generation + delivery operations
- prompt_generations table with status, prompt_type, requires_review, selected ruleset/template
- Render preview pane (markdown + raw contract JSON)
- deliveries table with retries, ack/failure details, target info, mode, priority
- Manual actions:
  - retry delivery
  - reroute target
  - change priority
  - force review
  - clone/requeue

7) Review queue + error recovery
- Unified queue for:
  - requires_review
  - failed generation
  - failed deliveries
  - processing_runs.status = failed
- Root-cause panel (latest error_text + failed stage + related trace)
- One-click “open all related artifacts” links

8) Log center
- Structured live-ish logs page (polling is fine)
- Service tabs: watcher, api, n8n, postgres
- Preset filters for error/warn and correlation by intake_note_id / utterance_id / prompt_generation_id / delivery_id
- Saveable filter presets

9) Settings/admin
- Environment config visibility (redacted secrets)
- Watch folders and processing folders display/edit UI
- Webhook enable/disable and endpoint health check
- LLM provider mode display (deterministic_only, etc.)
- Feature flags for dangerous operations

10) Auditability and exports
- Export trace bundle (JSON + markdown) per note
- Export failed items report
- Change history panel for rule/template edits (include actor + timestamp placeholders)

========================
SQL QUERY PACK (REQUIRED IN OUTPUT)
========================
In the Lovable prompt, include an explicit “Query Catalog” section with named queries at minimum:

Q1 Latest intake notes with project + latest prompt + latest delivery
Q2 Intake by status counts (24h, 7d, 30d)
Q3 Notes requiring review
Q4 Failed processing runs with stage + message
Q5 Failed deliveries and retry candidates
Q6 Queue depth by priority and destination
Q7 Full lineage for a note_relative_path
Q8 Transcript revision timeline for utterance_id
Q9 Diff source query for adjacent transcript revisions
Q10 Prompt generations with validation/render status
Q11 LLM run latency/token usage summary per model/provider
Q12 Project-level throughput/failure rate
Q13 Active rulesets/rules by scope and project
Q14 Term dictionary entries by scope/project
Q15 Prompt templates active by prompt_type and scope
Q16 Delivery targets and safety flags
Q17 Orphan/consistency checks (missing links between core tables)
Q18 Notes skipped for eligibility reasons (from logs/metadata where available)
Q19 Top recurring error_text fingerprints
Q20 End-to-end SLA query (imported_at -> delivered/failed latency)

Also include at least 5 mutation queries or API mutation actions for:
- update delivery status
- retry/requeue delivery
- update rule enabled/priority
- upsert dictionary term
- toggle template active version

All SQL must be parameterized and safe; no string interpolation.

========================
GUARDRAILS / RULES (MANDATORY)
========================
Your Lovable prompt must enforce these:
- Non-destructive by default; confirm dialogs for destructive mutations
- Role-aware controls: viewer/operator/admin modes
- Secrets redaction in UI/logs
- PII-safe logging and copy/export
- Optimistic UI only where rollback is reliable
- Strong input validation (zod or equivalent) for all forms
- Explicit empty/loading/error states everywhere
- Error boundaries + retry affordances
- Accessibility minimum:
  - keyboard navigable
  - visible focus
  - semantic labels
  - color contrast
- Responsive behavior:
  - mobile first-class
  - no critical function desktop-only
- Performance:
  - server pagination
  - virtualized long tables/log streams
  - debounced search/filter
- Testing expectations in generated app spec:
  - unit tests for critical logic
  - integration tests for data flows
  - smoke/e2e for core operator paths
- Explainability:
  - every automation decision panel should show “why” (matched rule, fallback path, warning)

========================
INFORMATION ARCHITECTURE (EXPECTED)
========================
Define concrete pages/routes and component map for:
- /dashboard
- /intake
- /intake/:id
- /pipeline/:intakeNoteId
- /prompts
- /deliveries
- /review
- /rules
- /dictionary
- /templates
- /targets
- /logs
- /settings
- /health

Include shared components:
- DataTable (filter/sort/paginate)
- TimelineTrace
- JsonViewer
- MarkdownPreview
- DiffViewer
- QueryInspector
- StatusBadge
- ActionDrawer
- ConfirmationModal

========================
OUTPUT STYLE CONSTRAINT
========================
Your output must be a single Lovable-ready prompt that is implementation-grade and specific, not generic product copy. It should include:
- clear build objective
- route map
- component blueprint
- query catalog
- mutation actions
- state management/data-fetching approach
- guardrails
- acceptance criteria checklist

End with a short “Assumptions I made” section.
```
