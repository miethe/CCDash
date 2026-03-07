---
doc_type: implementation_plan
status: in-progress
category: enhancements
title: 'Implementation Plan: Agentic SDLC Intelligence Foundation V1'
description: Implement the CCDash-side integration, normalization, scoring, and recommendation
  layers that connect live project telemetry to SkillMeat definitions.
author: codex
audience:
- ai-agents
- developers
- engineering-leads
- platform-engineering
created: 2026-03-07
updated: '2026-03-07'
tags:
- implementation
- analytics
- workflow
- recommendations
- skillmeat
- telemetry
feature_slug: agentic-sdlc-intelligence-foundation-v1
feature_family: agentic-sdlc-intelligence
lineage_family: agentic-sdlc-intelligence
lineage_parent: ''
lineage_children: []
lineage_type: iteration
linked_features:
- agentic-sdlc-intelligence-foundation-v1
prd: docs/project_plans/PRDs/enhancements/agentic-sdlc-intelligence-foundation-v1.md
prd_ref: docs/project_plans/PRDs/enhancements/agentic-sdlc-intelligence-foundation-v1.md
related:
- backend/db/sync_engine.py
- backend/db/sqlite_migrations.py
- backend/db/postgres_migrations.py
- backend/routers/analytics.py
- backend/routers/features.py
- backend/services/feature_execution.py
- backend/models.py
- services/analytics.ts
- services/execution.ts
- components/FeatureExecutionWorkbench.tsx
- docs/project_plans/implementation_plans/enhancements/wireframes/agentic-sdlc-intelligence/ASI-17-recommended-stack-card.png
- docs/project_plans/implementation_plans/enhancements/wireframes/agentic-sdlc-intelligence/ASI-18-workflow-effectiveness-view.png
- docs/project_plans/implementation_plans/enhancements/wireframes/agentic-sdlc-intelligence/ASI-19-similar-work-drilldown.png
- docs/project_plans/implementation_plans/enhancements/wireframes/agentic-sdlc-intelligence/ASI-20-definition-link-handling.png
plan_ref: agentic-sdlc-intelligence-foundation-v1
linked_sessions: []
request_log_id: ''
commits: [1d75483, b10d3e9]
prs: []
owner: platform-engineering
owners:
- platform-engineering
- ai-integrations
- fullstack-engineering
contributors:
- ai-agents
complexity: High
track: Foundation
timeline_estimate: 4-6 weeks across 6 phases
---

# Implementation Plan: Agentic SDLC Intelligence Foundation V1

## Objective

Implement the CCDash-side foundation for agentic SDLC intelligence:

1. resolve SkillMeat definitions,
2. normalize historical session behavior into observed stacks,
3. score workflow effectiveness from real outcomes,
4. and expose recommended stacks plus failure-pattern analytics in the app.

## Scope and Fixed Decisions

1. SkillMeat remains the canonical source for artifact, workflow, and context definitions.
2. CCDash performs read-only integration in this phase.
3. CCDash stores cached snapshots and derived analytics locally for speed and reproducibility.
4. Recommendations must be deterministic and evidence-backed.
5. V1 integrates into existing execution and analytics surfaces before adding any new orchestration behavior.

## Architecture

## 1) Integration Boundary

Add a SkillMeat integration client layer under the backend service tier.

Proposed modules:

1. `backend/services/integrations/skillmeat_client.py`
2. `backend/services/integrations/skillmeat_resolver.py`

Responsibilities:

1. fetch artifacts, workflows, and context modules from SkillMeat
2. normalize external payloads into CCDash-safe DTOs
3. cache snapshots and resolution metadata
4. fail gracefully when SkillMeat is unavailable

## 2) Definition Cache and Linkage Model

Add persistent storage for external definitions and resolution links.

Proposed tables:

1. `external_definition_sources`
   - project-scoped integration config
   - source kind (`skillmeat`)
   - base URL / project mapping / feature flags
2. `external_definitions`
   - source id
   - definition type (`artifact`, `workflow`, `context_module`)
   - external id
   - display name
   - version
   - raw snapshot JSON
   - fetched timestamp
3. `session_stack_observations`
   - session id
   - feature id
   - workflow ref
   - confidence
   - evidence JSON
4. `session_stack_components`
   - observation id
   - component type (`workflow`, `agent`, `skill`, `context_module`, `command`, `model_policy`)
   - explicit/inferred/resolved status
   - external definition FK when resolved
   - component payload JSON
5. `effectiveness_rollups`
   - scope type/id
   - period
   - metrics JSON
   - evidence summary JSON

Indexes:

1. `(project_id, definition_type, external_id)` on `external_definitions`
2. `(project_id, session_id)` on `session_stack_observations`
3. `(project_id, scope_type, scope_id, period)` on `effectiveness_rollups`

