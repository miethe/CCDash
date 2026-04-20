---
type: progress
schema_version: 2
doc_type: progress
prd: "ccdash-planning-reskin-v2"
feature_slug: "ccdash-planning-reskin-v2"
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-planning-reskin-v2.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md
phase: 9
title: "Testing — Unit, Integration, Component"
status: "pending"
created: 2026-04-20
updated: 2026-04-20
started: null
completed: null
commit_refs: []
pr_refs: []

overall_progress: 0
completion_estimate: "on-track"

total_tasks: 5
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0

owners: ["frontend-developer", "testing-specialist"]
contributors: ["python-backend-engineer", "web-accessibility-checker"]

model_usage:
  primary: "sonnet"
  external: []

tasks:
  - id: "T9-001"
    description: "Vitest unit tests for all primitives: StatusPill (11 status values), ArtifactChip (8 types), MetricTile, Spark, ExecBtn, PhaseDot, PhaseStackInline, TotalsCell, DocChip, Dot, Chip, Panel, Tile; target >90% coverage"
    status: "pending"
    assigned_to: ["frontend-developer", "testing-specialist"]
    dependencies: ["T8-004"]
    estimated_effort: "2 pts"
    priority: "high"
    assigned_model: "sonnet"

  - id: "T9-002"
    description: "Component tests for PlanningHomePage (metrics/chips), PlanningGraphPanel (rows/lanes/edges), PlanningNodeDetail (drawer open/close/lineage), TriagePanel (tabs/rows/actions), AgentRoster (rows/state dots); React Testing Library; mock API; target >80% coverage"
    status: "pending"
    assigned_to: ["frontend-developer", "testing-specialist"]
    dependencies: ["T9-001"]
    estimated_effort: "2.5 pts"
    priority: "high"
    assigned_model: "sonnet"

  - id: "T9-003"
    description: "OQ resolution integration test: backend (seed feature with OQ, call PATCH, verify 200 with resolved OQ, verify OTEL span) and frontend (mock API, render OQ editor, resolve, verify UI update); target >85% coverage"
    status: "pending"
    assigned_to: ["python-backend-engineer", "frontend-developer"]
    dependencies: ["T7-003", "T6-002"]
    estimated_effort: "2 pts"
    priority: "high"
    assigned_model: "sonnet"

  - id: "T9-004"
    description: "E2E tests (Playwright) for 7 critical journeys: open planning home, click graph row, drawer opens with lineage, resolve OQ inline, switch to DAG view, click exec button, toast appears and dismisses"
    status: "pending"
    assigned_to: ["testing-specialist"]
    dependencies: ["T9-003"]
    estimated_effort: "2 pts"
    priority: "high"
    assigned_model: "sonnet"

  - id: "T9-005"
    description: "Run axe-core automated a11y tests on all planning surfaces (target 0 violations); manual screen-reader smoke test for feature title and key interactive elements; document false positives"
    status: "pending"
    assigned_to: ["web-accessibility-checker", "testing-specialist"]
    dependencies: ["T8-004"]
    estimated_effort: "1.5 pts"
    priority: "high"
    assigned_model: "sonnet"

parallelization:
  batch_1: ["T9-001", "T9-003", "T9-005"]
  batch_2: ["T9-002"]
  batch_3: ["T9-004"]
  critical_path: ["T9-001", "T9-002", "T9-004"]
  estimated_total_time: "2-3 days"

blockers: []

success_criteria:
  - { id: "SC-9.1", description: "All primitives have unit tests with >90% coverage", status: "pending" }
  - { id: "SC-9.2", description: "All planning surfaces have component tests with >80% coverage", status: "pending" }
  - { id: "SC-9.3", description: "OQ resolution integration tests pass (backend + frontend)", status: "pending" }
  - { id: "SC-9.4", description: "E2E critical journeys pass (all 7 scenarios)", status: "pending" }
  - { id: "SC-9.5", description: "A11y tests pass (0 violations, screen-reader smoke test OK)", status: "pending" }
  - { id: "SC-9.6", description: "All tests pass in CI/CD", status: "pending" }

files_modified: []
---

