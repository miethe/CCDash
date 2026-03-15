# Document And Feature Mapping

Last updated: 2026-03-14
Status: Canonical

This spec defines:

- which frontmatter fields are expected per document type
- where each field group is displayed in CCDash
- which fields stay document-local versus bubble up to `Feature`
- which derived and user-editable fields should exist next

## 1. Current gaps to close

The repository already preserves raw frontmatter, but the normalized models and UI only expose a subset:

- `PlanDocument` currently normalizes tags, feature/session refs, lineage, version, PRD refs, request ids, commit refs, task counts, phase, and dates.
- `Feature` currently bubbles up title/status/tags/phases/linked docs/dates/related features, but not richer planning metadata such as `description`, `priority`, `risk_level`, `owners`, `target_release`, `complexity`, `track`, or typed linked-feature relationships.
- `DocumentModal`, `PlanCatalog`, and the feature surfaces show only a narrow slice of the available metadata.

The implementation goal is not to invent new document ownership rules. Documents remain independent first-class objects, and features consume a curated projection of their metadata.

## 2. Recommended document modal structure

Use the same tab set for every document type, with doc-type-specific sections populated as relevant:

1. `Summary`
2. `Delivery`
3. `Relationships`
4. `Content`
5. `Timeline`
6. `Raw`

### 2.1 Summary tab

Always show:

- Identity: `title`, `doc_type`, `doc_subtype`, `canonicalPath`, `primary_doc_role`
- Lifecycle: `status`, `decision_status`, `created`, `updated`, `started`, `completed`
- Ownership: `owner`, `owners`, `contributors`, `reviewers`, `approvers`, `audience`
- Classification: `category`, `priority`, `risk_level`, `complexity`, `track`, `target_release`, `milestone`
- Feature anchors: `feature_slug`, `feature_family`, `feature_version`
- Execution ordering: `sequence_order`
- Cross-doc anchors: `prd_ref`, `plan_ref`, `implementation_plan_ref`
- Summary copy: `description`, `summary`

### 2.2 Delivery tab

Shared sections:

- `Execution`: `execution_readiness`, `timeline_estimate`, `execution_entrypoints`
- `Change Surface`: `files_affected`, `files_modified`, `context_files`, `source_documents`
- `Quality`: `test_impact`, `integrity_signal_refs`
- `Progress`: `overall_progress`, task counters, `completion_estimate`

### 2.3 Relationships tab

Shared sections:

- `Features`: `linked_features[]`
- `Hard dependencies`: `blocked_by[]`
- `Documents`: `related_documents`, `prd_ref`, `plan_ref`, `implementation_plan_ref`
- `Sessions / Tasks / Delivery`: `linked_sessions`, `linked_tasks`, `request_log_ids`, `commit_refs`, `pr_refs`
- `Lineage`: `lineage_family`, `lineage_parent`, `lineage_children`, `lineage_type`

Relationship display rules:

- Feature relationships should render as clickable feature chips with type badges and a source badge (`manual`, `derived_lineage`, `explicit_doc_field`, `inferred`).
- Document references should render as clickable documents when a canonical path resolves, otherwise as plain refs.
- Session/task/request/commit/pr refs should render as entity links when resolvable, otherwise as monospace values.

### 2.4 Content tab

- Render markdown body.
- Provide in-page anchors for requirement ids, task ids, findings ids, and decision ids when present.

### 2.5 Timeline tab

- Show typed date signals from parser output first.
- Then show derived doc events from linked sessions, commits, and status changes.

### 2.6 Raw tab

- Show normalized frontmatter JSON and raw source frontmatter.
- This is required because migration will be incremental and raw fidelity is already preserved.

## 3. Document-type-specific modal sections

### 3.1 PRD

Summary:

- `problem_statement`
- `context`
- `users`
- `jobs_to_be_done`

Delivery:

- `goals`
- `success_metrics`
- `functional_requirements`
- `non_functional_requirements`
- `acceptance_criteria`
- `assumptions`
- `dependencies`
- `risks`

Card/List display:

- Title
- Status
- Priority
- Target release / milestone
- Linked feature chips
- Goal / metric count

### 3.2 Implementation plan

Summary:

- `objective`
- `scope.in_scope`
- `scope.out_of_scope`

