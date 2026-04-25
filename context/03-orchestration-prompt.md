# Orchestration Prompt

Branch: `fork/feature-request/recursive-voice-routing`

Use `codebase-memory-mcp` first for search and structure.

## Locked decisions
- Recursive intake is already acceptable through `Inbox/Voice/**`
- Route policy is derived from the initial folder path
- Prompt Forge owns route policy
- n8n is an optional bridge, not the canonical router
- Kanban fallback is queue/review, not silent drop
- When Kanban is unavailable, keep the prompt generation and mark it needs review

## Agent split
- `mini low`: docs, audits, route inventory, test sweeps
- `mini medium`: route grammar, backend registry, fallback semantics, UI copy
- `gpt-5.3-codex medium`: replay/recovery and broader integration tests

## Exit criteria
- Route grammar is written and mapped to existing intake behavior
- Kanban fallback is explicit
- UI surfaces show source folder and destination clearly
- Validation covers the recursive path and the outage path

## Completion signal
`<all-tasks-complete>`
