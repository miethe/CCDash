#!/usr/bin/env bash
# smoke-seeded-pg.sh — Seeded-v29 Postgres upgrade-path smoke test (T1-005 P1).
#
# Purpose: boot a PG container initialised from deploy/runtime/fixtures/pg-seed-v29.sql
# (schema_version=29, sessions table WITHOUT project_id), start the api container
# against it, wait for /api/health/ready, assert migrationStatus=="applied", and
# assert UndefinedColumnError is ABSENT from the PG container logs.
#
# This test proves the T1-002 migration reorder fix: the api must reach v35 without
# any UndefinedColumnError on sessions.project_id.
#
# Usage (from repo root):
#   npm run docker:hosted:smoke:seeded-pg
#   # or directly:
#   bash deploy/runtime/scripts/smoke-seeded-pg.sh
#
# Exit codes:
#   0  All assertions passed
#   1  One or more assertions failed or timed out
#
# Re-run (idempotency): the compose project name ccdash-seeded-smoke isolates
# volumes from the main ccdash stack.  The script tears down on exit so
# re-run starts from a clean slate.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
COMPOSE_FILE="${REPO_ROOT}/deploy/runtime/compose.yaml"
FIXTURE_SQL="${REPO_ROOT}/deploy/runtime/fixtures/pg-seed-v29.sql"
SMOKE_PROJECT="ccdash-seeded-smoke"
API_PORT="${CCDASH_SEEDED_SMOKE_API_PORT:-18000}"
API_URL="http://127.0.0.1:${API_PORT}"
TIMEOUT="${CCDASH_SEEDED_SMOKE_TIMEOUT:-90}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${YELLOW}[seeded-smoke]${NC} $*"; }
ok()    { echo -e "${GREEN}[PASS]${NC}  $*"; }
fail()  { echo -e "${RED}[FAIL]${NC}  $*" >&2; }

# ---------------------------------------------------------------------------
# Prerequisite checks
# ---------------------------------------------------------------------------
if [[ ! -f "${FIXTURE_SQL}" ]]; then
    fail "Fixture not found: ${FIXTURE_SQL}"
    exit 1
fi

if ! command -v docker &>/dev/null; then
    fail "docker not found in PATH — cannot run seeded-pg smoke"
    exit 1
fi

# ---------------------------------------------------------------------------
# Cleanup on exit (idempotent tear-down)
# ---------------------------------------------------------------------------
cleanup() {
    info "Tearing down seeded-smoke stack (project: ${SMOKE_PROJECT}) ..."
    docker compose \
        --project-name "${SMOKE_PROJECT}" \
        --file "${COMPOSE_FILE}" \
        --profile enterprise \
        --profile postgres \
        down --volumes --remove-orphans 2>/dev/null || true
}
trap cleanup EXIT

# Ensure clean state from any previous run
cleanup

# ---------------------------------------------------------------------------
# Build a minimal env file with overrides for the seeded smoke run
# ---------------------------------------------------------------------------
ENV_FILE="$(mktemp /tmp/ccdash-seeded-smoke.XXXXXX.env)"
trap 'rm -f "${ENV_FILE}"' EXIT

cat >"${ENV_FILE}" <<ENV
CCDASH_STORAGE_PROFILE=enterprise
CCDASH_DB_BACKEND=postgres
CCDASH_PROJECT_ROOT=/app
CCDASH_POSTGRES_DB=ccdash
CCDASH_POSTGRES_USER=ccdash
CCDASH_POSTGRES_PASSWORD=ccdash
CCDASH_API_BEARER_TOKEN=ccdash-seeded-smoke-token
CCDASH_API_PORT=${API_PORT}
CCDASH_API_UPSTREAM=http://api:8000
CCDASH_WORKER_PROJECT_ID=seeded-smoke-project
CCDASH_WORKER_PROBE_HOST=0.0.0.0
CCDASH_WORKER_PROBE_PORT=19465
CCDASH_TELEMETRY_EXPORT_ENABLED=false
CCDASH_SAM_ENDPOINT=
CCDASH_SAM_API_KEY=
VITE_CCDASH_API_BASE_URL=/api
ENV

# ---------------------------------------------------------------------------
# Write a minimal compose override that mounts the seed SQL as PG init script
# ---------------------------------------------------------------------------
OVERRIDE_FILE="$(mktemp /tmp/ccdash-seeded-smoke-override.XXXXXX.yaml)"
trap 'rm -f "${OVERRIDE_FILE}" "${ENV_FILE}"' EXIT

