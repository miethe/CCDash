---
schema_version: 2
doc_type: implementation_plan
title: Code Health Cleanup - Implementation Plan
description: Address remaining tech-debt and perf gaps surfaced by the 2026-04-28
  deep code-health pass that exceed the safe-to-implement scope of that pass.
  Bundle-split, mega-file split, router raw-SQL refactor, backend SELECT LIMIT,
  features.py JSON-extract → indexed columns, runtime_smoke skip resolution.
status: in-progress
created: '2026-04-28'
updated: '2026-04-29'
feature_slug: code-health-cleanup-v1
feature_version: v1
prd_ref: null
plan_ref: null
scope: Six independent harden-polish workstreams identified by the 2026-04-28
  deep code-health pass. Each has a separable phase and can ship independently.
effort_estimate: 22 story points
architecture_summary: No architectural changes. Phase work follows existing
  layered conventions (router → service → repository) and existing frontend
  Provider patterns. Most phases are mechanical refactors with measurement gates.
related_documents:
- docs/project_plans/implementation_plans/infrastructure/runtime-performance-hardening-v1.md
- docs/project_plans/implementation_plans/harden-polish/feature-surface-remediation-v1.md
references:
  related_prds: []
spike_ref: null
adr_refs: []
deferred_items_spec_refs: []
findings_doc_ref: null
changelog_required: true
owner: null
contributors: []
priority: medium
risk_level: medium
category: harden-polish
tags:
- tech-debt
- performance
- bundle
- architecture
- runtime-smoke
milestone: null
commit_refs: []
pr_refs: []
files_affected:
- App.tsx
- components/SessionInspector.tsx
- backend/routers/analytics.py
- backend/routers/features.py
- backend/routers/test_visualizer.py
- backend/services/test_health.py
- backend/db/repositories/features.py
- backend/db/repositories/postgres/features.py
- backend/db/repositories/sessions.py
- backend/db/repositories/postgres/sessions.py
- backend/services/codebase_explorer.py
- vite.config.ts
- package.json
---

# Implementation Plan: Code Health Cleanup v1

**Plan ID**: `IMPL-2026-04-28-CODE-HEALTH-CLEANUP`
**Date**: 2026-04-28
**Complexity**: Medium | **Total Estimated Effort**: 22 story points | **Target Timeline**: 3–4 weeks (phases independent)

## Executive Summary

The 2026-04-28 deep code-health pass shipped four batches of safe, low-risk improvements (commits `8ce7ec4`, `55e6464`, `d4f0f21`, `1913581`):

- **Frontend perf**: memoized 3 context provider values, fixed PlanCatalog a11y, cleaned 7 trivial `as any` casts.
- **Backend N+1**: 6 hotspots refactored to bulk repo fetches; 2 silent excepts and 6 parser skips made loud.
- **DB**: 3 composite indexes added.
- **Plan hygiene**: 5 PRDs flipped to completed, commit_refs backfilled on 8 plans, stale phase frontmatter reconciled, 4 findings docs accepted.

Six items in the audit need broader scope (measurement, owner sign-off, or non-trivial refactor) and were intentionally deferred to this follow-up plan. None are urgent but all reduce ongoing toil.

---

## Phases

### Phase 1: Route-Level Code Splitting (`React.lazy` + `Suspense`)

**Effort**: 5 pts | **Risk**: medium | **Owner**: ui-engineer-enhanced + react-performance-optimizer

**Problem**: `App.tsx` eagerly imports every page including `SessionInspector` (8990 LOC) and `ProjectBoard` (5433 LOC). Recharts (~300KB minified) is pulled in by `Dashboard`, `SessionInspector`, `Analytics/AnalyticsDashboard`, `Analytics/TrendChart`, `TestVisualizer/TestTimeline`. Initial bundle ships everything to every route.

**Approach**: Wrap each route in `React.lazy(() => import("./components/X"))` and add a `<Suspense fallback={<RoutePending />}>` boundary at the route shell. Verify in Vite that this produces separate chunks per route.

