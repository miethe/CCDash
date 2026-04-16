---
type: progress
schema_version: 2
doc_type: progress
prd: ccdash-planning-control-plane-v1
feature_slug: ccdash-planning-control-plane-v1
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-planning-control-plane-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-planning-control-plane-v1.md
phase: 1
title: Planning Graph and Derived State Foundation
status: in_progress
created: '2026-04-16'
updated: '2026-04-16'
started: '2026-04-16'
completed: null
commit_refs: []
pr_refs: []
overall_progress: 0
completion_estimate: on-track
total_tasks: 5
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- backend-architect
- python-backend-engineer
contributors:
- codex
tasks:
- id: PCP-101
  description: Define normalized planning node, edge, phase batch, and mismatch contracts shared across backend and frontend.
  status: pending
  assigned_to:
  - backend-architect
  - python-backend-engineer
  dependencies: []
  estimated_effort: 2 pts
  priority: high
- id: PCP-102
  description: Extend document/progress parsing or aggregation to derive linked planning relationships across design spec, PRD, implementation plan, progress, context, tracker, and reports.
  status: pending
  assigned_to:
  - python-backend-engineer
  dependencies:
  - PCP-101
  estimated_effort: 3 pts
  priority: high
- id: PCP-103
  description: Decide and implement how raw status, effective status, mismatch state, and existing `inferred_complete` compatibility behavior coexist without collapsing provenance.
  status: pending
  assigned_to:
  - backend-architect
  - python-backend-engineer
  dependencies:
  - PCP-101
  estimated_effort: 3 pts
  priority: high
- id: PCP-104
  description: Add service logic that computes raw status, effective status, mismatch state, and evidence for planning entities and phases.
  status: pending
  assigned_to:
  - python-backend-engineer
  - backend-architect
  dependencies:
  - PCP-103
  estimated_effort: 2 pts
  priority: high
- id: PCP-105
  description: Derive phase task batches, ownership, file-scope hints, parallelization groups, and readiness state from progress frontmatter.
  status: pending
  assigned_to:
  - python-backend-engineer
  dependencies:
  - PCP-102
  - PCP-104
  estimated_effort: 2 pts
  priority: high
parallelization:
  batch_1:
  - PCP-101
  batch_2:
  - PCP-102
  - PCP-103
  batch_3:
  - PCP-104
  batch_4:
  - PCP-105
  critical_path:
  - PCP-101
  - PCP-103
  - PCP-104
  - PCP-105
  estimated_total_time: 12 pts / 4-5 days
blockers: []
success_criteria:
- id: SC-1.1
  description: CCDash can compute a planning graph and phase-batch model from current source artifacts.
  status: pending
- id: SC-1.2
  description: Effective status, raw status, and mismatch/provenance state are represented explicitly with evidence.
  status: pending
- id: SC-1.3
  description: The derived model extends, rather than duplicates, current feature execution and dependency logic.
  status: pending
files_modified:
- docs/project_plans/implementation_plans/enhancements/ccdash-planning-control-plane-v1.md
- .claude/progress/ccdash-planning-control-plane-v1/phase-1-progress.md
---

# ccdash-planning-control-plane-v1 - Phase 1

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

```bash
python /Users/miethe/.codex/skills/artifact-tracking/scripts/update-status.py -f .claude/progress/ccdash-planning-control-plane-v1/phase-1-progress.md -t PCP-10X -s completed
```

## Objective

Build the canonical planning graph, effective status, mismatch state, and phase batch models that all later control-plane surfaces will consume.

## Orchestration Quick Reference

```bash
# Batch 1
Task("backend-architect", "Execute PCP-101: Define normalized planning node, edge, phase batch, and mismatch contracts shared across backend and frontend.")

# Batch 2 (after PCP-101)
Task("python-backend-engineer", "Execute PCP-102: Extend document/progress parsing or aggregation to derive linked planning relationships across design spec, PRD, implementation plan, progress, context, tracker, and reports.")
Task("backend-architect", "Execute PCP-103: Decide and implement how raw status, effective status, mismatch state, and existing inferred_complete compatibility behavior coexist without collapsing provenance.")

# Batch 3 (after PCP-103)
Task("python-backend-engineer", "Execute PCP-104: Add service logic that computes raw status, effective status, mismatch state, and evidence for planning entities and phases.")

# Batch 4 (after PCP-102 and PCP-104)
Task("python-backend-engineer", "Execute PCP-105: Derive phase task batches, ownership, file-scope hints, parallelization groups, and readiness state from progress frontmatter.")
```

## Notes

Phase opened on 2026-04-16. No implementation tasks have been started yet; launch Batch 1 first and keep downstream work aligned to the dependency graph above.
