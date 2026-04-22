# Operations Panel Guide

Operator workflows, developer integration notes, and sync/link-audit observability for the CCDash Operations panel.

> Consolidated from the former top-level user and developer docs. `docs/project_plans/` content was intentionally left untouched.

## User Guide

Last updated: 2026-03-15

The Operations panel is the control center for long sync/rebuild runs and link-audit checks.

Route:

- `/ops`

### What you can do

- Start a **Force Full Sync** (background).
- Start an **Incremental Sync** (background).
- Start a **Link Rebuild** only (background).
- Run **Targeted Path Sync** for selected changed files.
- Monitor live operation progress with phase/status updates.
- Inspect operation details (duration, counters, metadata, errors).
- Inspect live-update broker health (subscriber, buffer, replay-gap, and dropped-event counts).
- Run a **Link Audit** and review suspect mapping rows.
- Review app/project metadata (health, watcher status, paths, project list).

### Telemetry Exporter

The panel also exposes the telemetry exporter health surface:

- View exporter enablement, configuration state, masked SAM endpoint, queue counts, last push time, recent throughput, and the latest error summary.
- Use **Push Now** to trigger a manual export run when the exporter is configured and enabled.
- Watch pending, failed, and abandoned queue depth to confirm the worker is keeping up.

The exporter status and control flow are documented in:

- [`docs/telemetry-exporter-guide.md`](telemetry-exporter-guide.md)
- [`docs/telemetry-exporter-troubleshooting.md`](telemetry-exporter-troubleshooting.md)

### Reading operation status

Statuses:

- `running`: operation is active.
- `completed`: operation finished successfully.
- `failed`: operation ended with an error.

Typical full sync phases:

- `sessions` -> `documents` -> `tasks` -> `features` -> `links` -> `analytics` -> `completed`

Typical link rebuild sub-phases:

- `links:init`
- `links:feature-prep`
- `links:session-evidence`
- `links:documents`
- `links:catalog`
- `links:completed`

### Link audit in the panel

Use filters:

- `Feature ID` (optional): limits audit to one feature.
- `Limit`: max suspect rows.
- `Primary Floor`: minimum confidence to treat a link as “primary-like”.
- `Fanout Floor`: minimum feature fanout to flag “high fanout”.

The audit table shows suspect links with:

- `feature_id`
- `session_id`
- `confidence`
- `fanout_count`
- `reason`

### Recommended workflow

1. Run **Force Full Sync** after major parser/mapping changes.
2. Watch operation progress until `completed`.
3. Run **Link Audit** and export/review suspects.
4. Tune mapping rules.
5. Run **Link Rebuild** only for fast iteration.
6. For specific docs/progress files, run **Targeted Path Sync** instead of full sync.

### Notes

- Enable `VITE_CCDASH_LIVE_OPS_ENABLED=true` to use stream-first operation invalidation in the panel.
- When live ops rollout is disabled or the stream backs off, the panel returns to its existing polling cadence.
- Operation IDs are stable handles you can share in debugging.

## Developer Reference

Last updated: 2026-04-06

This reference documents the Ops page implementation and backend endpoints it uses.

### Frontend implementation

Primary page:

- `components/OpsPanel.tsx`

Route wiring:

- `App.tsx`

Sidebar nav wiring:

- `components/Layout.tsx`

Types:

- `types.ts`

### Backend endpoints consumed by Ops panel

- `GET /api/health`
- `GET /api/cache/status`
- `GET /api/cache/operations`
- `GET /api/cache/operations/{operation_id}`
- `POST /api/cache/sync`
- `POST /api/cache/rebuild-links`
- `POST /api/cache/sync-paths`
- `GET /api/links/audit`
- `GET /api/telemetry/export/status`
- `POST /api/telemetry/export/push-now`

Compatibility aliases also available:

- `POST /api/cache/rescan`
- `GET /api/cache/links/audit`

### Sync operation model

Operations are created/tracked in:

- `backend/db/sync_engine.py`

Key methods:

- `start_operation(...)`
- `get_observability_snapshot()`
- `sync_project(..., operation_id=...)`
- `rebuild_links(..., operation_id=...)`
- `sync_changed_files(..., operation_id=...)`

Startup orchestration:

- `backend/main.py` now runs a staggered startup pipeline:
  - light `sync_project(..., rebuild_links=False, capture_analytics=False)` first
  - deferred `rebuild_links(...)` later (config-driven)

