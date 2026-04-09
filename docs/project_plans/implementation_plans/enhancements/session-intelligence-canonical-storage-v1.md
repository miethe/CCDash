---
schema_name: ccdash_document
schema_version: 3
doc_type: implementation_plan
doc_subtype: implementation_plan
primary_doc_role: supporting_document
status: in-progress
category: enhancements
title: "Implementation Plan: Session Intelligence Canonical Storage V1"
description: "Turn the existing session_messages groundwork into an enterprise-ready canonical transcript and intelligence platform for semantic search, DX sentiment, code churn, scope drift, and approval-gated SkillMeat memory drafts."
summary: "Build on the DB caching checklist's Phase 3 seams and the data-platform storage-profile contract to make Postgres the canonical enterprise transcript store while preserving local SQLite cache behavior and stable read models."
author: codex
audience:
  - ai-agents
  - developers
  - platform-engineering
  - backend-platform
  - data-platform
created: 2026-04-01
updated: 2026-04-07
commit_refs:
- https://github.com/miethe/CCDash/commit/b88ad78
- https://github.com/miethe/CCDash/commit/d702a74
- https://github.com/miethe/CCDash/commit/932e5e0
- https://github.com/miethe/CCDash/commit/be3b9fd
pr_refs: []
tags:
  - implementation
  - session-intelligence
  - canonical-storage
  - postgres
  - pgvector
  - analytics
  - skillmeat
priority: high
risk_level: high
complexity: high
track: Data
timeline_estimate: 5-7 weeks across 7 phases
feature_slug: session-intelligence-canonical-storage-v1
feature_family: ccdash-data-platform
feature_version: v1
lineage_family: ccdash-data-platform
lineage_parent:
  ref: docs/project_plans/PRDs/enhancements/session-intelligence-canonical-storage-v1.md
  kind: implementation_of
lineage_children: []
lineage_type: enhancement
linked_features: []
prd: docs/project_plans/PRDs/enhancements/session-intelligence-canonical-storage-v1.md
prd_ref: docs/project_plans/PRDs/enhancements/session-intelligence-canonical-storage-v1.md
plan_ref: session-intelligence-canonical-storage-v1
owner: data-platform
owners:
  - data-platform
  - platform-engineering
contributors:
  - ai-agents
related_documents:
  - docs/project_plans/PRDs/enhancements/session-intelligence-canonical-storage-v1.md
  - .claude/plans/db-caching-layer-v1-execution-checklist-2026-03-27.md
  - docs/project_plans/implementation_plans/db-caching-layer-v1.md
  - docs/project_plans/implementation_plans/refactors/data-platform-modularization-v1.md
  - docs/guides/storage-profiles-guide.md
  - docs/guides/data-domain-ownership-matrix.md
  - docs/guides/data-domain-schema-layout.md
  - docs/guides/session-transcript-contract-guide.md
context_files:
  - backend/application/services/sessions.py
  - backend/services/session_transcript_contract.py
  - backend/services/session_transcript_projection.py
  - backend/db/sync_engine.py
  - backend/db/sqlite_migrations.py
  - backend/db/postgres_migrations.py
  - backend/db/repositories/session_messages.py
  - backend/db/repositories/postgres/session_messages.py
  - backend/db/repositories/sessions.py
  - backend/db/repositories/postgres/sessions.py
  - backend/runtime/container.py
  - backend/runtime_ports.py
  - backend/routers/api.py
  - backend/routers/analytics.py
  - backend/models.py
  - types.ts
  - services/analytics.ts
  - components/SessionInspector.tsx
  - components/execution/WorkflowEffectivenessSurface.tsx
  - backend/tests/test_session_messages_groundwork.py
  - backend/tests/test_session_transcript_projection.py
---

# Implementation Plan: Session Intelligence Canonical Storage V1

## Objective

Turn the existing `session_messages` transcript seam into a real session-intelligence platform:

1. make Postgres the canonical enterprise transcript store,
2. preserve local SQLite as a supported cache-oriented mode,
3. add enterprise-grade semantic search and derived intelligence facts,
4. expose DX sentiment, churn, and scope-drift analytics through stable read models,
5. and close the loop with approval-gated SkillMeat memory drafts rather than direct blind write-back.

## Entry Gate And Applicability

