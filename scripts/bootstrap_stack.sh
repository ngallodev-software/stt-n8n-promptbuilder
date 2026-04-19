#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  echo "docker compose is required" >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  echo "No .env file found; using compose defaults from .env.example placeholders." >&2
fi

mkdir -p vault/Inbox/Voice vault/Processed/Voice vault/Processing/Error vault/Projects

echo "Starting core services..."
docker compose up -d --build postgres n8n promptforge-api

echo "Waiting for Postgres..."
"$ROOT_DIR/scripts/wait_for_postgres.sh"

echo "Applying Postgres schema if needed..."
"$ROOT_DIR/scripts/migrate_postgres.sh"

echo "Backfilling legacy plaintext console secrets if present..."
docker compose exec -T promptforge-api python /app/scripts/migrate_console_secrets.py || {
  echo "console secret backfill failed" >&2
  exit 1
}

echo "Waiting for n8n..."
deadline=$((SECONDS + ${PROMPTFORGE_N8N_TIMEOUT_SECONDS:-120}))
until docker compose exec -T n8n wget -qO- http://localhost:5678/healthz >/dev/null 2>&1; do
  if (( SECONDS >= deadline )); then
    echo "Timed out waiting for n8n" >&2
    exit 1
  fi
  sleep 2
done

marker_path="/home/node/.n8n/.promptforge_workflows_imported"
already_imported="$(
  docker compose exec -T n8n sh -lc "[ -f '$marker_path' ] && echo 1 || true"
)"
if [[ "$already_imported" != "1" ]]; then
  echo "Importing n8n workflows..."
  "$ROOT_DIR/scripts/import_n8n_workflows.sh" promptforge-n8n docs/planning/n8n_workflows
  docker compose exec -T n8n sh -lc "touch '$marker_path'"
else
  echo "n8n workflows already imported."
fi

echo "Starting watcher..."
docker compose up -d promptforge-watcher

docker compose ps
