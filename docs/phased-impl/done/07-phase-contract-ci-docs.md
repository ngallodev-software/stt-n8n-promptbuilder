# Phase 7 Prompt: Contract Drift Guard + Final Docs/Release Safety

```text
Phase 7 objective:
Add cross-repo contract drift protection, finalize docs, and prepare safe release checklist.

Repos:
- /lump/apps/prompt-forge
- /lump/apps/prompt-forge-console

Parallel packets:

Packet A (Backend contract guard owner)
- Add CI check for API contract drift:
  - OpenAPI schema snapshot check OR endpoint shape validation suite.
- Ensure console endpoints are included.

Packet B (Frontend compatibility guard owner)
- Add CI check ensuring frontend service expectations align to backend contract artifact.
- Validate required endpoint presence and required fields.

Packet C (Docs + release checklist owner)
- Update:
  - backend `API_COMPAT.md`
  - frontend compatibility doc
  - release checklist with `api:patch|minor|major` labels
- Include rollback and smoke verification steps.

Constraints:
- Keep checks lightweight and deterministic.
- Avoid flaky network-dependent CI where possible.

Final acceptance:
1) Both repos have passing tests and build.
2) Contract drift checks pass.
3) Runtime smoke script passes.
4) Docs clearly state compatibility and release process.
5) Remaining risks (if any) are documented explicitly.
```
