---
schema_version: 2
slug: dashboard-kpi-tq-migration
title: Analytics Dashboard KPI zero-render fix — migrate to TanStack Query overview
  bundle
status: completed
runtime_smoke: passed
type: quick-feature
created: 2026-05-30
owner: opus-orchestrator
updated: '2026-05-30'
---

# Analytics Dashboard zero-KPI fix

## True behavior (verified)
Not a data-shape or backend bug. `/api/analytics/overview` is slow (20.5s cold / 9.7s warm
/ 4.2s via proxy). `Dashboard.tsx` renders `Number(overview?.kpis?.X || 0)` with **no loading
state**, so KPIs show literal `0` while the request is in flight; the `catch` only
`console.error`s, so an aborted request (fast modal nav + memory-guard in-flight GC) leaves
zeros permanently and silently. A separate probe returns 200 → reporter's contradiction.

## Intended design
`services/queries/analytics.ts::useAnalyticsOverviewQuery` (→ `/api/analytics/overview-bundle`,
server-memoized) was built to replace the imperative `getOverview()` path but Dashboard.tsx
was never migrated.

## Tasks
- T0-001 (backend): Extend `AnalyticsKPIsDTO` + bundle mapping in
  `backend/application/services/agent_queries/analytics_bundle.py` with `contextSessionCount`,
  `avgContextUtilizationPct`, `toolReportedTokens` (map from existing `kpis_raw`, camelCase
  serialization matching existing fields). status: pending
- T0-002 (frontend): Extend `AnalyticsOverviewBundleDTO` in `services/queries/analytics.ts`
  with the 3 new camelCase fields. status: pending
- T0-003 (frontend): Migrate `components/Dashboard.tsx` KPI cards + top models + workload to
  `useAnalyticsOverviewQuery` (loading skeleton / error state instead of `0`); decouple the
  remaining series + calibration imperative calls via `Promise.allSettled` with their own
  loading/error state. status: pending

## Acceptance criteria
- AC1: KPI cards show a loading skeleton (not `0`) while the bundle request is pending.
- AC2: On bundle error/abort, an error affordance is shown (not silent zeros).
- AC3: All KPIs (incl. contextSessionCount, avgContextUtilizationPct, observed workload incl.
  toolReportedTokens) render real values on success — no regression vs legacy path.
- AC4: A slow/failed series or calibration call no longer zeros the KPI cards.
- AC5: Runtime smoke: `#/dashboard` renders real KPIs in browser.