**Tasks**:
| ID | Description | Estimate |
|---|---|---|
| CH-101 | Convert `App.tsx` route imports to `React.lazy` | 1 pt |
| CH-102 | Add `<Suspense>` wrapper + accessible fallback (skeleton) | 1 pt |
| CH-103 | Verify Vite produces per-route chunks (`npm run build` then inspect `dist/assets/*.js`) | 0.5 pts |
| CH-104 | Lazy-load Recharts behind a `lazy(() => import("recharts"))` for chart-heavy components | 1.5 pts |
| CH-105 | Lazy-load `react-color` (Settings only) and `@google/genai` (Gemini service consumers only) | 1 pt |

**Quality gates**:
- `npm run build` succeeds; main chunk size < 50% of pre-change baseline
- Each route loads independently in `npm run dev` (DevTools Network tab)
- Runtime smoke: navigate Dashboard → Board → Plans → Sessions → Settings; verify no broken imports

---

### Phase 2: SessionInspector Mega-File Split

**Effort**: 5 pts | **Risk**: medium-high | **Owner**: ui-engineer-enhanced

**Problem**: `components/SessionInspector.tsx` is 8990 LOC. Tree-shaking suffers, code review is impractical, hot-path memoization is hard to land.

**Approach**: Identify natural region boundaries (transcript view, tool-usage panel, file-update panel, artifact panel, summary header, comparison/diff view). Extract each into a sibling file under `components/SessionInspector/` with clear named exports. Mechanical movement only — no behavior change. Run Vitest after each extraction.

**Tasks**:
| ID | Description | Estimate |
|---|---|---|
| CH-201 | Survey + diagram of region boundaries; document split plan | 0.5 pts |
| CH-202 | Extract transcript view (largest region) → `components/SessionInspector/TranscriptView.tsx` | 1 pt |
| CH-203 | Extract tool-usage + file-update + artifact panels | 1 pt |
| CH-204 | Extract summary header + comparison views | 1 pt |
| CH-205 | Memoize per-row date/label computations (`Date.now()` / `new Date()` callsites at lines 2404, 3910, 4130, 4633, 4782, 4793, 5663, 7987, 8171) | 1 pt |
| CH-206 | Vitest + runtime smoke after each extraction; final integration sweep | 0.5 pts |

**Quality gates**:
- All Vitest tests in `components/__tests__` pass at every extraction step
- Runtime smoke: open a session, verify all panels render identically
- New file count: SessionInspector parent < 1500 LOC; each child < 1500 LOC

---

### Phase 3: Router Raw-SQL → Repository Migration

**Effort**: 4 pts | **Risk**: low-medium | **Owner**: python-backend-engineer + backend-architect

**Problem**: Architecture violations — three routers issue raw SQL directly, bypassing the repository layer:
- `backend/routers/analytics.py:582-607, 3027-3099` — raw `SELECT` on `payload_json`, COUNT subqueries
- `backend/routers/features.py:1006-1045` — raw `INSERT INTO telemetry_events` directly in router
- `backend/routers/test_visualizer.py:208, 235, 418, 434` — raw `SELECT *` and joins
- `backend/services/test_health.py:584, 597` — raw `SELECT *` in service layer

**Approach**: For each callsite, identify or add the corresponding repository method, then have the router/service call the repo. Preserve all SQL semantics. Add coverage tests on the new repo methods.

**Tasks**:
| ID | Description | Estimate |
|---|---|---|
| CH-301 | analytics.py raw queries → `analytics_repository` (or extend existing) | 1.5 pts |
| CH-302 | features.py telemetry insert → `telemetry_repository` | 0.5 pts |
| CH-303 | test_visualizer.py raw queries → `test_visualizer_repository` | 1 pt |
| CH-304 | test_health.py service-level raw SQL → `test_health_repository` | 0.5 pts |
| CH-305 | Repo unit tests (parity with existing query results) | 0.5 pts |

**Quality gates**:
- No `await self.db.execute(` outside `backend/db/repositories/` (grep guardrail in CI)
- All affected endpoints return identical response shape (record-and-replay test)

---

