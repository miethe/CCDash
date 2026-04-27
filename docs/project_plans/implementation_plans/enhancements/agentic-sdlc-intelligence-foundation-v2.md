---
doc_type: implementation_plan
status: completed
category: enhancements
title: 'Implementation Plan: Agentic SDLC Intelligence Foundation V2'
description: Contract-align the current CCDash SkillMeat integration and extend it
  with auth-aware settings, effective workflow resolution, bundle/context-pack integration,
  and workflow execution awareness.
author: codex
audience:
- ai-agents
- developers
- engineering-leads
- platform-engineering
created: 2026-03-08
updated: '2026-04-27'
tags:
- implementation
- analytics
- workflow
- recommendations
- skillmeat
- telemetry
- contract-alignment
feature_slug: agentic-sdlc-intelligence-foundation-v2
feature_family: agentic-sdlc-intelligence
lineage_family: agentic-sdlc-intelligence
lineage_parent: docs/project_plans/implementation_plans/enhancements/agentic-sdlc-intelligence-foundation-v1.md
lineage_children: []
lineage_type: iteration
linked_features:
- agentic-sdlc-intelligence-foundation-v1
prd: docs/project_plans/PRDs/enhancements/agentic-sdlc-intelligence-foundation-v1.md
prd_ref: docs/project_plans/PRDs/enhancements/agentic-sdlc-intelligence-foundation-v1.md
related:
- .claude/worknotes/ccdash-integration/integration-audit.md
- .claude/worknotes/ccdash-integration/example-payloads.json
- backend/services/integrations/skillmeat_client.py
- backend/services/integrations/skillmeat_sync.py
- backend/services/integrations/skillmeat_resolver.py
- backend/services/stack_observations.py
- backend/services/stack_recommendations.py
- backend/services/workflow_effectiveness.py
- backend/routers/integrations.py
- backend/routers/features.py
- backend/routers/analytics.py
- backend/models.py
- components/Settings.tsx
- components/FeatureExecutionWorkbench.tsx
- components/execution/RecommendedStackCard.tsx
- services/execution.ts
- services/analytics.ts
plan_ref: agentic-sdlc-intelligence-foundation-v2
linked_sessions: []
request_log_id: ''
commits:
- 156cde6
- 13ba2a6
- a5ef78c
- 0260e0b
- 4b94b55
- 094c305
prs: []
owner: platform-engineering
owners:
- platform-engineering
- ai-integrations
- fullstack-engineering
contributors:
- ai-agents
complexity: High
track: V2 Integration Hardening
timeline_estimate: 3-5 weeks across 7 phases
---

# Implementation Plan: Agentic SDLC Intelligence Foundation V2

## Objective

Build the second-wave integration between CCDash and SkillMeat by:

1. aligning the existing CCDash implementation to the audited SkillMeat contract,
2. replacing first-wave assumptions with confirmed API/auth/mapping behavior,
3. extending stack intelligence with effective workflows, bundles, context-pack previews, and workflow executions,
4. and tightening the settings/UI experience so CCDash can integrate cleanly with both local and AAA-enabled SkillMeat instances.

## Current Baseline

The original Agentic SDLC Intelligence foundation is already implemented in CCDash. Current baseline capabilities include:

1. project-level SkillMeat integration settings
2. definition sync and caching
3. stack observation backfill
4. workflow effectiveness and failure-pattern analytics
5. recommended stack output in feature execution context
6. recommended stack rendering in the execution workbench

The SkillMeat audit packet in `.claude/worknotes/ccdash-integration/` confirms that CCDash now has enough contract detail to harden and deepen the integration.

## Why V2 Is Needed

The audit closes several open questions from V1, but it also reveals concrete contract mismatches and missed integration opportunities:

1. SkillMeat’s versioned API surface is `/api/v1/*`, while CCDash’s first-wave client still assumes `/api/*`.
2. SkillMeat uses mixed pagination modes by resource type; CCDash’s sync layer should become contract-aware instead of generic.
3. SkillMeat project mapping is based on filesystem-path `project_id`, not `workspaceId`.
4. Local SkillMeat instances typically require no auth, but AAA-enabled instances need credential support in CCDash settings.
5. Workflows should be resolved as project-scoped plus global definitions, with project same-name precedence.
6. Context module resolution should use project-scoped list/get semantics and `ctx:name` should be treated as authoring-time syntax, not an API identifier.
7. Bundles and workflow execution APIs create a better stack-matching and execution-awareness loop than V1 captured.

