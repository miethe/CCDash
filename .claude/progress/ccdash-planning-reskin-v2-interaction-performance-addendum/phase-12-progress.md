---
type: progress
schema_version: 2
doc_type: progress
prd: ccdash-planning-reskin-v2-interaction-performance-addendum
feature_slug: ccdash-planning-reskin-v2-interaction-performance-addendum
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-planning-reskin-v2.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2-interaction-performance-addendum-v1.md
phase: 12
title: Planning Query and Browser Cache Strategy
status: in_progress
created: 2026-04-21
updated: '2026-04-21'
started: null
completed: null
commit_refs: []
pr_refs: []
overall_progress: 80
completion_estimate: on-track
total_tasks: 5
completed_tasks: 4
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- python-backend-engineer
- react-performance-optimizer
contributors: []
model_usage:
  primary: sonnet
  external: []
tasks:
- id: P12-001
  description: Split summary/facets from graph/detail payloads if current summary
    cannot meet budget.
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  dependencies: []
  estimated_effort: 2 pts
  priority: high
  note: Implemented lightweight summary artifact facets without synchronous graph
    construction; targeted planning query tests passed.
- id: P12-002
  description: Add query params for active-first loading, terminal inclusion, and
    result limits.
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  dependencies:
  - P12-001
  estimated_effort: 2 pts
  priority: high
  note: Added active-first, include_terminal, and limit controls for planning summary
    results; targeted planning/router/cache tests passed.
- id: P12-003
  description: Fix backend cache fingerprint coverage for planning queries.
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  dependencies:
  - P12-001
  estimated_effort: 2 pts
  priority: high
  note: Expanded planning cache fingerprint coverage across sessions, features, feature
    phases, documents, entity links, and planning worktree contexts; document and
    phase-only invalidation tests passed.
- id: P12-004
  description: Add frontend bounded stale-while-revalidate cache for planning summary/facets.
  status: completed
  assigned_to:
  - react-performance-optimizer
  assigned_model: sonnet
  dependencies:
  - P12-001
  estimated_effort: 2 pts
  priority: high
  note: Added bounded in-memory SWR cache for planning summary payloads scoped by
    project and data freshness; planning page now renders warm summaries before
    background refresh and graph/detail payloads remain uncached.
- id: P12-005
  description: Add hover/open prefetch for feature context and roster/session details.
  status: pending
  assigned_to:
  - react-performance-optimizer
  assigned_model: sonnet
  dependencies:
  - P12-004
  estimated_effort: 1 pt
  priority: medium
parallelization:
  batch_1:
  - P12-001
  batch_2:
  - P12-002
  - P12-003
  - P12-004
  batch_3:
  - P12-005
  critical_path:
  - P12-001
  - P12-004
  - P12-005
  estimated_total_time: 2.5 days
blockers: []
success_criteria:
- id: SC-12.1
  description: Planning shell can render from a lightweight summary without building
    every graph synchronously
  status: completed
- id: SC-12.2
  description: Default home fetch prioritizes active/planned/blocked/review items;
    terminal features load on demand or after idle
  status: completed
- id: SC-12.3
  description: Cache invalidates when documents, feature phases, sessions, or entity
    links change, not only feature/session timestamps
  status: completed
- id: SC-12.4
  description: Returning to /planning renders warm state immediately (<250ms) and
    refreshes in background; cache has bounded keys and payload types
  status: completed
- id: SC-12.5
  description: Opening a recently hovered feature/agent is near-instant without preloading
    every detail payload
  status: pending
- id: SC-12.6
  description: All tests green
  status: pending
files_modified:
- backend/application/services/agent_queries/planning.py
- backend/application/services/agent_queries/cache.py
- backend/routers/agent.py
- backend/tests/test_agent_query_cache.py
- backend/tests/test_agent_query_cache_invalidation.py
- backend/tests/test_planning_coverage_pcp601.py
- backend/tests/test_planning_query_service.py
- backend/tests/test_planning_router.py
- components/Planning/PlanningHomePage.tsx
- services/planning.ts
- services/__tests__/planning.test.ts
progress: 80
---

# ccdash-planning-reskin-v2-interaction-performance-addendum - Phase 12: Planning Query and Browser Cache Strategy

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/ccdash-planning-reskin-v2-interaction-performance-addendum/phase-12-progress.md \
  -t P12-001 -s completed
```

---

## Phase Overview

**Title**: Planning Query and Browser Cache Strategy
**Entry Criteria**: Phase 11 complete. Backend summary fields agreed upon.
**Exit Criteria**: All tasks complete. Browser cache working with warm return <250ms. Cache invalidation covers all planning input tables. Tests green.

**Scope Reference**: `docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2-interaction-performance-addendum-v1.md#phase-12`

Phase 12 runs split across backend (python-backend-engineer) and frontend (react-performance-optimizer). Per the addendum's suggested execution order, the backend summary/cache contract work (P12-001 through P12-003) can proceed in parallel with Phase 11 modal extraction, provided the summary field contract is agreed first. P12-004 (browser cache) waits only on P12-001's payload split.

**Key constraint**: P12-003 must cover all planning input tables — features, feature phases, documents, sessions, entity links. The existing fingerprint only covers features/sessions; document-only changes can go stale under the current model.

---

## Task Details

