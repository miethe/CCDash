---
schema_name: ccdash_document
schema_version: 3
doc_type: prd
doc_subtype: integration_prd
status: draft
category: integrations
title: "PRD: SkillMeat Artifact Usage Intelligence Exchange V1"
description: "Extend the CCDash and SkillMeat feedback loop so project, collection, user, and artifact usage rollups drive rankings, context-optimization guidance, and artifact improvement recommendations."
summary: "Build on existing CCDash usage attribution and SkillMeat artifact metrics by adding project snapshot exchange, per-user/per-project artifact usage rollups, ranking surfaces, and optimization recommendations."
author: codex
created: 2026-05-06
updated: 2026-05-06
priority: high
risk_level: high
complexity: high
track: Integrations / Artifact Intelligence
timeline_estimate: "5-7 weeks across 6 phases"
feature_slug: skillmeat-artifact-usage-intelligence-exchange-v1
feature_family: ccdash-skillmeat-artifact-intelligence
feature_version: v1
lineage_family: ccdash-skillmeat-artifact-intelligence
lineage_parent:
  ref: docs/project_plans/PRDs/integrations/ccdash-telemetry-exporter.md
  kind: builds_on
lineage_children: []
lineage_type: integration
problem_statement: "CCDash can attribute tokens and workflow effectiveness to skills, agents, workflows, and artifacts, while SkillMeat can ingest artifact metrics, but the two systems do not yet exchange full project artifact snapshots or maintain project/user/collection-level usage intelligence for ranking and optimization decisions."
owner: platform-engineering
owners:
  - platform-engineering
  - ai-integrations
  - data-platform
contributors:
  - ai-agents
audience:
  - ai-agents
  - developers
  - platform-engineering
  - workflow-authors
  - engineering-leads
tags:
  - prd
  - integrations
  - skillmeat
  - artifacts
  - usage-attribution
  - rankings
  - recommendations
  - context-optimization
related_documents:
  - docs/project_plans/PRDs/integrations/ccdash-telemetry-exporter.md
  - docs/project_plans/implementation_plans/integrations/ccdash-telemetry-exporter-v1.md
  - docs/project_plans/PRDs/enhancements/claude-code-session-usage-attribution-v2.md
  - docs/project_plans/implementation_plans/enhancements/claude-code-session-usage-attribution-v2.md
  - docs/project_plans/PRDs/enhancements/workflow-registry-and-correlation-v1.md
  - docs/project_plans/PRDs/integrations/otel-session-metrics-ingestion-v1.md
  - ../skillmeat/docs/project_plans/PRDs/integrations/ccdash-artifact-metrics-integration-v1.md
  - ../skillmeat/docs/project_plans/implementation_plans/integrations/ccdash-artifact-metrics-integration-v1.md
context_files:
  - backend/ingestion/session_ingest_service.py
  - backend/services/session_usage_attribution.py
  - backend/services/session_usage_analytics.py
  - backend/services/workflow_effectiveness.py
  - backend/services/stack_observations.py
  - backend/services/integrations/telemetry_exporter.py
  - backend/services/integrations/sam_telemetry_client.py
  - backend/services/integrations/skillmeat_client.py
  - backend/services/integrations/skillmeat_trust.py
  - backend/services/integrations/skillmeat_resolver.py
  - backend/routers/analytics.py
  - backend/routers/agent.py
  - backend/mcp/server.py
  - backend/project_manager.py
  - backend/models.py
  - services/analytics.ts
  - components/Analytics/AnalyticsDashboard.tsx
  - components/execution/WorkflowEffectivenessSurface.tsx
  - components/Settings.tsx
  - types.ts
implementation_plan_ref: "docs/project_plans/implementation_plans/integrations/skillmeat-artifact-usage-intelligence-exchange-v1.md"
---

# PRD: SkillMeat Artifact Usage Intelligence Exchange V1

## Executive Summary

CCDash already has the local evidence needed to understand artifact utility: immutable usage events, attribution links, workflow effectiveness rollups, SkillMeat definition sync, and outbound telemetry for artifact outcomes. SkillMeat already has a complementary artifact-metrics foundation with artifact and version metrics, correlation endpoints, and artifact detail surfaces.

V1 of this enhancement closes the remaining loop. CCDash should request a SkillMeat snapshot of all artifacts relevant to a project and collection, bind session usage/effectiveness evidence to that snapshot, and send back normalized rollups that SkillMeat can store by project, collection, artifact, version, and user. CCDash should then expose artifact rankings and optimization recommendations locally, including recommendations to disable unused always-loaded skills, shift artifacts to workflow-specific loading, swap artifacts for better-performing alternatives, and prioritize optimization passes for high-utilization/high-cost artifacts.

