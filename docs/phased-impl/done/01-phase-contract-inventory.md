# Phase 1 Prompt: Contract + Inventory Baseline

```text
Phase 1 objective:
Establish a hard baseline for existing contracts, endpoints, and frontend service signatures before deeper implementation.

Repos:
- . (backend)
- prompt-forge-console (frontend)

Delegate these packets in parallel:

Packet A (Backend inventory owner)
- Own files: backend docs only.
- Extract current API surface:
  - public endpoints
  - /console endpoints
  - request/response shapes
  - error semantics (status codes + detail body)
- Produce/update: API compatibility matrix doc.

Packet B (Frontend contract owner)
- Own files: frontend service docs only.
- Extract current frontend service signatures and query key shapes from `src/services/promptforge/api.ts`.
- Produce mapping table: service fn -> backend endpoint -> fallback behavior.

Packet C (Gap analysis owner)
- Own files: docs only, either repo.
- Compare frontend expectations against backend capabilities.
- Produce a prioritized gap list:
  1) blocking
  2) high
  3) medium
  4) nice-to-have

Constraints:
- You are not alone; do not revert others’ changes.
- No implementation changes yet beyond docs/contracts.

Deliverables:
1) Contract matrix docs in both repos.
2) Explicit list of missing/partial endpoints.
3) Signed phase gate:
  - “ready for phase 2” only if all blocking gaps are enumerated.

Acceptance criteria:
- Every frontend service function has an explicit backend mapping state:
  - implemented
  - partial
  - missing
- Query key shapes documented and locked.
- No code behavior changes in this phase except documentation.
```
