#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8090}"
CONSOLE_URL="${CONSOLE_URL:-http://localhost:5173}"

pass_count=0
fail_count=0
separator=$'\x1f'

now_ms() {
  local realtime="${EPOCHREALTIME:-${SECONDS}.000000}"
  local seconds="${realtime%%.*}"
  local micros="${realtime#*.}000000"
  micros="${micros:0:3}"
  printf '%s\n' "$((10#$seconds * 1000 + 10#$micros))"
}

print_summary() {
  printf 'Passed: %d Failed: %d\n' "$pass_count" "$fail_count"
}

fail_check() {
  local label="$1"
  local elapsed_ms="$2"
  local http_code="$3"
  local body="$4"
  local reason="$5"

  fail_count=$((fail_count + 1))
  printf 'FAIL %s (%s ms)\n' "$label" "$elapsed_ms"
  printf '  reason: %s\n' "$reason"
  printf '  http: %s\n' "$http_code"
  printf '  body: %s\n' "${body:0:200}"
  print_summary
  exit 1
}

run_check() {
  local label="$1"
  local url="$2"
  local expected_code="$3"
  local expected_body_fragment="${4:-}"
  local response=""
  local body=""
  local http_code="000"
  local curl_rc=0
  local start_ms
  local elapsed_ms

  start_ms="$(now_ms)"
  if response="$(curl -sS "$url" -w "${separator}%{http_code}")"; then
    curl_rc=0
  else
    curl_rc=$?
  fi
  elapsed_ms="$(( $(now_ms) - start_ms ))"

  if [[ "$response" == *"$separator"* ]]; then
    http_code="${response##*$separator}"
    body="${response%$separator*}"
  else
    body="$response"
  fi

  if [[ "$curl_rc" -ne 0 ]]; then
    fail_check "$label" "$elapsed_ms" "$http_code" "$body" "curl request failed"
  fi

  if [[ "$http_code" != "$expected_code" ]]; then
    fail_check "$label" "$elapsed_ms" "$http_code" "$body" "expected HTTP ${expected_code}"
  fi

  if [[ -n "$expected_body_fragment" && "$body" != *"$expected_body_fragment"* ]]; then
    fail_check "$label" "$elapsed_ms" "$http_code" "$body" "body missing '${expected_body_fragment}'"
  fi

  pass_count=$((pass_count + 1))
  printf 'PASS %s (%s ms)\n' "$label" "$elapsed_ms"
}

run_check "API health" "${BASE_URL}/_healthz" "200" "ok"
run_check "Console" "${CONSOLE_URL}/" "200"
run_check "Bootstrap" "${BASE_URL}/console/bootstrap" "200" "projects"
run_check "Projects list" "${BASE_URL}/console/projects" "200"
run_check "Queue depth" "${BASE_URL}/console/metrics/queue-depth" "200"

print_summary
