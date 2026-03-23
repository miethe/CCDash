---
schema_name: ccdash_document
schema_version: 3
doc_type: implementation_plan
doc_subtype: enhancement_implementation_plan
primary_doc_role: supporting_document
status: draft
category: enhancements

title: "Implementation Plan: Dependency-Aware Execution and Family Views V1"
description: "Implement derived dependency state, family sequencing, and dependency-aware execution guidance across board, execution, plan catalog, and document views."
summary: "Turn blocked_by, feature_family, and sequence_order metadata into operational UI and backend behavior with blocker evidence, family ordering, and safer execution recommendations."
author: codex
owner: fullstack-engineering
owners: [fullstack-engineering]
contributors: [ai-agents]
audience: [ai-agents, developers, fullstack-engineering]
created: 2026-03-22
updated: 2026-03-22
tags: [implementation, dependencies, execution, feature-family, planning, workflow, frontend, backend]
priority: high
risk_level: medium
complexity: high
track: Dependency Awareness
timeline_estimate: "2-3 weeks across 5 phases"
feature_slug: dependency-aware-execution-and-family-views-v1
feature_family: dependency-aware-execution-and-family-views
feature_version: v1
lineage_family: dependency-aware-execution-and-family-views
lineage_parent:
  ref: docs/project_plans/designs/dependency-aware-execution-and-family-views-v1.md
  kind: implementation_of
lineage_children: []
lineage_type: enhancement
linked_features:
  - feature-execution-workbench-v1
related_documents:
  - docs/project_plans/designs/dependency-aware-execution-and-family-views-v1.md
  - docs/project_plans/PRDs/enhancements/dependency-aware-execution-and-family-views-v1.md
  - docs/project_plans/PRDs/enhancements/feature-execution-workbench-v1.md
  - docs/project_plans/implementation_plans/enhancements/feature-execution-workbench-v1.md
  - docs/schemas/document_frontmatter/document-and-feature-mapping.md
context_files:
  - backend/services/feature_execution.py
  - backend/routers/features.py
  - backend/routers/api.py
  - backend/parsers/documents.py
  - backend/parsers/features.py
  - backend/models.py
  - components/ProjectBoard.tsx
  - components/FeatureExecutionWorkbench.tsx
  - components/PlanCatalog.tsx
  - components/DocumentModal.tsx
  - services/execution.ts
  - types.ts
prd: docs/project_plans/PRDs/enhancements/dependency-aware-execution-and-family-views-v1.md
prd_ref: docs/project_plans/PRDs/enhancements/dependency-aware-execution-and-family-views-v1.md
plan_ref: dependency-aware-execution-and-family-views-v1

request_log_id: ""
commits: []
prs: []
---

# Implementation Plan: Dependency-Aware Execution and Family Views V1

## Objective

Deliver a dependency-aware experience that makes blocked work, family order, and the next executable item explicit across the board, execution workbench, plan catalog, and document modal.

## Current Baseline

The codebase already captures the raw metadata needed for this feature:

1. `blocked_by` identifies hard upstream dependencies.
2. `feature_family` groups related work.
3. `sequence_order` can order work within a family.
4. The execution workbench already has a recommendation and context endpoint that can be extended rather than replaced.

What is missing is the derived state layer and shared presentation model that make this metadata actionable in the UI.

## Scope and Fixed Decisions

1. V1 is derived-state only; no frontmatter mutation workflow is introduced.
2. No database migration is required for V1.
3. Missing dependency evidence must surface as `blocked_unknown`, not silent success.
4. Family ordering should remain visible even when `sequence_order` is missing.
5. The existing feature execution workbench remains the primary execution surface and receives the family/dependency overlay rather than a parallel workflow.

## Architecture

## 1) Derived Dependency and Family Service

Add or expand the execution service layer to compute the canonical derived state used by all surfaces.

Preferred target:

1. `backend/services/feature_execution.py`

Responsibilities:

