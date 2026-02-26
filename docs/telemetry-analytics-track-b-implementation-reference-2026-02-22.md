---
title: "Telemetry + Analytics Track B Implementation Reference"
description: "Telemetry fact model, OTel instrumentation, and self-hosted observability stack implementation details"
audience: [developers, maintainers, platform-engineers]
tags: [analytics, telemetry, otel, prometheus, grafana, tempo]
created: 2026-02-22
updated: 2026-02-22
category: "developer-reference"
status: "implemented"
---

# Telemetry + Analytics Track B Implementation Reference

This document captures Track B implementation details from:

- `docs/project_plans/implementation_plans/telemetry-analytics-modernization-v1.md`

## Summary

Track B delivery now includes:

1. `telemetry_events` fact storage + backfill and incremental ingestion.
2. Optional OTel instrumentation (traces + metrics) with Prometheus fallback metrics.
3. Self-hosted observability bundle (Collector + Prometheus + Grafana + Tempo + Loki) with pre-provisioned dashboards.

## B1: Telemetry Fact Model and Backfill

### Schema

Added `telemetry_events` to both DB backends:

- `backend/db/sqlite_migrations.py` (`SCHEMA_VERSION = 9`)
- `backend/db/postgres_migrations.py` (`SCHEMA_VERSION = 7`)

Key dimensions include:

- project/session/root session IDs
- feature/task/commit/PR context
- event type, tool, model, agent, skill, status
- duration/tokens/cost metrics
- full payload JSON and deterministic source key

### Sync ingestion

`backend/db/sync_engine.py` now:

1. Builds normalized telemetry events for each synced session.
2. Replaces session-scoped event rows atomically on each session sync.
3. Performs one-time project backfill when telemetry table is empty and sessions already exist.

### Backfill job

Manual job added:

- `backend/scripts/telemetry_backfill.py`

Examples:

```bash
python backend/scripts/telemetry_backfill.py
python backend/scripts/telemetry_backfill.py --project default-skillmeat
python backend/scripts/telemetry_backfill.py --all-projects
```

### Tests

- `backend/tests/test_sync_engine_telemetry.py`

## B2: OTel Instrumentation

### Runtime module

New module:

- `backend/observability/otel.py`

Capabilities:

1. Optional OTel bootstrap with OTLP HTTP exporters.
2. FastAPI request instrumentation.
3. Counters/histograms for ingestion, parser failures, tool reliability, token/cost metrics.
4. Prometheus fallback metrics server (if configured).

### Startup wiring

- `backend/main.py` now initializes and shuts down observability providers during app lifespan.

### Config

Added env vars in `backend/config.py`:

- `CCDASH_OTEL_ENABLED` (default `false`)
- `CCDASH_OTEL_ENDPOINT` (default `http://localhost:4318`)
- `CCDASH_OTEL_SERVICE_NAME` (default `ccdash-backend`)
- `CCDASH_PROM_PORT` (default `9464`)

### Dependencies

Added to `backend/requirements.txt`:

- `opentelemetry-api`
- `opentelemetry-sdk`
- `opentelemetry-exporter-otlp-proto-http`
- `opentelemetry-instrumentation-fastapi`
- `prometheus-client`

### Prom export enrichment

`backend/routers/analytics.py` now exports additional labeled metrics:

1. Tool call counts and average duration by tool/status.
2. Token and cost totals by model/direction.
3. Link confidence and unresolved-link counts.
4. Session thread fanout summaries.

## B3: Self-Hosted Observability Stack

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

### Quick start

```bash
cd deploy/observability
docker compose up -d
```

Default local ports:

1. Grafana: `http://localhost:3001`
2. Prometheus: `http://localhost:9090`
3. OTel HTTP receiver: `http://localhost:4318`

## Validation

Executed during implementation:

1. `python -m pytest backend/tests/test_sync_engine_telemetry.py backend/tests/test_sync_engine_linking.py backend/tests/test_analytics_router.py -q`
2. `python -m compileall backend`
