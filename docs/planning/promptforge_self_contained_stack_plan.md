# PromptForge Self-Contained Stack Plan (PromptForge + n8n + Postgres)

## Goal

Provide a self-contained, one-command local stack that includes:

- PromptForge API service
- PromptForge watcher
- Postgres (PromptForge schema)
- n8n

Target users:

- Developers (local build/test/integration)
- Advanced end users/self-hosters

## Should This Live In Repo?

Yes. Keeping stack assets in this repo makes onboarding and reproducible integration testing easier.

Recommended approach:

- Keep current MVP compose in `docs/planning/` as historical reference.
- Add production-ready dev/self-host profile at repo root (`docker-compose.yml` + env template + bootstrap scripts).

## Proposed Stack Topology

Services:

1. `promptforge-api`
2. `promptforge-watcher`
3. `postgres`
4. `n8n`

Optional utility services (future):

- `pgadmin` (dev profile)
- `ollama` or `llama.cpp-server` (LLM profile)

Networks/volumes:

- Shared internal Docker network for service-to-service traffic.
- Persistent named volumes for Postgres and n8n data.
- Bind mount for Obsidian vault path to watcher container.

## Compose/Env Design

## 1) Root compose files

- `docker-compose.yml`: base stack
- `docker-compose.dev.yml`: optional overrides (reload, debug, extra tools)
- `docker-compose.llm.yml`: optional local LLM endpoints (future)

## 2) Environment templates

- `.env.example`: all required variables with safe defaults
- `.env.n8n.example` (optional split)

## 3) Bootstrapping scripts

- `scripts/bootstrap_stack.sh`
- `scripts/migrate_postgres.sh`
- `scripts/import_n8n_workflows.sh` (already exists; integrate into bootstrap)

## Database + Migrations

- Use `docs/planning/promptforge_postgres_schema.sql` during bootstrap.
- Add idempotent migration runner strategy (simple SQL version table or lightweight migration tool).

## n8n Integration

- Start n8n with Postgres backing store.
- Auto-import PromptForge workflows on first boot (scripted, idempotent).
- Configure n8n webhook endpoint to receive PromptForge events.

## PromptForge Containerization

- Create production-focused Dockerfile for API.
- Create watcher image or shared image with watcher entrypoint.
- Healthchecks:
  - API `/health`
  - Postgres readiness
  - n8n health endpoint

## Developer Experience

One-command startup:

```bash
docker compose up -d --build
```

Recommended helper commands:

- `make up`
- `make down`
- `make logs`
- `make test`
- `make import-workflows`

## Security + Secrets

- No hardcoded secrets in compose.
- Keep credentials in `.env` (ignored by git).
- Provide generated secret guidance for n8n encryption key and DB password.

## Rollout Plan

1. Add root compose and env templates.
2. Add Dockerfiles and service entrypoints.
3. Add Postgres bootstrap/migration script.
4. Add n8n bootstrap + workflow import flow.
5. Add README quickstart for self-contained stack.
6. Add CI smoke test (`docker compose config`, container health checks, minimal end-to-end import).

## Acceptance Criteria

- Fresh clone -> `.env` setup -> `docker compose up` yields running API, watcher, Postgres, n8n.
- Watcher can ingest seeded note and persist to Postgres.
- Webhook flow reaches n8n endpoint.
- n8n workflows import successfully.
- Stack can be torn down/restarted without data loss (volumes persist).
