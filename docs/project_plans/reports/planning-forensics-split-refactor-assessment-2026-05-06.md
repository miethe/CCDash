---
schema_name: ccdash_document
schema_version: 3
doc_type: report
doc_subtype: investigation_report
status: published
category: investigations
title: "Planning / Forensics Split Refactor - Assessment Report"
description: "Findings and recommendations for separating planning and execution workflows from session forensics and metrics while preserving a shared CCDash evidence substrate."
summary: "Planning and execution should split from session forensics at product and query boundaries, while sharing canonical plan docs, feature/session links, normalized session ingestion, provenance, cache, and live invalidation."
author: codex
created: 2026-05-06
updated: 2026-05-06
priority: high
risk_level: high
complexity: high
track: Planning / Forensics / Architecture
feature_slug: planning-forensics-boundary-extraction-v1
feature_family: planning-forensics-boundary-extraction
feature_version: v1
lineage_family: planning-forensics-boundary-extraction
lineage_parent:
  ref: docs/project_plans/PRDs/enhancements/ccdash-planning-control-plane-v1.md
  kind: builds_on
lineage_children: []
lineage_type: refactor
owner: platform-engineering
owners:
  - platform-engineering
  - backend-platform
contributors:
  - ai-agents
audience:
  - ai-agents
  - developers
  - platform-engineering
tags:
  - report
  - refactor
  - planning
  - forensics
  - execution
  - sessions
  - metrics
  - architecture
related_documents:
  - docs/project_plans/PRDs/refactors/planning-forensics-boundary-extraction-v1.md
  - docs/project_plans/implementation_plans/refactors/planning-forensics-boundary-extraction-v1.md
  - docs/project_plans/design-specs/ccdash-planning-control-plane-architecture.md
  - docs/project_plans/PRDs/refactors/feature-surface-data-loading-redesign-v1.md
  - docs/project_plans/PRDs/integrations/otel-session-metrics-ingestion-v1.md
context_files:
  - backend/application/services/agent_queries/planning.py
  - backend/application/services/agent_queries/feature_forensics.py
  - backend/routers/agent.py
  - backend/ingestion/models.py
  - backend/ingestion/session_ingest_service.py
  - components/ProjectBoard.tsx
---

# Planning / Forensics Split Refactor - Assessment Report

## Executive Summary

Planning/execution workflows and session forensics/metrics should be separated as product domains and query boundaries. They should not be split into separate databases, a second service, or a separate app in the first refactor.

The current coupling exists because both surfaces need the same evidence: feature links, plan docs, session references, token usage, workflow signals, freshness, and provenance. That shared evidence need is real, but it does not require planning to call full forensic DTOs or frontend planning components to own session-detail behavior.

The safest target is a shared evidence substrate:

- Plan/frontmatter parsing and the derived planning graph remain shared.
- Canonical feature, document, and session links remain shared.
- `backend/ingestion/NormalizedSessionEnvelope` and `SessionIngestService` remain the shared write boundary for observed session data.
- A new bounded read contract, `FeatureEvidenceSummary`, becomes the shared read boundary for planning, execution, and feature/session surfaces.

The main implementation risk is splitting storage or UI ownership before establishing the read contracts. Doing that would create duplicate truth and force downstream consumers to reconcile conflicting planning, execution, and forensics facts.

## Architecture Diagrams

![CCDash split refactor shared evidence substrate](../assets/planning-forensics-boundary-extraction-v1/shared-evidence-substrate.png)

![CCDash split refactor UI and agent flow](../assets/planning-forensics-boundary-extraction-v1/ui-agent-flow.png)

## Method

This report is based on a code and docs inspection of:

- Planning agent query services and `/api/agent/planning/*` routes.
- Feature forensics query services and `/api/agent/feature-forensics/*`.
- Planning session board correlation logic.
- Feature modal and feature-surface frontend data loading.
- The normalized ingestion layer introduced for JSONL and future OTel sources.
- Execution run and planning worktree storage.
- Existing CCDash planning-control-plane, feature-surface, and OTel ingestion planning artifacts.

