# PromptForge MVP Implementation Roadmap

## Goal

Provide a practical build order for the Obsidian-first PromptForge MVP.

## Phase 1: foundation

### Deliverables

- Docker Compose stack for n8n + Postgres
- Postgres schema for core entities
- Obsidian folder structure
- voice intake note template
- Python watcher skeleton
- basic import pipeline

### Success criteria

- creating a note in `Inbox/Voice/` inserts frontmatter
- watcher detects eligible note
- watcher imports note into Postgres
- note state changes from `new` to `imported`

## Phase 2: deterministic intake

### Deliverables

- frontmatter parser
- directive parser
- canonical mapping dictionaries
- fuzzy project resolution
- note validation rules
- initial error handling

### Success criteria

- spoken directives fill approved fields
- defaults remain safe when directives are missing
- unresolved cases are flagged for review
- no LLM is needed for metadata routing basics

## Phase 3: transformation and rendering

### Deliverables

- llama.cpp integration
- schema-defined structured output contract
- Pydantic validators
- Jinja2 prompt renderers
- markdown formatting step

### Success criteria

- imported note becomes a validated final prompt
- structured output is stored
- final rendered markdown is stored
- invalid outputs fail cleanly without silent corruption

## Phase 4: delivery

### Deliverables

- delivery target records
- queue mode
- draft mode
- first CLI target adapter
- first chat target adapter
- delivery state tracking

### Success criteria

- final prompt can be queued
- queued prompts can be dispatched to selected targets
- delivery failures do not destroy prompt artifacts
- delivery state is queryable

## Phase 5: Obsidian write-back

### Deliverables

- note status updates
- generated tags
- processed note folder move
- prompt/result summary append
- optional linkback IDs in frontmatter

### Success criteria

- the user can see processing state from Obsidian
- notes are easy to browse and audit
- prompt history becomes navigable by project and destination

## Phase 6: quality hardening

### Deliverables

- tests for directive parsing
- tests for canonical mappings
- tests for Pydantic validation
- retry policy
- failure dashboard queries
- sample fixtures

### Success criteria

- deterministic components are test-covered
- invalid note shapes fail predictably
- transformations are explainable through stored lineage

## Recommended initial build order

1. Obsidian folder structure and note template
2. watcher import path
3. Postgres schema
4. directive parser
5. canonical project/prompt-type mapping
6. n8n webhook/workflow start
7. llama.cpp structured output
8. Pydantic validation and rendering
9. queue delivery
10. Obsidian write-back

## Recommendation on keyword-driven field fill

For MVP, support it, but keep it narrow and deterministic.

### Recommended rule

Support **a small spoken control vocabulary** that maps to a strict whitelist of fields.

That is not too much. It is valuable and achievable.

### Do not do this yet

- free-form metadata extraction
- broad intent inference for every field
- auto-filling internal system fields from speech
- hidden plugin logic that changes routing without DB trace

### Do this instead

- auto-insert template header
- parse a few approved directive patterns
- canonicalize with dictionaries and fuzzy matching
- retain safe defaults
- flag ambiguous cases for review

## Final build recommendation

The right MVP is not “manual frontmatter only” and not “fully inferred metadata from arbitrary speech.”

The right MVP is the hybrid path:

- **automatic template insertion**
- **limited deterministic spoken field filling**
- **safe defaults**
- **manual correction only when needed**

That is the implementation path this roadmap assumes.