This is not a replacement for the existing artifact metrics work. It is the next layer above it: snapshot-aware, project-aware, user-aware artifact intelligence.

## Current State

CCDash has these relevant foundations:

1. `session_usage_events` and `session_usage_attributions` persist event-level token usage and derived links to skills, agents, commands, artifacts, workflows, features, and subthreads.
2. `session_ingest_service.py` is the canonical persistence path for normalized sessions, messages, tool usage, artifacts, telemetry events, usage attributions, and intelligence facts.
3. `session_usage_analytics.py` exposes aggregate and drill-down views with exclusive versus supporting attribution semantics.
4. `workflow_effectiveness.py` computes effectiveness rollups for workflow, agent, skill, context module, bundle, stack, and related scopes.
5. `stack_observations.py` and SkillMeat definition sync infer observed skills, agents, artifacts, workflows, commands, bundles, and context modules from session evidence.
6. `skillmeat_client.py` reads SkillMeat artifacts, workflows, context modules, and bundles into CCDash definition caches.
7. `telemetry_exporter.py` and `sam_telemetry_client.py` already route execution, artifact, and artifact-version outcome payloads to SkillMeat/SAM endpoints.
8. `skillmeat_trust.py` emits metadata-only delegation headers for hosted SkillMeat calls.
9. Project settings already carry SkillMeat project and collection IDs plus feature flags for recommendations and usage attribution.

SkillMeat has these relevant foundations:

1. `ccdash-artifact-metrics-integration-v1` defines artifact and artifact-version metrics as the current metrics foundation.
2. `/api/v1/analytics/artifact-outcomes` and `/api/v1/analytics/artifact-version-outcomes` ingest CCDash-attributed artifact outcomes.
3. `ArtifactOutcomeCorrelationService` resolves CCDash artifact hints into SkillMeat artifact/version identities.
4. Artifact metrics query routes and UI hooks can surface effectiveness data on artifact/version surfaces.
5. Project detail APIs already expose deployed artifacts, grouped deployments, deployment profiles, default profile IDs, and stats by type/collection/profile.
6. Collection APIs already expose artifact membership and count-style aggregation.
7. BOM/snapshot APIs already provide nearby snapshot primitives, but not a single CCDash-ready project artifact snapshot with identity, deployment, profile, collection, drift, and freshness metadata.

Remaining gap: neither side yet treats a project artifact snapshot as the shared contract for usage intelligence, rankings, and optimization guidance.

## Problem Statement

Developers can see local CCDash attribution and SkillMeat can store artifact metrics, but there is no complete loop that answers:

1. Which artifacts in this project are actually used, by whom, and in which workflows?
2. Which always-loaded skills or agents add context cost without observed utility?
3. Which artifact versions produce better outcomes for this project or collection?
4. Which artifacts are high-utilization enough to justify an optimization pass?
5. Which workflow recommendations should change because real usage data contradicts static defaults?
6. Which artifacts should remain global defaults versus being loaded only for specific workflows?

The root issue is contract shape. CCDash has observed usage, but it needs a current SkillMeat project/collection artifact snapshot to know what should have been available, what was actually loaded, what version was deployed, and which entities belong to the user's collection. SkillMeat has artifact metrics tables, but it needs project/user/collection usage rollups and recommendation-grade evidence, not only artifact outcome aggregates.

## Goals

1. Define a snapshot exchange contract where SkillMeat provides CCDash with all project-relevant artifacts, versions, deployment/profile metadata, collection membership, and optimization metadata.
2. Extend CCDash rollups so usage and effectiveness can be grouped by artifact, artifact version, project, collection, workflow, and user/principal.
3. Send normalized artifact usage rollups back to SkillMeat without raw prompts, raw transcripts, code, local paths, or sensitive identifiers.
4. Add CCDash artifact rankings for usage, cost, effectiveness, confidence, recency, and context pressure.
5. Add optimization recommendations that are explicit, evidence-backed, and scoped to safe actions.
6. Enable the `ccdash` skill to retrieve project artifact rankings and recommendation summaries for agent-facing workflow optimization.

## Non-Goals