1. Resolve dependency completion state from linked feature status and existing reconciliation rules.
2. Resolve family siblings and sort them by sequence order and stable fallback rules.
3. Compute first blocking dependency, first executable family item, and current item position.
4. Produce reusable payloads for board, execution, catalog, and document views.

Recommended response models:

1. `FeatureDependencyState`
2. `FeatureFamilySummary`
3. `FeatureFamilyItem`
4. `ExecutionGateState`

## 2) API Payload Extensions

Extend existing feature and execution payloads rather than introducing a separate planning graph API.

Primary targets:

1. `backend/routers/features.py`
2. `backend/routers/api.py` if shared detail serialization is centralized there

Add derived fields to feature detail and list responses:

1. `dependencyState`
2. `blockingFeatures`
3. `familySummary`
4. `familyPosition`
5. `nextRecommendedFamilyItem`

Extend execution context responses with:

1. `executionGate`
2. `family`
3. `recommendedFamilyItem`

## 3) Shared Frontend Components

Create reusable UI pieces so the same dependency and family semantics render consistently across the app.

Targets:

1. `components/DependencyStateBadge.tsx`
2. `components/BlockingFeatureList.tsx`
3. `components/FamilySequenceLane.tsx`
4. `components/FamilySummaryCard.tsx`
5. `components/ExecutionGateCard.tsx`

These components should accept normalized derived state instead of re-deriving logic from raw frontmatter in each view.

## 4) Surface Integration

Update the existing user-facing surfaces to consume the shared derived model.

Targets:

1. `components/ProjectBoard.tsx`
2. `components/FeatureExecutionWorkbench.tsx`
3. `components/PlanCatalog.tsx`
4. `components/DocumentModal.tsx`

Behavior:

1. Blocked features show explicit text and evidence, not chips alone.
2. Family lanes render ordered siblings with current, done, next, blocked, and unsequenced states.
3. Document detail surfaces explain how the document fits into the family and what blocks it.
4. Execution recommendations change when the selected feature is blocked or waiting on a family predecessor.

## 5) Tests, Telemetry, and Rollout

Add unit and integration coverage around derived state and blocked-state rendering.

Targets:

1. `backend/tests/`
2. `components/__tests__/` or existing UI test locations
3. `services/execution.ts` typing and API helpers

Rollout should remain low risk:

1. Land backend derivation first.
2. Add API payload extensions.
3. Update shared frontend components.
4. Switch the existing views to the shared model.
5. Add telemetry for blocked views, dependency navigation, and family-item selection.

## Phase Overview

| Phase | Title | Effort | Duration | Critical Path | Objective |
|------|-------|--------|----------|---------------|-----------|
| 1 | Derived State Model | 8 pts | 3-4 days | Yes | Compute dependency, family, and execution-gate summaries in the backend |
| 2 | API Extensions | 6 pts | 2-3 days | Yes | Expose normalized derived fields on feature and execution payloads |
| 3 | Shared UI Components | 8 pts | 3-4 days | Partial | Build reusable badges, lanes, and gate cards for all surfaces |
| 4 | Surface Integration | 10 pts | 4-5 days | Yes | Wire board, execution, catalog, and document modal to the shared model |
| 5 | Validation and Rollout | 6 pts | 2-3 days | Final gate | Add tests, telemetry, and staged rollout checks |

**Total**: ~38 story points over 2-3 weeks

## Implementation Strategy

### Sequencing Rationale

1. Derive the state once in the backend so every surface renders the same truth.
2. Extend payloads before building new UI so the component contract stays stable.
3. Introduce shared components before editing individual pages to avoid duplicated blocked-state logic.
4. Update the execution workbench after the shared contract exists so its recommendation logic can safely pre-pass on dependency state.
5. Keep doc and catalog updates late in the sequence because they mostly consume the same derived payloads.

### Parallel Work Opportunities

1. Backend derivation and API serialization can proceed in parallel once the state model is agreed.
2. Shared component implementation can overlap with API work using mocked derived payloads.
3. Telemetry tests can start while the visual integration work is landing.

