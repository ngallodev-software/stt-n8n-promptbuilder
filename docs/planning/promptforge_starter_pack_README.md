# PromptForge Starter Pack README

## Purpose

This starter pack is the implementation bridge between the design artifacts and the first runnable codebase.

It provides:

- Python package skeletons
- basic configuration files
- startup structure for watcher and services
- a developer-oriented starting point

This is not a full application yet. It is the correct scaffold for building PromptForge in a disciplined way.

## Included components

### `promptforge_watcher`
Filesystem watcher/import boundary.

### `promptforge_services`
Deterministic processing services.

### `.env.example`
Example environment variables.

### `pyproject.toml`
Python dependency and packaging baseline.

### `README.md`
Local developer startup instructions.

## Recommended first implementation milestones

1. complete note parser
2. complete importer DB writes
3. complete directive parser
4. complete preprocess endpoint
5. complete structured validation models
6. complete renderer
7. wire n8n to service endpoints
8. add real delivery adapters

## Important implementation rule

Do not bury important logic in n8n nodes if it should live in Python code.

That applies especially to:
- parsing
- canonicalization
- validation
- rendering
- enum coercion
- error classification