## Current Coupling Map

### Planning Reads Forensics Internals

`PlanningQueryService` imports and constructs `FeatureForensicsQueryService` directly in `backend/application/services/agent_queries/planning.py:44-69`. Feature planning context then calls `get_forensics()` to obtain token usage and total tokens in `backend/application/services/agent_queries/planning.py:1404-1417`.

That creates a dependency from planning context to the full feature-forensics query surface. The planning UI needs bounded evidence fields, not the full forensic assembly path.

### Feature Forensics Does Transcript-Heavy Enrichment

`FeatureForensicsQueryService` treats linked sessions as the authoritative feature session list and documents the eventual-consistency model in `backend/application/services/agent_queries/feature_forensics.py:228-239`.

The same module enriches session refs by fetching transcript logs and deriving workflow/tool/failure signals in `backend/application/services/agent_queries/feature_forensics.py:156-205`. That is correct for forensics. It is too heavy and too domain-specific to be a planning dependency.

### Agent Router Mixes Product Domains

`backend/routers/agent.py` currently exposes project status, feature forensics, workflow diagnostics, planning summary/graph/context/phase operations, planning session board, and next-run preview from one router. Examples:

- Feature forensics: `backend/routers/agent.py:111-125`
- Workflow diagnostics: `backend/routers/agent.py:128-142`
- Planning summary and graph: `backend/routers/agent.py:170-229`
- Planning feature context and phase operations: `backend/routers/agent.py:232-299`
- Planning session board: `backend/routers/agent.py:310-376`

The router can remain a REST adapter, but the underlying services need clearer ownership boundaries.

### Planning Session Board Owns Reusable Correlation

The planning session board correlates agent sessions to features, phases, tasks, command tokens, and lineage. That behavior is not planning-only. Feature detail, session detail, workflow diagnostics, and execution review all need consistent answers about how a session relates to a feature.

The first refactor should move reusable correlation behind a shared query/helper boundary. It should keep `entity_links` as the bridge contract for v1 rather than adding a new projection table immediately.

### Feature Modal Still Mixes Product Concerns

`ProjectBoardFeatureModal` lives in `components/ProjectBoard.tsx:1379` and owns planning-board modal state, status updates, linked-session loading, feature test health, tab lifecycle, and compatibility state. It now uses `useFeatureModalData()` for lazy sections at `components/ProjectBoard.tsx:1427`, but still calls legacy feature detail through `getLegacyFeatureDetail()` at `components/ProjectBoard.tsx:1432`.

This is a good candidate for frontend boundary extraction:

- A reusable feature-detail shell owns tab frame, loading, retry, and section boundaries.
- Planning owns planning-native tabs/actions.
- Session forensics owns transcript/session evidence views.
- Execution owns run/approval/worktree detail.

### Execution Storage Is Already Mostly Separate

Execution run state is already modeled as operational state in `execution_runs`, `execution_run_events`, and `execution_approvals` in `backend/db/sqlite_migrations.py:847-906`. Planning worktree launch context is separately modeled in `planning_worktree_contexts` in `backend/db/sqlite_migrations.py:909-936`.

This supports a domain split without a storage fork: execution should own run lifecycle state, while session forensics remains the observed evidence layer.

### Ingestion Has The Right Shared Boundary

`backend/ingestion/models.py:47-76` defines `NormalizedSessionEnvelope` as a source-neutral payload for JSONL and future OTel adapters. `backend/ingestion/session_ingest_service.py:111-215` persists complete envelopes into canonical session rows, messages, logs, tools, files, artifacts, observability fields, usage attribution, telemetry, commit correlations, intelligence facts, export, and live updates.

That is the correct shared write boundary. Planning and execution should not bypass it, and future OTel metrics should not feed a parallel analytics-only store.

One limitation is explicit: `SessionIngestService.persist_envelope()` rejects non-`UPSERT_COMPLETE` merge policies today in `backend/ingestion/session_ingest_service.py:120-127`. The models define `PATCH_METRICS` and `APPEND_EVENTS`, but those should stay deferred until the read contracts are stable.

