# PromptForge LLM Prompting Spec

## Purpose

This document defines how PromptForge should prompt the LLM transformation stage.

The goal is not open-ended generation.

The goal is:

- normalize noisy dictated input
- preserve user intent
- map aliases to canonical PromptForge values
- emit schema-safe structured output
- route ambiguity into review instead of hallucination

## Design principles

### 1. Keep the prompt compact

The model already receives schema, control text, and transcript text.

Prompt text should be short and forceful.

Do not waste context on:

- marketing language
- long explanations
- redundant restatements of the schema

### 2. Include explicit normalization rules

The model should not have to infer alias policy.

Prompt must explicitly say that it should canonicalize aliases and misspellings to PromptForge values.

### 3. Include a few-shot block

At least 2 short examples should appear in the prompt profile used for production evaluation.

These examples should demonstrate:

- alias normalization
- review fallback for unresolved project or target
- destination/mode canonicalization

### 4. Prefer conservative behavior

If the model is unsure:

- use `target_identifier = null`
- use `project_slug = "inbox"` when project cannot be resolved confidently
- set `requires_review = true`

### 5. Output only JSON

No prose.
No markdown fence.
No explanatory prefix or suffix.

## Required guardrails

Every PromptForge transformation prompt should include these rules:

- preserve meaning
- use canonical enum values exactly
- canonicalize aliases and spacing variants
- do not invent specific targets, projects, or destinations without evidence
- if target unclear, use `null` and set `requires_review=true`
- if project unclear, use `"inbox"` and set `requires_review=true`
- if mode unclear, default to `"queue"`
- output exactly one JSON object

## Minimum few-shot examples

### Example A: alias normalization

Input:

- `project is thtaxmachine`
- `prompt type is codingcli`
- `destination is cli`
- `target is claude-tax-main`

Output highlights:

- `project_slug = "the-tax-machine"`
- `prompt_type = "coding-cli"`
- `destination = "cli"`
- `requires_review = false`

### Example B: ambiguous project fallback

Input:

- `project is tax thing`
- `destination is queue only`

Output highlights:

- `project_slug = "inbox"`
- `destination = "queue_only"`
- `requires_review = true`

### Example C: obsidian + mode normalization

Input:

- `project is prompt forge`
- `destination is obsidian`
- `mode is auto dispatch`

Output highlights:

- `project_slug = "promptforge"`
- `destination = "obsidian_note"`
- `mode = "auto_dispatch"`

## Separation of concerns

Prompting should not replace deterministic Python rules.

Python should still own:

- validator enforcement
- final canonical acceptance
- queue fallback behavior
- rendering

The prompt should help the model produce better candidate structured output before deterministic validation.

## Acceptance criteria

A good prompt profile should improve these metrics on eval fixtures:

- JSON validity rate
- validator pass rate
- canonical field match rate
- ambiguity handling rate

Canonical field match should be tracked at minimum for:

- `project_slug`
- `prompt_type`
- `destination`
- `target_identifier`
- `mode`
- `requires_review`
