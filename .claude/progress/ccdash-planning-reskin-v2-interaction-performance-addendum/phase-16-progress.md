---
type: progress
schema_version: 2
doc_type: progress
prd: ccdash-planning-reskin-v2-interaction-performance-addendum
feature_slug: ccdash-planning-reskin-v2-interaction-performance-addendum
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-planning-reskin-v2.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2-interaction-performance-addendum-v1.md
phase: 16
title: Verification and Performance Gates
status: completed
created: 2026-04-21
updated: '2026-04-22'
started: null
completed: null
commit_refs: []
pr_refs: []
overall_progress: 0
completion_estimate: on-track
total_tasks: 7
completed_tasks: 7
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- testing-specialist
- react-performance-optimizer
- web-accessibility-checker
contributors: []
model_usage:
  primary: sonnet
  external: []
tasks:
- id: P16-001
  description: Add frontend tests for modal-first navigation.
  status: completed
  assigned_to:
  - testing-specialist
  assigned_model: sonnet
  dependencies:
  - P11-002
  - P11-003
  estimated_effort: 1.5 pts
  priority: high
- id: P16-002
  description: Add cache and lazy-load tests.
  status: completed
  assigned_to:
  - testing-specialist
  assigned_model: sonnet
  dependencies:
  - P12-004
  - P12-005
  estimated_effort: 1.5 pts
  priority: high
- id: P16-003
  description: Add backend tests for planning summary fields and cache invalidation.
  status: completed
  assigned_to:
  - testing-specialist
  assigned_model: sonnet
  dependencies:
  - P13-001
  - P12-003
  estimated_effort: 1.5 pts
  priority: high
- id: P16-004
  description: Add roster and tracker interaction tests.
  status: completed
  assigned_to:
  - testing-specialist
  assigned_model: sonnet
  dependencies:
  - P14-001
  - P15-004
  estimated_effort: 1 pt
  priority: high
- id: P16-005
  description: Measure load budgets.
  status: completed
  assigned_to:
  - react-performance-optimizer
  assigned_model: sonnet
  dependencies:
  - P12-004
  - P12-005
  estimated_effort: 1.5 pts
  priority: high
- id: P16-006
  description: A11y regression for new modal/panel surfaces.
  status: completed
  assigned_to:
  - web-accessibility-checker
  assigned_model: sonnet
  dependencies:
  - P14-001
  - P15-004
  - P11-003
  estimated_effort: 1 pt
  priority: high
- id: P16-007
  description: Add OTEL spans on new planning query params and cache fingerprint paths.
  status: completed
  assigned_to:
  - python-backend-engineer
  assigned_model: sonnet
  dependencies:
  - P12-001
  - P12-002
  - P12-003
  - P15-001
  estimated_effort: 1 pt
  priority: medium
parallelization:
  batch_1:
  - P16-001
  - P16-002
  - P16-003
  - P16-004
  - P16-005
  - P16-006
  - P16-007
  critical_path:
  - P16-003
  - P16-005
  estimated_total_time: 2 days
blockers: []
success_criteria:
- id: SC-16.1
  description: Tests assert planning clicks do not navigate to /board unless explicit
    board link clicked
  status: pending
- id: SC-16.2
  description: Tests cover warm render, stale revalidation, bounded cache eviction,
    and detail-only-on-open behavior
  status: pending
- id: SC-16.3
  description: Tests cover statusCounts, ctx/phase fields, token availability, active-first
    filtering, and document-driven invalidation
  status: pending
- id: SC-16.4
  description: Tests cover side panel, row modal, agent naming precedence, and scroll-height
    behavior
  status: pending
- id: SC-16.5
  description: Warm planning return renders summary in under 250ms (component-level
    timing); cold local p95 under 2s for summary shell before graph hydration
  status: pending
- id: SC-16.6
  description: Focus trap on PlanningQuickViewPanel, agent detail modal, route-local
    feature modal; ARIA roles correct; keyboard-close on all three
  status: pending
- id: SC-16.7
  description: OTEL spans on P12-001, P12-002, P12-003, P15-001 service methods
  status: pending
