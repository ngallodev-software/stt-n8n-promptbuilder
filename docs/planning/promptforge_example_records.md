# PromptForge Example Records and End-to-End Walkthrough

## Purpose

This document gives production-grade example records for the PromptForge MVP so implementation and testing can target a concrete, shared model.

The examples here cover:

- normal successful import and queue flow
- ambiguous project/directive resolution
- validation failure
- delivery failure after successful prompt rendering

## Scenario A: successful coding CLI request

### Source note path

`Inbox/Voice/2026-04-14 retry-state-plan.md`

### Original note content

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

---

## Deterministic directive resolution

### Raw directives

```text
project is thtaxmachine
prompt type is codingcli
destination is cli
target is claude-tax-main
```

### Canonicalized directives

```json
{
  "project": "the-tax-machine",
  "prompt_type": "coding-cli",
  "destination": "cli",
  "target_identifier": "claude-tax-main"
}
```

### Reasoning used by the deterministic layer

- `thtaxmachine` fuzzy-matched to known project slug `the-tax-machine`
- `codingcli` mapped via alias dictionary to `coding-cli`
- `cli` already matched an allowed destination enum
- `claude-tax-main` matched a known delivery target identifier directly

---

## Example records

### `projects`

```json
{
  "id": "11111111-1111-4111-8111-111111111111",
  "slug": "the-tax-machine",
  "name": "the-tax-machine",
  "description": "Tax-return assembly portfolio project",
  "vault_path": "/vault/Projects/the-tax-machine",
  "git_repo_url": "git@github.com:example/the-tax-machine.git",
  "default_prompt_type": "coding-cli",
  "default_destination": "cli",
  "metadata_json": {
    "has_diagrams": true,
    "default_target_identifier": "claude-tax-main"
  }
}
```

### `intake_notes`

```json
{
  "id": "22222222-2222-4222-8222-222222222222",
  "vault_path": "/vault",
  "note_relative_path": "Inbox/Voice/2026-04-14 retry-state-plan.md",
  "note_title": "2026-04-14 retry-state-plan",
  "frontmatter_json": {
    "pf_version": 1,
    "capture_type": "voice",
    "project": "inbox",
    "destination": "queue_only",
    "prompt_type": "general",
    "watch_eligible": true
  },
  "body_markdown": "## Control\nproject is thtaxmachine\nprompt type is codingcli\ndestination is cli\ntarget is claude-tax-main\n\n## Transcript\num figure out why the retry state transitions do not line up with the review and error policy and prepare a patch plan",
  "project_id": "11111111-1111-4111-8111-111111111111",
  "status": "imported",
  "source_device": "windows-main"
}
```

### `utterances`

```json
{
  "id": "33333333-3333-4333-8333-333333333333",
  "intake_note_id": "22222222-2222-4222-8222-222222222222",
  "raw_text": "um figure out why the retry state transitions do not line up with the review and error policy and prepare a patch plan",
  "directive_text": "project is thtaxmachine\nprompt type is codingcli\ndestination is cli\ntarget is claude-tax-main",
  "project_id": "11111111-1111-4111-8111-111111111111",
  "scope": "project",
  "capture_type": "voice"
}
```

### `transcript_revisions`

#### raw

```json
{
  "revision_kind": "raw",
  "producer_type": "watcher",
  "producer_name": "obsidian-importer",
  "content": "um figure out why the retry state transitions do not line up with the review and error policy and prepare a patch plan",
  "metadata_json": {
    "source_section": "Transcript"
  }
}
```

#### directive_stripped

```json
{
  "revision_kind": "directive_stripped",
  "producer_type": "python",
  "producer_name": "promptforge-normalize",
  "content": "um figure out why the retry state transitions do not line up with the review and error policy and prepare a patch plan",
  "metadata_json": {
    "removed_directive_lines": 4
  }
}
```

#### deterministic_preprocessed

```json
{
  "revision_kind": "deterministic_preprocessed",
  "producer_type": "python",
  "producer_name": "promptforge-normalize",
  "content": "Figure out why the retry state transitions do not line up with the review and error policy, and prepare a patch plan.",
  "metadata_json": {
    "filler_removed": true,
    "terminology_applied": [],
    "project_slug": "the-tax-machine",
    "prompt_type": "coding-cli"
  }
}
```

#### llm_cleaned

```json
{
  "revision_kind": "llm_cleaned",
  "producer_type": "llm",
  "producer_name": "llama.cpp",
  "content": "Investigate why the retry state transitions are inconsistent with the review and error policy, then produce a patch plan.",
  "metadata_json": {
    "model": "llama3.1-local",
    "temperature": 0.2
  }
}
```