This plan exists because the DB caching execution checklist explicitly says the session-intelligence PRD should not begin full delivery until two conditions are met:

1. checklist Phase 3 is complete,
2. and a dedicated implementation plan exists for canonical transcript storage, embeddings, churn analytics, and scope-drift analytics.

This plan therefore assumes the following are true before Phase 1 implementation starts:

1. `db-caching-layer-v1` Phase 3 groundwork is complete and accepted.
2. The Phase 2 storage-profile model is settled enough to distinguish `local` from `enterprise`.
3. Shared-Postgres isolation rules are documented if enterprise mode may co-locate with SkillMeat.

If any of those assumptions are false, stop and finish the prerequisite checklist work instead of partially starting this plan.

## Current Baseline

CCDash is not starting from zero:

1. `session_messages` already exists in both SQLite and Postgres migrations.
2. Both local and enterprise storage adapters already expose a `session_messages` repository.
3. The sync engine already projects legacy session logs into canonical `session_messages`.
4. `SessionTranscriptService` already prefers `session_messages` and falls back to legacy `session_logs`.
5. Current transcript rows already preserve message ordering, provenance, entry UUIDs, parent UUIDs, family identifiers, and parent/root session references.
6. The data-domain ownership and schema-layout guides already classify `session_messages` as an inherited transcript seam under the `sessions` root rather than a directly ownable entity.
7. Runtime status already reports `canonicalSessionStore`, which provides a useful operator-facing seam for later rollout checks.

What is still missing:

1. Postgres is not yet the authoritative enterprise transcript source across ingest and query paths.
2. `pgvector` and semantic indexing are not present.
3. DX sentiment, churn, and scope-drift fact models do not exist as first-class derived tables.
4. There is no enterprise-ready query layer for semantic transcript search or intelligence summaries.
5. There is no approval-gated pipeline that drafts SkillMeat memory candidates from successful sessions.

## Scope And Fixed Decisions

In scope:

1. Promote the current transcript seam into a canonical enterprise transcript pipeline.
2. Add the Postgres-only extension and derived-fact path needed for semantic search and session intelligence.
3. Define stable services and APIs for transcript search, DX sentiment, churn, and scope drift.
4. Surface the intelligence in existing CCDash UX without breaking current session read models.
5. Add approval-gated SkillMeat memory-draft creation based on successful sessions.

Out of scope:

1. Replacing the local-first SQLite experience with enterprise-only assumptions.
2. Rebuilding the full DB caching layer or revisiting the storage-profile contract already covered by earlier plans.
3. Warehouse or OLAP redesign.
4. Direct auto-publish of generated memory artifacts to SkillMeat without a user-facing approval step.
5. Broad auth or RBAC delivery beyond the scope identifiers and ownership rules already defined by data-platform work.

Non-negotiables:

1. `local` mode remains functional without `pgvector`, enterprise-only tables, or hosted-worker assumptions.
2. `enterprise` mode treats Postgres as canonical for transcript intelligence, not as a parity cache backend.
3. `session_messages` remains inherited from the parent `sessions` root and does not grow direct ownership columns.
4. Existing session detail APIs stay stable through a compatibility projection layer until canonical reads fully cover the required payloads.
5. Derived intelligence facts are reproducible from canonical transcript plus existing file/update/document evidence and should not encode opaque one-off heuristics without provenance.

## Target Platform Shape

### Storage Posture

| Mode | Transcript source of truth | Intelligence capability | Notes |
|---|---|---|---|
| `local` | SQLite `session_messages` projected from local ingest | Limited, optional, cache-oriented | Local mode may keep transcript projection and lightweight analytics without requiring embeddings or hosted-only workers |
| `enterprise` | Postgres canonical transcript storage | Full | Semantic search, derived intelligence facts, and memory-draft generation run against Postgres |
| `enterprise` shared instance | Postgres canonical transcript storage with explicit isolation | Full | Schema and tenancy rules from prior data-platform work must hold before rollout |

### Canonical Data Components

