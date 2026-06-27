#!/usr/bin/env bash
# smoke-assert.sh — Poll the CCDash enterprise stack and assert health invariants.
#
# Usage:
#   ./deploy/runtime/scripts/smoke-assert.sh [API_URL] [READYZ_URL] [TIMEOUT_SECONDS]
#
# Defaults:
#   API_URL=http://localhost:8000
#   READYZ_URL=http://localhost:9466   (worker-watch probe; falls back to 9465)
#   TIMEOUT_SECONDS=120
#
# Exit codes:
#   0  All assertions passed
#   1  One or more assertions failed or timed out
#
# Runnable locally against a live enterprise stack:
#   docker compose --profile enterprise --profile postgres -f deploy/runtime/compose.yaml up -d --wait
#   CCDASH_EXTRA_MOUNT_1_HOST=deploy/runtime/test-fixtures/sessions \
#     CCDASH_EXTRA_MOUNT_1_CONTAINER=/mnt/ccdash/smoke-sessions \
#     ./deploy/runtime/scripts/smoke-assert.sh
set -euo pipefail

API_URL="${1:-${CCDASH_SMOKE_API_URL:-http://localhost:8000}}"
READYZ_URL="${2:-${CCDASH_SMOKE_READYZ_URL:-http://localhost:9466}}"
TIMEOUT="${3:-${CCDASH_SMOKE_TIMEOUT:-120}}"

SESSIONS_ENDPOINT="${API_URL}/api/sessions"
READYZ_ENDPOINT="${READYZ_URL}/readyz"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${YELLOW}[smoke]${NC} $*"; }
ok()    { echo -e "${GREEN}[PASS]${NC}  $*"; }
fail()  { echo -e "${RED}[FAIL]${NC}  $*" >&2; }

# ---------------------------------------------------------------------------
# 1. Poll GET /api/sessions until row count >= 1 or timeout
# ---------------------------------------------------------------------------
info "Polling ${SESSIONS_ENDPOINT} for at least 1 session (timeout ${TIMEOUT}s) ..."

deadline=$(( $(date +%s) + TIMEOUT ))
session_count=0
poll_interval=5

while true; do
    now=$(date +%s)
    if (( now >= deadline )); then
        fail "Timed out after ${TIMEOUT}s waiting for sessions. Got ${session_count} rows."
        exit 1
    fi

    http_code=$(curl -s -o /tmp/smoke_sessions.json -w "%{http_code}" \
        --max-time 10 \
        "${SESSIONS_ENDPOINT}" 2>/dev/null || echo "000")

    if [[ "${http_code}" == "200" ]]; then
        # Response can be a JSON array or {"items": [...], "total": N} object.
        session_count=$(python3 - /tmp/smoke_sessions.json 2>/dev/null <<'PY'
import json, sys
try:
    data = json.load(open(sys.argv[1]))
except Exception:
    print(0)
    sys.exit(0)
if isinstance(data, list):
    print(len(data))
elif isinstance(data, dict):
    # Try common envelope shapes: total, count, items
    for key in ("total", "count"):
        if isinstance(data.get(key), int):
            print(data[key])
            sys.exit(0)
    items = data.get("items") or data.get("sessions") or data.get("data") or []
    print(len(items) if isinstance(items, list) else 0)
else:
    print(0)
PY
        )
        if (( session_count >= 1 )); then
            ok "GET /api/sessions returned ${session_count} row(s)."
            break
        fi
        info "  sessions endpoint returned HTTP 200 but ${session_count} rows — waiting ${poll_interval}s ..."
    else
        info "  sessions endpoint returned HTTP ${http_code} — waiting ${poll_interval}s ..."
    fi
    sleep "${poll_interval}"
done

# ---------------------------------------------------------------------------
# 2. Assert worker readyz returns HTTP 200 (watch-paths > 0 configured)
# ---------------------------------------------------------------------------
info "Asserting ${READYZ_ENDPOINT} returns HTTP 200 (worker-watch ready) ..."

readyz_code=$(curl -s -o /tmp/smoke_readyz.json -w "%{http_code}" \
    --max-time 10 \
    "${READYZ_ENDPOINT}" 2>/dev/null || echo "000")

if [[ "${readyz_code}" == "200" ]]; then
    ok "Worker readyz (${READYZ_ENDPOINT}) returned HTTP 200."
else
    fail "Worker readyz (${READYZ_ENDPOINT}) returned HTTP ${readyz_code} — expected 200."
    info "  readyz body:"
    cat /tmp/smoke_readyz.json >&2 || true
    # -------------------------------------------------------------------
    # NEGATIVE ASSERTION NOTE:
    #
    # The positive readyz probe above expects HTTP 200 (watch paths > 0).
    # The complementary negative assertion — when worker-watch is configured
    # with zero valid watch paths (CCDASH_WORKER_WATCH_PROJECT_ID resolves
    # to a project id absent from the registry), readyz MUST return HTTP 503
    # with reason "configured_no_paths" — is exercised by the `smoke-no-paths`
    # job in .github/workflows/enterprise-e2e-smoke.yml.
    #
    # That negative assertion cannot run against this same stack instance
    # (it requires intentionally misconfiguring the watcher).
    # T0-003 (fail-loud readyz when watch-paths==0) has landed; the CI gate
    # is now active and is a required status check on main.
    # -------------------------------------------------------------------
    exit 1
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
ok "All smoke assertions passed."
ok "  Sessions ingested : ${session_count}"
ok "  Worker readyz     : HTTP ${readyz_code}"
