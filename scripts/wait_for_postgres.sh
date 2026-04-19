#!/usr/bin/env bash
set -euo pipefail

DATABASE_URL="${1:-${PROMPTFORGE_DATABASE_URL:-${DATABASE_URL:-}}}"
TIMEOUT_SECONDS="${PROMPTFORGE_POSTGRES_TIMEOUT_SECONDS:-90}"
SLEEP_SECONDS="${PROMPTFORGE_POSTGRES_RETRY_SECONDS:-2}"

if [[ -z "${DATABASE_URL}" ]]; then
  echo "PROMPTFORGE_DATABASE_URL or DATABASE_URL is required" >&2
  exit 1
fi

if command -v python3 >/dev/null 2>&1 && python3 - <<'PY' >/dev/null 2>&1
import importlib.util
raise SystemExit(0 if importlib.util.find_spec("psycopg") else 1)
PY
then
  python3 - "$DATABASE_URL" "$TIMEOUT_SECONDS" "$SLEEP_SECONDS" <<'PY'
from __future__ import annotations

import sys
import time

import psycopg

database_url = sys.argv[1]
timeout_seconds = float(sys.argv[2])
sleep_seconds = float(sys.argv[3])
deadline = time.monotonic() + timeout_seconds
last_error: Exception | None = None

while time.monotonic() < deadline:
    try:
        with psycopg.connect(database_url, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        print("Postgres is ready.")
        raise SystemExit(0)
    except Exception as exc:  # pragma: no cover - readiness loop
        last_error = exc
        time.sleep(sleep_seconds)

print(f"Timed out waiting for Postgres: {last_error}", file=sys.stderr)
raise SystemExit(1)
PY
  exit 0
fi

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  if ! docker compose ps postgres >/dev/null 2>&1; then
    echo "postgres service is not running in docker compose" >&2
    exit 1
  fi

  deadline=$((SECONDS + TIMEOUT_SECONDS))
  until docker compose exec -T postgres pg_isready -U promptforge -d promptforge >/dev/null 2>&1; do
    if (( SECONDS >= deadline )); then
      echo "Timed out waiting for docker compose postgres service" >&2
      exit 1
    fi
    sleep "$SLEEP_SECONDS"
  done
  echo "Postgres is ready."
  exit 0
fi

echo "Unable to check Postgres readiness: install psycopg or run inside docker compose" >&2
exit 1