### Critical Path

1. Phase 1 backend derivation
2. Phase 2 payload extensions
3. Phase 3 shared components
4. Phase 4 surface integration
5. Phase 5 validation and rollout

## Phase 1: Derived State Model

**Assigned Subagent(s)**: `backend-architect`, `python-backend-engineer`

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| DEP-001 | Dependency Completion Resolver | Implement the rule set that evaluates each `blocked_by` dependency against feature status and existing completion evidence. | The backend can classify each dependency as complete, blocked, or blocked_unknown with evidence. | 3 pts | backend-architect, python-backend-engineer | None |
| DEP-002 | Family Ordering and Sequencing Model | Resolve family siblings, sort by `sequence_order`, and preserve unsequenced items with stable fallback ordering. | The backend returns a deterministic family summary with sequenced and unsequenced items. | 3 pts | backend-architect, python-backend-engineer | DEP-001 |
| DEP-003 | Execution Gate Derivation | Compute the gate state used by execution surfaces, including first blocking feature and first executable family item. | The derived gate payload can drive blocked, ready, and unknown states without extra client logic. | 2 pts | python-backend-engineer | DEP-001, DEP-002 |

**Phase 1 Quality Gates**

1. Derived states are deterministic for the same input set.
2. Missing evidence produces `blocked_unknown`, not silent unblocking.
3. Family order is stable even when `sequence_order` is partially missing.

## Phase 2: API Extensions

**Assigned Subagent(s)**: `python-backend-engineer`, `backend-architect`

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| DEP-101 | Feature Payload Augmentation | Extend feature detail and list responses with dependency state, family summary, and family position fields. | Existing feature routes return the new derived fields without breaking current consumers. | 2 pts | python-backend-engineer | DEP-001, DEP-002 |
| DEP-102 | Execution Context Augmentation | Extend the execution context payload with gate and family fields so the workbench can react before recommendation rendering. | `/api/features/{feature_id}/execution-context` returns the derived family and blocking payloads. | 2 pts | python-backend-engineer | DEP-003 |
| DEP-103 | Serialization and Schema Coverage | Add response typing and serialization tests for new fields in router and service payloads. | API tests validate the new fields and preserve existing response shape compatibility. | 2 pts | backend-architect | DEP-101, DEP-102 |

**Phase 2 Quality Gates**

1. New payloads remain backward compatible for existing feature views.
2. Execution context includes enough evidence to explain every blocked state.
3. Router tests cover both complete and ambiguous dependency states.

## Phase 3: Shared UI Components

**Assigned Subagent(s)**: `ui-engineer-enhanced`, `frontend-developer`, `ui-designer`

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| DEP-201 | Dependency State Badge | Build a reusable badge that pairs text, iconography, and status for blocked, blocked_unknown, and unblocked states. | The badge never relies on color alone and is readable in compact surfaces. | 2 pts | ui-engineer-enhanced, ui-designer | DEP-101 |
| DEP-202 | Blocking Feature List | Build a compact list component that shows the first blocking feature, status, and view/open actions. | The list exposes blocker evidence and a direct navigation path. | 2 pts | frontend-developer, ui-engineer-enhanced | DEP-101, DEP-102 |
| DEP-203 | Family Lane and Summary Card | Build ordered family lane and summary card components with current, next, done, blocked, and unsequenced states. | Family order is scannable and keyboard readable in the shared component set. | 4 pts | ui-engineer-enhanced, ui-designer | DEP-102 |

**Phase 3 Quality Gates**

1. Shared components accept normalized backend payloads only.
2. Blocked state is clear in text and structure, not icon-only.
3. Family lanes remain readable on both desktop and narrow layouts.

## Phase 4: Surface Integration

