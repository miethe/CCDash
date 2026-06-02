---
type: progress
schema_version: 2
doc_type: progress
prd: ccdash-enterprise-edition-v1
feature_slug: ccdash-enterprise-edition-v1
prd_ref: docs/project_plans/planning/ccdash-enterprise-edition-v1/06-implementation-roadmap.md
plan_ref: docs/project_plans/planning/ccdash-enterprise-edition-v1/07-issue-task-backlog.md
phase: 5
title: Command Center as Multi-Project Control Plane
status: completed
created: '2026-06-01'
updated: '2026-06-01'
commit_refs: []
pr_refs: []
overall_progress: 0
total_tasks: 16
completed_tasks: 16
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners: []
contributors: []
tasks:
- id: T5-001
  ledger_id: P5-001
  title: Runtime capability flag for multi-project command center
  status: completed
  assigned_to:
  - fe-capability-owner
  assigned_model: sonnet
  batch: wave3_fe
  depends_on: []
  estimated_effort: S
  started: 2026-06-02T00:40Z
  completed: 2026-06-02T02:30Z
  evidence:
  - test: planning
  - build: vite-build-green
  verified_by:
  - T5-W3-GATE
- id: T5-002
  ledger_id: P5-002
  title: tokenUsageByModel on Feature + fix PlanningTokenTelemetry.source
  status: completed
  assigned_to:
  - contracts-owner
  assigned_model: sonnet
  batch: wave1_contracts
  depends_on: []
  estimated_effort: M
  started: 2026-06-01T23:20Z
  completed: 2026-06-02T00:30Z
  evidence:
  - test: backend/tests/test_p5_rollup_endpoints.py
  verified_by:
  - T5-W2-GATE
- id: T5-003
  ledger_id: P5-003
  title: Cross-project token/cost + portfolio rollup endpoints
  status: completed
  assigned_to:
  - rollups-owner
  assigned_model: sonnet
  batch: wave2_rollups
  depends_on: []
  estimated_effort: L
  started: 2026-06-01T23:20Z
  completed: 2026-06-02T00:30Z
  evidence:
  - test: backend/tests/test_p5_rollup_endpoints.py
  verified_by:
  - T5-W2-GATE
- id: T5-004
  ledger_id: P5-004
  title: Ranked next-work backlog endpoint
  status: completed
  assigned_to:
  - rollups-owner
  assigned_model: sonnet
  batch: wave2_rollups
  depends_on: []
  estimated_effort: M
  started: 2026-06-01T23:20Z
  completed: 2026-06-02T00:30Z
  evidence:
  - test: backend/tests/test_p5_rollup_endpoints.py
  verified_by:
  - T5-W2-GATE
- id: T5-005
  ledger_id: P5-005
  title: Feature.data_json columnar (owners/linkedDocs)
  status: completed
  assigned_to:
  - schema-owner
  assigned_model: sonnet
  batch: wave1_schema
  depends_on: []
  estimated_effort: M
  started: 2026-06-01T22:45Z
  completed: 2026-06-01T23:15Z
  evidence:
  - test: backend/tests/test_phase3_repository_migration.py
  verified_by:
  - T5-W1-GATE
- id: T5-006
  ledger_id: P5-006
  title: Deep-link /planning/feature/:id + lazy per-tab shell
  status: completed
  assigned_to:
  - fe-detail-owner
  assigned_model: sonnet
  batch: wave3_fe
  depends_on:
  - T5-001
  estimated_effort: M
  started: 2026-06-02T00:40Z
  completed: 2026-06-02T02:30Z
  evidence:
  - test: planningRoutes
  - build: vite-build-green
  verified_by:
  - T5-W3-GATE
- id: T5-007
  ledger_id: P5-007
  title: SkillMeat Artifacts tab
  status: completed
  assigned_to:
  - fe-detail-owner
  assigned_model: sonnet
  batch: wave3_fe
  depends_on:
  - T5-006
  estimated_effort: M
  started: 2026-06-02T00:40Z
  completed: 2026-06-02T02:30Z
  evidence:
  - test: planningRoutes
  - build: vite-build-green
  verified_by:
  - T5-W3-GATE
- id: T5-008
  ledger_id: P5-008
  title: Live PR status (cached, fail-soft, capability-gated)
  status: completed
  assigned_to:
  - scaffolds-owner
  assigned_model: sonnet
  batch: wave2_scaffolds
  depends_on: []
  estimated_effort: M
  started: 2026-06-01T23:20Z
  completed: 2026-06-02T00:30Z
  evidence:
  - test: backend/tests/test_p5_scaffolds.py
  verified_by:
  - T5-W2-GATE
- id: T5-009
  ledger_id: P5-009
  title: Cmd-K command palette
  status: completed
  assigned_to:
  - ux-owner
  assigned_model: sonnet
  batch: wave4_ux
  depends_on:
  - T5-001
  estimated_effort: M
  started: 2026-06-02T02:35Z
  completed: 2026-06-02T03:10Z
  evidence:
  - build: vite-build-green
  verified_by:
  - T5-W4-GATE
- id: T5-010
  ledger_id: P5-010
  title: New Spec creation workflow
  status: completed
  assigned_to:
  - ux-owner
  assigned_model: sonnet
  batch: wave4_ux
  depends_on: []
  estimated_effort: M
  started: 2026-06-02T02:35Z
  completed: 2026-06-02T03:10Z
  evidence:
  - test: backend/tests/test_p5_spec_create.py
  verified_by:
  - T5-W4-GATE
