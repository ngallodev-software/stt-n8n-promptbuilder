#!/usr/bin/env bash
set -euo pipefail

WAIT_SCRIPT="${WAIT_SCRIPT:-/usr/local/bin/wait_for_postgres.sh}"
DATABASE_URL="${PROMPTFORGE_DATABASE_URL:-postgresql://promptforge:change_me@postgres:5432/promptforge}"
VAULT_PATH="${PROMPTFORGE_VAULT_PATH:-/vault}"
API_HEALTH_URL="${PROMPTFORGE_API_HEALTH_URL:-http://promptforge-api:8090/_healthz}"
N8N_HEALTH_URL="${PROMPTFORGE_N8N_HEALTH_URL:-http://n8n:5678/healthz}"
WAIT_TIMEOUT_SECONDS="${PROMPTFORGE_SERVICE_WAIT_TIMEOUT_SECONDS:-120}"
WAIT_SLEEP_SECONDS="${PROMPTFORGE_SERVICE_WAIT_RETRY_SECONDS:-2}"

mkdir -p "$VAULT_PATH"
mkdir -p "$VAULT_PATH/${PROMPTFORGE_WATCH_FOLDER:-Inbox/Voice}"
mkdir -p "$VAULT_PATH/${PROMPTFORGE_PROCESSED_FOLDER:-Processed/Voice}"
mkdir -p "$VAULT_PATH/${PROMPTFORGE_ERROR_FOLDER:-Processing/Error}"

if [[ -x "$WAIT_SCRIPT" ]]; then
  "$WAIT_SCRIPT" "$DATABASE_URL"
else
  echo "wait_for_postgres.sh not found at $WAIT_SCRIPT" >&2
  exit 1
fi

python3 - "$API_HEALTH_URL" "$WAIT_TIMEOUT_SECONDS" "$WAIT_SLEEP_SECONDS" <<'PY'
from __future__ import annotations

import sys
import time
import urllib.error
import urllib.request

health_url = sys.argv[1]
timeout_seconds = float(sys.argv[2])
sleep_seconds = float(sys.argv[3])
deadline = time.monotonic() + timeout_seconds
last_error: Exception | None = None

while time.monotonic() < deadline:
    try:
        with urllib.request.urlopen(health_url, timeout=5) as response:
            if response.status < 400:
                raise SystemExit(0)
    except Exception as exc:  # pragma: no cover - readiness loop
        last_error = exc
        time.sleep(sleep_seconds)

print(f"Timed out waiting for API health at {health_url}: {last_error}", file=sys.stderr)
raise SystemExit(1)
PY

python3 - "$N8N_HEALTH_URL" "$WAIT_TIMEOUT_SECONDS" "$WAIT_SLEEP_SECONDS" <<'PY'
from __future__ import annotations

import sys
import time
import urllib.error
import urllib.request

health_url = sys.argv[1]
timeout_seconds = float(sys.argv[2])
sleep_seconds = float(sys.argv[3])
deadline = time.monotonic() + timeout_seconds
last_error: Exception | None = None

while time.monotonic() < deadline:
    try:
        with urllib.request.urlopen(health_url, timeout=5) as response:
            if response.status < 400:
                raise SystemExit(0)
    except Exception as exc:  # pragma: no cover - readiness loop
        last_error = exc
        time.sleep(sleep_seconds)

print(f"Timed out waiting for n8n health at {health_url}: {last_error}", file=sys.stderr)
raise SystemExit(1)
PY

exec python -m promptforge_watcher