#### llm_structured_source

```json
{
  "revision_kind": "llm_structured_source",
  "producer_type": "llm",
  "producer_name": "llama.cpp",
  "content": "{"intent":"agent_task","project_slug":"the-tax-machine","prompt_type":"coding-cli","destination":"cli","target_identifier":"claude-tax-main","requires_review":false,"final_prompt_markdown":"Investigate why the retry state transitions are inconsistent with the review and error policy. Produce a patch plan with affected files, state-machine changes, validation impacts, and recommended tests.","notes":[]}",
  "metadata_json": {
    "contract_name": "promptforge_agent_task_v1"
  }
}
```

#### final_rendered_prompt

```json
{
  "revision_kind": "final_rendered_prompt",
  "producer_type": "renderer",
  "producer_name": "promptforge-render",
  "content": "Project: the-tax-machine\nTarget: claude-tax-main\nMode: queue\n\nTask:\nInvestigate why the retry state transitions are inconsistent with the review and error policy. Produce a patch plan with affected files, state-machine changes, validation impacts, and recommended tests.",
  "metadata_json": {
    "template_name": "coding-cli-default",
    "template_version": 1
  }
}
```

### `prompt_generations`

```json
{
  "id": "44444444-4444-4444-8444-444444444444",
  "utterance_id": "33333333-3333-4333-8333-333333333333",
  "project_id": "11111111-1111-4111-8111-111111111111",
  "prompt_type": "coding-cli",
  "selected_ruleset_id": "55555555-5555-4555-8555-555555555555",
  "selected_template_id": "66666666-6666-4666-8666-666666666666",
  "structured_output_json": {
    "intent": "agent_task",
    "project_slug": "the-tax-machine",
    "prompt_type": "coding-cli",
    "destination": "cli",
    "target_identifier": "claude-tax-main",
    "requires_review": false,
    "final_prompt_markdown": "Investigate why the retry state transitions are inconsistent with the review and error policy. Produce a patch plan with affected files, state-machine changes, validation impacts, and recommended tests.",
    "notes": []
  },
  "final_prompt_markdown": "Project: the-tax-machine\nTarget: claude-tax-main\nMode: queue\n\nTask:\nInvestigate why the retry state transitions are inconsistent with the review and error policy. Produce a patch plan with affected files, state-machine changes, validation impacts, and recommended tests.",
  "requires_review": false,
  "status": "rendered"
}
```

### `llm_runs`

```json
{
  "id": "55555555-5555-4555-8555-555555555556",
  "utterance_id": "33333333-3333-4333-8333-333333333333",
  "prompt_generation_id": "44444444-4444-4444-8444-444444444444",
  "provider_name": "openai",
  "model_name": "gpt-4.1-mini",
  "mode": "review",
  "latency_ms": 842,
  "token_usage_json": {
    "input_tokens": 1832,
    "output_tokens": 214,
    "total_tokens": 2046
  },
  "fallback_chain_json": [
    "openai",
    "anthropic"
  ],
  "summary": "The prompt is structurally valid and the retry-state policy looks consistent with the requested patch plan.",
  "findings_json": {
    "findings": [
      {
        "severity": "low",
        "message": "No blocking issues found in the deterministic transition wording."
      }
    ]
  },
  "raw_response_json": {
    "provider": "openai",
    "id": "resp-123",
    "status": "success"
  }
}
```

### `delivery_targets`

```json
{
  "id": "77777777-7777-4777-8777-777777777777",
  "name": "Claude tax main",
  "target_type": "claude_session",
  "target_identifier": "claude-tax-main",
  "scope": "project",
  "project_id": "11111111-1111-4111-8111-111111111111",
  "is_default": true,
  "is_auto_dispatch_safe": false,
  "config_json": {
    "adapter": "claude_cli",
    "session_hint": "tax-main",
    "working_dir": "/srv/repos/the-tax-machine"
  }
}
```

### `deliveries`

```json
{
  "id": "88888888-8888-4888-8888-888888888888",
  "prompt_generation_id": "44444444-4444-4444-8444-444444444444",
  "delivery_target_id": "77777777-7777-4777-8777-777777777777",
  "destination": "cli",
  "target_type": "claude_session",
  "target_identifier": "claude-tax-main",
  "mode": "queue",
  "status": "queued",
  "priority": "normal",
  "queued_at": "2026-04-14T20:13:14Z"
}
```

### `processing_runs`

