# PromptForge Frontend and Backend Audit

Date: 2026-04-28

Scope audited (read-only):
- Backend: `/lump/apps/prompt-forge`
- Frontend: `/lump/apps/prompt-forge-console`

Method:
- Codebase inspection only (no refactor, no edits to existing files)
- Claims tied to concrete source paths
- Secrets redacted

Fact vs inference:
- `Fact:` directly observed in files.
- `Inference:` reasoned from observed code and config.

---

## 1) Repository Discovery

### Backend repo: `prompt-forge`

| Item | Finding | Evidence |
|---|---|---|
| Absolute path | `/lump/apps/prompt-forge` | `/lump/apps/prompt-forge` |
| Primary language | Python | `/lump/apps/prompt-forge/pyproject.toml` |
| Framework | FastAPI + Watchdog | `/lump/apps/prompt-forge/promptforge_services/api.py`, `/lump/apps/prompt-forge/promptforge_watcher/watcher.py` |
| Package manager | pip/setuptools (`pip install -e .`) | `/lump/apps/prompt-forge/README.md`, `/lump/apps/prompt-forge/pyproject.toml` |
| Runtime expectation | Python `>=3.11` | `/lump/apps/prompt-forge/pyproject.toml` |
| Dev commands | `uvicorn promptforge_services.api:app`, `python -m promptforge_watcher` | `/lump/apps/prompt-forge/README.md` |
| Test commands | `python3 -m pytest -q` | `/lump/apps/prompt-forge/README.md` |
| Build/deploy files | Dockerfiles + compose | `/lump/apps/prompt-forge/Dockerfile`, `/lump/apps/prompt-forge/Dockerfile.watcher`, `/lump/apps/prompt-forge/Dockerfile.shim`, `/lump/apps/prompt-forge/docker-compose.yml`, `/lump/apps/prompt-forge/docker-compose.dev.yml` |
| Env files | `.env`, `.env.example` | `/lump/apps/prompt-forge/.env`, `/lump/apps/prompt-forge/.env.example` |
| Setup docs | README + planning docs | `/lump/apps/prompt-forge/README.md`, `/lump/apps/prompt-forge/docs/planning/README.md` |
| Schema/migrations | SQL schema + migration SQLs | `/lump/apps/prompt-forge/docs/planning/promptforge_postgres_schema.sql`, `/lump/apps/prompt-forge/docs/planning/*.sql` |

### Frontend repo: `prompt-forge-console`

| Item | Finding | Evidence |
|---|---|---|
| Absolute path | `/lump/apps/prompt-forge-console` | `/lump/apps/prompt-forge-console` |
| Primary language | TypeScript | `/lump/apps/prompt-forge-console/src` |
| Framework | React + Vite | `/lump/apps/prompt-forge-console/src/App.tsx`, `/lump/apps/prompt-forge-console/vite.config.ts` |
| Package manager | npm (Bun locks also present) | `/lump/apps/prompt-forge-console/package.json`, `/lump/apps/prompt-forge-console/package-lock.json`, `/lump/apps/prompt-forge-console/bun.lockb` |
| Runtime expectation | Node 20 (Docker build stage) | `/lump/apps/prompt-forge-console/Dockerfile` |
| Dev/build/test | `vite`, `vite build`, `vitest run`, `eslint` | `/lump/apps/prompt-forge-console/package.json` |
| Deploy files | Docker + nginx reverse proxy | `/lump/apps/prompt-forge-console/Dockerfile`, `/lump/apps/prompt-forge-console/nginx.conf` |
| Env vars | `VITE_PROMPTFORGE_API_BASE` etc. | `/lump/apps/prompt-forge-console/Dockerfile`, `/lump/apps/prompt-forge-console/src/services/promptforge/api.ts`, `/lump/apps/prompt-forge-console/src/services/promptforge/config.ts` |
| Setup docs | README is placeholder | `/lump/apps/prompt-forge-console/README.md` |

### Environment variables (redacted)