- id: T5-011
  ledger_id: P5-011
  title: Replace synthesized sparkline + tokens-saved fictions
  status: completed
  assigned_to:
  - fe-home-owner
  assigned_model: sonnet
  batch: wave3_fe
  depends_on:
  - T5-003
  estimated_effort: S
  started: 2026-06-02T00:40Z
  completed: 2026-06-02T02:30Z
  evidence:
  - test: planningHomePage.behavior
  - build: vite-build-green
  verified_by:
  - T5-W3-GATE
- id: T5-012
  ledger_id: P5-012
  title: ARC council scaffold (capability-gated empty-state)
  status: completed
  assigned_to:
  - scaffolds-owner
  assigned_model: sonnet
  batch: wave2_scaffolds
  depends_on: []
  estimated_effort: S
  started: 2026-06-01T23:20Z
  completed: 2026-06-02T00:30Z
  evidence:
  - test: backend/tests/test_p5_scaffolds.py
  verified_by:
  - T5-W2-GATE
- id: T5-013
  ledger_id: P5-013
  title: MeatyWiki research scaffold (capability-gated)
  status: completed
  assigned_to:
  - scaffolds-owner
  assigned_model: sonnet
  batch: wave2_scaffolds
  depends_on: []
  estimated_effort: S
  started: 2026-06-01T23:20Z
  completed: 2026-06-02T00:30Z
  evidence:
  - test: backend/tests/test_p5_scaffolds.py
  verified_by:
  - T5-W2-GATE
- id: T5-014
  ledger_id: P5-014
  title: PlanningSummaryPanel attention click-through beyond ROW_LIMIT=8
  status: completed
  assigned_to:
  - fe-home-owner
  assigned_model: sonnet
  batch: wave3_fe
  depends_on: []
  estimated_effort: S
  started: 2026-06-02T00:40Z
  completed: 2026-06-02T02:30Z
  evidence:
  - test: PlanningSummaryPanel
  - build: vite-build-green
  verified_by:
  - T5-W3-GATE
- id: T5-015
  ledger_id: P5-015
  title: Emit ArtifactVersionOutcomePayload
  status: completed
  assigned_to:
  - telemetry-owner
  assigned_model: sonnet
  batch: wave2_telemetry
  depends_on: []
  estimated_effort: M
  started: 2026-06-01T23:20Z
  completed: 2026-06-02T00:30Z
  evidence:
  - test: backend/tests/test_workflow_effectiveness.py
  verified_by:
  - T5-W2-GATE
- id: T5-016
  ledger_id: P5-016
  title: SSE invalidation → session board + command center
  status: completed
  assigned_to:
  - fe-home-owner
  assigned_model: sonnet
  batch: wave3_fe
  depends_on:
  - T5-001
  estimated_effort: M
  started: 2026-06-02T00:40Z
  completed: 2026-06-02T02:30Z
  evidence:
  - test: planningHomePage.behavior
  - build: vite-build-green
  verified_by:
  - T5-W3-GATE
parallelization:
  wave1_schema:
  - T5-005
  wave1_contracts:
  - T5-002
  wave2_rollups:
  - T5-003
  - T5-004
  wave2_scaffolds:
  - T5-008
  - T5-012
  - T5-013
  wave2_telemetry:
  - T5-015
  wave3_fe:
  - T5-001
  - T5-006
  - T5-007
  - T5-011
  - T5-014
  - T5-016
  wave4_ux:
  - T5-009
  - T5-010
  critical_path: []
  estimated_total_time: 8-12 days
execution_model: wave-parallel
blockers: []
success_criteria: []
notes: ''
progress: 100
runtime_smoke: ''
merge_commit: ''
merge_branch: ''
---

# Phase 5 — Command Center as Multi-Project Control Plane

Progress file for CCDash Enterprise Edition v1, Phase 5.

## Summary

Expands the command center into a true multi-project control plane by adding cross-project token/cost
rollups, artifact intelligence, and capability-gated scaffolds (ARC council, MeatyWiki). Introduces
the feature deep-link experience with lazy per-tab shell, command palette, and live PR status. Emits
artifact outcome telemetry and replaces synthesized metrics with real data.

## Wave Execution Model

| Wave | Tasks | Focus |
|------|-------|-------|
| wave1_schema | T5-005 | Database schema: Feature.data_json columnar support |
| wave1_contracts | T5-002 | Type contracts: tokenUsageByModel + PlanningTokenTelemetry |
| wave2_rollups | T5-003, T5-004 | Backend: cross-project rollups + ranked backlog |
| wave2_scaffolds | T5-008, T5-012, T5-013 | Backend: PR status, ARC/MeatyWiki empty-states |
| wave2_telemetry | T5-015 | Backend: artifact outcome payload emission |
| wave3_fe | T5-001, T5-006, T5-007, T5-011, T5-014, T5-016 | Frontend: capability flag, feature detail, artifacts tab, real metrics, SSE |
| wave4_ux | T5-009, T5-010 | UX: command palette, spec creation |

## Key Dependencies

| Foundation | Downstream |
|-----------|-----------|
| T5-001 (capability flag) | T5-006, T5-009, T5-016 |
| T5-003 (token rollups) | T5-011 |
| T5-006 (feature deep-link) | T5-007 |
