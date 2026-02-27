---
doc_type: implementation_plan
status: draft
category: enhancements

title: "Implementation Plan: Feature Execution Workbench Phase 4 - SDK Orchestration"
description: "Implement multi-step SDK-based orchestration with checkpoints, approvals, resumability, and artifact lineage."
author: codex
audience: [ai-agents, developers, engineering-leads, platform-engineering, security]
created: 2026-02-27
updated: 2026-02-27

tags: [implementation, sdk, orchestration, workflows, approvals, recovery]
feature_slug: feature-execution-workbench-phase-4-sdk-orchestration-v1
feature_family: feature-execution-workbench
lineage_family: feature-execution-workbench
lineage_parent: docs/project_plans/implementation_plans/enhancements/feature-execution-workbench-phase-3-platform-connectors-v1.md
lineage_children: []
lineage_type: phase
linked_features: [feature-execution-workbench-v1]
prd: docs/project_plans/PRDs/enhancements/feature-execution-workbench-phase-4-sdk-orchestration-v1.md
prd_ref: docs/project_plans/PRDs/enhancements/feature-execution-workbench-phase-4-sdk-orchestration-v1.md
related:
  - backend/routers/execution.py
  - backend/services/execution/adapters
  - backend/models.py
  - components/FeatureExecutionWorkbench.tsx
  - services/execution.ts
  - types.ts
plan_ref: feature-execution-workbench-phase-4-sdk-orchestration-v1
linked_sessions: []

request_log_id: ""
commits: []
prs: []
owner: platform-engineering
owners: [platform-engineering, ai-integrations, security-engineering]
contributors: [ai-agents]

complexity: High
track: Phase 4
timeline_estimate: "2-4 weeks across 7 phases"
---

# Implementation Plan: Feature Execution Workbench Phase 4 - SDK Orchestration

## Objective

Enable orchestration-mode execution in CCDash: multi-step plans combining command and SDK steps with approval checkpoints, resumable execution, and traceable artifact outputs.

## Current Baseline

Assumes Phases 2 and 3 are complete and provide:

1. Run lifecycle and event persistence.
2. Policy/approval framework.
3. Adapter registry and provider reconciliation.

Phase 4 builds a workflow layer above single-run dispatch.

## Scope and Fixed Decisions

1. Initial orchestration supports ordered steps and optional DAG dependencies.
2. Orchestration is bounded to active project and selected feature context.
3. Approval checkpoints are mandatory for risk-classified steps.
4. Resume/retry/skip actions are explicit and audited.
5. Simple single-run UX remains default; orchestration is an opt-in mode.

## Architecture

## 1) Workflow Data Model

Add orchestration tables in both migration targets:

1. `backend/db/sqlite_migrations.py`
2. `backend/db/postgres_migrations.py`

Proposed tables:

1. `execution_workflows`
   - template or generated plan metadata
   - linked feature id
   - author and version metadata
2. `execution_workflow_steps`
   - ordered index
   - step type (`command`, `sdk`, `approval`, `validation`)
   - provider/tool metadata
   - policy/risk metadata
3. `execution_workflow_edges`
   - step dependency graph for DAG paths
4. `execution_workflow_runs`
   - workflow run state
   - current step pointer
   - resume token/checkpoint metadata
5. `execution_step_runs`
   - per-step execution status and timings
   - linked `execution_run_id` for concrete run dispatch
6. `execution_step_artifacts`
   - emitted artifact references and lineage metadata

Indexes:

1. `(project_id, feature_id, created_at DESC)` on workflow runs.
2. `(workflow_run_id, step_index)` on step runs.
3. `(workflow_run_id, sequence_no)` on workflow event stream.

## 2) Orchestration Engine

Add:

1. `backend/services/execution/orchestrator.py`
2. `backend/services/execution/state_machine.py`

Responsibilities:

1. Validate workflow structure.
2. Evaluate dependency readiness.
3. Dispatch step executions through adapter registry.
4. Enforce deterministic state transitions.
5. Pause for approval checkpoints and resume safely.

Canonical workflow states:

1. `queued`
2. `running`
3. `blocked`
4. `paused`
5. `failed`
6. `succeeded`
7. `canceled`

## 3) SDK Adapter Layer

Add SDK-specific adapters under:

1. `backend/services/execution/sdk_adapters/base.py`
2. `backend/services/execution/sdk_adapters/<provider>.py`

Adapter requirements:

1. Start step run with context payload.
2. Stream step events/tool summaries.
3. Return checkpoint/resume handles.
4. Cancel step run.
5. Normalize SDK metadata into standard step records.