Backend (`.env.example`):
- `POSTGRES_PASSWORD=<redacted>`
- `N8N_ENCRYPTION_KEY=<redacted>`
- `PROMPTFORGE_DATABASE_URL=postgresql://...`
- `PROMPTFORGE_VAULT_PATH`
- `PROMPTFORGE_N8N_WEBHOOK_URL`
- `PROMPTFORGE_KANBAN_BASE_URL`
- `PROMPTFORGE_KANBAN_WORKSPACE_ID`
- `PROMPTFORGE_WEBHOOK_ENABLED`
- watcher folder vars
- LLM base/model vars

Evidence: `/lump/apps/prompt-forge/.env.example`

---

## 2) Backend: High-Level Architecture

| Concern | What exists now | Evidence |
|---|---|---|
| Framework | FastAPI app | `/lump/apps/prompt-forge/promptforge_services/api.py` |
| Entrypoints | API + watcher module | `/lump/apps/prompt-forge/promptforge_services/api.py`, `/lump/apps/prompt-forge/promptforge_watcher/__main__.py` |
| API structure | Core contract endpoints + large `/console` router | `/lump/apps/prompt-forge/promptforge_services/api.py`, `/lump/apps/prompt-forge/promptforge_services/console_api.py` |
| Module organization | `promptforge_services` (API/pipeline/LLM/console), `promptforge_watcher` (ingest/watch/writeback/repo) | repo tree |
| Service wiring | Direct imports/function calls (no IoC container) | `/lump/apps/prompt-forge/promptforge_services/api.py` |
| DB layer | psycopg direct SQL in query/repo modules | `/lump/apps/prompt-forge/promptforge_services/console_queries.py`, `/lump/apps/prompt-forge/promptforge_watcher/repository.py` |
| Migration system | SQL files + startup helper migration | `/lump/apps/prompt-forge/docs/planning/*.sql`, `/lump/apps/prompt-forge/promptforge_services/schema_migrations.py` |
| Background workers | Filesystem watcher with startup catchup + event loop | `/lump/apps/prompt-forge/promptforge_watcher/watcher.py` |
| Queue/jobs | Delivery status lifecycle in DB, no dedicated broker | `/lump/apps/prompt-forge/docs/planning/promptforge_postgres_schema.sql` |
| External integrations | n8n webhook, Kanban TRPC, optional LLM provider calls | `/lump/apps/prompt-forge/promptforge_watcher/webhook.py`, `/lump/apps/prompt-forge/promptforge_services/kanban_client.py`, `/lump/apps/prompt-forge/promptforge_services/llm/*` |
| LLM integration | Router + provider abstractions (openai/anthropic/openai_compatible/ollama/codex_exec) | `/lump/apps/prompt-forge/promptforge_services/llm/router.py`, `/lump/apps/prompt-forge/promptforge_services/llm/providers.py` |
| n8n integration | Optional webhook emit + workflow assets | `/lump/apps/prompt-forge/promptforge_watcher/webhook.py`, `/lump/apps/prompt-forge/docs/planning/n8n_workflows/*` |
| Auth/security | No end-user auth model; role behavior mostly UI-level; secret encryption utilities for console settings | `/lump/apps/prompt-forge/promptforge_services/console_models.py`, `/lump/apps/prompt-forge/promptforge_services/secrets.py` |
| Logging/metrics/tracing | request logger middleware + DB-derived metric endpoints | `/lump/apps/prompt-forge/promptforge_services/api.py`, `/lump/apps/prompt-forge/promptforge_services/console_api.py` |
| Error handling | HTTPException mapping + workflow error table | `/lump/apps/prompt-forge/promptforge_services/api.py`, `/lump/apps/prompt-forge/docs/planning/promptforge_postgres_schema.sql` |

---

## 3) Backend: Domain Model and Database

### Enums (selected)
Fact: schema defines many enums: `pf_scope`, `pf_note_status`, `pf_revision_kind`, `pf_rule_type`, `pf_prompt_generation_status`, `pf_destination`, `pf_target_type`, `pf_delivery_mode`, `pf_delivery_status`, `pf_processing_status`, `pf_priority`.

Evidence: `/lump/apps/prompt-forge/docs/planning/promptforge_postgres_schema.sql`

### Tables (all major)

