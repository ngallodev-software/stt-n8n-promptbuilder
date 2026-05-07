# PromptForge Architecture and Complexity Audit

**Date**: 2026-04-28  
**Purpose**: Factual inventory of what PromptForge became to avoid repeating complexity in a new Kanban-integrated minimalist implementation.

**Audited Repositories**:
- Backend: `/lump/apps/prompt-forge`
- Frontend: `/lump/apps/prompt-forge-console`

---

## 1. Repository Discovery

### Backend: `prompt-forge`

**Path**: `/lump/apps/prompt-forge`

**Primary Language**: Python 3.11+

**Framework**: FastAPI + Uvicorn

**Package Manager**: pip / setuptools

**Runtime**: Python 3.11+

**Build Commands**:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

**Dev Commands**:
```bash
# API Service
PYTHONPATH=. uvicorn promptforge_services.api:app --host 127.0.0.1 --port 8090 --reload

# Watcher
PYTHONPATH=. python3 -m promptforge_watcher
```

**Test Commands**:
```bash
python3 -m pytest -q
```

**Docker Deployment**:
- `docker-compose.yml` - Full stack
- `docker-compose.dev.yml` - Dev mode with bind mounts
- `Dockerfile` - API service image
- `Dockerfile.watcher` - Watcher service image
- `Dockerfile.shim` - Codex shim service image

**Environment Files**:
- `.env.example` - Template with safe defaults
- `.env` - Local secrets (gitignored)

**Required Variables** (secrets redacted):
- `POSTGRES_PASSWORD` - Database password
- `N8N_ENCRYPTION_KEY` - n8n secrets encryption
- `WEBHOOK_URL` - n8n webhook base URL
- `PROMPTFORGE_DATABASE_URL` - Postgres connection string
- `PROMPTFORGE_VAULT_PATH` - Obsidian vault root (default: `/vault`)
- `PROMPTFORGE_WATCH_FOLDER` - Intake folder (default: `Inbox/Voice`)
- `PROMPTFORGE_PROCESSED_FOLDER` - Writeback folder (default: `Processed/Voice`)
- `PROMPTFORGE_KANBAN_BASE_URL` - Kanban app base URL (default: `http://localhost:3484`)
- `PROMPTFORGE_KANBAN_WORKSPACE_ID` - Optional workspace binding
- `PROMPTFORGE_SECRETS_MASTER_KEY` - Fernet key for console secret encryption (base64)

**README/Setup**: `/lump/apps/prompt-forge/README.md`

**Generated Code**: None

**Schema Files**: `/lump/apps/prompt-forge/docs/planning/promptforge_postgres_schema.sql`

**Dependencies** (from pyproject.toml):
- FastAPI, Uvicorn, Pydantic - API framework
- psycopg[binary] - Postgres driver
- python-frontmatter, PyYAML - Markdown/YAML parsing
- watchdog - Filesystem watching
- httpx - HTTP client
- orjson - Fast JSON serialization
- rapidfuzz, regex - Text matching and cleanup
- jinja2 - Template rendering
- mdformat - Markdown formatting
- cryptography - Secret encryption (Fernet)
- libtmux - tmux session management

---

### Frontend: `prompt-forge-console`

**Path**: `/lump/apps/prompt-forge-console`

**Primary Language**: TypeScript

**Framework**: React 18.3 + Vite 5.4

**Package Manager**: npm (lockfile present), bun (lockb present)

**Runtime**: Node.js (inferred from package.json)

**Build Commands**:
```bash
npm run build         # Production build
npm run build:dev     # Development build
```

**Dev Commands**:
```bash
npm run dev           # Vite dev server (default port 5173)
```

**Test Commands**:
```bash
npm test              # Run tests once
npm run test:watch    # Watch mode
```

**Docker Deployment**:
- `Dockerfile` - Nginx-based production image
- `nginx.conf` - Nginx configuration

**Environment Files**:
- Build-time: `VITE_PROMPTFORGE_API_BASE` (optional, defaults to relative paths)

**Setup Instructions**: Minimal `README.md`

**Generated Code**: None detected

