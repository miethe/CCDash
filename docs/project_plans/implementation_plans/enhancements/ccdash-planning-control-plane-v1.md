---
schema_name: ccdash_document
schema_version: 3
doc_type: implementation_plan
doc_subtype: enhancement_implementation_plan
primary_doc_role: supporting_document
status: draft
category: enhancements
title: "Implementation Plan: CCDash Planning Control Plane V1"
description: "Implement a planning-first control plane in CCDash that unifies planning artifacts, derived status, phase operations, tracker intake, and plan-driven agent-team launch preparation."
summary: "Build a derived planning graph, planning APIs, live planning updates, planning home and drill-down surfaces, and plan-driven launch preparation with worktree and provider/model awareness."
created: 2026-04-16
updated: 2026-04-16
priority: high
risk_level: high
complexity: High
track: Planning / Execution / Orchestration
timeline_estimate: 4-8 weeks across 6 phases
feature_slug: ccdash-planning-control-plane-v1
feature_family: planning-control-plane
feature_version: v1
lineage_family: planning-control-plane
lineage_parent:
  ref: docs/project_plans/design-specs/ccdash-planning-control-plane-architecture.md
  kind: implementation_of
lineage_children: []
lineage_type: enhancement
owner: platform-engineering
owners:
  - platform-engineering
  - fullstack-engineering
  - ai-integrations
contributors:
  - ai-agents
audience:
  - ai-agents
  - developers
  - platform-engineering
  - engineering-leads
tags:
  - implementation
  - planning
  - execution
  - orchestration
  - worktrees
  - workflow
  - frontend
  - backend
prd: docs/project_plans/PRDs/enhancements/ccdash-planning-control-plane-v1.md
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-planning-control-plane-v1.md
related:
  - docs/project_plans/design-specs/ccdash-planning-control-plane-architecture.md
  - docs/project_plans/PRDs/enhancements/ccdash-planning-control-plane-v1.md
  - docs/project_plans/PRDs/enhancements/feature-execution-workbench-future-phases-roadmap-v1.md
  - docs/project_plans/PRDs/enhancements/feature-execution-workbench-phase-3-platform-connectors-v1.md
  - docs/project_plans/PRDs/enhancements/feature-execution-workbench-phase-4-sdk-orchestration-v1.md
  - docs/project_plans/implementation_plans/enhancements/dependency-aware-execution-and-family-views-v1.md
  - docs/project_plans/implementation_plans/enhancements/workflow-registry-and-correlation-v1.md
  - backend/parsers/documents.py
  - backend/parsers/progress.py
  - backend/db/sync_engine.py
  - backend/services/feature_execution.py
  - backend/routers/features.py
  - backend/routers/execution.py
  - backend/routers/live.py
  - components/FeatureExecutionWorkbench.tsx
  - components/PlanCatalog.tsx
  - components/ProjectBoard.tsx
  - components/DocumentModal.tsx
  - services/live/
  - types.ts
plan_ref: ccdash-planning-control-plane-v1
linked_sessions: []
request_log_id: ""
commits: []
prs: []
---

# Implementation Plan: CCDash Planning Control Plane V1

## Objective

Implement a planning-first control plane in CCDash that turns existing frontmatter-driven planning artifacts into a live, explainable, feature-centric operational GUI. The feature should unify planning graph navigation, effective status and mismatch visibility, phase operations, tracker/intake visibility, and plan-driven launch preparation for parallel agent work.

## Current Baseline

The current codebase already provides the main foundations this plan should extend instead of replace:

1. Filesystem-backed document and progress parsing.
2. Cache DB sync and project-scoped entity linking.
3. Feature execution derived-state and recommendation logic.
4. Dependency-aware and family-aware execution state.
5. Workflow registry and workflow intelligence surfaces.
6. Live-update infrastructure for execution and feature state.
7. A staged execution roadmap for local runtime, provider connectors, and SDK orchestration.

What is missing is the control-plane layer that joins those pieces into one planning-native operator experience.