| Concern | Storage shape | Ownership posture | Notes |
|---|---|---|---|
| Transcript rows | `session_messages` | Inherited from `sessions` | Existing seam remains the parent entity for transcript intelligence |
| Semantic vectors | `session_embeddings` | Inherited from transcript/session scope | Enterprise-only, `pgvector` enabled |
| DX sentiment facts | `session_sentiment_facts` or equivalent derived table | Inherited | Derived from canonical user-facing transcript segments |
| Code churn facts | `session_code_churn` | Inherited | Derived from `session_file_updates`, diffs, and transcript turn order |
| Scope drift facts | `session_scope_drift_facts` or equivalent derived table | Inherited | Derived from plan blast radius plus actual file/resource footprint |
| Memory draft candidates | `session_memory_drafts` or equivalent operational table | Scope-aware operational state | Drafts remain reviewable CCDash artifacts until approved |

### Architecture Rules

1. Ingest once into canonical transcript rows, derive many downstream facts.
2. Canonical transcript writes happen at sync/ingest boundaries, not in UI request paths.
3. Intelligence facts are append-or-recompute safe and must be backfillable.
4. Search and analytics APIs should read from stable query services, not raw router SQL.
5. SkillMeat write-back remains a separate, approval-gated workflow from transcript ingestion.

## Phase Overview

| Phase | Title | Effort | Duration | Critical Path | Objective |
|---|---|---:|---|---|---|
| 1 | Canonical Transcript Contract Hardening | 10 pts | 4-5 days | Yes | Freeze transcript identity, provenance, compatibility, and ingest guarantees |
| 2 | Enterprise Transcript Canonicalization And Embeddings Substrate | 12 pts | 1 week | Yes | Make Postgres the enterprise transcript authority and add `pgvector`-ready storage |
| 3 | Intelligence Fact Pipelines | 12 pts | 1 week | Yes | Produce reproducible sentiment, churn, and scope-drift facts from canonical data |
| 4 | Query Services And API Surfaces | 10 pts | 4-5 days | Yes | Expose semantic search and intelligence summaries through stable backend contracts |
| 5 | UI And Workflow Surfaces | 8 pts | 3-4 days | No | Surface transcript intelligence in Session and execution UX |
| 6 | SkillMeat Memory Draft Loop | 8 pts | 3-4 days | No | Draft reviewable memory candidates from successful sessions |
| 7 | Backfill, Validation, And Rollout | 10 pts | 4-5 days | Final gate | Backfill, validate, document, and gate rollout by storage profile |

**Total**: ~70 story points over 5-7 weeks

## Implementation Strategy

### Critical Path

1. Freeze transcript identity and compatibility semantics before changing enterprise ingest behavior.
2. Land Postgres canonical transcript guarantees before any semantic search or intelligence metrics depend on them.
3. Build derived-fact pipelines before public APIs or UI surfaces depend on the metrics.
4. Keep SkillMeat write-back last, behind explicit review and operator controls.
5. Finish with backfill, health checks, and documentation so enterprise rollout is observable and reversible.

### Parallel Work Opportunities

1. Embedding-service integration can begin once Phase 2 finalizes the transcript block contract.
2. Scope-drift calculation design can start while churn analytics are being implemented because they depend on different evidence sources.
3. UI shells can begin against mocked API payloads once Phase 4 contracts are frozen.
4. Approval UX for memory drafts can proceed in parallel with extraction heuristics after the draft data model is fixed.

### Migration Order

1. Canonical transcript contract hardening
2. Enterprise canonical writes and `pgvector` substrate
3. Derived intelligence fact computation and backfill jobs
4. Query services and APIs
5. UI surfaces and operator workflows
6. Approval-gated SkillMeat draft loop
7. Rollout by profile with health and regression checks

## Phase 1: Canonical Transcript Contract Hardening

**Assigned Subagent(s)**: backend-architect, data-layer-expert, python-backend-engineer

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---|---|---|---|---:|---|---|
| SICS-001 | Transcript Contract Freeze | Audit the existing `session_messages` contract across parser projection, sync ingest, repositories, and transcript reads; freeze required fields for identity, provenance, family, and lineage behavior. | Canonical transcript fields are documented with clear semantics for `message_id`, ordering, provenance, lineage, and fallback behavior. | 3 pts | backend-architect, data-layer-expert | Entry gate |
| SICS-002 | Compatibility Projection Rules | Define the exact contract that maps canonical transcript rows back into existing session detail DTOs so current APIs stay stable during migration. | Session detail and transcript APIs can be served from canonical rows without consumer-visible regressions or silent field loss. | 3 pts | python-backend-engineer | SICS-001 |
| SICS-003 | Ingest Provenance Standardization | Normalize how Claude Code, Codex, and future platform parsers populate provenance, message role/type, tool metadata, and lineage fields before transcript persistence. | Transcript rows produced by supported platforms share a consistent provenance and message-shape contract. | 4 pts | python-backend-engineer, data-layer-expert | SICS-001 |

