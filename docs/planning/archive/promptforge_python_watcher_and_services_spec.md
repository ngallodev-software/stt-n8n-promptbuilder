# PromptForge Python Watcher and Services Technical Specification

## Purpose

This document defines the Python-side implementation contract for the PromptForge MVP.

It covers:

- vault watcher responsibilities
- import pipeline behavior
- deterministic preprocessing services
- validation and rendering service boundaries
- error handling
- recommended module layout
- operational sequencing between Python, Postgres, n8n, and llama.cpp

The goal is to make the Python layer the durable home for rule-heavy, testable, deterministic logic, while n8n remains the orchestrator.

---

## Architectural role of the Python layer

The Python layer has two main responsibilities:

### 1. Watcher / intake boundary
The watcher is responsible for turning an Obsidian note into canonical workflow records.

### 2. Deterministic processing services
The services are responsible for deterministic logic before and after the model:

- parsing
- normalization
- canonicalization
- validation
- rendering
- delivery adapter preparation

This means the Python layer owns the most correctness-sensitive parts of the system.

---

## Service split

For the MVP, the Python layer should be split into two operational components:

### A. `promptforge-watcher`
A filesystem watcher/importer.

Responsibilities:
- monitor `Inbox/Voice/`
- read newly created or changed eligible notes
- parse frontmatter and body
- extract directive block and transcript block
- apply initial deterministic note eligibility checks
- create intake note and utterance rows
- create raw transcript revision
- trigger n8n webhook

### B. `promptforge-services`
A callable HTTP or internal service layer.

Responsibilities:
- deterministic preprocessing
- structured output validation
- final prompt rendering
- delivery payload shaping
- optional future review summary generation

This split keeps file watching concerns separate from processing services.

---

## Recommended repository/module layout

```text
promptforge/
  promptforge_watcher/
    __init__.py
    __main__.py
    config.py
    watcher.py
    importer.py
    note_parser.py
    eligibility.py
    db.py
    webhook.py
    hashing.py
    logging.py

  promptforge_services/
    __init__.py
    __main__.py
    api.py
    config.py
    db.py
    models/
      frontmatter.py
      directives.py
      structured_output.py
      delivery.py
    preprocess/
      normalize.py
      directives.py
      canonicalize.py
      terminology.py
      transcript.py
    validate/
      structured_output.py
      enums.py
    render/
      templates.py
      markdown.py
      outputs.py
    delivery/
      adapters.py
      claude_cli.py
      codex_cli.py
      generic_queue.py
    common/
      errors.py
      ids.py
      time.py
      json.py
      logging.py

  tests/
    test_note_parser.py
    test_directive_parser.py
    test_canonicalize.py
    test_structured_validation.py
    test_rendering.py
    test_importer.py
```

---

## Watcher responsibilities in detail

## Watch folder contract

The watcher should only monitor:

`Inbox/Voice/`

It must ignore:
- other folders
- hidden files
- temp files
- files without markdown extension
- notes with `watch_eligible: false`
- notes already imported unless content hash changes and reimport policy allows update

## New note detection strategy

Preferred MVP strategy:
- polling plus content hashing, or
- filesystem watch plus stable delay before import

A safe import approach:
1. file appears
2. wait short stabilization interval
3. read file
4. compute hash
5. verify frontmatter/body parse
6. import once

This avoids partially written file reads.

## Note import steps

### Step 1: load note text
Read full markdown file from disk.

### Step 2: parse frontmatter
Extract YAML frontmatter and body.

### Step 3: validate eligibility
A note is eligible only when:
- path is under `Inbox/Voice/`
- markdown parses successfully
- `watch_eligible: true`
- `status: new`
- transcript body is non-empty

### Step 4: split control and transcript blocks
Recommended body sections:
- `## Control`
- `## Transcript`

The parser should support:
- explicit section headings
- compact first-line directive prefix fallback

### Step 5: write canonical records
Create:
- `intake_notes`
- `utterances`
- `transcript_revisions` with `raw`

