---
schema_name: ccdash_document
schema_version: 3
doc_type: prd
doc_subtype: refactor_prd
status: completed
category: refactors
title: 'PRD: Planning / Forensics Boundary Extraction V1'
description: Refactor planning and execution workflows away from full session-forensics
  dependencies by introducing shared bounded evidence contracts and clearer product-domain
  ownership.
summary: Separate planning/execution from session forensics at read-contract and frontend
  ownership boundaries while preserving one shared evidence substrate and canonical
  session-ingest path.
author: codex
created: 2026-05-06
updated: '2026-05-07'
priority: high
risk_level: high
complexity: high
track: Planning / Forensics / Architecture
timeline_estimate: 2-4 engineering weeks across 6 phases
feature_slug: planning-forensics-boundary-extraction-v1
feature_family: planning-forensics-boundary-extraction
feature_version: v1
lineage_family: planning-forensics-boundary-extraction
lineage_parent:
  ref: docs/project_plans/PRDs/enhancements/ccdash-planning-control-plane-v1.md
  kind: builds_on
lineage_children: []
lineage_type: refactor
problem_statement: Planning and execution currently need session-derived evidence,
  but some paths depend on full session-forensics DTOs and planning-specific correlation
  logic, making product boundaries unclear and increasing regression risk.
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
- prd
- refactor
- planning
- execution
- forensics
- sessions
- metrics
- api-contracts
related_documents:
- docs/project_plans/reports/planning-forensics-split-refactor-assessment-2026-05-06.md
- docs/project_plans/implementation_plans/refactors/planning-forensics-boundary-extraction-v1.md
- docs/project_plans/design-specs/ccdash-planning-control-plane-architecture.md
- docs/project_plans/PRDs/refactors/feature-surface-data-loading-redesign-v1.md
- docs/project_plans/PRDs/integrations/otel-session-metrics-ingestion-v1.md
context_files:
- backend/application/services/agent_queries/planning.py
- backend/application/services/agent_queries/feature_forensics.py
- backend/application/services/agent_queries/planning_sessions.py
- backend/routers/agent.py
- backend/ingestion/models.py
- backend/ingestion/session_ingest_service.py
- backend/services/feature_execution.py
- components/ProjectBoard.tsx
- services/featureSurface.ts
implementation_plan_ref: docs/project_plans/implementation_plans/refactors/planning-forensics-boundary-extraction-v1.md
---

# Feature Brief & Metadata

**Feature Name:** Planning / Forensics Boundary Extraction

**Filepath Name:** `planning-forensics-boundary-extraction-v1`

**Date:** 2026-05-06

**Author:** Codex

**Related Documents:**
- `/docs/project_plans/reports/planning-forensics-split-refactor-assessment-2026-05-06.md`
- `/docs/project_plans/implementation_plans/refactors/planning-forensics-boundary-extraction-v1.md`
- `/docs/project_plans/design-specs/ccdash-planning-control-plane-architecture.md`
- `/docs/project_plans/PRDs/refactors/feature-surface-data-loading-redesign-v1.md`
- `/docs/project_plans/PRDs/integrations/otel-session-metrics-ingestion-v1.md`

---

## 1. Executive Summary

Planning, execution, session forensics, metrics, and workflow intelligence currently share data sources and some query paths. The overlap is useful, but the product responsibilities are separate. Planning should not depend on full forensic DTOs to show token/session evidence, and planning UI components should not own session-forensics detail behavior.

This refactor introduces a shared bounded evidence read contract and extracts product-domain boundaries without creating a new app, database, or ingestion path. Planning and execution will consume evidence summaries; session forensics remains authoritative for transcript and telemetry detail; workflow intelligence becomes its own product module; and the shared substrate continues to own plan-doc parsing, canonical links, ingestion, provenance, cache, and live invalidation.

**Priority:** HIGH

**Key Outcomes:**
- Planning/execution no longer directly depend on full feature-forensics DTOs for token/session summaries.
- Session forensics remains authoritative for observed sessions, transcript facts, source provenance, usage/cost, telemetry, and metrics.
- Planning remains authoritative for plan docs, phase/task context, raw/effective status, mismatch/provenance, and next-run preparation.
- Execution remains authoritative for run creation, approvals, provider/worktree context, policy, retries, and run events.
- Existing API/UI response fields remain backward compatible during migration.

## Architecture Diagrams

![CCDash split refactor shared evidence substrate](../../assets/planning-forensics-boundary-extraction-v1/shared-evidence-substrate.png)

