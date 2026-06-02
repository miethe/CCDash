---
schema_name: ccdash_document
schema_version: 3
doc_type: prd
doc_subtype: enhancement_prd
status: completed
category: enhancements
title: 'PRD: Planning Command Center V1'
description: Add a planning portfolio console that shows all active, planned, ready,
  blocked, and reviewable features with deterministic next-command guidance, plan
  context, worktree state, and launch controls.
summary: Consolidate existing Planning, Project Board, Feature Execution Workbench,
  phase operations, and worktree launch capabilities into one searchable Planning
  Command Center for managing many features at once.
created: 2026-05-27
updated: '2026-06-01'
priority: high
risk_level: high
complexity: High
track: Planning / Execution / Orchestration
timeline_estimate: 4-6 weeks across 6 phases
feature_slug: planning-command-center-v1
feature_family: planning-command-center
feature_version: v1
lineage_family: planning-command-center
lineage_parent: docs/project_plans/PRDs/enhancements/ccdash-planning-control-plane-v1.md
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
- developers
- platform-engineering
- engineering-leads
- workflow-authors
- ai-agents
tags:
- prd
- planning
- command-center
- execution
- orchestration
- worktrees
- workflow
- frontend
- backend
linked_features:
- ccdash-planning-control-plane-v1
- feature-execution-workbench-v1
- planning-agent-session-board-v1
related_documents:
- docs/project_plans/PRDs/enhancements/ccdash-planning-control-plane-v1.md
- docs/project_plans/implementation_plans/enhancements/ccdash-planning-control-plane-v1.md
- docs/project_plans/PRDs/enhancements/feature-execution-workbench-v1.md
- docs/project_plans/implementation_plans/enhancements/feature-execution-workbench-v1.md
- docs/project_plans/PRDs/enhancements/planning-agent-session-board-v1.md
- docs/project_plans/implementation_plans/enhancements/planning-agent-session-board-v1.md
- docs/project_plans/PRDs/enhancements/ccdash-planning-reskin-v2.md
- docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md
- docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2-interaction-performance-addendum-v1.md
- docs/project_plans/design-specs/ccdash-planning-control-plane-architecture.md
- docs/project_plans/design-specs/spike-execution-wiring-v1.md
- docs/project_plans/design-specs/spec-creation-workflow-v1.md
- docs/project_plans/implementation_plans/enhancements/wireframes/planning-command-center-v1/list-view.png
- docs/project_plans/implementation_plans/enhancements/wireframes/planning-command-center-v1/board-view.png
context_files:
- App.tsx
- services/planningRoutes.ts
- components/Planning/PlanningHomePage.tsx
- components/Planning/PlanningAgentSessionBoard.tsx
- components/Planning/PlanningLaunchSheet.tsx
- components/Planning/PlanningNextRunPreview.tsx
- components/Planning/PlanningQuickViewPanel.tsx
- components/Planning/primitives/PhaseOperationsPanel.tsx
- components/ProjectBoard.tsx
- components/FeatureExecutionWorkbench.tsx
- components/DocumentModal.tsx
- services/useFeatureSurface.ts
- services/featureSurface.ts
- services/planning.ts
- backend/application/services/agent_queries/planning.py
- backend/application/services/agent_queries/planning_sessions.py
- backend/application/services/agent_queries/cache.py
- backend/application/services/launch_preparation.py
- backend/services/feature_execution.py
- backend/db/repositories/worktree_contexts.py
- backend/routers/agent.py
- backend/routers/execution.py
- backend/routers/live.py
implementation_plan_ref: docs/project_plans/implementation_plans/enhancements/planning-command-center-v1.md
---

# PRD: Planning Command Center V1

## Executive Summary

Planning Command Center V1 adds a portfolio-level operational console inside CCDash Planning. It shows every currently active, planned, ready, blocked, and review/closeout feature in one searchable, sortable, filterable surface. Operators can switch between list, card, and board views, expand any feature, inspect the next recommended command, edit launch text, attach related files, inspect phase and worktree state, and launch or copy the next action.

The feature does not replace Planning Control Plane, Planning Reskin, Project Board, Feature Execution Workbench, or Planning Agent Session Board. It consolidates their useful capabilities into a planning-native "many features at once" cockpit. The core new work is an aggregate planning command-center data contract and a shared command resolver that makes command choice deterministic across Planning, Execution, and launch preparation.

## Current State

CCDash already has most of the building blocks:

