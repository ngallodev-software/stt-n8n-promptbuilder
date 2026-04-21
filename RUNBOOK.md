# PromptForge Runbook

## Security Note

This application is not safe for network exposure. Bind to localhost only (127.0.0.1). Do not expose to a network interface.

---

## Start

### Required environment variables

```bash
PROMPTFORGE_DATABASE_URL=postgresql://promptforge:<password>@localhost:5432/promptforge
PROMPTFORGE_VAULT_PATH=/path/to/vault
PROMPTFORGE_WATCH_FOLDER=Inbox/Voice
PROMPTFORGE_PROCESSED_FOLDER=Processed/Voice
```

Optional but recommended:

```bash
PROMPTFORGE_SECRETS_MASTER_KEY=<fernet-base64-key>
PROMPTFORGE_WEBHOOK_ENABLED=false
```

### Start the watcher

```bash
PYTHONPATH=. python3 -m promptforge_watcher
```

### Start the API

```bash
PYTHONPATH=. uvicorn promptforge_services.api:app --host 127.0.0.1 --port 8090
```

---

## Stop

### Watcher

Send SIGINT or SIGTERM to the watcher process:

```bash
kill <watcher-pid>
```

Or if running in foreground: `Ctrl+C`.

### API

Send SIGINT or SIGTERM to the uvicorn process:

```bash
kill <uvicorn-pid>
```

Or if running in foreground: `Ctrl+C`.

---

## Health Check

```bash
curl -s http://127.0.0.1:8090/health
```

Expected responses:

| Response | Meaning |
|----------|---------|
| `{"status": "ok"}` | API up, DB reachable |
| Connection refused | API not running |
| `{"status": "degraded", ...}` | API up, DB or dependency issue — check logs |

---

## Note Failure Triage

### Find failed notes in DB

```sql
SELECT id, source_path, error_message, created_at
FROM workflow_error_records
ORDER BY created_at DESC
LIMIT 20;
```

### Identify the failed note

Match `source_path` from the query result to the file in the vault. The note may also appear in `PROMPTFORGE_ERROR_FOLDER` (default: `Processing/Error`).

### Reprocess a note

1. Fix the note content (correct frontmatter, transcript, or directive).
2. Ensure `status: new` and `watch_eligible: true` in frontmatter.
3. Move or re-drop the note into `PROMPTFORGE_WATCH_FOLDER`.

The watcher will pick it up on the next filesystem event or startup scan.

---

## Queue Depth

### Via API

```bash
curl -s http://127.0.0.1:8090/metrics/queue-depth
```

### Via DB

```sql
SELECT COUNT(*)
FROM intake_notes
WHERE status = 'new'
  AND watch_eligible = true;
```

---

## Backup

### Database

```bash
pg_dump \
  -h <db-host> \
  -U <db-user> \
  -d <db-name> \
  -F c \
  -f /backups/promptforge-$(date +%Y%m%d%H%M%S).dump
```

### Vault

```bash
rsync -av /path/to/vault/ /backups/vault-$(date +%Y%m%d%H%M%S)/
```

---

## Restore

### Database

```bash
pg_restore \
  -h <db-host> \
  -U <db-user> \
  -d <db-name> \
  -F c \
  /backups/promptforge-<timestamp>.dump
```

Or for plain SQL dump:

```bash
psql -h <db-host> -U <db-user> -d <db-name> -f /backups/promptforge-<timestamp>.sql
```

### Vault

```bash
rsync -av /backups/vault-<timestamp>/ /path/to/vault/
```

### Verification checklist

- [ ] `intake_notes` row count matches pre-backup count
- [ ] `delivery_records` row count matches pre-backup count
- [ ] `workflow_error_records` accessible
- [ ] Health endpoint responds: `curl -s http://127.0.0.1:8090/health` returns `{"status": "ok"}`
- [ ] Watcher starts without errors and picks up a test note
