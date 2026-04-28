---
schema_name: ccdash_document
schema_version: 3
doc_type: prd
doc_subtype: enhancement_prd
status: completed
category: enhancements
title: "PRD: CCDash Planning Control Plane V1"
description: "Turn CCDash into the GUI control plane for frontmatter-driven planning, phase operations, and agent-team execution preparation."
summary: "Add a planning-first control plane to CCDash that unifies planning artifacts, derived status, blockers, tracker intake, and plan-driven agent team launch on top of existing execution and workflow foundations."
created: 2026-04-15
updated: 2026-04-28
priority: high
risk_level: high
complexity: High
track: Planning / Execution / Orchestration
timeline_estimate: 4-8 weeks
feature_slug: ccdash-planning-control-plane-v1
feature_family: planning-control-plane
feature_version: v1
lineage_family: planning-control-plane
lineage_parent: docs/project_plans/design-specs/ccdash-planning-control-plane-architecture.md
lineage_children: []
lineage_type: enhancement
problem_statement: CCDash can parse plans, show documents, and orchestrate execution, but it still lacks a unified planning control plane that turns frontmatter-driven planning artifacts into an explainable, live, operational GUI for task, phase, and agent-team management.
owner: platform-engineering
owners:
  - platform-engineering
  - fullstack-engineering
  - ai-integrations
contributors:
  - ai-agents
audience:
  - developers
  - platform-engineering
  - engineering-leads
  - workflow-authors
  - ai-agents
tags:
  - prd
  - planning
  - execution
  - orchestration
  - worktrees
  - workflow
  - control-plane
linked_features:
  - feature-execution-workbench-v1
related_documents:
  - docs/project_plans/design-specs/ccdash-planning-control-plane-architecture.md
  - docs/project_plans/PRDs/enhancements/feature-execution-workbench-v1.md
  - docs/project_plans/PRDs/enhancements/feature-execution-workbench-future-phases-roadmap-v1.md
  - docs/project_plans/PRDs/enhancements/feature-execution-workbench-phase-3-platform-connectors-v1.md
  - docs/project_plans/PRDs/enhancements/feature-execution-workbench-phase-4-sdk-orchestration-v1.md
  - docs/project_plans/PRDs/enhancements/workflow-registry-and-correlation-v1.md
  - docs/project_plans/PRDs/enhancements/dependency-aware-execution-and-family-views-v1.md
context_files:
  - backend/parsers/documents.py
  - backend/parsers/progress.py
  - backend/db/sync_engine.py
  - backend/application/services/agent_queries/
  - backend/services/feature_execution.py
  - backend/services/execution_runtime.py
  - backend/routers/features.py
  - backend/routers/execution.py
  - backend/routers/live.py
  - components/FeatureExecutionWorkbench.tsx
  - components/PlanCatalog.tsx
  - components/ProjectBoard.tsx
  - components/DocumentModal.tsx
  - services/live/
  - types.ts
implementation_plan_ref: ""
---

# PRD: CCDash Planning Control Plane V1

## Executive Summary

CCDash already has the right technical substrate for a planning control plane: it parses planning artifacts, links features and documents, derives workflow intelligence, supports live updates, and is evolving toward provider-agnostic execution orchestration. What it does not yet provide is a planning-first operator experience that makes the existing frontmatter-driven workflow visible, navigable, and actionable in one place.

This enhancement turns CCDash into that control plane. V1 adds a planning graph and operations surface that unifies design specs, PRDs, implementation plans, progress files, context files, trackers, dependency state, execution readiness, and plan-driven agent team launch preparation. The planning workflow remains file-backed and CLI-compatible; CCDash becomes the live GUI layer that helps humans and orchestration agents understand what should happen next and why.

## Current State

CCDash already provides several pieces of the eventual solution:

1. Planning and document parsing from local filesystem sources.
2. Feature, session, and document linking across the project.
3. Execution Workbench for feature-level execution context and run management.
4. Workflow intelligence and workflow registry surfaces.
5. Dependency-aware and family-aware execution guidance.
6. Shared live-update infrastructure for execution, features, tests, and ops.

