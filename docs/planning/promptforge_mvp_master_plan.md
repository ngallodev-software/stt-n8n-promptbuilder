# PromptForge MVP Master Plan

## Purpose

PromptForge is a local-first voice-to-prompt compiler and router.

For the MVP, the recommended architecture is:

**Obsidian-first capture → Python watcher intake → Postgres persistence → n8n orchestration → deterministic preprocessing → llama.cpp transformation → deterministic validation/rendering → queued or direct delivery to chat/CLI targets**

This plan intentionally avoids building a custom Windows capture application in phase 1.

## MVP decision

The recommended MVP stack is:

- **Capture surface:** Obsidian on the main Windows PC
- **Vault location:** Debian 12 R630-hosted vault storage
- **Workflow orchestration:** n8n in Docker
- **Database:** Postgres in a separate Docker container
- **Deterministic rule engine:** Python service/scripts
- **Local model execution:** llama.cpp on local hardware
- **Human-readable workspace:** Obsidian
- **System of record:** Postgres

## Architectural principles

1. **Obsidian is the intake console, not the workflow engine.**
2. **Postgres is the canonical source of truth.**
3. **Raw captured text is immutable.**
4. **Each transformation stage is append-only and versioned.**
5. **LLM output is never trusted without deterministic validation.**
6. **Delivery state is tracked separately from prompt generation.**

## End-to-end flow

1. User creates a new note in `Inbox/Voice/`.
2. A note template automatically inserts standardized frontmatter.
3. User speaks a short directive prefix and then the body content.
4. Obsidian/plugin transcribes into the note.
5. Python watcher detects a new eligible note.
6. Watcher parses frontmatter, note body, and deterministic spoken directives.
7. Watcher creates intake records in Postgres.
8. Watcher triggers n8n workflow.
9. n8n resolves project, template, and routing context.
10. Python deterministic preprocessing normalizes text and metadata.
11. llama.cpp rewrites/transforms the note into structured prompt output.
12. Python validates, renders, and formats final prompt payload.
13. Delivery record is created and queued or dispatched.
14. Status and artifact links are written back to Postgres.
15. Optional: on successful processing, note is updated in Obsidian with processing metadata and moved out of `Inbox/Voice` into a processed folder. Failed runs keep the source draft in place.

## Why this MVP is strong

This approach:

- removes the need for a custom Windows app
- uses existing tools the user already wants in the workflow
- keeps notes human-readable from the beginning
- allows deterministic metadata extraction before LLM use
- preserves every stage for auditability and tuning
- supports future expansion to multiple destinations and agent sessions

## Main components

### 1. Obsidian capture layer

Responsibilities:

- create voice intake notes
- auto-apply voice note frontmatter template
- hold raw captured/transcribed text
- provide lightweight human review when needed

### 2. Python watcher/intake service

Responsibilities:

- monitor `Inbox/Voice/`
- parse frontmatter and markdown body
- extract spoken control directives
- apply initial deterministic normalization
- create canonical DB records
- invoke n8n workflow

### 3. Postgres

Responsibilities:

- store note lineage
- store transcription revisions
- store templates, rulesets, projects, and term dictionaries
- store final prompts and delivery records
- store processing state and audit trace

### 4. n8n

Responsibilities:

- orchestrate workflow stages
- trigger transformer and renderer steps
- manage retries and error paths
- queue or dispatch to chat/CLI targets
- integrate future notification and dashboard actions

### 5. Python deterministic processors

Responsibilities:

- preprocessing
- directive parsing
- terminology normalization
- schema validation
- output rendering
- markdown cleanup
- final delivery payload construction

### 6. llama.cpp

Responsibilities:

- disfluency-aware rewrite
- prompt transformation
- structured output generation
- optional target suggestion when routing is ambiguous

## Recommended delivery modes

### Draft mode
Generate cleaned output and final prompt but do not dispatch.

### Queue mode
Generate final prompt and place it into a delivery queue for a selected target.

### Auto-dispatch mode
Generate final prompt and immediately deliver to a configured target session.

For MVP, default to **queue mode** unless the user explicitly marks a target as safe for auto-dispatch.

## Recommended processing folders

Inside the vault:

- `Inbox/Voice/`
- `Processing/Voice/`
- `Processed/Voice/`
- `Archive/Voice/`
- `Projects/<project>/Voice Logs/`

The watcher should only act on `Inbox/Voice/`.

## Initial target classes

PromptForge MVP should support these destination classes:

- `chat`
- `cli`
- `obsidian_note`
- `queue_only`

For `cli`, the next layer can further resolve into:

- Claude CLI session
- Codex harness session
- future terminal agent target

## MVP exclusions

These should be excluded from phase 1:

- full autonomous project inference from arbitrary speech
- broad RAG over all project documents
- multi-user support
- streaming word-by-word terminal injection
- plugin-dependent hidden workflow logic
- bidirectional sync that treats Obsidian as the system of record

## Recommendation on spoken metadata filling

Do **not** make users fill every frontmatter field by hand.

Also do **not** try to extract every possible field from free speech.

The best MVP approach is a **hybrid model**:

- auto-insert a standardized frontmatter template with safe defaults
- deterministically parse a limited set of spoken control directives
- fill only a small approved set of fields from those directives
- let everything else remain defaulted or be resolved by rules
- allow optional manual correction in Obsidian before processing

This gives the system speed without making metadata extraction brittle.

## Recommended directive strategy

Support a small spoken directive grammar such as:

- `project is the-tax-machine`
- `prompt type is coding-cli`
- `destination is cli`
- `target is claude-tax-main`
- `mode is queue`
- `priority is high`

These directives should map only to approved frontmatter fields.

Everything else should remain in the note body.

## Final recommendation

Proceed with an Obsidian-first MVP using frontmatter templates, deterministic directive parsing, Postgres-backed lineage, n8n orchestration, Python preprocessing/rendering, and llama.cpp transformation.
