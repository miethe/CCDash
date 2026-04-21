---
type: progress
schema_version: 2
doc_type: progress
prd: ccdash-planning-reskin-v2
feature_slug: ccdash-planning-reskin-v2
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-planning-reskin-v2.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md
phase: 6
title: Feature Detail Drawer — SPIKEs, OQ, DAG, Exec Buttons
status: completed
created: 2026-04-20
updated: '2026-04-21'
started: null
completed: '2026-04-21'
commit_refs:
- 75642d7
pr_refs: []
overall_progress: 100
completion_estimate: on-track
total_tasks: 6
completed_tasks: 6
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- ui-engineer-enhanced
- frontend-developer
contributors: []
model_usage:
  primary: sonnet
  external: []
tasks:
- id: T6-001
  description: 'Render collapsible SPIKEs + OQ section (spec color border); two-column
    grid: SPIKE tiles (ID, title, status, hover-reveal ExecBtn) and OQ tiles (severity
    bar, ID, question, answer button)'
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  - frontend-developer
  dependencies:
  - T5-003
  estimated_effort: 2 pts
  priority: high
  assigned_model: sonnet
- id: T6-002
  description: 'OQ inline resolution editor: textarea opens on answer button click,
    Cmd+Enter fires PATCH /api/planning/features/:id/open-questions/:oq_id, success
    marks OQ resolved with ok background, error shows toast'
  status: completed
  assigned_to:
  - frontend-developer
  - ui-engineer-enhanced
  dependencies:
  - T6-001
  estimated_effort: 2 pts
  priority: high
  assigned_model: sonnet
- id: T6-003
  description: 'Render ModelLegend strip with opus/sonnet/haiku color dots, labels,
    token counts per model, totals right-aligned. Data source: server-provided feature.tokenUsageByModel
    from T7-004 — actual session-forensics tokens, not client-side estimates'
  status: completed
  assigned_to:
  - frontend-developer
  - ui-engineer-enhanced
  dependencies:
  - T6-002
  - T7-004
  estimated_effort: 1.5 pts
  priority: medium
  assigned_model: sonnet
- id: T6-004
  description: 'Render execution tasks section with Batches/DAG segment control; Batches
    view: ModelLegend strip, PhaseCards with per-batch BatchCol and per-task TaskRow
    (ID, title, agent chip, token display, status pill, hover-reveal ExecBtn)'
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  - frontend-developer
  dependencies:
  - T6-003
  estimated_effort: 3 pts
  priority: high
  assigned_model: sonnet
- id: T6-005
  description: 'Render DAG SVG view: nodes by phase (horizontal bands) and batch (columns),
    cubic bezier edges with arrowheads, animated active edges, blocked edges red,
    legend for edge states'
  status: completed
  assigned_to:
  - ui-engineer-enhanced
  dependencies:
  - T6-004
  estimated_effort: 3 pts
  priority: high
  assigned_model: sonnet
- id: T6-006
  description: 'Wire all exec buttons (per-phase/batch/task/SPIKE) to dispatch exec
    toast; toast: bottom-center fixed, label with brand dot, auto-dismisses 2.4s;
    actual execution stubbed (DEFER-02)'
  status: completed
  assigned_to:
  - frontend-developer
  - ui-engineer-enhanced
  dependencies:
  - T6-005
  estimated_effort: 1.5 pts
  priority: medium
  assigned_model: sonnet
parallelization:
  batch_1:
  - T6-001
  batch_2:
  - T6-002
  batch_3:
  - T6-003
  batch_4:
  - T6-004
  batch_5:
  - T6-005
  batch_6:
  - T6-006
  critical_path:
  - T6-001
  - T6-002
  - T6-003
  - T6-004
  - T6-005
  - T6-006
  estimated_total_time: 5-6 days
blockers: []
success_criteria:
- id: SC-6.1
  description: SPIKEs and OQ sections render correctly with correct borders and counts
  status: completed
- id: SC-6.2
  description: OQ inline editor functional (Cmd+Enter saves, Escape cancels)
  status: completed
- id: SC-6.3
  description: OQ resolution fires PATCH and updates UI on success
  status: completed
- id: SC-6.4
  description: ModelLegend accurate with per-model token counts sourced from server-provided
    feature.tokenUsageByModel (session-forensics actuals, not estimates)
  status: completed
- id: SC-6.5
  description: Batches view complete with all PhaseCard/BatchCol/TaskRow layers
  status: completed
- id: SC-6.6
  description: DAG view renders SVG correctly with phase bands and batch columns
  status: completed
- id: SC-6.7
  description: Exec buttons show toast within 50ms
  status: completed
- id: SC-6.8
  description: Toast auto-dismisses after 2.4s
  status: completed
files_modified:
- components/Planning/PlanningNodeDetail.tsx
- services/planning.ts
- components/Planning/__tests__/PlanningNodeDetail.test.tsx
- .claude/progress/ccdash-planning-reskin-v2/phase-6-progress.md
progress: 100
---

# ccdash-planning-reskin-v2 - Phase 6: Feature Detail Drawer — SPIKEs, OQ, DAG, Exec Buttons

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/ccdash-planning-reskin-v2/phase-6-progress.md \
  -t T6-001 -s completed