| Table | Source | Key fields | Relationships/constraints | Essential for new minimal system? |
|---|---|---|---|---|
| `projects` | schema sql | slug/name/defaults/active_ruleset_id | unique slug, FK to rulesets | Useful (simplified) |
| `intake_notes` | schema sql | note path/hash/frontmatter/body/status/route_json | unique `note_relative_path`, FK project | Essential |
| `utterances` | schema sql | raw_text/directive_text/scope/capture_type | FK intake_note + project | Essential |
| `transcript_revisions` | schema sql | revision_kind/content/producer/metadata | FK utterance | Useful (simplified) |
| `rulesets` | schema sql | scope/version/is_active | unique + active indexes | Usually avoid for MVP |
| `rules` | schema sql | rule_type/priority/enabled/match/action json | FK ruleset | Simplify/avoid |
| `term_dictionary` | schema sql | source_term/canonical_term/confidence | scoped uniqueness | Maybe useful in slim form |
| `prompt_templates` | schema sql | prompt_type/version/body/output_contract/is_active | scoped uniques | Useful (single template) |
| `prompt_generations` | schema sql | structured_output/final_markdown/requires_review/status | FK utterance/project/template/ruleset | Essential |
| `llm_runs` | schema sql | provider/model/mode/latency/tokens/findings | FK utterance + prompt_generation | Optional |
| `delivery_targets` | schema sql | target type/id/scope/default/safe/config | unique target_type+identifier | Avoid for MVP unless multi-target |
| `delivery_session_registry` | schema sql | session tracking per target | chat/cli session constraints | Avoid |
| `deliveries` | schema sql | destination/target/mode/status/priority/dispatch json/error | FK prompt_generation/target | Essential |
| `processing_runs` | schema sql | workflow_name/status/stages/trace | FK utterance | Useful (minimal) |
| `workflow_error_records` | schema sql | typed error rows with many optional refs | multiple FK links/indexes | Useful concept, simpler impl |
| `console_runtime_settings` | schema sql | scope/project/key/value_json | scoped unique keys | Avoid for MVP |
| `console_secret_settings` | schema sql | scoped secrets + ciphertext metadata | scoped unique keys | Avoid for MVP |
| `console_admin_audit_log` | schema sql | action/actor/payload | index on action+created | Avoid for MVP |

Who creates/updates lifecycle (fact):
- Watcher creates intake/utterance/revisions/prompt_generation/delivery/processing_run via repository import bundle.
- Console API mutates delivery/rules/templates/dictionary/settings and logs admin actions.

Evidence: `/lump/apps/prompt-forge/promptforge_watcher/repository.py`, `/lump/apps/prompt-forge/promptforge_services/console_api.py`

---

## 4) Backend: API Surface

### Core endpoints
- `GET /_healthz`
- `GET /health`
- `GET /providers/health`
- `POST /preprocess`
- `POST /validate`
- `POST /render`
- `POST /prepare-delivery`

Evidence: `/lump/apps/prompt-forge/promptforge_services/api.py`

### Console endpoints (inventory)
Fact: `/console` includes bootstrap, settings, project/intake/prompt/delivery/rules/templates/targets/logs/metrics/kanban/llm assist/errors endpoints.

Primary endpoint declarations:
- `/console/bootstrap`, `/console/health`, `/console/settings`, `/console/settings/runtime`
- `/console/projects`
- `/console/intake`, `/console/intake/{id}`, `/console/intake/{id}/archive`
- `/console/lineage/{intakeNoteId}`
- `/console/prompts`, `/console/prompts/{id}/force-review`, `/console/prompts/{id}/clone`, `/console/prompts/{id}/priority`, `/console/prompts/{id}/kanban/preview`, `/console/prompts/{id}/kanban/apply`
- `/console/deliveries`, `/console/deliveries/{id}/dispatch`, `/console/deliveries/{id}/retry`, `/console/deliveries/{id}/reroute`, `/console/deliveries/{id}/status`
- `/console/rulesets`, `/console/rules`, `/console/rulesets/{id}/dry-run`, `/console/rules/{id}`
- `/console/dictionary`
- `/console/templates`, `/console/templates/{id}`, `/console/templates/{id}/activate`
- `/console/targets`, `/console/targets/{id}/health`, `/console/targets/{id}/dispatch`
- `/console/logs`, `/console/metrics/*`
- `/console/kanban/workspaces`
- `/console/llm/assist`
- `/console/errors/recent`, `/console/errors/{id}/dismiss`