1. `/planning` shows planning health, active plans, planned features, graph, tracker intake, and agent sessions.
2. `/board` already has mature feature search, filter, sort, board/list views, and feature modal patterns.
3. `/execution` has feature-level next-command recommendation UX and run controls.
4. Planning phase operations expose batches, task groups, dependency state, launch readiness, and launch sheet integration.
5. Worktree context records exist and can be selected or created during launch.
6. Live update topics exist for feature, planning, project, and execution invalidation.
7. Planning Reskin already owns the visual shell, tokens, triage, metrics, density, route-local modal behavior, and active-first loading expectations.
8. Planning Agent Session Board already owns session grouping, feature lanes, next-run preview, and prompt context tray behavior.

The missing layer is the portfolio console: a single planning page that treats features as executable work items and lets operators manage multi-agent workflows across many features without drilling one feature at a time.

## Problem Statement

Operators can answer "what should I do next for this one feature?" by opening Feature Execution Workbench, and they can answer "what planning artifacts exist?" by using Planning. They cannot efficiently answer:

1. Which active or planned features are ready to run right now?
2. Which ones need PRD, plan, spike, contract, phase execution, review, or closeout?
3. Which plan path and phase should the next command operate against?
4. Which worktree, branch, PR, and git state belong to each feature?
5. Which files should be added to the next launch context?
6. Which review agents or quick commands should be run after implementation?

This creates avoidable context switching, inconsistent slash-command choice, and manual worktree hygiene for multi-agent execution.

## Goals

1. Show all active, planned, ready, blocked, and reviewable features in a single Planning Command Center.
2. Provide list, card, and board views with consistent search, sort, filters, saved views, and live updates.
3. Show deterministic next-command guidance for each feature using centralized planning workflow logic.
4. Show the specific artifact path that the command should operate against, including PRD, plan, spike, or contract paths.
5. Show current phase, next phase, phase table details, story points remaining/total, task/batch state, and phase completion evidence.
6. Show worktree, branch, PR, and live git state close to command execution controls.
7. Let operators copy, edit, or launch a command with target-platform selection.
8. Support review/closeout workflows with PR links, review-agent controls, squash-merge guidance, and worktree exit commands.
9. Reuse existing Planning, Feature Surface, Execution Workbench, Phase Operations, Launch Sheet, and live-update primitives.

## Non-Goals

1. Replacing markdown and frontmatter planning artifacts as source of truth.
2. Building a generic project-management board unrelated to CCDash planning workflows.
3. Bypassing execution policy, approval, launch capability checks, or audit logging.
4. Full in-app PRD or implementation-plan authoring in V1.
5. Real-time collaborative editing of planning artifacts.
6. General-purpose git client features beyond feature/worktree status required for safe execution.

## Scope Boundaries

1. Planning Control Plane remains the owner of `/planning`, planning graph, raw/effective status, mismatch provenance, phase operations, tracker intake, and launch preparation.
2. Planning Reskin remains the owner of planning tokens, density, shell layout, graph lanes, route-local modal behavior, and interaction/performance polish.
3. Feature Execution Workbench remains the owner of deep single-feature execution context, local terminal execution, provider connectors, and run lifecycle detail.
4. Planning Agent Session Board remains the owner of session grouping, feature lanes, correlation DTOs, and prompt context composition.
5. Planning Command Center should link into those surfaces and reuse their contracts. It should not fork replacement primitives.
6. Markdown/frontmatter artifacts remain canonical; V1 must not introduce a second planning database or generic PM model.
7. Feature clicks should stay route-local when possible, opening the planning-hosted shared feature modal or detail panel. Full navigation should be an explicit secondary action.

## Users and Jobs to Be Done

1. AI workflow operator: "Show me every feature that is ready for the next agent run, and give me the exact command."
2. Engineering lead: "Scan active and planned work by status, story points, blocker count, PR state, and phase readiness."
3. Implementation agent coordinator: "Attach the right files, choose launch platform/model/worktree, and start the next batch."
4. Reviewer: "Find review-ready features, run review agents, and squash merge completed work back to the feature branch."
5. Maintainer: "Identify stale worktrees, dirty branches, missing PRs, and blocked features before launching more agents."

## Functional Requirements

### FR-1: Planning Command Center Route and Placement

1. Add a Planning Command Center view under the Planning section.
2. The view may be the primary content below Planning summary metrics or a subroute such as `/planning/command-center`.
3. Navigation should make the relationship clear: this is a Planning portfolio execution console, not the single-feature `/execution` workbench.
4. The existing Planning dashboard, graph, tracker intake, and agent session board must remain available.

### FR-2: Portfolio Feature Scope

1. Include features whose effective planning status is active, in progress, planned, approved, ready, blocked, review, or closeout.
2. Include features with PRD/spec/report but no plan when they need `/plan:plan-feature`.
3. Include spikes and pre-commitment exploration artifacts when they map to feature candidates or planning work items.
4. Include Tier 1 feature contracts when they are ready for contract execution.
5. Exclude completed and archived features by default, but allow saved filters to show them.

