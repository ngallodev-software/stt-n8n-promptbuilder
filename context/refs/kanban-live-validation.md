# Kanban Live Validation

## Target

- Kanban repo: `kanban`
- branch: `fork/feature-requests/roll-up`

## Runtime

- started Kanban against a temp git repo
- runtime URL: `http://127.0.0.1:3484/pf-kanban-live-hqcq0l`
- workspace id: `pf-kanban-live-hqcq0l`

## Prompt Forge Apply Input

- source prompt generation id: `pg_live_001`
- source status: `rendered`
- binding:
  - `kanbanBaseUrl=http://127.0.0.1:3484`
  - `kanbanWorkspaceId=pf-kanban-live-hqcq0l`

## Apply Result

- `ok=true`
- `applied=true`
- `taskMappings[0].externalTaskKey=pf:pg:pg_live_001`
- `taskMappings[0].taskId=1243a`
- `taskMappings[0].columnId=backlog`

## Workspace Readback

- fetched `GET /api/trpc/workspace.getState` with header:
  - `x-kanban-workspace-id: pf-kanban-live-hqcq0l`
- confirmed one backlog card with:
  - `externalTaskKey=pf:pg:pg_live_001`
  - `title=Live dogfood task from Prompt Forge into Kanban.`
  - `prompt=Live dogfood task from Prompt Forge into Kanban.`

## Conclusion

- Prompt Forge backend apply route created a real Kanban board entry through the minimal import API.
- Readback from live Kanban workspace state matched the returned import mapping.
