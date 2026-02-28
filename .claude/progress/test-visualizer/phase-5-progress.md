---
type: progress
schema_version: 2
doc_type: progress
prd: "test-visualizer"
feature_slug: "test-visualizer"
prd_ref: /docs/project_plans/PRDs/features/test-visualizer-v1.md
plan_ref: /docs/project_plans/implementation_plans/features/test-visualizer-v1/phase-5-core-ui.md
phase: 5
title: "Core UI Components"
status: "planning"
started: "2026-02-28"
completed: null
commit_refs: []
pr_refs: []

overall_progress: 0
completion_estimate: "on-track"

total_tasks: 8
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0

owners: ["ui-engineer-enhanced"]
contributors: ["frontend-developer"]

tasks:
  - id: "TASK-5.1"
    description: "Add all test-related interfaces to types.ts: TestStatus, TestRun, TestDefinition, TestResult, TestDomain, TestFeatureMapping, TestIntegritySignal, DomainHealthRollup, FeatureTestHealth, TestTimelinePoint, FeatureTestTimeline."
    status: "pending"
    assigned_to: ["ui-engineer-enhanced"]
    dependencies: ["phase-3-complete"]
    estimated_effort: "2pt"
    priority: "high"

  - id: "TASK-5.2"
    description: "Implement all 8 API functions in services/testVisualizer.ts. Handle snake_case -> camelCase conversion. Return typed data. Graceful 503 handling (return null/empty). Error thrown on 4xx/5xx except 503."
    status: "pending"
    assigned_to: ["frontend-developer"]
    dependencies: ["TASK-5.1", "phase-3-complete"]
    estimated_effort: "3pt"
    priority: "high"

  - id: "TASK-5.3"
    description: "Implement useTestStatus, useTestRuns, useLiveTestUpdates hooks. Handle loading/error states. Cleanup on unmount. useLiveTestUpdates only polls when enabled=true."
    status: "pending"
    assigned_to: ["ui-engineer-enhanced"]
    dependencies: ["TASK-5.2"]
    estimated_effort: "2pt"
    priority: "high"

  - id: "TASK-5.4"
    description: "Implement TestStatusBadge (all 8 status types, 3 sizes, aria-label) and HealthSummaryBar (stacked horizontal bar: emerald/rose/amber segments)."
    status: "pending"
    assigned_to: ["ui-engineer-enhanced"]
    dependencies: ["TASK-5.1"]
    estimated_effort: "2pt"
    priority: "high"

  - id: "TASK-5.5"
    description: "Implement HealthGauge: circular SVG progress ring. Color scale based on health score. Animated value transitions (300ms)."
    status: "pending"
    assigned_to: ["ui-engineer-enhanced"]
    dependencies: ["TASK-5.4"]
    estimated_effort: "2pt"
    priority: "high"

  - id: "TASK-5.6"
    description: "Implement TestRunCard (run summary with session link and git_sha chip) and IntegrityAlertCard (severity left-border, expandable details_json)."
    status: "pending"
    assigned_to: ["frontend-developer"]
    dependencies: ["TASK-5.4"]
    estimated_effort: "2pt"
    priority: "high"

  - id: "TASK-5.7"
    description: "Implement TestResultTable: sortable/filterable results table, expandable rows for full error_message, loading skeleton (5 rows), empty state."
    status: "pending"
    assigned_to: ["ui-engineer-enhanced"]
    dependencies: ["TASK-5.4"]
    estimated_effort: "3pt"
    priority: "high"

  - id: "TASK-5.8"
    description: "Implement DomainTreeView: recursive collapsible tree, health badge per node, keyboard navigation (arrows + Enter + Escape), indigo highlight for selected node."
    status: "pending"
    assigned_to: ["ui-engineer-enhanced"]
    dependencies: ["TASK-5.4"]
    estimated_effort: "2pt"
    priority: "high"

parallelization:
  batch_1: ["TASK-5.1"]
  batch_2: ["TASK-5.2", "TASK-5.4"]
  batch_3: ["TASK-5.3", "TASK-5.5", "TASK-5.6", "TASK-5.7", "TASK-5.8"]
  critical_path: ["TASK-5.1", "TASK-5.2", "TASK-5.4", "TASK-5.7"]
  estimated_total_time: "18pt / ~1.5 weeks"

blockers:
  - "Requires Phase 3 complete (all API endpoints functional)"
  - "Requires Phase 4 complete (design specs for all components)"

success_criteria:
  - "All TypeScript types compile without errors (npx tsc --noEmit)"
  - "No any types in types.ts additions or component props"
  - "All 8 API service functions return correctly typed data"
  - "Service gracefully returns empty/null on 503"
  - "All 8 components render without errors in isolation"
  - "TestStatusBadge renders all 8 status types correctly"
  - "DomainTreeView keyboard navigation works: arrow keys + Enter"
  - "TestResultTable loading skeleton shows during fetch"
  - "HealthGauge animates smoothly on value change"
  - "useLiveTestUpdates cleans up polling interval on unmount (no memory leaks)"

files_modified:
  - "types.ts"
  - "services/testVisualizer.ts"
  - "components/TestVisualizer/TestStatusBadge.tsx"
  - "components/TestVisualizer/HealthGauge.tsx"
  - "components/TestVisualizer/HealthSummaryBar.tsx"
  - "components/TestVisualizer/TestRunCard.tsx"
  - "components/TestVisualizer/TestResultTable.tsx"
  - "components/TestVisualizer/DomainTreeView.tsx"
  - "components/TestVisualizer/IntegrityAlertCard.tsx"
  - "components/TestVisualizer/TestTimeline.tsx"
  - "components/TestVisualizer/TestStatusView.tsx"
  - "components/TestVisualizer/index.ts"
---

# test-visualizer - Phase 5: Core UI Components

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

Use CLI to update progress:

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py -f .claude/progress/test-visualizer/phase-5-progress.md -t TASK-5.X -s completed
```

---

## Objective

Build all shared frontend infrastructure: TypeScript types, API service layer (services/testVisualizer.ts), 8 reusable React components, and 3 custom hooks. All components live in components/TestVisualizer/ and are designed for reuse across the Testing Page, Feature Modal, Execution Page, and Session Page tabs.

---

## Orchestration Quick Reference

### Batch Execution Commands

```bash
# Batch 1 (types foundation)
Task("ui-engineer-enhanced", "Execute TASK-5.1: Add all test-related TypeScript interfaces to types.ts")

# Batch 2 (parallel after TASK-5.1)
Task("frontend-developer", "Execute TASK-5.2: Implement all 8 API functions in services/testVisualizer.ts with snake_case->camelCase conversion")
Task("ui-engineer-enhanced", "Execute TASK-5.4: Implement TestStatusBadge and HealthSummaryBar components")

# Batch 3 (parallel after TASK-5.2 and TASK-5.4)
Task("ui-engineer-enhanced", "Execute TASK-5.3: Implement useTestStatus, useTestRuns, useLiveTestUpdates hooks")
Task("ui-engineer-enhanced", "Execute TASK-5.5: Implement HealthGauge circular SVG progress ring with animation")
Task("frontend-developer", "Execute TASK-5.6: Implement TestRunCard and IntegrityAlertCard components")
Task("ui-engineer-enhanced", "Execute TASK-5.7: Implement TestResultTable with sort, filter, expandable rows, skeleton")
Task("ui-engineer-enhanced", "Execute TASK-5.8: Implement DomainTreeView with recursive tree and keyboard navigation")
```

---

## Implementation Notes

_To be filled during implementation._

---

## Completion Notes

_To be filled when phase completes._