### FR-3: Search, Sort, Filters, and Saved Views

The console must support:

1. Text search by feature name, feature id, slug, document path, branch, PR, owner, or tag.
2. Filters for status, planning signal, phase, owner, milestone, artifact type, tier, blocker state, worktree state, PR state, and launch readiness.
3. Sorting by last activity, priority, status, story points remaining, blocker count, phase number, updated time, and command type.
4. Saved views that persist selected filters and view mode.
5. URL-addressable state for filters, selected feature, expanded row, and view mode.

### FR-4: List View

The list view must provide a dense sortable table with columns:

1. Feature.
2. Status.
3. Phase.
4. Story points as remaining/total, for example `5 / 13 SP`.
5. Next command.
6. Plan file or relevant target artifact.
7. Worktree/branch.
8. Blockers.
9. Last activity.
10. Actions.

Rows must be expandable. The expanded row must show:

1. Editable next-command field.
2. Launch with target dropdown.
3. Copy command.
4. Related files with a plus button per file to add it to the command or launch context.
5. Review example controls when review-ready: PR badge/link, run review agents, squash merge, and worktree exit affordance.
6. Collapsible git state in a compact top-right section.
7. Phase table for the plan with phase number, phase name, story points, phase files, domain, model, agents, status, and details.

### FR-5: Card and Board Views

The card view and board view must reuse the same underlying data as the list view.

Board columns should support at least:

1. Needs Plan.
2. Ready to Execute.
3. Active Phase.
4. Blocked.
5. Review/Closeout.

Feature cards must show:

1. Feature name and status.
2. Phase progress.
3. Story points remaining/total.
4. Artifact and blocker indicators.
5. Next command chip.
6. Copy command action.
7. Execute or launch action.
8. Branch and worktree mini-strip.

### FR-6: Detail Panel

Selecting a feature in card or board view opens a right-side detail panel. The panel must include collapsible sections for:

1. Phase progress tree.
2. Next command.
3. Command rationale.
4. Related files.
5. Launch batch.
6. Worktree live git status.
7. Quick commands.

The phase progress tree must show phase tasks, story points, wave/batch plans, and status. Agent rows in Launch Batch must expand to show assigned model, skills, tools, run state, and queued/running status.

### FR-7: Command Resolution

Command resolution must be centralized so Planning Command Center, Feature Execution Workbench, next-run preview, and launch preparation agree.

Minimum V1 command matrix:

1. Spike charter or spike-needed item: `/plan:spike <spike-charter-path>`.
2. Exploration charter with follow-up needed: `/plan:explore <charter-path>` or recommended action from feasibility brief.
3. Spec, PRD, or report without implementation plan: `/plan:plan-feature <artifact-path>`.
4. Tier 1 feature contract: `/dev:execute-contract <contract-path>` if supported, otherwise a capability-gated contract execution command with an explicit warning.
5. Tier 2/3 plan with no completed phase: `/dev:execute-phase 1 <plan-path>`.
6. Tier 2/3 plan with active phase: `/dev:execute-phase <active-phase> <plan-path>`.
7. Tier 2/3 plan with completed phase N and incomplete phase N+1: `/dev:execute-phase <N+1> <plan-path>`.
8. Review-ready or all phases complete: `/dev:complete-user-story <feature-id>` or review/closeout command when the feature has an open PR.
9. Ambiguous feature with no planning artifact: `/dev:quick-feature <feature-id>` with a warning badge.

Each command recommendation must expose:

1. Command string.
2. Rule id.
3. Confidence.
4. Rationale.
5. Target artifact path.
6. Target phase number where applicable.
7. Required capabilities.
8. Warnings.
9. Alternative commands.

### FR-8: Worktree, Branch, PR, and Git State

The console must show stored worktree context and live git state where available:

1. Worktree path.
2. Branch.
3. Base branch and base SHA.
4. Current HEAD.
5. Dirty file count.
6. Stash count.
7. Ahead/behind state.
8. Upstream presence.
9. PR URL/number if available.
10. Last refresh time.
11. Worktree existence on disk.

Live git status must be compact and collapsible. It should not dominate command or phase details.

### FR-9: Quick Commands

The console must support configurable quick-command templates. V1 templates should include:

1. Copy next command.
2. Launch with selected platform.
3. Run review agents.
4. Squash merge to feature branch.
5. Exit or clean up worktree after merge.
6. Run validation gate.
7. Open PR or open existing PR.

Quick commands must pass through execution policy and capability checks before launch.

### FR-10: Visual and Interaction Requirements

