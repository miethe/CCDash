---
schema_name: ccdash_document
schema_version: 3
doc_type: implementation_plan
doc_subtype: enhancement_implementation_plan
primary_doc_role: supporting_document
status: in-progress
category: enhancements
title: 'Implementation Plan: CCDash Planning Control Plane V1'
description: Implement a planning-first control plane in CCDash that unifies planning
  artifacts, derived status, phase operations, tracker intake, and plan-driven agent-team
  launch preparation.
summary: Build a derived planning graph, planning APIs, live planning updates, planning
  home and drill-down surfaces, and plan-driven launch preparation with worktree and
  provider/model awareness.
created: 2026-04-16
updated: '2026-04-17'
phase_7_status: pending
phase_8_status: pending
priority: high
risk_level: high
complexity: High
track: Planning / Execution / Orchestration
timeline_estimate: 4-8 weeks across 6 phases; +2 weeks for Phase 7-8 consolidation and extraction
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
request_log_id: ''
commits: []
prs: []
phase_4_status: completed
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
| 7 | Planning UI Consolidation — Foundation & Extraction | 10-12 pts | 4-5 days | Post-gate | Audit planning components, extract reusable UI to @miethe/ui, consolidate metadata primitives, implement active/planned features columns |
| 8 | Planning UI Integration — Modals, Drill-Downs & Validation | 10-12 pts | 4-5 days | Post-gate | Integrate artifact composition drill-down screens, unify feature and document modals, complete navigation consistency, frontend test coverage |

**Total**: ~76-82 story points over 5-10 weeks depending on connector/worktree scope

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

## Phase 7: Planning UI Consolidation — Foundation & Extraction

### Objectives

1. Audit planning surfaces and inventory reusable UI components for extraction to @miethe/ui.
2. Extract qualifying UI primitives to @miethe/ui, publish, and wire back into CCDash with proper imports.
3. Consolidate metadata primitives (status/mismatch/batch-readiness badges) into `components/shared/PlanningMetadata.tsx`.
4. Implement active plans and planned features columns on planning home using board list primitives.
5. Ensure Phase 6 validation gates remain satisfied throughout consolidation.

### Primary Targets

1. `components/Planning/` (audit and component inventory)
2. `@miethe/ui` (package extraction and publication)
3. `components/shared/PlanningMetadata.tsx` (new consolidated metadata component)
4. `components/Planning/PlanningHomePage.tsx` (active/planned features columns)
5. `services/planning.ts`
6. `types.ts`

### Tasks

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|--------|-----------|-------------|---------------------|----------|-------------|--------------|
| PCP-701 | Audit Planning Primitives and @miethe/ui Extraction Manifest | Codebase explorer: identify all planning-only metadata components in `components/Planning/` (badges, status chips, list renderers). For each, determine: (a) import from @miethe/ui if exists, (b) extract to @miethe/ui if reusable, or (c) keep-local if planning-specific. Produce extraction manifest with location, purpose, and strategy. Reference `.claude/skills/planning/references/ui-extraction-guidance.md`. | Audit report and extraction manifest list every planning-only primitive with location, extraction decision (import/extract/keep-local), and rationale. Manifest is actionable for implementation. | 2 pts | codebase-explorer, frontend-developer, ui-engineer-enhanced | PCP-604 |
| PCP-702 | Active Plans + Planned Features Columns | Implement active plans (status: in-progress) and planned features (implementation plans with status: draft/approved) columns/tabs on planning home, reusing board column/list primitives from ProjectBoard. Ensure clicking a feature opens feature modal (not planning detail). | Planning home surfaces active and planned features using the same list component as /board. Clicking a feature opens feature modal. No planning-only feature detail panels remain. | 3 pts | frontend-developer, ui-engineer-enhanced | PCP-701, PCP-302 |
| PCP-706 | Consolidate Planning Metadata Components | Create or promote `components/shared/PlanningMetadata.tsx` with shared status/mismatch/batch-readiness badge and chip components. Migrate or deprecate planning-only variants in `components/Planning/` following PCP-701 extraction manifest. Update all imports across planning, board, and catalog surfaces. | No planning-only badges or status chips exist in `components/Planning/`; all such rendering delegates to `components/shared/PlanningMetadata.tsx` or upstream /board components. Extraction manifest is fully actioned. | 2 pts | ui-engineer-enhanced, frontend-developer | PCP-701 |
| PCP-709 | Extract and Publish Components to @miethe/ui | For each "extract" decision in PCP-701 manifest: fork component to temp branch in @miethe/ui; refactor dependencies; add package entry; port tests; add Storybook story; document; publish with semver. Update imports in CCDash to pull from @miethe/ui. Reference `.claude/skills/planning/references/ui-extraction-guidance.md` § "9-Step Extraction Process". Mark task description with `[pkg]` for model tracking. | All extraction candidates have been moved to @miethe/ui with published npm packages. CCDash imports updated to use extracted components from @miethe/ui. No inline/duplicated library-eligible primitives remain. | 3-5 pts | ui-engineer-enhanced, frontend-developer | PCP-701 |