The most important known architecture constraint is that current inferred-completion behavior can write `inferred_complete` back into source artifacts for some feature flows. V1 must explicitly preserve raw status, effective status, and mismatch/provenance in the control-plane model even if compatibility write-through behavior remains elsewhere in the stack.

## Scope and Fixed Decisions

1. V1 remains source-of-truth-compatible with markdown + frontmatter planning artifacts.
2. V1 introduces a derived planning graph and planning-focused APIs; it does not replace source files with a DB-owned planning model.
3. Existing execution workbench and workflow surfaces remain foundational and should be extended, not forked into parallel product concepts.
4. Launch preparation is in scope; fully autonomous orchestration remains bounded by existing policy, provider, and approval controls.
5. Worktree and provider/model awareness must be visible in V1, but advanced git lifecycle automation can remain intentionally narrow.
6. Batch launch UX must not ship ahead of explicit batch and worktree modeling; metadata-only launch dialogs are not acceptable.

## Architecture Overview

### Backend

Introduce a planning control-plane aggregation layer that composes:

1. parsed planning artifacts and feature links
2. effective-status and mismatch derivation
3. dependency and family-state data
4. execution-run and provider capability metadata
5. tracker/intake and validation-warning summaries

This layer should follow the existing service-first pattern: transport-neutral application services first, then router exposure.

### Frontend

Add planning-focused surfaces while reusing existing shell and component patterns:

1. planning home
2. planning graph / detail drill-down
3. phase operations view
4. feature control plane extensions in execution workbench
5. launch preparation surfaces with worktree and provider/model controls

### Storage

Continue to treat source markdown artifacts as canonical.

Persist only derived or operational state in CCDash storage, such as:

1. planning graph projections and indexes when beneficial
2. launch-preparation metadata
3. worktree context records
4. provider health and capability metadata
5. approvals, audits, and run linkage

## Implementation Strategy

### Sequencing Rationale

1. Derive a canonical planning graph and effective-status model first so all UI surfaces can consume one truth.
2. Expose that contract through stable APIs and live-update topics before editing multiple views.
3. Build planning-specific UI shells next, then integrate planning-aware behavior into the feature control plane and other reused surfaces.
4. Add launch preparation and worktree context only after the planning graph and phase model are stable.
5. Keep rollout and hardening last because this feature spans multiple existing surfaces and can create subtle drift if contracts change mid-stream.

### Parallel Work Opportunities

1. Planning graph derivation and API contract modeling can proceed in parallel once the core response model is agreed.
2. Planning home UI and graph/detail UI can develop in parallel using mocked contracts.
3. Feature control plane integration can overlap with tracker/intake surfaces once backend payloads are stable.
4. Launch-preparation UI can begin in parallel with worktree model implementation if provider capability mocks are defined early.

### Critical Path

1. Phase 1 derived planning graph and effective-status service
2. Phase 2 API and live-update contract
3. Phase 3 planning home and graph/detail shells
4. Phase 4 feature and phase operations integration
5. Phase 5 launch preparation, worktree context, and provider/model routing
6. Phase 6 validation, telemetry, and staged rollout

## Phase Overview

| Phase | Title | Effort | Duration | Critical Path | Objective |
|------|-------|--------|----------|---------------|-----------|
| 1 | Planning Graph and Derived State Foundation | 12 pts | 4-5 days | Yes | Build the canonical planning graph, effective status, mismatch state, and phase batch models |
| 2 | Planning APIs and Live Update Contracts | 8 pts | 3-4 days | Yes | Expose stable planning endpoints and stream-first planning invalidation topics |
| 3 | Planning Home, Graph, and Tracker/Intake Surfaces | 10 pts | 4-5 days | Partial | Deliver the new planning-first overview and document/graph drill-down views |
| 4 | Feature Control Plane and Phase Operations Integration | 10 pts | 4-5 days | Yes | Extend execution workbench and related surfaces with planning-aware phase operations |
| 5 | Launch Preparation, Worktrees, and Provider Routing | 12 pts | 5-6 days | Yes | Add plan-driven batch launch preparation with worktree and provider/model awareness |
| 6 | Validation, Telemetry, and Rollout | 6 pts | 2-3 days | Final gate | Harden, validate, instrument, and stage the rollout safely |