### Step 6: transition note/import state
Recommended DB state:
- `intake_notes.status = imported`

### Step 7: trigger n8n
POST webhook payload with identifiers and resolved baseline metadata.

### Step 8: finalize source note lifecycle
Recommended MVP behavior:
- if the full run succeeds, write back metadata and move/delete the source draft from `Inbox/Voice`
- if processing or delivery fails, keep the source draft in `Inbox/Voice`
- do not create processed-note write-back artifacts for failed runs

---

## Reimport policy

The watcher should support a clear reimport policy.

Recommended MVP behavior:
- if note path is already imported and content hash is unchanged: ignore
- if note path is already imported and status is `processed`: ignore by default
- if note path changed but `watch_eligible` is still true and reimport flag is enabled: create a new import event or revision entry, not silent overwrite

For MVP, simplest safe rule:
- one import per note path unless explicitly reset

---

## Note parser contract

## Frontmatter parser

Recommended libraries:
- `python-frontmatter`
- `PyYAML`

Output shape:
```python
class ParsedNote(BaseModel):
    relative_path: str
    title: str
    frontmatter: dict
    body_markdown: str
    control_text: str | None
    transcript_text: str | None
    note_hash: str
```

## Section extraction rules

Preferred order:
1. explicit `## Control` and `## Transcript`
2. fallback to first paragraph as control directives if it matches directive grammar
3. remainder becomes transcript

If transcript is empty after parsing:
- reject import
- record error

---

## Directive parsing contract

The watcher and preprocess service should share the same deterministic directive parser.

### Approved directive fields

- `project`
- `prompt_type`
- `destination`
- `target_identifier`
- `mode`
- `priority`
- `requires_review`

### Approved spoken patterns

- `project is <value>`
- `prompt type is <value>`
- `destination is <value>`
- `target is <value>`
- `mode is <value>`
- `priority is <value>`
- `review is true|false`

### Alias examples

- `prompt kind` -> `prompt_type`
- `dest` -> `destination`
- `session` -> `target_identifier`
- `repo` / `workspace` -> `project`

### Output shape

```python
class ParsedDirectives(BaseModel):
    project: str | None = None
    prompt_type: str | None = None
    destination: str | None = None
    target_identifier: str | None = None
    mode: str | None = None
    priority: str | None = None
    requires_review: bool | None = None
    warnings: list[str] = []
```

---

## Deterministic preprocessing service

## Endpoint responsibility

Suggested endpoint:
- `POST /preprocess`

Input:
```json
{
  "utterance_id": "33333333-3333-4333-8333-333333333333"
}
```

The service then loads canonical records from Postgres and performs deterministic transformations.

## Processing stages

### Stage P1: load utterance + context
Load:
- utterance
- intake note
- resolved project context
- applicable term dictionaries
- applicable rulesets
- frontmatter defaults

### Stage P2: directive canonicalization
Resolve directive values via:
- exact match
- alias mapping
- rapidfuzz similarity against known values

Examples:
- `thtaxmachine` -> `the-tax-machine`
- `codingcli` -> `coding-cli`

### Stage P3: terminology normalization
Apply deterministic term replacements using:
- project dictionary first
- user dictionary next
- global dictionary last

### Stage P4: transcript cleanup
Apply deterministic cleanup:
- remove leading filler words
- collapse repeated spaces
- normalize punctuation
- remove directive lines if still present
- preserve technical tokens already canonicalized

### Stage P5: emit preprocess result
Persist:
- `directive_stripped`
- `deterministic_preprocessed`

Update:
- `prompt_generations.status = preprocessed`

---

## Structured transformation service contract

The transform stage may be called by n8n directly to llama.cpp, or via a Python wrapper.

Recommended wrapper endpoint:
- `POST /transform`

Responsibilities:
- build model prompt from canonical preprocessed text
- include output contract instructions
- include strict enum hints and field requirements
- forward to llama.cpp
- return raw model JSON/text response

Wrapper advantage:
- one stable place for model prompt construction
- easier logging
- easier swapping of local models later

