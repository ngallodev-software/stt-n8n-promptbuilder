# PromptForge

PromptForge is a local-first voice-to-prompt compiler and router.

It converts structured Obsidian intake notes into deterministic prompt artifacts, delivery records, and optional downstream automation events.

## Related Repositories

- Backend/platform (this repo): `https://github.com/ngallodev-software/stt-n8n-promptbuilder`
- Frontend console: `https://github.com/ngallodev-software/prompt-forge-console`

See [API_COMPAT.md](API_COMPAT.md) for cross-repo API and contract expectations.

## What It Does Today

- Parses Obsidian intake notes from `Inbox/Voice/`.
- Canonicalizes directives and preprocesses transcript text.
- Validates and renders the `agent_task_v1` structured output contract.
- Creates deterministic delivery records.
- Optionally persists watcher imports to Postgres.
- Optionally emits n8n-compatible webhook payloads.
- Writes processed notes back to a processed folder with updated frontmatter.
- Auto-dispatches `obsidian_note` deliveries by writing rendered prompt notes into the vault.
- Ships importable n8n workflow JSON and an import helper script.

## Repository Layout

- `promptforge_services/`: FastAPI endpoints and deterministic pipeline logic.
- `promptforge_watcher/`: Vault watcher, import flow, repository persistence, writeback, webhook helpers.
- `tests/`: Unit tests and fixtures.
- `docs/planning/`: Product/design specs, schema, roadmap, and workflow artifacts.
- `scripts/`: Utilities such as workflow import and local LLM evaluation.

## Quickstart

### 1) Create env and install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

### 2) Run API service

```bash
PYTHONPATH=. uvicorn promptforge_services.api:app --host 0.0.0.0 --port 8090 --reload
```

### 3) Run watcher

```bash
PYTHONPATH=. python3 -m promptforge_watcher
```

### 4) Run tests

```bash
python3 -m pytest -q
```

## Self-Contained Stack

The repo includes a root Docker Compose stack for local development and self-hosting:

- `promptforge-api`
- `promptforge-watcher`
- `promptforge-console`
- `postgres`
- `n8n`

### 1) Configure env

Copy `.env.example` to `.env` and adjust any secrets you want to keep stable:

- `POSTGRES_PASSWORD`
- `N8N_ENCRYPTION_KEY`
- `WEBHOOK_URL`

### 2) Start the stack

```bash
docker compose up -d --build
```

For a developer loop with source bind mounts and API reload:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

### 3) Bootstrap schema and workflows

The helper script creates the vault folders, applies `docs/planning/promptforge_postgres_schema.sql`, and imports the n8n workflows on first boot:

```bash
./scripts/bootstrap_stack.sh
```

If you want to re-run just the database schema migration:

```bash
./scripts/migrate_postgres.sh
```

### 4) Useful endpoints

- API: `http://localhost:8090/health`
- Console: `http://localhost:5173`
- n8n: `http://localhost:5678/`

## API Endpoints

- `GET /health`
- `GET /_healthz`
- `POST /preprocess`
- `POST /validate`
- `POST /render`
- `POST /prepare-delivery`
- `GET /providers/health` for optional LLM provider status

Console integration endpoints:

- `GET /console/bootstrap`
- `POST /console/deliveries/{id}/retry`
- `POST /console/deliveries/{id}/reroute`
- `PATCH /console/deliveries/{id}/status`
- `PATCH /console/rules/{id}`
- `POST /console/dictionary/upsert`
- `POST /console/templates/{id}/activate`
- `POST /console/prompts/{id}/force-review`
- `POST /console/prompts/{id}/clone`
- `PATCH /console/prompts/{id}/priority`
- `PATCH /console/intake/{id}/archive`

## Optional LLM Support

LLM support is scaffolded but disabled by default. The deterministic preprocess, validate, render, and delivery flow remains the baseline path.

Only the Ollama/OpenAI-compatible path is wired for live calls right now. OpenAI and Anthropic remain stubs until their adapters are implemented.

LLM review or inference metadata is stored separately in the `llm_runs` table, with nullable provider, model, latency, token usage, fallback chain, summary, and findings fields so deterministic-only imports stay compatible.

Enable it with environment variables such as:

- `PROMPTFORGE_LLM_ENABLED=true`
- `PROMPTFORGE_LLM_MODE=deterministic_plus_review` or `llm_inference_optional`
- `PROMPTFORGE_LLM_REVIEW_PROVIDER=openai|anthropic|ollama|lmstudio|llamacpp|openai_compatible`
- `PROMPTFORGE_LLM_INFERENCE_PROVIDER=openai|anthropic|ollama|lmstudio|llamacpp|openai_compatible`
- `PROMPTFORGE_LLM_TIMEOUT_SECONDS=30`
- `PROMPTFORGE_LLM_MAX_RETRIES=2`

