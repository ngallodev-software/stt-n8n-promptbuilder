---
phase: 2
status: active
---

# Cavekit Overview — PromptForge Phase 2 Simplification

## What PromptForge Is

A local-first deterministic prompt compiler/router. It watches an Obsidian vault for structured notes, parses them, compiles prompt output, and queues delivery for operator dispatch.

## What PromptForge Is Not

- Not a platform
- Not a multi-user system
- Not a workflow engine (n8n does not own workflow)
- Not network-safe without explicit operator hardening
- Not an observability stack
- Not an LLM-first system (LLM is explicit opt-in only)

## Canonical Owners

| Concern | Owner |
|---------|-------|
| Workflow | Python only |
| Canonical truth | Postgres only |
| Intake surface | Obsidian (notes in, output written back) |
| Outbound sidecar | n8n optional, reactive only |
| Operator control | Console (narrow: queue/review, delivery ops, settings) |

## Phase 2 Goal

Remove architectural drag. Tighten ownership. Simplify product surface. Make the system smaller, truer, and easier to operate than phase 1.

## Domain Kits

| Domain | File | Summary |
|--------|------|---------|
| Architecture & Ownership | cavekit-architecture.md | Boundaries, runtime ownership, what gets deleted |
| Data Model | cavekit-data-model.md | Append-only delivery attempts, schema simplification |
| Console | cavekit-console.md | Route cuts, bootstrap reduction, narrow operator surface |
| Intake & Writeback | cavekit-intake-writeback.md | Strict note contract, archive semantics, writeback rules |
| Ops Baseline | cavekit-ops-baseline.md | Localhost-only, backup/restore, startup docs |

## Cross-Cutting Constraints (apply to all kits)

- Single-user only. No auth, no roles, no role headers.
- Local-only runtime. Bind localhost. Not safe for network exposure.
- Python is sole workflow owner. n8n reacts only.
- Postgres is sole canonical truth.
- No auto-delivery. All delivery requires explicit operator dispatch.
- LLM is explicit opt-in only, never default path.
- Deletion preferred over deferral where migration risk is low.