- id: SC-16.8
  description: Full test suite green
  status: pending
files_modified: []
progress: 100
---

# ccdash-planning-reskin-v2-interaction-performance-addendum - Phase 16: Verification and Performance Gates

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/ccdash-planning-reskin-v2-interaction-performance-addendum/phase-16-progress.md \
  -t P16-001 -s completed
```

---

## Phase Overview

**Title**: Verification and Performance Gates
**Entry Criteria**: Phases 11-15 feature-complete. All code integrated.
**Exit Criteria**: All tasks complete. Test suite green. Load budgets met. A11y regression coverage in place. OTEL instrumentation complete. QA pass.

**Scope Reference**: `docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2-interaction-performance-addendum-v1.md#phase-16`

All seven tasks in Phase 16 can run in parallel once phases 11-15 are complete — each targets a different surface (navigation, cache, backend fields, interactions, performance, a11y, OTEL). The critical path for performance measurement (P16-005) depends on lazy-loading changes from Phase 12, so ensure P12-004 and P12-005 are fully merged before taking load budget measurements.

Note: `assigned_to` for P16-007 is `python-backend-engineer`, which is not listed in `owners` for this phase. This is intentional — the plan assigns this task to the backend engineer who built the query params in Phase 12. Flag for human review if assignment needs to match a `web-accessibility-checker` or `react-performance-optimizer` resource.

---

## Task Details

| Task ID | Description | Assigned To | Model | Est | Deps | Status |
|---------|-------------|-------------|-------|-----|------|--------|
| P16-001 | Frontend tests: modal-first navigation | testing-specialist | sonnet | 1.5 pts | P11-002, P11-003 | pending |
| P16-002 | Frontend tests: cache and lazy-load behavior | testing-specialist | sonnet | 1.5 pts | P12-004, P12-005 | pending |
| P16-003 | Backend tests: planning summary fields + cache invalidation | testing-specialist | sonnet | 1.5 pts | P13-001, P12-003 | pending |
| P16-004 | Frontend tests: roster and tracker interactions | testing-specialist | sonnet | 1 pt | P14-001, P15-004 | pending |
| P16-005 | Measure load budgets | react-performance-optimizer | sonnet | 1.5 pts | P12-004, P12-005 | pending |
| P16-006 | A11y regression: new modal/panel surfaces | web-accessibility-checker | sonnet | 1 pt | P14-001, P15-004, P11-003 | pending |
| P16-007 | OTEL spans on new planning query/cache paths | python-backend-engineer | sonnet | 1 pt | P12-001..P12-003, P15-001 | pending |

### P16-001 Acceptance Criteria
Tests in `components/Planning/__tests__/planningHomePageNavigation.test.tsx` assert that: (a) clicking feature cards does not trigger navigation to `/board`; (b) the route-local feature modal opens; (c) browser back closes the modal without leaving `/planning`; (d) the explicit "Open board" secondary link does navigate to `/board`.

### P16-002 Acceptance Criteria
Tests in `services/__tests__/planning.test.ts` cover: (a) warm render returns cached summary immediately; (b) stale-while-revalidate triggers background refresh; (c) cache eviction fires when bounded key count is exceeded; (d) large detail payloads (`feature context`, `full graph`) are not loaded until their panel is opened.

### P16-003 Acceptance Criteria
Tests in `backend/tests/test_planning_query_service.py` cover: (a) `statusCounts` buckets are mutually exclusive and sum to total feature count; (b) `ctxPerPhase` returns `source="unavailable"` when data cannot be derived; (c) `tokenTelemetry` returns `source="unavailable"` when session attribution is missing; (d) active-first filtering excludes terminal features from default results; (e) modifying a document (without changing any feature) invalidates the planning cache.

### P16-004 Acceptance Criteria
Tests cover: (a) tracker row click opens `PlanningQuickViewPanel` (not board navigation); (b) feature-slug row resolves feature quick view; (c) doc-only row resolves document view; (d) roster rows show correct agent type label per precedence rules; (e) roster panel scroll height respects pinned height at desktop breakpoints.

