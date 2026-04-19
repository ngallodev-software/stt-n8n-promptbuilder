#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCHEMA_FILE="${1:-$ROOT_DIR/docs/planning/promptforge_postgres_schema.sql}"
MIGRATION_NAME="${MIGRATION_NAME:-001_schema}"
POSTGRES_SERVICE="${POSTGRES_SERVICE:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-promptforge}"
POSTGRES_USER="${POSTGRES_USER:-promptforge}"

if [[ ! -f "$SCHEMA_FILE" ]]; then
  echo "schema file not found: $SCHEMA_FILE" >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  echo "docker compose is required" >&2
  exit 1
fi

cd "$ROOT_DIR"

docker compose exec -T "$POSTGRES_SERVICE" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 <<'SQL'
CREATE TABLE IF NOT EXISTS promptforge_schema_migrations (
    migration_name TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    source_path TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (migration_name, source_sha256)
);
SQL

source_sha256="$(sha256sum "$SCHEMA_FILE" | awk '{print $1}')"
existing_row="$(
  docker compose exec -T "$POSTGRES_SERVICE" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -v ON_ERROR_STOP=1 <<SQL
SELECT 1
FROM promptforge_schema_migrations
WHERE migration_name = '$MIGRATION_NAME'
  AND source_sha256 = '$source_sha256'
LIMIT 1;
SQL
)"

if [[ "$existing_row" == "1" ]]; then
  echo "Migration $MIGRATION_NAME already applied for $SCHEMA_FILE"
  exit 0
fi

echo "Applying migration $MIGRATION_NAME from $SCHEMA_FILE"
docker compose exec -T "$POSTGRES_SERVICE" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 < "$SCHEMA_FILE"

docker compose exec -T "$POSTGRES_SERVICE" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 <<SQL
INSERT INTO promptforge_schema_migrations (migration_name, source_sha256, source_path)
VALUES ('$MIGRATION_NAME', '$source_sha256', '$SCHEMA_FILE')
ON CONFLICT DO NOTHING;
SQL

echo "Applied migration $MIGRATION_NAME"
