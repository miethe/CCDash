# Codebase Explorer Developer Reference

Last updated: 2026-02-25

This document describes the Codebase Explorer implementation, APIs, data rules, and performance behavior.

## Scope

Implemented in:

- `/Users/miethe/dev/homelab/development/CCDash/backend/services/codebase_explorer.py`
- `/Users/miethe/dev/homelab/development/CCDash/backend/routers/codebase.py`
- `/Users/miethe/dev/homelab/development/CCDash/components/CodebaseExplorer.tsx`
- `/Users/miethe/dev/homelab/development/CCDash/components/SessionInspector.tsx`

Route wiring:

- `/Users/miethe/dev/homelab/development/CCDash/App.tsx` (`/codebase`)
- `/Users/miethe/dev/homelab/development/CCDash/components/Layout.tsx` (sidebar nav)

## Session Inspector changes

Session detail is split into separate tabs:

1. `Activity`: chronological merged line items from logs, file actions, and artifacts.
2. `Files`: one row per file with multi-action chips (`Read/Create/Update/Delete`) and aggregate counts.

Transcript deep-links that previously targeted files now target `Activity` with `sourceLogId` highlighting.

## API surface

### `GET /api/codebase/tree`

Query:

- `prefix`
- `depth`
- `include_untouched`
- `search`

Returns folder/file tree nodes with touch metadata and aggregates.

### `GET /api/codebase/files`

Query:

- `prefix`
- `search`
- `include_untouched`
- `action`
- `feature_id`
- `sort_by`
- `sort_order`
- `offset`
- `limit`

Returns paginated file summaries.

### `GET /api/codebase/files/{file_path:path}`

Query:

- `activity_limit`

Returns file detail including:

- action rollups
- related sessions
- feature involvement
- linked documents
- recent file activity entries

## Data rules

Codebase universe:

- all files under active project root (`activeProject.path`)
- excludes from root `.gitignore`
- built-in excludes: `.git/`, `node_modules/`, `dist/`, `coverage/`, `.venv/`

Feature involvement scoring:

- action weights:
  - `create=1.00`
  - `update=0.80`
  - `delete=0.70`
  - `read=0.40`
- base score per session-file: `entity_link_confidence * max_action_weight`
- direct path signals in `entity_links.metadata_json.signals` can raise score
- involvement levels:
  - `primary >= 0.75`
  - `supporting 0.50-0.74`
  - `peripheral < 0.50`

## Path safety

- All requested file paths are normalized and checked against project root.
- Traversal/out-of-root paths are rejected with `400`.

## Caching and performance

In-memory cache is 30s TTL per project and mode:

- `touched` snapshot (default for most requests): no full filesystem scan.
- `full` snapshot (used when `include_untouched=true`): includes untouched files via filesystem walk.

This reduces latency for common explorer interactions and avoids unnecessary full scans.

Scanner hardening:

- Missing/inaccessible entries (including dangling symlinks) are skipped instead of crashing.

## Tests

- `/Users/miethe/dev/homelab/development/CCDash/backend/tests/test_codebase_router.py`

Covers:

- tree listing
- untouched toggle
- `.gitignore` + built-in excludes
- traversal rejection
- detail aggregation correctness
- involvement thresholds
- dangling symlink scan stability

