---
schema_version: "1.0"
doc_type: design-spec
title: "CCDash Planning Control Plane Architecture"
status: draft
created: "2026-04-15"
feature_slug: "ccdash-planning-control-plane-v1"
prd_ref: "docs/project_plans/PRDs/enhancements/ccdash-planning-control-plane-v1.md"
plan_ref: ""
---

# CCDash Planning Control Plane Architecture

## Problem Statement

CCDash already has most of the raw ingredients needed for an AI-native planning control plane:

- local-first parsing of planning documents and progress files
- workflow intelligence and execution recommendations
- an execution workbench with local runtime support and a connector roadmap
- live updates and multi-project awareness

What it does not yet have is a unified planning surface that treats design specs, PRDs, implementation plans, progress files, trackers, context files, and execution runs as one navigable operational graph.

Today the underlying planning workflow is optimized for agent consumption through YAML frontmatter and CLI scripts. That is the correct source-of-truth model, but it leaves operators without a strong GUI for:

- navigating plan hierarchy from initiative to phase task
- seeing effective state when raw status and derived status differ
- understanding why something is blocked or actionable
- launching agent teams or worktrees directly from plan guidance
- reconciling planning state with execution state across multiple runtimes

The goal of this design spec is to define how CCDash should become that control plane without displacing the existing file-based planning workflow.

---

## Design Goals

1. Preserve markdown + frontmatter planning artifacts as the canonical source of truth.
2. Make planning state navigable and explainable at every level of detail.
3. Reuse CCDash execution, workflow, dependency, and live-update foundations rather than introducing a second orchestration product inside the same repo.
4. Support multi-agent execution preparation, including worktree setup and provider/model routing, without making CCDash the authoring source for every plan artifact in V1.
5. Keep the architecture compatible with local-first usage and transport-neutral query surfaces.

## Non-Goals

1. Replacing SkillMeat or existing CLI-first planning scripts as the system of record.
2. Turning V1 into a generic project management suite with arbitrary issue schemas.
3. Shipping fully autonomous orchestration with no human governance.
4. Supporting cross-project dependency graphs or fleet scheduling in the first release.

---

## Architectural Thesis

CCDash should be the **planning and execution control plane** for an existing AI-native planning workflow.

The boundary should be:

- **Planning artifacts**: markdown files with structured frontmatter remain canonical.
- **CCDash**: derived planning graph, operator GUI, live status, orchestration entry point, and audit surface.
- **Execution providers**: local runtime, SDK orchestration, and external connectors execute work and report normalized state back into CCDash.

This is deliberately not a separate standalone product. A separate product would duplicate:

- document parsing and sync
- execution/workflow intelligence
- live update transport
- project and path configuration
- feature/document/session linking

Those are already native CCDash concerns.

---

## Core Design Decisions

### D1. CCDash is the shell; files stay canonical

The planning control plane must derive its model from planning documents and progress files already tracked by the filesystem sync layer. CCDash may offer controlled mutations later, but those writes should map back to structured frontmatter updates or helper scripts, not a second database-owned planning model.

### D2. The planning graph is derived, not independently authored

CCDash should construct a normalized planning graph from:

- design specs
- SPIKEs and reports when linked
- PRDs
- implementation plans
- phase progress files
- context files
- trackers
- execution runs, sessions, and workflow evidence

This graph is an operational view over source artifacts, not a competing source of truth.

### D3. Effective state must remain inference-first

The workflow’s status-propagation model should carry directly into CCDash:

- raw status is preserved
- effective status is computed
- mismatch state is explicit
- users can see why a status appears derived, stale, blocked, or reversed

This avoids the classic UI failure where a dashboard silently rewrites planning truth.

### D4. Planning and execution must share one feature-centric context model

The planning control plane should extend the existing feature/execution bounded context instead of creating a separate planning app inside CCDash. Features, family order, dependencies, documents, sessions, and execution runs should all stay joinable from one canonical feature context.

### D5. Agent teams are launched from plan batches, not ad hoc freeform only

The planning UI should treat progress frontmatter as the primary machine interface for orchestration:

- `tasks[]`
- `assigned_to`
- `parallelization.batch_N`
- phase metrics and blockers

That lets CCDash launch planned teams from the same structure the orchestration workflow already trusts.

### D6. Worktrees are first-class execution context

For multi-agent work, the system should model worktree preparation as a first-class concern associated with:

- project
- feature / phase
- batch or run
- provider / model selection
- workspace path and branch metadata

This is required if the planning control plane is going to coordinate parallel execution safely.

### D7. Provider abstraction should ride on the existing execution connector roadmap

The planning control plane should not invent a second connector stack. It should consume the execution provider abstraction already outlined for local runtime, platform connectors, and SDK orchestration.

### D8. Live planning updates should use the shared CCDash live-update platform

Planning status, execution state, and derived feature readiness should stream through the existing SSE/live-update platform instead of bespoke polling loops.

---

## Proposed Product Surfaces

### 1. Planning Home

Cross-project overview for:

- intake pipeline
- active initiatives
- blocked work
- stale phases
- tracker backlog
- validation / mismatch warnings

### 2. Planning Graph View