![CCDash split refactor UI and agent flow](../../assets/planning-forensics-boundary-extraction-v1/ui-agent-flow.png)

---

## 2. Context & Background

CCDash has been evolving into both:

- A planning/execution control plane over markdown/frontmatter artifacts, features, phases, worktrees, and agent runs.
- A session forensics and metrics system over observed sessions, transcripts, usage, telemetry, workflow signals, and source provenance.

The two capabilities were combined because they use the same underlying evidence: feature links, sessions, documents, task hints, token usage, and workflow signals. That common substrate should remain shared. The issue is that product-specific services and UI components now cross boundaries too freely.

Examples:

- Planning context calls feature forensics to obtain token usage.
- Planning session board correlation logic is useful outside planning.
- Feature modal code combines planning board behavior, linked sessions, feature detail, test health, and lazy tab behavior.
- The agent router exposes planning, feature forensics, workflow diagnostics, and execution-adjacent next-run preview from one adapter surface.

Existing architecture already supports a cleaner split:

- `backend/ingestion/NormalizedSessionEnvelope` is the right shared ingest contract.
- `SessionIngestService` is the right shared canonical persistence path.
- Feature-surface v1 already established bounded card/modal/session DTOs.
- Execution runs and planning worktree context are already stored as operational state distinct from transcript storage.

---

## 3. Problem Statement

As CCDash grows into a planning and execution control plane, planning workflows need session-derived evidence without inheriting the full complexity, payload shape, and ownership of session forensics.

As a developer or agent working in the codebase, I need clear domain boundaries so changes to transcript enrichment, metrics ingestion, or forensic session detail do not accidentally change planning semantics, and planning UI work does not need to understand forensic transcript internals.

**Technical Root Cause:**
- Planning reads call feature-forensics services directly for bounded evidence needs.
- Session-feature correlation exists in planning-specific code even though multiple surfaces need it.
- Feature modal state is not separated by domain.
- Workflow diagnostics live beside planning/forensics agent routes without a clear product module owner.
- Ingest contracts already declare partial/event merge policies, but the persistence path only supports complete upserts, so OTel merge expansion should not be mixed into this refactor.

---

## 4. Goals & Success Metrics

### Primary Goals

**Goal 1: Shared Evidence Summary Contract**
- Add a transport-neutral `FeatureEvidenceSummary` read contract for bounded cross-domain evidence.
- Include session count, representative sessions, token usage by model, total tokens, cost when available, workflow mix, latest activity, freshness/confidence, and source refs.
- Make the contract additive and backward compatible.

**Goal 2: Planning Uses Summaries, Not Full Forensics**
- Planning summary and feature context should consume evidence summaries for token/session evidence.
- Preserve current planning response fields during migration.
- Avoid loading transcript-heavy forensic detail for planning-only requests.

**Goal 3: Shared Session-Feature Correlation**
- Move reusable session-feature correlation behind a shared helper/query boundary.
- Preserve explicit links, phase hints, task hints, command-token detection, and lineage behavior.
- Keep `entity_links` as the bridge contract for v1.

**Goal 4: Frontend Domain Separation**
- Extract a reusable feature-detail shell/data boundary from the project-board modal.
- Keep planning-native tabs and actions in planning components.
- Keep transcript/session evidence behind forensics-specific components.
- Keep execution run/worktree state behind execution-specific components.

**Goal 5: Workflow Intelligence Ownership**
- Treat workflow diagnostics and effectiveness as a workflow-intelligence module.
- Keep Analytics as a consumer/linking surface rather than the owner of workflow behavior.

### Success Metrics

- Planning feature context returns the same token/session fields as before but no longer directly calls full feature forensics.
- Feature evidence summary can be used by planning, execution, and feature/session surfaces without transcript log enrichment.
- Feature modal sessions remain lazy and do not reintroduce eager linked-session detail loading.
- Existing `/api/agent/planning/*` and feature-forensics endpoints remain compatible.
- No new database split, storage fork, or ingestion bypass is introduced.

---

## 5. Requirements

### Functional Requirements

1. Add `FeatureEvidenceSummary` DTOs and a transport-neutral query/service.
2. Expose the evidence summary additively through backend routes.
3. Update planning query services to use the evidence summary for token/session fields.
4. Extract shared session-feature correlation logic from planning-specific ownership.
5. Extract frontend feature detail shell/data boundaries so planning, forensics, and execution tabs are owned by their domains.
6. Move workflow diagnostics/effectiveness UI ownership to a workflow-intelligence module or equivalent local structure.
7. Keep current public response fields stable until all consumers are migrated.

