# Tracking

## Current Status
- T-02 backend route grammar implemented in watcher + repository + console read path
- recognized family: `kanban`
- unknown families fail closed and persist route metadata for replay
- direct Kanban dispatch remains a later ticket

## Open Questions
- Should `kanban` route targets be validated against a workspace binding before later direct dispatch work?
- Should direct-root notes under `Inbox/Voice` stay on the legacy path indefinitely or be migrated to an explicit family?
- Should replay expose `route_json` as a first-class console field instead of only metadata?

## Notes
- Recursive intake is already supported by the watcher prefix model
- The work is in policy, not recursion
- route metadata is currently stored in `intake_notes.route_json` and surfaced through `metadata_json`