**Total**: ~58 story points over 4-8 weeks depending on connector/worktree scope

## Phase 1: Planning Graph and Derived State Foundation

### Objectives

1. Define the canonical derived planning graph and planning-node relationship model.
2. Compute raw status, effective status, mismatch state, and actionable batch readiness from source artifacts.
3. Reuse existing feature/dependency/family services where possible instead of forking duplicate logic.

### Primary Targets

1. `backend/services/feature_execution.py`
2. `backend/parsers/documents.py`
3. `backend/parsers/progress.py`
4. `backend/db/sync_engine.py`
5. `backend/models.py`
6. `types.ts`

### Tasks

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|--------|-----------|-------------|---------------------|----------|-------------|--------------|
| PCP-101 | Planning Graph Contract | Define normalized planning node, edge, phase batch, and mismatch contracts shared across backend and frontend. | Backend and frontend types cover planning graph, effective status, mismatch state, and batch readiness without ambiguous fields. | 2 pts | backend-architect, python-backend-engineer | None |
| PCP-102 | Artifact Relationship Derivation | Extend document/progress parsing or aggregation to derive linked planning relationships across design spec, PRD, implementation plan, progress, context, tracker, and reports. | A planning graph can be assembled from existing source artifacts without body parsing in the UI. | 3 pts | python-backend-engineer | PCP-101 |
| PCP-103 | Status Provenance Strategy | Decide and implement how raw status, effective status, mismatch state, and existing `inferred_complete` compatibility behavior coexist without collapsing provenance. | The backend preserves raw vs effective status explicitly and exposes provenance fields that the UI can render without ambiguity. | 3 pts | backend-architect, python-backend-engineer | PCP-101 |
| PCP-104 | Effective Status and Mismatch Service | Add service logic that computes raw status, effective status, mismatch state, and evidence for planning entities and phases. | Derived status logic is centralized and exposes evidence payloads suitable for UI explanation. | 2 pts | python-backend-engineer, backend-architect | PCP-103 |
| PCP-105 | Phase Batch Readiness Model | Derive phase task batches, ownership, file-scope hints, parallelization groups, and readiness state from progress frontmatter. | Phase payloads preserve `parallelization.batch_N` semantics and identify batch membership, readiness, and blockers using existing progress metadata. | 2 pts | python-backend-engineer | PCP-102, PCP-104 |

### Success Criteria

1. CCDash can compute a planning graph and phase-batch model from current source artifacts.
2. Effective status, raw status, and mismatch/provenance state are represented explicitly with evidence.
3. The derived model extends, rather than duplicates, current feature execution and dependency logic.

## Phase 2: Planning APIs and Live Update Contracts

### Objectives

1. Expose stable planning-focused APIs for summary, graph, feature drill-down, and phase operations.
2. Add planning live-update topics that align with the current SSE infrastructure.
3. Keep the contract transport-neutral so REST, CLI, and MCP can share it later.

### Primary Targets

1. `backend/application/services/agent_queries/`
2. `backend/routers/features.py`
3. `backend/routers/live.py`
4. `backend/application/live_updates/`
5. `services/live/topics.ts`
6. `services/live/useLiveInvalidation.ts`

### Tasks

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|--------|-----------|-------------|---------------------|----------|-------------|--------------|
| PCP-201 | Planning Query Service | Add a transport-neutral planning query layer for planning home, graph detail, feature planning context, and phase operations under the existing agent-query/service pattern. | One backend service owns planning-control-plane reads instead of scattering aggregation across routers. | 3 pts | backend-architect, python-backend-engineer | PCP-105 |
| PCP-202 | REST Planning Endpoints | Add or extend API endpoints for planning summary, graph/detail, feature planning context, and phase operations. | Frontend can load planning home, graph detail, and phase data without reconstructing server logic locally. | 2 pts | python-backend-engineer | PCP-201 |
| PCP-203 | Planning Live Topics | Add project and feature planning invalidation topics, plus any phase/worktree topics needed for V1. | Planning surfaces receive stream-first updates for status changes, reversals, and execution-linked readiness changes. | 2 pts | python-backend-engineer | PCP-201 |
| PCP-204 | Shared Types and Client Helpers | Add frontend types and API helpers for planning payloads and live subscriptions. | Frontend contract matches backend models and supports stream-first recovery paths. | 1 pt | frontend-developer | PCP-202, PCP-203 |