Evidence: `/lump/apps/prompt-forge/promptforge_services/console_api.py`

Inference: this exceeds a minimal intake->review->deliver API by a wide margin.

---

## 5) Backend: Processing Pipeline (note to final output)

Fact path:
1. Watcher starts, optional startup schema patch, scans watch folder for markdown.
2. For each candidate note, computes hash and eligibility checks.
3. Parses note/frontmatter/control/transcript and resolves route metadata.
4. Runs deterministic preprocess -> validate -> render -> prepare-delivery.
5. Persists bundle to repository (Postgres or in-memory).
6. Optional webhook emission to n8n.
7. Optional auto-dispatch (only `obsidian_note` target in watcher dispatch).
8. Writes back processed note with updated frontmatter/tags/status.
9. Updates delivery status after dispatch result.

Evidence:
- `/lump/apps/prompt-forge/promptforge_watcher/watcher.py`
- `/lump/apps/prompt-forge/promptforge_services/pipeline.py`
- `/lump/apps/prompt-forge/promptforge_watcher/repository.py`
- `/lump/apps/prompt-forge/promptforge_watcher/webhook.py`
- `/lump/apps/prompt-forge/promptforge_watcher/delivery.py`
- `/lump/apps/prompt-forge/promptforge_watcher/writeback.py`

Duplicates detection:
- hash guard in watcher (`seen_hashes`) and unique note path check in repository.

Evidence: `/lump/apps/prompt-forge/promptforge_watcher/watcher.py`, `/lump/apps/prompt-forge/promptforge_watcher/repository.py`

---

## 6) Backend: Complexity / Scope Creep Inventory

| Feature | Files | Solves | Complexity added | Recommendation |
|---|---|---|---|---|
| Large console mutation API | `promptforge_services/console_api.py` | ops/admin control | very high endpoint + policy surface | Avoid for new minimal app |
| Scope/project runtime + secrets DB | schema + `secrets.py` | configurable runtime | admin/security/migration burden | Simplify to env+single config |
| Multi-target delivery abstraction | schema + dispatch modules | future flexibility | branching target logic | Start single target (Kanban) |
| Session registry | schema (`delivery_session_registry`) | live sessions | heavy lifecycle complexity | Avoid |
| Rule engine tables and dry-run | schema + console endpoints | customization | governance + UX + precedence complexity | keep only small deterministic rule profile |
| n8n coupling | watcher webhook + workflow assets | automation | extra runtime dependency | Avoid in MVP |
| Metrics/log explorer endpoints | console queries/api | diagnostics | broad query surface | defer |
| Multi-provider LLM router | `llm/*` | provider portability | adapter complexity | start one provider or deterministic only |

---

## 7) Frontend: High-Level Architecture

| Concern | Finding | Evidence |
|---|---|---|
| Framework | React + Vite + TS | `/lump/apps/prompt-forge-console/src/App.tsx`, `/lump/apps/prompt-forge-console/vite.config.ts` |
| Entrypoint | `main.tsx` -> `App.tsx` | `/lump/apps/prompt-forge-console/src/main.tsx` |
| Routing | BrowserRouter with many pages | `/lump/apps/prompt-forge-console/src/App.tsx` |
| State | Zustand persisted store | `/lump/apps/prompt-forge-console/src/stores/app-store.ts` |
| API client pattern | typed fetch wrapper + React Query query keys | `/lump/apps/prompt-forge-console/src/services/promptforge/api.ts` |
| UI lib | shadcn/radix-style component suite | `/lump/apps/prompt-forge-console/src/components/ui/*` |
| Styling | Tailwind + CSS | `/lump/apps/prompt-forge-console/tailwind.config.ts`, `/lump/apps/prompt-forge-console/src/index.css` |
| Form/validation | react-hook-form + zod deps | `/lump/apps/prompt-forge-console/package.json` |
| Auth/session | no backend auth session; role switch in local store | `/lump/apps/prompt-forge-console/src/stores/app-store.ts`, `/lump/apps/prompt-forge-console/src/components/shell/RoleSwitcher.tsx` |
| Build/test tooling | Vite/Vitest/ESLint | `/lump/apps/prompt-forge-console/package.json` |
| Env vars | `VITE_PROMPTFORGE_API_BASE`, strict/fallback vars | `/lump/apps/prompt-forge-console/src/services/promptforge/api.ts`, `/lump/apps/prompt-forge-console/src/services/promptforge/config.ts` |
| Deploy assumptions | nginx proxies API paths to backend | `/lump/apps/prompt-forge-console/nginx.conf` |

