# Phase 4 Prompt: Frontend Service Migration to Dedicated Endpoints

```text
Phase 4 objective:
Migrate frontend service reads from bootstrap-heavy local filtering to dedicated backend endpoints while preserving UI contract stability.

Repo:
- prompt-forge-console

Parallel packets:

Packet A (Service reads owner)
- Own file: `src/services/promptforge/api.ts` (+ optional helper module).
- For each list/read function, call dedicated backend endpoint.
- Keep existing exported function names/signatures.
- Keep query key shapes stable unless unavoidable; if changed, add migration note.

Packet B (Fallback and strict-mode owner)
- Add deterministic behavior by environment:
  - dev: fallback allowed
  - staging/prod: strict backend by default
- Keep explicit `STRICT_BACKEND` override.
- Ensure clear error path when strict mode fails.

Packet C (Pagination/filtering correctness owner)
- Ensure all heavy pages use backend pagination/filtering.
- Remove in-memory filter/paginate over large local arrays where backend endpoint exists.

Constraints:
- Minimize page/component rewrites.
- Preserve data contracts consumed by pages.
- Keep mutation functions and invalidation flow intact.

Phase gate:
- All major read functions call backend endpoints.
- Dev still works without full backend via fallback.
- Staging/prod fails fast when backend contract is missing.
```
