---
doc_type: design_doc
doc_subtype: design_spec
status: draft
category: enhancements

title: "Design Spec: Dependency-Aware Execution and Family Views V1"
description: "Design the next iteration of CCDash dependency handling and family navigation so blocked work, family ordering, and sequence-aware execution become first-class app behaviors."
summary: "Turn passive `blocked_by`, `feature_family`, and `sequence_order` metadata into dependency-aware states, blocker messaging, and family sequence views across Board, Execution, documents, and plans."
author: codex
audience: [ai-agents, developers, engineering-leads, product-design]
created: 2026-03-15
updated: 2026-03-15

tags: [design, execution, dependencies, feature-family, planning, workflow]
feature_slug: dependency-aware-execution-and-family-views-v1
feature_family: dependency-aware-execution-and-family-views
feature_version: v1
blocked_by: []
sequence_order: null
lineage_family: dependency-aware-execution-and-family-views
lineage_parent: ""
lineage_children: []
lineage_type: iteration
primary_doc_role: supporting_design

linked_features:
  - feature-execution-workbench-v1
related_documents:
  - docs/schemas/document_frontmatter/document-and-feature-mapping.md
  - docs/project_plans/implementation_plans/enhancements/feature-execution-workbench-v1.md
  - docs/project_plans/PRDs/enhancements/feature-execution-workbench-v1.md
  - components/ProjectBoard.tsx
  - components/FeatureExecutionWorkbench.tsx
  - components/PlanCatalog.tsx
  - components/DocumentModal.tsx
  - backend/parsers/documents.py
  - backend/parsers/features.py
  - backend/services/feature_execution.py

surfaces:
  - project_board_feature_modal
  - execution_workbench
  - plan_catalog
  - document_modal
  - feature_router_and_execution_service
user_flows:
  - inspect_blocked_feature
  - unblock_by_finishing_dependency
  - navigate_feature_family
  - choose_next_family_item_for_execution
ux_goals:
  - Make blocked state explicit and explainable.
  - Make family sequencing scannable in the same way phases are scannable.
  - Preserve fast navigation from feature detail to the exact document or dependency that matters next.
components:
  - dependency_state_badge
  - blocker_reason_panel
  - family_sequence_lane
  - family_explorer_view
  - execution_gate_card
accessibility_notes:
  - Never use color alone to signal blocked state; pair with text and iconography.
  - Family sequence must be keyboard navigable and readable as ordered text, not only as a visual lane.
motion_notes:
  - Use light staggered reveal when expanding family sequence lanes or blocker evidence panels.
asset_refs: []

owner: fullstack-engineering
owners: [fullstack-engineering]
contributors: [codex]
---

# Design Spec: Dependency-Aware Execution and Family Views V1

## 1. Intent

CCDash now captures `blocked_by`, `feature_family`, and `sequence_order`, but the app still treats them as descriptive metadata. This design turns them into operational UX:

1. Features should visibly enter a blocked state when required upstream work is not complete.
2. Execution should refuse or soften "next command" guidance when dependencies are unresolved.
3. Families should become a first-class navigation model, similar to phases for a single plan.
4. Documents should show how they fit into a family sequence and why they are blocked.

The result should feel like CCDash understands not just isolated features, but delivery order across related features.

## 2. Current Gaps

Today the app can display:

1. Hard dependency chips pulled from `blocked_by`.
2. `feature_family` labels.
3. `sequence_order` badges.

It does not yet:

1. Derive whether a feature is actually blocked from dependency completion state.
2. Tell the user which dependency is preventing execution right now.
3. Offer a family-oriented view that orders sibling features/docs by sequence.
4. Use sequence and dependency data in execution recommendations.
5. Show a coherent dependency path from doc -> feature -> family -> next actionable item.

## 3. Product Goals

### Primary goals

1. Make dependency state visible anywhere a user makes an execution decision.
2. Make family order visible anywhere a user compares plans or features.
3. Keep blocked-state messaging evidence-based and explainable.
4. Reduce wrong-phase or wrong-feature execution by steering users to the first unblocked family item.

### Non-goals for V1

1. Automatic mutation of document frontmatter when dependencies complete.
2. Cross-project dependency graphs.
3. Arbitrary DAG editing in the UI.
4. Full Gantt/scheduling tooling.

## 4. Data Semantics

### 4.1 Canonical meanings

1. `blocked_by`: hard upstream feature dependencies, always interpreted as owning-feature slugs.
2. `feature_family`: versionless grouping key used to cluster related work into an ordered lane.
3. `sequence_order`: 0-based order within a family, used for progression and display.

