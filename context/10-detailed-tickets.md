# Detailed Tickets

## T-01 Watcher audit
- Model: `gpt-5.4-mini low`
- Confirm recursive intake behavior and current route-relevant metadata

## T-02 Route grammar
- Model: `gpt-5.4-mini medium`
- Define how `Inbox/Voice/<route>/...` maps to destination state

## T-03 Route registry
- Model: `gpt-5.4-mini medium`
- Persist route definitions and Kanban bindings per project

## T-04 Direct Kanban apply
- Model: `gpt-5.4-mini medium`
- Apply a routed note directly to Kanban when healthy

## T-05 Queue fallback
- Model: `gpt-5.4-mini medium`
- Store queue/review state when Kanban is unavailable

## T-06 Replay
- Model: `gpt-5.3-codex medium`
- Retry queued route items after recovery without duplicates

## T-07 n8n bridge
- Model: `gpt-5.4-mini medium`
- Define the webhook payload and relay contract

## T-08 Console route UX
- Model: `gpt-5.4-mini medium`
- Show source folder, route key, and destination in the console

## T-09 Validation
- Model: `gpt-5.3-codex medium`
- Add recursion, fallback, and replay tests

## T-10 Final audit
- Model: `gpt-5.4-mini low`
- Close tracking and record gaps