### Success Criteria

1. Planning component inventory is complete and extraction decisions documented in manifest.
2. All extraction candidates have moved to @miethe/ui with proper package structure, tests (>80% coverage), and Storybook stories.
3. CCDash imports all applicable shared UI from @miethe/ui instead of maintaining inline copies.
4. `components/shared/PlanningMetadata.tsx` is the single source of truth for planning status/badge rendering.
5. Active plans and planned features are visible on planning home using shared board list components.
6. Phase 6 validation gates remain satisfied; no regressions in existing Phase 3-6 behavior.
7. No planning-specific UI duplications of library-eligible primitives remain in codebase.

## Phase 8: Planning UI Integration — Modals, Drill-Downs & Validation

### Objectives

1. Make artifact composition indicators clickable with dedicated drill-down screens.
2. Unify feature clicks across planning surfaces to open the ProjectBoard feature modal.
3. Unify artifact clicks to open the DocumentModal from `/plans`.
4. Ensure all navigation follows a consistent modal ➜ page pattern with proper deep linking and back-button behavior.
5. Add comprehensive frontend test coverage for all new and refactored flows.

### Primary Targets

1. `components/Planning/PlanningHomePage.tsx`
2. `components/Planning/PlanningSummaryPanel.tsx`
3. `components/Planning/PlanningGraphPanel.tsx`
4. `components/Planning/PlanningNodeDetail.tsx`
5. `components/Planning/TrackerIntakePanel.tsx`
6. `components/ProjectBoard.tsx`
7. `components/DocumentModal.tsx`
8. `services/planning.ts`
9. `types.ts`

### Tasks

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|--------|-----------|-------------|---------------------|----------|-------------|--------------|
| PCP-703 | Artifact Composition Drill-Down Screens | Make each artifact-composition badge clickable; open a dedicated screen listing artifacts of that type (Design Specs, PRDs, Progress Files, etc.) with title, status, updated date, and key metadata, reusing DocumentsList or similar from /plans/documents. | Clicking "3 Design Specs" opens a filterable list screen using /plans document list components; users can click rows to open full DocumentModal. Drill-down screens are accessible from planning home and phase operations. | 3 pts | frontend-developer, ui-engineer-enhanced | PCP-702, PCP-303 |
| PCP-704 | Feature Modal Unification for Planning | Refactor planning surfaces (feature cards, feature lists, graph nodes representing features) to delegate to the ProjectBoard feature modal on click instead of planning-only detail panels. Add "Expand" button in modal that navigates to full feature page if needed. | Clicking any planned feature (on home, graph, list) opens the same feature modal as /board. Modal has an "Expand" button navigating to `/planning/feature/:id/detail` for advanced views. No planning-only feature detail panels remain. | 3 pts | frontend-developer, ui-engineer-enhanced | PCP-702, PCP-401 |
| PCP-705 | Document Modal Integration for Planning Artifacts | Refactor all planning artifact clicks (design spec, PRD, progress file, context file, report) to open DocumentModal from `/plans` instead of planning-only viewers. Ensure modal renders content, metadata, and navigation the same way as /plans. | Clicking a design spec, PRD, or progress file on any planning surface opens the full DocumentModal. Modal renders the document using UnifiedContentViewer and provides the same nav/metadata as /plans. No planning-only artifact viewers remain. | 2 pts | frontend-developer | PCP-706, PCP-303 |
| PCP-707 | Navigation and State Consistency | Ensure all planning surface modals and detail-page transitions follow the same pattern. Test modal ↔ page transitions, deep linking, and browser back/forward. Update route definitions and link generation to use consistent paths. | Users can navigate planning home ➜ feature modal ➜ full page ➜ back consistently. Deep links to features and artifacts work. Back button returns to previous planning view. State persists through modal/page transitions. | 2 pts | frontend-developer | PCP-703, PCP-704, PCP-705 |
| PCP-708 | Frontend Tests for Consolidation Flows | Add/update UI tests covering active plans/planned features columns (from Phase 7), artifact drill-down screens, feature modal integration, document modal flows, and badge consolidation. Confirm Phase 6 validation tests still pass. Run full test suite including Phase 3-6 tests to verify no regressions. | All new consolidation flows (Phases 7-8) have test coverage. Phase 6 and earlier validation tests pass without modification. No regressions in planning home, phase operations, or launch prep navigation. Mutation testing confirms coverage quality. | 2 pts | frontend-developer, task-completion-validator | PCP-707 |

