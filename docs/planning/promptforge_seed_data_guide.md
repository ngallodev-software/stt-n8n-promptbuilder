# PromptForge Seed Data Pack Guide

## Purpose

This document explains the production seed data pack and how it maps to the PromptForge MVP artifacts.

The accompanying SQL file provides realistic baseline rows for:

- projects
- rulesets
- rules
- term dictionary entries
- prompt templates
- delivery targets

File:
- `promptforge_seed_data.sql`

---

## What this seed pack is meant to do

The goal is to make a fresh PromptForge database immediately usable for MVP testing.

Instead of starting with an empty schema, the seed pack gives you:

- a safe fallback `inbox` project
- a concrete project example for `the-tax-machine`
- a concrete project example for `promptforge`
- initial cleanup/routing behavior
- starter terminology correction entries
- initial prompt templates
- realistic delivery targets

This makes it much easier to test the watcher, preprocessing, rendering, and delivery flow end to end.

In the live bootstrap path, the seed pack is also applied to an existing database when the operator catalogs are still empty, so the console pages do not depend on a fresh Postgres volume.

---

## Seeded projects

### `inbox`
Use this as the fallback unresolved project when directives or routing cannot be resolved confidently.

Purpose:
- safe default
- review queue fallback
- prevents brittle forced guesses

### `the-tax-machine`
Concrete coding project example.

Purpose:
- test project-specific routing
- test project-specific terminology canonicalization
- test a coding CLI default path

### `promptforge`
Concrete planning/project-docs example.

Purpose:
- test chat-oriented planning prompts
- test a second project with different defaults
- test project-specific target routing

---

## Seeded rulesets

### `global-defaults`
Global behavior that should apply unless a higher scope overrides it.

Examples:
- transcript cleanup defaults
- routing fallback to manual review queue
- markdown formatting normalization

### `the-tax-machine-defaults`
Project-specific behavior for the tax project.

Examples:
- default CLI routing
- project terminology protection
- coding workflow defaults

### `promptforge-defaults`
Project-specific behavior for PromptForge itself.

Examples:
- default chat routing
- planning-oriented destination behavior

---

## Seeded rules

The SQL includes examples of:
- cleanup rules
- routing rules
- formatting rules
- terminology rules

These are still JSON-configured placeholders, not a full rules engine implementation.
That is intentional.

For MVP, they provide:
- realistic stored config
- something for selection logic to load
- a clear path for later engine implementation

The console backend now also exposes durable create/edit endpoints for these records and a ruleset dry-run preview so the frontend can exercise the stored config without a local mock.

---

## Seeded term dictionary entries

The seed pack includes practical speech-to-canonical mappings such as:

- `lama cpp` -> `llama.cpp`
- `n 8 n` -> `n8n`
- `coding cli` -> `coding-cli`
- `thtaxmachine` -> `the-tax-machine`

This gives your deterministic layer immediate testable value.

Recommended use:
- exact replacements first
- fuzzy match second
- review fallback third

---

## Seeded prompt templates

The seed pack loads these template records:

- `coding-cli-default`
- `chat-prompt-default`
- `delegation-default`
- `review-item-default`
- `obsidian-note-summary`
- `tax-machine-coding-cli`

This gives you both:
- global templates
- project-specific override example

That lets you test template precedence:

**project override > global default**

---

## Seeded delivery targets

The pack includes:
- a global manual review queue
- a project-specific Claude session for `the-tax-machine`
- a project-specific Claude session for `promptforge`
- a PromptForge chat queue
- an Obsidian write-back target

This is enough to exercise:
- queue-only routing
- project CLI routing
- planning/chat routing
- note write-back paths

---

## Recommended load order

1. load the schema
2. load the seed data
3. create a few voice intake notes
4. run watcher import
5. run preprocessing
6. run rendering
7. inspect queue/delivery behavior

---

## Suggested first end-to-end tests

### Test 1: tax-machine coding request
Use a note with:
- `project is thtaxmachine`
- `prompt type is codingcli`
- `destination is cli`
- `target is claude-tax-main`

Expected:
- project resolves to `the-tax-machine`
- prompt type resolves to `coding-cli`
- delivery target resolves to tax project Claude session

### Test 2: unresolved project
Use a note with:
- `project is tax thing`
- `prompt type is coding`

Expected:
- project remains unresolved or falls back to `inbox`
- requires review is set
- delivery routes to `manual-review`

### Test 3: PromptForge planning note
Use a note with:
- `project is prompt forge`
- `prompt type is planning`

Expected:
- project resolves to `promptforge`
- destination falls to project default chat path
- rendered output uses planning-appropriate template

---

## Recommendation

Treat the seed pack as:
- starter baseline config
- a testing harness
- a living config example

Do not treat it as final production business logic.
It is the first realistic config set that should help you stand the system up quickly.
