---
doc_type: implementation_plan
status: draft
category: enhancements

title: "Implementation Plan: Feature Execution Workbench Phase 3 - Platform Connectors"
description: "Implement adapter-based platform connectors with unified dispatch, state normalization, reconciliation, and credential handling."
author: codex
audience: [ai-agents, developers, engineering-leads, platform-engineering]
created: 2026-02-27
updated: 2026-02-27

tags: [implementation, connectors, adapters, execution, integrations, reconciliation]
feature_slug: feature-execution-workbench-phase-3-platform-connectors-v1
feature_family: feature-execution-workbench
lineage_family: feature-execution-workbench
lineage_parent: docs/project_plans/implementation_plans/enhancements/feature-execution-workbench-phase-2-local-terminal-v1.md
lineage_children: []
lineage_type: phase
linked_features: [feature-execution-workbench-v1]
prd: docs/project_plans/PRDs/enhancements/feature-execution-workbench-phase-3-platform-connectors-v1.md
prd_ref: docs/project_plans/PRDs/enhancements/feature-execution-workbench-phase-3-platform-connectors-v1.md
related:
  - backend/routers/execution.py
  - backend/services/execution_runtime.py
  - backend/models.py
  - components/FeatureExecutionWorkbench.tsx
  - services/execution.ts
  - types.ts
plan_ref: feature-execution-workbench-phase-3-platform-connectors-v1
linked_sessions: []

request_log_id: ""
commits: []
prs: []
owner: platform-engineering
owners: [platform-engineering, integrations]
contributors: [ai-agents]

complexity: High
track: Phase 3
timeline_estimate: "2-3 weeks across 6 phases"
---

# Implementation Plan: Feature Execution Workbench Phase 3 - Platform Connectors

## Objective

Extend Phase 2 local execution into a provider-agnostic connector system so workbench runs can be dispatched to external agentic platforms while preserving CCDash-native run state and audit guarantees.

## Current Baseline

Assumes Phase 2 is complete and provides:

1. Execution run persistence and events.
2. Policy/approval gates.
3. Local runtime provider and run UI.

Phase 3 adds connector abstraction and cross-provider state reconciliation.

## Scope and Fixed Decisions

1. Local provider remains the fallback/default provider.
2. External providers integrate via adapter contract, not provider-specific branching in router/UI.
3. CCDash policy gates are always applied before dispatch.
4. Provider credentials are project-scoped and never emitted in run logs.

## Architecture

## 1) Adapter Contract and Registry

Add adapter abstraction under:

1. `backend/services/execution/adapters/base.py`
2. `backend/services/execution/adapters/local.py` (Phase 2 runtime wrapped as adapter)
3. `backend/services/execution/adapters/<provider>.py` (first external provider)
4. `backend/services/execution/adapter_registry.py`

Contract methods:

1. `validate_config`
2. `dispatch`
3. `poll_status`
4. `cancel`
5. `fetch_logs`
6. `capabilities`

Capabilities model:

1. `supports_streaming`
2. `supports_cancel`
3. `supports_artifacts`
4. `supports_resume`

## 2) Provider Config and Credential Storage

Add storage for provider config and credentials:

1. `execution_provider_configs`
2. `execution_provider_credentials`

Data principles:

1. Config metadata is queryable for UI.
2. Credential payload uses encrypted-at-rest storage.
3. UI receives masked metadata only.

Required migration targets:

1. `backend/db/sqlite_migrations.py`
2. `backend/db/postgres_migrations.py`

## 3) Run State Normalization

Extend run model in `backend/models.py` and execution repository to include:

1. `provider_id`
2. `provider_run_id`
3. `provider_status_raw`
4. `sync_status` (`in_sync`, `stale`, `error`)
5. `last_reconciled_at`

Status mapping service:

1. `backend/services/execution/provider_state_mapper.py`
2. Translate provider-native statuses into canonical CCDash run states.

## 4) Reconciliation Service

Add periodic reconciliation worker:

1. `backend/services/execution/reconciler.py`

Responsibilities:

1. Poll active external runs.
2. Update status/events/artifacts.
3. Mark stale or degraded runs when provider state cannot be confirmed.
4. Expose reconciliation metrics and error counters.

Lifecycle:

1. Startup task registration in `backend/main.py`.
2. Graceful shutdown support.

## 5) API Surface

Extend `backend/routers/execution.py` with connector endpoints:

1. `GET /api/execution/providers`
2. `PUT /api/execution/providers/{provider_id}/config`
3. `POST /api/execution/providers/{provider_id}/credentials`
4. `POST /api/execution/runs` (now accepts `providerId`)
5. `POST /api/execution/runs/{run_id}/reconcile`

Execution routing:

1. Validate provider availability and config health.
2. Fallback to local provider when configured by policy and provider unavailable.

## 6) Frontend Changes

Update:

1. `types.ts` with provider/capability/run-sync types.
2. `services/execution.ts` for provider APIs and provider-aware run launch.
3. `components/FeatureExecutionWorkbench.tsx`:
   - provider selector in execution pane
   - provider capability badges
   - sync status indicators on runs
4. `components/Settings.tsx`:
   - provider configuration and credential status UI.

## Phase Breakdown

## Phase 1: Schema and models

1. Add provider config/credential tables.
2. Extend run schema for provider fields and reconciliation markers.
3. Add models and repository methods.

## Phase 2: Adapter framework

1. Implement adapter base interface and registry.
2. Wrap existing local runtime as adapter.
3. Implement first external provider adapter.

## Phase 3: Provider APIs

1. Add provider config/credential endpoints.
2. Add provider-aware dispatch in run creation.
3. Add manual reconcile endpoint.

## Phase 4: Reconciliation worker

1. Implement periodic polling for external run states.
2. Persist status/log updates.
3. Add stale/degraded state handling.

## Phase 5: Frontend integration

1. Add provider picker and capabilities UI.
2. Add run sync-state badges and refresh actions.
3. Add settings panel for provider health and credentials.

## Phase 6: Hardening and rollout

1. Connector conformance tests and failure injection.
2. Security review of credential handling.
3. Gradual provider rollout behind flags.

## Testing Plan

## Unit Tests

1. Adapter contract compliance tests.
2. Provider state mapping tests.
3. Credential masking/serialization tests.

## Integration Tests

1. Dispatch to local and external providers.
2. Reconcile external state transitions.
3. Cancel behavior when provider supports/does-not-support cancel.
4. Fallback to local path when provider unavailable.

## UI Tests

1. Provider selection persistence.
2. Provider capability and sync-state rendering.
3. Settings credential status flows.

## Operational Tests

1. Simulate provider outage and verify isolation.
2. Simulate reconciliation lag and stale-state recovery.

## Risks and Mitigations

1. Risk: provider API drift.
   - Mitigation: strict adapter conformance tests and capability flags.
2. Risk: credential exposure.
   - Mitigation: encryption + masked responses + no log echo.
3. Risk: inconsistent run state.
   - Mitigation: canonical mapper + reconciliation worker + manual refresh.

## Acceptance Criteria

1. Workbench can dispatch runs to local and at least one external provider.
2. Provider statuses map consistently to CCDash canonical run states.
3. Reconciliation updates state/logs without blocking unrelated providers.
4. Credentials remain hidden in UI/log outputs and pass security review.
5. Users can inspect provider and sync status from run details.
