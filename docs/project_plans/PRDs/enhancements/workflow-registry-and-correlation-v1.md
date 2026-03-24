---
schema_name: ccdash_document
schema_version: 3
doc_type: prd
doc_subtype: enhancement_prd
status: inferred_complete
category: enhancements
title: 'PRD: Workflow Registry and Correlation Surface V1'
description: Add a dedicated Workflow page in CCDash that unifies SkillMeat definitions,
  CCDash-observed workflow families, workflow composition, and effectiveness evidence
  into one developer-facing control plane.
summary: Create a read-only workflow registry in CCDash so teams can inspect workflow
  identity, structure, correlation quality, and performance across CCDash and SkillMeat
  from one place.
created: 2026-03-13
updated: 2026-03-13
priority: high
risk_level: medium
complexity: High
track: Workflow Intelligence / Integrations
timeline_estimate: 3-5 weeks
feature_slug: workflow-registry-and-correlation-v1
feature_family: workflow-intelligence-and-integration
feature_version: v1
lineage_family: workflow-intelligence-and-integration
lineage_parent: null
lineage_children: []
lineage_type: enhancement
problem_statement: Workflow data is currently split across SkillMeat definitions,
  CCDash observations, effectiveness rollups, and execution-page recommendations,
  which makes workflow tuning and trust hard.
owner: platform-engineering
owners:
- platform-engineering
- ai-integrations
- fullstack-engineering
contributors:
- ai-agents
audience:
- developers
- platform-engineering
- engineering-leads
- workflow-authors
tags:
- prd
- workflows
- skillmeat
- analytics
- integrations
- execution
- recommendations
related_documents:
- docs/workflow-skillmeat-integration-developer-reference.md
- docs/agentic-sdlc-intelligence-developer-reference.md
- docs/project_plans/PRDs/enhancements/agentic-sdlc-intelligence-foundation-v1.md
- docs/project_plans/reports/agentic-sdlc-intelligence-v2-integration-overview-2026-03-08.md
context_files:
- backend/services/integrations/skillmeat_sync.py
- backend/services/integrations/skillmeat_resolver.py
- backend/services/stack_observations.py
- backend/services/workflow_effectiveness.py
- backend/services/stack_recommendations.py
- backend/routers/analytics.py
- backend/routers/features.py
- backend/models.py
- components/Analytics/AnalyticsDashboard.tsx
- components/execution/WorkflowEffectivenessSurface.tsx
- components/execution/RecommendedStackCard.tsx
- components/Layout.tsx
- types.ts
implementation_plan_ref: docs/project_plans/implementation_plans/enhancements/workflow-registry-and-correlation-v1.md
---
# PRD: Workflow Registry and Correlation Surface V1

## Executive Summary

CCDash has enough workflow-related data to support a true workflow management surface, but that data is currently fragmented across multiple parts of the app and multiple layers of the backend. Workflow definitions come from SkillMeat. Workflow observations come from CCDash session evidence. Effectiveness is computed in CCDash. Recommended stacks appear on the execution page. Deep links and artifact modals exist in isolated surfaces. There is no single place where a developer or workflow author can inspect the full picture.

This enhancement introduces a dedicated Workflow page in CCDash. The page should function as a workflow registry and correlation surface: a developer-facing control plane where users can inspect what workflows CCDash knows about, how those workflows map to SkillMeat definitions, which artifacts and context modules they depend on, how they are performing historically, and where the current mapping quality is weak or unresolved.

V1 is intentionally read-only. It should improve understanding, trust, and tuning without turning CCDash into a workflow authoring system. SkillMeat remains the source of truth for reusable workflow definitions. CCDash remains the source of truth for observed evidence and recommendations.

## Current State

1. SkillMeat definitions are pulled into CCDash and cached in `external_definitions`.
2. CCDash derives per-session workflow and stack observations in `session_stack_observations` and `session_stack_components`.
3. CCDash computes workflow, stack, agent, skill, context, and bundle effectiveness rollups.
4. The execution page shows recommended stacks and workflow evidence.
5. The analytics page shows workflow-effectiveness leaderboards.
6. Artifact modals and SkillMeat links now exist in several workflow-related surfaces.