```

---

## Phase Overview

**Title**: Feature Detail Drawer — SPIKEs, OQ, DAG, Exec Buttons
**Dependencies**: Phase 5 complete (T5-003 — drawer shell and lineage complete); Phase 7 (backend OQ endpoint) can proceed in parallel
**Entry Criteria**: Drawer shell and lineage complete
**Exit Criteria**: All drawer sections complete; exec buttons wired to toast; user can resolve OQs inline

**Scope Reference**: `docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md#phase-6`

Note: T6-002 fires `PATCH /api/planning/features/:id/open-questions/:oq_id` — Phase 7 must be complete before the OQ resolution integration test passes (T9-003), but T6-002 can be developed against a mocked endpoint. Tasks in this phase are sequential due to data dependencies.

---

## Task Details

| Task ID | Description | Assigned To | Est | Deps | Status |
|---------|-------------|-------------|-----|------|--------|
| T6-001 | SPIKEs + OQ section | ui-engineer-enhanced, frontend-developer | 2 pts | T5-003 | completed |
| T6-002 | OQ inline resolution editor | frontend-developer, ui-engineer-enhanced | 2 pts | T6-001 | completed |
| T6-003 | ModelLegend strip (server-provided actuals) | frontend-developer, ui-engineer-enhanced | 1.5 pts | T6-002, T7-004 | completed |
| T6-004 | Execution tasks section — batches view | ui-engineer-enhanced, frontend-developer | 3 pts | T6-003 | completed |
| T6-005 | Dependency DAG SVG view | ui-engineer-enhanced | 3 pts | T6-004 | completed |
| T6-006 | Exec buttons and toast | frontend-developer, ui-engineer-enhanced | 1.5 pts | T6-005 | completed |

---

## Quick Reference

### Batch 1 — After T5-003 (Phase 5) completes
```
Task("ui-engineer-enhanced", "T6-001: Render collapsible section (spec color left border, eyebrow, bold title, chevron, count). Two-column grid: SPIKE tiles (SPIKE ID, title, status pill, hover-reveal ExecBtn) and OQ tiles (severity bar, OQ ID, question text, '+ answer...' button). Section renders with color-coded border. Ref: docs/project_plans/designs/ccdash-planning/project/app/feature_detail.jsx")
```

### Batch 2 — After T6-001 completes
```
Task("frontend-developer", "T6-002: OQ inline resolution editor. Clicking '+ answer...' opens inline textarea. Cmd+Enter fires PATCH /api/planning/features/:id/open-questions/:oq_id with answer text. Pending state shows briefly. On success: OQ marked resolved with ok background, answer text visible. On error: error toast. Escape cancels. Click outside cancels.")
```

### Batch 3 — After T6-002 completes
```
Task("frontend-developer", "T6-003: Render ModelLegend strip: opus color dot + label + token count, sonnet color dot + label + token count, haiku color dot + label + token count, totals (pts + tokens) right-aligned. Data source: server-provided feature.tokenUsageByModel from T7-004 — actuals from session forensics (FeatureForensicsQueryService linked_sessions grouped by modelFamily), not client-side estimates.")
```

### Batch 4 — After T6-003 completes
```
Task("ui-engineer-enhanced", "T6-004: Render collapsible section with segment control 'Batches' / 'Dependency DAG'. In Batches view: ModelLegend strip, then per-PhaseCard list. PhaseCard: phase header (PHASE N, name, status, run-phase ExecBtn, progress bar + % and pts/tokens). Per-batch BatchCol (parallel label, task count, ExecBtn). Per-task TaskRow (task ID, title, agent chip with model color, token display, status pill, hover-reveal ExecBtn).")
```

### Batch 5 — After T6-004 completes
```
Task("ui-engineer-enhanced", "T6-005: DAG view — absolute-positioned SVG canvas. Nodes arranged by phase (horizontal bands) and batch (columns). Cubic bezier edges with arrowheads. Active edges animated (flow dashes, brand color). Blocked edges red. Legend for edge states (active/blocked/static). Render from phase/task/deps data in feature payload — no separate API call.")
```

### Batch 6 — After T6-005 completes
```
Task("frontend-developer", "T6-006: Wire all exec buttons (per-phase, per-batch, per-task, per-SPIKE) to dispatch exec toast. Toast: bottom-center fixed, shows label (e.g., '▶ running Phase 02 — Service layer') with brand color dot, auto-dismisses 2.4s. For v2, toast is client-side only; actual execution stubbed (DEFER-02).")
```

---

## Quality Gates

- [x] SPIKEs and OQ sections render correctly with color-coded borders
- [x] OQ inline editor functional (Cmd+Enter saves, Escape cancels)
- [x] OQ resolution fires PATCH and updates UI on success
- [x] ModelLegend accurate with per-model token counts sourced from server-provided feature.tokenUsageByModel (session-forensics actuals)
- [x] Batches view complete with all card/col/row layers
- [x] DAG view renders SVG with phase bands, batch columns, and correct edges
- [x] Exec buttons show toast within 50ms
- [x] Toast auto-dismisses 2.4s

---

## Status Updates

<!-- Agents: append timestamped notes here as work progresses -->