Delivery:

- `architecture_summary`
- `rollout_strategy`
- `rollback_strategy`
- `observability_plan`
- `testing_strategy`
- `security_considerations`
- `data_considerations`
- `phases[]`
- `execution_entrypoints`

Card/List display:

- Title
- Status
- Complexity / track / timeline estimate
- `feature_family` / `sequence_order` when present
- Phase count
- Linked feature chips

### 3.3 Phase plan

Summary:

- `phase`
- `phase_title`
- `phase_goal`
- `depends_on_phases`

Delivery:

- `entry_criteria`
- `exit_criteria`
- `tasks[]`
- `parallelization`
- `blockers`
- `success_criteria`
- `files_modified`

Card/List display:

- Phase number and title
- Status
- `feature_family` / `sequence_order` when present
- Task counts
- Linked parent plan

## 4. Follow-on plan for dependency/family logic

The current implementation should capture and display `blocked_by`, `feature_family`, and `sequence_order` without changing execution or status semantics. The next wiring pass should:

1. Use `blocked_by` to mark documents/features as blocked in board, catalog, and execution recommendation surfaces.
2. Show blocking feature status and resolution evidence anywhere a blocked dependency is rendered.
3. Add a feature-family timeline/sequence surface that groups sibling docs by `feature_family` and orders them by `sequence_order`, similar to phase lists.
4. Feed `blocked_by` and `sequence_order` into execution recommendation logic so "next work" respects hard dependencies and family ordering.

### 3.4 Progress

Summary:

- `phase`
- `completion_estimate`
- `owners`
- `contributors`

Delivery:

- `overall_progress`
- task counters
- `tasks[]`
- `blockers`
- `success_criteria`
- `next_steps`
- `files_modified`

Card/List display:

- Progress percentage
- Completed / total tasks
- Blocked / at-risk counts
- Updated date

### 3.5 Report

Summary:

- `report_kind`
- `scope`
- `impacted_features`

Delivery:

- `findings[]`
- `recommendations[]`
- `evidence[]`

Card/List display:

- Title
- Report subtype
- Severity summary
- Impacted feature count

### 3.6 Design doc

Summary:

- `surfaces`
- `user_flows`
- `ux_goals`

Delivery:

- `components`
- `accessibility_notes`
- `motion_notes`
- `asset_refs`

Card/List display:

- Title
- Subtype (`design_system`, `wireframe`, `interaction_spec`, etc.)
- Surface count
- Linked feature chips

### 3.7 Spec

Summary:

- `spec_kind`
- `interfaces`
- `entities`

Delivery:

- `data_contracts`
- `validation_rules`
- `migration_notes`
- `open_questions`

Card/List display:

- Title
- Spec subtype
- Interface/entity counts
- Linked feature chips

## 4. Documents page surfaces

### 4.1 Card view

Each card should show:

- Title
- `doc_type` and `doc_subtype`
- Status
- Linked feature chips
- One primary summary line from `description` or `summary`
- One secondary metadata row based on doc type:
  - PRD: `priority`, `target_release`
  - Implementation plan: `complexity`, `track`, phase count
  - Phase plan: `phase`, task counts
  - Progress: progress percent, blocked/at-risk counts
  - Report: subtype and finding count
  - Design doc: subtype and surface count
  - Spec: subtype and interface/entity count
- Primary date chip using parsed date confidence

### 4.2 List view

Add columns for:

- `doc_type`
- `doc_subtype`
- `linked feature`
- `priority`
- `updated`
- `primary date confidence`

### 4.3 Folder metadata pane

Show the same summary sections as the modal `Summary` tab, not only status/author/tags.

## 5. Feature bubble-up rules

Features should expose only fields that help summarize, filter, compare, or correlate the work item represented by the feature.

### 5.1 Bubble up directly

These should become first-class normalized `Feature` fields:

- `description`
  Source precedence: PRD `description` -> implementation plan `description`
- `summary`
  Source precedence: PRD `summary` -> implementation plan `summary`
- `priority`
  Source precedence: PRD -> plan -> highest explicit value across linked docs
- `risk_level`
  Source precedence: PRD -> plan -> highest explicit value across linked docs
- `complexity`
  Source precedence: implementation plan -> PRD
