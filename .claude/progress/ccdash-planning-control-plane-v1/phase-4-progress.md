---
type: progress
schema_version: 2
doc_type: progress
prd: ccdash-planning-control-plane-v1
feature_slug: ccdash-planning-control-plane-v1
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-planning-control-plane-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-planning-control-plane-v1.md
phase: 4
title: Feature Control Plane and Phase Operations Integration
status: in_progress
created: '2026-04-17'
updated: '2026-04-17'
started: '2026-04-17'
completed: null
commit_refs: []
pr_refs: []
overall_progress: 0
completion_estimate: 4-5 days
total_tasks: 4
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
  - frontend-developer
  - ui-engineer-enhanced
  - python-backend-engineer
contributors:
  - ai-agents
tasks:
  - id: PCP-401
    description: Extend execution workbench so feature-level planning hierarchy, batch
      readiness, and mismatch state render in one control-plane view, consuming
      FeaturePlanningContext and PhaseOperations from /api/agent/planning/*.
    status: pending
    assigned_to:
      - frontend-developer
      - python-backend-engineer
    dependencies:
      - PCP-202
      - PCP-303
    estimated_effort: 3 pts
    priority: high
  - id: PCP-402
    description: Add a phase-focused operations panel (workbench Phases tab) that
      shows batches, ownership, blockers, supporting docs, and validation outcomes
      backed by getPhaseOperations.
    status: pending
    assigned_to:
      - ui-engineer-enhanced
      - frontend-developer
    dependencies:
      - PCP-401
    estimated_effort: 3 pts
    priority: high
  - id: PCP-403
    description: Introduce reusable planning-aware primitives (status chips,
      mismatch badge, batch readiness pill, lineage row) under components/Planning/
      primitives so all supporting surfaces share the same semantics.
    status: pending
    assigned_to:
      - ui-engineer-enhanced
    dependencies:
      - PCP-202
    estimated_effort: 2 pts
    priority: high
  - id: PCP-404
    description: Update PlanCatalog, DocumentModal, and ProjectBoard to consume the
      shared planning-aware primitives where high value (lineage, effective status,
      mismatch warnings, planning navigation).
    status: pending
    assigned_to:
      - frontend-developer
    dependencies:
      - PCP-403
    estimated_effort: 2 pts
    priority: high
parallelization:
  batch_1:
    - PCP-403
    - PCP-401
  batch_2:
    - PCP-402
    - PCP-404
  critical_path:
    - PCP-403
    - PCP-401
    - PCP-402
  estimated_total_time: 10 pts / 4-5 days
blockers: []
notes:
  - Phase 2 exposed /api/agent/planning/{summary,graph,features/{id},features/{id}/phases/{n}}
    and services/planning.ts (getFeaturePlanningContext, getPhaseOperations) plus
    featurePlanningTopic for live invalidation; Phase 4 consumes these inside the
    feature control plane surfaces.
  - Phase 3 shipped Planning Home, graph, node detail, and tracker intake which
    reused locally-scoped chips/badges inside components/Planning/*. Phase 4 pulls
    those primitives out into shared components/Planning/primitives/ (PCP-403) so
    feature/catalog/board/modal surfaces render identical semantics.
  - Commits land per batch as requested ("commit in batches").
success_criteria:
  - id: SC-4.1
    description: Execution workbench becomes the feature-level planning control plane
      rather than only a recommendation surface.
    status: pending
  - id: SC-4.2
    description: Phase operations are explainable and actionable from the UI without
      opening raw progress files.
    status: pending
  - id: SC-4.3
    description: Planning-aware semantics stay consistent across feature, catalog,
      board, and modal surfaces via shared primitives.
    status: pending
files_modified: []
progress: 0
---

# ccdash-planning-control-plane-v1 - Phase 4

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

## Objective

Extend the execution workbench into a broader feature control plane, add a phase
operations view, and align plan catalog / document modal / project board with
shared planning-aware primitives. Consume the planning APIs and live topics
shipped in phases 2–3 so operators can reason about feature planning state in
one place.

## Primary Targets

- `components/FeatureExecutionWorkbench.tsx`
- `components/PlanCatalog.tsx`
- `components/DocumentModal.tsx`
- `components/ProjectBoard.tsx`
- `services/execution.ts` (contract touch-ups only; no core rewrite)
- `components/Planning/primitives/` (new shared primitives)

## Out of Scope (Phase 4)

- Launch preparation flows, worktree context, provider/model selection (Phase 5).
- Backend planning API additions beyond small payload adjustments required by
  workbench consumption (Phase 2 already shipped the contracts).
- Rollout telemetry and validation harnesses (Phase 6).

## Quality Gates

- `npm run build` (tsc) passes.
- `npx vitest run` passes (new tests for shared primitives; no regressions).
- `backend/.venv/bin/python -m pytest backend/tests/ -k planning -v` unchanged.
- Commits land in batches per task grouping.
