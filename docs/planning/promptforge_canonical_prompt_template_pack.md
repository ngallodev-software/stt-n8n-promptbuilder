# PromptForge Canonical Prompt Template Pack

## Purpose

This document defines the recommended first-pass prompt templates for the PromptForge MVP.

Templates should be deterministic, stored in the database, and selected after structured output validation.

The model should produce validated structured content.
The renderer should turn that structured content into final destination-ready text.

---

## Template design principles

1. Templates should be small and readable.
2. Templates should reflect destination requirements.
3. Rendering should not invent information missing from validated contracts.
4. Project and target metadata should appear when useful, not everywhere.
5. CLI templates should be direct and action-oriented.

---

## Template: `coding-cli-default`

### Use case
A task going to a CLI agent or coding harness.

### Inputs
- `project_slug`
- `target_identifier`
- `mode`
- `final_prompt_markdown`

### Jinja2 template

```jinja2
Project: {{ project_slug }}
Target: {{ target_identifier or "unassigned" }}
Mode: {{ mode }}

Task:
{{ final_prompt_markdown }}
```

### Notes
- keep it terse
- good default for Claude CLI / codex-job style workflows
- easily wrapped later in adapter-specific envelopes

---

## Template: `chat-prompt-default`

### Use case
A polished prompt intended for a chat interface.

### Inputs
- `project_slug`
- `prompt_type`
- `final_prompt_markdown`

### Jinja2 template

```jinja2
Project context: {{ project_slug }}
Prompt type: {{ prompt_type }}

{{ final_prompt_markdown }}
```

### Notes
- useful when you want some context preserved
- can later be simplified if project context proves noisy

---

## Template: `delegation-default`

### Use case
A prompt intended to hand work to another agent/session.

### Inputs
- `project_slug`
- `target_identifier`
- `final_prompt_markdown`

### Jinja2 template

```jinja2
Delegate the following task for project {{ project_slug }}.

Destination target: {{ target_identifier or "unassigned" }}

Task:
{{ final_prompt_markdown }}
```

---

## Template: `review-item-default`

### Use case
Manual review queue entry.

### Inputs
- `review_reason`
- `suggested_prompt_markdown`
- `notes`

### Jinja2 template

```jinja2
Review required.

Reason:
{{ review_reason }}

Suggested prompt:
{{ suggested_prompt_markdown or "None generated." }}

Notes:
{% if notes %}
{% for note in notes -%}
- {{ note }}
{% endfor %}
{% else %}
- No additional notes.
{% endif %}
```

---

## Template: `obsidian-note-summary`

### Use case
Write-back summary to a processed note or review note.

### Inputs
- `project_slug`
- `destination`
- `target_identifier`
- `requires_review`
- `final_prompt_markdown`

### Jinja2 template

```jinja2
## PromptForge Summary

- Project: {{ project_slug or "unresolved" }}
- Destination: {{ destination }}
- Target: {{ target_identifier or "unassigned" }}
- Requires review: {{ requires_review }}

## Final Prompt

{{ final_prompt_markdown }}
```

---

## Recommended DB seed examples

### coding-cli-default
- `name`: `coding-cli-default`
- `scope`: `global`
- `prompt_type`: `coding-cli`
- `output_contract_name`: `agent_task_v1`

### chat-prompt-default
- `name`: `chat-prompt-default`
- `scope`: `global`
- `prompt_type`: `general`
- `output_contract_name`: `chat_prompt_v1`

### delegation-default
- `name`: `delegation-default`
- `scope`: `global`
- `prompt_type`: `delegation`
- `output_contract_name`: `agent_task_v1`

### review-item-default
- `name`: `review-item-default`
- `scope`: `global`
- `prompt_type`: `review`
- `output_contract_name`: `review_item_v1`

---

## Recommendation

Use these as your first production seed templates.

Do not over-template early.
The real win is:
- good deterministic validation
- clean structured outputs
- stable delivery lifecycle

Templates should stay simple until real usage proves where more specialization is needed.