---

## 8) Frontend: Screens and User Flows

Routes:
- `/dashboard`
- `/intake`
- `/intake/:id`
- `/pipeline`
- `/pipeline/:intakeNoteId`
- `/prompts`
- `/deliveries`
- `/review`
- `/rules`
- `/dictionary`
- `/templates`
- `/targets`
- `/logs`
- `/health`
- `/settings`

Evidence: `/lump/apps/prompt-forge-console/src/App.tsx`

Fact: each page calls corresponding `/console/*` endpoints through service layer.
Evidence: `/lump/apps/prompt-forge-console/src/services/promptforge/api.ts`, `/lump/apps/prompt-forge-console/src/pages/*.tsx`

MVP relevance inference:
- Essential: intake list/detail, prompt preview/review, delivery trigger/status.
- Avoid initially: dashboard, settings/admin, rules/templates/targets/log/metrics pages.

---

## 9) Frontend: Component and UI Complexity

Major groups:
- Shell/navigation: `/src/components/shell/*`
- Data/ops components: `/src/components/pf/*`
- Large generic UI toolkit: `/src/components/ui/*`

Notable complexity-heavy patterns:
- Data tables + filters
- Query inspector + catalog
- Route preview and pipeline lineage panels
- Kanban integration panel
- Many global states for role/theme/env/mock/debug/polling

Evidence:
- `/lump/apps/prompt-forge-console/src/components/pf/DataTable.tsx`
- `/lump/apps/prompt-forge-console/src/components/pf/QueryInspector.tsx`
- `/lump/apps/prompt-forge-console/src/components/pf/RoutePreview.tsx`
- `/lump/apps/prompt-forge-console/src/stores/app-store.ts`

---

## 10) Frontend: Complexity / Scope Creep Inventory

| Feature | Files | User value | Complexity cost | Recommendation |
|---|---|---|---|---|
| Full dashboard metrics | `pages/Dashboard.tsx` | quick ops snapshot | high query fanout | Defer |
| Multi-page admin/settings | `pages/Settings.tsx` | config control | very high state + mutation logic | Avoid in MVP |
| Rules/templates/dictionary CRUD | `pages/Rules.tsx`, `Templates.tsx`, `Dictionary.tsx` | customization | broad API/UI surface | simplify to one rules profile |
| Delivery target management | `pages/Targets.tsx` | multi-target ops | abstraction overhead | avoid unless needed |
| Logs/errors views | `pages/Logs.tsx`, `Review.tsx` | triage | additional non-core work | minimal error list only |

---

## 11) Frontend ↔ Backend Contract

API base config:
- Derived from runtime store + `VITE_PROMPTFORGE_API_BASE`
- Hydration bootstrap path default `/console/bootstrap`

Evidence: `/lump/apps/prompt-forge-console/src/services/promptforge/api.ts`, `/lump/apps/prompt-forge-console/src/stores/app-store.ts`

Error behavior:
- Typed `ApiError` + strict backend mode + optional mock fallback in development.

Evidence: `/lump/apps/prompt-forge-console/src/services/promptforge/errors.ts`, `/lump/apps/prompt-forge-console/src/services/promptforge/config.ts`

Contract map (high-level):

| Frontend screen/component | Backend endpoint | Data used | Mutation? | Essential for new app? |
|---|---|---|---|---|
| Intake | `/console/intake`, `/console/intake/{id}` | intake notes, lineage refs | no | yes |
| Pipeline detail | `/console/lineage/{id}` | revisions/runs/deliveries | no | useful |
| Prompts | `/console/prompts`, `/console/prompts/{id}/kanban/*` | prompt generations | yes | yes |
| Deliveries | `/console/deliveries`, retry/reroute/status | delivery records | yes | yes (subset) |
| Rules/Templates/Dictionary | `/console/rules*`, `/console/templates*`, `/console/dictionary*` | admin data | yes | avoid/defer |
| Logs/Metrics/Health | `/console/logs`, `/console/metrics/*`, `/providers/health` | diagnostics | mostly no | defer |
| Settings | `/console/settings*` | runtime/secrets | yes | avoid/defer |

