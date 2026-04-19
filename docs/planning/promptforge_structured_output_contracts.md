# PromptForge Structured Output Contracts and Pydantic Models

## Purpose

This document defines the recommended structured output contracts for the PromptForge MVP.

The goals are:

- make LLM output machine-validated
- provide stable downstream contracts
- separate transformation from rendering
- allow multiple output shapes without free-form ambiguity

---

## Contract design principles

1. Every LLM output should map to a named contract.
2. Contracts should be small and explicit.
3. Required fields should stay minimal but meaningful.
4. Downstream systems should never trust raw model text without validation.
5. Final rendering should use validated contracts, not raw responses.

---

## Recommended MVP contracts

### 1. `agent_task_v1`
For CLI or agent-harness work.

### 2. `chat_prompt_v1`
For direct chat-oriented prompting.

### 3. `review_item_v1`
For cases that require manual review or triage.

### 4. `obsidian_note_output_v1`
For writing structured results back into the vault.

---

## Shared enums

Recommended canonical enums:

### destination
- `chat`
- `cli`
- `obsidian_note`
- `queue_only`

### prompt_type
- `general`
- `coding-cli`
- `delegation`
- `planning`
- `review`

### mode
- `draft`
- `queue`
- `auto_dispatch`

---

## Pydantic base models

```python
from pydantic import BaseModel, Field
from typing import Literal

Destination = Literal["chat", "cli", "obsidian_note", "queue_only"]
PromptType = Literal["general", "coding-cli", "delegation", "planning", "review"]
Mode = Literal["draft", "queue", "auto_dispatch"]

class BaseContract(BaseModel):
    contract_name: str
    requires_review: bool = False
    notes: list[str] = Field(default_factory=list)
```

---

## Contract: `agent_task_v1`

### Purpose
Represents a structured task intended for a coding harness or CLI agent target.

```python
class AgentTaskV1(BaseContract):
    contract_name: Literal["agent_task_v1"]
    intent: Literal["agent_task"]
    project_slug: str
    prompt_type: PromptType
    destination: Destination
    target_identifier: str | None = None
    mode: Mode = "queue"
    final_prompt_markdown: str
```

### Validation rules
- `project_slug` must be non-empty
- `final_prompt_markdown` must be non-empty
- `destination` should usually be `cli` or `queue_only`
- if `destination == "cli"` and target is missing, either:
  - fail validation, or
  - coerce to `queue_only` plus `requires_review = true`

Recommended MVP policy:
- require review rather than silently inventing a target

---

## Contract: `chat_prompt_v1`

### Purpose
Represents a polished prompt intended for a chat interface.

```python
class ChatPromptV1(BaseContract):
    contract_name: Literal["chat_prompt_v1"]
    intent: Literal["chat_prompt"]
    project_slug: str
    prompt_type: PromptType
    destination: Destination
    mode: Mode = "draft"
    final_prompt_markdown: str
```

### Typical destination values
- `chat`
- `queue_only`

---

## Contract: `review_item_v1`

### Purpose
Represents a case where the model can summarize intent but the system should not auto-route confidently.

```python
class ReviewItemV1(BaseContract):
    contract_name: Literal["review_item_v1"]
    intent: Literal["review_item"]
    project_slug: str | None = None
    destination: Destination = "queue_only"
    mode: Mode = "queue"
    review_reason: str
    suggested_prompt_markdown: str | None = None
```

### Example use cases
- ambiguous project
- ambiguous target
- invalid destination from source note
- incomplete user request

---

## Contract: `obsidian_note_output_v1`

### Purpose
Represents structured content to write back into Obsidian.

```python
class ObsidianNoteOutputV1(BaseContract):
    contract_name: Literal["obsidian_note_output_v1"]
    intent: Literal["obsidian_note_output"]
    project_slug: str | None = None
    title: str
    body_markdown: str
    tags: list[str] = Field(default_factory=list)
    destination: Destination = "obsidian_note"
    mode: Mode = "draft"
```

---

## Union model

Recommended validation approach:

```python
from typing import Union

PromptForgeContract = Union[
    AgentTaskV1,
    ChatPromptV1,
    ReviewItemV1,
    ObsidianNoteOutputV1,
]
```

You can validate by inspecting `contract_name` first, then dispatching to the correct model.

---

## Canonical validation behaviors

### Fail hard
Use validation failure when:
- required text field is empty
- enum value is unsupported
- contract name is unknown
- schema shape is missing required fields

### Coerce safely
Allow controlled coercion when:
- `codingcli` -> `coding-cli`
- `CLI` -> `cli`
- `queued` -> `queue`

### Mark for review
Use review when:
- project is unresolved
- target is absent for a CLI task
- output is structurally valid but routing is uncertain

---

## Recommended DB storage shape

Store:
- raw model output in `transcript_revisions` as `llm_structured_source`
- validated normalized JSON in `prompt_generations.structured_output_json`

That way you keep both:
- what the model actually produced
- the canonical validated form you trust downstream

---

## Example validated payload: `agent_task_v1`

```json
{
  "contract_name": "agent_task_v1",
  "intent": "agent_task",
  "project_slug": "the-tax-machine",
  "prompt_type": "coding-cli",
  "destination": "cli",
  "target_identifier": "claude-tax-main",
  "mode": "queue",
  "final_prompt_markdown": "Investigate why the retry state transitions are inconsistent with the review and error policy. Produce a patch plan with affected files, state-machine changes, validation impacts, and recommended tests.",
  "requires_review": false,
  "notes": []
}
```

---

## Example validated payload: `review_item_v1`

```json
{
  "contract_name": "review_item_v1",
  "intent": "review_item",
  "project_slug": null,
  "destination": "queue_only",
  "mode": "queue",
  "review_reason": "Project could not be resolved confidently from directive: tax thing",
  "suggested_prompt_markdown": "Compare the retry states to the review rules and prepare a change list.",
  "requires_review": true,
  "notes": [
    "Awaiting manual project assignment."
  ]
}
```

---

## Recommendation

Start with these four contracts only.

Do not create many contract variants until you have:
- stable watcher behavior
- stable preprocess and validation flow
- real usage data about which destinations and outputs matter most