**Phase 1 Quality Gates**

1. Transcript identity and lineage semantics are explicit and testable.
2. Canonical transcript rows are sufficient to power current read models.
3. No router or UI path depends on undocumented legacy log quirks.

### Phase 1 Execution Notes

1. Canonical role, provenance, identity, and compatibility semantics are codified in `backend/services/session_transcript_contract.py`.
2. Canonical projection now normalizes platform provenance and role semantics before persistence without mutating parser-owned metadata.
3. Session transcript reads preserve the legacy API speaker contract (`assistant` canonical rows project back to `agent`).
4. The canonical transcript contract is documented in `docs/guides/session-transcript-contract-guide.md` and backed by focused regression tests.

## Phase 2: Enterprise Transcript Canonicalization And Embeddings Substrate

**Assigned Subagent(s)**: data-layer-expert, backend-architect, python-backend-engineer

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---|---|---|---|---:|---|---|
| SICS-101 | Enterprise Canonical Write Path | Update enterprise ingest so Postgres `session_messages` is treated as the authoritative transcript target rather than a mirrored compatibility store. | Enterprise sync and transcript reads no longer depend on legacy `session_logs` as the primary source for supported session types. | 4 pts | data-layer-expert, python-backend-engineer | SICS-003 |
| SICS-102 | Transcript Block Strategy | Define a mixed embedding strategy with per-message canonical blocks plus windowed recall blocks, including dedupe and refresh rules. | The plan identifies stable embedding units, content-addressed dedupe, and a refresh/reindex rule that supports search quality and manageable cost. | 3 pts | backend-architect, data-layer-expert | SICS-001 |
| SICS-103 | `pgvector` And Embedding Storage | Add enterprise-only migration support for `pgvector`, `session_embeddings`, and related indexes/capability checks while keeping local mode unaffected. | Enterprise Postgres can store and query embeddings; local SQLite remains supported without extension requirements. | 5 pts | data-layer-expert | SICS-101, SICS-102 |

**Phase 2 Quality Gates**

1. Enterprise transcript writes are canonical and backfillable.
2. Embedding storage is additive, enterprise-scoped, content-addressed, and health-checkable.
3. Local mode still runs without enterprise-only extension requirements.

### Phase 2 Execution Notes

1. The embedding unit is a mixed block model built from canonical `session_messages` rows:
   - per-message blocks for every substantive canonical row, including user prompts, assistant replies, and tool-bearing turns;
   - 5-row sliding window blocks for local transcript context and recall around decisions, corrections, and tool usage.
2. Block identity is content-addressed. Each stored embedding is keyed by the session, block kind, ordered canonical row membership, normalized content, provenance, role, and message identity so identical inputs collapse to one row.
3. Dedupe is deterministic. If a block hash already exists for the same session and block kind, the embedding row is skipped; a changed canonical input produces a new hash instead of mutating the previous one.
4. Refresh and reindex are additive. When a canonical message changes, every direct message block is recomputed and every overlapping window block is regenerated with a new hash; stale hashes can be superseded without rewriting unrelated rows.
5. The substrate stays enterprise-only. Local SQLite continues to read canonical transcript rows without requiring `pgvector`, and embedding materialization remains disabled outside the enterprise Postgres path.

## Phase 3: Intelligence Fact Pipelines

**Assigned Subagent(s)**: data-layer-expert, backend-architect, analytics-engineer

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---|---|---|---|---:|---|---|
| SICS-201 | DX Sentiment Fact Model | Define and implement a lightweight sentiment-scoring pipeline for user-authored transcript segments plus confidence and provenance metadata. | Session and feature-level DX sentiment can be computed reproducibly with traceable source messages and bounded heuristics. | 4 pts | analytics-engineer, data-layer-expert | SICS-101 |
| SICS-202 | Churn-To-Progress Fact Model | Derive repeated-edit and churn signals by combining transcript turn order with `session_file_updates`, diff evidence, and repeated rewrite patterns. | Churn metrics identify repeated low-progress edit loops without double counting ordinary iterative edits. | 4 pts | analytics-engineer, data-layer-expert | SICS-101 |
| SICS-203 | Scope-Drift Fact Model | Compare planned blast radius from linked plan documents against actual session file/resource activity to compute scope-adherence metrics. | Scope-drift facts are queryable per session and feature, with explainable evidence for flagged deviations. | 4 pts | backend-architect, analytics-engineer | SICS-101 |