Despite that progress, workflow understanding is still fragmented:

1. There is no dedicated workflow list or registry.
2. There is no unified view of:
   - SkillMeat workflow definition
   - observed CCDash workflow family
   - resolved command artifact
   - bundle/context/artifact composition
   - historical effectiveness
   - mapping/correlation quality
3. The current `workflowRef` concept is overloaded:
   - sometimes it represents a CCDash command-shaped workflow family
   - sometimes it points at a SkillMeat workflow definition
   - sometimes it resolves best to a SkillMeat command artifact
4. Tuning the integration requires moving between docs, logs, analytics, execution recommendations, and SkillMeat itself.

## Problem Statement

As a developer or workflow author, I need one place in CCDash where I can inspect workflows as first-class objects across both CCDash and SkillMeat. Today that is not possible. Workflow information is distributed across multiple surfaces and multiple data models, which makes it difficult to answer:

1. What workflows actually exist for this project?
2. Which are authoritative SkillMeat workflows and which are only observed CCDash workflow families?
3. Which artifacts, context modules, bundles, or sub-structures belong to each workflow?
4. Which workflows are performing well and which are producing rework or weak outcomes?
5. Where is CCDash relying on command-like approximations rather than strong SkillMeat workflow resolution?
6. Which gaps should we fix next in the integration?

Without a dedicated workflow surface:

1. workflow tuning remains slow and manual
2. resolution gaps remain hard to spot
3. trust in recommendations is lower than it should be
4. teams cannot use CCDash as a workflow-intelligence layer in a disciplined way

## Goals

1. Introduce a dedicated Workflow page in CCDash.
2. Present workflows as first-class entities rather than as side effects of the execution page or analytics rollups.
3. Correlate SkillMeat workflow definitions, CCDash-observed workflow families, command artifacts, bundles, context modules, and effectiveness evidence in one surface.
4. Expose mapping quality so developers can see where workflow resolution is strong, hybrid, or unresolved.
5. Provide workflow composition visibility, including artifacts, context modules, plan-stage metadata, and related references where available.
6. Provide direct actions to inspect underlying SkillMeat objects and representative CCDash evidence.

## Non-Goals

1. Editing SkillMeat workflows from CCDash in V1.
2. Writing workflow metadata back into SkillMeat in V1.
3. Replacing the existing execution page recommended-stack surface.
4. Replacing analytics workflow-effectiveness views.
5. Full workflow orchestration or run management from this new page.
6. Solving every workflow-identity problem in storage before shipping the page.

## Users and Jobs-to-be-Done

1. Workflow authors: "Show me how my SkillMeat workflows are being interpreted and whether they are actually working in practice."
2. Platform engineers: "Show me where workflow identity and artifact resolution are weak so I can improve the integration contract."
3. Engineers: "Show me which workflow I should trust for this kind of work and what it depends on."
4. Leads: "Show me which workflows are durable, which are risky, and which ones are not really resolved yet."

## Product Thesis

The execution page and analytics page answer downstream questions:

1. What stack should I use next?
2. Which workflow performed better historically?

The missing surface is upstream:

1. What is this workflow, exactly?
2. How is it represented across CCDash and SkillMeat?
3. What is inside it?
4. How trustworthy is the current correlation?

The new Workflow page should close that gap. It should act as the identity and composition layer that sits between SkillMeat definitions and CCDash recommendation/analytics surfaces.

## Proposed Surface

V1 should be a dedicated page, for example `/workflows`, linked from the main app navigation.

The page should include:

### 1) Workflow Catalog

A searchable, filterable list of workflow entities known to CCDash.

Each row should expose:

1. display name
2. workflow type:
   - SkillMeat workflow
   - CCDash workflow family
   - hybrid / resolved-to-artifact
   - unresolved
3. correlation status
4. primary source
5. recent effectiveness summary
6. representative command family when relevant

