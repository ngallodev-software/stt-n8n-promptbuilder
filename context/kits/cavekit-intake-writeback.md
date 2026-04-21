# Cavekit: Intake & Writeback Contract

## Scope

Defines the strict note structure required for intake, parse failure behavior, queue semantics, archive behavior after processing, and writeback semantics. Optimizes for determinism over rescue heuristics.

## Requirements

### R1: Note Structure Is Strict

**Description:** A valid intake note must contain exactly `## Control` and `## Transcript` sections. Notes without these sections fail fast. No heuristic fallback.

**Acceptance Criteria:**
- [ ] Parser checks for presence of `## Control` section; fails with structured error if absent
- [ ] Parser checks for presence of `## Transcript` section; fails with structured error if absent
- [ ] Malformed or missing section structure produces a `workflow_error_records` row with `error_type=parse_failure` and a human-readable message
- [ ] Note file remains in place on parse failure; it is not moved, deleted, or renamed
- [ ] No heuristic section detection (e.g., "first H2 becomes Control") occurs

### R2: Parse Failure Behavior Is Explicit

**Description:** Parse failures stop processing for that note and write an error record. The watcher continues to process other notes.

**Acceptance Criteria:**
- [ ] `workflow_error_records` row written for every parse failure
- [ ] Error row includes: `note_path`, `error_type`, `error_message`, `failed_at`
- [ ] Note file is not deleted or moved on parse failure; it remains in place for operator review
- [ ] Console shows parse failures in the failure visibility feed (Gate 3: operator can see it)

### R3: Queue Semantics Are Explicit

**Description:** `queue_only` target means: compile, persist, do not deliver. Wait for explicit operator dispatch from console. No auto-delivery path exists in phase 2 for any target type.

**Acceptance Criteria:**
- [ ] Notes processed with `queue_only` target produce a `deliveries` row with `status=queued`
- [ ] No code path automatically dispatches a `queued` delivery without operator action
- [ ] Watcher does not dispatch deliveries; it only compiles and persists
- [ ] Console dispatch endpoints are the only path that transitions delivery from `queued` to `dispatching`

### R4: Original Note Archived After Successful Processing

**Description:** After a note is successfully compiled and persisted, the original source note is moved to an archive folder (e.g., `_archive/processed/`). The archive copy is unchanged — no metadata rewritten.

**Acceptance Criteria:**
- [ ] After successful compile+persist, original note is moved to `<vault_root>/_archive/processed/<filename>`
- [ ] Archived note content is byte-for-byte identical to original (no frontmatter rewrite)
- [ ] Archive folder is configurable via runtime settings
- [ ] If archive move fails, the error is logged but does not roll back the DB record
- [ ] Integration test: process a valid note → original note appears in archive folder, DB record exists

### R5: Generated Output Written as Separate File

**Description:** Rendered/generated prompt output is written as a separate file in a configurable output folder. It is not written into the original source note.

**Acceptance Criteria:**
- [ ] Output file is written to `<vault_root>/<output_folder>/<note_stem>-output.md` (or similar configurable pattern)
- [ ] Output file does not contain the original note's frontmatter or raw transcript
- [ ] Output folder is configurable via runtime settings
- [ ] If output write fails, the error is logged and a `workflow_error_records` row is written

### R6: Writeback Happens Only After Operator Dispatch

**Description:** Writing output back to the vault is a delivery action, not an automatic post-compile side effect. It requires explicit operator dispatch from the queue.

**Acceptance Criteria:**
- [ ] No code path writes output to the vault as part of compile or persist phase
- [ ] `obsidian_note` delivery target write only occurs when operator triggers dispatch
- [ ] Console dispatch flow for `obsidian_note` target shows the pending output before confirming write
- [ ] Integration test: process note → no output file written until operator dispatches

## Out of Scope

- Multi-vault support
- Automatic format detection beyond `## Control` / `## Transcript`
- Frontmatter schema validation beyond required sections
- LLM-assisted parse rescue
- Conflict resolution for duplicate output filenames (not handled in phase 2)

## Cross-References

- Depends on: cavekit-architecture.md R3 (Postgres is canonical truth, not vault)
- Depends on: cavekit-architecture.md R5 (live-session delivery removed)
- Depends on: cavekit-console.md R8 (vault path containment)
- Depended on by: cavekit-data-model.md R4 (intake_notes is first node in lineage)
