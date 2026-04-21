# Cavekit: Ops Baseline

## Scope

Defines the minimum operational posture for phase 2. Covers localhost-only runtime defaults, startup/runbook documentation, backup/restore, restore verification, and minimal failure visibility. Does not introduce observability tooling beyond basic log access.

## Requirements

### R1: Localhost-Only Runtime Default

**Description:** Both the watcher and the API bind to localhost by default. No remote exposure. Documentation explicitly states this is not safe for network exposure.

**Acceptance Criteria:**
- [ ] API server default bind address is `127.0.0.1` (not `0.0.0.0`)
- [ ] Watcher does not open any listening socket
- [ ] `README` or `RUNBOOK.md` contains explicit statement: "This application is not safe for network exposure. Bind to localhost only."
- [ ] No configuration option silently enables `0.0.0.0` binding without a loud warning in logs

### R2: Startup and Runbook Documentation Exists

**Description:** A `RUNBOOK.md` (or equivalent) exists that covers: how to start the watcher, how to start the API, how to check system health, how to stop gracefully, and what to do when a note fails to process.

**Acceptance Criteria:**
- [ ] `RUNBOOK.md` exists at repo root or `docs/`
- [ ] Runbook covers: start watcher, start API, health check command, graceful stop
- [ ] Runbook covers: what to check when a note fails (where to find error records, how to reprocess)
- [ ] Runbook covers: how to check queue depth (console URL or direct DB query)

### R3: Backup and Restore Procedures Documented

**Description:** A documented procedure exists for backing up Postgres and the vault, restoring from backup, and verifying restore integrity.

**Acceptance Criteria:**
- [ ] Backup procedure documented: `pg_dump` command with correct connection args
- [ ] Restore procedure documented: `pg_restore` or `psql` command
- [ ] Vault backup documented: a command that produces a complete copy of the vault directory (e.g., `rsync -av <vault_root>/ <backup_dest>/`)
- [ ] Restore verification checklist exists: at minimum, check row counts in key tables and health endpoint responds

### R4: Minimal Failure Visibility in Console

**Description:** The console shows actionable failures: recent workflow errors tied to specific notes and deliveries, plus a compact recent-event feed. No broad observability UI.

**Acceptance Criteria:**
- [ ] Console displays `workflow_error_records` for the last 24 hours, grouped by note/delivery
- [ ] Each error entry shows: note path or delivery ID, error type, message, timestamp
- [ ] Operator can dismiss/acknowledge an error from the console
- [ ] No separate log viewer, metrics dashboard, or trace UI built in phase 2

### R5: Health Endpoint Returns Truthful Status

**Description:** `GET /health` (or equivalent) returns a truthful operational status: DB connectivity, watcher running state, vault path accessibility.

**Acceptance Criteria:**
- [ ] `/health` returns `{ "db": "ok"|"error", "vault": "ok"|"error", "watcher": "running"|"unknown" }`
- [ ] DB check performs a real lightweight query (e.g., `SELECT 1`)
- [ ] Vault check verifies the configured vault path exists and is readable
- [ ] Response time < 200ms

## Out of Scope

- Prometheus/Grafana integration
- Distributed tracing
- Log aggregation services
- Alerting/notification pipelines
- Multi-environment (staging/prod) deployment
- Container orchestration

## Cross-References

- Depends on: cavekit-architecture.md R1 (Python-owned runtime to describe in runbook)
- See also: cavekit-console.md R4 (failure visibility is part of console, not separate stack)
