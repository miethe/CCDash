---
type: progress
schema_version: 2
doc_type: progress
prd: ccdash-planning-control-plane-v1
feature_slug: ccdash-planning-control-plane-v1
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-planning-control-plane-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-planning-control-plane-v1.md
phase: 5
title: Launch Preparation, Worktrees, and Provider Routing
status: completed
created: '2026-04-17'
updated: '2026-04-17'
started: '2026-04-17'
completed: ''
commit_refs:
- a98738e
- 287fe92
- ccc7e6f
- c18f865
pr_refs: []
overall_progress: 0
completion_estimate: 5-7 days
total_tasks: 5
completed_tasks: 5
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0
owners:
- backend-architect
- python-backend-engineer
- frontend-developer
- ui-engineer-enhanced
contributors:
- ai-agents
tasks:
- id: PCP-501
  description: Add a persisted worktree context model tied to project, feature, phase/batch,
    branch, and run linkage, distinct from cache/clone-oriented repo workspaces.
  status: completed
  assigned_to:
  - backend-architect
  - python-backend-engineer
  dependencies:
  - PCP-201
  estimated_effort: 3 pts
  priority: high
- id: PCP-502
  description: Define launch-preparation payloads that combine plan batch data, provider
    capabilities, model selections, worktree context, and approval requirements.
  status: completed
  assigned_to:
  - backend-architect
  - python-backend-engineer
  dependencies:
  - PCP-501
  - PCP-401
  estimated_effort: 2 pts
  priority: high
- id: PCP-503
  description: Add execution-side endpoints or extensions for worktree-aware launch
    preparation and batch launch initiation.
  status: completed
  assigned_to:
  - python-backend-engineer
  dependencies:
  - PCP-502
  estimated_effort: 3 pts
  priority: high
- id: PCP-504
  description: Build a launch sheet/panel that lets operators review batch context,
    choose provider/model, select or create worktree context, and launch.
  status: completed
  assigned_to:
  - frontend-developer
  - ui-engineer-enhanced
  dependencies:
  - PCP-503
  estimated_effort: 3 pts
  priority: high
- id: PCP-505
  description: Gate advanced launch actions behind provider capability checks and
    rollout flags, keeping unsupported paths clearly disabled.
  status: completed
  assigned_to:
  - python-backend-engineer
  - frontend-developer
  dependencies:
  - PCP-503
  - PCP-504
  estimated_effort: 1 pt
  priority: high
parallelization:
  batch_1:
  - PCP-501
  batch_2:
  - PCP-502
  batch_3:
  - PCP-503
  batch_4:
  - PCP-504
  batch_5:
  - PCP-505
  critical_path:
  - PCP-501
  - PCP-502
  - PCP-503
  - PCP-504
  - PCP-505
  estimated_total_time: 12 pts / 5-7 days
blockers: []
notes:
- Phase 5 is highly sequential because later tasks depend on earlier contracts (worktree
  model -> launch contract -> execution API -> UI -> guardrails). Each batch is committed
  independently per operator instruction.
- Worktree context is deliberately distinct from RepoWorkspaceManager/cache; that
  existing abstraction stays focused on cache/clone for integrations while PCP-501
  introduces plan-driven worktree context records linked to feature/phase/batch/run.
- Launch preparation leverages Phase 4 getPhaseOperations contract (PCP-401) and Phase
  2 planning graph derivation (PCP-201); see services/planning.ts and backend/routers/agent.py
  for the upstream data surface.
progress: 100
---

# Phase 5 Progress: Launch Preparation, Worktrees, and Provider Routing

## Overview

Phase 5 introduces plan-driven launch preparation with worktree context and provider/model awareness. Five sequential tasks build the model, contract, API, UI, and guardrails that take a prepared batch from the planning control plane into an execution-ready state, without bypassing existing connector/orchestration plans.

## Batches

### Batch 1 — PCP-501: Worktree Context Model
Persisted model + migrations + repository for worktree contexts (project/feature/phase/batch/branch/run linkage), distinct from the existing repo workspace cache.

### Batch 2 — PCP-502: Launch Preparation Contract
Pydantic DTOs combining batch plan data, provider capabilities, model selections, worktree context, and approval requirements. Shared between API and UI.

### Batch 3 — PCP-503: Execution API and Provider Wiring
New endpoints (`/api/execution/launch/prepare`, `/api/execution/launch/start`) consuming Phase 4 phase operations + worktree context + provider metadata.

### Batch 4 — PCP-504: Launch Preparation UI
`components/Planning/PlanningLaunchSheet.tsx` + `services/execution.ts` additions; entry point on PhaseOperationsPanel.

### Batch 5 — PCP-505: Local-First Safety and Capability Guardrails
Config flag (`CCDASH_LAUNCH_PREP_ENABLED`) + provider capability checks in prepare/start + disabled-state UI messaging.
