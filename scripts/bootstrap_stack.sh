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

POSTGRES_USER="${POSTGRES_USER:-promptforge}"
POSTGRES_DB="${POSTGRES_DB:-promptforge}"

mkdir -p vault/Inbox/Voice vault/Processed/Voice vault/Processing/Error vault/Projects

echo "Starting Postgres..."
docker compose up -d --build postgres

echo "Waiting for Postgres..."
"$ROOT_DIR/scripts/wait_for_postgres.sh"

echo "Synchronizing Postgres role password with compose config..."
"$ROOT_DIR/scripts/sync_postgres_password.sh"

echo "Applying Postgres schema if needed..."
"$ROOT_DIR/scripts/migrate_postgres.sh"

echo "Seeding operator catalogs if the database is still empty..."
catalog_counts="$(
  docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -v ON_ERROR_STOP=1 <<'SQL'
SELECT
  (SELECT COUNT(*) FROM projects)::text || ':' ||
  (SELECT COUNT(*) FROM rulesets)::text || ':' ||
  (SELECT COUNT(*) FROM rules)::text || ':' ||
  (SELECT COUNT(*) FROM term_dictionary)::text || ':' ||
  (SELECT COUNT(*) FROM prompt_templates)::text || ':' ||
  (SELECT COUNT(*) FROM delivery_targets)::text;
SQL
)"
if [[ "$catalog_counts" == "0:0:0:0:0:0" ]]; then
  docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 < "$ROOT_DIR/docs/planning/promptforge_seed_data.sql"
else
  echo "Operator catalogs already present; skipping seed load."
fi

echo "Starting app services..."
docker compose up -d --build n8n promptforge-api

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
