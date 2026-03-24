---
schema_name: ccdash_document
schema_version: 3
doc_type: prd
doc_subtype: enhancement_prd
status: inferred_complete
category: enhancements
title: 'PRD: Dependency-Aware Execution and Family Views V1'
description: Make blocked work, family ordering, and sequence-aware execution first-class
  behaviors across board, execution, catalog, and document views.
summary: Turn `blocked_by`, `feature_family`, and `sequence_order` from descriptive
  metadata into derived dependency states, family navigation, and execution gating
  that steer users to the first actionable item.
created: 2026-03-22
updated: 2026-03-22
priority: high
risk_level: medium
complexity: High
track: Dependency Awareness
timeline_estimate: 2-3 weeks
feature_slug: dependency-aware-execution-and-family-views-v1
feature_family: dependency-aware-execution-and-family-views
feature_version: v1
lineage_family: dependency-aware-execution-and-family-views
lineage_parent: docs/project_plans/designs/dependency-aware-execution-and-family-views-v1.md
lineage_children: []
lineage_type: enhancement
problem_statement: CCDash captures dependency and family metadata, but execution surfaces
  still treat it as passive context instead of operational state, which leads users
  toward blocked work and hides the correct next item in a family.
owner: fullstack-engineering
owners:
- fullstack-engineering
contributors:
- ai-agents
audience:
- ai-agents
- developers
- engineering-leads
- product-design
tags:
- prd
- execution
- dependencies
- feature-family
- planning
- workflow
linked_features:
- feature-execution-workbench-v1
related_documents:
- docs/project_plans/designs/dependency-aware-execution-and-family-views-v1.md
- docs/project_plans/PRDs/enhancements/feature-execution-workbench-v1.md
- docs/project_plans/implementation_plans/enhancements/feature-execution-workbench-v1.md
- docs/schemas/document_frontmatter/document-and-feature-mapping.md
context_files:
- backend/parsers/documents.py
- backend/parsers/features.py
- backend/services/feature_execution.py
- backend/routers/features.py
- backend/models.py
- components/ProjectBoard.tsx
- components/FeatureExecutionWorkbench.tsx
- components/PlanCatalog.tsx
- components/DocumentModal.tsx
- types.ts
implementation_plan_ref: docs/project_plans/implementation_plans/enhancements/dependency-aware-execution-and-family-views-v1.md
---
# PRD: Dependency-Aware Execution and Family Views V1

## Executive Summary

CCDash already captures the metadata needed to describe hard dependencies and ordered feature families. The problem is that the app still treats `blocked_by`, `feature_family`, and `sequence_order` as passive annotations. Users can see the fields, but the product does not derive whether a feature is blocked, which upstream item is responsible, or which sibling item is the correct next executable step.

This enhancement turns that metadata into operational product behavior. The board, execution workbench, plan catalog, and document modal should all expose a shared derived model for blocked state, blocker evidence, family position, and first executable family item. The result should be a safer and more explainable execution flow that helps users avoid starting blocked work and navigate related feature families with less guesswork.

## Current State

Today CCDash can already display:

1. raw `blocked_by` chips
2. `feature_family` labels
3. `sequence_order` badges
4. execution recommendations based on plan phase state

Those pieces are useful, but they are not enough:

1. The app does not derive whether a feature is actually blocked from upstream completion state.
2. Users are not told which dependency is preventing execution right now.
3. There is no family-oriented navigation model that orders sibling work across features and docs.
4. Execution recommendations do not pre-pass on dependency or family state, so they can still point at blocked work.
5. Document and plan surfaces do not explain how a doc fits into the family sequence or why it matters next.

## Problem Statement

As an engineer or lead using CCDash to decide what to work on next, I need the app to understand dependency completion and ordered family progression, not just display the raw metadata. Today I still have to infer whether a feature is blocked, which sibling in a family should come first, and whether the execution workbench is recommending the wrong target.

Without derived dependency and family views:

1. blocked work can still look runnable
2. users can choose the wrong feature or wrong phase
3. family progression is hard to scan across related plans and documents
4. execution guidance is less trustworthy than it should be

## Goals

1. Make dependency state explicit anywhere a user makes an execution decision.
2. Make feature-family order visible anywhere a user compares plans, features, or supporting docs.
3. Keep blocked-state messaging evidence-based and explainable.
4. Change execution guidance so blocked work is not presented as the primary next action.
5. Let users move from a blocked item directly to the dependency or first executable family sibling that matters next.

## Non-Goals

1. Automatic mutation of frontmatter when dependencies complete.
2. Cross-project dependency graphs.
3. Arbitrary DAG editing in the UI.
4. Full scheduling or Gantt tooling.
5. User-authored manual overrides for dependency state in V1.

## Users and Jobs-to-be-Done

1. Engineers: "Tell me whether this work is actually executable and why."
2. Tech leads: "Show me where this feature sits in the family and what has to complete first."
3. Reviewers and operators: "Let me navigate quickly from a blocked item to the right dependency or sibling."

## Product Requirements

### 1) Derived Dependency State

The system must derive a dependency state for features and related docs instead of relying on raw frontmatter alone.

Required states:

1. `unblocked`
2. `blocked`
3. `blocked_unknown`
4. `ready_after_dependencies`

Each derived state must include evidence fields sufficient for UI explanation, including:

1. dependency feature identity
2. dependency status
3. completion evidence summary
4. blocking document references when available
5. a human-readable blocking reason

### 2) Dependency Completion Rules

For V1, a dependency counts as complete when at least one of the following is true:

1. the dependency feature is terminal (`done` or `deferred`)
2. the dependency feature has completion-equivalent owning docs under existing reconciliation rules

If dependency evidence is missing or cannot be resolved, the state must be `blocked_unknown`, not silently unblocked.

### 3) Family Ordering Rules

For any `feature_family`, the system must:

1. sort items by `sequence_order` ascending
2. use stable fallback ordering when sequence values tie
3. keep missing-order items visible in an `Unsequenced` bucket
4. treat missing sequence order as a warning, not a blocker by itself

The family model must provide:

1. current item position
2. completed item count
3. first blocked item
4. first executable item
5. previous/current/next relationships when they exist

### 4) Project Board Feature Modal

The feature modal must become a decision surface, not just a detail view.

It must:

1. show a prominent blocked-state banner when unresolved hard dependencies exist
2. name the first blocking dependency and expose a `View dependency` action
3. show family position, next unblocked family item, and derived dependency state in feature overview data
4. include a family lane or family tab that displays ordered sibling items
5. label blocked items textually rather than relying on metadata chips alone

### 5) Execution Workbench

The execution workbench must become dependency-aware before it applies phase-based recommendation rules.

It must:

1. evaluate family and dependency state before existing recommendation rules
2. avoid recommending `/dev:execute-phase ...` as the primary action when the selected feature is blocked
3. surface a top-level execution gate state such as `Ready`, `Blocked`, or `Unknown`
4. provide direct actions to open the blocking dependency or first executable family item
5. explain the evidence used to decide why a feature is blocked or ready

### 6) Plan Catalog

The plan catalog must support family-oriented scanning in addition to file-oriented browsing.

It must:

1. offer a family-based mode or grouped lane view
2. sort family members by `sequence_order`
3. render blocked/unblocked state per item
4. keep unsequenced members visible and labeled
5. expose family, sequence position, and blocker count in list/card metadata

### 7) Document Modal

Document detail must explain how a document fits into execution.

It must:

1. show derived dependency state in the summary view
2. show family position and next item in family when available
3. show hard dependencies with dependency status and completion evidence
4. render previous/current/next family sequence context in relationships

### 8) Shared Backend and UI Model

The app must use a shared family and dependency model across surfaces so all views speak the same language.

The backend should expose normalized payloads for:

1. feature dependency state
2. family summary
3. family item
4. execution gate state

The frontend should render those payloads via shared reusable components rather than re-deriving logic per screen.

## Non-Functional Requirements

1. Derived-state evaluation must be deterministic for the same input set.
2. UI must never rely on color alone to communicate blocked state.
3. Family sequence views must remain keyboard navigable and readable as ordered text.
4. Existing feature and execution surfaces must remain resilient to partial evidence and show explicit warning states rather than failing silently.
5. No database migration should be required for V1 unless implementation discovery proves current feature state cannot be derived from existing sources.

## Scope

### In Scope

1. Derived dependency-state logic.
2. Shared family-summary model.
3. Execution gating based on family and dependency pre-pass.
4. Board, execution, catalog, and document-modal updates.
5. Shared UI components for badges, blocker lists, family lanes, and execution gates.

### Out of Scope

1. Editing dependencies or sequence order from the UI.
2. Automatic metadata repair flows.
3. Cross-project dependency resolution.
4. Timeline planning and scheduling.

## Success Metrics

1. Blocked workbench sessions no longer recommend blocked work as the primary next action.
2. Users can identify the first blocking dependency from board and execution surfaces without extra navigation.
3. Family lanes or grouped family views appear consistently across the four target surfaces.
4. Missing or ambiguous dependency evidence is represented explicitly rather than silently falling back to unblocked behavior.

## Dependencies and Assumptions

1. Existing parser and feature reconciliation logic continue to expose the raw dependency and family metadata reliably.
2. Existing execution-context APIs can be extended without replacing the workbench architecture.
3. Current feature and document status rules remain the source of truth for completion evidence.

## Risks and Mitigations

1. Risk: derived blocker logic conflicts with stale metadata.
   - Mitigation: show evidence sources and expose `blocked_unknown` as a distinct warning state.
2. Risk: family grouping clusters unrelated work with the same slug.
   - Mitigation: require exact family-key matches and keep unsequenced items visible rather than forcing order.
3. Risk: execution guidance feels too restrictive.
   - Mitigation: preserve alternate guidance while keeping primary guidance dependency-aware.

## Acceptance Criteria

1. A blocked feature clearly renders as blocked in board and execution surfaces with named upstream dependencies.
2. Execution no longer recommends starting blocked work as the primary next action.
3. Users can inspect a family as an ordered lane and move across sibling items without leaving context.
4. Catalog and document surfaces expose family position and blocking dependencies consistently.
5. Missing or ambiguous dependency evidence produces an explicit warning state rather than silent fallback behavior.

## Implementation Approach

### Phase 1: Derived State Model

1. add backend dependency and family derivation
2. define reusable payloads for dependency state, family summaries, and execution gate state
3. add tests for blocker resolution and family ordering

### Phase 2: API Extensions

1. extend feature detail and execution context payloads
2. keep derived fields explainable and backward compatible
3. validate ambiguous evidence behavior

### Phase 3: Shared Components and Surface Integration

1. add shared dependency and family components
2. integrate them into board, execution, catalog, and document modal
3. update recommendation rules to pre-pass on blocked and family state

### Phase 4: Validation and Rollout

1. add UI and API coverage
2. add telemetry around blocked-state and family navigation
3. roll out behind normal enhancement validation gates