Despite that, planning operations remain fragmented:

1. There is no planning home that shows intake, active initiatives, stale phases, trackers, and mismatches together.
2. Plan hierarchy is spread across documents and modals rather than one explainable graph.
3. Effective status propagation and raw status divergence are not surfaced as first-class product states.
4. Plan-driven agent-team launch is implicit in docs and external workflows rather than visible in CCDash.
5. Worktree setup, provider selection, and multi-model assignment are not yet planning-native controls.

## Problem Statement

As a developer, lead, or orchestration operator using an AI-native planning workflow, I need CCDash to act as the control plane for planning and execution rather than just a collection of adjacent surfaces. Today the source artifacts contain the truth, but the product does not yet make that truth easy to inspect, drill into, validate, and use to launch safe parallel work.

Without a planning control plane:

1. operators still reconstruct plan state manually from multiple artifacts
2. planning status and execution status can drift without obvious explanation
3. blockers, stale work, and promotion candidates are harder to notice than they should be
4. launching parallel agent work remains more procedural than productized
5. CCDash stops short of being the natural shell for AI-native SDLC management

## Goals

1. Make planning artifacts first-class operational objects inside CCDash.
2. Surface both raw and effective status for plans, phases, and features, including mismatch evidence.
3. Provide a feature-centric drill-down from initiative to phase, task batch, execution run, and supporting artifacts.
4. Let operators prepare agent-team launches directly from plan guidance, including provider, model, and worktree selection.
5. Reuse existing CCDash execution, workflow, and live-update foundations instead of creating a separate planning application.

## Non-Goals

1. Replacing markdown + frontmatter planning artifacts as the source of truth in V1.
2. Full in-app authoring for every planning artifact type in V1.
3. Arbitrary generalized project management workflows unrelated to the AI-native planning model.
4. Cross-project orchestration or multi-project dependency graphs in V1.
5. Fully autonomous execution without policy, approval, or audit controls.

## Users and Jobs-to-be-Done

1. Developers: "Show me the exact feature, phase, and batch I should run next, with the evidence that justifies it."
2. Engineering leads: "Show me where work is blocked, stale, drifting, or ready for promotion across the project."
3. Workflow authors and operators: "Show me how planning structure, execution history, and workflow recommendations fit together so I can coordinate agent teams safely."
4. AI orchestration operators: "Let me turn plan metadata into a concrete multi-agent launch with the right provider, model choices, and worktree setup."

## Product Thesis

The existing planning workflow is already optimized for machine readability. The missing layer is not a new planner database but a strong operational GUI that can:

1. interpret the planning graph
2. explain effective state
3. join planning with execution
4. help humans and agents act on that graph

CCDash is already the closest system to that role. The right move is to extend CCDash into a planning control plane, not to fork a generic PM tool or build a disconnected parallel product.

## Product Requirements

### 1) Planning Home

CCDash must provide a planning-first home surface that summarizes:

1. design specs ready for promotion
2. active PRDs and implementation plans
3. blocked or stale phases
4. tracker backlog and deferred work
5. validation or status mismatch warnings
6. recent planning-related execution activity

The surface must support project-scoped filtering and deep links into the underlying artifacts and feature views.

### 2) Planning Graph and Drill-Down

CCDash must present planning artifacts as a linked graph rather than isolated documents.

The graph must allow users to navigate between:

1. design spec
2. PRD
3. implementation plan
4. phase progress file
5. context file
6. tracker or report
7. related feature, session, and execution runs

The user must be able to drill from a top-level feature or plan into phase-level detail without losing context.

### 3) Raw vs Effective Status

CCDash must distinguish between:

1. raw artifact status
2. effective derived status
3. mismatch or unresolved state

For V1, the UI must make it obvious when:

1. a raw status is stale
2. effective state has advanced or regressed
3. a phase is blocked because of task evidence
4. a higher-level artifact appears complete only by inference