## Scope and Fixed Decisions

1. CCDash will continue to treat SkillMeat as the source of truth for artifact, workflow, context module, bundle, and workflow execution definitions/state.
2. CCDash remains read-only against SkillMeat in this phase.
3. SkillMeat API integration will target `/api/v1/*` and tolerate additive schema changes.
4. CCDash project mapping will use a SkillMeat project filesystem path as the canonical `project_id`.
5. CCDash settings will include an **AAA enabled** toggle; when enabled, CCDash will reveal an API credential field for integration with auth-protected SkillMeat instances.
6. Workflow effectiveness and stack recommendation logic will prefer effective project workflows over raw global matches when both exist.
7. Context pack preview and workflow plan endpoints will be consumed as read-only enrichment sources.
8. Workflow execution data will be ingested as execution awareness, not as a replacement for CCDash session telemetry.

## Contract Decisions from the SkillMeat Audit

### 1) Base Paths and Discovery

1. SkillMeat base URL defaults to `http://127.0.0.1:8080` in local dev.
2. All supported integration endpoints live under `/api/v1`.
3. `openapi.json` is available and should be used for fixture-driven contract verification.

### 2) Auth and AAA

1. Local default: no auth required.
2. AAA-enabled or hosted mode: CCDash must be able to send a credential.
3. CCDash settings UX should expose:
   - `AAA enabled` toggle
   - credential input field when enabled
   - optional guidance text indicating local mode uses no credential

For implementation purposes, CCDash should support a generic credential field labeled for API key use, but the client should send it in the form SkillMeat accepts for authenticated mode.

### 3) Project Mapping

1. `skillMeat.projectId` should store the SkillMeat project filesystem path.
2. `workspaceId` is not part of the audited API contract and should be deprecated in CCDash.
3. `collectionId` is optional and useful for bundle/artifact context, but not the primary project mapping key.

### 4) Stable Identity Rules

1. Artifacts: primary ID is `type:name`; UUID is secondary/stable for cross-system storage.
2. Workflows: primary API lookup key is the workflow UUID.
3. Context modules: primary API lookup key is opaque `id`; `ctx:name` must be resolved client-side.
4. Bundles should be treated as curated stack definitions when exposed.

### 5) Read-Only Enrichment Endpoints

CCDash should explicitly consume:

1. `GET /api/v1/artifacts`
2. `GET /api/v1/artifacts/{artifact_id}`
3. `GET /api/v1/workflows`
4. `GET /api/v1/workflows/{workflow_id}`
5. `POST /api/v1/workflows/{workflow_id}/plan`
6. `GET /api/v1/context-modules`
7. `GET /api/v1/context-modules/{module_id}`
8. `POST /api/v1/context-packs/preview`
9. `GET /api/v1/workflow-executions`
10. `GET /api/v1/workflow-executions/{execution_id}`
11. `GET /api/v1/bundles` and bundle detail endpoints when enabled by the current SkillMeat instance

## Direct Changes Required to the Existing CCDash Implementation

## 1) Settings and Config Model

Current CCDash config still exposes `workspaceId`. V2 should:

1. repurpose `projectId` as explicit SkillMeat project path
2. remove or deprecate `workspaceId`
3. add:
   - `aaaEnabled`
   - `apiKey` or credential field
   - optional `collectionId`
   - optional `authMode` if needed for internal clarity

Files:

1. `backend/models.py`
2. `types.ts`
3. `components/Settings.tsx`

## 2) Client Contract Alignment

Current SkillMeat client assumptions need to be replaced with resource-aware handling:

1. use `/api/v1` endpoints
2. support page-based artifact pagination
3. support offset-based workflow pagination
4. support cursor-based context-module pagination
5. parse standard error envelopes and retry rules
6. support optional auth header when AAA is enabled

