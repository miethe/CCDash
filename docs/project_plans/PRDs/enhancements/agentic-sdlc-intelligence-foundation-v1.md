---
doc_type: prd
status: completed
category: enhancements
title: 'PRD: Agentic SDLC Intelligence Foundation V1'
description: Establish CCDash as the evidence-backed recommendation and optimization
  layer for agentic SDLC workflows, with read-only integration to SkillMeat artifact,
  workflow, and context definitions.
author: codex
audience:
- ai-agents
- developers
- engineering-leads
- platform-engineering
created: 2026-03-07
updated: 2026-04-07
commit_refs:
- https://github.com/miethe/CCDash/commit/4ebcaf9
pr_refs:
- https://github.com/miethe/CCDash/pull/7
tags:
- prd
- analytics
- workflow
- skillmeat
- recommendations
- telemetry
- agentic-sdlc
feature_slug: agentic-sdlc-intelligence-foundation-v1
feature_family: agentic-sdlc-intelligence
lineage_family: agentic-sdlc-intelligence
lineage_parent: ''
lineage_children: []
lineage_type: iteration
linked_features:
- agentic-sdlc-intelligence-foundation-v1
related:
- README.md
- docs/session-data-discovery.md
- docs/project_plans/implementation_plans/telemetry-analytics-modernization-v1.md
- docs/project_plans/implementation_plans/enhancements/agentic-sdlc-intelligence-foundation-v1.md
- docs/project_plans/implementation_plans/enhancements/agentic-sdlc-intelligence-foundation-v2.md
- docs/project_plans/PRDs/enhancements/feature-execution-workbench-v1.md
- docs/project_plans/PRDs/enhancements/feature-execution-workbench-phase-4-sdk-orchestration-v1.md
- backend/db/sync_engine.py
- backend/routers/analytics.py
- backend/services/feature_execution.py
implementation_plan_ref: docs/project_plans/implementation_plans/enhancements/agentic-sdlc-intelligence-foundation-v1.md
request_log_id: ''
commits: []
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
# PRD: Agentic SDLC Intelligence Foundation V1

## Executive Summary

CCDash already captures the raw ingredients for an agentic SDLC intelligence system: session telemetry, artifact links, feature/document correlation, execution recommendations, test telemetry, and cross-platform session parsing. V1 formalizes the next layer above that data: a system that can explain what agent/skill/workflow stacks are being used, determine which ones are working, and recommend the best next stack for a given feature, phase, or workflow condition.

The key integration decision is to keep **SkillMeat as the source of truth for definitions** and make **CCDash the source of truth for effectiveness**.

In this phase:

1. CCDash reads and resolves SkillMeat artifact, workflow, and context definitions.
2. CCDash normalizes observed session behavior into candidate stacks and workflow observations.
3. CCDash computes effectiveness signals from real delivery outcomes.
4. CCDash exposes evidence-backed recommended stacks and workflow insights in the app.

This phase is intentionally **groundwork-first on the CCDash side**. It does not require write-back into SkillMeat, new SkillMeat definition formats, or remote execution orchestration from CCDash.

## Product Thesis

The grand purpose of CCDash is not just to inspect sessions after the fact. It is to become the operating intelligence layer for AI-native software delivery.

SkillMeat manages the reusable supply side:

1. Artifact definitions (`agent:*`, `skill:*`, `command:*`, `mcp:*`, etc.).
2. Workflow definitions (SWDL).
3. Context module definitions (`ctx:*`).

CCDash manages the adaptive demand side:

1. What was actually used.
2. What worked in practice.
3. What failed or caused rework.
4. What stack should be recommended next, for this feature, in this repo, under current conditions.

## Context and Current State

CCDash already has a strong telemetry substrate:

1. `telemetry_events` fact storage with feature, task, model, agent, skill, tool, cost, and token dimensions.
2. Session forensics for resource footprint, queue pressure, subagent topology, tool-result intensity, test execution, and codex payload signals.
3. Feature execution recommendation logic that already derives the next likely command from feature state and linked documents.
4. Correlation across features, sessions, documents, test mappings, commits, and artifacts.

SkillMeat already has a compatible definition substrate:

1. Artifact APIs with stable artifact IDs in `type:name` form.
2. Workflow APIs and SWDL definitions with artifact references in stages.
3. Context module APIs and `ctx:*` references with selector-based packing.
4. Project-scoped workflow overrides and execution planning patterns.

Today, these systems are adjacent rather than integrated. CCDash can tell the user what happened in a session, but not:

1. which reusable SkillMeat workflow or stack that session most closely corresponded to,
2. whether that workflow is outperforming alternatives,
3. which context modules and skill bundles correlate with better outcomes,
4. or which stack should be suggested next from real project evidence.

## Problem Statement

Agentic SDLC workflows currently lack a clean closed loop.