### Success Criteria

1. Planning surfaces can bootstrap from stable APIs and remain fresh via live invalidation.
2. Routers stay thin and the aggregation logic remains service-owned.
3. No view needs to re-derive planning graph or mismatch logic from raw frontmatter.

## Phase 3: Planning Home, Graph, and Tracker/Intake Surfaces

### Objectives

1. Deliver a planning-first home route that surfaces intake, active work, blockers, stale items, and trackers.
2. Deliver graph/detail drill-down for planning artifacts and feature-level lineage.
3. Surface tracker and intake data as a GUI counterpart to current plan-status and tracker workflows.

### Primary Targets

1. `components/Planning/PlanningHomePage.tsx`
2. `components/Planning/PlanningGraphPanel.tsx`
3. `components/Planning/PlanningNodeDetail.tsx`
4. `components/Planning/TrackerIntakePanel.tsx`
5. `components/Layout.tsx`
6. `services/planning.ts`

### Tasks

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|--------|-----------|-------------|---------------------|----------|-------------|--------------|
| PCP-301 | Planning Route and Shell | Add the planning route, navigation entry point, loading/error/empty states, and page shell. | CCDash exposes a dedicated planning-first route wired into existing app navigation. | 2 pts | frontend-developer | PCP-204 |
| PCP-302 | Planning Home Summary Surface | Build summary cards and lists for intake, active plans, stale phases, mismatches, and tracker backlog. | Operators can see high-level planning state and navigate directly to relevant feature or artifact drill-down. | 3 pts | ui-engineer-enhanced, frontend-developer | PCP-301 |
| PCP-303 | Planning Graph and Detail Drill-Down | Build graph/list detail surfaces that explain lineage, blockers, and related entities. | Users can drill from feature or artifact into linked planning nodes with raw/effective status evidence. | 3 pts | ui-engineer-enhanced, frontend-developer | PCP-301, PCP-202 |
| PCP-304 | Tracker and Intake Surface | Add panels or tabs for ready-for-promotion specs, stale shaping work, deferred tracker items, and validation warnings. | The planning route exposes GUI equivalents for current intake and tracker visibility workflows. | 2 pts | frontend-developer | PCP-302, PCP-303 |

### Success Criteria

1. Planning home becomes the primary entry point for project-level planning operations.
2. Users can navigate planning hierarchy without bouncing between unrelated screens.
3. Tracker and intake visibility is available in-product and grounded in existing workflow semantics.

## Phase 4: Feature Control Plane and Phase Operations Integration

### Objectives

1. Extend the execution workbench into a broader feature control plane.
2. Add phase operations surfaces that expose batches, blockers, validation status, and supporting evidence.
3. Align plan catalog, document modal, and project board with the same planning-aware contract where appropriate.

### Primary Targets

1. `components/FeatureExecutionWorkbench.tsx`
2. `components/PlanCatalog.tsx`
3. `components/DocumentModal.tsx`
4. `components/ProjectBoard.tsx`
5. `services/execution.ts`
6. shared planning UI primitives under `components/Planning/`