| Task ID | Description | Assigned To | Model | Est | Deps | Status |
|---------|-------------|-------------|-------|-----|------|--------|
| P12-001 | Split summary/facets from graph/detail payloads | python-backend-engineer | sonnet | 2 pts | — | pending |
| P12-002 | Add active-first query params to backend | python-backend-engineer | sonnet | 2 pts | P12-001 | pending |
| P12-003 | Fix backend cache fingerprint coverage | python-backend-engineer | sonnet | 2 pts | P12-001 | pending |
| P12-004 | Add frontend bounded stale-while-revalidate cache | react-performance-optimizer | sonnet | 2 pts | P12-001 | pending |
| P12-005 | Add hover/open prefetch for feature/agent details | react-performance-optimizer | sonnet | 1 pt | P12-004 | pending |

### P12-001 Acceptance Criteria
The planning shell can render from a lightweight summary payload (status counts, facets, feature list) without building every graph relationship synchronously. Graph/detail payloads are available as separate endpoints or deferred lazy loads. Backend: `backend/application/services/agent_queries/planning.py`, `backend/routers/api.py`.

### P12-002 Acceptance Criteria
Backend supports query params controlling active-first loading (prioritizes `in-progress`, `review`, `blocked`, `draft`, `approved`), optional terminal inclusion (`done`, `completed`, `closed`, `deferred`, `superseded`), and result limits. Default home fetch excludes or deprioritizes terminal features.

### P12-003 Acceptance Criteria
Backend cache fingerprint for all planning queries includes: features, feature phases, documents, sessions, entity links, and any planning status/writeback tables. A document-only change invalidates the cache. Files: `backend/application/services/agent_queries/cache.py`, `backend/application/services/agent_queries/planning.py`.

### P12-004 Acceptance Criteria
Frontend implements a bounded stale-while-revalidate cache scoped by project id and planning data freshness. Returning to `/planning` renders warm summary state immediately (target <250ms) and revalidates in background. Cache has bounded project count and payload type limits to prevent memory growth. Only summary/facet/list payloads are cached; large detail payloads are not.

### P12-005 Acceptance Criteria
Hovering a feature card or agent roster row begins prefetching the detail payload. Opening a recently hovered item resolves near-instantly. Does not preload all detail payloads eagerly; only hovered items trigger prefetch.

---

## Quick Reference

### Batch 1 — Unblocked; backend and frontend can coordinate on contract
```
Task("python-backend-engineer", "P12-001: Split summary/facets from graph/detail payloads in backend/application/services/agent_queries/planning.py. Planning shell must render from a lightweight summary without building every graph synchronously. Coordinate with react-performance-optimizer on the summary field contract before P12-004 starts.")
```

### Batch 2 — After P12-001; run in parallel
```
Task("python-backend-engineer", "P12-002: Add query params for active-first loading, terminal inclusion, and result limits to backend/application/services/agent_queries/planning.py and backend/routers/api.py. Default fetch prioritizes in-progress/review/blocked/draft/approved; terminal features load on demand or after idle.")
Task("python-backend-engineer", "P12-003: Fix backend cache fingerprint coverage for all planning queries in backend/application/services/agent_queries/cache.py. Must include features, feature phases, documents, sessions, entity links, and planning status/writeback tables. A document-only change must invalidate the cache.")
Task("react-performance-optimizer", "P12-004: Add frontend bounded stale-while-revalidate cache for planning summary/facets in services/planning.ts. Scoped by project id and data freshness. Warm return target <250ms. Bounded keys and payload types — no caching of large detail payloads. Files: services/planning.ts, contexts/AppEntityDataContext.tsx or equivalent.")
```

### Batch 3 — After P12-004
```
Task("react-performance-optimizer", "P12-005: Add hover/open prefetch for feature context and roster/session details. Hovering a feature card or agent row begins prefetching detail payload. Opening a recently hovered item resolves near-instantly. Do not eagerly preload all details. Files: services/planning.ts, components/Planning/PlanningAgentRosterPanel.tsx, components/Planning/PlanningHomePage.tsx")
```

---

## Quality Gates

- [ ] Summary payload renders planning shell without graph synchronously
- [x] Active-first query params documented and tested
- [x] Cache fingerprint covers all 6 planning input tables
- [ ] Warm `/planning` return renders in <250ms (component timing)
- [ ] Browser cache bounded (project count + payload type limits)
- [ ] Prefetch triggers on hover; does not eagerly load all details
- [x] Backend tests cover active-first filtering and document-driven invalidation
- [ ] Tests green

---

## Status Updates

<!-- Agents: append timestamped notes here as work progresses -->
- 2026-04-21 Worker D: Completed P12-002/P12-003. Added active-first planning
  summary query controls (`active_first`, `include_terminal`, `limit`), expanded
  planning cache fingerprints to cover sessions/features/feature phases/documents/entity
  links/planning worktree contexts, and verified targeted backend tests:
  `PYTHONPATH=. uv run pytest backend/tests/test_planning_query_service.py backend/tests/test_planning_router.py backend/tests/test_planning_coverage_pcp601.py backend/tests/test_agent_query_cache.py backend/tests/test_agent_query_cache_invalidation.py -q`
  (96 passed).
- 2026-04-21 Worker E: Completed P12-004. Added bounded project/data-freshness
  SWR cache for planning summary payloads, synchronous warm summary handoff in
  `/planning`, background revalidation state refresh, force refresh for live
  invalidations, and focused Vitest coverage for warm returns, revalidation, and
  project-key eviction. Verified `npm run test -- services/__tests__/planning.test.ts
  services/__tests__/planningExtended.test.ts` and `npm run build`.