Files:

1. `backend/services/integrations/skillmeat_client.py`
2. `backend/tests/test_skillmeat_client.py`

## 3) Resolution and Matching Hardening

Current stack resolution should be updated to:

1. match artifacts by `type:name` first and UUID second when available
2. resolve workflows using project + global effective precedence
3. resolve `ctx:name` references by project list + name matching
4. integrate bundle definitions as named stack families

Files:

1. `backend/services/integrations/skillmeat_resolver.py`
2. `backend/services/stack_observations.py`
3. `backend/services/stack_recommendations.py`

## 4) Enrichment Beyond Definitions

V2 should add:

1. workflow plan snapshots from `/plan`
2. context pack preview summaries
3. workflow execution summaries and correlation

These should enrich, not replace, CCDash’s own telemetry.

## Architecture

## 1) Auth-Aware SkillMeat Integration Settings

Evolve the current `SkillMeatProjectConfig` into a contract-aligned model.

Proposed settings shape:

1. `enabled`
2. `baseUrl`
3. `projectId`
4. `collectionId`
5. `aaaEnabled`
6. `apiKey`
7. `requestTimeoutSeconds`
8. feature flags for CCDash-side surfaces

UI behavior:

1. when SkillMeat integration is enabled, show base URL, timeout, and project path
2. include connection-status indicators for the base URL and project-path mapping fields so users can verify the instance is reachable and the configured SkillMeat project can be resolved as expected
3. when `AAA enabled` is checked, enable the API key field
4. include an auth-status indicator for the API key field so users can verify the credential is accepted by the configured SkillMeat instance
5. hide or de-emphasize credential input for local unauthenticated mode
6. show help text explaining local vs AAA-enabled behavior

## 2) Resource-Aware API Client and DTO Layer

Expand the client layer so CCDash stops treating SkillMeat as a generic list API.

Responsibilities:

1. versioned endpoint routing
2. per-resource pagination loops
3. error envelope parsing with retry guidance
4. optional auth injection
5. contract tests against sanitized payload fixtures and selected OpenAPI-derived expectations

Proposed modules:

1. `backend/services/integrations/skillmeat_client.py`
2. `backend/services/integrations/skillmeat_contracts.py`

## 3) Effective Definition Sync

Extend sync so CCDash stores the definitions it actually needs for stack reasoning.

Definition classes for V2:

1. artifacts
2. workflows
3. context modules
4. bundles

Sync behavior:

1. fetch project-scoped workflows
2. fetch global workflows
3. store scope metadata in `resolution_metadata`
4. compute and persist `effectiveWorkflowKey` when project and global workflows share a name
5. record artifact UUID when present in raw payload

Files:

1. `backend/services/integrations/skillmeat_sync.py`
2. `backend/db/repositories/intelligence.py`
3. `backend/db/sqlite_migrations.py`
4. `backend/db/postgres_migrations.py`

## 4) Workflow Intelligence Layer

Use both the raw workflow definition and the `/plan` endpoint.

V2 workflow enrichment should include:

1. SWDL artifact references extracted from raw YAML
2. `ctx:name` references extracted from YAML
3. resolved context module IDs and names
4. plan summary:
   - batch count
   - gate presence
   - stage ordering
   - stage dependency structure

This lets CCDash recommend:

1. the workflow definition,
2. the stack components inside it,
3. and the shape of execution it implies.

## 5) Context Intelligence Layer

Use context modules and pack previews to strengthen recommendations.

V2 should:

1. list project context modules during sync
2. resolve `ctx:name` workflow references against real modules
3. optionally request pack previews for high-confidence recommended workflows
4. expose context availability and estimated token footprint in recommendation evidence

## 6) Bundle / Curated Stack Integration

SkillMeat bundles should be treated as curated stack definitions when available.

CCDash should use bundles for:

1. grouping observed stacks into named families
2. improving recommendation labels
3. comparing "observed stack" vs "curated bundle" fit

## 7) Workflow Execution Awareness

Add a read-only execution-awareness layer from SkillMeat workflow executions.

Use cases:

1. show recent SkillMeat executions for a recommended workflow
2. correlate execution state with CCDash feature context
3. expose execution timing and step status in workbench evidence
4. optionally poll or stream live execution status when the user is already viewing a relevant workflow

This should remain separate from CCDash session telemetry so provenance remains clear.

## 8) Deep-Link and UI Routing Fidelity

Use audited routes instead of generic source URLs where possible.

Stable targets:

1. artifacts: `/artifacts/{type:name}`
2. workflows: `/workflows/{workflow_uuid}`
3. workflow execution list: `/workflows/executions`
4. project memory fallback: `/projects/{encoded_project_id}/memory`

CCDash should store both:

1. raw SkillMeat source URL if present
2. computed stable UI route when enough identifiers are known

## Phase Breakdown

## Phase 1: Contract remediation and auth-aware settings

Objective:

Bring the current CCDash integration configuration and client assumptions into alignment with the audited SkillMeat contract.

| Task ID | Task Name | Description | Acceptance Criteria | Estimate (pts) | Assigned Subagent(s) |
| --- | --- | --- | --- | --- | --- |
| ASI2-1 | Settings model revision | Update `SkillMeatProjectConfig` to support project-path mapping, optional collection ID, AAA toggle, and API key field; deprecate `workspaceId`. | Backend/frontend types are aligned and persisted settings can round-trip without losing existing config. | 2 | python-backend-engineer, frontend-developer |
| ASI2-2 | AAA-aware settings UX | Update Settings UI so enabling AAA reveals the API key input, adds connection/auth status indicators, and clarifies project-path mapping. | Users can configure local no-auth and AAA-enabled SkillMeat instances without ambiguity and can verify connectivity/auth from the form state. | 2 | frontend-developer |
| ASI2-3 | Contract-aware client | Update client base paths, auth header support, timeout handling, and error-envelope parsing. | Client targets `/api/v1/*`, supports optional auth, and handles audited retry/failure rules. | 3 | python-backend-engineer |
| ASI2-4 | Contract fixture tests | Add tests against the packet payloads/OpenAPI-derived expectations for artifacts, workflows, context modules, errors, and auth modes. | Client/DTO tests fail on contract regressions and pass with current fixture payloads. | 2 | python-backend-engineer |

Quality gates:

1. No remaining use of `workspaceId` in active integration flows.
2. `AAA enabled` toggle drives credential field visibility and auth-status messaging.
3. Connection status is surfaced for base URL/project mapping validation.
4. Client tests explicitly cover the audited error envelope and auth behavior.

## Phase 2: Effective definition sync and scope-aware caching

Objective:

Upgrade definition sync so CCDash caches the correct SkillMeat entities with the right scope semantics.

| Task ID | Task Name | Description | Acceptance Criteria | Estimate (pts) | Assigned Subagent(s) |
| --- | --- | --- | --- | --- | --- |
| ASI2-5 | Sync artifacts with stable identity | Preserve `type:name` as primary external ID and capture UUID/source identity in snapshots where present. | Artifact cache stores stable IDs and enough metadata for robust cross-linking. | 2 | python-backend-engineer |
| ASI2-6 | Global + project workflow sync | Sync workflows from both global and project scopes and record scope metadata. | Cached workflows can distinguish global and project definitions. | 3 | python-backend-engineer |
| ASI2-7 | Effective workflow resolver | Add resolver logic that treats project same-name workflows as effective over globals until SkillMeat exposes a dedicated endpoint. | Recommendation and analytics layers can ask for the effective workflow for a project. | 3 | backend-architect, python-backend-engineer |
| ASI2-8 | Bundle sync | Sync bundle definitions where available and store them as curated stack families. | Bundles are cached and queryable for recommendation/grouping use. | 2 | python-backend-engineer |

Quality gates:

1. Workflow scope precedence is deterministic and tested.
2. Definition cache can answer artifact/workflow/context/bundle queries from local storage when SkillMeat is unavailable.
3. Sync summaries surface per-resource counts and degraded states clearly.

## Phase 3: Workflow plan and SWDL enrichment

Objective:

Use workflow definition internals and plan output to improve stack intelligence.

