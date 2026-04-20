# PromptForge Data Model and State Machine

## Purpose

This document defines the core relational model and workflow state machine for the PromptForge MVP.

## Core design rule

There are three distinct objects:

1. **intake note**
2. **prompt generation**
3. **delivery**

These must not be collapsed into a single lifecycle record.

## Core entities

### projects

Represents a project/workspace context.

Fields:

- `id`
- `slug`
- `name`
- `description`
- `vault_path`
- `git_repo_url`
- `default_prompt_type`
- `default_destination`
- `active_ruleset_id`
- `created_at`
- `updated_at`

### intake_notes

Represents imported Obsidian notes.

Fields:

- `id`
- `vault_path`
- `note_relative_path`
- `note_title`
- `obsidian_created_at`
- `imported_at`
- `frontmatter_json`
- `body_markdown`
- `project_id` nullable
- `status`
- `watch_eligible`
- `source_device`
- `created_at`

### utterances

Represents the canonical raw captured language unit.

Fields:

- `id`
- `intake_note_id`
- `raw_text`
- `directive_text` nullable
- `project_id` nullable
- `scope`
- `capture_type`
- `created_at`

### transcript_revisions

Append-only text stages.

Fields:

- `id`
- `utterance_id`
- `revision_kind`
- `content`
- `producer_type`
- `producer_name`
- `template_profile` nullable
- `quality_score` nullable
- `created_at`

Recommended revision kinds:

- `raw`
- `directive_stripped`
- `deterministic_preprocessed`
- `llm_cleaned`
- `llm_structured_source`
- `final_rendered_prompt`

### rulesets

Fields:

- `id`
- `name`
- `scope`
- `project_id` nullable
- `version`
- `is_active`
- `description`

### rules

Fields:

- `id`
- `ruleset_id`
- `rule_type`
- `priority`
- `enabled`
- `match_conditions_json`
- `action_json`

### term_dictionary

Fields:

- `id`
- `scope`
- `project_id` nullable
- `source_term`
- `canonical_term`
- `confidence`
- `notes`

### prompt_templates

Fields:

- `id`
- `name`
- `scope`
- `project_id` nullable
- `prompt_type`
- `version`
- `body_template`
- `output_contract_name`
- `is_active`

### prompt_generations

Fields:

- `id`
- `utterance_id`
- `project_id` nullable
- `prompt_type`
- `selected_ruleset_id`
- `selected_template_id`
- `structured_output_json`
- `final_prompt_markdown`
- `status`
- `created_at`

### delivery_targets

Fields:

- `id`
- `name`
- `target_type`
- `target_identifier`
- `scope`
- `project_id` nullable
- `is_default`
- `is_auto_dispatch_safe`
- `config_json`

### deliveries

Fields:

- `id`
- `prompt_generation_id`
- `delivery_target_id` nullable
- `destination`
- `target_type`
- `target_identifier`
- `mode`
- `status`
- `queued_at`
- `dispatched_at` nullable
- `acked_at` nullable
- `error_text` nullable

### processing_runs

Fields:

- `id`
- `utterance_id`
- `workflow_name`
- `status`
- `started_at`
- `ended_at` nullable
- `error_stage` nullable
- `trace_json`

## Scope precedence

When resolving configuration:

**project overrides user overrides global**

This precedence should apply to:

- rulesets
- term dictionaries
- prompt templates
- delivery targets
- formatting profiles

## Workflow state machines

### Intake note state machine

States:

- `new`
- `imported`
- `processing`
- `processed`
- `error`
- `archived`

Transitions:

- `new -> imported`
- `imported -> processing`
- `processing -> processed`
- `processing -> error`
- `processed -> archived`

### Prompt generation state machine

States:

- `created`
- `preprocessed`
- `transforming`
- `structured_validating`
- `rendered`
- `failed`

Transitions:

- `created -> preprocessed`
- `preprocessed -> transforming`
- `transforming -> structured_validating`
- `structured_validating -> rendered`
- `structured_validating -> failed`
- `transforming -> failed`

### Delivery state machine

States:

- `not_started`
- `queued`
- `dispatching`
- `delivered`
- `acked`
- `failed`

Transitions:

- `not_started -> queued`
- `queued -> dispatching`
- `dispatching -> delivered`
- `delivered -> acked`
- `dispatching -> failed`
- `queued -> failed`

## Console mutation contract notes

The console backend mutation contract has three explicit guarantees that should remain stable:

1. Delivery mutation immutability for non-queue destinations
- For destinations other than `queue_only`, terminal delivery records (`delivered`, `acked`, `failed`) are immutable for:
- `POST /console/deliveries/{id}/retry`
- `POST /console/deliveries/{id}/reroute`
- `PATCH /console/deliveries/{id}/status`
- These operations return `409` with structured error details and do not modify the delivery row.

2. Queue-only carveout
- `queue_only` deliveries are intentionally mutable, including records in terminal statuses.
- This supports operator-driven review queue correction and replay workflows.

3. Append-only rules/template mutations
- `PATCH /console/rules/{id}` creates a new `rulesets` version row and clones rules into the new version, applying the patch only in that new version.
- `PATCH /console/templates/{id}` creates a new `prompt_templates` row with a strictly increasing version.
- Existing versions remain queryable for traceability; active pointers are moved forward instead of in-place updates.

## Unsupported dispatch envelope

`POST /console/targets/{id}/dispatch` returns a structured `501` envelope for unsupported target types (for example `pf_target_type = none`):

- `detail.code = "unsupported_target_type"`
- `detail.status = "unsupported"`
- `detail.machine_status = "unsupported"`
- `detail.capability = "delivery_dispatch"`
- `detail.details` includes `target_type`, plus persisted `delivery_id` and `status`

Even when unsupported, the backend still records a failed delivery attempt for auditability.

## Important separation rule

A prompt can be rendered successfully even if delivery fails.

That is why prompt generation state and delivery state must be separate.

## Minimal lineage queries the system must support

The MVP should be able to answer:

1. Which note produced this prompt?
2. Which raw utterance produced this final rendered prompt?
3. Which ruleset and template version were used?
4. Which delivery target was selected?
5. What failed, if anything?
6. What exact text existed at each stage?

## Recommendation

Keep all text stages append-only and all state transitions explicit. Do not overwrite raw text, cleaned text, or final prompt artifacts.