A drill-down surface that links:

- design spec
- PRD
- implementation plan
- phase progress
- context
- reports / trackers
- execution runs

The graph should make lineage and dependency relationships obvious, not hidden in frontmatter fields.

### 3. Feature Control Plane

An expanded feature workbench that combines:

- planning hierarchy
- effective status and blockers
- active phase and task batches
- workflow recommendations
- recent sessions and artifacts
- launch controls for orchestration

This likely evolves the existing execution workbench rather than replacing it.

### 4. Phase Operations View

A phase-focused board where operators can:

- inspect task batches
- see ownership and file-scope constraints
- compare raw vs effective progress
- launch or relaunch batch runs
- review approvals and validation outcomes

### 5. Agent Team Launch Surface

A launch flow driven by plan metadata that allows operators to:

- choose local vs connector vs SDK provider
- pick models / agent classes per task or batch
- create or reuse worktrees
- attach context artifacts
- launch batch execution with approval policy

### 6. Tracker and Deferred Work Surface

A queue for:

- deferred items
- promotion conditions
- stale shapers
- ready-for-promotion specs

This is the GUI counterpart to CLI intake and plan-status reporting.

---

## Derived Data Model

The planning control plane should expose a transport-neutral derived model with at least these entities:

### PlanningNode

- `id`
- `type` (`design_spec`, `prd`, `implementation_plan`, `progress`, `context`, `tracker`, `report`)
- `path`
- `title`
- `featureSlug`
- `rawStatus`
- `effectiveStatus`
- `mismatchState`
- `updatedAt`

### PlanningEdge

- `sourceId`
- `targetId`
- `relationType`
  - `promotes_to`
  - `implements`
  - `phase_of`
  - `informs`
  - `blocked_by`
  - `family_member_of`
  - `tracked_by`
  - `executed_by`

### PhaseBatch

- `featureSlug`
- `phase`
- `batchId`
- `taskIds`
- `assignedAgents`
- `fileScopeHints`
- `readinessState`

### AgentTeamRun

- `runId`
- `featureSlug`
- `phase`
- `batchId`
- `providerId`
- `worktreeId`
- `status`
- `approvalState`
- `modelSelections`
- `linkedExecutionRunIds`

### WorktreeContext

- `worktreeId`
- `projectId`
- `featureSlug`
- `branch`
- `path`
- `status`
- `ownerRunId`

---

## System Integration Plan

### Backend

Add a planning bounded context on top of existing parsing and agent-query patterns:

- planning graph aggregation service
- effective-status and mismatch service
- tracker/intake service
- orchestration launch preparation service
- worktree context service

These should live behind transport-neutral application services first, then be exposed to REST, CLI, and MCP as needed.

### Frontend

Add planning-focused surfaces while reusing:

- current feature workbench shell
- document modal / content viewer patterns
- workflow registry drill-down patterns
- live invalidation hooks

### Storage

Continue to derive canonical planning state from filesystem-backed artifacts.

Use CCDash DB storage only for:

- cached graph projections
- execution-run normalization
- worktree metadata
- approvals / audit events
- provider config and health

### Live Updates

Add planning topic families for:

- project planning summary
- feature planning state
- phase progress invalidation
- orchestration / worktree state

These should compose with existing feature and execution topics rather than replace them.

---

## UX Principles

1. Show summary first, evidence second, raw artifact always reachable.
2. Never hide the difference between explicit and inferred state.
3. Keep action entry points close to the plan evidence that justifies them.
4. Favor feature-centric navigation over document-centric maze navigation.
5. Treat blocked, stale, mismatched, and unresolved states as first-class visual conditions.

---

## Key Risks

### Risk 1. CCDash becomes a second planning system

Mitigation:

- keep file-backed artifacts canonical
- keep UI mutations narrow and structured
- show artifact links and raw frontmatter evidence

### Risk 2. Planning scope overlaps confusingly with execution workbench phases

Mitigation:

- define planning control plane as a broader shell
- position existing execution workbench and workflow registry as sub-surfaces

### Risk 3. Worktree and multi-agent launch semantics vary by provider

Mitigation:

- normalize required launch metadata at the CCDash layer
- keep provider adapters capability-driven

### Risk 4. Live status looks wrong when derived and raw state diverge

Mitigation:

- expose mismatch state explicitly
- always show derivation evidence and raw artifact status together

---

## Recommended Delivery Shape

The feature should be delivered as an enhancement track in CCDash with staged rollout:

1. Planning graph and status surfaces.
2. Feature control plane and phase operations.
3. Agent team launch, worktree context, and provider/model routing.
4. Deeper orchestration and automation loops once execution connectors are mature.

This sequencing preserves the existing planning workflow while incrementally adding GUI control.

---

## Acceptance Criteria

1. CCDash remains the GUI/control plane and does not supersede file-backed planning artifacts as source of truth.
2. The design clearly defines how planning, execution, and workflow surfaces converge into one control plane.
3. Effective status, mismatch state, and orchestration launch preparation are all explicitly covered.
4. Worktree and multi-agent coordination are modeled as first-class concerns.
5. The architecture can be implemented on top of existing CCDash live-update, parsing, and execution foundations.
