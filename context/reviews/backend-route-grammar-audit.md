# Backend Route Grammar Audit

## Scope

This audit covers recursive intake under `Inbox/Voice/**`, route derivation from the initial folder segment(s), direct Kanban dispatch when binding is healthy, and queue/review fallback when Kanban is unavailable.

It is grounded in:

- `context/01-scope.md`
- `context/05-refs-existing-behavior.md`
- `promptforge_watcher/watcher.py`
- `promptforge_watcher/config.py`
- `promptforge_watcher/models.py`
- `promptforge_services/kanban_client.py`

## Current State

- The watcher already recurses below `Inbox/Voice` via `watch_path.rglob("*.md")` and recursive filesystem observation.
- Eligibility is folder-prefix based, not flat: a note is eligible when `relative_path` starts with the normalized watch folder prefix.
- The current watcher preserves the source path as `note_relative_path`, which is enough to make route decisions auditable later.
- Kanban import already exists as a local harness; Prompt Forge already has a project-scoped workspace binding and a client that can talk to a local Kanban instance.
- Queue fallback already exists in behavior terms, but the current watcher still treats route choice as delivery outcome rather than as an explicit route policy layer.

## Proposed Route Grammar

### Canonical base

The canonical intake root is:

- `Inbox/Voice/**`

Only notes under that tree are eligible for recursive intake.

### Route extraction rule

Interpret the first segment below `Inbox/Voice` as the route family.

For a path like:

- `Inbox/Voice/kanban/prompt-forge/research/note.md`

the derived route is:

- `route_family = kanban`

The next segment, when present, is the route target key:

- `route_target = prompt-forge`

Any remaining nested folders are metadata, not additional route keys:

- `route_context = research/`

The full source folder path must be preserved on the intake record for audit and replay.

### Folder semantics

- `Inbox/Voice/kanban/<workspace>/...` means route family `kanban` with a workspace binding key.
- `Inbox/Voice/queue/...` means queue/review routing.
- `Inbox/Voice/review/...` means review-only intake.
- `Inbox/Voice/<other>/...` should be treated as an explicit route family if the family is recognized, or rejected as unsupported if it is not.

### Metadata rule

Folders deeper than the first one or two route segments are metadata only.

That means:

- they must not create new delivery targets by themselves
- they must be preserved in stored intake metadata
- they may influence display, lineage, or replay notes, but not the primary route family

## Fallback Contract

### Healthy Kanban path

If the Kanban binding is present and reachable:

- dispatch directly to Kanban
- record the returned Kanban identifiers or mappings
- keep the source note path and route metadata attached to the intake record

### Unhealthy Kanban path

If Kanban is unavailable, incomplete, or missing binding fields:

- do not invent a transport fallback
- queue the prompt generation locally
- mark the item as needing review
- preserve enough route metadata to replay the same item when Kanban becomes available again

### Replay rule

Replay must use the same derived route family and workspace key from the original source folder.

Replay must not re-derive a different route from later folder moves unless the source note itself was intentionally re-homed.

## Minimum Backend Changes

1. Add a route parser that derives `route_family`, `route_target`, and `route_context` from the note's relative path under `Inbox/Voice`.
2. Persist the parsed route fields alongside the existing note-relative-path metadata.
3. Wire the route parser into the intake/bundle assembly so delivery can choose direct Kanban or queue/review fallback without guessing from generic delivery state.
4. Add a binding health check for Kanban before direct dispatch.
5. Keep replay keyed by the original source path and derived route fields.
6. Add tests for:
   - recursive nested folders under `Inbox/Voice`
   - recognized route families
   - unsupported route families
   - Kanban healthy dispatch
   - Kanban unavailable fallback to queue/review
   - replay using preserved route metadata

## Ambiguities / Decisions Needed

- Whether `Inbox/Voice/<family>/<target>` should allow arbitrary family names or only a fixed allowlist.
- Whether a missing workspace key under `kanban` should fall back to queue/review or fail closed.
- Whether `review` is a route family or a delivery mode in the long-term model.
- Whether folder moves after intake are allowed to change route semantics, or only audit metadata.
- How much of `route_context` should be visible in console/UI versus stored only for replay.

## Assessment

The route grammar is close to implementation-ready, but it still needs one explicit policy decision: the allowlist and failure behavior for unknown route families.

The backend delta is small. The code already supports recursive discovery and source-path preservation; the missing piece is a first-class route parser plus a health-gated dispatch decision.
