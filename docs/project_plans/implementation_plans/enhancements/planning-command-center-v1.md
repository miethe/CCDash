---
schema_name: ccdash_document
schema_version: 3
doc_type: implementation_plan
doc_subtype: enhancement_implementation_plan
primary_doc_role: supporting_document
status: draft
category: enhancements
title: "Implementation Plan: Planning Command Center V1"
description: "Implement a planning portfolio console with searchable feature work items, deterministic next-command resolution, phase/worktree context, and launch/review controls."
summary: "Add a command-center aggregate API, centralized planning command resolver, live worktree/git state, and Planning UI views for list, card, and board workflows."
created: 2026-05-27
updated: 2026-05-27
priority: high
risk_level: high
complexity: High
track: Planning / Execution / Orchestration
timeline_estimate: "4-6 weeks across 6 phases"
feature_slug: planning-command-center-v1
feature_family: planning-command-center
feature_version: v1
lineage_family: planning-command-center
lineage_parent:
  ref: docs/project_plans/PRDs/enhancements/ccdash-planning-control-plane-v1.md
  kind: extension_of
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
  - command-center
  - execution
  - orchestration
  - worktrees
  - workflow
  - frontend
  - backend
prd: docs/project_plans/PRDs/enhancements/planning-command-center-v1.md
prd_ref: docs/project_plans/PRDs/enhancements/planning-command-center-v1.md
related:
  - docs/project_plans/PRDs/enhancements/planning-command-center-v1.md
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
  - docs/project_plans/design-specs/planning-collab-threads-v1.md
  - docs/project_plans/implementation_plans/enhancements/wireframes/planning-command-center-v1/list-view.png
  - docs/project_plans/implementation_plans/enhancements/wireframes/planning-command-center-v1/board-view.png
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
plan_ref: planning-command-center-v1
linked_sessions: []
request_log_id: ""
commits: []
prs: []
---

# Implementation Plan: Planning Command Center V1

## Objective

Implement a Planning Command Center that turns CCDash Planning into a portfolio-level execution console. The feature should show all active, planned, ready, blocked, and reviewable features; expose deterministic next-command guidance; show the exact plan or artifact path to operate against; surface phase, story point, related-file, launch-batch, worktree, branch, PR, and live git context; and support list, card, and board views.

## Current Baseline

The implementation should extend existing surfaces rather than replace them:

1. `PlanningHomePage` already owns the Planning landing route, summary metrics, active/planned columns, graph, tracker intake, quick view, and session board.
2. `ProjectBoard` already provides mature feature search/filter/sort, list/board view concepts, and feature modal reuse.
3. `FeatureExecutionWorkbench` already provides selected-feature next-command rendering, command copy/run affordances, execution context, phases, sessions, documents, and review/run controls.
4. `PhaseOperationsPanel` and `PlanningLaunchSheet` already expose phase operations, batches, provider/model/worktree selection, command override, and launch preparation.
5. Agent planning APIs already expose summary, graph, feature context, phase operations, session board, and next-run preview.
6. Execution APIs already expose run lifecycle, launch capability, launch prepare/start, and worktree-context CRUD.

## Scope Boundaries

1. This is a Planning portfolio console, not a replacement for `/execution`.
2. `/execution` remains the deep single-feature execution workspace.
3. Planning Command Center owns broad feature work-item discovery, command readiness, and multi-feature launch/review scanning.
4. Launch, approval, provider, model, and worktree mutation remain owned by execution services.
5. Markdown planning artifacts remain the source of truth.
6. Mutating quick commands must go through execution policy and capability checks.
7. Planning Reskin remains the owner of planning shell, density, tokens, route-local modals, and interaction/performance polish.
8. Planning Agent Session Board remains the owner of session grouping, feature lanes, correlation DTOs, and prompt context tray behavior.
9. Feature clicks should remain route-local by default, with full navigation to `/execution`, `/board`, or document detail as explicit secondary actions.

## Wireframes

