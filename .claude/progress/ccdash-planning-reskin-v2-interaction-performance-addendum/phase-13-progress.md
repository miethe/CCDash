---
type: progress
schema_version: 2
doc_type: progress
prd: "ccdash-planning-reskin-v2-interaction-performance-addendum"
feature_slug: "ccdash-planning-reskin-v2-interaction-performance-addendum"
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-planning-reskin-v2.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2-interaction-performance-addendum-v1.md
phase: 13
title: "Metrics, Filters, and Density Wiring"
status: "pending"
created: 2026-04-21
updated: 2026-04-21
started: null
completed: null
commit_refs: []
pr_refs: []

overall_progress: 0
completion_estimate: "on-track"

total_tasks: 4
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0

owners: ["ui-engineer-enhanced", "python-backend-engineer"]
contributors: []

model_usage:
  primary: "sonnet"
  external: []

tasks:
  - id: "P13-001"
    description: "Add summary fields for statusCounts, ctxPerPhase, and token telemetry availability."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    assigned_model: "sonnet"
    dependencies: ["P12-001"]
    estimated_effort: "2 pts"
    priority: "high"

  - id: "P13-002"
    description: "Rework metric tiles into status buckets plus health signals."
    status: "pending"
    assigned_to: ["ui-engineer-enhanced"]
    assigned_model: "sonnet"
    dependencies: ["P13-001"]
    estimated_effort: "1.5 pts"
    priority: "high"

  - id: "P13-003"
    description: "Make each metric tile clickable and filter-reflective in route state."
    status: "pending"
    assigned_to: ["ui-engineer-enhanced"]
    assigned_model: "sonnet"
    dependencies: ["P13-002"]
    estimated_effort: "1 pt"
    priority: "medium"

  - id: "P13-004"
    description: "Apply density variables across lists, rows, tracker tabs, graph rows, and roster."
    status: "pending"
    assigned_to: ["ui-engineer-enhanced"]
    assigned_model: "sonnet"
    dependencies: []
    estimated_effort: "1.5 pts"
    priority: "medium"

parallelization:
  batch_1: ["P13-001", "P13-004"]
  batch_2: ["P13-002"]
  batch_3: ["P13-003"]
  critical_path: ["P13-001", "P13-002", "P13-003"]
  estimated_total_time: "2 days"

blockers: []

success_criteria:
  - { id: "SC-13.1", description: "UI consumes real statusCounts, ctxPerPhase, tokenTelemetry fields; no fabricated values remain", status: "pending" }
  - { id: "SC-13.2", description: "Status buckets are mutually exclusive and add to total; health signals labeled as overlays/signals", status: "pending" }
  - { id: "SC-13.3", description: "Clicking a count filters planning lists/graph; filter reflected in route state and clearable", status: "pending" }
  - { id: "SC-13.4", description: "Comfortable vs compact density changes visible consistently across all major planning list/table surfaces", status: "pending" }
  - { id: "SC-13.5", description: "Density covered by component tests", status: "pending" }
  - { id: "SC-13.6", description: "All tests green", status: "pending" }

files_modified: []
---

# ccdash-planning-reskin-v2-interaction-performance-addendum - Phase 13: Metrics, Filters, and Density Wiring

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/ccdash-planning-reskin-v2-interaction-performance-addendum/phase-13-progress.md \
  -t P13-001 -s completed
```

---

## Phase Overview

**Title**: Metrics, Filters, and Density Wiring
**Entry Criteria**: Phase 12 complete. Summary payload includes `statusCounts`, `ctxPerPhase`, token telemetry fields.
**Exit Criteria**: All tasks complete. Metric tiles show real data. Filters clickable and reflected in route state. Density changes visible across surfaces. Tests green.

**Scope Reference**: `docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2-interaction-performance-addendum-v1.md#phase-13`

P13-001 (backend fields) and P13-004 (density) can run in parallel — density wiring is independent of summary payload changes. P13-002 must wait for P13-001's fields to land. P13-003 builds on the reworked tiles from P13-002.

**Key concern**: `PlanningMetricsStrip` currently mixes overlapping status counts. The canonical buckets (`shaping`, `planned`, `active`, `blocked`, `review`, `completed`, `deferred`, `stale_or_mismatched`) must be mutually exclusive. Health signals (`blocked`, `stale`, `mismatch`) should remain visually distinct — they are overlapping annotations, not additive buckets.

---

## Task Details

