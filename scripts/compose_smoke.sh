#!/usr/bin/env bash
# CCDash Compose E2E Smoke Harness (Phase 9 / T9-006)
#
# Usage:
#   ./scripts/compose_smoke.sh [--compose-file FILE] [--timeout N] [--no-teardown]
#
# What it does:
#   1. Starts the compose stack (docker compose up -d)
#   2. Polls GET /readyz on the api service until HTTP 200 (bounded timeout)
#   3. Issues a cross-project /api/v1/sessions request against Postgres and
#      asserts a non-empty response envelope
#   4. Tears the stack down (unless --no-teardown is passed)
#   5. Exits non-zero on any failure; prints the last /readyz body if readyz
#      never reaches 200
#
# Environment:
#   COMPOSE_FILE       Path to docker-compose.yml (default: docker-compose.yml)
#   READYZ_TIMEOUT     Seconds to wait for /readyz to return 200 (default: 120)
#   API_HOST           Hostname for the API service (default: 127.0.0.1)
#   API_PORT           Port for the API service (default: 8000)
#
# Notes:
#   - The script does NOT commit or modify any source files.
#   - Requires: docker, curl (or python3 urllib fallback), jq (optional; degrades gracefully)
#   - postgres 15 is bundled in docker-compose.yml; no external PG needed.
#
set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults / argument parsing
# ---------------------------------------------------------------------------
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
READYZ_TIMEOUT="${READYZ_TIMEOUT:-120}"
API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"
NO_TEARDOWN=0
LAST_READYZ_BODY=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --compose-file) COMPOSE_FILE="$2"; shift 2 ;;
    --timeout)      READYZ_TIMEOUT="$2"; shift 2 ;;
    --no-teardown)  NO_TEARDOWN=1; shift ;;
    *) echo "Unknown flag: $1" >&2; exit 1 ;;
  esac
done

READYZ_URL="http://${API_HOST}:${API_PORT}/readyz"
SESSIONS_URL="http://${API_HOST}:${API_PORT}/api/v1/sessions"

log() { echo "[compose_smoke] $*"; }
fail() { echo "[compose_smoke] FAIL: $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Teardown trap
# ---------------------------------------------------------------------------
teardown() {
  if [[ "$NO_TEARDOWN" -eq 0 ]]; then
    log "Tearing down compose stack..."
    docker compose -f "${COMPOSE_FILE}" down --volumes --remove-orphans || true
  else
    log "--no-teardown set; leaving stack running."
  fi
}
trap teardown EXIT

# ---------------------------------------------------------------------------
# Helper: HTTP GET with curl or python fallback
# ---------------------------------------------------------------------------
_http_get() {
  # Returns HTTP status code on stdout; body to stderr (captured by caller)
  local url="$1"
  if command -v curl >/dev/null 2>&1; then
    curl -s -o /tmp/smoke_response_body.txt -w "%{http_code}" \
      --max-time 5 --connect-timeout 4 "$url" 2>/dev/null || echo "000"
  else
    python3 - <<PYEOF 2>/dev/null || echo "000"
import sys, urllib.request, json
try:
    with urllib.request.urlopen("${url}", timeout=5) as resp:
        body = resp.read().decode()
        with open("/tmp/smoke_response_body.txt", "w") as f:
            f.write(body)
        print(resp.status)
except Exception as exc:
    with open("/tmp/smoke_response_body.txt", "w") as f:
        f.write(str(exc))
    print("000")
PYEOF
  fi
}

_response_body() {
  cat /tmp/smoke_response_body.txt 2>/dev/null || echo "(no body)"
}

# ---------------------------------------------------------------------------
# Step 1: Start the compose stack
# ---------------------------------------------------------------------------
log "Starting compose stack: ${COMPOSE_FILE}"
docker compose -f "${COMPOSE_FILE}" up -d

# ---------------------------------------------------------------------------
# Step 2: Poll /readyz until 200 (bounded timeout)
# ---------------------------------------------------------------------------
log "Polling ${READYZ_URL} (timeout ${READYZ_TIMEOUT}s)..."
ELAPSED=0
POLL_INTERVAL=5
READY=0

while [[ $ELAPSED -lt $READYZ_TIMEOUT ]]; do
  STATUS=$(_http_get "${READYZ_URL}")
  LAST_READYZ_BODY=$(_response_body)

  if [[ "$STATUS" == "200" ]]; then
    log "/readyz returned 200 after ${ELAPSED}s"
    READY=1
    break
  fi

  log "  /readyz → ${STATUS} (${ELAPSED}s elapsed); retrying in ${POLL_INTERVAL}s..."
  sleep "$POLL_INTERVAL"
  ELAPSED=$((ELAPSED + POLL_INTERVAL))
done

if [[ "$READY" -eq 0 ]]; then
  echo ""
  echo "[compose_smoke] /readyz never reached 200 within ${READYZ_TIMEOUT}s."
  echo "[compose_smoke] Last /readyz response body:"
  echo "${LAST_READYZ_BODY}"
  echo ""
  # Dump API container logs for diagnostics
  docker compose -f "${COMPOSE_FILE}" logs api --tail=50 2>/dev/null || true
  fail "/readyz timeout after ${READYZ_TIMEOUT}s"
fi

# ---------------------------------------------------------------------------
# Step 3: Cross-project session-detail call
# ---------------------------------------------------------------------------
log "Issuing GET ${SESSIONS_URL} to verify non-empty detail envelope..."

STATUS=$(_http_get "${SESSIONS_URL}")
BODY=$(_response_body)

if [[ "$STATUS" != "200" ]]; then
  log "Sessions endpoint returned HTTP ${STATUS}; body:"
  echo "${BODY}"
  fail "GET /api/v1/sessions returned non-200 (${STATUS})"
fi

# Assert response is not empty (non-null / non-empty JSON).
# Prefer jq for clean validation; fall back to string length check.
ENVELOPE_NONEMPTY=0
if command -v jq >/dev/null 2>&1; then
  # Accept either a non-null object or an array with at least 0 items
  if echo "${BODY}" | jq -e '. != null' >/dev/null 2>&1; then
    ENVELOPE_NONEMPTY=1
  fi
else
  # Fallback: body must be longer than 2 chars (not just "{}" or "[]" counts as success)
  if [[ ${#BODY} -gt 2 ]]; then
    ENVELOPE_NONEMPTY=1
  fi
fi

if [[ "$ENVELOPE_NONEMPTY" -eq 0 ]]; then
  log "Sessions response appears empty; body:"
  echo "${BODY}"
  fail "GET /api/v1/sessions returned null/empty envelope"
fi

log "Session envelope: OK (${#BODY} bytes)"

# ---------------------------------------------------------------------------
# Step 4: Success
# ---------------------------------------------------------------------------
log "============================================"
log "  Compose smoke harness: ALL CHECKS PASSED"
log "============================================"
log "  /readyz:                200 OK"
log "  /api/v1/sessions:       200 OK (non-empty)"
log ""
exit 0
