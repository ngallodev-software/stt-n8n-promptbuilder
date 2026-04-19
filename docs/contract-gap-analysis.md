# Contract Gap Analysis

Scope:

- Frontend source: `/lump/apps/prompt-forge-console/docs/frontend-service-mapping.md`
- Backend contract snapshot: `/lump/apps/prompt-forge/docs/api-compatibility-matrix.md`

This is a doc-to-doc comparison. It does not inspect runtime behavior.

## Summary

- Blocking gaps: none found.
- High gaps: response-shape mismatches on mutating console routes.
- Medium gaps: non-strict frontend fallback masks backend error semantics.
- Nice-to-have gaps: many read paths are bootstrap-backed only and do not have dedicated backend endpoints yet.

## Blocking

No frontend service function in the mapping expects a backend endpoint that is missing from the compatibility matrix.

The explicit endpoint calls in `src/services/promptforge/api.ts` are all represented in the matrix:

- `getHealth` -> `GET /_healthz`, `GET /providers/health`
- `retryDelivery` -> `POST /console/deliveries/{delivery_id}/retry`
- `rerouteDelivery` -> `POST /console/deliveries/{delivery_id}/reroute`
- `updateDeliveryStatus` -> `PATCH /console/deliveries/{delivery_id}/status`
- `updateRule` -> `PATCH /console/rules/{rule_id}`
- `upsertTerm` -> `POST /console/dictionary/upsert`
- `activateTemplate` -> `POST /console/templates/{template_id}/activate`
- `forceReview` -> `POST /console/prompts/{prompt_generation_id}/force-review`
- `clonePrompt` -> `POST /console/prompts/{prompt_generation_id}/clone`
- `changePromptPriority` -> `PATCH /console/prompts/{prompt_generation_id}/priority`
- `archiveNote` -> `PATCH /console/intake/{intake_note_id}/archive`

## High

These routes exist, but the frontend-facing response shape in the service mapping is more specific than the matrix contract currently guarantees.

| Service fn | Endpoint | Gap |
| --- | --- | --- |
| `retryDelivery` | `POST /console/deliveries/{id}/retry` | Frontend expects `{ ok, id, message }`; matrix only guarantees `{ ok: true, message: "Retry queued" }`. `id` is missing from the canonical success shape. |
| `rerouteDelivery` | `POST /console/deliveries/{id}/reroute` | Frontend expects `{ ok, id, targetId }`; matrix only guarantees `{ ok: true }`. |
| `updateDeliveryStatus` | `PATCH /console/deliveries/{id}/status` | Frontend expects `{ ok, id, status }`; matrix only guarantees `{ ok: true }`. |
| `updateRule` | `PATCH /console/rules/{id}` | Frontend expects `{ ok, id, enabled?, priority? }`; matrix only guarantees `{ ok: true }`. |
| `activateTemplate` | `POST /console/templates/{id}/activate` | Frontend expects `{ ok, id, family }`; matrix only guarantees `{ ok: true }`. |
| `forceReview` | `POST /console/prompts/{id}/force-review` | Frontend expects `{ ok, id }`; matrix only guarantees `{ ok: true }`. |
| `clonePrompt` | `POST /console/prompts/{id}/clone` | Frontend expects `{ ok, id, newId }`; matrix only guarantees `{ ok, newId }`. |
| `changePromptPriority` | `PATCH /console/prompts/{id}/priority` | Frontend expects `{ ok, id, priority }`; matrix only guarantees `{ ok: true }`. |
| `archiveNote` | `PATCH /console/intake/{id}/archive` | Frontend expects `{ ok, id }`; matrix only guarantees `{ ok: true }`. |

### Notes

- `upsertTerm` is not listed here because the matrix response includes an echoed payload, which is directionally compatible with the service signature even though the frontend currently treats it as a submitted payload echo rather than a fully normalized record.
- `getHealth` is not listed here because the service already composes the two matrix endpoints into a single snapshot.

## Medium

The frontend service layer is intentionally forgiving when `VITE_PROMPTFORGE_STRICT_BACKEND` is not set. That means backend failures can be masked by synthetic success values or degraded mock data, which diverges from the matrix's explicit error semantics.

| Service fn | Endpoint(s) | Gap |
| --- | --- | --- |
| `getHealth` | `GET /_healthz`, `GET /providers/health` | If either fetch fails and strict mode is off, the service returns the cached `healthSnapshot` instead of surfacing the backend error. |
| `retryDelivery` | `POST /console/deliveries/{id}/retry` | Backend `503`, `404`, or validation failures are not surfaced in non-strict mode; the service returns synthetic success instead. |
| `rerouteDelivery` | `POST /console/deliveries/{id}/reroute` | Same masking behavior in non-strict mode. |
| `updateDeliveryStatus` | `PATCH /console/deliveries/{id}/status` | Same masking behavior in non-strict mode. |
| `updateRule` | `PATCH /console/rules/{id}` | Same masking behavior in non-strict mode. |
| `upsertTerm` | `POST /console/dictionary/upsert` | Same masking behavior in non-strict mode. |
| `activateTemplate` | `POST /console/templates/{id}/activate` | Same masking behavior in non-strict mode. |
| `forceReview` | `POST /console/prompts/{id}/force-review` | Same masking behavior in non-strict mode. |
| `clonePrompt` | `POST /console/prompts/{id}/clone` | Same masking behavior in non-strict mode. |
| `changePromptPriority` | `PATCH /console/prompts/{id}/priority` | Same masking behavior in non-strict mode. |
| `archiveNote` | `PATCH /console/intake/{id}/archive` | Same masking behavior in non-strict mode. |

## Nice-to-have

These frontend functions are read-only and already work through the shared bootstrap snapshot in the service layer. The backend matrix covers `/console/bootstrap`, but there is no dedicated per-resource HTTP surface yet.

### Intake and lineage

- `listIntakeNotes`
- `getIntakeNote`
- `getIntakeStatusCounts`
- `listUtterancesForNote`
- `listRevisionsForUtterance`
- `getNoteLineage`

### Prompt generation

- `listPromptGenerations`
- `getPromptGeneration`
- `getLatestPromptForNote`

### Deliveries and queueing

- `listDeliveries`
- `getDelivery`
- `getDeliveryHistory`
- `getQueueDepth`

### Processing and observability

- `listProcessingRunsForNote`
- `listFailedProcessingRuns`
- `getLlmRunAggregate`
- `listLogs`
- `getErrorFingerprints`
- `getSlaSummary`
- `getProjectThroughput`

### Rules, dictionary, templates, and targets

- `listRulesets`
- `listRules`
- `listTerms`
- `listTemplates`
- `listTargets`

### Notes

- `listProjects` is not a gap because the shared bootstrap path already exists in the matrix as `GET /console/bootstrap`.
- These are candidates for future dedicated endpoints, not current blockers for the frontend.