### 2) Workflow Detail View

Selecting a workflow should open a detail view or detail panel with:

1. identity summary
2. resolved SkillMeat references
3. observed CCDash aliases and command families
4. workflow composition
5. historical effectiveness
6. representative sessions
7. current issues / warnings

### 3) Workflow Composition Section

Where available, show:

1. artifact refs
2. context module refs
3. bundle alignment
4. plan summary
5. stage order
6. gate count
7. fan-out count
8. related references

V1 may use cards, lists, and summarized graphs rather than a fully interactive DAG, but the surface must make composition inspectable.

### 4) Correlation Quality Section

For each workflow, CCDash should explicitly show:

1. observed CCDash workflow refs
2. resolved SkillMeat workflow definition, if any
3. resolved command artifact, if any
4. matching method or source attribution
5. confidence / quality state:
   - strong
   - hybrid
   - weak
   - unresolved

### 5) Effectiveness and Evidence Section

Reuse and unify existing signals:

1. success
2. efficiency
3. quality
4. risk
5. sample size
6. representative sessions
7. recent SkillMeat workflow executions when available
8. related stack recommendations

### 6) Actions

V1 actions should remain read-only:

1. open workflow in SkillMeat
2. open related artifact/context/bundle in SkillMeat
3. open representative session in CCDash
4. refresh SkillMeat cache
5. recompute workflow-effectiveness data

## Success Metrics

| Metric | Baseline | Target |
|--------|----------|--------|
| Single-surface workflow visibility in CCDash | None | Dedicated workflow page available |
| Workflows with visible correlation state | 0 | 100% of surfaced workflows |
| Workflow rows with at least one direct drill-down action | Fragmented | 100% |
| Time to identify why a workflow is unresolved | High/manual | Reduced through page-level issue visibility |
| Workflow tuning loops requiring multiple app surfaces | High | Reduced to one primary CCDash surface plus SkillMeat deep links |

## User Stories

1. As a workflow author, I can open one page and see all workflows CCDash knows about for this project.
2. As a workflow author, I can tell whether CCDash resolved a workflow to a SkillMeat workflow definition, to a command artifact, or not at all.
3. As a platform engineer, I can inspect the composition of a workflow and verify which artifacts and context modules CCDash thinks are part of it.
4. As an engineer, I can compare workflows by effectiveness without losing the identity and composition context behind those scores.
5. As a maintainer, I can spot hybrid or weakly correlated workflows and use that information to improve the integration contract.

## Functional Requirements

| ID | Requirement | Priority | Notes |
|----|-------------|----------|-------|
| FR-1 | CCDash must expose a dedicated Workflow page in the app navigation. | Must | Separate from execution and analytics pages. |
| FR-2 | The Workflow page must list workflows from both SkillMeat definitions and CCDash-observed workflow families. | Must | Hybrid registry view. |
| FR-3 | Each workflow row must show a correlation state that distinguishes strong, hybrid, weak, and unresolved mapping. | Must | Must not hide ambiguity. |
| FR-4 | The page must show whether a workflow is backed by a SkillMeat workflow definition, a command artifact, both, or neither. | Must | This is the core trust signal. |
| FR-5 | The page must expose workflow composition using currently available workflow metadata, including artifacts, context refs, bundle alignment, and plan/stage summaries where available. | Must | Summary form acceptable in V1. |
| FR-6 | The page must expose workflow effectiveness signals using current CCDash scoring data. | Must | Reuse existing metrics. |
| FR-7 | The page must support drill-down actions into SkillMeat and into representative CCDash sessions. | Must | Read-only only. |
| FR-8 | The page must support search and filtering by workflow type, correlation state, and effectiveness posture. | Should | Necessary for usability at scale. |
| FR-9 | The page must surface issues and warnings for stale cache, unresolved refs, missing context resolution, or weak composition coverage. | Must | This is a tuning surface, not just a dashboard. |
| FR-10 | The page must degrade gracefully when SkillMeat integration is disabled or stale. | Must | Clear empty/disabled states required. |

