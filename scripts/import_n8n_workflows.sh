#!/usr/bin/env bash
set -euo pipefail

detect_container() {
  local candidates=(
    "promptforge-n8n"
    "n8n-n8n-1"
  )

  for name in "${candidates[@]}"; do
    if docker ps --format '{{.Names}}' | grep -Fxq "$name"; then
      printf '%s\n' "$name"
      return 0
    fi
  done

  docker ps --format '{{.Names}}' | grep -E '(^|-)n8n($|-)' | head -n 1
}

CONTAINER_NAME="${1:-$(detect_container)}"
WORKFLOW_DIR="${2:-docs/planning/n8n_workflows}"
CONTAINER_DIR="/tmp/promptforge-n8n-workflows"

if [[ -z "${CONTAINER_NAME:-}" ]]; then
  echo "unable to detect n8n container; pass it explicitly as arg 1" >&2
  exit 1
fi

if [[ ! -d "$WORKFLOW_DIR" ]]; then
  echo "workflow directory not found: $WORKFLOW_DIR" >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required" >&2
  exit 1
fi

docker exec -u node "$CONTAINER_NAME" sh -lc "rm -rf '$CONTAINER_DIR' && mkdir -p '$CONTAINER_DIR'"
docker cp "$WORKFLOW_DIR/." "$CONTAINER_NAME:$CONTAINER_DIR/"
docker exec -u node "$CONTAINER_NAME" n8n import:workflow --separate --input="$CONTAINER_DIR"

echo "Imported PromptForge workflows from $WORKFLOW_DIR into $CONTAINER_NAME"