Stored operation fields include:

- `id`, `kind`, `projectId`, `trigger`
- `status`, `phase`, `message`
- `progress`, `counters`, `stats`, `metadata`
- `startedAt`, `updatedAt`, `finishedAt`, `durationMs`
- `error`

### Link audit analyzer

Shared analyzer module:

- `backend/link_audit.py`

CLI wrapper:

- `backend/scripts/link_audit.py`

Router integration:

- `backend/routers/cache.py`

### API payload notes

`GET /api/health` now includes:

- `storageMode`
- `storageProfile`
- `storageBackend`
- `storageComposition`
- `recommendedStorageProfile`
- `supportedStorageProfiles`
- `watchEnabled`
- `syncEnabled`
- `syncProvisioned`
- `jobsEnabled`
- `telemetryExports`
- `filesystemSourceOfTruth`
- `storageFilesystemRole`
- `sharedPostgresEnabled`
- `storageIsolationMode`
- `supportedStorageIsolationModes`
- `storageCanonicalStore`
- `auditStore`
- `sessionIntelligenceProfile`
- `sessionIntelligenceAnalyticsLevel`
- `sessionIntelligenceBackfillStrategy`
- `sessionIntelligenceMemoryDraftFlow`
- `sessionIntelligenceIsolationBoundary`
- `storageSchema`
- `canonicalSessionStore`
- `migrationGovernanceStatus`
- `requiredStorageGuarantees`
- `storageProfileValidationMatrix`
- `supportedStorageCompositions`

The Ops panel renders these fields in a compact runtime/storage capability section so operators can confirm the deployment posture at a glance. That section is meant to answer five questions quickly: which storage profile and composition are active, whether the runtime should be running background work, whether sync is actually provisioned, whether the current Postgres posture matches the intended isolation model, and which session-intelligence capabilities are supposed to differ across local SQLite, dedicated enterprise Postgres, and shared-instance enterprise Postgres.

`storageProfileValidationMatrix` is the comparison payload for that last question. It exposes one row per supported storage posture with the canonical store, filesystem role, audit-write status, session-embedding write status, supported isolation modes, and session-intelligence rollout fields (`sessionIntelligenceProfile`, `sessionIntelligenceAnalyticsLevel`, `sessionIntelligenceBackfillStrategy`, `sessionIntelligenceMemoryDraftFlow`, `sessionIntelligenceIsolationBoundary`).

`GET /api/cache/status` now includes:

- `projectId`, `projectName`
- `activePaths.sessionsDir`
- `activePaths.docsDir`
- `activePaths.progressDir`
- `operations` snapshot object
- `liveUpdates` broker snapshot (`active_subscribers`, `buffered_topics`, `replay_gaps`, `dropped_events`, etc.)

### Telemetry exporter surface

The Ops panel also reflects the worker-side telemetry exporter state.

Implementation files:

- `backend/services/integrations/telemetry_exporter.py`
- `backend/adapters/jobs/telemetry_exporter.py`
- `backend/runtime/container.py`
- `backend/observability/otel.py`

The panel surfaces queue depth, last push time, last error, and enabled/disabled state. For operator procedures and troubleshooting, link users to:

- [`docs/telemetry-exporter-guide.md`](telemetry-exporter-guide.md)
- [`docs/telemetry-exporter-troubleshooting.md`](telemetry-exporter-troubleshooting.md)
- [`docs/storage-profiles-guide.md`](storage-profiles-guide.md)

### Live invalidation path

- Frontend rollout gate: `VITE_CCDASH_LIVE_OPS_ENABLED`
- Topic: `project.{project_id}.ops`
- Frontend subscription helper: `services/live/useLiveInvalidation.ts`
- Backend publishers:
  - `backend/db/sync_engine.py`
  - `backend/application/live_updates/domain_events.py`

The panel now uses stream-first invalidation and only falls back to interval polling while the connection is disabled, closed, or in backoff.

### Tests

Endpoint and behavior tests:

- `backend/tests/test_cache_router.py`
- `backend/tests/test_link_audit.py`

Core linking tests still relevant:

- `backend/tests/test_sync_engine_linking.py`

### Validation commands

Backend tests:

```bash
PYTHONPATH=. pytest -q backend/tests/test_cache_router.py backend/tests/test_link_audit.py backend/tests/test_sync_engine_linking.py
```

Frontend build:

```bash
npm run build
```

