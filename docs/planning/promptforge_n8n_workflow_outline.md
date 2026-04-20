# PromptForge n8n Workflow Outline

## Purpose

This document defines the production-grade orchestration shape for the PromptForge MVP.

The workflow is intentionally divided so that:

- Python owns deterministic text logic and schema enforcement
- n8n owns step sequencing, retries, routing, and delivery orchestration
- Postgres owns canonical state
- llama.cpp owns ambiguous language transformation only

## High-level workflow map

### Workflow A: Obsidian intake orchestration
Triggered by the Python watcher after a note is imported into Postgres.

### Workflow B: delivery queue processor
Triggered on a schedule or via queue event to dispatch pending prompt deliveries.

### Workflow C: review and error recovery
Triggered on a schedule to surface items requiring human attention.

---

## Workflow A: Obsidian intake orchestration

### Trigger

Webhook from watcher service.

### Example payload

```json
{
  "intake_note_id": "22222222-2222-4222-8222-222222222222",
  "utterance_id": "33333333-3333-4333-8333-333333333333",
  "project_slug": "the-tax-machine",
  "destination": "cli",
  "target_identifier": "claude-tax-main"
}
```

### Stage A1: create processing run

#### Actions

- insert `processing_runs` row with `workflow_name = promptforge-intake-v1`
- mark run as `running`
- attach input payload to `trace_json`

#### Failure policy

- hard fail only if DB write fails

---

### Stage A2: load canonical context

#### Actions

Load from Postgres:

- intake note
- utterance
- resolved project
- matching delivery target, if any
- applicable rulesets
- applicable prompt templates
- current frontmatter state

#### Required outputs

```json
{
  "project_slug": "the-tax-machine",
  "prompt_type": "coding-cli",
  "destination": "cli",
  "delivery_mode": "queue"
}
```

#### Failure policy

- if no utterance is found, fail run
- if no project is found, continue with `inbox` if allowed and set review flag

---

### Stage A3: deterministic preprocessing

#### Implementation

Call Python service endpoint or module wrapper such as:

- `promptforge-preprocess`

#### Responsibilities

- parse directive lines
- strip directives from transcript body
- normalize punctuation and whitespace
- remove filler words according to approved rules
- canonicalize terms from dictionaries
- resolve aliases
- set warnings or `requires_review` if confidence is low

#### Expected persisted outputs

- `transcript_revisions` row with `directive_stripped`
- `transcript_revisions` row with `deterministic_preprocessed`
- optional frontmatter normalization info in `trace_json`

#### Retry policy

Safe to retry on transient service failure.

Do not blindly retry on:
- invalid frontmatter
- empty transcript
- irrecoverable parsing failure

Those should move to review/error.

---

### Stage A4: create or update prompt generation record

#### Actions

Insert `prompt_generations` row if not present.

Set:
- `status = preprocessed`
- `requires_review` based on preprocessing warnings
- `selected_ruleset_id`
- `selected_template_id`

---

### Stage A5: LLM transformation

#### Implementation

Call llama.cpp server or local model endpoint.

#### Input guidance

Provide:
- deterministic preprocessed text
- resolved project slug
- prompt type
- destination
- selected output contract name
- allowed enum/domain hints
- instruction to return schema-conforming JSON only

#### Expected outputs

- structured JSON response
- optional clean rewritten prompt body
- notes/warnings when ambiguity remains

#### Persisted artifacts

- `transcript_revisions` row with `llm_cleaned`
- `transcript_revisions` row with `llm_structured_source`

#### Prompt generation status

- set `status = transforming` before call
- advance to `structured_validating` after response is received

#### Retry policy

Safe to retry on:
- HTTP timeout
- connection failure
- temporary model endpoint failure

Not safe to loop forever on:
- consistently malformed structured output
- contract mismatch after multiple attempts

Recommended cap:
- 2 transformation attempts maximum for MVP

---

### Stage A6: structured validation

#### Implementation

Call deterministic validator service:

- `promptforge-validate`

#### Responsibilities

- validate schema with Pydantic
- ensure required fields are present
- coerce enums to canonical values where safely allowed
- reject empty final prompt content
- reject unsupported destinations/targets
- attach review flag if project/target is unresolved

#### Expected outcomes

##### Success
- validated structured JSON returned
- `prompt_generations.status` remains on path to render

##### Failure
- `prompt_generations.status = failed`
- `prompt_generations.error_text` populated
- `processing_runs.status = failed`
- `processing_runs.error_stage = structured_validating`

#### Retry policy

Do not blindly retry a validation failure unless the failure mode indicates transient upstream corruption.

---

### Stage A7: deterministic rendering

#### Implementation

Call renderer service:

- `promptforge-render`

#### Responsibilities