1. List view: `docs/project_plans/implementation_plans/enhancements/wireframes/planning-command-center-v1/list-view.png`
2. Board view: `docs/project_plans/implementation_plans/enhancements/wireframes/planning-command-center-v1/board-view.png`

The annotated mockup requirements are treated as V1 acceptance drivers:

1. Review-ready example with PR, review agents, squash merge, and worktree closeout affordances.
2. Story points displayed as remaining/total.
3. Editable command field.
4. Launch dropdown for target-platform selection.
5. Per-file plus buttons to add files to command or launch context.
6. Compact collapsible git state.
7. Plan phase table/tree with phase files, model, agents, status, and details.
8. Expandable Launch Batch agents with skills, tools, and run state.

## Architecture

### Backend Services

Add a shared planning command resolver:

1. Proposed module: `backend/application/services/planning_command_resolver.py`
2. Responsibilities:
   - Determine command type from feature, docs, tier, phases, progress, and review state.
   - Return command, rule id, confidence, rationale, target artifact path, phase, warnings, alternatives, and required capabilities.
   - Support spike, explore, plan-feature, contract, execute-phase, complete-user-story, and quick-feature outputs.
   - Be callable by Feature Execution Workbench recommendation code, Planning next-run preview, Launch Preparation, and the new command-center endpoint.

Add a command-center query service:

1. Proposed module: `backend/application/services/agent_queries/planning_command_center.py`
2. Responsibilities:
   - Compose feature surface list results with planning summary/context, phase operations, worktree context, execution/review state, and command resolver output.
   - Avoid frontend N+1 calls for next-run preview.
   - Return paginated, sortable, filterable work-item DTOs.

Add a live git probe service:

1. Proposed module: `backend/application/services/worktree_git_state.py`
2. Responsibilities:
   - Probe only known worktree paths from worktree contexts.
   - Return path existence, HEAD, dirty count, stash count, upstream, ahead/behind, and last probe time.
   - Apply short timeouts and safe degradation.
   - Cache snapshots briefly to avoid expensive polling.

### API

Add agent planning endpoints:

1. `GET /api/agent/planning/command-center`
2. `GET /api/agent/planning/command-center/{feature_id}`
3. Optional: `POST /api/agent/planning/command-center/preview-command`

The list endpoint should accept:

1. `project_id`
2. `q`
3. `status`
4. `phase`
5. `tier`
6. `artifact_type`
7. `worktree_state`
8. `pr_state`
9. `launch_readiness`
10. `sort_by`
11. `sort_direction`
12. `page`
13. `page_size`

### Frontend Services

Add a Planning Command Center service module:

1. Proposed module: `services/planningCommandCenter.ts`
2. Responsibilities:
   - Type DTOs and API calls.
   - Serialize query state.
   - Cache feature detail/row expansions.
   - Integrate live invalidation topics.

Reuse:

1. `useFeatureSurface` query patterns for search/filter/sort conventions.
2. `services/planning.ts` cache patterns for planning context.
3. Existing live subscription helpers.

### Frontend Components

Add a component family under `components/Planning/CommandCenter/`:

1. `PlanningCommandCenter.tsx`
2. `CommandCenterToolbar.tsx`
3. `CommandCenterListView.tsx`
4. `CommandCenterBoardView.tsx`
5. `CommandCenterCardView.tsx`
6. `CommandCenterFeatureRow.tsx`
7. `CommandCenterFeatureCard.tsx`
8. `CommandCenterDetailPanel.tsx`
9. `EditableCommandField.tsx`
10. `RelatedFilesPicker.tsx`
11. `PhasePlanTable.tsx`
12. `PhaseProgressTree.tsx`
13. `WorktreeGitStatePanel.tsx`
14. `ReviewActionsPanel.tsx`
15. `QuickCommandBar.tsx`
16. `LaunchBatchAgentList.tsx`

Wire into `PlanningHomePage` as a main planning module or subroute. Prefer a subroute if the existing landing page would become too dense.