### Success Criteria

1. Planning surfaces (home, graph, operations, launch prep) reuse `/board` and `/plans` components instead of maintaining planning-only primitives.
2. Artifact composition indicators are clickable; drill-down screens reuse document-list rendering from `/plans`.
3. All feature clicks open the feature modal (consistent with /board); artifact clicks open DocumentModal (consistent with /plans).
4. All planning navigation follows the same modal ➜ page pattern as `/board` and `/plans`.
5. Phase 6 validation gates remain satisfied; no behavior changes, only component consolidation.
6. Deep links to features and artifacts work; browser back/forward navigation is consistent.
7. Comprehensive test coverage confirms all Phase 7-8 flows work and Phase 3-6 behavior is unchanged.

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

### Risk 5: Consolidation churn and @miethe/ui extraction coordination

Mitigation:

1. Phase 7-8 is a progressive refactor (data contracts stay stable); Phase 6 validation gates remain valid.
2. PCP-701 audit and extraction manifest is a blocking prerequisite; all downstream refactoring depends on decisions documented there.
3. Preserve Phase 3/4 UI behavior during consolidation; only swap underlying components.
4. Test all Phase 3/4 scenarios after Phase 7-8 to confirm no regressions.
5. @miethe/ui extraction follows established 9-step process; extracted components must have >80% test coverage and Storybook stories before merge.
6. Extracted components use published npm versioning; CCDash pins specific versions to avoid API drift.

### Risk 6: @miethe/ui API stability during parallel extraction

Mitigation:

1. Extracted planning components must have stable APIs (unchanged for 2+ weeks) before extraction.
2. @miethe/ui package versions are semver-strict; breaking changes trigger major version bumps and documented migration paths.
3. CCDash imports pin specific versions, not floating ranges; updates are explicit.
4. If @miethe/ui updates break planning surfaces, revert/pin, and file issue for collaborative fix.

## Testing Plan

### Backend Tests (Phases 1-6)

1. Planning graph derivation and artifact relationship assembly.
2. Effective status, mismatch, stale, and reversal cases.
3. Planning query service payload coverage.
4. Launch-preparation and worktree contract validation.

### Frontend Tests (Phases 3-6)

1. Planning home summary rendering and navigation.
2. Planning graph/detail drill-down flows.
3. Phase operations states, including blocked and mismatch conditions.
4. Launch sheet states, capability gating, and approval prompts.

### Phase 7 Tests (@miethe/ui Extraction & Consolidation)

1. Extracted components have >80% unit test coverage and pass Storybook rendering.
2. Planning metadata component consolidation — status/mismatch/batch-readiness badges render consistently across surfaces.
3. Active plans and planned features columns render on planning home using shared board list components.
4. Phase 6 validation tests still pass without modification.

### Phase 8 Tests (Modal Integration & Navigation)

1. Artifact composition drill-down screens open and filter correctly.
2. Feature modal unification — all feature clicks open ProjectBoard modal.
3. Document modal integration — all artifact clicks open DocumentModal from /plans.
4. Navigation consistency — modal ↔ page transitions, deep linking, back/forward.
5. Full test suite regression check — Phase 3-6 tests pass; no behavior regressions.

### Integration / Rollout Checks (Phases 1-6)

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
6. Planning surfaces (home, graph, phase operations, launch prep) reuse `/board` feature modals and `/plans` document modals instead of maintaining planning-only viewers.
7. Active plans and planned features are visible on planning home, surfaced with the same list primitives as `/board`.
8. Artifact composition indicators are clickable, delegating to shared document-list components from `/plans`.
9. All navigation follows a consistent pattern: click feature ➜ feature modal ➜ expand to detail page; click artifact ➜ document modal.
10. No inline planning-specific duplications of library-eligible primitives remain in codebase; all reusable components are extracted to `@miethe/ui` with published npm packages, proper tests (>80% coverage), and Storybook stories.
11. `components/shared/PlanningMetadata.tsx` is the single source of truth for planning status/mismatch/batch-readiness rendering.
12. Phase 6 validation gates remain satisfied; all Phase 3-6 behavior is preserved through Phase 7-8 consolidation.