1. Editing SkillMeat artifacts from CCDash in V1.
2. Automatically disabling or uninstalling artifacts without user approval.
3. Exporting raw session transcripts, prompts, file paths, tool arguments, or source code.
4. Building a full marketplace recommendation engine.
5. Replacing existing SkillMeat artifact metrics ingestion endpoints.
6. Solving every artifact identity mismatch; unresolved rows should be captured for reconciliation rather than guessed aggressively.

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-1 | Add a SkillMeat project artifact snapshot fetch in CCDash that returns artifacts, versions, content hashes, collection membership, deployment/profile/default status, and lifecycle metadata for the configured project/collection. | Must |
| FR-2 | Store snapshot identity and freshness in CCDash so rankings can distinguish missing, stale, disabled, loaded, observed-only, and unresolved artifacts. | Must |
| FR-3 | Extend CCDash rollups with `user_scope` where available from hosted auth or OTel user attributes; local mode must use a privacy-preserving pseudonymous user scope or omit the dimension. | Must |
| FR-4 | Compute artifact ranking rows by project, collection, user, artifact, version, workflow, and period. | Must |
| FR-5 | Include usage, token, cost, confidence, sample size, recency, success, efficiency, quality, risk, context-pressure, and unresolved-identity fields in ranking outputs. | Must |
| FR-6 | Emit project/user/collection-aware artifact usage rollups back to SkillMeat through additive endpoints or backward-compatible extensions to artifact outcome ingestion. | Must |
| FR-7 | SkillMeat must persist project-level and collection-level artifact usage metrics without losing existing artifact/version metrics behavior. | Must |
| FR-8 | CCDash must expose local ranking and recommendation APIs for Analytics, Workflow Effectiveness, Execution Workbench, and the `ccdash` skill. | Must |
| FR-9 | Recommendations must be categorized as `disable_candidate`, `load_on_demand`, `workflow_specific_swap`, `optimization_target`, `version_regression`, `identity_reconciliation`, or `insufficient_data`. | Must |
| FR-10 | Every recommendation must include evidence, confidence, affected artifact IDs, scope, and a non-destructive next action. | Must |
| FR-11 | Settings must show snapshot freshness, export freshness, unresolved identity count, and whether artifact intelligence is enabled for the project. | Should |
| FR-12 | SkillMeat should expose collection-level and project-level artifact rankings so catalog owners can identify high-value and low-yield artifacts across teams. | Should |

## Data Contract

### SkillMeat Snapshot to CCDash

The snapshot should be versioned and project-scoped:

```json
{
  "schemaVersion": "skillmeat-artifact-snapshot-v1",
  "generatedAt": "2026-05-06T00:00:00Z",
  "projectId": "skillmeat-project-id",
  "collectionId": "collection-id",
  "artifacts": [
    {
      "definitionType": "skill",
      "externalId": "skill:frontend-design",
      "artifactUuid": "uuid",
      "displayName": "frontend-design",
      "versionId": "version-id",
      "contentHash": "sha256:...",
      "collectionIds": ["collection-id"],
      "deploymentProfileIds": ["claude-code", "codex"],
      "defaultLoadMode": "always|on_demand|workflow_scoped|disabled",
      "workflowRefs": ["workflow-id"],
      "tags": ["frontend", "design"],
      "status": "active|deprecated|disabled|unresolved"
    }
  ]
}
```

### CCDash Rollup to SkillMeat

The rollup should extend the existing artifact outcome model rather than replacing it:

```json
{
  "schemaVersion": "ccdash-artifact-usage-rollup-v1",
  "projectSlug": "ccdash-project-id",
  "skillmeatProjectId": "skillmeat-project-id",
  "collectionId": "collection-id",
  "userScope": "hosted-principal-or-pseudonymous-local-scope",
  "period": "7d",
  "artifact": {
    "definitionType": "skill",
    "externalId": "skill:frontend-design",
    "artifactUuid": "uuid",
    "versionId": "version-id",
    "contentHash": "sha256:..."
  },
  "usage": {
    "exclusiveTokens": 12000,
    "supportingTokens": 24000,
    "costUsdModelIO": 0.42,
    "sessionCount": 8,
    "workflowCount": 3,
    "lastObservedAt": "2026-05-06T00:00:00Z",
    "averageConfidence": 0.83
  },
  "effectiveness": {
    "successScore": 0.78,
    "efficiencyScore": 0.64,
    "qualityScore": 0.72,
    "riskScore": 0.22,
    "sampleSize": 8
  },
  "recommendations": [
    {
      "type": "load_on_demand",
      "confidence": 0.81,
      "rationaleCode": "low_recency_high_context_pressure",
      "nextAction": "Review before changing deployment profile defaults."
    }
  ]
}
```

## Recommendation Semantics

Recommendations must be advisory and evidence-backed:

1. `disable_candidate`: artifact is always available but has no usage over a configured window and no policy requiring it.
2. `load_on_demand`: artifact has narrow workflow usage and high context pressure.
3. `workflow_specific_swap`: an alternative artifact/version has materially better effectiveness for a matching workflow.
4. `optimization_target`: artifact is high-utilization and has poor efficiency, high token cost, high risk, or low quality.
5. `version_regression`: newer version performs worse than prior version with adequate sample size.
6. `identity_reconciliation`: CCDash observed usage but cannot resolve it confidently to a SkillMeat artifact.
7. `insufficient_data`: sample size, confidence, or snapshot freshness is too weak for action.

## Product Surfaces

