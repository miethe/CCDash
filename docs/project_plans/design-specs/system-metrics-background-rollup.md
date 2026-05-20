---
schema_version: 2
doc_type: design_spec
title: "System Metrics Background Rollup - Design Spec"
status: draft
maturity: shaping
feature_slug: system-wide-metrics
prd_ref: docs/project_plans/PRDs/features/system-wide-metrics-v1.md
plan_ref: docs/project_plans/implementation_plans/features/system-wide-metrics-v1.md
created: 2026-05-20
updated: 2026-05-20
category: features
tags: [metrics, rollup, performance, deferred]
related_documents:
  - .claude/worknotes/system-wide-live-metrics-spike/spike.md
  - docs/project_plans/implementation_plans/features/system-wide-metrics-v1.md
---

# System Metrics Background Rollup

## Problem Statement

`SystemMetricsQueryService.get_system_active_count()` fans out per project via `asyncio.gather` (semaphore-bounded, default concurrency 10) and aggregates in-process on every uncached call. At v1's project counts (~36 active workspaces), local p95 is ~73ms — well inside the 200ms budget. As the project count grows or as new system-wide metrics layer on top of the same fan-out path (sessions/day, token totals, error rates), the linear cost will eventually exceed the budget. A pre-computed rollup table backing the service would decouple read latency from project count.

Promotion trigger (from plan §Deferred Items DEF-001):
- Project count exceeds ~100 AND p95 > 200ms sustained, OR
- A desktop widget API requiring sub-10ms response is implemented.

## Known Constraints

- v1 is intentionally in-process; the rollup must remain optional and behind a config switch.
- `SystemMetricsQueryService` is the single transport-neutral consumer; the rollup must keep the existing `SystemActiveCountDTO` shape (no contract breakage).
- The staleness contract (`is_stale`, `last_synced_at`) is load-bearing: a rollup must update per-project rows on every sync, not on a fixed cadence, or the staleness signal will lie.
- Worker process already exists (`backend/worker.py`); the rollup is a natural worker responsibility.

## Open Questions

- Storage: a new `system_metrics_rollup` table, or extend `sessions` with denormalised aggregates? The former keeps concerns separated; the latter avoids a join.
- Trigger model: write-through on every `sessions.upsert`, or scheduled tick every N seconds? Write-through guarantees freshness but costs per-write CPU.
- Backfill: how is the rollup primed at worker startup without blocking the API runtime?
- Failure modes: if the rollup goes stale, does the service fall back to live fan-out, or does it serve stale-with-warning?

## Notes

When this spec is promoted, the new service path should remain hidden behind a config flag (`CCDASH_SYSTEM_METRICS_ROLLUP_ENABLED`, default `false`) so the in-process fan-out path stays available as a fallback during the rollout window.