## Recommendation

Split the system by domain responsibility:

| Domain | Owns | Must Not Own |
| --- | --- | --- |
| Planning | Plan docs, planning graph, raw/effective status, mismatch/provenance, phases, tasks, batch/run-prep context, open questions | Transcript enrichment, token aggregation internals, forensic session DTO assembly |
| Execution | Run creation, approvals, provider/worktree context, policy, retry state, run events | Canonical transcript storage, observed session provenance, plan-doc parsing |
| Session Forensics / Metrics | Sessions, messages, transcript facts, source provenance, usage/cost, telemetry, intelligence facts, forensic detail | Planning graph status, execution run lifecycle decisions |
| Workflow Intelligence | Workflow effectiveness, diagnostics, workflow mix, rework/failure signals | Generic analytics ownership or planning-specific phase/run behavior |
| Shared Evidence Substrate | Feature/document/session links, bounded evidence summaries, freshness/confidence, cache/provenance helpers, live invalidation | Product-specific UI flows or heavy detail DTOs |

Do not split the database, app, or ingestion service in v1. The data sources overlap intentionally. The split should happen at query contracts and frontend ownership boundaries first.

## Proposed Boundary Contract

Add a transport-neutral `FeatureEvidenceSummary` query/service. It should return only fields needed across domains:

- `feature_id`
- `project_id`
- `session_count`
- `representative_sessions`
- `primary_session_ids`
- `token_usage_by_model`
- `total_tokens`
- `estimated_cost`
- `workflow_mix`
- `latest_activity_at`
- `freshness`
- `confidence`
- `source_refs`
- `warnings`

Planning should consume this contract for token/session evidence instead of calling full feature forensics. Execution can consume it for run-prep evidence. Feature/session surfaces can consume it for bounded summaries, then load forensic detail only when the user opens forensic tabs.

## Difficulty Assessment

| Area | Difficulty | Rationale |
| --- | --- | --- |
| Docs and contract inventory | Low | Existing docs and plans already point toward the split. |
| Backend evidence summary service | Medium | Requires careful aggregation without recreating full forensic behavior. |
| Planning query migration | Medium | Must preserve current response fields while removing direct full-forensics dependency. |
| Session-feature correlation extraction | Medium to High | Existing correlation has multiple heuristics and several downstream consumers. |
| Frontend modal/data boundary extraction | Medium to High | `ProjectBoardFeatureModal` is large and mixes state, tabs, lazy loading, and compatibility paths. |
| Workflow intelligence ownership cleanup | Medium | Mostly modular ownership and navigation, but current Analytics expectations must be preserved. |
| Ingest merge-policy hardening | High | Partial metrics and append-only event semantics can corrupt truth if merged prematurely. Defer until read boundaries are stable. |

## Recommended Phasing

1. Create docs and lock boundaries: this report, the PRD, and implementation plan.
2. Add the shared `FeatureEvidenceSummary` read contract and service.
3. Move planning token/session evidence to the summary contract while preserving existing planning DTO fields.
4. Extract reusable session-feature correlation behind a shared helper/query boundary.
5. Extract frontend feature-detail shell and split planning/session/execution tabs by domain.
6. Move workflow diagnostics/effectiveness under workflow-intelligence ownership with Analytics linking to it.
7. Defer OTel `PATCH_METRICS` and `APPEND_EVENTS` implementation until after the above boundaries are stable.

## Open Questions

- Whether `FeatureEvidenceSummary` should be exposed only through `/api/agent/*` initially or also through `/api/v1/features/*` in the same phase.
- Whether session-feature correlation should remain query-only in v1 or gain a storage-backed projection after performance measurement.
- Whether planning next-run preview should consume only evidence summaries or optionally request richer forensic context when the user explicitly includes selected sessions.

## Final Recommendation

Proceed with the split refactor, but treat it as a boundary extraction, not a platform split. CCDash should keep one shared evidence substrate and one canonical ingestion path, then separate planning, execution, forensics, and workflow intelligence through bounded read contracts and frontend module ownership.
