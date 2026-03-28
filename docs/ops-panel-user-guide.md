# Operations Panel User Guide

Last updated: 2026-03-15

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
- Inspect live-update broker health (subscriber, buffer, replay-gap, and dropped-event counts).
- Run a **Link Audit** and review suspect mapping rows.
- Review app/project metadata (health, watcher status, paths, project list).

## Telemetry Exporter

The panel also exposes the telemetry exporter health surface:

- View exporter enablement, configuration state, masked SAM endpoint, queue counts, last push time, recent throughput, and the latest error summary.
- Use **Push Now** to trigger a manual export run when the exporter is configured and enabled.
- Watch pending, failed, and abandoned queue depth to confirm the worker is keeping up.

The exporter status and control flow are documented in:

- [`docs/guides/telemetry-exporter-guide.md`](./guides/telemetry-exporter-guide.md)
- [`docs/guides/telemetry-exporter-troubleshooting.md`](./guides/telemetry-exporter-troubleshooting.md)

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

- Enable `VITE_CCDASH_LIVE_OPS_ENABLED=true` to use stream-first operation invalidation in the panel.
- When live ops rollout is disabled or the stream backs off, the panel returns to its existing polling cadence.
- Operation IDs are stable handles you can share in debugging.