## Recommended Data Model Direction

V1 does not need a new persistence layer if the page can be built from existing definitions, observations, and rollups. But the page should introduce a clear response contract that separates:

1. observed workflow family id
2. resolved SkillMeat workflow id
3. resolved command artifact id
4. display label
5. correlation state
6. composition summary
7. evidence summary

This is important because current `workflowRef` values are overloaded.

## Recommended Product Decisions

### 1. Dedicated page, not just another analytics tab

This surface is about identity, structure, and correlation, not only ranking. A dedicated page is justified if the long-term goal is workflow tuning.

### 2. Read-only first

V1 should optimize for trust and understanding. Editing workflows from CCDash would expand scope too much and blur the SkillMeat ownership boundary.

### 3. Make ambiguity explicit

CCDash should not pretend every workflow is cleanly resolved. The page should make hybrid and weak states visible rather than flattening them into polished labels.

### 4. Reuse existing evidence instead of inventing a new scoring system

V1 should compose:

1. SkillMeat definitions and enrichment
2. CCDash observations
3. workflow-effectiveness rollups
4. recommended-stack evidence

It should not introduce a separate scoring engine just for the page.

## Non-Functional Requirements

1. The page must remain usable when SkillMeat is unreachable but CCDash caches exist.
2. The page must make provenance clear so developers can distinguish cached SkillMeat metadata from CCDash-computed evidence.
3. Response payloads should be shaped for frontend rendering without requiring the UI to reconstruct correlation logic on the client.
4. The page should scale to dozens or hundreds of workflows without loading every deep detail eagerly.

## In Scope

1. New Workflow page route and navigation entry.
2. Backend aggregation endpoint for workflow registry/detail data.
3. Workflow catalog, filters, and detail surface.
4. Composition, correlation, effectiveness, and issues sections.
5. Deep links into SkillMeat and CCDash evidence.
6. Disabled/empty/error states.

## Out of Scope

1. Workflow editing or mutation in SkillMeat.
2. Workflow authoring in CCDash.
3. Write-back of recommendations or outcomes into SkillMeat.
4. Fully interactive workflow graph editor.
5. New long-term persistent workflow graph tables in V1 unless required by implementation.

## Dependencies and Assumptions

1. Existing SkillMeat definition sync remains the authoritative CCDash cache source.
2. Existing observation backfill and effectiveness services remain available.
3. Existing recommended-stack and workflow-effectiveness logic remains reusable.
4. SkillMeat stable links for artifacts, workflows, bundles, and context memory remain usable from CCDash.

## Risks and Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| The page exposes workflow ambiguity that users find confusing | Medium | Medium | Use explicit correlation-state language and help text. |
| Existing backend services do not yet expose enough workflow-composition detail | High | Medium | Introduce a dedicated aggregation layer that reuses current metadata and exposes gaps clearly. |
| The surface becomes another leaderboard instead of a workflow control plane | High | Medium | Keep identity, composition, and issues as first-class sections. |
| Hybrid workflow identity remains too overloaded for clean rendering | High | Medium | Define a response contract that separates observed family, resolved workflow, and resolved artifact. |
| Loading all workflow detail at once becomes slow | Medium | Medium | Use list + on-demand detail loading. |

## Open Questions

1. Should the page live at top-level navigation or inside analytics for the first release?
2. Should workflow detail open inline, in a drawer, or on a dedicated detail route?
3. Should bundle-aligned "workflow packages" appear as peer entities in the catalog or as workflow detail enrichments only?
4. Should V1 include manual correlation annotations or stay fully derived?

## Acceptance Criteria

1. CCDash exposes a dedicated Workflow page for the active project.
2. The page lists workflows from both SkillMeat definitions and CCDash-observed workflow families.
3. Every workflow row shows a visible correlation state.
4. Workflow detail exposes identity, composition, effectiveness, and issues in one place.
5. Users can open related SkillMeat definitions and representative CCDash sessions from the page.
6. The page degrades gracefully when SkillMeat integration is disabled or partially unresolved.
