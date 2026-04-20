# PromptForge Deterministic Processing and LLM Transformation Spec

## Purpose

This document defines what should happen before and after the LLM in the PromptForge MVP.

## Processing pipeline

1. Intake note imported
2. Spoken directives parsed
3. Deterministic preprocessing
4. LLM transformation to structured output
5. Deterministic validation
6. Deterministic rendering/formatting
7. Delivery payload creation

## Deterministic preprocessing goals

Use deterministic code for anything that should be stable, testable, and cheap.

### Preprocessing responsibilities

- parse frontmatter
- extract spoken directives
- normalize whitespace and punctuation
- strip or isolate directive prefix from transcript body
- apply project/user/global term mappings
- apply alias resolution for prompt type and destination
- fuzzy match known project names
- mark unresolved fields for review
- generate normalized transcript input for the LLM

## Recommended preprocessing modules

### 1. frontmatter parser
Read YAML frontmatter and body safely.

### 2. directive parser
Recognize approved spoken directives.

### 3. canonicalization layer
Resolve values like:

- `thtaxmachine` -> `the-tax-machine`
- `codingcli` -> `coding-cli`

### 4. terminology normalizer
Apply approved project and global term dictionaries.

### 5. transcript normalizer
Standardize punctuation, repeated spaces, and obvious speech artifacts.

## Recommended Python libraries

- `python-frontmatter`
- `PyYAML`
- `regex`
- `rapidfuzz`
- `pydantic`
- `jinja2`
- `mdformat`
- `orjson`

Optional later:

- `spacy`

## Suggested directive extraction policy

Only parse whitelisted metadata directives.

Approved fields:

- project
- prompt_type
- destination
- target_identifier
- mode
- priority
- requires_review

Do not parse arbitrary metadata from speech.

## Example preprocessing result

Input note:

```md
## Control
project is thtaxmachine
prompt type is codingcli
destination is cli

## Transcript
um figure out why the retry transitions are weird and write me a patch plan
```

Deterministic output:

- `project = the-tax-machine`
- `prompt_type = coding-cli`
- `destination = cli`
- normalized transcript:
  `figure out why the retry transitions are inconsistent and write a patch plan`

## LLM transformation role

The LLM should do what deterministic code cannot do well:

- disfluency-aware rewrite
- convert rough instructions into high-quality prompt language
- preserve technical terms after deterministic canonicalization
- produce structured output matching a schema
- optionally infer target suggestions when allowed

## LLM output contract

Recommended structured response shape:

```json
{
  "intent": "agent_task",
  "project_slug": "the-tax-machine",
  "prompt_type": "coding-cli",
  "destination": "cli",
  "target_identifier": "claude-tax-main",
  "requires_review": false,
  "final_prompt_markdown": "Investigate the retry transitions and produce a patch plan...",
  "notes": []
}
```

## Deterministic validation

Every LLM output must be validated with Pydantic.

Validation responsibilities:

- required fields exist
- enum values are canonical
- prompt text is non-empty
- project slug is known or review is required
- destination is allowed
- mode is allowed
- unsupported fields are ignored or rejected

## Deterministic rendering

After validation, render the final output using a deterministic template.

Examples:

- chat prompt template
- coding CLI instruction template
- delegation request template
- queue item template
- Obsidian output note template

Use Jinja2 for rendering and mdformat for final markdown normalization.

## Error handling rules

### Preprocessing errors
Examples:

- invalid frontmatter
- empty transcript
- unparseable file
- invalid YAML

Action:

- mark note/import as error
- do not invoke LLM
- write error details to DB

### Validation errors
Examples:

- missing destination
- invalid prompt type
- empty final prompt
- unsupported target mode

Action:

- mark prompt generation as failed
- optionally set `requires_review = true`
- keep all intermediate artifacts

### HTTP contract notes

The HTTP service endpoints that sit on top of this pipeline should keep the same failure semantics:

- `POST /validate` returns `400` with the Pydantic validation detail when structured output is malformed.
- `POST /render` returns `400` with the same validation detail if the structured payload cannot be rendered safely.
- `POST /prepare-delivery` returns `400` for invalid or incomplete structured payloads before any delivery record is created.
- live `claude_session`, `codex_session`, and `chat_session` dispatch remains unsupported in the Python backend until a real transport exists.
- unsupported live dispatch should persist the failed delivery attempt and leave the prompt-generation artifact intact.

### Console backend notes

The console mutation surface should use explicit, validation-first behavior rather than silent fallthrough:

- `/console/dictionary/upsert` is a real upsert endpoint and must reject invalid scope or empty terms before any write.
- `/console/llm/assist` should return a structured `501` stub when the LLM router is disabled or unavailable.
- `/console/settings/secrets` must fail closed with a `503` when secret encryption is not configured.
- `/console/admin/purge-archived-notes` remains an admin-only destructive action and must require the exact confirmation string.
- `/console/deliveries/{id}/retry` and `/console/deliveries/{id}/reroute` become immutable after a terminal delivery state.
- queue-only reroutes may still happen before terminal state is reached.
- session-registry support is currently read/dispatch oriented; there is no public CRUD surface for live session rows yet.

### Soft resolution failures
Examples:

- project match below confidence threshold
- ambiguous target identifier

Action:

- keep defaults
- set `requires_review = true`
- continue only if safe

## Recommendation on metadata filling

The system should not require users to fill frontmatter by hand in normal operation.

The best MVP policy is:

- always auto-insert frontmatter template
- deterministically fill approved fields from spoken directives
- use defaults for everything else
- allow manual edits for exceptional cases
- force review when confidence is low

This is the best balance of usability and reliability.