- render final output using selected template
- normalize final markdown
- generate any destination-specific wrapper text
- persist final artifact

#### Persisted outputs

- `transcript_revisions` row with `final_rendered_prompt`
- `prompt_generations.final_prompt_markdown`
- `prompt_generations.status = rendered`

#### Example rendering targets

- coding CLI instruction block
- chat-ready prompt block
- queue summary note
- Obsidian output note

---

### Stage A8: create delivery record

#### Delivery mode resolution

Use explicit frontmatter value first, then project defaults.

Possible modes:

- `draft`
- `queue`
- `auto_dispatch`

#### Actions

Create `deliveries` row with:
- destination
- target type
- target identifier
- mode
- status

Recommended defaults:

- `draft` -> leave as `not_started`
- `queue` -> set `queued` and stamp `queued_at`
- `auto_dispatch` -> either queue immediately or hand off to dispatch workflow

#### Important rule

A rendered prompt can exist with no valid delivery target. In that case:

- set `requires_review = true`
- create `queue_only` delivery or skip delivery creation
- do not discard the rendered prompt

---

### Stage A9: finalize workflow state

#### Actions

- `intake_notes.status = processed`
- `processing_runs.status = completed`
- `processing_runs.ended_at = now()`

#### Optional actions

- trigger Obsidian write-back/update for successful runs
- move note to processed folder only after a successful run; failed runs keep the source note in `Inbox/Voice`
- append generated summary/tags

---

## Workflow B: delivery queue processor

### Trigger options

- scheduled every N seconds/minutes
- DB-backed polling loop
- future queue event trigger

### Stage B1: fetch next eligible delivery

#### Query conditions

- `status = queued`
- ordered by priority then queued_at
- only dispatch if target adapter is available

### Stage B2: mark delivery as dispatching

Set:
- `status = dispatching`

### Stage B3: resolve target adapter

Possible adapters:

- Claude CLI session adapter
- Codex harness adapter
- chat session adapter
- generic queue adapter

### Stage B4: dispatch

#### On success

Set:
- `status = delivered`
- `dispatched_at = now()`

#### On acknowledgment, if supported

Set:
- `status = acked`
- `acked_at = now()`

#### On failure

Set:
- `status = failed`
- `error_text = <adapter error>`

#### Important rule

Delivery failure must not mutate prompt generation back to failed.

---

## Workflow C: review and error recovery

### Trigger

Scheduled scan, for example every 10 minutes.

### Query sets

1. `prompt_generations` with `requires_review = true`
2. `prompt_generations.status = failed`
3. `deliveries.status = failed`
4. `intake_notes.status = error`

### Actions

- build review summaries
- optionally write review notes to Obsidian
- optionally queue manual triage items
- surface top failure reasons

### Example review summary content

- note path
- project
- failure stage
- warning list
- current prompt artifact presence
- delivery status

---

## Recommended node and service split

### n8n should orchestrate

- webhook trigger
- DB read/write nodes
- HTTP calls to Python services
- retry branching
- queue processing logic
- notification/review workflows

### Python services should own

- frontmatter parsing
- directive parsing
- canonicalization dictionaries
- fuzzy resolution
- Pydantic validation
- final markdown rendering
- destination-specific formatting

### llama.cpp should own

- disfluency-aware rewrite
- structured content transformation
- optional notes about ambiguity

---

## Minimal persisted state changes by stage

### Prompt generation states

1. `created`
2. `preprocessed`
3. `transforming`
4. `structured_validating`
5. `rendered`
6. `failed`

### Delivery states

1. `not_started`
2. `queued`
3. `dispatching`
4. `delivered`
5. `acked`
6. `failed`

### Intake note states

1. `new`
2. `imported`
3. `processing`
4. `processed`
5. `error`
6. `archived`

---

## Retry rules

### Safe automatic retries

- transient preprocessing service timeout
- llama.cpp timeout
- renderer timeout
- temporary dispatch adapter failure

### Route to review instead of infinite retry

- invalid YAML/frontmatter
- unresolved project below threshold
- empty transcript
- repeated contract/schema violations
- unsupported target type

Recommended MVP retry caps:

- preprocess: 2
- transform: 2
- validate: 1 unless upstream response changed
- render: 2
- delivery dispatch: 3

---

## Logging and observability fields

Every orchestration run should capture at minimum:

- `workflow_name`
- `intake_note_id`
- `utterance_id`
- `prompt_generation_id`
- `delivery_id`
- selected project slug
- selected ruleset id
- selected template id
- destination
- target identifier
- final state
- error stage
- error message
- attempt count

---

## Recommendation

Treat n8n as the conductor.

It should know:
- what the next stage is
- what inputs that stage needs
- what success and failure mean
- when to retry
- when to route to review

It should not become the place where core parsing, normalization, or schema logic quietly lives.
