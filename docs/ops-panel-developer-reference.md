# Operations Panel Developer Reference

Last updated: 2026-02-25

This reference documents the Ops page implementation and backend endpoints it uses.

## Frontend implementation

Primary page:

- `/Users/miethe/dev/homelab/development/CCDash/components/OpsPanel.tsx`

Route wiring:

- `/Users/miethe/dev/homelab/development/CCDash/App.tsx`

Sidebar nav wiring:

- `/Users/miethe/dev/homelab/development/CCDash/components/Layout.tsx`

Types:

- `/Users/miethe/dev/homelab/development/CCDash/types.ts`

## Backend endpoints consumed by Ops panel

- `GET /api/health`
- `GET /api/cache/status`
- `GET /api/cache/operations`
- `GET /api/cache/operations/{operation_id}`
- `POST /api/cache/sync`
- `POST /api/cache/rebuild-links`
- `POST /api/cache/sync-paths`
- `GET /api/links/audit`

Compatibility aliases also available:

- `POST /api/cache/rescan`
- `GET /api/cache/links/audit`

## Sync operation model

Operations are created/tracked in:

- `/Users/miethe/dev/homelab/development/CCDash/backend/db/sync_engine.py`

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

## Link audit analyzer

Shared analyzer module:

- `/Users/miethe/dev/homelab/development/CCDash/backend/link_audit.py`

CLI wrapper:

- `/Users/miethe/dev/homelab/development/CCDash/backend/scripts/link_audit.py`

Router integration:

- `/Users/miethe/dev/homelab/development/CCDash/backend/routers/cache.py`

## API payload notes

`GET /api/cache/status` now includes:

- `projectId`, `projectName`
- `activePaths.sessionsDir`
- `activePaths.docsDir`
- `activePaths.progressDir`
- `operations` snapshot object

## Tests

Endpoint and behavior tests:

- `/Users/miethe/dev/homelab/development/CCDash/backend/tests/test_cache_router.py`
- `/Users/miethe/dev/homelab/development/CCDash/backend/tests/test_link_audit.py`

Core linking tests still relevant:

- `/Users/miethe/dev/homelab/development/CCDash/backend/tests/test_sync_engine_linking.py`

## Validation commands

Backend tests:

```bash
PYTHONPATH=. pytest -q backend/tests/test_cache_router.py backend/tests/test_link_audit.py backend/tests/test_sync_engine_linking.py
```

Frontend build:

```bash
npm run build
```
