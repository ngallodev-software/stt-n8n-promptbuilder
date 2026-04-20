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

Versioning rule:

- treat each row as immutable history
- create a new row for a new version
- select the active row with `is_active = true`
- for project rulesets, `projects.active_ruleset_id` is the pointer to the current active row
- patch operations must never overwrite an older row in place
- tests should assert that a patch creates a later row and preserves the prior version in history

### rules

Fields:

- `id`
- `ruleset_id`
- `rule_type`
- `priority`
- `enabled`
- `match_conditions_json`
- `action_json`

Versioning note:

- rules are mutable inside a ruleset, so patch operations update the existing row in place
- version history lives on the surrounding ruleset/template records, not on the individual rule row

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

Versioning rule:

- treat each row as immutable history
- create a new row for a new version
- select the active row with `is_active = true`
- active rows are unique per scope/project/prompt type bucket
- patch operations must never overwrite an older row in place
- tests should assert that a patch creates a later row and preserves the prior version in history

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

### delivery_session_registry

Persistent registry for live chat and CLI delivery sessions.

Fields:

- `id`
- `delivery_target_id` nullable
- `target_type`
- `target_identifier`
- `session_identifier`
- `session_status`
- `provider_name` nullable
- `is_current`
- `is_attached`
- `is_busy`
- `is_reachable`
- `is_stale`
- `last_seen_at` nullable
- `heartbeat_at` nullable
- `ended_at` nullable
- `metadata_json`
- `created_at`
- `updated_at`

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
- `session_identifier` nullable
- `dispatch_request_json`
- `dispatch_response_json`
- `queued_at`
- `dispatched_at` nullable
- `acked_at` nullable
- `error_text` nullable

Delivery attempt rule:

- each row is one delivery attempt
- retries create new rows rather than overwriting prior attempts
- the attempt history is already stored in `deliveries`
- once a delivery reaches a terminal state, retry and reroute endpoints must not mutate the row
- queued deliveries may still be rerouted to another queue target before they become terminal

### delivery_session_registry

The session registry is a live lookup table for chat and CLI transports, not a public CRUD surface.

- current API coverage may expose health and dispatch behavior for live targets
- until a real transport exists, live session dispatch should stay unsupported in the Python backend
- tests should validate the unsupported path and the persisted failed delivery attempt, not invent registry writes

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

### workflow_error_records

Append-only exact error rows used for triage and human intervention.

Fields:

- `id`
- `source_kind`
- `project_id` nullable
- `intake_note_id` nullable
- `utterance_id` nullable
- `prompt_generation_id` nullable
- `delivery_id` nullable
- `processing_run_id` nullable
- `delivery_target_id` nullable
- `stage_name` nullable
- `error_class` nullable
- `error_code` nullable
- `error_message`
- `error_context_json`
- `human_intervention_required`
- `created_at`

## Scope precedence

When resolving configuration:

**project overrides user overrides global**

This precedence should apply to:

- rulesets
- term dictionaries
- prompt templates
- delivery targets
- formatting profiles

## Error reporting rule

Store exact error rows in `workflow_error_records` and derive summary fingerprints on read.
Do not bake computed fingerprints into the persisted record shape.

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

Rulesets and prompt templates are versioned configuration records, not lineage artifacts. Editing them should preserve the prompt-generation history that already references an older version.

Delivery mutations should stay narrow: retry and status updates may change delivery state, queue timestamps, and error text, but they must not rewrite the linked prompt generation, raw transcript, or rendered prompt content.