### P16-005 Acceptance Criteria
Load budget measurement using component-level timing (not network): (a) warm return to `/planning` renders summary shell in <250ms; (b) cold local dev p95 renders summary shell in <2s before graph hydration begins. Measurement methodology documented. If budgets are not met, file a finding and block Phase 17.

### P16-006 Acceptance Criteria
Accessibility regression covering three new surfaces: `PlanningQuickViewPanel`, agent detail modal (P15-004), and route-local feature modal (P11-001). Each must pass: (a) focus trap when open, (b) correct ARIA roles (`dialog` or `complementary` as appropriate), (c) keyboard-close (Escape key), (d) no focus-loss on close.

### P16-007 Acceptance Criteria
OTEL spans instrument the following new service methods: the summary/facets split endpoint (P12-001), active-first query param handler (P12-002), cache fingerprint builder (P12-003), and `subagentType` derivation path (P15-001). Spans include relevant context attributes (project id, query params used, cache hit/miss). Files: `backend/observability/otel.py`, instrumented service methods.

---

## Quick Reference

### Batch 1 — After all feature phases (11-15) complete; run all in parallel
```
Task("testing-specialist", "P16-001: Add frontend tests for modal-first navigation to components/Planning/__tests__/planningHomePageNavigation.test.tsx. Assert: feature clicks open route-local modal (not /board); browser back closes modal; explicit 'Open board' link still navigates. Depends on P11-002, P11-003.")
Task("testing-specialist", "P16-002: Add frontend cache and lazy-load tests to services/__tests__/planning.test.ts. Cover: warm render from cache, stale-while-revalidate refresh, bounded cache eviction, detail payloads load only on open. Depends on P12-004, P12-005.")
Task("testing-specialist", "P16-003: Add backend tests to backend/tests/test_planning_query_service.py. Cover: statusCounts mutually exclusive, ctxPerPhase unavailable fallback, tokenTelemetry unavailable fallback, active-first filtering, document-driven cache invalidation. Depends on P13-001, P12-003.")
Task("testing-specialist", "P16-004: Add tests for roster and tracker interactions. Cover: tracker row opens PlanningQuickViewPanel, feature-slug resolution, doc-only resolution, agent type label precedence, roster scroll height. Depends on P14-001, P15-004.")
Task("react-performance-optimizer", "P16-005: Measure load budgets for planning page. Warm return summary shell <250ms (component timing). Cold local p95 summary shell <2s before graph hydration. Document methodology. If budgets missed, file finding and block Phase 17. Depends on P12-004, P12-005.")
Task("web-accessibility-checker", "P16-006: A11y regression for three new surfaces: PlanningQuickViewPanel, agent detail modal (P15-004), route-local feature modal (P11-001). Each needs: focus trap, ARIA roles, keyboard-close (Escape), no focus-loss on close. Depends on P14-001, P15-004, P11-003.")
Task("python-backend-engineer", "P16-007: Add OTEL spans to service methods introduced in P12-001 (summary split), P12-002 (active-first params), P12-003 (fingerprint builder), P15-001 (subagentType derivation). Include project id, query params, cache hit/miss in span attributes. Files: backend/observability/otel.py and the relevant service methods.")
```

---

## Quality Gates

- [ ] No planning clicks route to `/board` without explicit board link (P16-001)
- [ ] Cache warm/stale/eviction behavior verified by test (P16-002)
- [ ] `statusCounts` mutual exclusion verified by backend test (P16-003)
- [ ] Document-driven cache invalidation verified by backend test (P16-003)
- [ ] Tracker/roster interaction tests pass (P16-004)
- [ ] Warm <250ms, cold p95 <2s load budgets met or finding filed (P16-005)
- [ ] Focus trap + ARIA + keyboard-close on all 3 new surfaces (P16-006)
- [ ] OTEL spans on all 4 new service paths (P16-007)
- [ ] Full test suite green

---

## Status Updates

<!-- Agents: append timestamped notes here as work progresses -->