### Phase 4: Backend SELECT LIMIT + Pagination

**Effort**: 3 pts | **Risk**: low | **Owner**: data-layer-expert + python-backend-engineer

**Problem**: Backend session-detail loaders return unbounded result sets even though FE has a transcript ring buffer cap (FE-101). Backend still ships the full payload over the wire on the first fetch.
- `backend/db/repositories/sessions.py:679, 691, 698, 705, 712` — five `SELECT * FROM session_logs / session_tool_usage / session_file_updates / session_artifacts WHERE session_id = ?` without LIMIT.
- `backend/db/repositories/usage_attribution.py:76`, `session_messages.py:57` — same pattern.
- `backend/db/repositories/documents.py:383` and `features.py:234` — `list_all` calls `list_paginated(0, 1_000_000)`.

**Approach**: Add a server-side LIMIT (default 5000 to match FE ring buffer) plus optional `cursor` parameter for follow-up pages. Existing single-page consumers continue to work; new pagination opt-in.

**Tasks**:
| ID | Description | Estimate |
|---|---|---|
| CH-401 | sessions.py: add LIMIT + offset/cursor to log/tool/file/artifact loaders | 1.5 pts |
| CH-402 | usage_attribution.py + session_messages.py: same pattern | 0.5 pts |
| CH-403 | documents.py + features.py: deprecate `list_all` (or hard-cap at 5000) | 0.5 pts |
| CH-404 | Update API docs + tests | 0.5 pts |

**Quality gates**:
- No regression in current session detail endpoint response shape
- New `cursor` param works end-to-end on `/api/sessions/<id>/logs`
- Pagination metadata accurate (test fixture with 6000 logs returns 5000 + cursor)

---

### Phase 5: features.py JSON-Extract → Indexed Columns

**Effort**: 3 pts | **Risk**: medium | **Owner**: data-layer-expert + python-backend-engineer

**Problem**: `backend/db/repositories/features.py` and `backend/db/repositories/postgres/features.py` carry 14× duplicated `TODO P2` markers (lines 35, 37, 70, 92, 98, 116, 125 in each) where queries fall back to `json_extract(payload_json, ...)` because columns "should be added".

**Approach**: Audit which JSON-extract fields are queried often (filtering, sorting). Promote those to first-class columns via migration (with backfill from `payload_json`). Replace JSON-extract code paths with column reads. Drop the TODO markers.

**Tasks**:
| ID | Description | Estimate |
|---|---|---|
| CH-501 | Audit each TODO P2 site: which fields, query frequency, write frequency | 0.5 pts |
| CH-502 | Migration: add columns + backfill from payload_json (sqlite + postgres) | 1 pt |
| CH-503 | Update repository methods to use new columns; remove TODO markers | 1 pt |
| CH-504 | Add indexes if filtering/sorting columns warrant them | 0.5 pts |

**Quality gates**:
- Backfill migration is safe on existing data (test with fixture DB)
- All `TODO P2` markers in features.py removed
- Existing feature query latency unchanged or improved

---

### Phase 6: Runtime Smoke Skip Resolution + Branch Merge

**Effort**: 2 pts | **Risk**: low (mostly process) | **Owner**: nick + devops-architect

**Problem**: Three categories of unresolved smoke skips:

1. **`runtime_smoke: skipped` debt** carried forward from prior plans:
   - `runtime-performance-hardening-v1` phase 4
   - `feature-surface-data-loading-redesign-v1` phase 4 + phase 5
2. **Containerized-deployment skips** with technical reasons:
   - phase 5 (`SELinux unavailable on macOS host`)
   - phase 7 (`podman-compose 1.5.0 KeyError on depends_on.postgres`)
3. **Branch merge decision**: `infra/containerized-deployment` has phase 4/5/7 commits and plan marked `completed`, but is **NOT on `main`**. Either merge or revert plan status.

