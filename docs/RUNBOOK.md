# Runbook

## Startup

```bash
cp .env.example .env
# Edit .env: set POSTGRES_PASSWORD and N8N_ENCRYPTION_KEY to non-default values
docker compose up -d --build
docker compose ps
```

Expected: all 5 services show `(healthy)`:
- `promptforge-postgres`
- `promptforge-n8n`
- `promptforge-api`
- `promptforge-watcher`
- `promptforge-console`

First startup takes 2-3 minutes for postgres init + n8n bootstrap.

## Smoke Test

```bash
bash scripts/smoke_test.sh
```

Expected: 5/5 PASS, exit code 0.

Override URLs if needed:

```bash
BASE_URL=http://localhost:8090 CONSOLE_URL=http://localhost:5173 bash scripts/smoke_test.sh
```

## Common Failures

### postgres unhealthy

```bash
docker compose logs postgres
```

- Port conflict on `15432` → change `PROMPTFORGE_POSTGRES_HOST_PORT` in `.env`
- Volume permission → `docker compose down -v` then `up -d --build`

### promptforge-api unhealthy

```bash
docker compose logs promptforge-api
```

- `POSTGRES_PASSWORD` mismatch between `.env` and running postgres container → `docker compose down -v && docker compose up -d --build`
- Migrations failed → check logs for SQL errors

### promptforge-console not serving

```bash
docker compose logs promptforge-console
```

- `VITE_PROMPTFORGE_API_BASE` is baked at build time → after changing `.env`, rebuild:

```bash
docker compose build --no-cache promptforge-console
docker compose up -d promptforge-console
```

### watcher not processing files

```bash
docker compose logs promptforge-watcher
```

- `PROMPTFORGE_VAULT_SOURCE` path doesn't exist on host → create it or update `.env`
- Wrong `PROMPTFORGE_WATCH_FOLDER` → check path relative to vault root

### smoke test: bootstrap fails with 503

- Backend DB not yet ready → wait 30s and retry
- `DATABASE_URL` env var not set in container → check `docker compose ps` for api health

## Restart / Reset

```bash
docker compose restart promptforge-api       # restart single service
docker compose restart                        # restart all services
docker compose down                           # stop all (data preserved)
docker compose down -v                        # stop all + wipe volumes (DATA LOSS)
```

## Logs

```bash
docker compose logs -f promptforge-api
docker compose logs -f --tail=100 promptforge-watcher
docker compose logs -f --since=5m             # last 5 minutes across all services
```