## Sync Observability and Link Audit

Last updated: 2026-02-25

This document describes the new sync/rebuild observability and link-audit APIs.

### Startup behavior

Startup now uses a staggered sync pipeline by default:

1. Light startup sync runs first (`trigger=startup`):
   - sessions/documents/tasks/features are synced
   - link rebuild and analytics capture are skipped
2. Deferred rebuild runs later (`trigger=startup_deferred`):
   - entity links are rebuilt
   - analytics capture is optional

Tuning env vars:

- `CCDASH_STARTUP_SYNC_LIGHT_MODE` (default `true`)
- `CCDASH_STARTUP_SYNC_DELAY_SECONDS` (default `2`)
- `CCDASH_STARTUP_DEFERRED_REBUILD_LINKS` (default `true`)
- `CCDASH_STARTUP_DEFERRED_REBUILD_DELAY_SECONDS` (default `45`)
- `CCDASH_STARTUP_DEFERRED_CAPTURE_ANALYTICS` (default `false`)

### Why this exists

- Long sync/rebuild runs now expose operation IDs and live phase progress.
- You can trigger full syncs, targeted path syncs, and link-only rebuilds from API.
- You can run mapping audits from API (`/api/links/audit`) without CLI access.

### Operation model

Every sync/rebuild operation tracks:

- `id`: operation ID (`OP-...`)
- `kind`: `full_sync`, `rebuild_links`, `sync_changed_files`
- `status`: `running`, `completed`, `failed`
- `phase`: current phase (`sessions`, `documents`, `links:session-evidence`, etc.)
- `message`: human-readable progress text
- `progress`: phase counters (processed/total)
- `counters`: entity-level counters (links created, docs synced, etc.)
- `stats`: final result payload
- `startedAt`, `updatedAt`, `finishedAt`, `durationMs`

### Endpoints

#### Status and operations

- `GET /api/cache/status`
- `GET /api/cache/operations?limit=20`
- `GET /api/cache/operations/{operation_id}`

#### Trigger full sync

- `POST /api/cache/sync`
  - body: `{ "force": true, "background": true, "trigger": "api" }`
- `POST /api/cache/rescan` (alias for force background sync)

#### Trigger link rebuild only

- `POST /api/cache/rebuild-links`
  - body: `{ "background": true, "captureAnalytics": false, "trigger": "api" }`

#### Targeted changed-path sync

- `POST /api/cache/sync-paths`
  - body:
    - `paths`: list of `{ "path": "...", "changeType": "modified|added|deleted" }`
    - `background`: boolean
    - `trigger`: string
  - Path handling:
    - relative paths are resolved from active project root
    - absolute paths must remain under project/docs/progress/sessions roots

#### Link audit

- `GET /api/links/audit`
- `GET /api/cache/links/audit` (alias)
  - query params:
    - `feature_id` (optional)
    - `primary_floor` (default `0.55`)
    - `fanout_floor` (default `10`)
    - `limit` (default `50`)

### Typical workflows

1. Start a full sync in background (`POST /api/cache/sync`).
2. Poll `GET /api/cache/operations/{operation_id}` until `status=completed|failed`.
3. Run `GET /api/links/audit` to review suspect mappings.
4. If only links changed, use `POST /api/cache/rebuild-links` instead of full sync.
5. For specific files, run `POST /api/cache/sync-paths`.

### Sync mode details

`SyncEngine.sync_project(...)` now accepts:

- `rebuild_links` (default `true`)
- `capture_analytics` (default `true`)

Startup light mode sets both to `false` for initial responsiveness, then runs deferred `rebuild_links(...)`.

### Date Metadata Notes

- Full sync and changed-file sync now compute document git dates in batches (no per-file git process fanout).
- Commit history is cached by repo `HEAD` and sync scope.
- Dirty/untracked markdown files are checked each sync so local edits can update `updatedAt` confidence.
- Feature date derivation receives this same git-backed document metadata.

### Backfill Workflow (All Existing Docs)

To refresh normalized date fields for all previously indexed docs/features:

1. Trigger `POST /api/cache/sync` with `{ "force": true, "background": true }`.
2. Poll operation status until `completed`.
3. Re-open document/feature views (or refetch API data) to confirm updated dates/timelines.

### Code references

- `backend/db/sync_engine.py`
- `backend/routers/cache.py`
- `backend/link_audit.py`
- `backend/scripts/link_audit.py`