**Dependencies** (from package.json):
- React, React DOM, React Router DOM - Core framework
- @radix-ui/* - UI component primitives (30+ packages)
- @tanstack/react-query - Server state management
- zustand - Client state management
- react-hook-form, zod, @hookform/resolvers - Form handling
- tailwindcss, tailwindcss-animate - Styling
- lucide-react - Icons
- sonner - Toast notifications
- cmdk - Command palette
- recharts - Charts/data visualization
- react-window - Virtualized lists
- date-fns - Date utilities
- TypeScript 5.8, Vite, Vitest, ESLint - Tooling

**File Count**: 126 TypeScript/TSX files

---

## 2. Backend: High-Level Architecture

**Framework**: FastAPI

**Application Entrypoints**:
- `/lump/apps/prompt-forge/promptforge_services/api.py` - API service
- `/lump/apps/prompt-forge/promptforge_watcher/__main__.py` - Watcher service

**API Structure**: RESTful HTTP endpoints

**Routing/Module Organization**:
- `promptforge_services/api.py` - Main FastAPI app, core processing endpoints
- `promptforge_services/console_api.py` - Console management API router (mounted at `/console`)
- Endpoints organized functionally: processing pipeline, console management, LLM providers

**Dependency Injection**: None formal - uses module-level functions and direct imports

**Service Wiring Pattern**: Functional composition - pipeline functions called from route handlers

**Database/Storage Layer**:
- PostgreSQL 16 (production)
- psycopg3 with dict_row cursor factory
- Raw SQL queries (no ORM)
- Connection management via `psycopg.connect()` context managers

**Migration System**:
- Manual SQL scripts in `/lump/apps/prompt-forge/docs/planning/`
- Startup migration hook in API: `ensure_intake_notes_route_json()`
- Bootstrap script: `/lump/apps/prompt-forge/scripts/bootstrap_stack.sh`
- Separate migration runner: `/lump/apps/prompt-forge/scripts/migrate_postgres.sh`

**Background Workers**: None - watcher runs as separate long-lived process

**Schedulers**: None

**File Watchers**:
- `/lump/apps/prompt-forge/promptforge_watcher/watcher.py`
- Uses `watchdog` library for filesystem events
- Two-phase: startup catch-up scan + event-driven mode
- Per-file debouncing with configurable stabilization delay

**Queue/Job System**: None formal - database-backed delivery queue with status transitions

**External Integrations**:
- **n8n**: Optional webhook POST on note import
- **Kanban app**: Direct HTTP POST for delivery dispatch
- **LLM providers**: Pluggable (OpenAI, Anthropic, Ollama, OpenAI-compatible, LMStudio, LlamaCPP)

**LLM/Provider Integration**:
- `/lump/apps/prompt-forge/promptforge_services/llm/router.py` - Provider abstraction
- `/lump/apps/prompt-forge/promptforge_services/llm/providers.py` - Provider implementations
- `/lump/apps/prompt-forge/promptforge_services/llm/config.py` - LLM settings
- Default mode: `deterministic_only` (LLM disabled)
- Optional modes: `deterministic_plus_review`, `llm_inference_optional`

**Webhook/n8n Integration**:
- `/lump/apps/prompt-forge/promptforge_watcher/webhook.py`
- Configurable via `PROMPTFORGE_WEBHOOK_ENABLED`, `PROMPTFORGE_N8N_WEBHOOK_URL`
- POST intake note payload to n8n on successful import

**Auth/Security Model**:
- **No auth** - localhost-only deployment
- CORS configured for local frontend origins
- Secrets encryption: Fernet (symmetric) with `PROMPTFORGE_SECRETS_MASTER_KEY`
- `/lump/apps/prompt-forge/promptforge_services/secrets.py` - Secret encryption helpers

**Logging/Metrics/Tracing**:
- Python `logging` module
- HTTP request logging middleware (excludes health checks)
- No structured logging, no metrics export, no tracing

**Error Handling Pattern**:
- HTTPException for API errors (400, 404, 503)
- Database errors logged, not always caught
- LLM errors captured in `llm_runs` table with nullable fields

---

## 3. Backend: Domain Model and Database

Schema source: `/lump/apps/prompt-forge/docs/planning/promptforge_postgres_schema.sql`

### Core Entities

#### `projects`
- **Source**: Line 172
- **Fields**: `id`, `slug`, `name`, `description`, `vault_path`, `git_repo_url`, `default_prompt_type`, `default_destination`, `active_ruleset_id`, `metadata_json`, `created_at`, `updated_at`
- **Required**: `slug`, `name`
- **Relationships**: `active_ruleset_id` → `rulesets(id)`, referenced by `intake_notes`, `utterances`, `rulesets`, etc.
- **Indexes**: `active_ruleset_id`
- **Lifecycle**: Created manually or via console, updated via PATCH
- **Essential for new system**: **No** - single-project systems don't need a projects table

---

#### `intake_notes`
- **Source**: Line 202
- **Fields**: `id`, `vault_path`, `note_relative_path`, `note_title`, `note_hash`, `obsidian_created_at`, `imported_at`, `frontmatter_json`, `body_markdown`, `project_id`, `status`, `watch_eligible`, `source_device`, `route_json`, `last_error`, `created_at`
- **Required**: `vault_path`, `note_relative_path`, `note_title`, `body_markdown`
- **Relationships**: `project_id` → `projects(id)`
- **Indexes**: `project_id`, `status`, `watch_eligible`, `imported_at`, `body_tsv` (full-text)
- **Status values**: `new`, `imported`, `processing`, `processed`, `error`, `archived`
- **Lifecycle**: Created by watcher on file import, updated on processing, moved to `archived` after delivery
- **Who creates**: Watcher
- **Who updates**: Watcher (status, hash), console (archive action)
- **Essential for new system**: **Partially** - intake record concept useful, but schema is over-normalized

---

#### `utterances`
- **Source**: Line 241
- **Fields**: `id`, `intake_note_id`, `raw_text`, `directive_text`, `project_id`, `scope`, `capture_type`, `created_at`
- **Required**: `intake_note_id`, `raw_text`
- **Relationships**: `intake_note_id` → `intake_notes(id)`, `project_id` → `projects(id)`
- **Indexes**: `intake_note_id`, `project_id`, `scope`
- **Lifecycle**: Created during note import (one utterance per note in current design)
- **Who creates**: Watcher
- **Who updates**: Never
- **Essential for new system**: **No** - unnecessary layer for 1:1 note-to-utterance mapping

---

#### `transcript_revisions`
- **Source**: Line 261
- **Fields**: `id`, `utterance_id`, `revision_kind`, `content`, `producer_type`, `producer_name`, `template_profile`, `quality_score`, `metadata_json`, `created_at`
- **Required**: `utterance_id`, `revision_kind`, `content`, `producer_type`, `producer_name`
- **Relationships**: `utterance_id` → `utterances(id)`
- **Indexes**: `utterance_id`, `revision_kind`, `created_at`, `content_tsv` (full-text)
- **Revision kinds**: `raw`, `directive_stripped`, `deterministic_preprocessed`, `llm_cleaned`, `llm_structured_source`, `final_rendered_prompt`
- **Lifecycle**: Append-only, created at each processing stage
- **Who creates**: Watcher, API pipeline functions
- **Who updates**: Never (append-only)
- **Essential for new system**: **No** - audit trail overkill for minimal implementation

---

#### `rulesets`
- **Source**: Line 295
- **Fields**: `id`, `name`, `scope`, `project_id`, `version`, `is_active`, `description`, `created_at`
- **Required**: `name`, `scope`
- **Relationships**: `project_id` → `projects(id)`, referenced by `projects(active_ruleset_id)`, `rules(ruleset_id)`
- **Indexes**: `scope, project_id, is_active`, unique active per scope/project
- **Lifecycle**: Created via console, versioned, activated via toggle
- **Who creates**: Console UI
- **Who updates**: Console UI (version bump, activation)
- **Essential for new system**: **No** - deterministic rule application doesn't need DB persistence

---

#### `rules`
- **Source**: Line 333
- **Fields**: `id`, `ruleset_id`, `rule_type`, `priority`, `enabled`, `match_conditions_json`, `action_json`, `notes`, `created_at`
- **Required**: `ruleset_id`, `rule_type`
- **Relationships**: `ruleset_id` → `rulesets(id)`
- **Indexes**: `ruleset_id`, `rule_type, priority`
- **Rule types**: `cleanup`, `expansion`, `routing`, `formatting`, `safety`, `terminology`
- **Lifecycle**: Created/updated via console, evaluated during preprocessing
- **Who creates**: Console UI
- **Who updates**: Console UI
- **Essential for new system**: **No** - rules can live in code or config files

---

#### `term_dictionary`
- **Source**: Line 352
- **Fields**: `id`, `scope`, `project_id`, `source_term`, `canonical_term`, `confidence`, `notes`, `created_at`
- **Required**: `source_term`, `canonical_term`
- **Relationships**: `project_id` → `projects(id)`
- **Indexes**: `scope, project_id`, unique per `scope, project_id, source_term`
- **Lifecycle**: Created/updated via console dictionary UI
- **Who creates**: Console UI
- **Who updates**: Console UI
- **Essential for new system**: **No** - term replacement can be file-based

---

#### `prompt_templates`
- **Source**: Line 374
- **Fields**: `id`, `name`, `scope`, `project_id`, `prompt_type`, `version`, `body_template`, `output_contract_name`, `is_active`, `created_at`
- **Required**: `name`, `scope`, `prompt_type`, `body_template`, `output_contract_name`
- **Relationships**: `project_id` → `projects(id)`
- **Indexes**: `scope, project_id, prompt_type`, unique active per scope/project/type
- **Lifecycle**: Created/versioned via console, activated via toggle
- **Who creates**: Console UI
- **Who updates**: Console UI (version bump, activation)
- **Essential for new system**: **Partially** - template concept useful, but file-based simpler than DB versioning

---

#### `prompt_generations`
- **Source**: Line 407
- **Fields**: `id`, `utterance_id`, `project_id`, `prompt_type`, `selected_ruleset_id`, `selected_template_id`, `structured_output_json`, `final_prompt_markdown`, `requires_review`, `status`, `error_text`, `created_at`
- **Required**: `utterance_id`, `prompt_type`
- **Relationships**: `utterance_id` → `utterances(id)`, `project_id` → `projects(id)`, `selected_ruleset_id` → `rulesets(id)`, `selected_template_id` → `prompt_templates(id)`
- **Indexes**: `utterance_id`, `project_id`, `status`
- **Status values**: `created`, `preprocessed`, `transforming`, `structured_validating`, `rendered`, `failed`
- **Lifecycle**: Created during processing, updated through pipeline stages
- **Who creates**: API pipeline
- **Who updates**: API pipeline, console (review actions)
- **Essential for new system**: **Partially** - generated prompt record useful, but status machine is complex

---

#### `llm_runs`
- **Source**: Line 434
- **Fields**: `id`, `utterance_id`, `prompt_generation_id`, `provider_name`, `model_name`, `mode`, `latency_ms`, `token_usage_json`, `fallback_chain_json`, `summary`, `findings_json`, `raw_response_json`, `created_at`
- **Required**: `utterance_id`, `prompt_generation_id`
- **Relationships**: `utterance_id` → `utterances(id)`, `prompt_generation_id` → `prompt_generations(id)`
- **Indexes**: `utterance_id`, `prompt_generation_id`, `mode`
- **Modes**: `review`, `inference`
- **Lifecycle**: Created when LLM is invoked (optional feature)
- **Who creates**: LLM router
- **Who updates**: Never
- **Essential for new system**: **No** - LLM review/inference is future feature

---

#### `delivery_targets`
- **Source**: Line 462
- **Fields**: `id`, `name`, `target_type`, `target_identifier`, `scope`, `project_id`, `is_default`, `is_auto_dispatch_safe`, `config_json`, `created_at`
- **Required**: `name`, `target_type`, `target_identifier`
- **Relationships**: `project_id` → `projects(id)`
- **Indexes**: `scope, project_id`, `is_default`, unique per `target_type, target_identifier`
- **Target types**: `none`, `chat_session`, `claude_session`, `codex_session`, `obsidian_note`, `generic_queue`
- **Lifecycle**: Created/updated via console targets UI
- **Who creates**: Console UI
- **Who updates**: Console UI
- **Essential for new system**: **No** - Kanban-only delivery doesn't need multi-target registry

---

#### `delivery_session_registry`
- **Source**: Line 487
- **Fields**: `id`, `delivery_target_id`, `target_type`, `target_identifier`, `session_identifier`, `session_status`, `provider_name`, `is_current`, `is_attached`, `is_busy`, `is_reachable`, `is_stale`, `last_seen_at`, `heartbeat_at`, `ended_at`, `metadata_json`, `created_at`, `updated_at`
- **Required**: `target_type`, `target_identifier`, `session_identifier`, `session_status`
- **Relationships**: `delivery_target_id` → `delivery_targets(id)`
- **Indexes**: `target_type, target_identifier, created_at`, `session_status, is_current`, unique `session_identifier`, unique current per target
- **Session statuses**: `active`, `stale`, `closed`, `failed`
- **Lifecycle**: Created/updated by delivery dispatch logic (tmux session tracking)
- **Who creates**: Delivery dispatcher
- **Who updates**: Delivery dispatcher (heartbeat, status)
- **Essential for new system**: **No** - tmux session tracking irrelevant for Kanban delivery

---

#### `deliveries`
- **Source**: Line 538
- **Fields**: `id`, `prompt_generation_id`, `delivery_target_id`, `destination`, `target_type`, `target_identifier`, `mode`, `status`, `priority`, `queued_at`, `dispatched_at`, `acked_at`, `session_identifier`, `dispatch_request_json`, `dispatch_response_json`, `error_text`, `created_at`
- **Required**: `prompt_generation_id`, `destination`, `target_type`, `target_identifier`
- **Relationships**: `prompt_generation_id` → `prompt_generations(id)`, `delivery_target_id` → `delivery_targets(id)`
- **Indexes**: `prompt_generation_id`, `status`, `target_type, target_identifier`, `priority, status`, `session_identifier`
- **Statuses**: `not_started`, `queued`, `dispatching`, `delivered`, `acked`, `failed`
- **Modes**: `draft`, `queue`, `auto_dispatch`
- **Priorities**: `low`, `normal`, `high`, `urgent`
- **Lifecycle**: Created during delivery preparation, updated during dispatch
- **Who creates**: Watcher (via delivery preparation)
- **Who updates**: Watcher/dispatcher (status transitions), console (retry, reroute)
- **Essential for new system**: **Partially** - delivery record concept useful, but status/priority/session complexity avoidable

---

#### `processing_runs`
- **Source**: Line 574
- **Fields**: `id`, `utterance_id`, `workflow_name`, `status`, `started_at`, `ended_at`, `error_stage`, `trace_json`
- **Required**: `utterance_id`, `workflow_name`
- **Relationships**: `utterance_id` → `utterances(id)`
- **Indexes**: `utterance_id`, `status`
- **Statuses**: `running`, `completed`, `failed`
- **Lifecycle**: Created at workflow start, updated at completion/failure
- **Who creates**: Watcher
- **Who updates**: Watcher
- **Essential for new system**: **No** - workflow tracking overkill for deterministic pipeline

---

#### `workflow_error_records`
- **Source**: Line 595
- **Fields**: `id`, `source_kind`, `project_id`, `intake_note_id`, `utterance_id`, `prompt_generation_id`, `delivery_id`, `processing_run_id`, `delivery_target_id`, `stage_name`, `error_class`, `error_code`, `error_message`, `error_context_json`, `human_intervention_required`, `created_at`
- **Required**: `source_kind`, `error_message`, one of the ID references
- **Relationships**: References `projects`, `intake_notes`, `utterances`, `prompt_generations`, `deliveries`, `processing_runs`, `delivery_targets`
- **Indexes**: `created_at`, `source_kind`, `human_intervention_required`, `project_id`, `intake_note_id`, `utterance_id`, `delivery_id`, `delivery_target_id`, `processing_run_id`, `prompt_generation_id`
- **Source kinds**: `intake_note`, `utterance`, `prompt_generation`, `delivery`, `processing_run`, `console_action`, `system`
- **Lifecycle**: Created on error events, never updated
- **Who creates**: Watcher, API, console error handlers
- **Who updates**: Never (append-only)
- **Essential for new system**: **No** - simple error logging sufficient

---

#### `console_runtime_settings`
- **Source**: Line 681
- **Fields**: `id`, `scope`, `project_id`, `key`, `value_json`, `updated_by_user_id`, `created_at`, `updated_at`
- **Required**: `scope`, `key`, `value_json`
- **Relationships**: `project_id` → `projects(id)`
- **Indexes**: Unique per `scope, project_id, key`
- **Lifecycle**: Created/updated via console settings UI
- **Who creates**: Console UI
- **Who updates**: Console UI
- **Essential for new system**: **No** - env vars or local config file simpler

---

### Schema Summary

**Total tables**: 15

**Normalization level**: Very high (3NF+), append-only audit trails

**Over-normalized for MVP**: Yes - many tables support multi-user, multi-project, versioning, audit trails that aren't needed for single-user localhost tool

**Essential tables for new minimal implementation**:
1. `intake_notes` (simplified - just source record)
2. `prompt_generations` (simplified - just output record)
3. `deliveries` (simplified - just Kanban delivery status)

**Avoidable tables**:
- `projects` - not needed for single-project
- `utterances` - unnecessary 1:1 indirection
- `transcript_revisions` - audit trail overkill
- `rulesets`, `rules` - deterministic logic can live in code
- `term_dictionary` - can be file-based
- `prompt_templates` - can be file-based
- `llm_runs` - future feature
- `delivery_targets` - Kanban-only doesn't need registry
- `delivery_session_registry` - tmux session tracking irrelevant
- `processing_runs` - workflow tracking overkill
- `workflow_error_records` - simple logging sufficient
- `console_runtime_settings` - env vars simpler

---

## 4. Backend: API Surface

Source: `/lump/apps/prompt-forge/promptforge_services/api.py`, `/lump/apps/prompt-forge/promptforge_services/console_api.py`

### Core Processing Endpoints

| Method | Path | Source | Request | Response | Auth | Side Effects | DB Entities | Frontend Calls | Essential |
|--------|------|--------|---------|----------|------|--------------|-------------|----------------|-----------|
| GET | `/health` | api.py:87 | None | `{"ok": true, "supported_contracts": ["agent_task_v1"]}` | None | None | None | Health checks | Yes |
| GET | `/_healthz` | api.py:82 | None | `{"ok": true}` | None | None | None | Docker healthcheck | Yes |
| GET | `/providers/health` | api.py:92 | None | `LLMProvidersHealthResponse` | None | None | None | Console health page | No (LLM feature) |
| POST | `/preprocess` | api.py:97 | `PreprocessRequest` | `PreprocessResponse` | None | None | None | Not called by frontend | Partially |
| POST | `/validate` | api.py:102 | `ValidateRequest` | `ValidateResponse` | None | None | None | Not called by frontend | Partially |
| POST | `/render` | api.py:110 | `RenderRequest` | `RenderResponse` | None | None | None | Not called by frontend | Partially |
| POST | `/prepare-delivery` | api.py:118 | `PrepareDeliveryRequest` | `PrepareDeliveryResponse` | None | None | None | Not called by frontend | Partially |

**Notes**:
- Core pipeline endpoints are called by **watcher**, not frontend
- Frontend uses `/console/*` endpoints exclusively
- LLM provider health is optional feature

---

### Console Management Endpoints (Frontend-Facing)

Organized by functional group:

#### Health/Bootstrap

| Method | Path | Source | Purpose | Essential |
|--------|------|--------|---------|-----------|
| GET | `/console/health` | console_api.py | Overall system health | Yes |
| GET | `/console/bootstrap` | console_api.py | Initial config and metadata for frontend | Yes |

---

#### Intake Notes

| Method | Path | Source | Purpose | Essential |
|--------|------|--------|---------|-----------|
| GET | `/console/intake` | console_api.py | List intake notes with filters/pagination | Yes |
| GET | `/console/intake/{id}` | console_api.py | Intake note detail | Yes |
| PATCH | `/console/intake/{id}/archive` | console_api.py | Archive processed note | Useful |
| POST | `/console/intake/purge-archived` | console_api.py | Bulk delete archived notes | Useful |
| GET | `/console/intake/{id}/lineage` | console_api.py | Full processing lineage (note → utterance → prompt → delivery) | No (debug feature) |

---

#### Prompts

| Method | Path | Source | Purpose | Essential |
|--------|------|--------|---------|-----------|
| GET | `/console/prompts` | console_api.py | List prompt generations with filters | Yes |
| GET | `/console/prompts/{id}` | console_api.py | Prompt detail | Yes |
| POST | `/console/prompts/{id}/force-review` | console_api.py | Mark for human review | Useful |
| POST | `/console/prompts/{id}/clone` | console_api.py | Duplicate prompt | Avoidable |
| PATCH | `/console/prompts/{id}/priority` | console_api.py | Update delivery priority | Avoidable |

---

#### Deliveries

| Method | Path | Source | Purpose | Essential |
|--------|------|--------|---------|-----------|
| GET | `/console/deliveries` | console_api.py | List deliveries with filters | Yes |
| GET | `/console/deliveries/{id}` | console_api.py | Delivery detail | Yes |
| POST | `/console/deliveries/{id}/retry` | console_api.py | Retry failed delivery | Useful |
| POST | `/console/deliveries/{id}/reroute` | console_api.py | Change delivery target | Avoidable |
| PATCH | `/console/deliveries/{id}/status` | console_api.py | Manual status update | Avoidable |

---

#### Delivery Targets

| Method | Path | Source | Purpose | Essential |
|--------|------|--------|---------|-----------|
| GET | `/console/targets` | console_api.py | List delivery targets | No (Kanban-only) |
| GET | `/console/targets/{id}` | console_api.py | Target detail | No |
| POST | `/console/targets` | console_api.py | Create target | No |
| PATCH | `/console/targets/{id}` | console_api.py | Update target | No |
| DELETE | `/console/targets/{id}` | console_api.py | Delete target | No |
| GET | `/console/targets/{id}/health` | console_api.py | Target health check | No |
| POST | `/console/targets/{id}/dispatch` | console_api.py | Manual dispatch test | No |

---

#### Rules/Rulesets

| Method | Path | Source | Purpose | Essential |
|--------|------|--------|---------|-----------|
| GET | `/console/rulesets` | console_api.py | List rulesets | No (file-based better) |
| GET | `/console/rulesets/{id}` | console_api.py | Ruleset detail | No |
| POST | `/console/rulesets` | console_api.py | Create ruleset | No |
| PATCH | `/console/rulesets/{id}` | console_api.py | Update ruleset | No |
| DELETE | `/console/rulesets/{id}` | console_api.py | Delete ruleset | No |
| GET | `/console/rules` | console_api.py | List rules | No |
| GET | `/console/rules/{id}` | console_api.py | Rule detail | No |
| POST | `/console/rules` | console_api.py | Create rule | No |
| PATCH | `/console/rules/{id}` | console_api.py | Update rule | No |
| DELETE | `/console/rules/{id}` | console_api.py | Delete rule | No |
| POST | `/console/rules/dry-run` | console_api.py | Test rule against sample text | No |

---

#### Templates

| Method | Path | Source | Purpose | Essential |
|--------|------|--------|---------|-----------|
| GET | `/console/templates` | console_api.py | List prompt templates | No (file-based better) |
| GET | `/console/templates/{id}` | console_api.py | Template detail | No |
| POST | `/console/templates` | console_api.py | Create template | No |
| PATCH | `/console/templates/{id}` | console_api.py | Update template | No |
| DELETE | `/console/templates/{id}` | console_api.py | Delete template | No |
| POST | `/console/templates/{id}/activate` | console_api.py | Set as active template | No |

---

#### Dictionary

| Method | Path | Source | Purpose | Essential |
|--------|------|--------|---------|-----------|
| GET | `/console/dictionary` | console_api.py | List term mappings | No (file-based better) |
| POST | `/console/dictionary/upsert` | console_api.py | Create/update term | No |
| DELETE | `/console/dictionary/{id}` | console_api.py | Delete term | No |

---

#### Settings

| Method | Path | Source | Purpose | Essential |
|--------|------|--------|---------|-----------|
| GET | `/console/settings` | console_api.py | Get runtime settings | Useful |
| PATCH | `/console/settings/runtime` | console_api.py | Update runtime config (vault path, webhook URL, Kanban URL, etc.) | Useful |
| PATCH | `/console/settings/secrets` | console_api.py | Update encrypted secrets (API keys) | Useful |

---

#### Logs/Errors/Metrics

| Method | Path | Source | Purpose | Essential |
|--------|------|--------|---------|-----------|
| GET | `/console/logs` | console_api.py | Query workflow error records | Avoidable |
| GET | `/console/errors/fingerprints` | console_api.py | Grouped error summary | Avoidable |
| GET | `/console/metrics/queue-depth` | console_api.py | Current queue stats | Avoidable |
| GET | `/console/metrics/throughput` | console_api.py | Processing throughput over window | Avoidable |
| GET | `/console/metrics/sla-summary` | console_api.py | SLA compliance metrics | Avoidable |
| GET | `/console/metrics/health-snapshot` | console_api.py | Combined health/metrics snapshot | Avoidable |

---

#### Kanban Integration

| Method | Path | Source | Purpose | Essential |
|--------|------|--------|---------|-----------|
| GET | `/console/kanban/workspaces` | console_api.py | Discover Kanban workspaces | Useful |
| POST | `/console/kanban/preview/{id}` | console_api.py | Preview Kanban task manifest | Useful |
| POST | `/console/kanban/apply/{id}` | console_api.py | Import to Kanban workspace | Useful |

---

#### Projects

| Method | Path | Source | Purpose | Essential |
|--------|------|--------|---------|-----------|
| GET | `/console/projects` | console_api.py | List projects | No (single-project) |
| GET | `/console/projects/{id}` | console_api.py | Project detail | No |
| POST | `/console/projects` | console_api.py | Create project | No |
| PATCH | `/console/projects/{id}` | console_api.py | Update project | No |
| DELETE | `/console/projects/{id}` | console_api.py | Delete project | No |

---

#### LLM Assist (Optional Feature)

| Method | Path | Source | Purpose | Essential |
|--------|------|--------|---------|-----------|
| POST | `/console/llm/assist` | console_api.py | LLM-assisted console operations | No (future feature) |

---

### API Summary

**Total endpoints**: 60+

**Endpoint groups**:
- Core processing: 7 (called by watcher)
- Console intake: 5
- Console prompts: 5
- Console deliveries: 5
- Console targets: 7
- Console rules/rulesets: 11
- Console templates: 6
- Console dictionary: 3
- Console settings: 3
- Console logs/errors/metrics: 6
- Console Kanban: 3
- Console projects: 5
- Console LLM: 1

**Essential for new minimal implementation**:
- Health: `GET /health`
- Bootstrap: `GET /console/bootstrap`
- Intake: `GET /console/intake`, `GET /console/intake/{id}`
- Prompts: `GET /console/prompts`, `GET /console/prompts/{id}`
- Deliveries: `GET /console/deliveries`, `GET /console/deliveries/{id}`, `POST /console/deliveries/{id}/retry`
- Kanban: `GET /console/kanban/workspaces`, `POST /console/kanban/apply/{id}`

**~14 essential endpoints** vs 60+ total = **77% complexity avoidable**

---

## 5. Backend: Processing Pipeline

Source: `/lump/apps/prompt-forge/promptforge_watcher/__main__.py`, `/lump/apps/prompt-forge/promptforge_services/pipeline.py`, `/lump/apps/prompt-forge/promptforge_watcher/watcher.py`

### Pipeline Flow

```
Obsidian note created/modified
  ↓
File watcher event (watchdog)
  ↓
Debounce/stabilize (configurable delay)
  ↓
Hash check (skip if unchanged)
  ↓
Parse frontmatter + body
  ↓
Eligibility check (status: new, watch_eligible: true, has transcript)
  ↓
[PERSIST] Create intake_note record
  ↓
[PERSIST] Create utterance record
  ↓
[API CALL] POST /preprocess → directive extraction, transcript cleanup
  ↓
[PERSIST] Create transcript_revision (raw, directive_stripped, deterministic_preprocessed)
  ↓
[API CALL] POST /validate → structured output validation
  ↓
[PERSIST] Create prompt_generation record
  ↓
[API CALL] POST /render → Jinja2 template rendering
  ↓
[PERSIST] Update prompt_generation (final_prompt_markdown)
  ↓
[OPTIONAL] LLM review/inference (if enabled)
  ↓
[PERSIST] Create llm_run record (if LLM used)
  ↓
[API CALL] POST /prepare-delivery → delivery target resolution
  ↓
[PERSIST] Create delivery record
  ↓
Route by destination:
  - obsidian_note → Write rendered prompt to vault folder
  - chat/cli → Dispatch to session (tmux/Codex/Claude API)
  - queue_only → Leave queued for manual action
  - Kanban → POST to Kanban workspace
  ↓
[PERSIST] Update delivery status (dispatching → delivered/failed)
  ↓
[OPTIONAL] Webhook to n8n (if enabled)
  ↓
[WRITEBACK] Update source note frontmatter (status: processed, delivery ID, etc.)
  ↓
[WRITEBACK] Move note to processed folder
```

### Key Functions/Modules

#### Note Entry

**Function**: `_handle_note_file()` in `/lump/apps/prompt-forge/promptforge_watcher/watcher.py`

**Steps**:
1. Read file, parse frontmatter + body
2. Hash content
3. Check eligibility (`status: new`, `watch_eligible: true`, transcript present)
4. Insert `intake_notes` record
5. Extract transcript from frontmatter or body
6. Insert `utterances` record with raw transcript

---

#### Preprocessing

**Function**: `preprocess_request()` in `/lump/apps/prompt-forge/promptforge_services/pipeline.py`

**Input**: `PreprocessRequest` (frontmatter, control_text, transcript_text, known_projects)

**Output**: `PreprocessResponse` (resolved_project, resolved_prompt_type, resolved_destination, target_identifier, mode, normalized_transcript, parsed_directives, draft_structured_output)

**Steps**:
1. Parse directives from `control_text` (e.g., `#project:promptforge`, `#type:coding-cli`, `#dest:cli`)
2. Clean transcript text (remove artifacts, normalize whitespace, apply rules)
3. Detect project from directives or fuzzy-match transcript content
4. Resolve prompt_type, destination, target_identifier, mode from directives or defaults
5. Build draft `AgentTaskV1` structured output
6. Return preprocessed metadata + normalized transcript

**Complexity sources**:
- Directive parsing with regex
- Fuzzy project detection (rapidfuzz)
- Rule application (if ruleset configured)
- Term dictionary lookups (if configured)

---

#### Validation

**Function**: `validate_request()` in `/lump/apps/prompt-forge/promptforge_services/pipeline.py`

**Input**: `ValidateRequest` (contract_name, payload dict)

**Output**: `ValidateResponse` (valid, warnings, payload as typed model)

**Steps**:
1. Validate `contract_name` is `agent_task_v1`
2. Parse payload dict as `AgentTaskV1` Pydantic model
3. Collect validation warnings (e.g., missing target_identifier)
4. Return typed payload

**Complexity**: Minimal (just Pydantic validation)

---

#### Rendering

**Function**: `render_request()` in `/lump/apps/prompt-forge/promptforge_services/pipeline.py`

**Input**: `RenderRequest` (contract_name, payload dict)

**Output**: `RenderResponse` (template_name, final_prompt_markdown, payload)

**Steps**:
1. Validate contract_name
2. Parse payload as `AgentTaskV1`
3. Select prompt template (from DB or default)
4. Render Jinja2 template with payload as context
5. Update payload with rendered markdown
6. Return template_name + final_prompt_markdown

**Complexity sources**:
- Database query for active template (scope precedence logic)
- Jinja2 template engine
- Template versioning and activation rules

---

#### Delivery Preparation

**Function**: `prepare_delivery_request()` in `/lump/apps/prompt-forge/promptforge_services/pipeline.py`

**Input**: `PrepareDeliveryRequest` (contract_name, payload, priority)

**Output**: `PrepareDeliveryResponse` (delivery metadata, payload)

**Steps**:
1. Validate contract_name
2. Parse payload
3. Map `destination` to `target_type`
4. Resolve `target_identifier` from payload or defaults
5. Build `PreparedDelivery` object (destination, target_type, target_identifier, mode, priority, requires_review)
6. Return delivery + payload

**Complexity**: Minimal (just mapping logic)

---

#### Delivery Dispatch

**Function**: `dispatch_delivery()` in `/lump/apps/prompt-forge/promptforge_watcher/delivery.py`

**Input**: Delivery record from database

**Output**: Updated delivery status

**Steps**:
1. Read delivery record
2. Route by `target_type`:
   - `obsidian_note` → Write markdown file to vault
   - `chat_session` / `claude_session` / `codex_session` → Dispatch to tmux session or API
   - `generic_queue` → Kanban workspace import
   - `none` → No-op
3. Update delivery status (dispatching → delivered/failed)
4. Record dispatch_request_json, dispatch_response_json, error_text

**Complexity sources**:
- Tmux session management (libtmux)
- Codex API calls (httpx)
- Kanban API calls (httpx)
- Session registry tracking (database writes)
- Error handling and retry logic

---

#### Webhook Posting

**Function**: `post_webhook()` in `/lump/apps/prompt-forge/promptforge_watcher/webhook.py`

**Input**: Intake note payload

**Output**: HTTP POST to n8n

**Steps**:
1. Build webhook payload (note metadata + transcript)
2. POST to configured `PROMPTFORGE_N8N_WEBHOOK_URL`
3. Log success/failure

**Complexity**: Minimal (just HTTP POST)

---

#### Writeback

**Function**: `writeback_processed_note()` in `/lump/apps/prompt-forge/promptforge_watcher/writeback.py`

**Input**: Intake note record, delivery record

**Output**: Updated note file in vault

**Steps**:
1. Read original note file
2. Update frontmatter (status: processed, delivery_id, processed_at)
3. Write updated note to processed folder
4. Update `intake_notes` record (status: processed)

**Complexity**: Minimal (file I/O + frontmatter update)

---

### Pipeline Summary

**Processing stages**: 10+

**Database writes per note**: 8-12 (intake_note, utterance, transcript_revisions × 3, prompt_generation, llm_run, delivery, delivery updates)

**API calls per note**: 4 (preprocess, validate, render, prepare-delivery)

**External calls per note**: 0-3 (LLM if enabled, n8n webhook if enabled, Kanban import if destination=generic_queue)

**Simplification opportunities**:
- Collapse utterance/transcript_revisions into intake_note (single record)
- Inline preprocessing logic (no API call)
- File-based templates (no DB query)
- Skip delivery preparation API call (just create delivery directly)
- **Result**: 1-2 DB writes, 0-1 API calls, 0-1 external calls per note

---

## 6. Backend: Complexity and Scope Creep Inventory

### Multi-Project Support

**Files**:
- `/lump/apps/prompt-forge/docs/planning/promptforge_postgres_schema.sql` (lines 172-196, projects table)
- `/lump/apps/prompt-forge/promptforge_services/console_api.py` (project CRUD endpoints)

**Problem**: Enables multiple projects per installation

**Complexity**:
- Project table with slug/name/defaults
- Project-scoped rules, templates, targets, settings
- Scope precedence logic (project > user > global)
- Foreign keys across 10+ tables
- Console UI for project management

**Minimal replacement**: Single-project assumption, env var or hardcoded project name

---

### Role-Based Access (Scaffolded but Unused)

**Files**:
- Schema has `updated_by_user_id` fields
- Console settings has `updated_by_user_id`

**Problem**: Multi-user infrastructure without auth

**Complexity**:
- User ID tracking (but no users table)
- Audit trail fields unused

**Minimal replacement**: Remove user tracking entirely (localhost single-user)

---

### Rule Engine

**Files**:
- `/lump/apps/prompt-forge/docs/planning/promptforge_postgres_schema.sql` (lines 295-347, rulesets + rules)
- `/lump/apps/prompt-forge/promptforge_services/console_api.py` (rule CRUD, dry-run endpoint)
- Frontend: `/lump/apps/prompt-forge-console/src/pages/Rules.tsx` (25KB)

**Problem**: Generic rule matching and action execution

**Complexity**:
- Ruleset versioning and activation
- Rule types: cleanup, expansion, routing, formatting, safety, terminology
- JSON-based match conditions and actions
- Priority ordering
- Scope precedence
- Console UI for rule creation/testing

**Minimal replacement**: Hardcoded Python functions for cleanup/routing, or simple regex config file

---

### Template Versioning and Activation

**Files**:
- Schema: `prompt_templates` table (lines 374-401)
- Console API: Template CRUD + activation
- Frontend: `/lump/apps/prompt-forge-console/src/pages/Templates.tsx` (19KB)

**Problem**: Database-backed template management with versioning

**Complexity**:
- Template scope (global/user/project)
- Version bumping
- Active/inactive toggle
- Unique constraint enforcement
- Template selection logic with scope precedence

**Minimal replacement**: Jinja2 templates in `templates/` directory, version-controlled with git

---

### Term Dictionary

**Files**:
- Schema: `term_dictionary` table
- Console API: Dictionary CRUD
- Frontend: `/lump/apps/prompt-forge-console/src/pages/Dictionary.tsx` (16KB)

**Problem**: Manages canonical term mappings

**Complexity**:
- Scope-based term resolution
- Confidence scoring
- Console UI for term management
- Application during preprocessing

**Minimal replacement**: YAML file with source → canonical mappings

---

### Delivery Target Registry

**Files**:
- Schema: `delivery_targets`, `delivery_session_registry` tables
- Console API: Target CRUD, health checks, manual dispatch
- Frontend: `/lump/apps/prompt-forge-console/src/pages/Targets.tsx` (11KB)
- `/lump/apps/prompt-forge/promptforge_services/delivery_dispatch.py`

**Problem**: Multi-target delivery infrastructure

**Complexity**:
- Target types: chat_session, claude_session, codex_session, obsidian_note, generic_queue
- Session registry with heartbeat tracking
- Target health probing
- Auto-dispatch safety flags
- Tmux session management (libtmux)

**Minimal replacement**: Hardcoded Kanban workspace URL, single delivery target

---

### LLM Provider Abstraction

**Files**:
- `/lump/apps/prompt-forge/promptforge_services/llm/router.py`
- `/lump/apps/prompt-forge/promptforge_services/llm/providers.py`
- `/lump/apps/prompt-forge/promptforge_services/llm/config.py`

**Problem**: Multi-provider LLM support (OpenAI, Anthropic, Ollama, OpenAI-compatible, LMStudio, LlamaCPP)

**Complexity**:
- Provider-specific adapters
- Fallback chain logic
- Token usage tracking
- Mode switching (review vs inference)
- Health probing per provider
- llm_runs table for audit trail

**Minimal replacement**: Skip LLM entirely (deterministic-only mode)

---

### n8n Workflow Integration

**Files**:
- `/lump/apps/prompt-forge/promptforge_watcher/webhook.py`
- `/lump/apps/prompt-forge/docs/planning/n8n_workflows/`
- Scripts: `import_n8n_workflows.sh`
- Docker Compose: n8n service container

**Problem**: Workflow orchestration dependency

**Complexity**:
- n8n container in stack
- Webhook URL configuration
- Workflow import scripts
- Postgres shared between PromptForge and n8n

**Minimal replacement**: Skip n8n entirely (direct Kanban delivery)

---

### Obsidian Writeback and Folder Management

**Files**:
- `/lump/apps/prompt-forge/promptforge_watcher/writeback.py`
- Watcher config: `PROMPTFORGE_PROCESSED_FOLDER`, `PROMPTFORGE_ERROR_FOLDER`

**Problem**: Note lifecycle management across vault folders

**Complexity**:
- Move notes between folders on status change
- Update frontmatter with processing metadata
- Error folder for failed notes

**Minimal replacement**: Leave notes in place, update frontmatter only

---

### Console Metrics and Dashboards

**Files**:
- Console API: Queue depth, throughput, SLA summary, health snapshot endpoints
- Frontend: `/lump/apps/prompt-forge-console/src/pages/Dashboard.tsx` (11KB)

**Problem**: Operational metrics and monitoring

**Complexity**:
- Time-window aggregations
- SLA compliance tracking
- Queue depth by status/priority
- Throughput calculations
- Dashboard charts (recharts)

**Minimal replacement**: Skip metrics entirely (not needed for single-user tool)

---

### Error Fingerprinting and Grouping

**Files**:
- Console API: `/console/errors/fingerprints`
- Schema: `workflow_error_records` table

**Problem**: Error aggregation and grouping

**Complexity**:
- Error class/code extraction
- Fingerprint hashing
- Grouped error summaries
- Human intervention flags

**Minimal replacement**: Simple error log file or stderr output

---

### Secrets Encryption

**Files**:
- `/lump/apps/prompt-forge/promptforge_services/secrets.py`
- `/lump/apps/prompt-forge/promptforge_services/secrets_migration.py`
- Schema: `console_runtime_settings` with encrypted values

**Problem**: Encrypt API keys in database

**Complexity**:
- Fernet symmetric encryption
- Key versioning for rotation
- Migration script for legacy plaintext secrets

**Minimal replacement**: Environment variables (not stored in DB)

---

### Audit Trails

**Files**:
- Schema: `transcript_revisions` (append-only), `workflow_error_records`, `llm_runs`, `processing_runs`

**Problem**: Comprehensive audit logging

**Complexity**:
- Append-only tables for all text transformations
- Processing run tracking
- Error history
- LLM interaction logs

**Minimal replacement**: Minimal logging (just final state, not intermediate steps)

---

### Settings Management

**Files**:
- Console API: `/console/settings`, `/console/settings/runtime`, `/console/settings/secrets`
- Frontend: `/lump/apps/prompt-forge-console/src/pages/Settings.tsx` (42KB - largest page)
- Schema: `console_runtime_settings` table

**Problem**: DB-backed runtime configuration

**Complexity**:
- Scope-based settings (global/user/project)
- Encrypted secret storage
- Settings UI with validation
- Runtime reconfiguration without restart

**Minimal replacement**: `.env` file or command-line args

---

## 7. Frontend: High-Level Architecture

**Framework**: React 18.3 + Vite 5.4 + TypeScript 5.8

**Entrypoint**: `/lump/apps/prompt-forge-console/src/main.tsx`

**Routing**: React Router DOM 6.30
- `/lump/apps/prompt-forge-console/src/App.tsx` - Route definitions

**State Management**:
- **Server state**: @tanstack/react-query (TanStack Query v5)
- **Client state**: Zustand 4.5
- Stores: `/lump/apps/prompt-forge-console/src/stores/`

**API Client**:
- `/lump/apps/prompt-forge-console/src/services/promptforge/` - API client functions
- Uses `fetch` API
- Base URL from `VITE_PROMPTFORGE_API_BASE` env var or relative paths

**UI Library**: Radix UI primitives (30+ packages)

**Component Library**: Custom components built on Radix + Tailwind
- `/lump/apps/prompt-forge-console/src/components/ui/` - Reusable primitives (shadcn-style)
- `/lump/apps/prompt-forge-console/src/components/pf/` - PromptForge-specific components
- `/lump/apps/prompt-forge-console/src/components/shell/` - Layout/shell components

**Styling**: Tailwind CSS 3.4 + tailwindcss-animate

**Form Handling**: React Hook Form 7.61 + Zod 3.23 + @hookform/resolvers

**Build**: Vite 5.4 with SWC plugin

**Test**: Vitest 3.2 + Testing Library

---

## 8. Frontend: Screens and User Flows

Source: `/lump/apps/prompt-forge-console/src/pages/`

| Route | File | Purpose | Components | API Calls | Mutations | Essential |
|-------|------|---------|-----------|-----------|-----------|-----------|
| `/` | Dashboard.tsx (11KB) | Overview dashboard | Stats cards, queue depth, throughput charts | `/console/metrics/health-snapshot`, `/console/metrics/queue-depth`, `/console/metrics/throughput` | None | No (metrics) |
| `/intake` | Intake.tsx (9KB) | Intake note list | Table, filters, search, pagination | `/console/intake` | Archive notes | Yes |
| `/intake/:id` | IntakeDetail.tsx (6KB) | Intake note detail | Note viewer, lineage graph | `/console/intake/{id}`, `/console/intake/{id}/lineage` | Archive | Yes |
| `/prompts` | Prompts.tsx (19KB) | Prompt generation queue | Table, filters, priority badges, markdown preview | `/console/prompts` | Force review, clone, update priority | Yes |
| `/prompts/:id` | (Inferred detail page) | Prompt detail | Prompt viewer, delivery trigger | `/console/prompts/{id}` | Clone, priority update | Useful |
| `/deliveries` | Deliveries.tsx (18KB) | Delivery queue | Table, filters, status tracking | `/console/deliveries` | Retry, reroute, status update | Yes |
| `/deliveries/:id` | (Inferred detail page) | Delivery detail | Delivery viewer, dispatch log | `/console/deliveries/{id}` | Retry, reroute | Useful |
| `/targets` | Targets.tsx (11KB) | Delivery target registry | Table, health status, target CRUD | `/console/targets`, `/console/targets/{id}/health` | Create, update, delete, dispatch test | No (Kanban-only) |
| `/rules` | Rules.tsx (25KB) | Rule management | Ruleset picker, rule list, rule editor, dry-run tester | `/console/rulesets`, `/console/rules`, `/console/rules/dry-run` | Create/update/delete rulesets and rules | No (file-based) |
| `/templates` | Templates.tsx (19KB) | Template management | Template list, editor, version history, activation | `/console/templates` | Create/update/delete templates, activate | No (file-based) |
| `/dictionary` | Dictionary.tsx (16KB) | Term dictionary | Term list, term editor | `/console/dictionary` | Upsert, delete terms | No (file-based) |
| `/settings` | Settings.tsx (42KB) | Settings editor | Tabbed settings UI, runtime config, secrets, Kanban binding | `/console/settings`, `/console/kanban/workspaces` | Update runtime settings, update secrets | Useful (simplified) |
| `/review` | Review.tsx (7KB) | Review queue | Notes/prompts requiring human review | `/console/prompts?requires_review=true` | Approve/reject | Useful |
| `/pipeline` | Pipeline.tsx (19KB) | Processing pipeline visualization | Flow diagram, stage detail | `/console/intake`, `/console/prompts`, `/console/deliveries` | None | No (debug view) |
| `/logs` | Logs.tsx (5KB) | Error log viewer | Log table, filters | `/console/logs` | None | Avoidable |
| `/health` | Health.tsx (3KB) | System health | Service status, provider health | `/console/health`, `/providers/health` | None | Useful |
| `*` | NotFound.tsx (0.7KB) | 404 page | Error message | None | None | Yes |

---

### Screen Groupings

#### Essential Screens (6)
- `/intake` - View imported notes
- `/intake/:id` - Note detail
- `/prompts` - Review generated prompts
- `/deliveries` - Track deliveries
- `/settings` - Configure Kanban binding
- `/health` - System health

#### Useful Screens (3)
- `/prompts/:id` - Prompt detail
- `/deliveries/:id` - Delivery detail
- `/review` - Review queue

#### Avoidable Screens (7)
- `/` - Dashboard (metrics)
- `/targets` - Multi-target management
- `/rules` - Rule engine UI
- `/templates` - Template versioning UI
- `/dictionary` - Term management UI
- `/pipeline` - Debug visualization
- `/logs` - Error log viewer

**~60% of screens avoidable** for Kanban-only minimal implementation

---

## 9. Frontend: Component and UI Complexity

### Component Inventory

Source: `/lump/apps/prompt-forge-console/src/components/`

#### UI Primitives (`/components/ui/`)

**Count**: 40+ components

**Examples**:
- `accordion.tsx`, `alert.tsx`, `avatar.tsx`, `badge.tsx`, `button.tsx`, `calendar.tsx`, `card.tsx`, `checkbox.tsx`, `collapsible.tsx`, `command.tsx`, `context-menu.tsx`, `dialog.tsx`, `dropdown-menu.tsx`, `form.tsx`, `hover-card.tsx`, `input.tsx`, `label.tsx`, `menubar.tsx`, `navigation-menu.tsx`, `popover.tsx`, `progress.tsx`, `radio-group.tsx`, `scroll-area.tsx`, `select.tsx`, `separator.tsx`, `sheet.tsx`, `slider.tsx`, `switch.tsx`, `table.tsx`, `tabs.tsx`, `textarea.tsx`, `toast.tsx`, `toggle.tsx`, `tooltip.tsx`

**Purpose**: Radix UI wrappers with Tailwind styling

**Where Used**: All pages

**Reuse for new system**: **Yes** - well-built accessible components

---

#### Shell Components (`/components/shell/`)

**Examples**:
- `Header.tsx` - Top navigation bar
- `Sidebar.tsx` - Left navigation menu
- `Layout.tsx` - Page layout wrapper
- `Breadcrumbs.tsx` - Breadcrumb navigation
- `Footer.tsx` - Footer bar

**Where Used**: All pages

**Reuse for new system**: **Simplify** - minimal Kanban UI doesn't need complex shell

---

#### PromptForge Components (`/components/pf/`)

**Examples**:
- `IntakeNoteCard.tsx` - Intake note list item
- `PromptCard.tsx` - Prompt generation list item
- `DeliveryCard.tsx` - Delivery list item
- `RuleEditor.tsx` - Rule creation/edit form
- `TemplateEditor.tsx` - Template editor
- `MarkdownPreview.tsx` - Markdown renderer
- `StatusBadge.tsx` - Status badges
- `PriorityBadge.tsx` - Priority badges
- `TargetTypeIcon.tsx` - Delivery target icons
- `LineageGraph.tsx` - Processing lineage visualization
- `FilterBar.tsx` - Table filter controls
- `PaginationControls.tsx` - Pagination UI

**Where Used**: Domain-specific pages

**Reuse for new system**: **Partially** - `MarkdownPreview`, badges, filter/pagination useful; rule/template editors avoidable

---

### Styling Patterns

**Base**: Tailwind utility classes

**Theme**: `next-themes` for dark mode support

**Colors**: Custom Tailwind theme in `tailwind.config.ts`

**Typography**: `@tailwindcss/typography` plugin

**Animations**: `tailwindcss-animate` plugin

**Icons**: `lucide-react`

**Reuse for new system**: **Yes** - modern, accessible, well-organized

---

### Data Handling Patterns

**Tables**:
- Custom table component with `@radix-ui/react-table` (NOT TanStack Table)
- Virtualization with `react-window` for large lists
- Client-side filtering and sorting

**Forms**:
- React Hook Form + Zod validation
- Reusable form components (`/components/ui/form.tsx`)

**Search**:
- Debounced search inputs
- API-side search (not client-side)

**Filters**:
- URL query params for filter state
- Filter bar component

**Pagination**:
- API-side pagination (limit/offset)
- Pagination controls component

**Reuse for new system**: **Yes** - patterns are solid

---

## 10. Frontend: Complexity and Scope Creep Inventory

### Full Dashboard

**Files**: `/lump/apps/prompt-forge-console/src/pages/Dashboard.tsx` (11KB)

**Features**:
- Queue depth by status/priority
- Throughput charts (recharts)
- SLA compliance metrics
- Health snapshot cards

**Complexity**:
- Multiple API calls on mount
- Real-time updates via react-query polling
- Chart configuration

**Minimal replacement**: Skip dashboard entirely (direct links to intake/prompts/deliveries)

---

### Multi-Page Admin Console

**Files**: 15 page components

**Features**:
- Separate pages for intake, prompts, deliveries, targets, rules, templates, dictionary, settings, logs, health, review, pipeline, dashboard

**Complexity**:
- Navigation menu with active state tracking
- Breadcrumbs
- Per-page layouts

**Minimal replacement**: Single-page or 2-3 page app (intake → prompts → deliveries)

---

### Overbuilt Tables

**Features**:
- Virtualized scrolling (react-window)
- Client-side sorting
- Advanced filters (status, priority, date range, search)
- Pagination controls

**Complexity**:
- Table components reused across 8+ pages
- Filter state management in URL params

**Minimal replacement**: Simple HTML table with server-side pagination, no virtualization

---

### User/Role Management UI

**Files**: Settings page has user management sections

**Features**:
- User list
- Role assignment
- User settings

**Complexity**:
- Full CRUD UI
- Scope-based permissions

**Minimal replacement**: Remove entirely (single-user)

---

### Delivery Target Management

**Files**: `/lump/apps/prompt-forge-console/src/pages/Targets.tsx` (11KB)

**Features**:
- Target CRUD
- Health probing
- Manual dispatch testing
- Target type selection

**Complexity**:
- Multi-target registry UI
- Health status polling

**Minimal replacement**: Remove entirely (Kanban-only)

---

### Rule Management UI

**Files**: `/lump/apps/prompt-forge-console/src/pages/Rules.tsx` (25KB - largest page)

**Features**:
- Ruleset picker
- Rule list
- Rule editor with JSON schema builder
- Dry-run tester
- Version management

**Complexity**:
- Complex form for match conditions + actions (JSON builder)
- Inline dry-run testing
- Scope and priority UI

**Minimal replacement**: Remove entirely (file-based rules)

---

### Template Management UI

**Files**: `/lump/apps/prompt-forge-console/src/pages/Templates.tsx` (19KB)

**Features**:
- Template list
- Template editor (Jinja2 syntax highlighting)
- Version history
- Activation toggle

**Complexity**:
- Code editor integration
- Version comparison
- Scope-based template selection

**Minimal replacement**: Remove entirely (file-based templates)

---

### Dictionary UI

**Files**: `/lump/apps/prompt-forge-console/src/pages/Dictionary.tsx` (16KB)

**Features**:
- Term list
- Term editor
- Scope selection
- Confidence scoring

**Complexity**:
- Full term management UI

**Minimal replacement**: Remove entirely (file-based dictionary)

---

### Settings UI

**Files**: `/lump/apps/prompt-forge-console/src/pages/Settings.tsx` (42KB - by far the largest)

**Features**:
- Tabbed settings (Runtime, Secrets, Kanban, Projects)
- Runtime config editor (vault path, webhook URL, LLM mode, etc.)
- Secret input fields with encryption
- Kanban workspace discovery + binding
- Project management

**Complexity**:
- 10+ setting fields
- Secret encryption/decryption
- Kanban workspace picker
- Form validation

**Minimal replacement**: Simple Kanban URL input form (3-5 fields)

---

### Logs/Metrics Viewers

**Files**:
- `/lump/apps/prompt-forge-console/src/pages/Logs.tsx` (5KB)
- Dashboard metrics

**Features**:
- Log table with filters
- Error fingerprints
- Throughput charts
- SLA summaries

**Complexity**:
- Time-window selectors
- Chart configuration
- Log level filtering

**Minimal replacement**: Remove entirely (stderr logging sufficient)

---

### Complex Empty/Loading/Error States

**Across all pages**:
- Custom empty state illustrations
- Loading skeletons
- Error boundaries
- Retry buttons

**Complexity**:
- Per-page empty state components
- Loading state orchestration

**Minimal replacement**: Simple "Loading..." / "No data" / "Error" text

---

### Generic Reusable Components Not Needed

**Examples**:
- Command palette (cmdk)
- Context menus
- Hover cards
- Navigation menus (complex)
- Carousels
- Sliders
- Toggle groups

**Used**: Rarely or not at all

**Minimal replacement**: Remove unused Radix components

---

## 11. Frontend ↔ Backend Contract

### API Client

**Location**: `/lump/apps/prompt-forge-console/src/services/promptforge/`

**Client Files**:
- `client.ts` - Base fetch wrapper
- `intake.ts` - Intake API calls
- `prompts.ts` - Prompt API calls
- `deliveries.ts` - Delivery API calls
- `targets.ts` - Target API calls
- `rules.ts` - Rule API calls
- `templates.ts` - Template API calls
- `dictionary.ts` - Dictionary API calls
- `settings.ts` - Settings API calls
- `logs.ts` - Log API calls
- `health.ts` - Health API calls
- `kanban.ts` - Kanban API calls
- `projects.ts` - Project API calls

**Base URL**: Configured via `VITE_PROMPTFORGE_API_BASE` env var, defaults to relative paths

**Generated Types**: None - hand-written TypeScript types in service files

**Shared Schemas**: None - frontend and backend types defined independently

**Error Handling**:
- HTTP errors thrown from client
- Caught in react-query error handlers
- Toast notifications for errors (sonner)

**Auth Headers**: None

**Session Behavior**: None

**Polling**: react-query refetchInterval for dashboard/health pages

**Optimistic Updates**: None

**Cache Invalidation**: Manual invalidation via react-query `queryClient.invalidateQueries()`

---

### Contract Mismatches

**None detected** - frontend and backend appear aligned on API contract

---

### Frontend → Backend Mapping

| Frontend Screen | Backend Endpoint(s) | Data Used | Mutation? | Essential for New App? |
|----------------|-------------------|-----------|-----------|----------------------|
| Dashboard | `/console/metrics/health-snapshot`, `/console/metrics/queue-depth`, `/console/metrics/throughput` | Stats, charts | No | No |
| Intake list | `/console/intake` | Note list, filters, pagination | No | Yes |
| Intake detail | `/console/intake/{id}`, `/console/intake/{id}/lineage` | Note detail, lineage | No | Yes |
| Intake archive | `/console/intake/{id}/archive` | - | Yes (PATCH) | Useful |
| Prompts list | `/console/prompts` | Prompt list, filters, pagination | No | Yes |
| Prompts detail | `/console/prompts/{id}` | Prompt detail | No | Useful |
| Prompts review | `/console/prompts/{id}/force-review` | - | Yes (POST) | Useful |
| Prompts clone | `/console/prompts/{id}/clone` | - | Yes (POST) | No |
| Prompts priority | `/console/prompts/{id}/priority` | - | Yes (PATCH) | No |
| Deliveries list | `/console/deliveries` | Delivery list, filters, pagination | No | Yes |
| Deliveries detail | `/console/deliveries/{id}` | Delivery detail | No | Useful |
| Deliveries retry | `/console/deliveries/{id}/retry` | - | Yes (POST) | Useful |
| Deliveries reroute | `/console/deliveries/{id}/reroute` | - | Yes (POST) | No |
| Deliveries status | `/console/deliveries/{id}/status` | - | Yes (PATCH) | No |
| Targets list | `/console/targets` | Target list | No | No |
| Targets detail | `/console/targets/{id}` | Target detail | No | No |
| Targets CRUD | `/console/targets`, `/console/targets/{id}` | - | Yes (POST/PATCH/DELETE) | No |
| Targets health | `/console/targets/{id}/health` | Health status | No | No |
| Targets dispatch | `/console/targets/{id}/dispatch` | - | Yes (POST) | No |
| Rules list | `/console/rulesets`, `/console/rules` | Rulesets, rules | No | No |
| Rules CRUD | `/console/rulesets`, `/console/rules`, `/console/rules/{id}` | - | Yes (POST/PATCH/DELETE) | No |
| Rules dry-run | `/console/rules/dry-run` | Dry-run result | Yes (POST) | No |
| Templates list | `/console/templates` | Template list | No | No |
| Templates CRUD | `/console/templates`, `/console/templates/{id}` | - | Yes (POST/PATCH/DELETE) | No |
| Templates activate | `/console/templates/{id}/activate` | - | Yes (POST) | No |
| Dictionary list | `/console/dictionary` | Term list | No | No |
| Dictionary upsert | `/console/dictionary/upsert` | - | Yes (POST) | No |
| Dictionary delete | `/console/dictionary/{id}` | - | Yes (DELETE) | No |
| Settings view | `/console/settings` | Settings | No | Useful |
| Settings runtime | `/console/settings/runtime` | - | Yes (PATCH) | Useful |
| Settings secrets | `/console/settings/secrets` | - | Yes (PATCH) | Useful |
| Settings Kanban | `/console/kanban/workspaces` | Workspace list | No | Useful |
| Kanban preview | `/console/kanban/preview/{id}` | Preview manifest | Yes (POST) | Useful |
| Kanban apply | `/console/kanban/apply/{id}` | - | Yes (POST) | Useful |
| Logs | `/console/logs` | Log list | No | No |
| Errors | `/console/errors/fingerprints` | Error summary | No | No |
| Health | `/console/health`, `/providers/health` | Health status | No | Useful |
| Projects list | `/console/projects` | Project list | No | No |
| Projects CRUD | `/console/projects`, `/console/projects/{id}` | - | Yes (POST/PATCH/DELETE) | No |

**Essential mappings**: 10 (intake list/detail, prompts list/detail, deliveries list/detail/retry, health, Kanban apply)

**Total mappings**: 50+

**~80% avoidable**

---

## 12. Runtime and Deployment Shape

### Local Development

**Backend**:
```bash
cd /lump/apps/prompt-forge
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Terminal 1 - API
PYTHONPATH=. uvicorn promptforge_services.api:app --host 127.0.0.1 --port 8090 --reload

# Terminal 2 - Watcher
PYTHONPATH=. python3 -m promptforge_watcher
```

**Frontend**:
```bash
cd /lump/apps/prompt-forge-console
npm install
npm run dev
```

**Access**:
- Backend API: `http://localhost:8090`
- Frontend: `http://localhost:5173`

---

### Docker Compose Stack

**Services**:
1. `postgres` - PostgreSQL 16 database
2. `n8n` - n8n workflow orchestration
3. `promptforge-shim` - Codex API shim (optional)
4. `promptforge-api` - FastAPI backend
5. `promptforge-watcher` - Filesystem watcher
6. `promptforge-console` - Nginx-served frontend

**Ports**:
- `15439` - Postgres (host)
- `5678` - n8n (host)
- `8765` - Codex shim (host)
- `8090` - Backend API (host)
- `5174` - Frontend (host)

**Volumes**:
- `promptforge_postgres_data` - Database persistence
- `promptforge_n8n_data` - n8n workflow data
- Bind mount: Obsidian vault (`PROMPTFORGE_VAULT_SOURCE` → `/vault`)
- Bind mount: Source code (dev mode)

**Networks**:
- Bridge network with `host.docker.internal` for Kanban access

**Dependencies**:
- console → api
- watcher → postgres, api, shim, n8n
- api → postgres, shim
- n8n → postgres

**Startup**:
```bash
docker compose up -d --build
./scripts/bootstrap_stack.sh
```

**Operational Burden**:
- 6 containers to manage
- Database migrations
- n8n workflow imports
- Secret management across services
- Volume backups
- Container health checks
- Log aggregation

---

### Deployment Shape Assessment

**Is this too heavy for Kanban companion app?**

**Yes**:
- 6 Docker containers for local-only single-user tool
- Postgres database for ~100 records
- n8n workflow engine unused in Kanban-only flow
- Multiple ports exposed
- Complex startup scripts
- Inter-service dependencies

**Minimal alternative**:
- Single Python script or Flask/FastAPI app
- SQLite database or flat files
- Direct Kanban HTTP POST
- Single Docker container or native Python process
- ~1 port

**Deployment complexity**: **10x simpler** with minimal implementation

---

## 13. What Is Worth Reusing

### 1. Speech Artifact Cleanup Logic

**Source**: `/lump/apps/prompt-forge/promptforge_services/pipeline.py` (preprocessing)

**Why useful**: Obsidian speech-to-text produces artifacts ("um", "uh", incorrect punctuation, etc.)

**How to reuse**: Extract regex patterns and replacement rules as standalone function

**Dependencies**: `regex` library (optional), `rapidfuzz` (optional for fuzzy matching)

**Example patterns** (inferred from code):
```python
# Remove filler words
text = re.sub(r'\b(um|uh|like|you know)\b', '', text, flags=re.IGNORECASE)

# Normalize whitespace
text = re.sub(r'\s+', ' ', text).strip()

# Fix common speech-to-text errors
text = text.replace('gonna', 'going to')
text = text.replace('wanna', 'want to')
```

---

### 2. Prompt Formatting Templates

**Source**: `/lump/apps/prompt-forge/docs/planning/` (template examples)

**Why useful**: Jinja2 templates for rendering structured prompts work well

**How to reuse**: Copy template files, use Jinja2 for rendering

**Dependencies**: `jinja2`

**Example template structure**:
```jinja2
# {{ project_slug | upper }} - {{ prompt_type | title }}

## Intent
{{ intent }}

## Context
{{ normalized_transcript }}

{% if notes %}
## Notes
{% for note in notes %}
- {{ note }}
{% endfor %}
{% endif %}

## Deliverable
{{ destination }} → {{ target_identifier }}
```

---

### 3. Markdown/Frontmatter Parser

**Source**: Watcher uses `python-frontmatter`

**Why useful**: Obsidian notes use YAML frontmatter

**How to reuse**: Use `python-frontmatter` library directly

**Dependencies**: `python-frontmatter`, `PyYAML`

**Example**:
```python
import frontmatter

with open('note.md') as f:
    post = frontmatter.load(f)

metadata = post.metadata  # dict
content = post.content    # str
```

---

### 4. Project Detection Rules

**Source**: `/lump/apps/prompt-forge/promptforge_services/pipeline.py` (preprocessing)

**Why useful**: Auto-detect project from directives or transcript content

**How to reuse**: Extract project detection function

**Dependencies**: `rapidfuzz` (fuzzy matching)

**Example**:
```python
from rapidfuzz import fuzz

def detect_project(transcript: str, known_projects: list[str]) -> str:
    # Check for explicit directive
    match = re.search(r'#project:(\w+)', transcript, re.IGNORECASE)
    if match:
        return match.group(1)
    
    # Fuzzy match transcript keywords
    for project in known_projects:
        if fuzz.partial_ratio(project, transcript.lower()) > 80:
            return project
    
    return 'inbox'  # default
```

---

### 5. Review Queue Concept

**Source**: `prompt_generations.requires_review` field, frontend `/review` page

**Why useful**: Human-in-the-loop for uncertain prompts

**How to reuse**: Flag prompts for review, display in separate view

**Dependencies**: None (just a boolean field)

**Implementation**: Add `requires_review` boolean to prompt record, filter by it in UI

---

### 6. Prompt Preview UI

**Source**: `/lump/apps/prompt-forge-console/src/components/pf/MarkdownPreview.tsx`

**Why useful**: Preview rendered markdown before delivery

**How to reuse**: Copy React component

**Dependencies**: React, markdown renderer library

**Alternative**: Use existing frontend markdown component or lightweight library like `marked`

---

### 7. Delivery Record Concept

**Source**: `deliveries` table, delivery status tracking

**Why useful**: Track delivery attempts, success/failure, error messages

**How to reuse**: Simplified delivery record with just `id`, `prompt_id`, `kanban_workspace_id`, `status`, `error_text`, `created_at`, `delivered_at`

**Dependencies**: None

---

### 8. Error Taxonomy

**Source**: `workflow_error_records.error_class`, `error_code`

**Why useful**: Structured error handling

**How to reuse**: Define error classes (e.g., `VaultReadError`, `TemplateRenderError`, `KanbanAPIError`)

**Dependencies**: None

**Example**:
```python
class PromptForgeError(Exception):
    code: str = "PF_ERROR"

class VaultReadError(PromptForgeError):
    code = "VAULT_READ_ERROR"

class KanbanAPIError(PromptForgeError):
    code = "KANBAN_API_ERROR"
```

---

## 14. What Must Be Avoided

### 1. Multi-Project/Multi-User Architecture

**What to avoid**: Projects table, scope precedence (global/user/project), user ID tracking

**Why it hurt**: Added 10+ foreign keys, scope resolution logic, complex queries, multi-tenant UI

**Sign we're repeating it**: Adding a "projects" or "users" table, scope enums

**Minimal alternative**: Single project hardcoded or from env var, no user tracking

---

### 2. Database-Backed Configuration

**What to avoid**: `console_runtime_settings`, `rulesets`, `prompt_templates`, `term_dictionary` in database

**Why it hurt**: CRUD endpoints, versioning logic, activation toggles, scope precedence, migration overhead

**Sign we're repeating it**: Storing config in Postgres, building admin UI for config

**Minimal alternative**: `.env` file, YAML config file, Python constants, file-based templates

---

### 3. Append-Only Audit Trails

**What to avoid**: `transcript_revisions`, `processing_runs`, `llm_runs`, `workflow_error_records` with full history

**Why it hurt**: Database bloat, complex queries, unused data, over-engineering

**Sign we're repeating it**: Creating "revisions" or "history" tables, append-only constraints

**Minimal alternative**: Log final state only, use file-based logs for errors

---

### 4. Generic Rule Engine

**What to avoid**: JSON-based rule definitions, match conditions, action execution, rule priority sorting

**Why it hurt**: Complex UI, fragile JSON schemas, over-abstraction

**Sign we're repeating it**: Building a rule builder UI, JSON schema for rules

**Minimal alternative**: Hardcoded Python functions, simple regex patterns in code

---

### 5. Multi-Target Delivery Registry

**What to avoid**: `delivery_targets`, `delivery_session_registry`, tmux session tracking, target health probing

**Why it hurt**: Complex session management, health check logic, multi-target routing

**Sign we're repeating it**: Creating a "targets" table, session registry, health checks

**Minimal alternative**: Hardcoded Kanban workspace URL, single delivery target

---

### 6. LLM Provider Abstraction

**What to avoid**: Multi-provider router, fallback chains, provider health checks, token usage tracking

**Why it hurt**: Provider-specific adapters, complex config, unused in deterministic mode

**Sign we're repeating it**: Building a provider abstraction layer, supporting multiple LLMs

**Minimal alternative**: Skip LLM entirely (deterministic mode), or single provider if needed

---

### 7. n8n Integration

**What to avoid**: n8n container, webhook posting, workflow imports

**Why it hurt**: Extra service dependency, workflow management overhead, unused for Kanban-only flow

**Sign we're repeating it**: Adding workflow orchestration, webhook architecture

**Minimal alternative**: Direct function calls, no webhook layer

---

### 8. Over-Normalized Database Schema

**What to avoid**: 15-table schema, 1:1 indirection (intake_notes → utterances), separate revision tables

**Why it hurt**: Join complexity, migration overhead, query performance, overkill for small datasets

**Sign we're repeating it**: Creating normalized tables for 1:1 relationships, junction tables for simple links

**Minimal alternative**: 3 tables max (intake, prompts, deliveries), or flat files

---

### 9. Metrics/Dashboard Infrastructure

**What to avoid**: Queue depth calculations, throughput aggregations, SLA tracking, charts

**Why it hurt**: Complex queries, polling overhead, unused by single-user

**Sign we're repeating it**: Building dashboard with metrics, chart libraries, aggregation queries

**Minimal alternative**: Skip metrics entirely, or simple count queries

---

### 10. Complex Settings UI

**What to avoid**: 42KB Settings.tsx, tabbed UI, encrypted secrets, runtime reconfiguration

**Why it hurt**: Largest frontend file, complex form validation, secrets encryption overhead

**Sign we're repeating it**: Building multi-tab settings UI, secret encryption, DB-backed settings

**Minimal alternative**: Simple form with 3-5 fields (Kanban URL, workspace ID, API key)

---

### 11. Premature Abstraction

**What to avoid**: Generic "contracts", versioned templates, scoped rules, producer types

**Why it hurt**: Abstract layers that don't pay for themselves at small scale

**Sign we're repeating it**: Creating "contracts", "producers", "scopes", "versions" before they're needed

**Minimal alternative**: Start concrete, abstract when second use case emerges

---

### 12. Console Everywhere

**What to avoid**: 15-page admin console, full CRUD for all entities, debug pages

**Why it hurt**: Massive frontend, maintenance burden, unused features

**Sign we're repeating it**: Building admin pages for internal data structures

**Minimal alternative**: 3-5 pages max (intake → prompts → deliveries), minimal UI

---

### 13. Over-Engineered Error Handling

**What to avoid**: Error fingerprinting, error grouping, human intervention flags, error contexts

**Why it hurt**: Complex error table, unused grouping logic

**Sign we're repeating it**: Building error grouping, fingerprint hashing, intervention workflows

**Minimal alternative**: Simple error log (stderr or file), error message in delivery record

---

## 15. Minimal Replacement Recommendation

Based on audit, here's the smallest new system that preserves useful parts:

### Backend Responsibilities

1. **Watch Obsidian vault** for new markdown notes
2. **Parse frontmatter + body** (project, transcript)
3. **Clean transcript** (remove speech artifacts, normalize whitespace)
4. **Render prompt** from Jinja2 template
5. **POST to Kanban** workspace
6. **Update note frontmatter** with delivery status
7. **Log errors** to stderr

**Out of scope**: n8n, LLM, multi-target delivery, rules engine, template versioning, metrics, audit trails

---

### Frontend Responsibilities

1. **List intake notes** (read-only)
2. **List generated prompts** (read-only)
3. **List deliveries** with status
4. **Retry failed deliveries**
5. **Configure Kanban URL/workspace**

**Out of scope**: Dashboard, metrics, rules UI, templates UI, dictionary UI, targets UI, projects UI, logs UI, pipeline visualization

---

### Data Model

**3 tables** (or flat files):

1. **intake_notes**
   - `id`, `file_path`, `title`, `project`, `transcript`, `status`, `created_at`, `processed_at`, `error`

2. **prompts**
   - `id`, `intake_note_id`, `rendered_markdown`, `requires_review`, `created_at`

3. **deliveries**
   - `id`, `prompt_id`, `kanban_workspace_id`, `status`, `error`, `created_at`, `delivered_at`

**Or**: Skip database entirely, use frontmatter + markdown files for state

---

### API Endpoints

**6 endpoints**:

1. `GET /health` - Health check
2. `GET /intake` - List intake notes
3. `GET /prompts` - List prompts
4. `GET /deliveries` - List deliveries
5. `POST /deliveries/{id}/retry` - Retry failed delivery
6. `PATCH /settings` - Update Kanban config

---

### Processing Lifecycle

```
1. Note created in Obsidian vault/Inbox/Voice/
2. Watcher detects file event
3. Parse frontmatter (project: X, transcript: "...")
4. Clean transcript (regex cleanup)
5. Render template (Jinja2)
6. POST to Kanban workspace API
7. Update frontmatter (status: delivered, delivery_id: Y)
8. Move note to vault/Processed/Voice/ (optional)
```

**No database writes** (use frontmatter for state), **no intermediate API calls**, **no webhook**, **no LLM**

---

### Explicitly Out of Scope

- Multi-project support
- User/role management
- Rule engine
- Template versioning
- Term dictionary
- Delivery targets beyond Kanban
- n8n integration
- LLM review/inference
- Metrics/dashboard
- Admin console for config
- Error fingerprinting
- Audit trails
- Session tracking

**Defer until after first working Kanban delivery loop**: LLM review, multi-workspace delivery, advanced cleanup rules

---

## 16. Final Summary

### What PromptForge Backend Actually Became

A **production-grade multi-user platform** with:
- 15-table normalized Postgres schema
- Multi-project/scope architecture
- Generic rule engine with versioning
- Template versioning and activation system
- Multi-target delivery with session tracking
- LLM provider abstraction (5+ providers)
- n8n workflow integration
- Append-only audit trails
- Secrets encryption infrastructure
- 60+ API endpoints (7 core, 50+ console)
- Complex processing pipeline with 10+ stages
- 8-12 database writes per note

**Complexity level**: **Enterprise SaaS product**, not localhost single-user tool

---

### What PromptForge Frontend Actually Became

A **full-featured admin console** with:
- 15 pages (dashboard, intake, prompts, deliveries, targets, rules, templates, dictionary, settings, logs, health, review, pipeline, projects, 404)
- 126 TypeScript files
- 40+ reusable UI components
- Advanced table features (virtualization, filters, pagination, sorting)
- Multi-tab settings UI (42KB file)
- Rule/template/dictionary editors
- Charts and metrics
- Real-time updates (react-query polling)

**Complexity level**: **Multi-page enterprise admin portal**, not minimal companion UI

---

### Three Most Valuable Pieces to Salvage

1. **Speech artifact cleanup logic** - Regex patterns for cleaning Obsidian voice transcripts
2. **Jinja2 prompt templates** - Template structure for rendering structured prompts
3. **Delivery record tracking** - Simple delivery status tracking (queued → delivered/failed)

---

### Three Most Dangerous Complexity Traps to Avoid

1. **Database-backed configuration** (rules, templates, settings) - Use files instead
2. **Multi-project/multi-target architecture** - Single project, single Kanban target
3. **Over-normalized database schema** (15 tables, append-only audit trails) - 3 tables max or flat files

---

### Recommended Smallest Possible New Implementation

**Backend**: Single Python script (Flask/FastAPI) or lightweight daemon

**Data**: SQLite (3 tables) or frontmatter-only (no database)

**Pipeline**: Watch folder → parse note → clean transcript → render template → POST Kanban → update frontmatter (5 steps, not 10+)

**API**: 6 endpoints (health, intake, prompts, deliveries, retry, settings)

**Frontend**: 3 pages (intake list, prompt queue, delivery status) or single-page app

**Dependencies**: `watchdog`, `python-frontmatter`, `jinja2`, `httpx`, `fastapi`/`flask` (5-6 libraries)

**Deployment**: Single Python process or Docker container (not 6-container stack)

**Config**: `.env` file or command-line args (not database-backed settings)

**Focus**: Obsidian note → cleaned intent → generated prompt package → human review → Kanban task delivery

**Estimated complexity reduction**: **10x simpler** (60 → 6 endpoints, 15 → 3 tables, 15 → 3 pages, 6 → 1 containers)

---

### Open Questions Requiring Human Decision

1. **Database vs frontmatter-only state**: Should we use SQLite/Postgres, or store all state in Obsidian note frontmatter?

2. **Kanban workspace binding**: Should Kanban workspace ID be configured once (env var), or support multiple workspaces?

3. **Review queue**: Should we build a review queue UI, or just flag prompts in frontmatter and handle review in Obsidian?

4. **Template storage**: File-based templates (git-versioned) or database-backed (runtime editing)?

5. **Error handling**: Simple error logging (stderr/file) or delivery error records in database?

6. **Frontend hosting**: Serve frontend from backend (FastAPI static files) or separate Nginx container?

7. **Cleanup rules**: Hardcoded Python functions or YAML config file?

8. **Project detection**: Hardcoded project name or auto-detect from transcript?

9. **Note writeback**: Update source note frontmatter and move to processed folder, or leave in place?

10. **Retry mechanism**: Manual retry via console UI, or auto-retry with exponential backoff?

---

**End of Audit Report**
