#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  echo "docker compose is required" >&2
  exit 1
fi

desired_password="$(
  docker compose config --format json | python3 -c 'import json,sys; config=json.load(sys.stdin); print(config["services"]["postgres"]["environment"]["POSTGRES_PASSWORD"])'
)"

if [[ -z "$desired_password" ]]; then
  echo "Resolved POSTGRES_PASSWORD is empty" >&2
  exit 1
fi

docker compose exec -u postgres -T postgres psql -U promptforge -d promptforge -v ON_ERROR_STOP=1 -v password="$desired_password" <<'SQL'
ALTER USER promptforge WITH PASSWORD :'password';
SQL

docker compose exec -T postgres env PGPASSWORD="$desired_password" psql -h 127.0.0.1 -U promptforge -d promptforge -v ON_ERROR_STOP=1 -Atqc "SELECT 1" >/dev/null

echo "Postgres role password synchronized."