## Data Model

### `PlanningCommandCenterItem`

Required fields:

1. `feature`: id, slug, name, category, tags, priority, summary.
2. `status`: raw status, effective status, planning signal, mismatch state.
3. `tier`: tier number/name, estimated points.
4. `storyPoints`: total, remaining, completed.
5. `phase`: current phase, next phase, total phases, completed phases.
6. `artifacts`: specs, PRDs, plans, contracts, spikes, context files, reports.
7. `targetArtifact`: path, doc type, title, exists flag.
8. `command`: resolver output.
9. `relatedFiles`: file path, doc type, size, last modified, addable flag.
10. `phaseRows`: phase number, name, story points, phase files, domain, model, agents, status, details.
11. `launchBatch`: batch id, label, readiness, agents, queued/running state.
12. `worktree`: stored worktree context.
13. `gitState`: live git status snapshot.
14. `pullRequest`: provider, number, URL, state, review status.
15. `blockers`: count, labels, top reasons.
16. `lastActivity`: timestamp, actor, source.
17. `capabilities`: copy, launch, review, merge, cleanup, openPR, editCommand.

## Command Resolver Rules

Use explicit rule ids so the UI can explain every recommendation.

| Rule | Condition | Primary Command | Notes |
|---|---|---|---|
| `PCC-CMD-001` | Spike charter or spike-needed item | `/plan:spike <spike-charter-path>` | Use linked spike path when present. |
| `PCC-CMD-002` | Exploration charter or feasibility brief recommends more exploration | `/plan:explore <charter-path>` | Use recommended action from feasibility brief when present. |
| `PCC-CMD-003` | Spec, PRD, or report exists but implementation plan missing | `/plan:plan-feature <artifact-path>` | Prefer PRD, then spec/report. |
| `PCC-CMD-004` | Tier 1 feature contract ready | `/dev:execute-contract <contract-path>` | Capability-gated until command support is confirmed. |
| `PCC-CMD-005` | Plan exists and no phases completed | `/dev:execute-phase 1 <plan-path>` | Target phase 1. |
| `PCC-CMD-006` | A phase is active or in review | `/dev:execute-phase <active-phase> <plan-path>` | Resume active work. |
| `PCC-CMD-007` | Phase N complete and phase N+1 available | `/dev:execute-phase <N+1> <plan-path>` | Continue next phase. |
| `PCC-CMD-008` | All phases complete or review-ready | `/dev:complete-user-story <feature-id>` | Show PR/review alternatives when present. |
| `PCC-CMD-009` | No planning artifact found | `/dev:quick-feature <feature-id>` | Warning state. |

## Phase Breakdown

| Phase | Name | Story Points | Primary Owner | Parallelizable | Outcome |
|---|---:|---:|---|---|---|
| 1 | Contract and Resolver Foundation | 9 | backend-architect | Partial | Shared DTOs and resolver rules. |
| 2 | Aggregate API and Live Git State | 13 | python-backend-engineer | Yes | Paginated command-center endpoint with git snapshots. |
| 3 | List View and Expanded Row | 13 | frontend-developer | Yes | Dense list UX with editable command and related files. |
| 4 | Card/Board Views and Detail Panel | 11 | ui-engineer-enhanced | Yes | Board/card modes with collapsible right detail. |
| 5 | Launch, Review, Quick Commands | 10 | fullstack-engineering | Partial | Launch dropdown, review agents, PR/merge controls. |
| 6 | Validation, Accessibility, Docs, Rollout | 7 | task-completion-validator | Yes | Regression coverage, visual QA, docs, feature flag rollout. |

Total estimate: 63 story points.

## Phase 1: Contract and Resolver Foundation

Goal: Establish backend command resolution and DTO contracts before frontend work depends on them.

