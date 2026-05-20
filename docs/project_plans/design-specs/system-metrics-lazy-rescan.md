---
schema_version: 2
doc_type: design_spec
title: "System Metrics Lazy On-Demand Rescan - Design Spec"
status: draft
maturity: idea
feature_slug: system-wide-metrics
prd_ref: docs/project_plans/PRDs/features/system-wide-metrics-v1.md
plan_ref: docs/project_plans/implementation_plans/features/system-wide-metrics-v1.md
created: 2026-05-20
updated: 2026-05-20
category: features
tags: [metrics, freshness, rescan, deferred]
related_documents:
  - .claude/worknotes/system-wide-live-metrics-spike/spike.md
  - docs/project_plans/feature_contracts/features/watcher-rebind-on-active-project-switch-v1.md
---

# System Metrics Lazy On-Demand Rescan

## Problem Statement

`SystemMetricsQueryService` reports a per-project `is_stale` flag computed from the most recent `sessions.updated_at` on that project. When `is_stale=true`, the UI shows a warning icon but the count is whatever the DB currently has — there is no opportunistic rescan. PRD OQ-1 asks whether the service should trigger a lazy per-project filesystem rescan when reading a stale project, so that opening the home dashboard naturally heals stale counts without operator intervention.

Promotion trigger (from plan §Deferred Items DEF-002):
- `watcher-rebind-on-active-project-switch-v1` ships AND
- Operators report stale counts exceeding 2h on non-active projects in real usage.

## Known Constraints

- The dashboard chip polls every 30s. Naïve rescan-on-stale would trigger N filesystem scans per home-dashboard load when many projects are stale — a thundering-herd risk.
- Filesystem scans are not free; the existing parser pipeline assumes the watcher pushes changes, not that arbitrary readers pull.
- `@memoized_query` TTL (30s in v1) absorbs duplicate polls — the rescan path must respect that cache or it will run on every cache miss.
- Rescan must be bounded — a single project's `sessions_dir` can hold thousands of JSONL files.

## Open Questions

- Where does the rescan run — inside `get_system_active_count` (blocking the response) or as a fire-and-forget worker job?
- Concurrency: how do we prevent stampedes when 10 stale projects all expire at the same instant?
- Coalescing: if two reads arrive within 1s for the same stale project, both should observe the same rescan, not trigger two.
- Should `is_stale=true` always trigger a rescan, or only after a threshold (e.g., stale for >2h)?
- Cache invalidation: when a rescan completes, should it invalidate the memoized aggregate, force the next reader to recompute, or both?

## Notes

A simpler interim mitigation is to expose a manual `POST /api/agent/system/active-count/rescan` endpoint that the UI can call from a stale-tooltip action. That keeps the read path predictable while giving operators an escape hatch before this spec is fully promoted.
