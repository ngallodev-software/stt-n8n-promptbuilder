# Repository Guidelines

## Project Structure & Module Organization
This repository is a thin Python scaffold plus planning artifacts. Edit runnable code in `promptforge_services/` and `promptforge_watcher/`. `promptforge_services/api.py` exposes the FastAPI endpoints, while `promptforge_services/models.py` holds shared Pydantic contracts such as `AgentTaskV1`. `promptforge_watcher/` contains the filesystem watcher entrypoint and env-backed config.

Use `docs/planning/` for specifications, SQL schema and seed data, the MVP Docker Compose file, and the archived starter pack. Treat those documents as the design source of truth; when code behavior changes, update the matching spec in the same change.

## Build, Test, and Development Commands
Create a virtual environment with `python3 -m venv .venv && source .venv/bin/activate`.

Run the API from the repo root with `PYTHONPATH=. uvicorn promptforge_services.api:app --host 0.0.0.0 --port 8090 --reload`.

Run the watcher with `PYTHONPATH=. python3 -m promptforge_watcher`.

Use `python3 -m compileall promptforge_services promptforge_watcher` for a quick syntax check. For local stack work, use `docker compose -f docs/planning/promptforge_docker_compose_mvp.yml up`.

Dependency versions are documented in `docs/planning/pyproject.toml`; keep new packages aligned there until packaging metadata is moved to the repo root.

## Coding Style & Naming Conventions
Target Python 3.11+ and use 4-space indentation. Keep modules `snake_case`, classes `PascalCase`, and constants/env vars `UPPER_SNAKE_CASE`. Prefer explicit type hints on new functions and Pydantic models for request, response, and config shapes.

Version external contracts deliberately, following the existing `*V1` naming pattern. Keep parsing, validation, and rendering logic in Python rather than hiding it in n8n workflow steps.

## Testing Guidelines
There is no dedicated `tests/` package yet. Add new tests under a root `tests/` directory using `pytest`, with file names like `test_api.py` or `test_watcher_config.py`.

At minimum, validate syntax with `compileall` and smoke-test `/health`, `/preprocess`, `/validate`, and `/render` after API changes.

## Commit & Pull Request Guidelines
This snapshot does not include local Git history, so use short imperative commit subjects; `feat: add note parser` and `fix: harden webhook config` fit the current style.

PRs should describe the behavior change, link the affected planning doc under `docs/planning/`, list verification commands, and include example payloads or logs when contracts, schemas, or watcher behavior change. Never commit real vault paths, webhook URLs, or database secrets; use `docs/planning/.env.example` as the template.