### 4.2 Derived dependency state

Introduce a derived state model rather than relying on raw frontmatter alone:

1. `unblocked`
2. `blocked`
3. `blocked_unknown`
4. `ready_after_dependencies`

Each derived state must include evidence:

1. `dependencyFeatureId`
2. `dependencyStatus`
3. `dependencyCompletionEvidence`
4. `blockingDocumentIds`
5. `blockingReason`

### 4.3 Dependency completion rule

For V1, a dependency counts as complete when one of these is true:

1. The dependency feature status is terminal (`done` or `deferred`).
2. The dependency feature has completion-equivalent owning docs under the existing feature reconciliation rules.

If the dependency feature cannot be resolved or has insufficient evidence, mark the dependent item `blocked_unknown`, not silently unblocked.

### 4.4 Family ordering rule

For a given `feature_family`, sort by:

1. `sequence_order` ascending
2. document/feature type priority
3. title/path stable fallback

When `sequence_order` is missing:

1. keep item visible
2. place it in an "Unsequenced" bucket at the end
3. surface missing-order as an information warning, not a blocker

## 5. Experience Model

## 5.1 Project Board: feature modal

The feature modal should evolve from "rich detail" to "decision surface."

### New behavior

1. Show a prominent blocked-state banner when any unresolved hard dependency exists.
2. Banner copy format:
   - `Blocked by 2 upstream features`
   - followed by the first dependency title/status and a `View dependency` CTA
3. Show a `Family` tab or lane section alongside existing tabs.
4. Family lane should list sibling family items in sequence order, with:
   - current item
   - completed items
   - first unblocked next item
   - blocked items

### Feature overview card additions

1. `Derived dependency state`
2. `First blocking feature`
3. `Family position` like `2 of 5`
4. `Next unblocked family item`

### Docs tab additions

1. Group docs by:
   - primary feature docs
   - family sequence docs
   - supporting context docs
2. Each doc row should show:
   - family slug
   - sequence order
   - blocked/unblocked state
   - blocking dependency references when present

## 5.2 Execution Workbench

Execution should become dependency-aware, not only phase-aware.

### New execution states

1. `Ready to execute`
2. `Blocked by dependency`
3. `Waiting on family predecessor`
4. `Unknown dependency state`

### New execution gate card

Place a top-level gate card above primary recommendation output.

Card states:

1. `Blocked`
   - shows blocking dependency chips with status and completion evidence
   - primary CTA becomes `Open dependency feature`
   - secondary CTA becomes `Open blocking document`
2. `Ready`
   - shows first eligible family item and rationale
3. `Unknown`
   - shows fallback guidance and evidence gap warning

### Recommendation rule changes

Add a dependency/family pre-pass before existing recommendation rules:

1. Resolve family siblings and order.
2. Resolve dependency completion state.
3. If current feature is blocked, do not recommend `/dev:execute-phase ...` as primary.
4. Instead recommend one of:
   - `Open dependency feature`
   - `/dev:complete-user-story {dependency}`
   - `/dev:execute-phase {N} {dependency-plan}`
5. Only when the feature is unblocked should existing phase rules run.

### Workbench family panel

Add a `Family` panel with:

1. ordered sibling features
2. status icons
3. blocker links
4. "current recommended item" highlight
5. one-click navigation to any sibling feature detail

## 5.3 Plan Catalog

The catalog should support family-oriented scanning, not only file-oriented browsing.

### New view mode

Add `Family` as a new catalog mode:

1. each family renders as a grouped lane
2. items sort by `sequence_order`
3. each item shows blocked/unblocked state
4. missing ordering appears in an `Unsequenced` subsection

### Existing card/list updates

1. blocked items should show a textual blocked label, not just chips
2. secondary metadata line should include:
   - family
   - sequence position
   - blocked by count

## 5.4 Document Modal

Document detail should explain why the doc matters to execution.

### Summary tab additions

1. derived dependency state
2. family position
3. "next item in family" link if one exists

### Relationships tab additions

1. `Hard Dependencies` should show:
   - dependency feature name
   - dependency status
   - completion evidence summary
2. `Family Sequence` should show previous/current/next docs in the same family

## 6. Family View Model

Introduce a reusable family abstraction that multiple screens can consume.

### 6.1 Family summary payload

Proposed shape:

1. `familyId`
2. `displayName`
3. `items[]`
4. `firstBlockedItem`
5. `firstExecutableItem`
6. `completedCount`
7. `totalCount`
8. `unsequencedCount`

