# Phased Implementation Prompt Pack

This directory contains delegation-optimized prompts for finishing remaining integration work across:

- Backend repo: `stt-n8n-promptbuilder` (`/lump/apps/prompt-forge`)
- Frontend repo: `prompt-forge-console` (`/lump/apps/prompt-forge-console`)

## Files

- `00-orchestrator-prompt.md`: master orchestration prompt for a lead agent.
- `01-phase-contract-inventory.md`: baseline inventory + contract lock.
- `02-phase-backend-read-surface.md`: backend read endpoints + typed schemas.
- `03-phase-backend-mutation-hardening.md`: backend mutation strictness + tests.
- `04-phase-frontend-service-migration.md`: frontend service migration to real endpoints.
- `05-phase-frontend-test-hardening.md`: frontend test coverage and error behavior.
- `06-phase-runtime-compose-smoke.md`: docker/runtime and smoke checks.
- `07-phase-contract-ci-docs.md`: contract drift guard + docs + release safety.

## How to Use

1. Start with `00-orchestrator-prompt.md` in your lead/orchestrator chat.
2. Execute phases in order.
3. For each phase:
- run the full phase prompt as-is
- delegate sub-packets in parallel
- merge only when phase acceptance criteria pass

## Delegation Model Guidance

- Use `gpt-5.4` for orchestration and high-coupling design decisions.
- Use `gpt-5.4-mini` for scoped implementation packets that are not too complex.
- Keep file ownership explicit to avoid merge conflicts.