| ID | Task | Acceptance Criteria | Points | Assigned Subagents |
|---|---|---|---:|---|
| PCC-101 | Define command-center DTOs | Models cover feature summary, status, story points, phases, target artifact, command, files, launch batch, worktree, git state, PR, blockers, and capabilities. | 2 | backend-architect |
| PCC-102 | Add `PlanningCommandResolver` | Resolver produces rule id, command, target path, phase, confidence, rationale, warnings, alternatives, and required capabilities. | 3 | backend-architect, python-backend-engineer |
| PCC-103 | Migrate existing next-command callers conceptually | Feature Execution Workbench and planning next-run preview can call the resolver or have a documented migration path. | 1 | python-backend-engineer |
| PCC-104 | Add resolver tests | Tests cover spike, plan-feature, contract, execute phase 1, active phase, next phase, review/complete, and quick-feature fallback. | 2 | backend-test-engineer |
| PCC-105 | Confirm contract execution command support | Determine whether `/dev:execute-contract` exists; document fallback if not. | 1 | implementation-planner |

Quality gate:

1. Resolver tests pass.
2. No frontend code depends on command heuristics outside the resolver.
3. Open question for contract execution is resolved or represented as a capability warning.

## Phase 2: Aggregate API and Live Git State

Goal: Provide one efficient API for the command-center UI and avoid frontend N+1 composition.

| ID | Task | Acceptance Criteria | Points | Assigned Subagents |
|---|---|---|---:|---|
| PCC-201 | Add command-center query service | Service composes feature surface, planning context, phase rows, worktree context, execution state, and command resolver output. | 4 | python-backend-engineer |
| PCC-202 | Add paginated endpoint | `GET /api/agent/planning/command-center` supports project, search, filters, sort, and pagination. | 2 | python-backend-engineer |
| PCC-203 | Add feature detail endpoint | `GET /api/agent/planning/command-center/{feature_id}` returns expanded detail without overfetching the full list. | 2 | python-backend-engineer |
| PCC-204 | Add live git state probe | Safe git probe returns path exists, HEAD, dirty count, stash, upstream, ahead/behind, and last refresh. | 2 | backend-architect, python-backend-engineer |
| PCC-205 | Add live invalidation integration | Planning/feature/execution/worktree updates invalidate command-center caches and affected feature rows. | 1 | python-backend-engineer |
| PCC-206 | Add API tests | Tests cover list filters, resolver output inclusion, missing worktree degradation, and pagination. | 2 | backend-test-engineer |

Quality gate:

1. API can load 50 work items without per-row next-run preview calls.
2. Missing git/worktree state degrades without failing the row.
3. Endpoint respects active project context.

## Phase 3: List View and Expanded Row

Goal: Build the dense list experience represented by `list-view.png`.

| ID | Task | Acceptance Criteria | Points | Assigned Subagents |
|---|---|---|---:|---|
| PCC-301 | Add frontend service and types | `planningCommandCenter.ts` exposes list/detail calls and typed DTOs. | 2 | frontend-developer |
| PCC-302 | Add route/module shell | Planning Command Center appears under Planning with list/card/board toggle, filters, saved views, and live refresh state. | 2 | frontend-developer |
| PCC-303 | Build sortable list view | Table shows feature, status, phase, story points remaining/total, command, plan file, worktree/branch, blockers, activity, and actions. | 3 | frontend-developer, ui-engineer-enhanced |
| PCC-304 | Build expanded row | Expanded row shows editable command, launch dropdown, copy, related files, review controls, compact git state, and phase table. | 3 | frontend-developer, ui-engineer-enhanced |
| PCC-305 | Add related-file append behavior | Each related file has a plus button that appends path to command text or selected launch context. | 1 | frontend-developer |
| PCC-306 | Add list view tests | Tests cover filters, row expansion, command editing, file add buttons, and story point formatting. | 2 | frontend-test-engineer |

Quality gate:

1. List view can be used without opening Feature Execution Workbench.
2. Editable command changes are local until copied or launched.
3. Story points always display as remaining/total.

## Phase 4: Card/Board Views and Detail Panel

Goal: Build card and board modes represented by `board-view.png`.