| Task ID | Task Name | Description | Acceptance Criteria | Estimate (pts) | Assigned Subagent(s) |
| --- | --- | --- | --- | --- | --- |
| ASI2-9 | SWDL reference extraction | Parse workflow YAML to extract stage-level artifact references, gate/fan-out structure, and `ctx:name` references. | Cached workflow enrichment includes artifact refs, context refs, and execution-shape metadata. | 3 | backend-architect, python-backend-engineer |
| ASI2-10 | Workflow plan snapshot sync | Call `/workflows/{id}/plan` during enrichment for targeted workflows and cache plan summaries. | CCDash can display plan-derived batches, gate presence, and dependency structure without re-calling SkillMeat on every page load. | 3 | python-backend-engineer |
| ASI2-11 | Effective workflow DTOs | Extend internal DTOs to represent raw workflow, effective workflow, and plan summary distinctly. | Recommendation and UI layers can consume effective workflow data cleanly. | 2 | python-backend-engineer |

Quality gates:

1. YAML parsing failure does not break the rest of sync.
2. Plan enrichment is cached and bounded to avoid excessive upstream calls.
3. Effective workflow metadata stays separable from raw snapshots.

## Phase 4: Context-pack and bundle-aware stack intelligence

Objective:

Improve stack matching and recommendation quality using context module and bundle information.

| Task ID | Task Name | Description | Acceptance Criteria | Estimate (pts) | Assigned Subagent(s) |
| --- | --- | --- | --- | --- | --- |
| ASI2-12 | Context-module resolution by name | Resolve workflow `ctx:name` references by listing project modules and matching names to IDs. | Resolved context references are attached to workflows and recommended stacks with confidence/source attribution. | 2 | python-backend-engineer |
| ASI2-13 | Context-pack preview enrichment | Use `context-packs/preview` for selected recommended workflows/modules to capture token budget and memory availability evidence. | Recommended stacks can display context coverage and token footprint evidence. | 3 | python-backend-engineer |
| ASI2-14 | Bundle-aware stack grouping | Map observed stacks to bundles where fit is high enough and expose bundle-family evidence. | Recommendations and analytics can show curated bundle alignment instead of only local inferred clusters. | 3 | backend-architect, python-backend-engineer |

Quality gates:

1. `ctx:name` is never treated as a direct API identifier.
2. Context preview requests are opt-in and rate-bounded.
3. Bundle matching does not override stronger project-specific workflow evidence without justification.

## Phase 5: Workflow execution awareness and cross-app correlation

Objective:

Bring live SkillMeat workflow execution state into CCDash as a first-class read-only signal.

| Task ID | Task Name | Description | Acceptance Criteria | Estimate (pts) | Assigned Subagent(s) |
| --- | --- | --- | --- | --- | --- |
| ASI2-15 | Execution client support | Add workflow execution list/detail support, including execution-step DTO normalization. | CCDash can sync and read execution state from SkillMeat using the audited execution schema. | 2 | python-backend-engineer |
| ASI2-16 | Execution cache and correlation | Persist execution summaries and correlate them with workflows, recommended stacks, and features using workflow/project/time evidence. | Feature context can show recent SkillMeat executions relevant to the current workflow or stack. | 3 | python-backend-engineer |
| ASI2-17 | Optional live polling / SSE hook | Add a bounded live-update path for users already viewing a relevant workflow execution surface. | Active execution state can refresh in-app without affecting baseline sync reliability. | 2 | python-backend-engineer, frontend-developer |

Quality gates:

1. Execution data is clearly labeled as SkillMeat-native, not CCDash session telemetry.
2. Correlation rules are explainable and non-destructive.
3. Live refresh remains opt-in or view-scoped.

## Phase 6: Recommendation, scoring, and deep-link upgrades

Objective:

Use the new contract-aligned data to improve the actual decision engine.

