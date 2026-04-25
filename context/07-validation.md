# Validation

## Gate 1
- `pytest` or project test command passes on changed modules

## Gate 2
- Route grammar unit tests pass
- Watcher recursion tests still pass
- Queue fallback tests pass

## Gate 3
- End-to-end route preview/apply passes for a live Kanban workspace
- End-to-end fallback passes when Kanban is unavailable

## Gate 4
- No meaningful regressions in watcher startup or intake throughput

## Gate 5
- Prompt Forge starts cleanly with the new routing settings

## Gate 6
- Human review confirms route policy is understandable and not hidden in n8n
