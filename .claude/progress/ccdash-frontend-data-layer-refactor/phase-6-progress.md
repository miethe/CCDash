---
schema_version: 2
doc_type: progress
type: progress
prd: ccdash-frontend-data-layer-refactor
feature_slug: ccdash-frontend-data-layer-refactor
phase: 6
title: List Virtualization
status: not_started
created: '2026-05-28'
updated: '2026-05-28'
prd_ref: docs/project_plans/PRDs/refactors/ccdash-frontend-data-layer-refactor-v1.md
plan_ref: docs/project_plans/implementation_plans/refactors/ccdash-frontend-data-layer-refactor-v1.md
commit_refs: []
pr_refs: []
owners:
- ui-engineer-enhanced
contributors: []
execution_model: batch-parallel
started: null
completed: null
overall_progress: 0
completion_estimate: on-track
total_tasks: 5
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
model_usage:
  primary: sonnet
  external: []
tasks:
- id: T6-001
  description: Virtualize session list in SessionInspector.tsx:5856-5901 using useVirtualizer; scroll position preserved on back-nav; 200-item fallback when container height=0; VITE_CCDASH_MEMORY_GUARD_ENABLED interplay preserved
  status: pending
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T2-011
- id: T6-002
  description: Virtualize document list in PlanCatalog.tsx using useVirtualizer; count badge reads total from TQ useDocumentsQuery; MAX_DOCUMENTS_IN_MEMORY=2000 cap via TQ select preserved; same fallback pattern
  status: pending
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T2-011
- id: T6-003
  description: Virtualize legacy feature list in ProjectBoard.tsx using useVirtualizer (up to 5000 entries); v2 surface already paginated 50/page — no change to v2
  status: pending
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T2-011
- id: T6-004
  description: Runtime smoke SessionInspector (>50 sessions), PlanCatalog (>100 docs), ProjectBoard legacy (>50 features); verify smooth scroll, count badges correct, memory guard interplay confirmed
  status: pending
  assigned_to:
  - ui-engineer-enhanced
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T6-003
- id: T6-005
  description: task-completion-validator gate (P6)
  status: pending
  assigned_to:
  - task-completion-validator
  assigned_model: sonnet
  model_effort: adaptive
  dependencies:
  - T6-004
parallelization:
  batch_1:
  - T6-001
  - T6-002
  - T6-003
  batch_2:
  - T6-004
  batch_3:
  - T6-005
  critical_path:
  - T6-001
  - T6-004
  - T6-005
blockers: []
success_criteria:
- id: SC-6.1
  description: Session list in SessionInspector.tsx:5856-5901 uses useVirtualizer
  status: pending
- id: SC-6.2
  description: Document list in PlanCatalog.tsx uses useVirtualizer; count badge reads total from TQ
  status: pending
- id: SC-6.3
  description: Legacy feature list in ProjectBoard.tsx uses useVirtualizer
  status: pending
- id: SC-6.4
  description: Vitest row-count assertions — DOM row count ≤ overscan*2 + visibleCount
  status: pending
- id: SC-6.5
  description: Scroll position restored on back-nav for session list
  status: pending
- id: SC-6.6
  description: Memory guard interplay — MAX_DOCUMENTS_IN_MEMORY and mergeSessionDetail ring-buffer still enforced
  status: pending
- id: SC-6.7
  description: Runtime smoke all 3 virtualized lists
  status: pending
- id: SC-6.8
  description: task-completion-validator sign-off
  status: pending
files_modified:
- components/SessionInspector.tsx
- components/PlanCatalog.tsx
- components/ProjectBoard.tsx
---

# CCDash Frontend Data Layer Refactor - Phase 6: List Virtualization

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/ccdash-frontend-data-layer-refactor/phase-6-progress.md \
  -t T6-001 -s completed
```

---

## Objective

Virtualize three large list surfaces using `useVirtualizer` from `@tanstack/react-virtual` (already installed). T6-001/T6-002/T6-003 are independent and can run in parallel. P6 starts after P2 complete (domain hooks exist). Pattern to copy: `TranscriptView.tsx:2448`. Preserve memory guard interplay (`VITE_CCDASH_MEMORY_GUARD_ENABLED`).
