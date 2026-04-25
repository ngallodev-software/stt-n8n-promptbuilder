# Kit: Recursive Voice Routing

## Scope
Support route derivation from the initial folder under `Inbox/Voice/**`, direct Kanban dispatch when healthy, and queue/review fallback when not.

## Requirements

### R1 Route derivation
- Derive a route key from the initial folder path below `Inbox/Voice`
- Preserve deeper path segments as metadata
- Do not require a new note format to get routing
- Recognized route families are explicit and finite
  - `kanban` is recognized in this slice
  - direct root notes under `Inbox/Voice` remain on the legacy/default path
- Unknown route families must fail closed
  - do not silently map an unknown family to queue, review, or Kanban
  - preserve the source path and route metadata for later explicit replay or policy update

### R2 Recursive intake
- Notes under any nested subfolder below `Inbox/Voice` remain eligible if they satisfy existing watcher rules
- Routing must work for nested folders, not only one-level folders

### R3 Kanban direct dispatch
- If a route targets Kanban and the target workspace is healthy, create the finished prompt in the workspace
- The route must carry the intended workspace identity explicitly

### R4 Queue fallback
- If Kanban is unavailable, create the prompt generation in queue mode
- Mark the item as needing review or equivalent review-gated state
- Preserve enough metadata to replay to Kanban later

### R5 Replay/recovery
- Once Kanban is back, queued route items can be retried without losing route context
- Replay must be idempotent at the route key level

### R6 n8n bridge
- n8n may emit or relay intake events
- n8n must not own route resolution or fallback policy

### R7 Observability
- Users must be able to see the source folder, route key, destination, and fallback state

## Acceptance Criteria
- A note under `Inbox/Voice/kanban/prompt-forge/...` resolves to the Kanban destination route
- A Kanban outage sends the item to queue/review instead of dropping it
- Replay after Kanban recovery does not create duplicates
- Console surfaces the route meaning in the intake detail or settings flow
- A note under `Inbox/Voice/<unknown>/...` is rejected as unsupported until the policy explicitly grows that family
- A note directly under `Inbox/Voice/...` continues to follow the default legacy intake path
