---
type: progress
schema_version: 2
doc_type: progress
prd: "test-visualizer"
feature_slug: "test-visualizer"
prd_ref: /docs/project_plans/PRDs/features/test-visualizer-v1.md
plan_ref: /docs/project_plans/implementation_plans/features/test-visualizer-v1/phase-6-integration.md
phase: 6
title: "Page & Tab Integration"
status: "planning"
started: "2026-02-28"
completed: null
commit_refs: []
pr_refs: []

overall_progress: 0
completion_estimate: "on-track"

total_tasks: 7
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0

owners: ["ui-engineer-enhanced"]
contributors: ["frontend-developer"]

tasks:
  - id: "TASK-6.1"
    description: "Add /tests route to App.tsx. Add 'Testing' NavItem to Layout.tsx using TestTube2 icon, positioned after Execution and before Documents."
    status: "pending"
    assigned_to: ["frontend-developer"]
    dependencies: ["phase-5-complete"]
    estimated_effort: "1pt"
    priority: "high"

  - id: "TASK-6.2"
    description: "Implement components/TestVisualizer/TestingPage.tsx: split layout with DomainTreeView left sidebar and TestStatusView right panel, global health header, breadcrumb navigation, URL-synced selection state."
    status: "pending"
    assigned_to: ["ui-engineer-enhanced"]
    dependencies: ["TASK-6.1"]
    estimated_effort: "4pt"
    priority: "high"

  - id: "TASK-6.3"
    description: "Implement TestFilters component rendering into #sidebar-portal. Status checkboxes, search input, run date filter. Apply filter to TestStatusView. 300ms debounce on search."
    status: "pending"
    assigned_to: ["frontend-developer"]
    dependencies: ["TASK-6.2"]
    estimated_effort: "2pt"
    priority: "medium"

  - id: "TASK-6.4"
    description: "Extend WorkbenchTab type to include 'test-status'. Add to TAB_ITEMS. Add conditional render calling TestStatusView with featureId filter. Derive isSessionActive. Show LIVE badge when active session. 30s poll when live."
    status: "pending"
    assigned_to: ["ui-engineer-enhanced"]
    dependencies: ["phase-5-complete"]
    estimated_effort: "3pt"
    priority: "high"

  - id: "TASK-6.5"
    description: "Extend session tab type to include 'test-status'. Add to tab items. Implement SessionTestStatusView with modified-tests section using isTestFile() helper. Tab renders in SessionInspector."
    status: "pending"
    assigned_to: ["ui-engineer-enhanced"]
    dependencies: ["phase-5-complete"]
    estimated_effort: "3pt"
    priority: "high"

  - id: "TASK-6.6"
    description: "Extend FeatureModalTab type to include 'test-status'. Conditional tab inclusion based on test health data. Implement FeatureModalTestStatus compact view. Fetch test health on modal open."
    status: "pending"
    assigned_to: ["frontend-developer"]
    dependencies: ["phase-5-complete"]
    estimated_effort: "2pt"
    priority: "high"

  - id: "TASK-6.7"
    description: "Add URL search param syncing for TestingPage: ?domainId=, ?featureId=, ?runId=. Deep links work from correlate response links object. Back button restores previous selection."
    status: "pending"
    assigned_to: ["frontend-developer"]
    dependencies: ["TASK-6.2"]
    estimated_effort: "1pt"
    priority: "medium"

parallelization:
  batch_1: ["TASK-6.1", "TASK-6.4", "TASK-6.5", "TASK-6.6"]
  batch_2: ["TASK-6.2"]
  batch_3: ["TASK-6.3", "TASK-6.7"]
  critical_path: ["TASK-6.1", "TASK-6.2", "TASK-6.4"]
  estimated_total_time: "16pt / ~1 week"

blockers:
  - "Requires Phase 5 complete (all core UI components exist and functional)"
  - "Requires Phase 3 complete (all API endpoints functional)"
  - "Requires Phase 4 design specs finalized"

success_criteria:
  - "All 4 entry points render without errors"
  - "/tests route resolves and TestingPage renders"
  - "Domain tree click selects domain and updates detail panel"
  - "TestingPage URL params (?featureId=, ?domainId=) pre-select on load"
  - "Execution Page Test Status tab appears only when feature has test runs"
  - "Session Page Test Status tab shows modified test files correctly"
  - "Feature Modal Test Status tab is hidden when feature has no test data"
  - "Live badge appears and polling starts when session.status === 'running'"
  - "Sidebar filter portal renders filters when on /tests route, disappears on other routes"
  - "No existing functionality broken"

files_modified:
  - "App.tsx"
  - "components/Layout.tsx"
  - "components/TestVisualizer/TestingPage.tsx"
  - "components/FeatureExecutionWorkbench.tsx"
  - "components/SessionInspector.tsx"
  - "components/ProjectBoard.tsx"
  - "components/TestVisualizer/SessionTestStatusView.tsx"
  - "components/TestVisualizer/FeatureModalTestStatus.tsx"
  - "components/TestVisualizer/TestFilters.tsx"
---

# test-visualizer - Phase 6: Page & Tab Integration

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

Use CLI to update progress:

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py -f .claude/progress/test-visualizer/phase-6-progress.md -t TASK-6.X -s completed
```

---

## Objective

Wire Phase 5 components into the four UI entry points: the dedicated Testing Page (/tests), Execution Page "Test Status" tab, Session Page "Test Status" tab, and Feature Modal "Test Status" tab. No new components are built — only composition of Phase 5 work. Adds routing, sidebar nav item, portal-based filters, and live polling for active sessions.

---

## Orchestration Quick Reference

### Batch Execution Commands

```bash
# Batch 1 (parallel — all depend only on Phase 5)
Task("frontend-developer", "Execute TASK-6.1: Add /tests route to App.tsx and Testing NavItem to Layout.tsx")
Task("ui-engineer-enhanced", "Execute TASK-6.4: Add test-status tab to Execution Page WorkbenchTab with live session detection")
Task("ui-engineer-enhanced", "Execute TASK-6.5: Add test-status tab to Session Page with SessionTestStatusView and modified-tests section")
Task("frontend-developer", "Execute TASK-6.6: Add test-status tab to Feature Modal with conditional inclusion based on test health data")

# Batch 2 (after TASK-6.1)
Task("ui-engineer-enhanced", "Execute TASK-6.2: Implement TestingPage.tsx with split layout, breadcrumb, and URL-synced selection state")

# Batch 3 (parallel after TASK-6.2)
Task("frontend-developer", "Execute TASK-6.3: Implement TestFilters sidebar portal component with status/search/date filters")
Task("frontend-developer", "Execute TASK-6.7: Add URL search param syncing for TestingPage deep links")
```

---

## Implementation Notes

_To be filled during implementation._

---

## Completion Notes

_To be filled when phase completes._