Every derived state must have evidence that is inspectable in the UI.

### 4) Phase Operations

CCDash must provide a phase-focused operational view for progress files.

That view must expose:

1. task list with ownership and status
2. batch grouping for parallelization
3. readiness state per batch
4. blockers and missing prerequisites
5. validation and audit outcomes where available
6. direct links to supporting docs, sessions, and artifacts

V1 may remain read-mostly for task mutation, but it must support operational decision-making without forcing users back into raw files for every question.

### 5) Feature Control Plane

The existing execution workbench must evolve into a broader feature control plane.

It must combine:

1. feature summary and dependency state
2. linked planning hierarchy
3. current phase and first actionable batch
4. workflow and stack recommendations
5. recent execution runs
6. artifact and session context

The product must avoid presenting planning and execution as unrelated tabs from different mental models.

### 6) Agent-Team Launch Preparation

CCDash must support a launch flow that turns plan metadata into an execution-ready batch.

For each eligible phase or batch, the operator must be able to:

1. choose an execution provider
2. choose or confirm model / agent assignment
3. create or select a worktree context
4. attach plan and context artifacts
5. review policy and approval requirements
6. launch the batch with audit trail

The launch flow must be driven by planning metadata first, not only by ad hoc command entry.

### 7) Worktree Awareness

Worktrees must become first-class planning and execution objects.

The UI must expose:

1. whether a batch has an assigned worktree
2. worktree path and branch context
3. active or stale worktree ownership
4. relationship between worktree, run, feature, and batch

V1 does not need to support every git lifecycle action, but it must support enough visibility and control to make parallel agent work safe.

### 8) Provider and Model Routing

The control plane must support provider-aware and model-aware launch preparation.

It must be able to represent:

1. local runtime vs external connector vs SDK orchestration path
2. model selection at least at batch level
3. provider capabilities and limitations
4. approval or security requirements implied by the provider

V1 may constrain the number of supported providers, but the UI and contracts must remain adapter-based.

### 9) Tracker and Intake Operations

CCDash must provide a GUI counterpart to intake and tracker workflows.

The product must surface:

1. ready-for-promotion design specs
2. stale shaping work
3. deferred tracker items and promotion conditions
4. documents with validation or frontmatter issues

This should mirror the existing planning-reporting workflow instead of inventing a new backlog taxonomy.

### 10) Live Planning State

Planning-related surfaces must update live as planning artifacts or execution state change.

The control plane must react to:

1. progress-file status changes
2. effective-status reversals
3. execution run changes that affect planning readiness
4. feature dependency changes
5. tracker and intake updates

The normal experience should be stream-first with REST recovery rather than heavy polling.

## Non-Functional Requirements

### Performance

1. Planning home should render project summary state within 2 seconds p95 after initial load for typical local projects.
2. Feature and phase drill-down should switch views within 500ms p95 once cached.
3. Live planning updates should appear within 2 seconds of source change under local runtime conditions.

### Reliability

1. Derived planning state must be reproducible from source artifacts after restart.
2. No planning status update should rely solely on transient in-memory state.
3. Execution-launch preparation must remain consistent with provider capability metadata.

### Explainability

1. Every derived status or gating decision must include inspectable evidence.
2. The UI must not collapse explicit and inferred state into a single unlabeled badge.
3. Users must always be able to open the source artifact that produced the visible state.

### Security

1. Launch paths that can execute commands or agent teams must respect existing policy and approval controls.
2. Provider credentials and secrets must never be exposed in planning views.
3. Worktree and run actions must remain project-scoped.

### Observability

1. Planning graph reads, launch preparation actions, and orchestration launches must emit telemetry.
2. Planning mismatch and stale-state conditions should be measurable for rollout evaluation.
3. Live planning topic health should be visible in existing ops / cache status tooling where applicable.

## Scope

### In Scope