1. SkillMeat can define and distribute reusable artifacts and workflows.
2. CCDash can observe outcomes and correlations.
3. But there is no canonical system that joins the two to answer:
   - "Which stack is working here?"
   - "Which workflow should we run next?"
   - "Which agent/skill combination is wasting tokens or creating rework?"
   - "Which context modules improve delivery quality in this repository?"

Without this loop:

1. teams continue to choose stacks by intuition,
2. strong workflows do not compound into standardized playbooks,
3. low-yield patterns remain invisible,
4. and the app stops short of being a decision engine for agentic delivery.

## Goals

1. Introduce a first-class CCDash model for external definitions resolved from SkillMeat.
2. Normalize session evidence into observed workflow stacks and candidate workflow matches.
3. Compute effectiveness signals for agents, skills, workflows, context modules, and stack combinations.
4. Recommend a "best next stack" for a feature or execution context with explicit evidence and confidence.
5. Surface failure patterns and bottlenecks that explain low-yield workflows.
6. Deep-link from CCDash recommendations directly to SkillMeat artifact/workflow/context definitions.

## Non-Goals

1. Making SkillMeat writable from CCDash in V1.
2. Editing SkillMeat artifact/workflow/context definitions from CCDash.
3. Replacing SkillMeat workflow execution or authoring surfaces.
4. Full autonomous orchestration or multi-step execution from these recommendations.
5. Heavy ML ranking systems that cannot explain their conclusions.

## Users and Jobs-to-be-Done

1. Engineers: "Tell me which stack to use next for this feature and why."
2. Leads: "Show me which agents, skills, and workflows are producing durable outcomes in this repo."
3. Platform engineers: "Identify inefficient or risky workflow patterns so we can improve shared playbooks."
4. Workflow authors: "Use real outcome data to refine SkillMeat artifacts, workflows, and context modules."

## Functional Requirements

### 1) External Definition Resolution Layer

CCDash must support a read-only integration layer that resolves SkillMeat definitions into CCDash-visible references.

Minimum supported definition classes:

1. artifact definitions
2. workflow definitions
3. context module definitions

Requirements:

1. Store SkillMeat integration settings per CCDash project.
2. Resolve and cache external definitions with stable external IDs and version metadata.
3. Preserve provenance for every resolved definition:
   - source system
   - external id
   - version
   - fetched timestamp
   - raw payload snapshot
4. Support deep links back to SkillMeat UI/API resources when available.

### 2) Observed Stack Normalization

CCDash must derive observed stacks from existing session data.

An observed stack may include:

1. workflow definition match
2. primary agent artifact
3. supporting skill artifacts
4. command/workbench pattern
5. context module references
6. model or effort policy marker

Requirements:

1. Support both explicit and inferred evidence.
2. Distinguish between:
   - explicit session evidence
   - inferred from telemetry/logs
   - resolved via SkillMeat definition matching
3. Persist per-session stack observations and confidence.
4. Allow many-to-one resolution where multiple sessions map to the same recommended stack family.

### 3) Effectiveness Scoring Engine

CCDash must compute effectiveness using delivery outcomes, not just tool counts.

Inputs must be drawn from existing CCDash data where possible:

1. feature progression
2. phase completion state
3. test execution and integrity outcomes
4. follow-on debug or retry behavior
5. queue pressure and subagent waste
6. command and artifact event counts
7. token and cost efficiency
8. file churn and rework proxies

Outputs must include:

1. success score
2. efficiency score
3. quality-confidence score
4. failure-risk score
5. evidence summary explaining the score

The system must support rollups by:

1. workflow
2. agent
3. skill
4. context module
5. stack family
6. feature/phase/domain

### 4) Recommended Stack Engine

CCDash must expose a recommendation service that returns the best next stack for a selected feature or execution context.

A recommended stack should contain:

1. primary workflow reference when available
2. primary agent reference
3. supporting skill references
4. context module references
5. recommended command or execution entry point
6. confidence
7. evidence and tradeoff notes

Requirements:

1. Recommendations must be deterministic and evidence-backed.
2. The engine must degrade gracefully when SkillMeat definitions cannot be resolved.
3. Recommendations must still work in CCDash-only mode using observed local patterns.
4. The result must expose source attribution:
   - historical stack match
   - feature-state rule
   - quality outcome evidence
   - ambiguity or missing-definition warnings

### 5) Workflow Effectiveness and Failure Pattern Analytics

CCDash must provide analytics surfaces for understanding what is working and what is not.

Minimum analytics:

1. workflow effectiveness leaderboard
2. agent/skill effectiveness by feature or phase
3. failure pattern clusters
4. subagent ROI and orchestration waste indicators
5. low-yield stack detection

Failure pattern outputs should explain conditions such as:

1. repeated retries with little feature progress
2. high queue pressure with low completion
3. test weakening or low-confidence validation paths
4. heavy cost with follow-on debug sessions
5. repeated fallback to generic commands due to missing definitions or ambiguous evidence