### 6.2 Family item payload

Each item should include:

1. `featureId`
2. `featureName`
3. `sequenceOrder`
4. `status`
5. `dependencyState`
6. `blockedBy[]`
7. `primaryDocs[]`
8. `isCurrent`
9. `isNextRecommended`

### 6.3 Shared UI pattern

Use the same visual pattern across Board, Execution, and Catalog:

1. ordered lane
2. explicit labels for `Done`, `Current`, `Next`, `Blocked`, `Unsequenced`
3. compact dependency callouts on blocked items

## 7. Backend Design

## 7.1 Parser layer

The parser layer already captures the raw fields. No new frontmatter parsing is required.

Keep current responsibilities in:

1. `backend/parsers/documents.py`
2. `backend/parsers/features.py`

## 7.2 Derived dependency service

Add a new service module or expand existing feature execution service responsibilities:

1. resolve dependency status for a feature
2. resolve family siblings and sequence ordering
3. resolve the first executable family item
4. produce blocker evidence for UI

Preferred location:

1. `backend/services/feature_dependencies.py`
2. or expand `backend/services/feature_execution.py` only if a clean boundary can be preserved

### Recommended service outputs

1. `FeatureDependencyState`
2. `FeatureFamilySummary`
3. `FeatureFamilyItem`
4. `ExecutionGateState`

## 7.3 API surfaces

### Extend existing feature detail payloads

Add derived fields to feature detail/list responses:

1. `dependencyState`
2. `blockingFeatures`
3. `familySummary`
4. `familyPosition`

### Extend execution context

Add to `/api/features/{feature_id}/execution-context`:

1. `executionGate`
2. `family`
3. `recommendedFamilyItem`

### Optional dedicated family endpoint

If reuse becomes awkward, add:

1. `GET /api/features/families`
2. `GET /api/features/families/{family_id}`

## 8. Frontend Design

## 8.1 Shared component set

Introduce reusable components rather than embedding all logic in page components:

1. `DependencyStateBadge`
2. `BlockingFeatureList`
3. `FamilySequenceLane`
4. `FamilySummaryCard`
5. `ExecutionGateCard`

## 8.2 Navigation patterns

Every blocked-state element should offer at least one direct path:

1. `Open dependency feature`
2. `Open blocking doc`
3. `Jump to family lane`

## 8.3 Copy strategy

Use direct language:

1. `Blocked by feature-blocker-v1`
2. `Waiting for family item #1 to complete`
3. `Next executable item in this family`

Avoid vague copy like:

1. `Not ready`
2. `Has issues`
3. `Needs work`

## 9. Rollout Plan

### Phase 1: Derived state model

1. add backend dependency/family derivation
2. extend feature and execution API payloads
3. add tests for blocker resolution and family ordering

### Phase 2: Execution gating

1. add execution gate card
2. change recommendation pre-pass to dependency-aware ordering
3. add telemetry for blocked-state views and dependency navigation

### Phase 3: Family view surfaces

1. add family lane to feature modal
2. add family panel to execution
3. add family mode to plan catalog

### Phase 4: Doc experience polish

1. add family sequence strip in document modal
2. add richer blocker evidence
3. add missing-sequence warnings and authoring guidance

## 10. Risks

1. Derived blocker logic may disagree with user intent when doc status is stale.
   - Mitigation: always show evidence source and fallback state.
2. Family grouping may over-cluster unrelated items with the same slug.
   - Mitigation: require exact `feature_family` matches and keep unsequenced items visible.
3. Recommendation logic may feel too restrictive if blocked state is noisy.
   - Mitigation: allow alternative commands under a warning section, but keep the primary action dependency-aware.

## 11. Open Questions

1. Should blocked-state resolution rely only on feature terminal state, or also require completed primary plan docs?
2. Should family order be feature-centric, document-centric, or both depending on surface?
3. Do we want a top-level `/families` route, or should family exploration remain embedded in Board/Execution/Catalog?
4. Should unsequenced family items be treated as warnings or blockers for recommendation generation?
5. Should users be able to override derived blocker state in the UI, or stay frontmatter-only for V1?

## 12. Acceptance Criteria

1. A blocked feature clearly renders as blocked in Board and Execution, with named upstream dependencies.
2. Execution no longer recommends starting blocked work as the primary next command.
3. Users can inspect a family as an ordered lane and move across sibling items without leaving context.
4. Document and catalog surfaces expose family position and blocking dependencies in a consistent way.
5. Missing or ambiguous dependency evidence produces an explicit warning state rather than silent fallback behavior.
