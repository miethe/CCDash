# Phase 9 — Postgres Parity + Container/Compose
## Operator Guide

**Feature slug**: `ccdash-core-remediation` / Phase 9  
**Status**: delivered (Wave 4)  
**Gate**: Postgres / container convergence — no product features added.  
**Date**: 2026-06-11

---

## What Phase 9 Delivers

| Task | Artifact | Purpose |
|------|----------|---------|
| T9-001/T9-002 | `test_migration_governance.py` | Column inventory: Phase 5/6 columns parity-clean; allowlist audit |
| T9-003 | `LiveSchemaParityTests` in test_migration_governance.py | Live dual-backend parity (PG-gated) |
| T9-004 | `deploy/runtime/Dockerfile` (api + worker targets) | Named multi-stage image targets |
| T9-005 | `docker-compose.yml` (repo root) | All-in-one Postgres stack |
| T9-006 | `scripts/compose_smoke.sh` | E2E smoke harness |
| T9-007 | `backend/tests/test_pg_coalescing.py` | Durable-queue coalescing tests |
| T9-008 | `/readyz` in `backend/runtime/bootstrap.py` + `test_readyz_health.py` | API readyz probe |

---

## Column Parity Inventory (T9-001 Audit Result)

**Phase 5 detection columns** — `sessions` table, added by T5-006/T5-007:

| Column | SQLite DDL | Postgres DDL | Parity |
|--------|-----------|--------------|--------|
| `model_slug` | `TEXT DEFAULT ''` | `TEXT DEFAULT ''` | ✅ clean |
| `workflow_id` | `TEXT` (nullable) | `TEXT` (nullable) | ✅ clean |
| `subagent_parent_id` | `TEXT` (nullable) | `TEXT` (nullable) | ✅ clean |
| `skill_name` | `TEXT` (nullable) | `TEXT` (nullable) | ✅ clean |
| `context_window` | `TEXT` (nullable) | `TEXT` (nullable) | ✅ clean |

**Phase 6 pricing columns** — `sessions` table:

| Column | SQLite DDL | Postgres DDL | Parity |
|--------|-----------|--------------|--------|
| `context_window_size` | `INTEGER DEFAULT 0` | `INTEGER DEFAULT 0` | ✅ clean |
| `pricing_model_source` | `TEXT DEFAULT ''` | `TEXT DEFAULT ''` | ✅ clean |

**Allowlist audit** — `COLUMN_PARITY_DRIFT_ALLOWLIST` has 7 entries, all documented:

| Entry | DRIFT-NNN | Rationale |
|-------|-----------|-----------|
| `(outbound_telemetry_queue, event_type)` | DRIFT-001 | SQLite adds via migration procedure; PG has it in baseline DDL |
| `(session_relationships, created_at)` | DRIFT-002 | NOT NULL mismatch; both sides always write a value |
| `(oq_resolutions, created_at)` | DRIFT-003 | Nullability mismatch; harmless in practice |
| `(oq_resolutions, updated_at)` | DRIFT-003 | Nullability mismatch; harmless in practice |
| `(session_sentiment_facts, evidence_json)` | DRIFT-004 | Postgres NOT NULL, SQLite nullable; repo always writes non-NULL |
| `(session_code_churn_facts, evidence_json)` | DRIFT-005 | Same as DRIFT-004 |
| `(session_scope_drift_facts, evidence_json)` | DRIFT-006 | Same as DRIFT-004 |

**No new drift found.** T9-002 (DDL repair) is a no-op.

---

## Running the Compose Stack

### Prerequisites

- Docker 28+ with Compose v2 (`docker compose`)
- Available ports: 5432 (postgres), 8000 (api), 9465 (worker probe)
- **pgvector-capable Postgres image required** — the compose stack uses `pgvector/pgvector:pg15`
  (not plain `postgres:15-alpine`). Enterprise session-intelligence uses `CREATE EXTENSION vector`
  and the `app.session_embeddings.embedding vector` column; a plain Postgres image will crash
  migrations with `vector.control: No such file or directory`.

### Start (all-in-one)

```bash
# From repo root
docker compose up -d

# Wait for all services to be healthy
docker compose ps
```

### Environment Variables

All have sensible defaults for local testing. Override as needed:

```bash
# Required for external Postgres (otherwise the in-stack postgres is used)
export CCDASH_DATABASE_URL=postgresql://user:pass@db.example.com:5432/ccdash

# Optional: session-log directory (bind-mounted into api and worker)
export CCDASH_SESSION_LOG_PATH=/path/to/your/.claude/projects

# Optional: port remapping
export CCDASH_API_PORT=8001
export CCDASH_POSTGRES_PORT=5433
```