| ID | Task | Acceptance Criteria | Points | Assigned Subagents |
|---|---|---|---:|---|
| PCC-401 | Build feature card component | Cards show status, phase progress, story points, artifacts, next command, copy, launch, branch, and worktree strip. | 2 | ui-engineer-enhanced |
| PCC-402 | Build board columns | Board supports Needs Plan, Ready to Execute, Active Phase, Blocked, and Review/Closeout columns. | 2 | frontend-developer |
| PCC-403 | Build card view | Card grid uses the same card component and filters as board/list. | 1 | frontend-developer |
| PCC-404 | Build right detail panel | Panel has collapsible sections for phase tree, command, rationale, files, launch batch, worktree, and quick commands. | 3 | ui-engineer-enhanced, frontend-developer |
| PCC-405 | Build phase tree and launch agents | Phase tree shows tasks/story points/wave-batch state; agents expand to model, skills, tools, and run status. | 2 | frontend-developer |
| PCC-406 | Add board/card tests | Tests cover view switching, card copy/run actions, detail panel sections, and keyboard navigation. | 1 | frontend-test-engineer |

Quality gate:

1. List, card, and board views are backed by the same query state and DTOs.
2. Detail sections are collapsible and accessible.
3. Board cards expose copy and launch actions directly.

## Phase 5: Launch, Review, Quick Commands

Goal: Make command-center actions operational while preserving existing execution guardrails.

| ID | Task | Acceptance Criteria | Points | Assigned Subagents |
|---|---|---|---:|---|
| PCC-501 | Integrate launch dropdown | Launch button supports `Launch with...` target selection and opens `PlanningLaunchSheet` with command override/context. | 2 | frontend-developer |
| PCC-502 | Add quick-command template model | Quick commands expose label, command template, required vars, capability, risk level, and applies-to filters. | 2 | backend-architect, python-backend-engineer |
| PCC-503 | Add review-ready controls | Review rows/cards show PR, run review agents, squash merge, and worktree exit affordances. | 2 | fullstack-engineering |
| PCC-504 | Add PR/worktree action wiring | PR links and worktree open actions work; mutating commands are policy/capability gated. | 2 | python-backend-engineer, frontend-developer |
| PCC-505 | Add action audit events | Launch, copy, quick command, review-agent, and merge-prep actions produce telemetry/audit events. | 1 | python-backend-engineer |
| PCC-506 | Add policy tests | Tests confirm unsupported launch/merge/review actions are disabled with clear reasons. | 1 | backend-test-engineer, frontend-test-engineer |

Quality gate:

1. No mutating quick command bypasses execution policy.
2. Review examples include PR and review-agent controls.
3. Launch uses existing provider/model/worktree capability checks.

## Phase 6: Validation, Accessibility, Docs, Rollout

Goal: Ship safely with visual, accessibility, performance, and regression coverage.

| ID | Task | Acceptance Criteria | Points | Assigned Subagents |
|---|---|---|---:|---|
| PCC-601 | Add frontend regression coverage | Vitest/RTL coverage for list, expanded row, board, detail panel, filters, command editing, and live invalidation. | 2 | frontend-test-engineer |
| PCC-602 | Add accessibility verification | Keyboard and screen-reader coverage for table expansion, board cards, detail panel, command editor, and launch dropdown. | 1 | web-accessibility-checker |
| PCC-603 | Add visual QA | Browser screenshots verify list and board views match wireframe intent at desktop and laptop widths. | 1 | ui-engineer-enhanced |
| PCC-604 | Add backend performance checks | API test or benchmark confirms 50-item load avoids N+1 command preview calls and stays within target latency. | 1 | backend-test-engineer |
| PCC-605 | Update docs | User docs explain Planning Command Center views, command rules, worktree state, quick commands, and review actions. | 1 | documentation-writer |
| PCC-606 | Feature flag rollout | Gate initial rollout behind a config flag or capability check, with graceful fallback to current Planning. | 1 | fullstack-engineering |

