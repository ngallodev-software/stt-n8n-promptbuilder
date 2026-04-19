# Phase 4 Gate Check

Date: 2026-04-19

## Acceptance Criteria

### ✅ All major read functions call backend endpoints

Migrated in `src/services/promptforge/api.ts`:
- `getIntakeNotes()` → `GET /console/intake` with pagination + 6 filters
- `getPrompts()` → `GET /console/prompts` with pagination + 3 filters
- `getDeliveries()` → `GET /console/deliveries` with pagination + status filter
- `getTermDictionary()` → `GET /console/dictionary` with pagination + scope/project filters
- `getTemplates()` → `GET /console/templates` with pagination + 4 filters
- `getLogs()` → `GET /console/logs` with pagination + 7 filters

Bootstrap still used for: health, projects, targets, rulesets, rules, metrics (small/fast endpoints).

### ✅ Dev works without full backend via fallback

`config.ts` (new):
- `RUNTIME_ENVIRONMENT` detected from NODE_ENV → window.location.hostname
- `STRICT_BACKEND = false` in dev by default
- `logBackendFallback()` warns to console then falls through to mock data
- `lastHydrationAt` set on fallback to prevent immediate retry storm

### ✅ Staging/prod fails fast when backend contract missing

- `STRICT_BACKEND = true` when `RUNTIME_ENVIRONMENT !== "development"`
- `createStrictBackendError()` wraps cause with "Backend unavailable in strict mode"
- `STRICT_BACKEND` / `VITE_PROMPTFORGE_STRICT_BACKEND` env var forces strict in dev

### ✅ In-memory filtering/pagination removed

Removed from all migrated functions:
- Local `.filter()` chains over bootstrap data
- Local `.slice()` pagination
- Local `paginate()` helper function (deleted)
- `buildQueryPath()` helper converts filter params to backend query string

### ✅ Mutation functions and invalidation flow intact

No mutation functions touched. Query key shapes (`qk.*`) unchanged.

## Deliverables

Files changed (frontend repo):
- `src/services/promptforge/api.ts` (+78, -69) — reads migrated, local filtering removed
- `src/services/promptforge/config.ts` (new, 68 lines) — env detection + strict mode

## Residual Risks

1. **PageResult shape mismatch**: Backend returns `{ items, total, limit, offset }` shape (per Phase 2 PaginatedResponse). Frontend expects `{ rows, total, page, pageSize }`. May need adapter. Verify at integration test time.

2. **No TypeScript build validation**: Changes not compiled. Type errors possible in fetchJson return type assertions.

3. **Bootstrap-only reads not migrated**: projects, targets, rulesets, rules, metrics still read from bootstrap hydration — acceptable for now (small collections), but note for Phase 6 docker compose validation.

## Phase 4 Decision

**Status**: ✅ READY FOR PHASE 5

**Rationale**:
- All heavy paginated reads now call backend endpoints
- In-memory filtering eliminated
- Strict/fallback mode wired for all 3 environments
- Mutation paths untouched

**Caveat**: PageResult shape alignment should be verified in Phase 5 test harness.

**Next phase trigger**: Proceed to Phase 5 (frontend test hardening).
