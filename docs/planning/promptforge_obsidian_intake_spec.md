# PromptForge Obsidian Intake Specification

## Goal

Define the exact intake note format for Obsidian-based voice capture.

The intake note is the human-facing entry artifact. It is not the canonical workflow record. The canonical workflow record begins when the watcher imports the note into Postgres.

## Intake folder

The watcher should process only:

`Inbox/Voice/`

No other folder should trigger automatic processing.

## Note lifecycle

1. Note created in `Inbox/Voice/`
2. Frontmatter template inserted automatically
3. Voice transcription populates note body
4. Optional spoken control directives fill selected frontmatter fields
5. User optionally reviews the note
6. Watcher imports the note
7. Note status changes to imported/processing/processed
8. If processing succeeds, the source draft may be moved out of `Inbox/Voice` after write-back. If processing or delivery fails, the source draft stays in `Inbox/Voice` for retry/review.

## Frontmatter template

Recommended base template:

```yaml
---
pf_version: 1
capture_type: voice
status: new
created_by: obsidian
project: inbox
destination: queue_only
prompt_type: general
target_type: none
target_identifier: ""
mode: queue
priority: normal
requires_review: false
template_profile: default
source_device: windows-main
watch_eligible: true
imported_at: null
utterance_id: null
prompt_generation_id: null
delivery_status: not_started
tags_generated: []
---
```

## Required fields

- `pf_version`
- `capture_type`
- `status`
- `project`
- `destination`
- `prompt_type`
- `mode`
- `watch_eligible`

## Optional fields

- `target_type`
- `target_identifier`
- `priority`
- `requires_review`
- `template_profile`
- `source_device`
- `imported_at`
- `utterance_id`
- `prompt_generation_id`
- `delivery_status`
- `tags_generated`

## Recommended defaults

- `project: inbox`
- `destination: queue_only`
- `prompt_type: general`
- `mode: queue`
- `priority: normal`
- `requires_review: false`

These defaults ensure the note is still valid even when spoken directives are absent.

## Body structure

Recommended body pattern:

```md
## Control
project is the-tax-machine
prompt type is coding-cli
destination is cli
target is claude-tax-main

## Transcript
figure out why the retry state transitions do not line up with the error policy and prepare a patch plan
```

This structure gives the watcher a deterministic place to look for directives while still allowing natural dictation.

## Simpler variant

If you want lower user friction, allow a compact directive prefix:

```md
project is the-tax-machine prompt type is coding-cli destination is cli target is claude-tax-main

figure out why the retry state transitions do not line up with the error policy and prepare a patch plan
```

The watcher can parse the first line or first sentence block before the main transcript.

## Recommendation on directive filling

The recommended MVP approach is:

- **Auto-insert template always**
- **Auto-fill a small whitelist of fields from spoken directives**
- **Do not require manual field editing for normal use**
- **Allow manual correction when needed**
- **Never try to infer all metadata from free-form speech**

## Approved spoken directive fields

For MVP, only these fields should be auto-filled from spoken directives:

- `project`
- `prompt_type`
- `destination`
- `target_identifier`
- `mode`
- `priority`
- `requires_review`

Do not fill fields like IDs, timestamps, statuses, or internal version markers from speech.

## Suggested spoken grammar

Supported patterns:

- `project is <value>`
- `prompt type is <value>`
- `destination is <value>`
- `target is <value>`
- `mode is <value>`
- `priority is <value>`
- `review is true|false`

Aliases may be supported:

- `project` / `repo` / `workspace`
- `prompt type` / `prompt kind`
- `destination` / `dest`
- `target` / `session`
- `review` / `requires review`

## Deterministic mapping examples

Input phrase:

`project is thtaxmachine`

Deterministic resolution:

- fuzzy match against known projects
- canonical output: `the-tax-machine`

Input phrase:

`prompt type is codingcli`

Deterministic resolution:

- map through alias dictionary
- canonical output: `coding-cli`

## Failure behavior

If spoken directives are not confidently resolvable:

- keep frontmatter defaults
- mark `requires_review: true`
- store parsing warnings in DB
- do not guess beyond configured fuzzy thresholds

## Tag strategy

Tags are optional and secondary.

Recommended generated tags:

- `#pf/voice`
- `#pf/project/the-tax-machine`
- `#pf/destination/cli`
- `#pf/mode/queue`

Use tags for navigation, not as the primary routing contract.

## Import eligibility rules

A note should only be imported when:

- it is inside `Inbox/Voice/`
- `watch_eligible: true`
- `status: new`
- frontmatter parses successfully
- note contains non-empty transcript content

## Suggested Obsidian automation behavior

Use an Obsidian template or plugin automation so that any new note in `Inbox/Voice/` automatically receives the frontmatter header.

That is the right balance for MVP: template insertion is automatic, field filling is partly deterministic, and remaining values are resolved by defaults or rules.