Provider credentials and models are read from the corresponding OpenAI, Anthropic, or OpenAI-compatible environment variables. If no provider is configured, `/providers/health` still reports the disabled scaffold state.

For Ollama, point the OpenAI-compatible base URL at the local server, for example:

- `PROMPTFORGE_OPENAI_COMPAT_BASE_URL=http://localhost:11434/v1`
- `PROMPTFORGE_OPENAI_COMPAT_MODEL=llama3.1`

If you prefer the native Ollama chat endpoint, use the same model value with a base URL like `http://localhost:11434`; the provider will switch to `/api/chat` automatically.

## Watcher Runtime Behavior

The watcher uses a two-stage flow:

1. Startup catch-up scan for existing `*.md` files in `PROMPTFORGE_WATCH_FOLDER`.
2. Long-running event-driven mode for filesystem create/modify events.

Event handling behavior:

- Debounces per file using `PROMPTFORGE_STABILIZATION_SECONDS`.
- Ignores hidden/temp/editor-artifact files.
- Uses content hash guards to skip unchanged rewrites.
- Persists and/or dispatches only when note remains eligible (`status: new`, `watch_eligible: true`, transcript present, in watch folder).

## Configuration

Main watcher environment variables:

- `PROMPTFORGE_DATABASE_URL` (optional): enable Postgres persistence.
- `PROMPTFORGE_VAULT_PATH` (default: `/vault`): vault root path.
- `PROMPTFORGE_WATCH_FOLDER` (default: `Inbox/Voice`): intake folder.
- `PROMPTFORGE_PROCESSED_FOLDER` (default: `Processed/Voice`): writeback folder.
- `PROMPTFORGE_ERROR_FOLDER` (default: `Processing/Error`): error folder contract.
- `PROMPTFORGE_STABILIZATION_SECONDS` (default: `0.5`): debounce delay.
- `PROMPTFORGE_N8N_WEBHOOK_URL` (default: `http://n8n:5678/webhook/promptforge-intake`): webhook destination.
- `PROMPTFORGE_WEBHOOK_ENABLED` (default: `false`): enable webhook posting.

## n8n Workflow Assets

Importable n8n workflow definitions live in `docs/planning/n8n_workflows/`.

Use:

```bash
./scripts/import_n8n_workflows.sh
```

## Local LLM Evaluation Harness

PromptForge includes an evaluation harness for structured output quality checks.

- Script: `scripts/eval_llamacpp_promptforge.py`
- Cases: `tests/fixtures/llamacpp_eval_cases.jsonl`
- Prompt templates: `tests/fixtures/llamacpp_prompts/`

Example:

```bash
python3 scripts/eval_llamacpp_promptforge.py \
  --prompt-profile compact \
  --limit 1
```

Codex-backed comparison mode is available:

```bash
python3 scripts/eval_llamacpp_promptforge.py \
  --backend codex-exec \
  --prompt-profile compact \
  --limit 1
```

## Ollama Benchmark Suite

For Ollama LAN benchmarking, use the dedicated HTTP benchmark script. It runs warmups, repeated samples, near-context stress cases, and PromptForge-like contract prompts.

Summary output:

```bash
python3 scripts/bench_ollama_promptforge.py \
  --base-url http://localhost:11434 \
  --model llama3.1 \
  --warmups 1 \
  --runs 3
```

Streaming mode:

```bash
python3 scripts/bench_ollama_promptforge.py \
  --base-url http://localhost:11434 \
  --model llama3.1 \
  --stream
```

Chunked synthesis mode:

```bash
python3 scripts/bench_ollama_promptforge.py \
  --base-url http://localhost:11434 \
  --model llama3.1 \
  --chunk-size 2048 \
  --chunk-overlap 256
```

Machine-readable JSON output:

```bash
python3 scripts/bench_ollama_promptforge.py \
  --base-url http://localhost:11434 \
  --model llama3.1 \
  --output-format json
```

You can also adjust the request budget and limit the case set while iterating:

```bash
python3 scripts/bench_ollama_promptforge.py \
  --base-url http://localhost:11434 \
  --model llama3.1 \
  --num-ctx 8192 \
  --limit 2
```

## Planning and Specs

Planning/specification source of truth is under `docs/planning/`, including:

- watcher + services spec
- processing and contract specs
- data model + schema
- roadmap and implementation runbook

## Security Notes

- Do not commit real vault paths, webhook URLs, or database credentials.
- Use environment variables and local `.env` files for secrets.
- Keep sample values in docs/templates only.