# ccdash-planning-reskin-v2 - Phase 9: Testing — Unit, Integration, Component

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/ccdash-planning-reskin-v2/phase-9-progress.md \
  -t T9-001 -s completed
```

---

## Phase Overview

**Title**: Testing — Unit, Integration, Component
**Dependencies**: Phase 8 complete (T8-004 — a11y hardened); Phase 7 complete (T7-003 — OQ backend endpoint ready); Phase 6 complete (T6-002 — OQ frontend ready)
**Entry Criteria**: All features complete and a11y hardened
**Exit Criteria**: >80% code coverage, all critical flows tested, OQ write-back integration tested

**Scope Reference**: `docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md#phase-9`

T9-001, T9-003, and T9-005 can start in parallel — T9-001 depends on T8-004, T9-003 depends on T7-003+T6-002, T9-005 depends on T8-004. T9-002 waits for T9-001. T9-004 waits for T9-003.

---

## Task Details

| Task ID | Description | Assigned To | Est | Deps | Status |
|---------|-------------|-------------|-----|------|--------|
| T9-001 | Primitive component unit tests | frontend-developer, testing-specialist | 2 pts | T8-004 | pending |
| T9-002 | Planning surface component tests | frontend-developer, testing-specialist | 2.5 pts | T9-001 | pending |
| T9-003 | OQ resolution integration test | python-backend-engineer, frontend-developer | 2 pts | T7-003, T6-002 | pending |
| T9-004 | E2E critical journeys | testing-specialist | 2 pts | T9-003 | pending |
| T9-005 | A11y automated + manual tests | web-accessibility-checker, testing-specialist | 1.5 pts | T8-004 | pending |

---

## Quick Reference

### Batch 1 — After T8-004 (Phase 8) and T7-003 (Phase 7) and T6-002 (Phase 6) complete; run in parallel
```
Task("frontend-developer", "T9-001: Vitest unit tests for all Planning primitives: StatusPill (all 11 status values), ArtifactChip (all 8 types), MetricTile, Spark, ExecBtn, PhaseDot, PhaseStackInline, TotalsCell, DocChip, Dot, Chip, Panel, Tile. Each test: render, props, basic interaction. Target >90% coverage.")
Task("python-backend-engineer", "T9-003: Backend integration test for PATCH /api/planning/features/{id}/open-questions/{oq_id}: (1) seed test feature with OQ, (2) call endpoint with answer text, (3) verify 200 with resolved OQ state, (4) verify OTEL span exported. Frontend integration test: mock API, render OQ editor, Cmd+Enter, verify UI update. Target >85% coverage.")
Task("web-accessibility-checker", "T9-005: Run axe-core (Vitest plugin) on all planning surfaces. Target 0 violations. Manual smoke test: screen reader (NVDA on Windows or VoiceOver on Mac) for feature title and key interactive elements in planning graph and detail drawer. Document any false positives.")
```

### Batch 2 — After T9-001 completes
```
Task("frontend-developer", "T9-002: Component tests (React Testing Library) for: PlanningHomePage (metrics render, chip navigation), PlanningGraphPanel (rows/lanes/edges render), PlanningNodeDetail (drawer open/close, lineage tiles), TriagePanel (tab switching, row actions), AgentRoster (rows, state dot colors). Mock all API calls. Target >80% coverage.")
```

### Batch 3 — After T9-003 completes
```
Task("testing-specialist", "T9-004: E2E tests (Playwright) for 7 critical journeys: (1) open planning home, (2) click graph row, (3) drawer opens with lineage, (4) resolve OQ inline, (5) switch to DAG view, (6) click exec button, (7) toast appears and auto-dismisses. Capture screenshots for visual regression if enabled.")
```

---

## Quality Gates

- [ ] All primitives have unit tests with >90% coverage
- [ ] All planning surfaces have component tests with >80% coverage
- [ ] OQ resolution integration tests pass (backend + frontend)
- [ ] E2E critical journeys pass (7 scenarios)
- [ ] A11y tests pass (0 violations, screen-reader smoke test OK)
- [ ] All tests pass in CI/CD

---

## Status Updates

<!-- Agents: append timestamped notes here as work progresses -->