1. Planning home and planning graph views.
2. Raw/effective status presentation and mismatch state.
3. Feature and phase drill-down with planning-aware context.
4. Agent-team launch preparation driven by planning metadata.
5. Worktree awareness for plan-driven execution.
6. Provider/model selection surfaces aligned with execution connectors.
7. Tracker and intake views that mirror the existing planning workflow.
8. Live planning state integrated with existing live-update infrastructure.

### Out of Scope

1. Replacing source markdown artifacts with DB-authored planning objects.
2. Generic Jira/Linear-style issue management unrelated to the frontmatter-driven model.
3. Cross-project agent scheduling.
4. Full workflow authoring inside CCDash.
5. Automatic no-approval execution of high-risk agent teams.

## Dependencies

1. Existing planning artifact parsing and filesystem sync.
2. Dependency-aware execution and family-state derivation.
3. Execution workbench local runtime baseline.
4. Platform connector abstraction and provider capability model.
5. SDK orchestration path for richer multi-step launches.
6. Shared live-update infrastructure.

## Risks and Mitigations

1. Risk: the feature duplicates existing planning truth instead of representing it.
   Mitigation: keep file-backed artifacts canonical and make derived state evidence explicit.
2. Risk: the feature becomes too broad and tries to ship every orchestration capability at once.
   Mitigation: stage V1 around visibility and launch preparation, with deeper automation deferred.
3. Risk: worktree and provider state become hard to reason about in the UI.
   Mitigation: normalize worktree and provider models before exposing advanced flows.
4. Risk: overlap with execution workbench and workflow registry confuses product boundaries.
   Mitigation: define the planning control plane as the umbrella shell that incorporates those surfaces rather than competing with them.

## Success Metrics

1. At least 80% of active features in pilot projects can be understood from intake to current phase without leaving CCDash.
2. Mean time to identify the first actionable phase or batch for an active feature drops by at least 50%.
3. At least 60% of eligible parallel batch launches in pilot projects start from plan-driven launch preparation rather than ad hoc command entry.
4. Planning mismatch and stale-state issues are surfaced early enough that manual status remediation incidents drop by at least 40%.
5. Operator satisfaction for planning/execution coordination improves materially in pilot feedback.

## UI Integration & Consolidation (Amendment)

### Problem

Phases 1–5 of the Planning Control Plane V1 introduced planning-specific UI surfaces (`/planning` route with `PlanningHomePage`, `PlanningGraphPanel`, `PlanningNodeDetail`, `TrackerIntakePanel`, and shared planning metadata badges) in isolation. However, the existing `/board` and `/plans` pages already provide powerful, proven navigation, modal interactions, and artifact viewing patterns. The current planning UI creates **parallel primitive sets instead of reusing shared components**, leading to:

1. **UI Inconsistency**: Planning surfaces use planning-only badges and list views instead of the same feature modals, document modals, and board column patterns used elsewhere.
2. **Data Gaps**: No unified view of **active plans** as a workflow column; no distinct view of **planned features** (features with implementation plans but no start date); no way to see both sides of execution readiness.
3. **Navigation Friction**: Clicking planning artifacts opens planning-specific detail panels rather than the familiar feature modal (/board) or full document modal (/plans) that operators already use.
4. **Component Debt**: `components/Planning/` contains planning-only metadata primitives instead of delegating to existing `components/DocumentModal.tsx`, `components/ProjectBoard.tsx` feature modal logic, and shared board/catalog components.

### Requirements

**R-A: Active Plans Column + Planned Features View**
Planning home must provide an additional column or tab showing active implementation plans (plans with `status: in-progress`) and a separate column for planned features (features with implementation plans and `status: [draft|approved]` but no execution start). Both should reuse the same list/column primitives from `/board` (e.g., `SessionCard` or feature card components) for consistency.

**R-B: Clickable Artifact Composition Indicators**
Each artifact-composition badge (e.g., "3 Design Specs", "1 PRD", "2 Progress Files") on planning surfaces should be clickable. Clicking should open a dedicated screen listing all artifacts of that type, with one row per artifact showing title, status, last updated, and key metadata. This screen should reuse the same components as the Documents tab on `/board` (LinkedDocumentsList or similar) and the full document list on `/plans`.