### Stop and Teardown

```bash
docker compose down --volumes --remove-orphans
```

---

## Running the E2E Smoke Harness (T9-006)

```bash
# Full smoke: boot → readyz → session check → teardown
./scripts/compose_smoke.sh

# Custom timeout (seconds to wait for /readyz)
READYZ_TIMEOUT=180 ./scripts/compose_smoke.sh

# Keep stack running after smoke (for manual inspection)
./scripts/compose_smoke.sh --no-teardown

# Explicit compose file
./scripts/compose_smoke.sh --compose-file docker-compose.yml
```

The harness exits non-zero on any failure and prints the last `/readyz` body if the API never becomes ready.

---

## Running Parity + Readyz Tests

### Non-PG tests (always runnable)

```bash
# Column parity + allowlist audit (static DDL parse; no live DB)
backend/.venv/bin/python -m pytest backend/tests/test_migration_governance.py -v

# /readyz health-gate unit tests (all three failure modes + happy path)
backend/.venv/bin/python -m pytest backend/tests/test_readyz_health.py -v

# Durable-queue coalescing tests (non-PG mock-based)
backend/.venv/bin/python -m pytest backend/tests/test_pg_coalescing.py -v
```

### PG-gated tests (require live Postgres)

These tests are **skipped** without `CCDASH_DATABASE_URL`. Run against the compose stack:

```bash
# Start compose stack first
docker compose up -d
# Wait for health: docker compose ps

# Run PG-gated tests against compose PG
export CCDASH_DATABASE_URL=postgresql://ccdash:ccdash@localhost:5432/ccdash

# Live dual-backend schema parity
backend/.venv/bin/python -m pytest backend/tests/test_migration_governance.py \
    -k "LiveSchemaParityTests" -v

# Live PG coalescing
backend/.venv/bin/python -m pytest backend/tests/test_pg_coalescing.py \
    -k "LivePGCoalescingTests" -v
```

---

## /readyz Endpoint Reference (T9-008)

**Endpoint**: `GET /readyz` on the API service (`:8000/readyz`)

**Response (200 — all healthy)**:
```json
{
  "schemaVersion": "1",
  "runtimeProfile": "api",
  "ready": true,
  "checks": {
    "db_connected": true,
    "migration_head_applied": true,
    "queue_reachable": true
  },
  "reasons": [],
  "reasonCodes": []
}
```

**Response (503 — partial failure)**:
```json
{
  "schemaVersion": "1",
  "runtimeProfile": "api",
  "ready": false,
  "checks": {
    "db_connected": false,
    "migration_head_applied": false,
    "queue_reachable": true
  },
  "reasons": [
    {"code": "db_unreachable", "detail": "connection refused"},
    {"code": "migration_behind", "detail": "db not connected"}
  ],
  "reasonCodes": ["db_unreachable", "migration_behind"]
}
```

**Reason codes**:
- `db_unreachable` — DB connection failed or no connection established
- `migration_behind` — `migrations_applied` does not contain the current `SCHEMA_VERSION` row
- `queue_unreachable` — `job_queue` table inaccessible (only when `JOB_QUEUE_BACKEND != memory`)

---

## Dockerfile Build Targets (T9-004)

The base `deploy/runtime/Dockerfile` now has three named stages:

| Target | Command | Profile | Probe |
|--------|---------|---------|-------|
| `runtime` | (base; use api or worker) | — | CCDASH_RUNTIME_PROFILE-aware |
| `api` | `docker build --target api` | `api` | `/readyz` on :8000 |
| `worker` | `docker build --target worker` | `worker` | `/readyz` on :9465 |

```bash
# Build api image only
docker build --target api -t ccdash-api:dev .

# Build worker image only
docker build --target worker -t ccdash-worker:dev .
```

---

## PG-Gated Test Inventory (for orchestrator)

The following tests are **PG-gated** (skipped without live PG; must pass against compose PG):

| Test file | Class | Tests |
|-----------|-------|-------|
| `backend/tests/test_migration_governance.py` | `LiveSchemaParityTests` | 5 tests |
| `backend/tests/test_pg_coalescing.py` | `LivePGCoalescingTests` | 2 tests |

Run command for orchestrator:
```bash
export CCDASH_DATABASE_URL=postgresql://ccdash:ccdash@localhost:5432/ccdash
backend/.venv/bin/python -m pytest \
    backend/tests/test_migration_governance.py \
    backend/tests/test_pg_coalescing.py \
    -v
```