```json
{
  "id": "99999999-9999-4999-8999-999999999999",
  "utterance_id": "33333333-3333-4333-8333-333333333333",
  "workflow_name": "promptforge-intake-v1",
  "status": "completed",
  "started_at": "2026-04-14T20:12:55Z",
  "ended_at": "2026-04-14T20:13:14Z",
  "trace_json": {
    "steps": [
      "load_context",
      "deterministic_preprocess",
      "llm_transform",
      "structured_validate",
      "render_prompt",
      "create_delivery"
    ]
  }
}
```

---

## Scenario B: ambiguous project resolution

### Input note body

```md
## Control
project is tax thing
prompt type is coding
destination is cli

## Transcript
compare the retry states to the review rules and prepare a change list
```

### Deterministic outcome

The watcher should not silently guess a project when the confidence score is below threshold.

### Expected canonical handling

```json
{
  "resolved_project": "inbox",
  "requires_review": true,
  "warnings": [
    "project_match_below_threshold"
  ]
}
```

### Expected prompt generation record fragment

```json
{
  "prompt_type": "coding-cli",
  "requires_review": true,
  "status": "rendered",
  "structured_output_json": {
    "intent": "agent_task",
    "project_slug": "inbox",
    "prompt_type": "coding-cli",
    "destination": "cli",
    "target_identifier": "",
    "requires_review": true,
    "notes": [
      "Project could not be resolved confidently from directive: tax thing"
    ]
  }
}
```

### Expected delivery behavior

Because no valid target is selected, delivery may either:

- remain uncreated and route to review, or
- create a `queue_only` delivery for later manual routing

Recommended MVP behavior:

```json
{
  "destination": "queue_only",
  "target_type": "generic_queue",
  "target_identifier": "manual-review",
  "mode": "queue",
  "status": "queued"
}
```

---

## Scenario C: structured output validation failure

### Failure example

The LLM returns:

```json
{
  "intent": "agent_task",
  "project_slug": "the-tax-machine",
  "prompt_type": "coding-cli",
  "destination": "cli",
  "final_prompt_markdown": ""
}
```

### Why this fails

- `final_prompt_markdown` is empty
- target resolution may also be incomplete

### Expected handling

#### `prompt_generations`

```json
{
  "status": "failed",
  "requires_review": true,
  "error_text": "Validation failed: final_prompt_markdown must be non-empty"
}
```

#### `processing_runs`

```json
{
  "status": "failed",
  "error_stage": "structured_validating"
}
```

#### Important rule

All prior revisions remain stored. The system does not discard the raw or cleaned text just because the structured output is invalid.

---

## Scenario D: delivery failure after successful prompt rendering

### Preconditions

- prompt generation rendered successfully
- delivery target exists
- CLI adapter cannot reach target session

### Expected state

#### `prompt_generations`

```json
{
  "status": "rendered",
  "requires_review": false
}
```

#### `deliveries`

```json
{
  "mode": "queue",
  "status": "failed",
  "error_text": "Target session unavailable: claude-tax-main"
}
```

### Important rule

Prompt rendering success and delivery success are separate. A failed delivery must not roll back or erase the prompt artifact.

---

## Example note write-back after successful processing

```yaml
---
pf_version: 1
capture_type: voice
status: processed
created_by: obsidian
project: the-tax-machine
destination: cli
prompt_type: coding-cli
target_type: claude_session
target_identifier: claude-tax-main
mode: queue
priority: normal
requires_review: false
template_profile: default
source_device: windows-main
watch_eligible: false
imported_at: 2026-04-14T20:11:03Z
utterance_id: 33333333-3333-4333-8333-333333333333
prompt_generation_id: 44444444-4444-4444-8444-444444444444
delivery_status: queued
tags_generated:
  - pf/voice
  - pf/project/the-tax-machine
  - pf/destination/cli
  - pf/mode/queue
---
```

---

## Example note write-back for review-required case

```yaml
---
pf_version: 1
capture_type: voice
status: processed
created_by: obsidian
project: inbox
destination: queue_only
prompt_type: coding-cli
target_type: generic_queue
target_identifier: manual-review
mode: queue
priority: normal
requires_review: true
template_profile: default
source_device: windows-main
watch_eligible: false
imported_at: 2026-04-14T20:22:10Z
utterance_id: aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
prompt_generation_id: bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb
delivery_status: queued
tags_generated:
  - pf/voice
  - pf/review-required
  - pf/destination/queue-only
---
```

## Recommendation

Use this file as your seed fixture source when building:

- watcher import tests
- directive parser tests
- canonicalization tests
- structured output validator tests
- renderer tests
- delivery error handling tests