| Task ID | Task Name | Description | Acceptance Criteria | Estimate (pts) | Assigned Subagent(s) |
| --- | --- | --- | --- | --- | --- |
| ASI2-18 | Recommendation ranking upgrade | Re-rank recommended stacks using effective workflow, bundle alignment, context availability, and execution history. | Recommended stack output becomes more specific and more stable for repos with rich SkillMeat data. | 4 | backend-architect, python-backend-engineer |
| ASI2-19 | Workflow effectiveness scope upgrade | Extend analytics rollups to compare raw observed stacks, effective workflows, and bundle-aligned stack families. | Analytics UI/API can explain both historical local clusters and curated SkillMeat-aligned families. | 3 | python-backend-engineer |
| ASI2-20 | Stable deep-link builder | Replace ad hoc source-url usage with audited UI route construction for artifacts, workflows, executions, and project memory fallback. | Recommended stack chips and evidence links consistently open the right SkillMeat destination. | 2 | frontend-developer, python-backend-engineer |

Quality gates:

1. Recommendation evidence explicitly cites whether the match came from local observation, effective workflow, bundle, context preview, or execution history.
2. All deep links degrade to safe fallbacks when a dedicated destination does not exist.
3. Analytics output avoids double-counting project/global workflow pairs.

## Phase 7: UI polish, migration, and rollout hardening

Objective:

Ship the contract-aligned and richer integration safely without regressing the already-implemented V1 experience.

| Task ID | Task Name | Description | Acceptance Criteria | Estimate (pts) | Assigned Subagent(s) |
| --- | --- | --- | --- | --- | --- |
| ASI2-21 | Settings migration and defaults | Add compatibility handling for existing saved SkillMeat config and migrate deprecated fields forward. | Existing project configs continue to work and surface clear defaults after upgrade. | 2 | python-backend-engineer |
| ASI2-22 | Workbench UI enhancements | Add execution-awareness panels, context-pack evidence, bundle labels, and stronger route/open behavior to workbench UI. | `/execution` surfaces the richer SkillMeat integration without overwhelming the current command-first flow. | 3 | frontend-developer, ui-engineer-enhanced |
| ASI2-23 | End-to-end rollout tooling | Extend rollout/backfill scripts to cover contract re-sync, effective workflow recompute, bundle ingestion, and execution enrichment. | Operators can reinitialize the V2 intelligence state for an existing project with one documented workflow. | 2 | python-backend-engineer |
| ASI2-24 | Documentation and operator notes | Document local mode vs AAA-enabled mode, project path mapping, and fallback behavior when SkillMeat is unavailable. | Internal maintainers can configure and troubleshoot the integration without source diving. | 1 | documentation-writer |

Quality gates:

1. Old configs are migrated or interpreted safely.
2. V2 remains usable when SkillMeat is down by falling back to cached snapshots and previously computed rollups.
3. Rollout docs cover both local and AAA-enabled SkillMeat instances.

## Testing Plan

## Unit Tests

1. SkillMeat client pagination behavior by resource type
2. auth header behavior for local vs AAA-enabled settings
3. effective workflow resolution rules
4. `ctx:name` to module-ID resolution
5. bundle-alignment scoring
6. execution correlation helpers

## Integration Tests

1. settings -> sync -> definition cache -> recommendation flow with contract-aligned fixture payloads
2. local unauthenticated SkillMeat instance flow
3. AAA-enabled configuration flow with credential attached
4. workflow plan enrichment and context-pack preview enrichment
5. execution snapshot ingestion and feature-context exposure

## UI Tests

1. AAA toggle reveals API key field and auth-status indicator in Settings
2. base URL/project path fields show connection-status feedback
3. project path field labeling and validation
4. recommended stack card renders bundle/context/execution evidence
5. deep-link chips route to audited SkillMeat URLs

## Rollout Notes

1. Run this as a V2 upgrade of the already-implemented V1 foundation, not a greenfield integration.
2. Start with one internal SkillMeat instance in local no-auth mode.
3. Validate the AAA-enabled settings path with a protected instance before broadening usage.
4. Only enable execution polling after definition sync and workflow resolution are stable.

## SkillMeat-Side Follow-On Requests

These are not blockers for CCDash V2, but should be tracked as external enhancement opportunities:

1. effective workflow endpoint
2. context-module deep-link route
3. richer bundle composition contract
4. webhook/event support for change notifications
5. workflow execution outcome metadata write-back support