**Assigned Subagent(s)**: `frontend-developer`, `ui-engineer-enhanced`, `python-backend-engineer`

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| DEP-301 | Project Board Feature Modal Updates | Integrate dependency state and family summary into the feature modal on the board. | Blocked features show a named blocker, family position, and next unblocked item. | 3 pts | frontend-developer, ui-engineer-enhanced | DEP-201, DEP-202 |
| DEP-302 | Execution Workbench Family Overlay | Update the execution workbench to pre-pass on dependency state and recommend navigation to the first executable family item. | Blocked workbench states no longer recommend blocked work as the primary path. | 3 pts | python-backend-engineer, frontend-developer | DEP-102, DEP-203 |
| DEP-303 | Plan Catalog Family Mode | Add family-oriented scanning to the catalog so grouped lanes and unsequenced items are visible there as well. | The catalog can browse family lanes, sequence order, and blocked state consistently. | 2 pts | frontend-developer, ui-engineer-enhanced | DEP-203 |
| DEP-304 | Document Modal Relationship Enhancements | Update document detail to explain family position, blocker evidence, and the next item in family. | Document modal shows why the doc matters to execution and how to navigate onward. | 2 pts | frontend-developer | DEP-101, DEP-203 |

**Phase 4 Quality Gates**

1. The same derived state renders consistently across all four surfaces.
2. Execution guidance never points primary guidance at blocked work.
3. Documents and plans expose the same family semantics as the board and workbench.

## Phase 5: Validation and Rollout

**Assigned Subagent(s)**: `testing-specialist`, `frontend-developer`, `documentation-writer`

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| DEP-401 | Backend and API Tests | Add unit and router tests for dependency derivation, family ordering, and blocked_unknown behavior. | Test coverage proves the derived model works for complete, ambiguous, and missing-data cases. | 2 pts | testing-specialist, python-backend-engineer | DEP-001, DEP-102 |
| DEP-402 | UI and Interaction Tests | Add UI tests for blocked-state banners, family lanes, and navigation actions across the updated surfaces. | The new components and updated views render and behave as expected under common states. | 2 pts | testing-specialist, frontend-developer | DEP-201, DEP-203, DEP-301 |
| DEP-403 | Telemetry and Documentation | Add telemetry events for blocked-state views and update user-facing planning notes if needed. | The rollout can measure blocked-state engagement and family navigation usage. | 2 pts | documentation-writer, frontend-developer | DEP-301, DEP-302, DEP-304 |

**Phase 5 Quality Gates**

1. Tests cover both correct unblocking and explicit ambiguity handling.
2. Telemetry distinguishes blocked views from family navigation actions.
3. Documentation references the derived-state model instead of raw frontmatter assumptions.

## Testing Plan

## Unit Tests

1. Dependency completion resolution for terminal, non-terminal, and unresolved dependencies.
2. Family ordering for mixed sequence, missing sequence, and stable fallback cases.
3. Execution gate derivation for blocked, ready, and blocked_unknown states.

## Integration Tests

1. Feature detail and execution context payloads include derived fields.
2. Board, execution, catalog, and document routes consume the same normalized model.
3. Blocked features never surface as the primary recommended execution path.

## UI Tests

1. Dependency badges render with text and iconography.
2. Family lanes preserve order and expose unsequenced items.
3. Navigation actions open the correct dependency or family target.

## Risks and Mitigations

1. Risk: Derived blocker logic disagrees with users when source metadata is stale.
   - Mitigation: show the evidence source and a distinct `blocked_unknown` state.
2. Risk: Family grouping over-clusters related but distinct work.
   - Mitigation: require exact `feature_family` matches and keep unsequenced items visible.
3. Risk: Execution guidance becomes too restrictive.
   - Mitigation: preserve alternate guidance while keeping the primary action dependency-aware.

## Acceptance Criteria

1. Blocked features render as blocked in board and execution surfaces with named upstream dependencies.
2. Family order is visible in board, execution, catalog, and document views.
3. Execution recommendations no longer present blocked work as the primary next action.
4. Missing or ambiguous dependency evidence produces an explicit warning state rather than silent fallback.
5. Shared UI components and backend payloads expose the same derived model across all surfaces.