### Tasks

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|--------|-----------|-------------|---------------------|----------|-------------|--------------|
| PCP-401 | Feature Planning Context Integration | Extend execution workbench payload consumption so feature-level planning hierarchy, batch readiness, and mismatch state render in one control-plane view. | The selected feature view shows planning hierarchy, active phase, actionable batch, and supporting evidence together. | 3 pts | frontend-developer, python-backend-engineer | PCP-202, PCP-303 |
| PCP-402 | Phase Operations View | Add a phase-focused operations panel for task batches, ownership, blockers, supporting docs, and validation outcomes. | Operators can inspect and reason about a phase without opening raw progress files for routine questions. | 3 pts | ui-engineer-enhanced, frontend-developer | PCP-401 |
| PCP-403 | Shared Planning-Aware Metadata Components | Introduce reusable badges/cards for raw vs effective status, mismatch, batch readiness, and artifact lineage. | Planning-aware semantics render consistently across feature, catalog, board, and modal surfaces. | 2 pts | ui-engineer-enhanced | PCP-202 |
| PCP-404 | Cross-Surface Adoption | Update plan catalog, document modal, and board touchpoints to use the shared planning metadata where high value. | Key planning-aware views show consistent status, lineage, and navigation behavior. | 2 pts | frontend-developer | PCP-403 |

### Success Criteria

1. Execution workbench becomes the feature-level planning control plane rather than only a recommendation surface.
2. Phase operations are explainable and actionable from the UI.
3. Planning-aware semantics stay consistent across the main supporting surfaces.

## Phase 5: Launch Preparation, Worktrees, and Provider Routing

### Objectives

1. Add plan-driven launch preparation for actionable batches.
2. Introduce worktree context visibility and storage for safe parallel execution.
3. Expose provider and model routing in a way that aligns with the current execution connector roadmap.

### Primary Targets

1. `backend/services/execution/`
2. `backend/services/repo_workspaces/manager.py`
3. `backend/models.py`
4. `backend/db/sqlite_migrations.py`
5. `backend/db/postgres_migrations.py`
6. `backend/routers/execution.py`
7. `components/Planning/PlanningLaunchSheet.tsx`
8. `components/execution/`
9. `services/execution.ts`
10. `types.ts`

### Tasks

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|--------|-----------|-------------|---------------------|----------|-------------|--------------|
| PCP-501 | Worktree Context Model | Add a persisted worktree context model tied to project, feature, phase/batch, branch, and run linkage, distinct from cache/clone-oriented repo workspaces. | CCDash can represent and query worktree state for plan-driven execution preparation without overloading existing workspace cache concepts. | 3 pts | backend-architect, python-backend-engineer | PCP-201 |
| PCP-502 | Launch Preparation Contract | Define launch-preparation payloads that combine plan batch data, provider capabilities, model selections, worktree context, and approval requirements. | Launch-preparation API contract is stable and grounded in batch metadata rather than ad hoc command text only. | 2 pts | backend-architect, python-backend-engineer | PCP-501, PCP-401 |
| PCP-503 | Execution API and Provider Wiring | Add execution-side endpoints or extensions for worktree-aware launch preparation and batch launch initiation. | The backend can prepare and start plan-driven launches with provider/model metadata and audit-safe request handling. | 3 pts | python-backend-engineer | PCP-502 |
| PCP-504 | Launch Preparation UI | Build a launch sheet/panel that lets operators review batch context, choose provider/model, select or create worktree context, and launch. | Operators can initiate a plan-driven batch launch from the feature/phase UI with clear approval and capability messaging. | 3 pts | frontend-developer, ui-engineer-enhanced | PCP-503 |
| PCP-505 | Local-First Safety and Capability Guardrails | Gate advanced launch actions behind provider capability checks and rollout flags, keeping unsupported paths clearly disabled. | V1 ships safely even if some providers or worktree flows are partial. | 1 pt | python-backend-engineer, frontend-developer | PCP-503, PCP-504 |

### Success Criteria

1. Plan-driven launch preparation exists and is visibly distinct from ad hoc run entry.
2. Worktree context is first-class and linked to feature, phase, and batch execution.
3. Provider/model routing stays aligned with existing connector and orchestration plans instead of bypassing them.

## Phase 6: Validation, Telemetry, and Rollout

### Objectives

1. Add validation coverage for the new planning graph, APIs, UI states, and launch preparation.
2. Add telemetry for planning operations and rollout diagnostics.
3. Stage rollout behind feature flags and project settings where appropriate.