1. Analytics: add an artifact rankings view with filters for project, collection, user, period, artifact type, workflow, and recommendation type.
2. Workflow Effectiveness: show artifact contribution and top optimization targets for each workflow or stack.
3. Execution Workbench: surface recommended artifact set changes for the selected feature/workflow, with no automatic mutation.
4. Settings: show SkillMeat snapshot/export health and unresolved identity counts.
5. `ccdash` skill: expose a concise recommendation query that agents can use before selecting skills, agents, context modules, or workflow stacks.
6. SkillMeat: expose project and collection metrics so artifact owners can see adoption, effectiveness, and optimization priority across deployments.

## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Snapshot coverage | Definitions cached by type, no full project artifact snapshot | 95%+ of configured SkillMeat project artifacts appear in CCDash snapshot with identity and freshness | Snapshot validation job |
| Attribution-to-artifact resolution | Current usage attribution plus existing SkillMeat definitions | 90%+ high-confidence artifact-linked usage on representative projects | Calibration report |
| Per-user rollup availability | Not first-class | Hosted deployments expose user-scoped artifact usage where auth/OTel identity is available | API contract tests |
| Recommendation precision | No artifact lifecycle recommendations | 80%+ accepted/no-action-safe recommendations in manual review sample | Recommendation review log |
| SkillMeat feedback loop | Artifact/version outcomes exist | Project and collection usage rankings visible in SkillMeat | SkillMeat API/UI smoke |

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Identity mismatch between CCDash scopes and SkillMeat artifacts | Incorrect rankings or recommendations | Use snapshot IDs/content hashes first, alias matching second, unresolved quarantine last. |
| Recommendations become too aggressive | Users disable useful artifacts | Keep V1 advisory, require evidence/confidence, and never mutate artifacts automatically. |
| User-scoped metrics expose sensitive behavior | Privacy and compliance risk | Use hosted principal scopes only where authorized; pseudonymize local scopes; aggregate before export. |
| Snapshot staleness creates false unused-artifact recommendations | Bad action guidance | Include snapshot age in every recommendation and suppress destructive recommendations on stale snapshots. |
| Existing artifact metrics endpoints diverge from new rollups | Duplicate/conflicting truth | Treat existing artifact/version metrics as foundation; add project/user/collection dimensions via additive contract. |
| SkillMeat trust headers are mistaken for cryptographic proof | Overstated security boundary | Document metadata-only delegation and require receiver-side verification before trusted user-scoped writes. |

## Implementation Outline

1. Phase 1: Contract and snapshot foundation. Define snapshot/rollup schemas, CCDash DTOs, freshness semantics, and compatibility with existing SkillMeat artifact outcome payloads.
2. Phase 2: CCDash snapshot ingestion and storage. Fetch SkillMeat project/collection artifact snapshots, persist freshness and identity mapping, and surface diagnostics.
3. Phase 3: Ranking and recommendation engine. Compute artifact rankings and advisory recommendations from usage attribution, workflow effectiveness, snapshot state, and context pressure.
4. Phase 4: SkillMeat rollup export and persistence. Extend outbound telemetry and SkillMeat storage with project/user/collection dimensions.
5. Phase 5: UI and `ccdash` skill surfaces. Add Analytics, Workflow Effectiveness, Execution Workbench, Settings, and skill-facing query surfaces.
6. Phase 6: Validation, privacy review, docs, and rollout gates. Add contract tests, seeded fixture tests, recommendation calibration, and operator docs.

## Acceptance Criteria

1. CCDash can fetch and display a fresh SkillMeat artifact snapshot for a configured project and collection.
2. CCDash can produce artifact ranking rows grouped by project, collection, user, artifact, version, workflow, and period.
3. CCDash can generate non-mutating optimization recommendations with evidence and confidence.
4. SkillMeat can ingest or derive project/user/collection artifact usage rollups without regressing existing artifact metrics ingestion.
5. The `ccdash` skill can retrieve concise artifact usage and optimization recommendations for a project.
6. No exported payload includes raw prompts, raw transcript text, source code, absolute local paths, API keys, or unhashed local usernames.
7. Focused tests cover snapshot freshness, identity resolution, recommendation gating, export payload privacy, and unresolved-artifact quarantine behavior.

## Open Questions

1. Should the SkillMeat snapshot be a new endpoint, or should CCDash compose it from existing artifact/workflow/context/bundle endpoints in V1?
2. Should per-user rollups be stored in SkillMeat for local mode, or only for hosted authenticated deployments?
3. Should `context_pressure` be computed from observed token attribution only, or also from static artifact size/context footprint?
4. Should recommendation review outcomes be written back to SkillMeat so accepted/rejected recommendations become training signals?
5. Should collection-level rankings include artifacts not deployed in the project, or only artifacts available through configured deployment profiles?