**Tasks**:
| ID | Description | Estimate |
|---|---|---|
| CH-601 | Run hosted runtime smoke on the 3 prior-plan skips OR document permanent waiver in each plan body | 0.5 pts |
| CH-602 | File GH issues for podman-compose ≥1.6 upgrade and macOS SELinux fallback | 0.25 pts |
| CH-603 | Decide + execute on `infra/containerized-deployment` → `main` (merge or revert plan status) | 1 pt |
| CH-604 | Update `feature-execution-workbench` family (parent + phase-3, phase-4, future-phases): kill, archive, or schedule (frontmatter status drift since 2026-02-27) | 0.25 pts |

**Quality gates**:
- No plan retains `runtime_smoke: skipped` without explicit justification field set
- `git branch --contains` confirms recent containerized-deployment commits are on `main` (or plan reverted to `in-progress`)
- `feature-execution-workbench` family: each plan has `status` matching reality

---

## Phase Summary

| Phase | Title | Estimate | Risk | Independent? |
|-------|-------|----------|------|--------------|
| 1 | Route-Level Code Splitting | 5 pts | medium | yes |
| 2 | SessionInspector Mega-File Split | 5 pts | med-high | yes |
| 3 | Router Raw-SQL → Repository | 4 pts | low-med | yes |
| 4 | Backend SELECT LIMIT + Pagination | 3 pts | low | yes |
| 5 | features.py JSON-Extract → Indexed Columns | 3 pts | medium | yes (migration coordination) |
| 6 | Runtime Smoke Resolution + Branch Merge | 2 pts | low | yes (mostly process) |
| **Total** | — | **22 pts** | — | All phases parallelizable |

---

## Out of Scope

- Anything already shipped by `runtime-performance-hardening-v1` (transcript ring buffer, document pagination cap, polling teardown, in-flight GC, link rebuild dedup, query cache TTL=600s, batch workflow query, Prometheus counters)
- Provider memoization, PlanCatalog a11y, `as any` cleanup (shipped in `8ce7ec4`)
- Backend N+1 fixes (shipped in `55e6464`)
- Composite indexes (shipped in `d4f0f21`)
- Plan/PRD frontmatter reconciliation (shipped in `1913581`)
- Design-spec maturity flips on shaping specs (`agent-query-cache-lru-v1`, `transcript-fetch-on-demand-v1`, planning-* specs) — owner decision required
- React.memo across hot-list components — defer until Phase 1 (route splitting) measurement establishes a baseline

---

## Risk Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Phase 1: route lazy-load breaks dynamic imports under Vite | medium | low | Verify in dev mode before merging; rollback is one-revert |
| Phase 2: SessionInspector split misses an internal cross-reference | high | medium | Vitest after each extraction; runtime smoke per region |
| Phase 3: router → repo refactor changes response shape | medium | low | Record-and-replay test per endpoint before/after |
| Phase 4: pagination breaks downstream consumers | medium | low | Default LIMIT preserves single-page behavior; cursor is opt-in |
| Phase 5: backfill migration on large feature tables takes too long | medium | low | Backfill in batches; document rollback DDL |
| Phase 6: branch-merge decision has hidden conflicts | medium | medium | Dry-run rebase before declaring intent |

---

## Success Metrics

- **Bundle**: Initial route bundle reduced by ≥40% post-Phase 1 (measured via `npm run build` chunk sizes)
- **Maintainability**: SessionInspector parent file < 1500 LOC after Phase 2
- **Architecture**: Zero `await self.db.execute(` callsites outside `backend/db/repositories/` after Phase 3
- **Resilience**: Backend session-log endpoint returns ≤5000 rows by default after Phase 4
- **Tech debt**: All 14 `TODO P2` markers removed from `features.py` after Phase 5
- **Hygiene**: Zero `runtime_smoke: skipped` without justification; `infra/containerized-deployment` resolved after Phase 6

---

## Wrap-Up

After all phases ship:
1. Update CHANGELOG `[Unreleased]` with each phase's user-facing impact (Phase 1 perf, Phase 4 backend resilience).
2. Backfill `commit_refs` on this plan.
3. Flip `status: completed`.
4. No new design specs required (these are all closure work, not new capability).

---

**Implementation Plan Version**: 1.0
**Last Updated**: 2026-04-28
