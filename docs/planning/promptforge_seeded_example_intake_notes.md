# PromptForge Seeded Example Intake Notes

## Purpose

This file provides example input notes that align with the seeded projects, templates, targets, and term dictionary.

Use these examples to test the watcher and end-to-end pipeline.

---

## Example 1: the-tax-machine coding request

```md
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

## Control
project is thtaxmachine
prompt type is codingcli
destination is cli
target is claude-tax-main

## Transcript
um figure out why the retry state transitions do not line up with the review and error policy and prepare a patch plan
```

Expected:
- project -> `the-tax-machine`
- prompt_type -> `coding-cli`
- target -> `claude-tax-main`
- template -> project override `tax-machine-coding-cli`

---

## Example 2: unresolved review item

```md
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

## Control
project is tax thing
prompt type is coding

## Transcript
compare the retry states to the review rules and prepare a change list
```

Expected:
- project unresolved
- route to review/manual queue
- `requires_review = true`

---

## Example 3: PromptForge planning note

```md
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

## Control
project is prompt forge
prompt type is planning

## Transcript
write a clean implementation plan for the watcher importer and the preprocess endpoint and note where the state transitions should be persisted
```

Expected:
- project -> `promptforge`
- destination -> project default chat
- target -> `claude-promptforge-main` or project default chat queue depending on rule path