**Phase 3 Quality Gates**

1. Every intelligence score has traceable source evidence.
2. Fact generation is idempotent and backfillable.
3. Metrics distinguish supported heuristics from operator-facing truth claims.

## Phase 4: Query Services And API Surfaces

**Assigned Subagent(s)**: python-backend-engineer, backend-architect, frontend-developer

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---|---|---|---|---:|---|---|
| SICS-301 | Semantic Search Service | Build a backend service that resolves query embeddings, rank/filters transcript matches, and returns explainable search results scoped by project, feature, and session family. | Enterprise transcript search returns relevant transcript matches with stable latency targets and project-safe scoping. | 4 pts | python-backend-engineer, backend-architect | SICS-103 |
| SICS-302 | Intelligence Summary APIs | Add additive API surfaces for DX sentiment, churn, and scope drift, including list, detail, and drilldown payloads. | APIs return versioned, typed read models without forcing routers to compose raw SQL or ad hoc joins. | 3 pts | python-backend-engineer | SICS-201, SICS-202, SICS-203 |
| SICS-303 | Compatibility Read Path Cutover | Move eligible transcript and analytics read paths to the new services while preserving current payload compatibility for existing consumers. | Session detail, analytics, and supporting UI requests can read from canonical services with controlled fallback behavior. | 3 pts | python-backend-engineer, frontend-developer | SICS-301, SICS-302 |

**Phase 4 Quality Gates**

1. Search and intelligence APIs are additive and typed.
2. Compatibility fallback remains bounded and observable.
3. Router code stays thin and service-driven.

## Phase 5: UI And Workflow Surfaces

**Assigned Subagent(s)**: frontend-developer, ui-engineer-enhanced

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---|---|---|---|---:|---|---|
| SICS-401 | Session Intelligence Surface | Add Session Inspector support for transcript search hits, DX sentiment state, churn flags, and scope-drift evidence. | Operators can inspect why a session was flagged without leaving the session workflow. | 3 pts | frontend-developer | SICS-302, SICS-303 |
| SICS-402 | Feature And Workflow Rollups | Extend feature/execution surfaces to show aggregated sentiment, churn, and drift indicators at the feature or workflow level. | Feature and workflow views expose intelligence summaries without reimplementing backend logic in the client. | 3 pts | frontend-developer, ui-engineer-enhanced | SICS-302 |
| SICS-403 | Operator Messaging And States | Add profile-aware empty/loading/error states that distinguish unsupported local-mode capabilities from enterprise failures. | UI makes storage-profile limitations explicit instead of implying missing data is an error. | 2 pts | ui-engineer-enhanced | SICS-303 |

**Phase 5 Quality Gates**

1. UI distinguishes unsupported capability from failed capability.
2. Intelligence surfaces provide evidence, not just scores.
3. Existing session workflows remain usable when enterprise-only features are absent.

## Phase 6: SkillMeat Memory Draft Loop

**Assigned Subagent(s)**: backend-architect, python-backend-engineer, frontend-developer

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---|---|---|---|---:|---|---|
| SICS-501 | Memory Draft Candidate Model | Define the CCDash-side draft record, extraction evidence, review status, and linkage back to sessions/features/workflows. | Memory candidates are persisted as reviewable CCDash artifacts with traceable source evidence. | 3 pts | backend-architect, python-backend-engineer | SICS-201, SICS-202, SICS-203 |
| SICS-502 | Draft Extraction Worker | Build the worker logic that selects successful sessions and drafts candidate SkillMeat context modules or guideline snippets. | Candidate generation is deterministic enough to review, rate-limit, and retry without duplicate spam. | 3 pts | python-backend-engineer | SICS-501 |
| SICS-503 | Approval-Gated Publish Flow | Add operator review and approval before calling the SkillMeat write API for accepted draft artifacts. | No draft is published automatically; approved drafts can be pushed with auditability and error handling. | 2 pts | frontend-developer, python-backend-engineer | SICS-502 |