**R-C: Feature Modal First, Expand to Detail**
Clicking on any planned feature or feature-related planning artifact should open the **same feature modal component used on /board** (not a planning-only detail panel). The modal must include an "Expand" button that navigates to the full dedicated page (e.g., `/planning/feature/:featureId/detail`) for deeper phase/batch operations. This unifies navigation: planning home ➜ feature modal ➜ full page drill-down.

**R-D: Planning Artifact ➜ Document Modal Integration**
Clicking on an individual planning artifact (design spec, PRD, progress file, context file, report) should open the **full document modal from `/plans`** with the same rendering, metadata, and navigation UI. Planning surfaces should not introduce planning-only document viewers; instead, delegate to the existing DocumentModal component and its content viewing capabilities.

**R-E: Replace Planning-Only Primitives with Board/Plans Components**
Audit `components/Planning/` and identify all planning-only metadata components (badges, status chips, list renderers) that duplicate logic from `/board` or `/plans` (e.g., `EffectiveStatusChips`, `MismatchBadge`, planning-only feature cards). Replace with shared components or upstream the planning-aware variants to a truly shared location (e.g., `components/shared/PlanningMetadata.tsx`) so adoption is automatic across `/board`, `/plans`, and `/planning`.

### Rationale

Phases 1–5 ship working planning surfaces but introduce **primitive duplication** that fragments the operator experience. A consolidation pass in Phase 7 (before final validation) ensures:

1. **Consistency**: Planning operators see the same UI patterns and modal behaviors as feature/board operators.
2. **Reusability**: Shared components reduce maintenance surface and make new planning-aware features cheaper to add elsewhere.
3. **Navigation Clarity**: "Click something" always leads to a predictable modal ➜ page pattern, not different modals in different surfaces.
4. **Phase 6 Compatibility**: Phase 6 validation gates remain valid because Phase 7 consolidation refactors UI only, not data contracts or behavior.

### Acceptance Criteria Additions

1. Active plans and planned features columns/views render using the same list primitives as `/board` feature lists.
2. Clicking an artifact-composition badge opens a screen with the same component set as the Documents tab or `/plans` artifact list.
3. Clicking a feature opens the feature modal; "Expand" navigates to full page (no separate planning modals for features).
4. Clicking a planning artifact opens the DocumentModal component from `/plans`, not a planning-only renderer.
5. `components/Planning/` contains no planning-only metadata primitives; all status/mismatch/batch-readiness rendering delegates to shared components under `components/shared/PlanningMetadata.tsx` or upstream to `/board` components where applicable.
6. All planning surfaces use the same modal interactions, document viewers, and feature card patterns as `/board` and `/plans`.

### Out of Scope (Consolidation Phase)

1. **No redesign of `/board` or `/plans`** themselves; consolidation flows one direction (planning ➜ reuse board/plans).
2. **No change to Phase 6 validation gates** or test expectations; Phase 7 is UI refactoring, not behavioral change.
3. **No new planning-native data structures** or contract changes; Phase 7 uses existing planning and feature APIs.
4. **No feature flag or partial rollout** needed for Phase 7 (it's a consolidation, not a new capability).

## Rollout Strategy

V1 should ship in progressive slices:

1. planning graph + planning home
2. feature and phase control plane views
3. tracker / intake surfaces
4. plan-driven launch preparation with worktree and provider/model selection

This keeps the first release useful even before the deepest orchestration paths mature.

## Acceptance Criteria

1. CCDash exposes a planning-first surface that unifies planning artifacts, blockers, trackers, and live state.
2. Users can drill from feature-level context into phase, batch, and source artifacts without losing planning context.
3. Raw status, effective status, and mismatch state are all represented explicitly.
4. Operators can prepare a batch launch from plan metadata, including provider and worktree selection.
5. The feature composes with existing execution workbench, workflow registry, dependency-awareness, and live-update foundations instead of bypassing them.
