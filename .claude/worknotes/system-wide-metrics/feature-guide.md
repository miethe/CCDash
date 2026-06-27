---
doc_type: feature_guide
feature_slug: system-wide-metrics
prd_ref: docs/project_plans/PRDs/features/system-wide-metrics-v1.md
plan_ref: docs/project_plans/implementation_plans/features/system-wide-metrics-v1.md
spike_ref: .claude/worknotes/system-wide-live-metrics-spike/spike.md
adr_refs: []
created: 2026-05-20
---

# System-Wide Metrics — Feature Guide

## What Was Built

- **`SystemMetricsQueryService`** (`backend/application/services/agent_queries/system_metrics.py`) — transport-neutral aggregation across all known projects with per-project staleness signals, bounded fan-out, partial-failure handling, and a memoized cache.
- **Three transports** on top of the service:
  - REST: `GET /api/agent/system/active-count` (with `Cache-Control: max-age=30`).
  - MCP: tool `ccdash_system_active_count`.
  - CLI: `ccdash system active-count` (`--json` flag for machine output).
- **Dashboard chip** (`components/SystemMetricsChip.tsx`) integrated into `components/Dashboard.tsx` between the Feature Portfolio surface and the KPI stat-card grid. The chip polls every 30s, pauses on hidden tab, and exposes an expand/collapse per-project breakdown with stale indicators.

## Architecture Overview

```
project_manager.list_projects()
        │
        ▼
SystemMetricsQueryService.get_system_active_count()
   • asyncio.Semaphore(CCDASH_SYSTEM_METRICS_CONCURRENCY) fan-out
   • per project:
       SessionsRepository.count_active(project_id, window_seconds=…)
       SELECT MAX(updated_at) FROM sessions WHERE project_id = ?
       → is_stale = (now - max_updated_at) > CCDASH_SYSTEM_METRICS_STALE_HORIZON_SECONDS
   • exceptions → {count:None, error:str(exc)}; aggregate continues
   • status = "partial" if any errors else "ok"
   • wrapped with @memoized_query (TTL = CCDASH_SYSTEM_METRICS_CACHE_TTL_SECONDS)
        │
        ▼
  ┌─────────────┬──────────────┬─────────────────────┐
  │  REST       │   MCP        │  CLI                │
  │ agent.py    │ tools/system │ commands/system.py  │
  └─────────────┴──────────────┴─────────────────────┘
        │
        ▼
SystemMetricsChip.tsx (30s poll, expand/collapse, resilience states)
```

**OQ-5 resolution (Postgres staleness path)** — kept `SessionsRepository.count_active()` unchanged; the service runs a separate `SELECT MAX(updated_at) ...` query per project (dual-path for SQLite + Postgres, mirroring `cache.py:_query_max_updated_at`). This avoids contract drift on the `live-agents-count-v1` Tier 1 primitive at the cost of one extra small query per project — well inside the latency budget.

## How to Test

REST:

```bash
curl -s http://localhost:8000/api/agent/system/active-count | jq .
```

CLI:

```bash
backend/.venv/bin/ccdash system active-count
backend/.venv/bin/ccdash system active-count --json
```

MCP — invoke via an MCP client connected to `backend/mcp/server.py` and call tool `ccdash_system_active_count`.

Browser smoke (required before merge to main per CLAUDE.md runtime-smoke gate):

1. `npm run dev`
2. Open the home dashboard.
3. Confirm "Live now" chip appears between the Feature Portfolio surface and the KPI cards.
4. Click the chip; per-project breakdown expands without re-fetching.
5. For any project last touched > 1h ago, the warning icon is shown next to its row.

## Test Coverage Summary

- Backend unit (`backend/tests/test_system_metrics.py`):
  - `test_stale_horizon_boundary` — fresh / boundary / stale → correct `is_stale` values.
  - `test_partial_aggregate_resilience` — one project raises → DTO continues, status=partial.
  - `test_cache_hit` — second call within TTL reuses memoized result.
  - `test_all_errors_returns_partial_status` — every project errors → status=partial, total=0.
- Backend integration:
  - `test_system_metrics_transport_parity` — REST JSON matches service DTO.
  - `test_dashboard_contract_parity` — every FE-consumed field present in REST JSON (R-P3 seam gate).
- Backend performance (env-gated by `CCDASH_RUN_PERF_TESTS=1`):
  - `test_system_metrics_performance` — 36-project fixture, p95 < 200ms (local p95 ≈ 73ms).
  - `test_system_metrics_performance_cached` — cached repeat < 20ms.
- Frontend (`components/__tests__/SystemMetricsChip.test.tsx`): 26 Vitest cases across all six resilience variants plus expand/collapse and live-component smoke.

## Known Limitations

- **Fan-out ceiling** (~100 projects) — see `docs/project_plans/design-specs/system-metrics-background-rollup.md` (DEF-001). v1 in-process fan-out is adequate for current scale.
- **Lazy rescan not implemented** — stale projects show a warning but the service does not opportunistically rescan the filesystem. See `system-metrics-lazy-rescan.md` (DEF-002).
- **Widget API not hardened** — the REST surface is widget-friendly but not yet versioned or authenticated for external consumers. See `system-metrics-widget-api-hardening.md` (DEF-003).
- **Runtime smoke is human-gated** — this feature was authored as a background-agent sprint; the browser smoke step is a human-reviewer responsibility before merge to main.
- **Hard release gate**: `watcher-rebind-on-active-project-switch-v1` (already landed on this branch) is the contract behind accurate `is_stale` for non-active projects. Do not ship without it.
