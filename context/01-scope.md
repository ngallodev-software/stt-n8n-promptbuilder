# Scope

## What This Feature Does
- Keep recursive voice intake on `Inbox/Voice/**`
- Interpret the first path segment(s) below `Inbox/Voice` as a route key
- Route to Kanban when the target binding is healthy and reachable
- Fall back to queue plus review state when Kanban is down or incomplete
- Preserve the source folder path so route decisions are auditable

## What This Feature Does Not Do
- Does not replace the existing watcher recursion model
- Does not containerize Kanban
- Does not move route policy into n8n
- Does not merge delivery targets and route policy into one page
- Does not require a new transport if existing watcher/webhook flows are enough

## Routing Model
- Source folder is canonical for route selection
- Example path:
  - `Inbox/Voice/kanban/prompt-forge/...`
- Proposed interpretation:
  - route family: `kanban`
  - workspace key: `prompt-forge`
  - deeper folders: preserved as context/metadata
- Unknown route families under `Inbox/Voice/**` fail closed
  - they do not auto-map to queue, review, or Kanban
  - they remain eligible for replay only after an explicit policy change

## Fallback Model
- If Kanban is reachable and binding is valid, apply directly
- If Kanban is unavailable, queue the prompt generation and mark it needs review
- When Kanban becomes available again, queued items can be replayed

## n8n Role
- n8n can stay a transport/automation bridge
- n8n should not own route policy
- route policy should live in Prompt Forge so fallback/replay stays coherent