Quality gate:

1. Frontend and backend tests pass.
2. Visual screenshots cover list and board modes.
3. Accessibility checks pass for keyboard navigation and panel controls.
4. Docs are updated before enabling by default.

## Integration Points

### Existing Components to Reuse

1. `PlanningHomePage` for route placement, live invalidation, and planning shell.
2. `PlanningQuickViewPanel` for side-panel interaction patterns.
3. `PlanningNextRunPreview` for command preview UX patterns.
4. `PlanningLaunchSheet` for provider/model/worktree launch flow.
5. `PhaseOperationsPanel` for batch/task readiness semantics.
6. `ProjectBoard` for feature surface filters and board/list patterns.
7. `FeatureExecutionWorkbench` for command rationale and execution context patterns.
8. `PlanningAgentSessionBoard` for session grouping and prompt-context affordances.
9. `DocumentModal` for route-local artifact drill-in.
10. `planningRoutes.ts` for URL-backed planning modal/filter state.

### Existing Backend to Reuse

1. `FeatureListQuery` and feature surface listing for search/filter/sort.
2. `PlanningQueryService` for planning summary, feature context, phase operations, and next-run preview migration.
3. `feature_execution.build_execution_recommendation` as migration source for resolver rules.
4. `LaunchPreparationApplicationService` for launch command override and worktree context.
5. `worktree_contexts` repository for stored worktree metadata.
6. Live update topics for planning, feature, project, and execution invalidation.

## Validation Plan

Run targeted checks during implementation:

1. Backend unit tests for `PlanningCommandResolver`.
2. Backend API tests for command-center list/detail filters and pagination.
3. Frontend tests for toolbar filters, list expansion, card/board switching, detail panel, and launch dropdown.
4. Accessibility tests for keyboard flow and ARIA labels.
5. Browser visual checks for list and board layouts.
6. Existing regression tests around Planning, Project Board, Feature Execution Workbench, and Launch Sheet.

Suggested final gate:

```bash
npm test -- --run
pytest backend/tests -q
```

Adjust exact commands to the repo's current test scripts when implementation begins.

## Risks and Mitigations

1. Risk: The aggregate endpoint duplicates feature surface behavior.
   Mitigation: Reuse feature surface query/repository semantics and add planning-specific enrichment only.

2. Risk: Command resolver migration breaks Feature Execution Workbench.
   Mitigation: Add resolver tests that mirror current execution recommendation scenarios before changing callers.

3. Risk: Live git probes slow the endpoint.
   Mitigation: Fetch stored worktree metadata in list responses and load live git snapshots lazily or cached.

4. Risk: Board/detail UI becomes too dense.
   Mitigation: Keep sections collapsible, reuse compact tokens, and preserve list as the primary high-density view.

5. Risk: Quick commands mutate state unexpectedly.
   Mitigation: Treat quick commands as command templates routed through launch/policy checks, not raw shell execution.

## Open Questions

1. Confirm whether `/dev:execute-contract` is a supported slash command. If not, define a contract-execution resolver output that maps to the existing Tier 1 autonomous sprint workflow.
2. Decide whether saved views are local-only in V1 or persisted by project/user.
3. Decide whether PR state comes from local git metadata, GitHub integration, or both.
4. Decide whether command edits should persist as launch drafts or remain local to the current interaction.
5. Decide whether live git snapshots should be fetched on list load, row expansion, or explicit refresh.

## Done Criteria

1. PRD and plan are approved.
2. Command-center endpoint returns paginated, enriched work items.
3. Shared command resolver powers Planning Command Center and has a migration path for existing next-command callers.
4. List, card, and board views ship behind a flag or clear navigation path.
5. Expanded row and detail panel match the accepted wireframe behavior.
6. Worktree/git/PR state is visible and degrades safely.
7. Launch/review/quick commands are capability and policy gated.
8. Tests, visual QA, accessibility checks, and docs are complete.