### Non-Functional Requirements

1. Evidence summary queries must be bounded and must not fetch transcript logs by default.
2. Query/service boundaries must remain transport-neutral.
3. JSONL complete-session ingest behavior must remain unchanged.
4. OTel partial metrics and append-event merge policies must remain deferred unless separately planned.
5. Cache and live invalidation behavior must be documented for planning, feature, session, and workflow consumers.

---

## 6. Scope

### In Scope

- Backend evidence-summary contract and additive route exposure.
- Planning query migration to summary evidence.
- Shared session-feature correlation boundary.
- Frontend feature-detail shell extraction and domain-specific tab ownership.
- Workflow diagnostics/effectiveness ownership cleanup.
- Focused backend/frontend tests and compatibility checks.
- Documentation updates in report, PRD, and implementation plan.

### Out Of Scope

- New app or service split.
- Split database or large storage migration.
- Removing existing public response fields before consumers migrate.
- Implementing OTel `PATCH_METRICS` or `APPEND_EVENTS`.
- Replacing canonical markdown/frontmatter plan docs.
- Replacing `backend/ingestion/SessionIngestService`.

---

## 7. Dependencies & Assumptions

- `backend/ingestion/NormalizedSessionEnvelope` remains the shared session-ingest boundary.
- `entity_links` remains the v1 feature/document/session bridge.
- Existing feature-surface v1 contracts remain available during migration.
- Planning control plane keeps markdown/frontmatter canonical and planning graph data derived.
- Execution run storage remains operational state separate from observed session transcript storage.
- Backward compatibility is required for existing UI and REST consumers.

---

## 8. Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Evidence summary becomes another large DTO | Recreates current coupling | Keep summary fields bounded and prohibit transcript-log enrichment by default. |
| Planning response fields regress | Breaks planning UI and agent clients | Add compatibility tests for token telemetry and feature context fields. |
| Correlation extraction changes heuristics | Session board and feature detail drift | Preserve existing fixtures and compare old/new correlation outputs. |
| Frontend extraction breaks modal lazy loading | Reintroduces eager requests or empty tabs | Add focused UI tests for tab loading, retries, encoded IDs, and no eager session calls. |
| Workflow move breaks Analytics entrypoints | Users lose discoverability | Keep Analytics links or embeds while moving module ownership. |
| OTel merge semantics get mixed into split work | Partial data corrupts canonical truth | Defer merge-policy implementation to a separate plan. |

---

## 9. Target State

Planning, execution, forensics, and workflow intelligence are separate product modules over a shared evidence substrate.

Planning asks for bounded evidence summaries when it needs token/session context. Session forensics assembles full transcript and telemetry detail only when forensic views request it. Execution uses summary evidence for run-prep decisions and keeps run lifecycle state separate from observed session state. Workflow intelligence owns diagnostics and effectiveness surfaces.

The shared substrate owns:

- Plan/frontmatter ingestion and derived planning graph inputs.
- Canonical feature/document/session links.
- Normalized session ingestion and canonical session stores.
- Bounded evidence summary contracts.
- Freshness/confidence/source refs.
- Cache and live invalidation helpers.

---

## 10. Acceptance Criteria

- `FeatureEvidenceSummary` service and DTO exist and are covered by unit tests.
- Planning feature context no longer directly imports or calls the full feature-forensics query service for token/session summaries.
- Existing planning token telemetry fields remain present and compatible.
- Session-feature correlation is callable from shared code outside planning-specific board logic.
- Project board feature detail code has a reusable shell/data boundary with planning, forensics, and execution concerns separated.
- Workflow diagnostics/effectiveness has clear module ownership and Analytics remains able to navigate to it.
- Existing feature-forensics endpoints still return full forensic detail.
- JSONL ingestion tests still pass and no partial OTel merge behavior is introduced.

---

## 11. Implementation Overview

The implementation should proceed in bounded phases:

1. Contract and route addition for `FeatureEvidenceSummary`.
2. Planning query migration to summary evidence.
3. Session-feature correlation extraction.
4. Frontend feature-detail shell extraction and domain tab split.
5. Workflow intelligence ownership cleanup.
6. Compatibility, regression, and docs validation.

Progress tracking should be created only when implementation starts.
