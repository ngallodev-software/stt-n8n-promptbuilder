# Cavekit: Data Model Simplification

## Scope

Defines the simplified Postgres schema for phase 2. Covers append-only delivery attempts, removal of future-facing admin/session tables, and minimum viable lineage. Does not cover migration execution details.

## Requirements

### R1: Delivery History Is Append-Only

**Description:** Every delivery attempt creates a new row. Prior attempts are never mutated. Retry and reroute create new attempt records. Latest state is a projection, not the authoritative record.

**Acceptance Criteria:**
- [ ] A `delivery_attempts` table (or equivalent append-only structure) exists with: `id`, `delivery_id`, `target_id`, `attempted_at`, `outcome` (pending/success/failure/skipped), `error_detail`, `response_payload`
- [ ] `POST /deliveries/{id}/retry` creates a new attempt row, does not mutate prior rows
- [ ] `POST /deliveries/{id}/reroute` creates a new attempt row with new target, does not mutate prior rows
- [ ] `PATCH /deliveries/{id}/status` is restricted to operator annotation only (e.g., marking reviewed), not attempt history
- [ ] A read-path projection of latest attempt state exists for UI convenience
- [ ] Integration test: retry twice → 3 attempt rows exist, none modified after creation

### R2: Session Registry Table Removed

**Description:** `delivery_session_registry` is removed. Live-session delivery is out of phase 2 scope.

**Acceptance Criteria:**
- [ ] `delivery_session_registry` table does not exist in the running schema
- [ ] Migration exists to drop the table if it was previously created
- [ ] No code references `delivery_session_registry`

### R3: Admin/Audit Tables Removed or Deferred

**Description:** `console_admin_audit_log` and `console_secret_settings` are removed or replaced with a no-op stub. Single-user local-only does not need admin audit logging or secret rotation schema.

**Acceptance Criteria:**
- [ ] `console_admin_audit_log` is dropped or not created in phase 2 schema
- [ ] `console_secret_settings` is dropped or not created in phase 2 schema
- [ ] No code writes to `console_admin_audit_log`
- [ ] `console_runtime_settings` remains (needed for runtime config persistence)

### R4: Minimum Viable Lineage

**Description:** The canonical compiler graph is: intake_note → utterance → transcript_revision → prompt_generation → delivery → delivery_attempt → workflow_error. No additional lineage tables or projections are introduced in phase 2.

**Acceptance Criteria:**
- [ ] All 7 entities above exist and are used
- [ ] No new lineage tables added in phase 2 without explicit requirement
- [ ] The `/lineage/{intakeNoteId}` endpoint returns data from existing tables without new projections
- [ ] Lineage query traces intake note → final delivery attempt in a single coherent response

### R5: No In-Place Mutation of Delivery State for History

**Description:** `deliveries` table current-state columns may exist for operational convenience (latest status, latest target), but the authoritative history is in `delivery_attempts`. Mutating `deliveries` rows is allowed only for current-state bookkeeping, not for recording attempt history.

**Acceptance Criteria:**
- [ ] Code comment or doc note distinguishes `deliveries` (current state) from `delivery_attempts` (history)
- [ ] No retry or reroute logic overwrites `deliveries.status` as its only history record
- [ ] `deliveries` row has a `latest_attempt_id` FK or equivalent for UI projection convenience

## Out of Scope

- Full event sourcing
- Multi-tenant data isolation
- Schema versioning beyond migration files
- Token/cost analytics tables
- Session management tables for multi-user

## Cross-References

- Depends on: cavekit-architecture.md R1 (Python owns state transitions)
- Depended on by: cavekit-console.md R1 (delivery ops UI reads attempt history)
- See also: cavekit-intake-writeback.md R2 (archive semantics tied to intake_notes table)
