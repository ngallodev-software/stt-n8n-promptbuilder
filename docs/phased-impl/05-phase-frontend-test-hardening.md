# Phase 5 Prompt: Frontend Test + Error/Invalidation Hardening

```text
Phase 5 objective:
Add frontend service-layer confidence with strict/fallback tests, mutation invalidation checks, and robust error handling expectations.

Repo:
- /lump/apps/prompt-forge-console

Parallel packets:

Packet A (Service tests owner)
- Add tests for:
  - successful backend reads
  - strict mode backend failure behavior
  - fallback mode behavior
  - payload adaptation/mapping correctness

Packet B (Mutation behavior owner)
- Add tests that confirm mutation function behavior and subsequent refresh expectations.
- Create/extend query invalidation map documentation:
  - retry/reroute/status -> deliveries + dashboard metrics
  - rule update -> rules/rulesets
  - dictionary upsert -> term dictionary views
  - template activate -> templates + prompt flows
  - force review/priority/archive -> prompts/intake/review

Packet C (UX error policy owner)
- Document and enforce service-level error policy:
  - typed API errors
  - retryable vs terminal errors
  - user-facing messages for critical flows

Constraints:
- Keep page-level refactor minimal.
- Do not rewrite entire test architecture.

Phase gate:
- Service tests cover strict/fallback and representative failure modes.
- Mutation side effects and invalidation policy are explicit and verified.
```
