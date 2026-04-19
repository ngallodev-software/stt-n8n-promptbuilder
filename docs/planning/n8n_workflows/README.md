# PromptForge n8n Workflows

This directory contains importable n8n workflow JSON files for the current PromptForge MVP slice.

Current scope:

- `promptforge_intake_orchestration.json`
  Accepts the watcher webhook payload, validates the shape, classifies the event, and responds with an orchestration summary.
- `promptforge_delivery_queue_processor.json`
  Polls Postgres for queued deliveries, marks the next one as dispatching, classifies the adapter path, and emits a dispatch result envelope.
- `promptforge_review_recovery_scan.json`
  Scans Postgres for review-required or failed records and returns a compact triage summary.

These workflows intentionally do not duplicate Python-owned parsing or rendering logic. They orchestrate around the existing watcher payload and database state.

## Import

Use the repo helper:

```bash
./scripts/import_n8n_workflows.sh
```

By default it imports into the `promptforge-n8n` Docker container using the n8n CLI's `import:workflow --separate --input=...` form documented in the official CLI docs.
If that container name does not exist, the helper will auto-detect a live n8n container such as `n8n-n8n-1`.

## Runtime assumptions

- `promptforge-services` is reachable at `http://promptforge-services:8090`
- Postgres credentials are configured in n8n and attached to the Postgres nodes after import
- The watcher webhook path is `promptforge-intake`
- Delivery adapter execution beyond local Obsidian write-back remains a placeholder path for now

## Post-import note

Imported workflows arrive inactive. In this repo they also include placeholder Postgres credential references, so you must open each workflow once in n8n, assign the real Postgres credential, and then activate the workflows you want to run.
