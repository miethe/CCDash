# Telemetry and Analytics Implementation Reference

Consolidated Track A and Track B implementation reference for CCDash telemetry, analytics, and observability.

> Consolidated from the former top-level user and developer docs. `docs/project_plans/` content was intentionally left untouched.

## Track A Implementation Reference

This document describes the implemented changes from Track A in:

- `docs/project_plans/implementation_plans/telemetry-analytics-modernization-v1.md`

### Summary

Implemented Track A outcomes:

1. Correctness and persistence parity for task completion and session telemetry.
2. New analytics query endpoints and alert CRUD APIs.
3. UI wiring to backend-derived analytics (no hardcoded dashboard KPI values, no simulated token timeline, persisted alert settings).

### Backend Changes

#### 1. Task completion semantics

Task completion metrics now treat these statuses as terminal-complete:

- `done`
- `deferred`
- `completed` (legacy compatibility)

Updated files:

- `backend/db/repositories/tasks.py`
- `backend/db/repositories/postgres/tasks.py`

Impact:

- `task_velocity` and `task_completion_pct` no longer return incorrect zero values when tasks are tracked as `done`/`deferred`.

#### 2. Session telemetry persistence

Implemented persistence and rehydration for session timeline/date/impact fields.

New `sessions` columns:

- `dates_json` (`TEXT`, default `'{}'`)
- `timeline_json` (`TEXT`, default `'[]'`)
- `impact_history_json` (`TEXT`, default `'[]'`)

Schema version bumps:

- SQLite: `SCHEMA_VERSION = 8`
- Postgres: `SCHEMA_VERSION = 6`

Updated files:

- `backend/db/sqlite_migrations.py`
- `backend/db/postgres_migrations.py`
- `backend/db/repositories/sessions.py`
- `backend/db/repositories/postgres/sessions.py`
- `backend/routers/api.py`

#### 3. Tool duration capture (`session_tool_usage.total_ms`)

Implemented real duration capture from tool-use to tool-result timestamps.

- Parser now computes per-tool elapsed duration and stores `ToolUsage.totalMs`.
- Repositories now persist `total_ms` during `upsert_tool_usage`.

Updated files:

- `backend/parsers/sessions.py`
- `backend/models.py`
- `backend/db/repositories/sessions.py`
- `backend/db/repositories/postgres/sessions.py`

#### 4. Token timeline data source

Message-level token usage metadata is now persisted in session logs when available:

- `inputTokens`
- `outputTokens`
- `totalTokens`

Used by `/api/analytics/series?metric=session_tokens&session_id=...` to build real cumulative token timeline points.

Updated files:

- `backend/parsers/sessions.py`
- `backend/routers/analytics.py`

#### 5. Analytics metric metadata and entity links

Analytics capture now writes:

- non-empty `analytics_entries.metadata_json`
- `analytics_entity_links` entries (currently linked at minimum to project scope)

Updated file:

- `backend/db/sync_engine.py`

### Analytics API Surface

Implemented in:

- `backend/routers/analytics.py`

#### New endpoints

1. `GET /api/analytics/overview`
   - Returns KPI payload plus top model usage.
2. `GET /api/analytics/series`
   - Supports `point|hourly|daily|weekly` rollups.
   - Supports session token timeline mode with `session_id`.
3. `GET /api/analytics/breakdown`
   - Supports dimensions: `model`, `model_family`, `session_type`, `tool`, `agent`, `skill`, `feature`.
4. `GET /api/analytics/correlation`
   - Returns correlated session/feature link data with confidence metadata.
5. Alert CRUD:
   - `POST /api/analytics/alerts`
   - `PATCH /api/analytics/alerts/{id}`
   - `DELETE /api/analytics/alerts/{id}`

#### Compatibility endpoints retained

1. `GET /api/analytics/metrics`
2. `GET /api/analytics/trends`
3. `GET /api/analytics/export/prometheus`

### Frontend Wiring

#### Dashboard

`components/Dashboard.tsx` now loads analytics from backend:

- KPIs from `GET /api/analytics/overview`
- Cost and velocity series from `GET /api/analytics/series`
- Model usage chart from overview payload

Removed dependency on hardcoded KPI/model values for displayed dashboard metrics.

#### Session Inspector

`components/SessionInspector.tsx` token timeline now uses:

- `GET /api/analytics/series?metric=session_tokens&period=point&session_id=...`

Fallback behavior:

- If series fetch fails, it reconstructs from persisted log token metadata (`totalTokens`) rather than synthetic random values.

#### Settings Alerts

`components/Settings.tsx` alerts tab now performs persisted CRUD:

- create alert (`POST`)
- toggle active/inactive (`PATCH`)
- delete alert (`DELETE`)

### Shared Types / Services

Updated files:

- `services/analytics.ts`
- `types.ts`

New/expanded client support includes:

- overview/series/breakdown/correlation API methods
- alert CRUD methods
- analytics type extensions
- tool usage optional `totalMs`
- alert metric type widened for backend metric IDs

### Tests Added/Updated

New tests:

- `backend/tests/test_tasks_repository.py`
- `backend/tests/test_analytics_router.py`

Updated tests:

- `backend/tests/test_sessions_parser.py`

Coverage focus:

1. completion semantics (`done`/`deferred`/`completed`)
2. token metadata extraction for log-derived timelines
3. tool duration persistence path
4. analytics series and alert CRUD behavior

### Operational Notes

1. Run migrations on startup as normal; schema upgrades are additive.
2. To refresh existing cached analytics with new semantics/metadata, run a sync and analytics rebuild.
3. If historical sessions predate these parser changes, token timeline resolution depends on previously captured usage metadata.

### File Index

Primary implementation files:

- `backend/db/sync_engine.py`
- `backend/routers/analytics.py`
- `backend/routers/api.py`
- `backend/parsers/sessions.py`
- `backend/models.py`
- `backend/db/repositories/tasks.py`
- `backend/db/repositories/postgres/tasks.py`
- `backend/db/repositories/sessions.py`
- `backend/db/repositories/postgres/sessions.py`
- `backend/db/sqlite_migrations.py`
- `backend/db/postgres_migrations.py`
- `services/analytics.ts`
- `components/Dashboard.tsx`
- `components/SessionInspector.tsx`
- `components/Settings.tsx`
- `types.ts`

## Track B Implementation Reference

This document captures Track B implementation details from:

- `docs/project_plans/implementation_plans/telemetry-analytics-modernization-v1.md`

### Summary

Track B delivery now includes:

1. `telemetry_events` fact storage + backfill and incremental ingestion.
2. Optional OTel instrumentation (traces + metrics) with Prometheus fallback metrics.
3. Self-hosted observability bundle (Collector + Prometheus + Grafana + Tempo + Loki) with pre-provisioned dashboards.

### B1: Telemetry Fact Model and Backfill

#### Schema

Added `telemetry_events` to both DB backends:

- `backend/db/sqlite_migrations.py` (`SCHEMA_VERSION = 9`)
- `backend/db/postgres_migrations.py` (`SCHEMA_VERSION = 7`)

Key dimensions include:

- project/session/root session IDs
- feature/task/commit/PR context
- event type, tool, model, agent, skill, status
- duration/tokens/cost metrics
- full payload JSON and deterministic source key

#### Sync ingestion

`backend/db/sync_engine.py` now:

1. Builds normalized telemetry events for each synced session.
2. Replaces session-scoped event rows atomically on each session sync.
3. Performs one-time project backfill when telemetry table is empty and sessions already exist.

#### Backfill job

Manual job added:

- `backend/scripts/telemetry_backfill.py`

Examples:

```bash
python backend/scripts/telemetry_backfill.py
python backend/scripts/telemetry_backfill.py --project default-skillmeat
python backend/scripts/telemetry_backfill.py --all-projects
```

#### Tests

- `backend/tests/test_sync_engine_telemetry.py`

### B2: OTel Instrumentation

#### Runtime module

New module:

- `backend/observability/otel.py`

Capabilities:

1. Optional OTel bootstrap with OTLP HTTP exporters.
2. FastAPI request instrumentation.
3. Counters/histograms for ingestion, parser failures, tool reliability, token/cost metrics.
4. Prometheus fallback metrics server (if configured).

#### Startup wiring

- `backend/main.py` now initializes and shuts down observability providers during app lifespan.

#### Config

Added env vars in `backend/config.py`:

- `CCDASH_OTEL_ENABLED` (default `false`)
- `CCDASH_OTEL_ENDPOINT` (default `http://localhost:4318`)
- `CCDASH_OTEL_SERVICE_NAME` (default `ccdash-backend`)
- `CCDASH_PROM_PORT` (default `9464`)

#### Dependencies

Added to `backend/requirements.txt`:

- `opentelemetry-api`
- `opentelemetry-sdk`
- `opentelemetry-exporter-otlp-proto-http`
- `opentelemetry-instrumentation-fastapi`
- `prometheus-client`

#### Prom export enrichment

`backend/routers/analytics.py` now exports additional labeled metrics:

1. Tool call counts and average duration by tool/status.
2. Token and cost totals by model/direction.
3. Link confidence and unresolved-link counts.
4. Session thread fanout summaries.

### B3: Self-Hosted Observability Stack

Assets added under `deploy/observability`:

1. `docker-compose.yml` (collector, prometheus, grafana, tempo, loki)
2. `otel-collector-config.yaml`
3. `prometheus/prometheus.yml`
4. `tempo.yaml`
5. Grafana provisioning:
   - `grafana/provisioning/datasources/datasources.yml`
   - `grafana/provisioning/dashboards/dashboards.yml`
6. Dashboards:
   - `grafana/dashboards/ingestion-health-lag.json`
   - `grafana/dashboards/token-cost-efficiency.json`
   - `grafana/dashboards/tool-reliability-retry-burden.json`
   - `grafana/dashboards/session-thread-complexity-latency.json`
   - `grafana/dashboards/link-confidence-ambiguity.json`

#### Quick start

```bash
cd deploy/observability
docker compose up -d
```

Default local ports:

1. Grafana: `http://localhost:3001`
2. Prometheus: `http://localhost:9090`
3. OTel HTTP receiver: `http://localhost:4318`

### Validation

Executed during implementation:

1. `python -m pytest backend/tests/test_sync_engine_telemetry.py backend/tests/test_sync_engine_linking.py backend/tests/test_analytics_router.py -q`
2. `python -m compileall backend`
