---
doc_type: implementation_plan
status: draft
category: enhancements

title: "Implementation Plan: Feature Execution Workbench Phase 2 - Local Terminal Execution"
description: "Implement secure in-app local command execution with policy checks, approvals, streaming output, cancellation, and audit history."
author: codex
audience: [ai-agents, developers, engineering-leads, security]
created: 2026-02-27
updated: 2026-02-27

tags: [implementation, execution, terminal, policy, audit, backend, frontend]
feature_slug: feature-execution-workbench-phase-2-local-terminal-v1
feature_family: feature-execution-workbench
lineage_family: feature-execution-workbench
lineage_parent: docs/project_plans/implementation_plans/enhancements/feature-execution-workbench-v1.md
lineage_children: []
lineage_type: phase
linked_features: [feature-execution-workbench-v1]
prd: docs/project_plans/PRDs/enhancements/feature-execution-workbench-phase-2-local-terminal-v1.md
prd_ref: docs/project_plans/PRDs/enhancements/feature-execution-workbench-phase-2-local-terminal-v1.md
related:
  - components/FeatureExecutionWorkbench.tsx
  - services/execution.ts
  - backend/routers/features.py
  - backend/services/feature_execution.py
  - backend/models.py
  - backend/db/sqlite_migrations.py
  - backend/db/postgres_migrations.py
plan_ref: feature-execution-workbench-phase-2-local-terminal-v1
linked_sessions: []

request_log_id: ""
commits: []
prs: []
owner: platform-engineering
owners: [platform-engineering, security-engineering]
contributors: [ai-agents]

complexity: High
track: Phase 2
timeline_estimate: "2-3 weeks across 7 phases"
---

# Implementation Plan: Feature Execution Workbench Phase 2 - Local Terminal Execution

## Objective

Add controlled local command execution inside CCDash Execution Workbench, including:

1. Policy evaluation before launch.
2. Approval gating for risky commands.
3. Live output streaming/polling.
4. Cancel/retry controls.
5. Durable, auditable execution history linked to feature and recommendation rule.

## Current Baseline

Existing V1 baseline already provides:

1. `/execution` page (`components/FeatureExecutionWorkbench.tsx`).
2. Recommendation retrieval (`GET /api/features/{feature_id}/execution-context`).
3. Recommendation telemetry (`POST /api/features/execution-events`).
4. Execution context models and service (`backend/models.py`, `backend/services/feature_execution.py`).

Phase 2 extends this baseline from recommendation-only to in-app run execution.

## Scope and Fixed Decisions

1. Initial runtime provider is local process execution only.
2. Streaming transport in Phase 2 uses polling-friendly event retrieval API; websockets are optional later.
3. All runs are scoped to active project workspace boundaries.
4. No anonymous/rule-bypass command execution path.
5. Risky commands require explicit approval prior to process start.

## Architecture

## 1) Data Model and Migrations

Add execution persistence tables in both:

1. `backend/db/sqlite_migrations.py`
2. `backend/db/postgres_migrations.py`

Proposed tables:

1. `execution_runs`
   - `id`, `project_id`, `feature_id`
   - `provider` (`local`)
   - `source_command`, `normalized_command`
   - `cwd`, `env_profile`
   - `recommendation_rule_id`
   - `risk_level`, `policy_verdict`, `requires_approval`
   - `approved_by`, `approved_at`
   - `status`, `exit_code`
   - `started_at`, `ended_at`, `created_at`, `updated_at`
   - `metadata_json`
2. `execution_run_events`
   - `id`, `run_id`, `sequence_no`
   - `stream` (`stdout`, `stderr`, `system`)
   - `event_type` (`output`, `status`, `policy`, `approval`, `error`)
   - `payload_text`, `payload_json`
   - `occurred_at`
3. `execution_approvals`
   - `id`, `run_id`, `decision`, `reason`
   - `requested_at`, `resolved_at`
   - `requested_by`, `resolved_by`

Key indexes:

1. `execution_runs(project_id, feature_id, created_at DESC)`
2. `execution_runs(project_id, status, updated_at DESC)`
3. `execution_run_events(run_id, sequence_no)`

## 2) Repository Layer

Add repository contracts and implementations:

1. Protocol in `backend/db/repositories/base.py`.
2. Factory binding in `backend/db/factory.py`.
3. SQLite implementation: `backend/db/repositories/execution.py`.
4. Postgres implementation: `backend/db/repositories/postgres/execution.py`.

Primary repository methods:

1. `create_run`
2. `update_run_status`
3. `append_run_events`
4. `get_run`
5. `list_runs`
6. `list_events_after_sequence`
7. `create_approval`
8. `resolve_approval`