### 6) Similar-Work Retrieval

CCDash must support retrieval of similar prior sessions or feature runs to inform recommendations.

Requirements:

1. Match on feature metadata, files, commands, skills, agents, and outcome profile.
2. Return prior stacks and outcomes for comparison.
3. Show why a historical example is considered similar.

### 7) UI Surfaces

At minimum, V1 must surface the new intelligence in:

1. Feature Execution Workbench
2. analytics/workflow effectiveness views
3. session or feature detail pages where stack evidence is relevant

The Feature Execution Workbench should gain:

1. recommended stack card
2. linked SkillMeat definition references
3. evidence view
4. alternatives and warnings

### 8) Integration Boundary with SkillMeat

V1 must treat SkillMeat as authoritative for definitions and CCDash as authoritative for observed outcomes.

Fixed decisions:

1. CCDash is read-only against SkillMeat in this phase.
2. CCDash stores local snapshots/cache for performance and historical reproducibility.
3. CCDash does not mutate SkillMeat workflow YAML, artifact files, or context modules.
4. CCDash recommendations may deep-link to SkillMeat definitions but do not require SkillMeat execution integration in this phase.

## Non-Functional Requirements

1. Recommendation and effectiveness queries should remain explainable and deterministic.
2. Definition resolution must tolerate remote unavailability via cached snapshots.
3. Historical recommendations should remain reproducible against the definition snapshot used at that time.
4. UI surfaces should degrade gracefully when SkillMeat integration is unavailable.
5. Feature flags must gate the full integration surface.

## Data and Integration Requirements

### Confirmed SkillMeat-side assumptions from current code/docs

These are safe to design against from the CCDash side:

1. Artifacts are addressable by stable IDs in `type:name` form.
2. Workflows are available as managed definitions and can be listed, fetched, validated, and planned.
3. Context modules are project-scoped and support CRUD/list/get semantics.
4. Workflow definitions can reference artifact IDs and `ctx:*` context modules.

### CCDash-side data additions expected

1. project-level integration settings for SkillMeat
2. cached external definitions
3. session-to-stack observation records
4. effectiveness score records or materialized rollups
5. recommendation payload models and API responses

## Success Metrics

1. At least 70% of eligible sessions resolve to a candidate observed stack with medium-or-better confidence.
2. At least 60% of recommendations for features with linked sessions and plans include one or more resolved SkillMeat references.
3. Recommended stack interactions are used in at least 25% of execution workbench visits within the first release window.
4. At least 3 concrete low-yield workflow patterns are identifiable in pilot data within the first two weeks after backfill.
5. Median time from selecting a feature to choosing a stack or command is reduced by at least 40% versus the baseline workbench flow.

## Risks and Mitigations

1. Risk: SkillMeat definitions and CCDash session evidence do not align cleanly.
   - Mitigation: explicit/inferred/resolved evidence tiers and confidence scoring.
2. Risk: Recommendations appear authoritative without enough evidence.
   - Mitigation: show evidence, confidence, and ambiguity warnings on every recommendation.
3. Risk: External integration becomes a hard dependency.
   - Mitigation: cache snapshots, feature flags, and CCDash-only fallback mode.
4. Risk: V1 becomes too broad.
   - Mitigation: keep V1 read-only, recommendation-first, and grounded in existing telemetry.

## Dependencies

1. Existing telemetry, session forensics, and analytics infrastructure.
2. Existing Feature Execution Workbench and recommendation service.
3. Stable CCDash project-to-SkillMeat project mapping strategy.

## Open Questions for the Next Implementation Round

These are intentionally called out rather than invented in this phase:

1. What is the canonical per-project mapping between a CCDash project and a SkillMeat `project_id`, collection, or workspace scope?
2. What authentication model should CCDash use for SkillMeat API access in local and hosted modes?
3. Which SkillMeat endpoints should be treated as stable contracts for artifacts, workflows, and context modules in production?
4. How should CCDash represent non-artifact stack elements such as model selection and effort policy when those do not map to SkillMeat artifact IDs?
5. Should recommended stacks point to base workflow definitions, project overrides, or both when SkillMeat override layers exist?
6. Is there a stable SkillMeat deep-link URL pattern for artifacts, workflows, and context modules, or should CCDash only link to API identifiers in V1?
7. Should CCDash eventually write effectiveness summaries back into SkillMeat metadata, or remain a separate analytics plane?

## Acceptance Criteria

1. CCDash can be configured to resolve SkillMeat artifacts, workflows, and context modules for a project.
2. CCDash persists resolved external definitions with provenance and version metadata.
3. CCDash derives observed stacks from historical sessions with explicit confidence.
4. CCDash exposes workflow/agent/skill/context effectiveness views from real project evidence.
5. Feature execution context can return a recommended stack with SkillMeat references when available.
6. Recommendations and analytics include evidence and degrade gracefully when external resolution is incomplete.