## 3) Observed Stack Extraction

Build a normalization pipeline that turns existing CCDash signals into stack observations.

Primary evidence sources:

1. `agentsUsed`
2. `skillsUsed`
3. linked artifacts from session parsing
4. session metadata and command mappings
5. execution workbench command recommendations and launch records
6. session forensics, including queue pressure, subagent topology, and test execution

Matching strategy:

1. explicit references from parsed artifacts/log metadata
2. deterministic name/ID matching against resolved SkillMeat definitions
3. workflow candidate inference from command sequences and component combinations
4. unresolved local-only observations when no SkillMeat match exists

## 4) Effectiveness Engine

Add a scoring service that computes outcome metrics from existing CCDash data.

Proposed module:

1. `backend/services/workflow_effectiveness.py`

Signals to combine:

1. feature progression and terminal state changes
2. test execution deltas and integrity signals
3. follow-on debug sessions and retries
4. queue pressure and subagent waste
5. cost and token efficiency
6. file churn / rework proxies

Primary outputs:

1. `successScore`
2. `efficiencyScore`
3. `qualityScore`
4. `riskScore`
5. `evidenceSummary`

## 5) Recommendation Service

Extend the existing execution recommendation pattern into stack recommendations.

Likely integration point:

1. expand `backend/services/feature_execution.py`

Proposed response additions:

1. `recommendedStack`
2. `stackAlternatives`
3. `stackEvidence`
4. `definitionResolutionWarnings`

Recommendation strategy:

1. preserve current command recommendation rules
2. augment those rules with historical stack effectiveness
3. prefer resolved SkillMeat definitions when confidence is sufficient
4. fall back to CCDash-only local patterns when not

## 6) UI Surfaces

Primary V1 surfaces:

1. Feature Execution Workbench
2. analytics/workflow effectiveness surface
3. feature/session detail drill-downs where stack evidence adds value

Expected UI additions:

1. recommended stack card
2. resolved SkillMeat definition chips/links
3. effectiveness metrics summary
4. failure-pattern drill-down
5. similar-work evidence list

## API Surface

Add or extend endpoints for:

1. `GET /api/features/{feature_id}/execution-context`
   - add recommended stack and stack evidence
2. `GET /api/analytics/workflow-effectiveness`
   - rollups by workflow, agent, skill, context module, stack family
3. `GET /api/analytics/failure-patterns`
   - ranked low-yield patterns with evidence
4. `GET /api/sessions/similar`
   - similar-work retrieval for a session or feature context
5. `POST /api/integrations/skillmeat/sync`
   - on-demand definition sync for current project
6. `GET /api/integrations/skillmeat/definitions`
   - cached definition catalog and sync metadata

## Phase Breakdown

## Phase 1: SkillMeat integration contract and definition cache

Objective:

Establish CCDash-side project settings, client code, and persistent snapshots for SkillMeat definitions.

| Task ID | Task Name | Description | Acceptance Criteria | Estimate (pts) | Assigned Subagent(s) |
| --- | --- | --- | --- | --- | --- |
| ASI-1 | Project integration settings | Add project-scoped settings for SkillMeat enablement, base URL, and project/workspace mapping. | Settings persist and can be retrieved through existing project config flow. | 2 | python-backend-engineer, backend-architect |
| ASI-2 | SkillMeat client | Implement read-only client for artifacts, workflows, and context modules with timeout/error handling. | Client can fetch definitions and returns normalized DTOs for all three definition types. | 3 | python-backend-engineer |
| ASI-3 | Definition cache schema | Add DB tables and repositories for external definition sources and snapshots in SQLite/Postgres parity. | Migrations succeed and repositories support upsert/list/get by project and external id. | 3 | data-layer-expert, backend-architect |
| ASI-4 | On-demand sync endpoint | Add endpoint/service for syncing SkillMeat definitions into CCDash cache. | Sync endpoint returns counts, timestamps, and non-fatal warning details. | 2 | python-backend-engineer |

Quality gates:

1. SQLite and Postgres migrations stay in parity.
2. Sync path works without crashing when SkillMeat is unavailable.
3. Definition snapshots preserve version and raw payload provenance.

## Phase 2: Observed stack extraction and resolution

Objective:

Normalize historical session evidence into reusable stack observations.

