# Release Checklist

## Pre-Release Gates

- [ ] `python3 scripts/check_contract.py` — exits 0 (no backend contract drift)
- [ ] `node ../prompt-forge-console/scripts/check_compat.mjs` — exits 0 (frontend endpoints present)
- [ ] `pytest tests/` — all pass
- [ ] `bash scripts/smoke_test.sh` — 5/5 PASS against staging or local stack

## API Change Labels

Apply one label to every PR touching `console_api.py` or `console_models.py`:

| Label | When to use |
|-------|-------------|
| `api:patch` | No shape change — internal refactor, error message wording, performance |
| `api:minor` | Additive — new endpoint, new optional field, new enum value |
| `api:major` | Breaking — removed endpoint, removed/renamed field, changed enum values, pagination shape |

`api:major` requires explicit sign-off and frontend migration plan before merge.

## Rollback

```bash
# Stop current stack
docker compose down

# Check out previous release tag
git checkout <previous-tag>
cd ../prompt-forge-console && git checkout <previous-tag>
cd ../prompt-forge

# Rebuild and restart
docker compose up -d --build

# Verify
bash scripts/smoke_test.sh
```

## Post-Deploy Smoke Verification

```bash
bash scripts/smoke_test.sh
```

All 5 checks must pass. If any fail:
1. Check `docker compose ps` — confirm all services healthy
2. Check `docker compose logs -f promptforge-api` for startup errors
3. If bootstrap returns 503 — wait 30s for postgres to finish init, retry

## Residual Risks (as of v0.3.0 / phases 1-7)

| Risk | Severity | Mitigation |
|------|----------|------------|
| No mutation integration tests run in CI | Medium | `tests/test_console_mutations.py` exists but requires live DB — run manually before major releases |
| Bootstrap backward-compat not tested | Low | Phase 2 refactor preserved shape; verify manually if bootstrap schema changes |
| PageResult items key hardcoded per endpoint | Low | If backend renames field alias, frontend adapter silently returns `rows=[]` — covered by compat check |
| Console frontend not type-checked in CI | Medium | Add `tsc --noEmit` to compat-check workflow when tsconfig is stable |
| Watcher healthcheck is minimal (`test -f /proc/1/status`) | Low | Sufficient for compose ordering; does not verify actual file processing |