## 3) Policy Service

Add `backend/services/execution_policy.py`:

1. Command tokenization and normalization.
2. Risk classification (`low`, `medium`, `high`).
3. Workspace boundary validation using active project path.
4. Policy verdict output:
   - `allow`
   - `requires_approval`
   - `deny`
5. Structured policy reason codes for UI messaging and audits.

## 4) Runtime Service

Add `backend/services/execution_runtime.py`:

1. Launch process with `asyncio.create_subprocess_exec`.
2. Capture stdout/stderr as event chunks.
3. Maintain in-memory process map for active runs.
4. Support cancel via process termination escalation.
5. Persist final status and exit code.

Design constraint:

1. Runtime logic must not write outside approved `cwd`.

## 5) API Router

Add `backend/routers/execution.py` and register in `backend/main.py`.

Proposed endpoints:

1. `POST /api/execution/runs`
2. `GET /api/execution/runs`
3. `GET /api/execution/runs/{run_id}`
4. `GET /api/execution/runs/{run_id}/events?after_sequence=...`
5. `POST /api/execution/runs/{run_id}/approve`
6. `POST /api/execution/runs/{run_id}/cancel`
7. `POST /api/execution/runs/{run_id}/retry`

Validation:

1. Requires active project.
2. Verifies feature linkage where feature id is provided.
3. Rejects disallowed command patterns with policy reason payload.

## 6) Frontend Integration

Extend:

1. `types.ts` with run models (`ExecutionRun`, `ExecutionRunEvent`, `ExecutionPolicyResult`, `ExecutionApproval`).
2. `services/execution.ts` with run/approve/cancel/retry APIs.
3. `components/FeatureExecutionWorkbench.tsx`:
   - `Run` actions on recommendation cards
   - pre-run review modal
   - approval prompt state
   - live run output panel (polling by event sequence)
   - run history list for selected feature.

Add components:

1. `components/execution/ExecutionRunPanel.tsx`
2. `components/execution/ExecutionApprovalDialog.tsx`
3. `components/execution/ExecutionRunHistory.tsx`

## Phase Breakdown

## Phase 1: Schema and contracts

1. Add migration DDL for run/event/approval tables.
2. Add backend model classes for run payloads.
3. Add repository protocol and both DB implementations.

## Phase 2: Policy engine

1. Implement command normalization and risk classification.
2. Implement allow/approval/deny evaluation.
3. Add policy unit tests and fixture cases.

## Phase 3: Runtime engine

1. Build local process lifecycle manager.
2. Persist output events and status transitions.
3. Implement cancel flow with status reconciliation.

## Phase 4: Execution API

1. Add new execution router endpoints.
2. Register router in backend app.
3. Add endpoint tests for:
   - allowed run
   - denied run
   - approval-required run
   - cancel/retry.

## Phase 5: Workbench UI and run UX

1. Add run action controls in recommendation pane.
2. Add review and approval dialogs.
3. Add output viewer and run history panel.
4. Add copy/export output support.

## Phase 6: Telemetry and audit integration

1. Add telemetry events for run lifecycle actions.
2. Ensure run metadata includes recommendation rule linkage.
3. Add audit validation checks for all state transitions.

## Phase 7: Hardening and rollout

1. Load/perf test output polling.
2. Security review for policy coverage.
3. Staged rollout behind feature flag.

## Testing Plan

## Unit Tests

1. Policy classification and verdict generation.
2. Runtime process state transitions.
3. Event sequence correctness.

## Integration Tests

1. Start -> stream -> succeed flow.
2. Start -> cancel flow.
3. Approval-required flow.
4. Denied command flow.

## UI Tests

1. Run button opens review state.
2. Approval gate blocks launch until resolved.
3. Output panel updates from polling.
4. History panel lists latest runs and statuses.

## Manual QA

1. Execute safe command in valid workspace.
2. Attempt blocked command and verify deny reason.
3. Execute approval-required command and complete approval path.
4. Cancel long-running command and verify final status.

## Risks and Mitigations

1. Risk: command safety gaps.
   - Mitigation: strict policy defaults and approval requirements.
2. Risk: output volume causing UI lag.
   - Mitigation: chunk limits and sequence polling windows.
3. Risk: orphaned processes.
   - Mitigation: watchdog reconciliation and startup recovery scan.

## Acceptance Criteria

1. Recommended command can be launched in-app.
2. Policy verdicts enforce allow/approval/deny behavior.
3. Output and lifecycle states are visible and persisted.
4. Cancel and retry work end-to-end.
5. All runs are auditable and linked to feature/recommendation context.