## 4) Approval and Policy Integration

Extend policy service to step-level evaluations:

1. `backend/services/execution_policy.py`

Policy integration points:

1. Pre-step execution gate.
2. On-demand approval checkpoint insertion for high-risk steps.
3. Skip/override policy with elevated approval only.

Audit requirements:

1. every approval decision
2. every retry/skip/replan action
3. every transition into/out of blocked state.

## 5) API Surface

Extend `backend/routers/execution.py` with orchestration endpoints:

1. `POST /api/execution/workflows`
2. `GET /api/execution/workflows/{workflow_id}`
3. `POST /api/execution/workflows/{workflow_id}/runs`
4. `GET /api/execution/workflow-runs/{run_id}`
5. `POST /api/execution/workflow-runs/{run_id}/approve`
6. `POST /api/execution/workflow-runs/{run_id}/resume`
7. `POST /api/execution/workflow-runs/{run_id}/cancel`
8. `POST /api/execution/workflow-runs/{run_id}/retry-step`
9. `POST /api/execution/workflow-runs/{run_id}/skip-step`
10. `GET /api/execution/workflow-runs/{run_id}/report`

## 6) Frontend Integration

Update:

1. `types.ts` with workflow/step/run/report types.
2. `services/execution.ts` with orchestration APIs.
3. `components/FeatureExecutionWorkbench.tsx`:
   - orchestration mode toggle
   - step graph/timeline panel
   - checkpoint approval prompts
   - resume/retry/skip controls

Add components:

1. `components/execution/OrchestrationBuilder.tsx`
2. `components/execution/OrchestrationTimeline.tsx`
3. `components/execution/StepApprovalCard.tsx`
4. `components/execution/OrchestrationRunReport.tsx`

## Phase Breakdown

## Phase 1: Schema and model groundwork

1. Add workflow tables and indexes.
2. Add backend and frontend orchestration types.
3. Add repositories for workflow entities.

## Phase 2: Orchestrator and state machine

1. Implement deterministic workflow state machine.
2. Implement dependency resolution for ordered and DAG steps.
3. Add transition and invariant tests.

## Phase 3: SDK step adapters

1. Add SDK adapter interfaces and first provider implementation.
2. Normalize SDK events/tool summaries into step run events.
3. Add adapter contract and compatibility tests.

## Phase 4: Approval and recovery controls

1. Integrate step-level approval checkpoints.
2. Implement resume/retry/skip behaviors with audit trails.
3. Add policy-based override constraints.

## Phase 5: Orchestration APIs

1. Add workflow create/run/read endpoints.
2. Add control endpoints (approve/resume/cancel/retry/skip).
3. Add run report endpoint and report model.

## Phase 6: Workbench orchestration UX

1. Add orchestration mode and plan builder UI.
2. Add step timeline, dependency view, and blocked-state UX.
3. Add report export and artifact lineage navigation.

## Phase 7: Hardening and rollout

1. Failure injection testing for interrupted runs.
2. Resume reliability test suite.
3. Progressive rollout with internal feature flags.

## Testing Plan

## Unit Tests

1. Workflow state transition invariants.
2. Dependency resolution behavior for DAG and ordered flows.
3. Step policy and approval gating behavior.

## Integration Tests

1. End-to-end workflow execution (command + SDK + validation).
2. Approval-blocked run with manual resume.
3. Interrupted workflow restart and resume.
4. Retry and skip paths with audit verification.

## UI Tests

1. Orchestration plan creation and launch.
2. Step timeline updates and status rendering.
3. Checkpoint approval UX and recovery controls.
4. Run report display and deep-link integrity.

## Chaos and Recovery Tests

1. Provider timeout during SDK step.
2. Backend restart during workflow run.
3. Stale external state requiring reconciliation before resume.

## Risks and Mitigations

1. Risk: orchestration complexity overwhelms users.
   - Mitigation: default simple mode and progressive disclosure.
2. Risk: state machine bugs cause deadlocks.
   - Mitigation: strict transition tests and reconciliation tooling.
3. Risk: uncontrolled overrides.
   - Mitigation: elevated approval policy with immutable audit records.

## Acceptance Criteria

1. User can launch a multi-step orchestration from execution workbench.
2. Command and SDK steps execute under unified workflow state tracking.
3. Approval checkpoints correctly block and resume flow.
4. Resume/retry/skip work with full auditability.
5. Step artifacts and run reports are linked to feature context and accessible in UI.
