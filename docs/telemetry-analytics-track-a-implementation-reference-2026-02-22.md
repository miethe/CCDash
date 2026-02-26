---
title: "Telemetry + Analytics Track A Implementation Reference"
description: "Implemented backend/frontend changes for analytics correctness, query expansion, and UI wiring"
audience: [developers, maintainers]
tags: [analytics, telemetry, api, migrations, dashboard, alerts]
created: 2026-02-22
updated: 2026-02-22
category: "developer-reference"
status: "implemented"
---

# Telemetry + Analytics Track A Implementation Reference

This document describes the implemented changes from Track A in:

- `docs/project_plans/implementation_plans/telemetry-analytics-modernization-v1.md`

## Summary

Implemented Track A outcomes:

1. Correctness and persistence parity for task completion and session telemetry.
2. New analytics query endpoints and alert CRUD APIs.
3. UI wiring to backend-derived analytics (no hardcoded dashboard KPI values, no simulated token timeline, persisted alert settings).

## Backend Changes

### 1. Task completion semantics

Task completion metrics now treat these statuses as terminal-complete:

- `done`
- `deferred`
- `completed` (legacy compatibility)

Updated files:

- `backend/db/repositories/tasks.py`
- `backend/db/repositories/postgres/tasks.py`

Impact:

- `task_velocity` and `task_completion_pct` no longer return incorrect zero values when tasks are tracked as `done`/`deferred`.

### 2. Session telemetry persistence

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

### 3. Tool duration capture (`session_tool_usage.total_ms`)

Implemented real duration capture from tool-use to tool-result timestamps.

- Parser now computes per-tool elapsed duration and stores `ToolUsage.totalMs`.
- Repositories now persist `total_ms` during `upsert_tool_usage`.

Updated files:

- `backend/parsers/sessions.py`
- `backend/models.py`
- `backend/db/repositories/sessions.py`
- `backend/db/repositories/postgres/sessions.py`

### 4. Token timeline data source

Message-level token usage metadata is now persisted in session logs when available:

- `inputTokens`
- `outputTokens`
- `totalTokens`

Used by `/api/analytics/series?metric=session_tokens&session_id=...` to build real cumulative token timeline points.

Updated files:

- `backend/parsers/sessions.py`
- `backend/routers/analytics.py`

### 5. Analytics metric metadata and entity links

Analytics capture now writes:

- non-empty `analytics_entries.metadata_json`
- `analytics_entity_links` entries (currently linked at minimum to project scope)

Updated file:

- `backend/db/sync_engine.py`

## Analytics API Surface

Implemented in:

- `backend/routers/analytics.py`

### New endpoints

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

### Compatibility endpoints retained

1. `GET /api/analytics/metrics`
2. `GET /api/analytics/trends`
3. `GET /api/analytics/export/prometheus`

## Frontend Wiring

### Dashboard

`components/Dashboard.tsx` now loads analytics from backend:

- KPIs from `GET /api/analytics/overview`
- Cost and velocity series from `GET /api/analytics/series`
- Model usage chart from overview payload

Removed dependency on hardcoded KPI/model values for displayed dashboard metrics.

### Session Inspector

`components/SessionInspector.tsx` token timeline now uses:

- `GET /api/analytics/series?metric=session_tokens&period=point&session_id=...`

Fallback behavior:

- If series fetch fails, it reconstructs from persisted log token metadata (`totalTokens`) rather than synthetic random values.

### Settings Alerts

`components/Settings.tsx` alerts tab now performs persisted CRUD:

- create alert (`POST`)
- toggle active/inactive (`PATCH`)
- delete alert (`DELETE`)

## Shared Types / Services

Updated files:

- `services/analytics.ts`
- `types.ts`

New/expanded client support includes:

- overview/series/breakdown/correlation API methods
- alert CRUD methods
- analytics type extensions
- tool usage optional `totalMs`
- alert metric type widened for backend metric IDs

## Tests Added/Updated

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

## Operational Notes

1. Run migrations on startup as normal; schema upgrades are additive.
2. To refresh existing cached analytics with new semantics/metadata, run a sync and analytics rebuild.
3. If historical sessions predate these parser changes, token timeline resolution depends on previously captured usage metadata.

## File Index

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