---

## 12) Runtime and Deployment Shape

Fact (compose topology):
- `postgres`
- `n8n`
- `promptforge-shim`
- `promptforge-api`
- `promptforge-watcher`
- `promptforge-console`

Ports (default):
- API `8090`
- Console host `5174` -> container `80`
- n8n `5678`
- Postgres host `15439` -> `5432`
- Shim `8765`

Evidence: `/lump/apps/prompt-forge/docker-compose.yml`

Inference: this is operationally heavy for a minimalist Kanban companion app.

---

## 13) What Is Worth Reusing

| Reusable | Source | Why | How to reuse without drag |
|---|---|---|---|
| Deterministic preprocess + render contract | `promptforge_services/pipeline.py`, `promptforge_services/models.py` | core value path already implemented | keep only preprocess/render/prepare subset |
| Watcher debounce/hash/eligibility logic | `promptforge_watcher/watcher.py` | robust local ingest behavior | port minimal event loop + guards |
| Kanban preview/apply manifest concept | `promptforge_services/kanban_manifest_builder.py`, `kanban_client.py` | explicit preflight before send | keep single-task manifest flow only |
| Route metadata parsing | `promptforge_watcher/routing.py` | useful source-routing hints | keep if folder semantics matter |

---

## 14) What Must Be Avoided

| Avoid | Why it hurt | Sign you are repeating it | Minimal alternative |
|---|---|---|---|
| Full `/console` platform recreation | too broad for core workflow | endpoint count explodes early | keep a tiny API for queue/preview/deliver |
| Multi-scope runtime+secret admin systems | high maintenance and policy overhead | building settings/admin pages first | static config + env for MVP |
| Multi-target/session delivery abstractions | premature generalization | adding target/session tables early | single Kanban delivery path |
| Ruleset/version marketplace behavior | over-generalized customization | creating rules CRUD suite | one deterministic rule profile |
| n8n dependency as default path | extra component and failure domain | requiring workflow import to run | direct app->kanban integration |
| Rich metrics dashboards early | non-core spend | adding throughput/SLA boards before loop | simple logs + failed-delivery list |

---

## 15) Minimal Replacement Recommendation (audit-based)

Target flow only:
- Obsidian note -> cleaned intent -> prompt package -> human review -> Kanban task delivery.

Minimal backend responsibilities:
- Watch + ingest note metadata/text
- Deterministic cleanup + guardrails
- Build prompt package
- Persist note/prompt/delivery status in SQLite
- Expose read-only queue + preview + deliver endpoints

Minimal frontend responsibilities:
- Read-only list/detail views
- Prompt preview of exact payload to Kanban
- Manual send action + delivery result status

Minimal data model:
- `notes`
- `prompt_generations`
- `deliveries`
- optional `rule_profile` and `processing_events`

Explicitly out of scope initially:
- multi-user roles/auth
- n8n orchestration
- multi-target delivery management
- full settings admin console
- metrics dashboard suite
- template/rules marketplaces

---

## 16) Final Summary

What PromptForge backend actually became:
- A deterministic note compiler plus a broad operations platform (console APIs, extensive schema, optional integrations).

What PromptForge frontend actually became:
- A multi-page admin/ops console, not just a narrow intake->preview->deliver UI.

Top 3 pieces to salvage:
1. Deterministic preprocess/render pipeline.
2. Watcher ingest stability patterns.
3. Kanban preflight preview/apply pattern.

Top 3 complexity traps to avoid:
1. Expanding admin/settings/secret systems before core loop stability.
2. Building generalized delivery target/session architecture upfront.
3. Recreating dashboards/metrics/rules/templates platforms in MVP.

Recommended smallest new implementation:
- SQLite-backed watcher + deterministic transform + read-only preview UI + explicit Kanban send.

Open questions needing human decision:
1. Which exact guardrail/rule knobs must be user-configurable in MVP?
2. Should delivery retries be manual-only in v1?
3. Should note archiving/writeback remain in the MVP or be deferred?

