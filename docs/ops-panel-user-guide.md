# Operations Panel User Guide

Last updated: 2026-02-19

The Operations panel is the control center for long sync/rebuild runs and link-audit checks.

Route:

- `/ops`

## What you can do

- Start a **Force Full Sync** (background).
- Start an **Incremental Sync** (background).
- Start a **Link Rebuild** only (background).
- Run **Targeted Path Sync** for selected changed files.
- Monitor live operation progress with phase/status updates.
- Inspect operation details (duration, counters, metadata, errors).
- Run a **Link Audit** and review suspect mapping rows.
- Review app/project metadata (health, watcher status, paths, project list).

## Reading operation status

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

## Link audit in the panel

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

## Recommended workflow

1. Run **Force Full Sync** after major parser/mapping changes.
2. Watch operation progress until `completed`.
3. Run **Link Audit** and export/review suspects.
4. Tune mapping rules.
5. Run **Link Rebuild** only for fast iteration.
6. For specific docs/progress files, run **Targeted Path Sync** instead of full sync.

## Notes

- Polling is faster while operations are active and slower when idle.
- Operation IDs are stable handles you can share in debugging.