| Task ID | Description | Assigned To | Model | Est | Deps | Status |
|---------|-------------|-------------|-------|-----|------|--------|
| P13-001 | Add summary fields: statusCounts, ctxPerPhase, token telemetry | python-backend-engineer | sonnet | 2 pts | P12-001 | pending |
| P13-002 | Rework metric tiles: status buckets + health signals | ui-engineer-enhanced | sonnet | 1.5 pts | P13-001 | pending |
| P13-003 | Make metric tiles clickable; filter in route state | ui-engineer-enhanced | sonnet | 1 pt | P13-002 | pending |
| P13-004 | Apply density variables across all planning surfaces | ui-engineer-enhanced | sonnet | 1.5 pts | — | pending |

### P13-001 Acceptance Criteria
`ProjectPlanningSummaryDTO` and `ProjectPlanningSummary` expose: `statusCounts` (mutually exclusive buckets: shaping, planned, active, blocked, review, completed, deferred, staleOrMismatched), `ctxPerPhase` (contextCount, phaseCount, ratio, source — `"backend"` or `"unavailable"`), `tokenTelemetry` (totalTokens or null, byModelFamily, source — `"session_attribution"` or `"unavailable"`). No fabricated/heuristic values. Files: `backend/application/services/agent_queries/planning.py`, `types.ts`.

### P13-002 Acceptance Criteria
`PlanningMetricsStrip` renders two visually distinct zones: (1) status bucket tiles that sum to total features, (2) health signal badges labeled as overlapping indicators. Token-saved and ctx/phase tiles either show real backend values or render an explicit "unavailable" state — no fake percentages. Files: `components/Planning/PlanningMetricsStrip.tsx`.

### P13-003 Acceptance Criteria
Clicking any status bucket tile applies a planning-page filter scoped to that bucket. The active filter is reflected in URL/route state (e.g., `?filter=blocked`). A clear/reset action removes the filter. Feature lists and graph respond to the active filter. Files: `components/Planning/PlanningMetricsStrip.tsx`, `components/Planning/PlanningHomePage.tsx`, `services/planningRoutes.ts`.

### P13-004 Acceptance Criteria
`comfortable` vs `compact` density mode changes are visible in: feature list rows, tracker tabs/rows, graph node rows, and roster rows. Row height, gaps, table padding, and compact metadata density all respond to the CSS variable. Hard-coded padding/gaps/heights in planning row components are replaced with token references. Covered by component-level tests. Files: `components/Planning/PlanningRouteLayout.tsx`, planning row components.

---

## Quick Reference

### Batch 1 — Unblocked; run in parallel
```
Task("python-backend-engineer", "P13-001: Add statusCounts, ctxPerPhase, and tokenTelemetry fields to ProjectPlanningSummaryDTO and ProjectPlanningSummary in backend/application/services/agent_queries/planning.py. statusCounts buckets must be mutually exclusive: shaping/planned/active/blocked/review/completed/deferred/staleOrMismatched. ctxPerPhase and tokenTelemetry use source='unavailable' when data is not derivable. Update types.ts with corresponding TypeScript interfaces.")
Task("ui-engineer-enhanced", "P13-004: Apply density CSS variables across all planning list/table surfaces in components/Planning/. Replace hard-coded padding/gaps/heights in planning row components with token references. comfortable vs compact should produce visible changes in: feature list rows, tracker tabs/rows, graph node rows, roster rows. Add component tests covering density mode switching. Files: components/Planning/PlanningRouteLayout.tsx and all planning row components.")
```

### Batch 2 — After P13-001
```
Task("ui-engineer-enhanced", "P13-002: Rework PlanningMetricsStrip (components/Planning/PlanningMetricsStrip.tsx) to render two zones: (1) mutually exclusive status bucket tiles that sum to total, (2) health signal badges labeled as overlapping indicators. Token-saved and ctx/phase tiles show real backend values or explicit 'unavailable' state — remove all fake/heuristic values. Consume statusCounts, ctxPerPhase, tokenTelemetry from summary payload.")
```

### Batch 3 — After P13-002
```
Task("ui-engineer-enhanced", "P13-003: Make each metric tile in PlanningMetricsStrip clickable. Clicking applies a planning filter scoped to that status bucket. Filter reflected in route state (?filter=<bucket>). Clear action removes filter. Feature lists and graph respond to active filter. Files: components/Planning/PlanningMetricsStrip.tsx, components/Planning/PlanningHomePage.tsx, services/planningRoutes.ts")
```

---

## Quality Gates

- [ ] No fake token-saved or ctx/phase values in PlanningMetricsStrip
- [ ] `statusCounts` buckets are mutually exclusive (verified by backend test)
- [ ] Metric tile clicks apply and clear filters correctly
- [ ] Filter reflected in route state (back/forward preserves filter)
- [ ] Density mode produces visible changes across all major planning surfaces
- [ ] Component tests cover density switching
- [ ] Tests green

---

## Status Updates

<!-- Agents: append timestamped notes here as work progresses -->
