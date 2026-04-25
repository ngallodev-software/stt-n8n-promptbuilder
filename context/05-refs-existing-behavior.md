# Existing Behavior

## Watcher
- Default watch folder is `Inbox/Voice`
- A note is eligible when its relative path starts with the watch folder prefix
- The watcher already processes recursively below that prefix
- The note path is preserved in `note_relative_path`

## n8n
- Webhook delivery exists as a transport hook
- It is currently treated as downstream notification/automation
- It should not become the canonical route policy engine

## Kanban
- Kanban import already exists through the minimal import API harness
- Kanban workspace binding is project-scoped in Prompt Forge
- Direct dispatch works when Kanban is reachable and configured
- Queue fallback exists when binding or reachability fails

## Console
- Settings page already exposes backend runtime settings
- Intake pages already show note paths and project context
- The current UX can hide route meaning behind generic labels

## Brownfield takeaway
- The watcher recursion is not the gap
- The gap is route derivation, fallback policy, and UI clarity