1. Use the existing CCDash dark planning visual language and planning tokens.
2. Keep the page dense and operational, not marketing-oriented.
3. Do not use nested cards for the main table/detail composition.
4. Use familiar icon buttons for copy, launch, expand/collapse, open, and add-file actions.
5. Keep panels, rows, and cards readable at laptop widths.
6. Preserve keyboard navigation for filter controls, row expansion, board cards, and detail panel sections.
7. Maintain accessible labels and focus behavior for command editing and launch actions.

## Wireframes

The V1 wireframes live with the implementation plan:

1. `docs/project_plans/implementation_plans/enhancements/wireframes/planning-command-center-v1/list-view.png`
2. `docs/project_plans/implementation_plans/enhancements/wireframes/planning-command-center-v1/board-view.png`

The annotated changes incorporated into these wireframes are requirements for V1:

1. Review example row with PR, review agents, squash merge, and worktree closeout affordances.
2. Story points as remaining/total.
3. Editable command text field.
4. Launch dropdown for target platform selection.
5. Per-file add-to-command controls.
6. Compact collapsible git state.
7. Phase table/tree with phase files, agents, model, status, and details.
8. Expandable agent details showing model, skills, tools, and run state.

## Data Contract Requirements

V1 should expose an aggregate feature work item DTO instead of requiring the frontend to stitch together many endpoints.

Recommended endpoint:

`GET /api/agent/planning/command-center`

Required query support:

1. `project_id`.
2. `q`.
3. `status`.
4. `phase`.
5. `tier`.
6. `artifact_type`.
7. `worktree_state`.
8. `pr_state`.
9. `launch_readiness`.
10. `sort_by`.
11. `sort_direction`.
12. `page`.
13. `page_size`.

Each returned work item should include:

1. Feature summary.
2. Effective and raw planning status.
3. Planning signal badges.
4. Tier and story points.
5. Current phase and next phase.
6. Plan path and target artifact path.
7. Linked artifact summaries.
8. Phase summaries and phase table rows.
9. Blocker summary.
10. Next command recommendation.
11. Related files.
12. Launch batch summary.
13. Worktree context.
14. Live git state.
15. PR summary.
16. Latest activity.
17. Actions/capabilities.

## Acceptance Criteria

1. Planning Command Center can show at least 50 active/planned features without N+1 next-run preview calls.
2. List, card, and board views render from the same normalized data model.
3. Operators can search, filter, sort, and save views for active/planned/ready/blocked/review work.
4. Expanding a feature shows an editable next-command field and target artifact path.
5. Related files can be added to launch context or command text with a plus button.
6. Story points are displayed as remaining/total wherever feature or phase points are shown.
7. Review-ready examples show PR, review-agent, squash-merge, and closeout affordances.
8. Phase details show phase number, name, story points, phase files, domain, model, agents, status, and validation/commit details when available.
9. Board cards expose copy and launch actions for the next command.
10. Right detail panel sections are collapsible and keyboard accessible.
11. Worktree state includes live git probe fields where available and degrades clearly when unavailable.
12. Command recommendations are produced by one backend resolver shared by Planning and Execution.
13. Launch actions remain subject to existing launch capability, provider, approval, and execution policy checks.
14. Existing Planning dashboard, Feature Execution Workbench, Project Board, and Session Board behavior does not regress.

## Risks and Mitigations

1. Risk: The frontend becomes a fragile join layer across many endpoints.
   Mitigation: Add a backend aggregate endpoint with a stable DTO and pagination.

2. Risk: Command guidance diverges between Planning and Execution.
   Mitigation: Centralize command resolution behind a shared service and migrate existing callers.

3. Risk: Live git probes become slow or unsafe.
   Mitigation: Probe only known worktree paths, set timeouts, cache short-lived snapshots, and degrade to stored context.

4. Risk: Quick commands can mutate branches or worktrees without enough guardrails.
   Mitigation: Route mutating actions through execution policy checks, confirmation, and audit events.

5. Risk: The page becomes too dense for routine use.
   Mitigation: Use view modes, saved views, collapsible sections, progressive disclosure, and density controls.

## Open Questions

1. Is `/dev:execute-contract <contract-path>` an actual supported command, or should V1 define a contract-execution resolver output that maps to an existing autonomous sprint workflow?
2. Should `/plan:explore` items appear in the same console as feature work items, or only after they produce a go/conditional feasibility brief?
3. Which git provider fields can be sourced locally versus from GitHub integration in V1?
4. Should saved views be local browser preferences first, or persisted per user/project?
5. Should quick-command templates be config-file-backed, DB-backed, or hardcoded behind feature flags for V1?

## Out of Scope Follow-Ups

1. Drag-and-drop status mutation on the board.
2. Full planning artifact editing.
3. Cross-project portfolio command center.
4. GitHub PR merge automation beyond preparing/recommending guarded commands.
5. Historical command effectiveness analytics.
