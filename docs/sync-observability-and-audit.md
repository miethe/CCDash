# Sync Observability and Link Audit

Last updated: 2026-02-25

This document describes the new sync/rebuild observability and link-audit APIs.

## Startup behavior

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

## Why this exists

- Long sync/rebuild runs now expose operation IDs and live phase progress.
- You can trigger full syncs, targeted path syncs, and link-only rebuilds from API.
- You can run mapping audits from API (`/api/links/audit`) without CLI access.

## Operation model

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

## Endpoints

### Status and operations

- `GET /api/cache/status`
- `GET /api/cache/operations?limit=20`
- `GET /api/cache/operations/{operation_id}`

### Trigger full sync

- `POST /api/cache/sync`
  - body: `{ "force": true, "background": true, "trigger": "api" }`
- `POST /api/cache/rescan` (alias for force background sync)

### Trigger link rebuild only

- `POST /api/cache/rebuild-links`
  - body: `{ "background": true, "captureAnalytics": false, "trigger": "api" }`

### Targeted changed-path sync

- `POST /api/cache/sync-paths`
  - body:
    - `paths`: list of `{ "path": "...", "changeType": "modified|added|deleted" }`
    - `background`: boolean
    - `trigger`: string
  - Path handling:
    - relative paths are resolved from active project root
    - absolute paths must remain under project/docs/progress/sessions roots

### Link audit

- `GET /api/links/audit`
- `GET /api/cache/links/audit` (alias)
  - query params:
    - `feature_id` (optional)
    - `primary_floor` (default `0.55`)
    - `fanout_floor` (default `10`)
    - `limit` (default `50`)

## Typical workflows

1. Start a full sync in background (`POST /api/cache/sync`).
2. Poll `GET /api/cache/operations/{operation_id}` until `status=completed|failed`.
3. Run `GET /api/links/audit` to review suspect mappings.
4. If only links changed, use `POST /api/cache/rebuild-links` instead of full sync.
5. For specific files, run `POST /api/cache/sync-paths`.

## Sync mode details

`SyncEngine.sync_project(...)` now accepts:

- `rebuild_links` (default `true`)
- `capture_analytics` (default `true`)

Startup light mode sets both to `false` for initial responsiveness, then runs deferred `rebuild_links(...)`.

## Date Metadata Notes

- Full sync and changed-file sync now compute document git dates in batches (no per-file git process fanout).
- Commit history is cached by repo `HEAD` and sync scope.
- Dirty/untracked markdown files are checked each sync so local edits can update `updatedAt` confidence.
- Feature date derivation receives this same git-backed document metadata.

## Backfill Workflow (All Existing Docs)

To refresh normalized date fields for all previously indexed docs/features:

1. Trigger `POST /api/cache/sync` with `{ "force": true, "background": true }`.
2. Poll operation status until `completed`.
3. Re-open document/feature views (or refetch API data) to confirm updated dates/timelines.

## Code references

- `/Users/miethe/dev/homelab/development/CCDash/backend/db/sync_engine.py`
- `/Users/miethe/dev/homelab/development/CCDash/backend/routers/cache.py`
- `/Users/miethe/dev/homelab/development/CCDash/backend/link_audit.py`
- `/Users/miethe/dev/homelab/development/CCDash/backend/scripts/link_audit.py`