| Task ID | Task Name | Description | Acceptance Criteria | Estimate (pts) | Assigned Subagent(s) |
| --- | --- | --- | --- | --- | --- |
| ASI-5 | Observation schema | Add tables/models for stack observations and stack components. | Session observations can store explicit, inferred, and resolved component records. | 3 | data-layer-expert, python-backend-engineer |
| ASI-6 | Session evidence extractor | Build extractor over session rows, linked artifacts, commands, and badges to emit candidate stack observations. | Historical sessions produce observations with confidence and evidence JSON. | 3 | python-backend-engineer |
| ASI-7 | Definition resolver | Match observed components to cached SkillMeat definitions with deterministic resolution rules. | Components are marked resolved/unresolved with confidence and source attribution. | 3 | backend-architect, python-backend-engineer |
| ASI-8 | Backfill job | Add project-level backfill path for historical stack observations. | Existing sessions can be backfilled without full re-sync of unrelated entities. | 2 | python-backend-engineer |

Quality gates:

1. Resolution rules are deterministic and tested.
2. Unmatched local patterns are retained instead of dropped.
3. Backfill can run incrementally for large session sets.

## Phase 3: Effectiveness scoring and derived analytics

Objective:

Compute usable effectiveness metrics from existing telemetry and correlation data.

| Task ID | Task Name | Description | Acceptance Criteria | Estimate (pts) | Assigned Subagent(s) |
| --- | --- | --- | --- | --- | --- |
| ASI-9 | Outcome metric contract | Define metric formulas for success, efficiency, quality, and risk using existing CCDash signals. | Metric definitions are documented in code and produce stable outputs on fixtures. | 2 | backend-architect |
| ASI-10 | Effectiveness service | Implement scoring engine and materialized rollup generation for workflow/agent/skill/context/stack scopes. | Service produces rollups by requested scope and period with evidence summaries. | 4 | python-backend-engineer, backend-architect |
| ASI-11 | Failure pattern detector | Identify repeated low-yield patterns such as queue waste, repeated debug loops, or weak validation paths. | Detector returns ranked patterns with enough evidence to explain why they were flagged. | 3 | python-backend-engineer |
| ASI-12 | Analytics endpoints | Add workflow-effectiveness and failure-pattern endpoints. | API returns filtered rollups with project/feature/date filters and tests cover major scopes. | 3 | python-backend-engineer |

Quality gates:

1. Metrics are explainable from underlying evidence.
2. Rollups can be recomputed deterministically.
3. Failure-pattern outputs avoid opaque labels without evidence.

## Phase 4: Recommended stack service and execution-context integration

Objective:

Join feature-state rules with historical effectiveness to recommend the next stack.

| Task ID | Task Name | Description | Acceptance Criteria | Estimate (pts) | Assigned Subagent(s) |
| --- | --- | --- | --- | --- | --- |
| ASI-13 | Recommendation DTOs | Extend backend/frontend types with recommended stack, alternatives, evidence, and warnings. | Execution-context payload supports stack recommendation fields without breaking existing command recommendation clients. | 2 | python-backend-engineer, frontend-developer |
| ASI-14 | Stack recommender | Implement deterministic recommender that merges feature rules with historical effectiveness and definition resolution. | Feature contexts return primary stack plus alternatives and evidence references. | 4 | backend-architect, python-backend-engineer |
| ASI-15 | Similar-work retrieval | Add service/query for similar historical sessions/features used in recommendation evidence. | Recommendation payload can include similar-work examples with similarity reasons. | 3 | python-backend-engineer |
| ASI-16 | Execution-context integration | Wire recommended stack into existing feature execution context endpoint and tests. | Workbench payload exposes command recommendation plus stack recommendation together. | 2 | python-backend-engineer |

Quality gates:

1. Existing command recommendations remain intact.
2. Stack recommendations degrade cleanly when no SkillMeat definitions resolve.
3. Similar-work results are relevant and bounded.

## Phase 5: UI surfaces and navigation

Objective:

Expose the intelligence layer in the places users already make execution decisions.

### Wireframes

Reference wireframes were scaffolded via Gemini (nano-banana) and live under `docs/project_plans/implementation_plans/enhancements/wireframes/agentic-sdlc-intelligence/`. Implementing agents MUST use these as the primary visual reference for layout, component structure, and interaction states.

| Task ID | Wireframe | Description |
| --- | --- | --- |
| ASI-17 | [`ASI-17-recommended-stack-card.png`](wireframes/agentic-sdlc-intelligence/ASI-17-recommended-stack-card.png) | Recommended stack card with confidence badge, primary stack components as pill chips, collapsible alternatives with effectiveness scores, and evidence links to past sessions. |
| ASI-18 | [`ASI-18-workflow-effectiveness-view.png`](wireframes/agentic-sdlc-intelligence/ASI-18-workflow-effectiveness-view.png) | Full-page analytics view with scope/period filters, summary stat cards, scored data table with progress bars, and failure patterns sidebar. |
| ASI-19 | [`ASI-19-similar-work-drilldown.png`](wireframes/agentic-sdlc-intelligence/ASI-19-similar-work-drilldown.png) | Modal overlay listing similar past sessions with similarity scores, matched component chips, outcome indicators, key metrics, and session deep links. |
| ASI-20 | [`ASI-20-definition-link-handling.png`](wireframes/agentic-sdlc-intelligence/ASI-20-definition-link-handling.png) | Three definition link states (resolved/unresolved/cached) with status dots, tooltips, hover popovers for cached metadata, and inline workbench reference panel. |