**Phase 6 Quality Gates**

1. Memory drafts are reviewable before publish.
2. SkillMeat integration remains opt-in and auditable.
3. Failed publish attempts do not corrupt transcript or intelligence state.

## Phase 7: Backfill, Validation, And Rollout

**Assigned Subagent(s)**: data-layer-expert, python-backend-engineer, qa-engineer, documentation-writer

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---|---|---|---|---:|---|---|
| SICS-601 | Historical Backfill Plan | Build the job strategy and operator runbook for backfilling canonical transcript rows, embeddings, and derived facts from existing enterprise session history. | Historical enterprise sessions can be backfilled incrementally with restart-safe checkpoints and clear operator guidance. | 3 pts | data-layer-expert | SICS-103, SICS-203 |
| SICS-602 | Storage-Profile Validation Matrix | Extend tests and health reporting to cover local SQLite, dedicated Postgres enterprise, and shared-instance enterprise capability differences. | Supported profile differences are explicit, tested, and reflected in runtime health/status output. | 4 pts | qa-engineer, python-backend-engineer | SICS-303 |
| SICS-603 | Docs, Rollout, And Guardrails | Update operator and developer docs for canonical transcript behavior, search/analytics capabilities, backfill, and SkillMeat approval flow. | Rollout is documented with feature flags, prerequisites, failure modes, and rollback guidance. | 3 pts | documentation-writer | SICS-601, SICS-602 |

**Phase 7 Quality Gates**

1. Enterprise backfill is resumable and observable.
2. Supported capability differences by storage profile are documented and tested.
3. Rollout can be staged without breaking local-first usage.

## Verification Plan

Required validation before rollout:

1. Migration tests for SQLite and Postgres transcript tables, plus enterprise-only `pgvector` capability checks.
2. Repository tests for canonical transcript writes, reads, backfills, and compatibility projection behavior.
3. Sync-engine tests proving supported platforms populate transcript provenance and lineage correctly.
4. Fact-pipeline tests for sentiment, churn, and scope-drift derivation with fixture-backed evidence.
5. API tests for semantic search, analytics summaries, and compatibility fallbacks.
6. UI tests for enterprise-enabled and local-only capability states.
7. Worker tests for memory-draft extraction, approval gating, and publish retries.

## Risks And Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Transcript contract drifts between ingest paths | Metrics and search quality become inconsistent | Freeze provenance and identity rules in Phase 1 and back them with fixtures |
| `pgvector` rollout complicates enterprise setup | Hosted deployments fail or become hard to debug | Keep extension capability checks explicit and document unsupported environments clearly |
| Sentiment or churn heuristics overclaim precision | Operators lose trust in the metrics | Store evidence and confidence, label heuristics clearly, and avoid opaque score-only UX |
| Scope-drift joins become expensive | Analytics endpoints degrade | Precompute fact tables and use bounded drilldown queries instead of request-time recomputation |
| SkillMeat auto-write creates noisy or unsafe artifacts | External artifact registry quality drops | Keep publish approval mandatory and rate-limit draft generation |
| Local mode regresses because enterprise logic leaks inward | Local-first experience degrades | Preserve profile-aware capability gating and keep enterprise-only tables/extensions optional |

## Follow-On Notes

This plan should hand off cleanly into later work, not reopen earlier storage decisions.

Expected follow-ons after completion:

1. richer thread-family semantic search and rollups,
2. improved approval and review UX for SkillMeat draft publishing,
3. enterprise auth-aware visibility controls on intelligence surfaces,
4. and possible future splitting of operational intelligence facts into a more formal analytics boundary if scale requires it.

## Success Criteria

This plan is complete when:

1. enterprise Postgres acts as the canonical transcript intelligence source for supported session types,
2. local SQLite remains a supported cache-oriented mode without enterprise-only runtime requirements,
3. semantic search, DX sentiment, churn, and scope-drift surfaces are queryable through stable backend services,
4. current transcript/session detail consumers continue to function during and after the cutover,
5. and SkillMeat memory generation is available only through a reviewable, approval-gated draft flow.