### Primary Targets

1. `backend/tests/`
2. `components/**/__tests__/`
3. `services/**/__tests__/`
4. `docs/`
5. feature-flag and settings surfaces as needed

### Tasks

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|--------|-----------|-------------|---------------------|----------|-------------|--------------|
| PCP-601 | Backend and Contract Tests | Add coverage for planning graph derivation, effective status, mismatch state, planning APIs, and launch-preparation contracts. | Backend behavior is validated for normal, blocked, stale, and reversal cases. | 2 pts | python-backend-engineer, task-completion-validator | PCP-505 |
| PCP-602 | Frontend Interaction Tests | Add UI tests for planning home, graph drill-down, phase operations, and launch preparation states. | The main planning control-plane journeys are covered and stable. | 2 pts | frontend-developer, task-completion-validator | PCP-505 |
| PCP-603 | Telemetry and Rollout Controls | Add telemetry events, ops visibility, and staged rollout controls for planning and launch-preparation surfaces. | Planning-control-plane adoption and failure modes can be measured and the feature can be safely disabled per rollout plan. | 1 pt | python-backend-engineer, frontend-developer | PCP-601, PCP-602 |
| PCP-604 | Documentation and Operator Guidance | Update user/developer docs describing planning control plane behavior, limitations, and rollout caveats. | Operators and developers can understand how to use and extend the new control plane safely. | 1 pt | documentation-writer | PCP-603 |

### Success Criteria

1. The feature is validated end-to-end across backend, UI, and launch-preparation paths.
2. Telemetry distinguishes planning-home usage, graph navigation, phase operations, and launch-preparation actions.
3. Rollout can be staged and reversed cleanly if drift or confusion is observed.

## Cross-Phase Risks and Mitigations

### Risk 1: Duplicate planning truth

Mitigation:

1. Keep source markdown artifacts canonical.
2. Treat the CCDash model as a derived graph and operational projection.
3. Make raw vs effective status visible in every high-signal planning surface.

### Risk 2: Contract sprawl across features router, execution router, and new planning reads

Mitigation:

1. Add a planning query layer before expanding multiple routers.
2. Keep router logic thin and UI-focused payloads server-owned.

### Risk 3: Launch preparation outpaces provider maturity

Mitigation:

1. Keep provider capability and rollout gating explicit.
2. Ship local-first / narrow provider support first if required.
3. Keep advanced orchestration dependent on existing connector and SDK roadmap work.

### Risk 4: UI complexity overwhelms operators

Mitigation:

1. Use progressive disclosure and planning-first summaries.
2. Keep feature control plane and planning home as the default entry points.
3. Make deeper graph and batch views opt-in rather than mandatory for simple workflows.

## Testing Plan

### Backend Tests

1. Planning graph derivation and artifact relationship assembly.
2. Effective status, mismatch, stale, and reversal cases.
3. Planning query service payload coverage.
4. Launch-preparation and worktree contract validation.

### Frontend Tests

1. Planning home summary rendering and navigation.
2. Planning graph/detail drill-down flows.
3. Phase operations states, including blocked and mismatch conditions.
4. Launch sheet states, capability gating, and approval prompts.

### Integration / Rollout Checks

1. Live planning invalidation and REST recovery.
2. Feature control plane integration with planning payloads.
3. Worktree-aware launch preparation against at least one supported provider path.
4. Rollback behavior with planning-specific flags disabled.

## Acceptance Criteria

1. CCDash exposes a planning-first route with planning home, graph/detail drill-down, and tracker/intake visibility.
2. Raw status, effective status, and mismatch state are explicit across planning and feature control-plane views.
3. Users can inspect phase batches, blockers, and supporting evidence from a dedicated phase operations surface.
4. Operators can prepare a plan-driven batch launch with worktree and provider/model awareness.
5. The implementation reuses existing execution, workflow, dependency, and live-update foundations instead of creating a disconnected second product inside CCDash.