cat >"${OVERRIDE_FILE}" <<YAML
services:
  postgres:
    volumes:
      - "${FIXTURE_SQL}:/docker-entrypoint-initdb.d/00-seed-v29.sql:ro"
YAML

# ---------------------------------------------------------------------------
# Start the postgres + api services (no worker needed for migration test)
# ---------------------------------------------------------------------------
info "Starting seeded-v29 PG + api containers (project: ${SMOKE_PROJECT}) ..."
docker compose \
    --project-name "${SMOKE_PROJECT}" \
    --env-file "${ENV_FILE}" \
    --file "${COMPOSE_FILE}" \
    --file "${OVERRIDE_FILE}" \
    --profile enterprise \
    --profile postgres \
    up --build -d postgres api

# ---------------------------------------------------------------------------
# Poll /api/health/ready until migrationStatus=="applied" or timeout
# ---------------------------------------------------------------------------
info "Polling ${API_URL}/api/health/ready (timeout ${TIMEOUT}s) ..."
deadline=$(( $(date +%s) + TIMEOUT ))
migration_status=""
last_http_code="000"

while true; do
    now=$(date +%s)
    if (( now >= deadline )); then
        fail "Timed out after ${TIMEOUT}s waiting for /api/health/ready."
        fail "Last HTTP code: ${last_http_code} | migrationStatus: '${migration_status}'"
        exit 1
    fi

    last_http_code=$(curl -s -o /tmp/seeded_smoke_ready.json \
        -w "%{http_code}" \
        --max-time 8 \
        "${API_URL}/api/health/ready" 2>/dev/null || echo "000")

    if [[ "${last_http_code}" == "200" ]]; then
        migration_status=$(python3 - /tmp/seeded_smoke_ready.json 2>/dev/null <<'PY'
import json, sys
try:
    data = json.load(open(sys.argv[1]))
    print(data.get("migrationStatus", ""))
except Exception:
    print("")
PY
        )
        if [[ "${migration_status}" == "applied" ]]; then
            ok "/api/health/ready returned migrationStatus==\"applied\"."
            break
        fi
        info "  HTTP 200 but migrationStatus='${migration_status}' — waiting 5s ..."
    else
        info "  HTTP ${last_http_code} — waiting 5s ..."
    fi
    sleep 5
done

# ---------------------------------------------------------------------------
# Assert UndefinedColumnError is ABSENT from PG container logs
# ---------------------------------------------------------------------------
info "Checking PG container logs for UndefinedColumnError ..."

PG_CONTAINER=$(docker compose \
    --project-name "${SMOKE_PROJECT}" \
    --env-file "${ENV_FILE}" \
    --file "${COMPOSE_FILE}" \
    --file "${OVERRIDE_FILE}" \
    --profile enterprise \
    --profile postgres \
    ps -q postgres 2>/dev/null | head -1)

if [[ -z "${PG_CONTAINER}" ]]; then
    fail "Could not find postgres container for project ${SMOKE_PROJECT}"
    exit 1
fi

PG_LOGS=$(docker logs "${PG_CONTAINER}" 2>&1 || true)

if echo "${PG_LOGS}" | grep -q "UndefinedColumnError"; then
    fail "UndefinedColumnError found in PG container logs — migration ordering bug."
    echo "${PG_LOGS}" | grep -C 5 "UndefinedColumnError" >&2
    exit 1
fi
ok "UndefinedColumnError ABSENT from PG container logs."

# Also check api container logs for the error pattern
API_CONTAINER=$(docker compose \
    --project-name "${SMOKE_PROJECT}" \
    --env-file "${ENV_FILE}" \
    --file "${COMPOSE_FILE}" \
    --file "${OVERRIDE_FILE}" \
    --profile enterprise \
    --profile postgres \
    ps -q api 2>/dev/null | head -1)

if [[ -n "${API_CONTAINER}" ]]; then
    API_LOGS=$(docker logs "${API_CONTAINER}" 2>&1 || true)
    if echo "${API_LOGS}" | grep -q "UndefinedColumnError"; then
        fail "UndefinedColumnError found in api container logs — migration ordering bug."
        echo "${API_LOGS}" | grep -C 5 "UndefinedColumnError" >&2
        exit 1
    fi
    ok "UndefinedColumnError ABSENT from api container logs."
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
ok "All seeded-pg smoke assertions passed."
ok "  PG seed version   : v29 (sessions table without project_id)"
ok "  Migration result  : ${migration_status} (reached SCHEMA_VERSION=35)"
ok "  UndefinedColumnError : ABSENT"