- `track`
  Source precedence: implementation plan -> PRD
- `timeline_estimate`
  Source precedence: implementation plan -> PRD
- `target_release`
  Source precedence: PRD -> plan
- `milestone`
  Source precedence: PRD -> plan
- `owners`
  Union from PRD, implementation plan, active progress docs
- `contributors`
  Union from all linked docs
- `request_log_ids`
  Union from all linked docs
- `commit_refs`
  Union from all linked docs and progress tasks
- `pr_refs`
  Union from all linked docs
- `execution_readiness`
  Derived from plans, progress, blockers, and test impact
- `test_impact`
  Highest explicit value across docs

### 5.2 Keep document-local only

Do not bubble these to top-level feature fields; keep them on documents and show them through linked-doc detail:

- full `requirements`
- full `success_metrics`
- full `findings`
- full `evidence`
- full `parallelization`
- raw `validation_rules`
- `asset_refs`
- `source_documents`
- `files_modified`

### 5.3 Bubble up as derived collections

These should become computed feature collections:

- `primary_documents`
  One canonical PRD, one canonical implementation plan, zero-many phase plans, latest progress docs, supporting reports/design/specs.
- `linked_features[]`
  Merge manual, explicit, lineage-derived, and inferred feature relationships.
- `document_coverage`
  Which expected doc types exist and which are missing.
- `quality_signals`
  Rollup of blockers, at-risk tasks, integrity signals, and test impact.

## 6. Recommended feature modal structure

Use these tabs:

1. `Overview`
2. `Delivery`
3. `Docs`
4. `Relations`
5. `Sessions`
6. `History`
7. `Test Status`

### 6.1 Overview

Show:

- Title, id, status
- `description`
- `summary`
- task and phase counts
- document coverage summary
- `priority`, `risk_level`, `complexity`, `track`, `target_release`, `milestone`
- `owners`, `contributors`
- `execution_readiness`

### 6.2 Delivery

Show:

- phase summaries
- `timeline_estimate`
- blockers and at-risk counts from progress docs
- aggregated `commit_refs`, `pr_refs`, `request_log_ids`
- active rollout / testing / observability notes from the implementation plan

### 6.3 Docs

Group linked documents by:

- Primary
- Delivery tracking
- Quality / reports
- Design / specs

Each card should show:

- Title
- doc type/subtype
- role badge (`primary`, `supporting`)
- status
- summary line
- most relevant typed metrics for that doc type

### 6.4 Relations

Show:

- `linked_features[]` with type/source/confidence
- lineage chain
- dependency-like relationships to other features
- cross-feature correlations implied by shared PRDs/plans/specs

### 6.5 Sessions / History / Test Status

Keep the current session, history, and test-status tabs, but enrich them with:

- doc-sourced request/commit/pr refs
- doc-sourced timeline events
- blockers / integrity references from progress and reports

## 7. Feature cards and other feature surfaces

Feature cards should add:

- `priority`
- `target_release` or `milestone`
- `execution_readiness`
- linked-feature count
- document coverage badge
- optional risk badge when `risk_level` is `high` or `critical`

Linked-feature and linked-document preview rows should show typed badges rather than plain ids only.

## 8. Complex and interactive fields to add

### 8.1 `linked_features[]`

Canonical structure:

```yaml
linked_features:
  - feature: feature-execution-workbench-phase-2-local-terminal-v1
    type: phase
    source: derived_lineage
    confidence: 1.0
    notes: "Derived from lineage_parent on linked PRD/plan."
```

Rules:

- populate from explicit `linked_features`
- augment from `lineage_parent`, `lineage_children`, `feature_family`, `related_documents`, and PRD/plan cross-links
- allow manual additions and manual type overrides
- preserve both the inferred type and the manual override source

### 8.2 `execution_readiness`

Derived from:

- presence of a primary PRD and plan
- latest progress status
- open blockers / at-risk tasks
- test impact and integrity signals

### 8.3 `document_coverage`

Derived per feature:

- primary PRD present?
- primary plan present?
- progress present?
- latest report present?
- relevant design/spec support present?

### 8.4 `quality_signals`

Derived rollup:

- blocker count
- at-risk task count
- report findings severity summary
- integrity signal refs
- test status summary