### Tasks

| Task ID | Task Name | Description | Acceptance Criteria | Estimate (pts) | Assigned Subagent(s) | Wireframe Ref |
| --- | --- | --- | --- | --- | --- | --- |
| ASI-17 | Workbench recommended stack UI | Add recommended stack card, alternative stacks, evidence, and deep links in the execution workbench. | Users can see resolved SkillMeat refs, stack rationale, and command alignment from one surface. Layout matches wireframe. | 3 | frontend-developer, ui-engineer-enhanced | `ASI-17-recommended-stack-card.png` |
| ASI-18 | Workflow effectiveness view | Add analytics UI for workflow/agent/skill/context effectiveness and failure patterns. | Users can filter and compare effectiveness across scopes without leaving CCDash. Layout matches wireframe. | 4 | frontend-developer, ui-engineer-enhanced | `ASI-18-workflow-effectiveness-view.png` |
| ASI-19 | Similar-work drill-down | Add linked prior-work panel or modal from recommendations. | Users can inspect why a previous session/stack is being suggested. Modal layout matches wireframe. | 2 | frontend-developer | `ASI-19-similar-work-drilldown.png` |
| ASI-20 | Definition link handling | Add safe deep-link/open behaviors for artifacts, workflows, and context modules. | Resolved references open the correct SkillMeat destination or show cached metadata when direct deep link is unavailable. Chip states match wireframe. | 2 | frontend-developer | `ASI-20-definition-link-handling.png` |

Quality gates:

1. UI remains usable when integration is disabled or partially unavailable.
2. Recommendation surfaces show warnings instead of blank states.
3. Link behavior is consistent across artifact/workflow/context definitions.

## Phase 6: Backfill, telemetry, hardening, and rollout

Objective:

Make the feature operational for real project data and safe to evolve.

| Task ID | Task Name | Description | Acceptance Criteria | Estimate (pts) | Assigned Subagent(s) |
| --- | --- | --- | --- | --- | --- |
| ASI-21 | Backfill and recomputation tooling | Add commands/jobs to sync definitions, backfill observations, and recompute rollups. | Operators can initialize pilot data without manual DB edits. | 2 | python-backend-engineer |
| ASI-22 | Feature flags and config guards | Add kill switches for SkillMeat integration, recommendation UI, and effectiveness endpoints. | Features can be disabled cleanly per env/project scope. | 2 | python-backend-engineer |
| ASI-23 | Test coverage | Add unit/integration tests across migrations, sync, extraction, scoring, recommendation, and UI. | Critical paths have automated coverage and regression fixtures. | 3 | python-backend-engineer, frontend-developer |
| ASI-24 | Documentation and pilot rollout | Add developer/operator guidance for setup, sync, and interpretation of scores. | Pilot rollout checklist and setup notes are available in repo docs. | 1 | documentation-writer |

Quality gates:

1. Historical recomputation is idempotent.
2. Feature flags can disable the full surface quickly.
3. Pilot docs are sufficient for internal rollout.

## Testing Plan

## Unit Tests

1. SkillMeat definition normalization and caching.
2. Observation extraction and resolution rules.
3. Effectiveness score formulas and evidence generation.
4. Recommended stack ranking and fallback behavior.

## Integration Tests

1. project sync -> definition cache -> observation backfill -> effectiveness query
2. execution-context endpoint with and without SkillMeat availability
3. analytics filters for workflow, agent, skill, context, and stack family

## UI Tests

1. recommended stack rendering in execution workbench
2. failure-pattern and effectiveness filters
3. deep-link and cached-definition fallback behavior

## Rollout Notes

1. Start with one internal project mapping to SkillMeat.
2. Sync definitions and backfill stack observations for that project.
3. Validate recommendation quality against recent manually known-good workflows.
4. Expand to additional projects after scoring and resolution rules stabilize.

## Open Items to Resolve Before Implementation Starts

1. Final SkillMeat auth and connection model for local vs hosted use.
2. Canonical CCDash project -> SkillMeat project/workspace mapping.
3. Whether model policy should be represented as a first-class stack component without a SkillMeat artifact id.
4. Exact deep-link destinations for workflow and context module records in SkillMeat UI.
