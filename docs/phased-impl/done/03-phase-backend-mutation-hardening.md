# Phase 3 Prompt: Backend Mutation Hardening

```text
Phase 3 objective:
Harden existing `/console/*` mutation endpoints with strict validation, consistent error semantics, and integration tests.

Repo:
- /lump/apps/prompt-forge

Parallel packets:

Packet A (Validation + error model owner)
- Own files: console request models + shared error helpers.
- Enforce:
  - strict enums for statuses/priorities/scopes
  - field constraints
  - meaningful 400 responses
  - consistent 404 for missing entities
  - 503 when DB unavailable

Packet B (Mutation query owner)
- Own files: mutation SQL and endpoint handlers.
- Verify and harden:
  - delivery retry
  - delivery reroute
  - delivery status patch
  - rule patch
  - dictionary upsert
  - template activation
  - force review
  - clone prompt generation
  - prompt priority patch
  - archive intake
- Ensure idempotency where possible.

Packet C (Integration tests owner)
- Add endpoint tests for:
  - happy path
  - bad payload
  - missing target record
  - bad enum
  - DB unavailable
- Include at least one test that verifies mutation side effects by re-reading resource state.

Constraints:
- No secret/PII leakage in errors.
- Keep response shapes stable for frontend service layer.
- Do not remove existing fields from responses.

Phase gate:
- All mutations are validated and tested.
- Error semantics are consistent and documented.
- No regression in existing API tests.
```