---

## Validation service

Suggested endpoint:
- `POST /validate`

Input:
```json
{
  "prompt_generation_id": "44444444-4444-4444-8444-444444444444"
}
```

## Responsibilities
- validate structured JSON with Pydantic
- canonicalize enums where safe
- reject empty required fields
- attach validation errors
- set review flags where partial ambiguity remains

## Validation output model

```python
class AgentTaskOutput(BaseModel):
    intent: str
    project_slug: str
    prompt_type: str
    destination: str
    target_identifier: str | None = None
    requires_review: bool = False
    final_prompt_markdown: str
    notes: list[str] = []
```

---

## Rendering service

Suggested endpoint:
- `POST /render`

## Responsibilities
- select output template
- render final prompt markdown via Jinja2
- normalize markdown with mdformat
- persist `final_rendered_prompt`
- update `prompt_generations.final_prompt_markdown`
- update status to `rendered`

## Template selection precedence

1. explicit template tied to prompt generation
2. project prompt type template
3. user-scoped fallback
4. global default

---

## Delivery shaping service

Suggested endpoint:
- `POST /prepare-delivery`

Responsibilities:
- resolve destination class
- resolve target adapter config
- shape payload for downstream dispatcher
- ensure dispatch metadata is complete enough for queueing

This service does not have to dispatch in MVP, but it should prepare canonical payloads.

---

## Recommended internal error taxonomy

Use stable machine-readable error codes.

### Import/parsing
- `NOTE_PARSE_ERROR`
- `INVALID_FRONTMATTER`
- `EMPTY_TRANSCRIPT`
- `INELIGIBLE_NOTE`
- `DUPLICATE_IMPORT`

### Directive/canonicalization
- `UNKNOWN_PROJECT`
- `AMBIGUOUS_PROJECT`
- `INVALID_DESTINATION`
- `INVALID_PROMPT_TYPE`
- `INVALID_MODE`

### Transformation/validation
- `LLM_TIMEOUT`
- `LLM_INVALID_JSON`
- `VALIDATION_FAILED`
- `EMPTY_FINAL_PROMPT`

### Delivery
- `TARGET_NOT_FOUND`
- `TARGET_UNAVAILABLE`
- `DISPATCH_FAILED`

These should be persisted in `processing_runs.trace_json` and/or error text fields.

---

## Database access rules

Python services should not silently mutate unrelated records.

Recommended discipline:
- watcher creates intake note, utterance, raw revision
- preprocess service only appends revisions and updates prompt generation status fields
- validation service only updates prompt generation validation fields
- renderer only appends final rendered revision and updates final prompt fields
- dispatch service only updates delivery records

This keeps lineage and responsibility clear.

---

## Logging policy

Each Python component should emit structured logs.

Minimum log fields:
- service_name
- note_relative_path
- intake_note_id
- utterance_id
- prompt_generation_id
- delivery_id
- stage
- result
- error_code
- duration_ms

Do not log full prompt text by default in production logs if not needed; prefer IDs plus selective debug logging.

---

## Testing strategy

The Python layer should be the most heavily tested part of the system.

### Unit tests
- frontmatter parsing
- section extraction
- directive parsing
- canonicalization
- term normalization
- structured validation
- final rendering

### Fixture tests
Use the example-record artifact as source fixtures.

### Integration tests
- import note -> DB rows created
- preprocess -> revisions appended
- validate -> status transitions correct
- render -> final prompt persisted

---

## Recommended implementation order

1. note parser
2. watcher importer
3. directive parser
4. canonicalization layer
5. preprocess endpoint
6. structured output model definitions
7. validation endpoint
8. rendering endpoint
9. delivery payload preparation
10. adapter implementations

---

## Final recommendation

The Python layer should be the stable engine room of PromptForge.

It should own:
- deterministic text handling
- rule evaluation
- contract validation
- rendering
- payload shaping

That gives you a system that is testable, explainable, and much easier to evolve than a workflow made entirely from n8n node logic.
