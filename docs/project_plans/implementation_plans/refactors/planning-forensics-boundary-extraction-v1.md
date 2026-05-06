---
schema_name: ccdash_document
schema_version: 3
doc_type: implementation_plan
doc_subtype: implementation_plan
primary_doc_role: supporting_document
status: draft
category: refactors
title: "Implementation Plan: Planning / Forensics Boundary Extraction V1"
description: "Phased implementation plan for separating planning and execution workflows from session forensics and metrics through bounded shared evidence contracts."
summary: "Add a shared FeatureEvidenceSummary contract, migrate planning away from full forensic DTOs, extract session-feature correlation, split frontend feature-detail ownership, and preserve canonical ingest/read compatibility."
author: codex
created: 2026-05-06
updated: 2026-05-06
priority: high
risk_level: high
complexity: high
track: Planning / Forensics / Architecture
timeline_estimate: "2-4 engineering weeks across 6 phases"
feature_slug: planning-forensics-boundary-extraction-v1
feature_family: planning-forensics-boundary-extraction
feature_version: v1
lineage_family: planning-forensics-boundary-extraction
lineage_parent:
  ref: docs/project_plans/PRDs/refactors/planning-forensics-boundary-extraction-v1.md
  kind: implementation_of
lineage_children: []
lineage_type: refactor
prd: docs/project_plans/PRDs/refactors/planning-forensics-boundary-extraction-v1.md
prd_ref: docs/project_plans/PRDs/refactors/planning-forensics-boundary-extraction-v1.md
plan_ref: planning-forensics-boundary-extraction-v1
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
  - implementation
  - refactor
  - planning
  - execution
  - forensics
  - sessions
  - metrics
  - api-contracts
related_documents:
  - docs/project_plans/reports/planning-forensics-split-refactor-assessment-2026-05-06.md
  - docs/project_plans/PRDs/refactors/planning-forensics-boundary-extraction-v1.md
context_files:
  - backend/application/services/agent_queries/planning.py
  - backend/application/services/agent_queries/feature_forensics.py
  - backend/application/services/agent_queries/planning_sessions.py
  - backend/application/services/agent_queries/workflow_intelligence.py
  - backend/routers/agent.py
  - backend/routers/client_v1.py
  - backend/routers/_client_v1_features.py
  - backend/application/services/feature_surface/list_rollup_service.py
  - backend/application/services/feature_surface/modal_service.py
  - backend/application/services/feature_surface/dtos.py
  - backend/ingestion/session_ingest_service.py
  - backend/cli/feature_commands.py
  - backend/mcp/server.py
  - components/ProjectBoard.tsx
  - services/useFeatureModalData.ts
  - components/FeatureModal/TabStateView.tsx
  - components/shared/PlanningMetadata.tsx
  - services/featureSurface.ts
  - services/featureSurfaceCache.ts
  - services/featureCacheBus.ts
---

# Implementation Plan: Planning / Forensics Boundary Extraction

**Plan ID:** `IMPL-2026-05-06-PLANNING-FORENSICS-BOUNDARY-EXTRACTION`
**Date:** 2026-05-06
**Author:** Codex (revised by Claude Opus 4.7 after senior review on 2026-05-06)
**Complexity:** L
**Total Estimated Effort:** 63 points
**Target Timeline:** 2-4 engineering weeks, depending on frontend extraction depth and available test fixtures

## Revision Notes (2026-05-06)

This plan was revised post-review. Material changes:

- Added `_client_v1_features.py` and the `feature_surface` package as named seams (parallel forensics consumers the original draft missed).
- Phase 0 now requires a written inventory artifact, not a verbal call-site list.
- Phase 1 must explicitly decide MCP/CLI transport wiring (in-scope or deferred with rationale).
- Phase 2 ACs now name the import-time singleton coupling in `planning.py` (module-level construction at import) and its test-isolation implications.
- Phase 3 names both correlation sources (`planning.py` and `planning_sessions.py`) and is gated on Phase 1 contract stability.
- Phase 4 is rescoped from 12 → 20 pts and explicitly names `useFeatureModalData.ts`, `featureCacheBus.ts`, `featureSurfaceCache.ts`, `TabStateView.tsx`. Adds an @miethe/ui shell-extraction decision point.
- New risk rows: `_client_v1_features.py` / CLI v1 contract, cache invalidation bus, import-time singleton.
- Per-phase model + thinking-effort guidance added (see Models & Thinking Effort).

## Executive Summary

This plan separates planning/execution workflows from session forensics/metrics by adding a bounded shared evidence contract, migrating planning reads away from full forensic DTOs, extracting reusable session-feature correlation, and splitting frontend feature-detail ownership by product domain.

The refactor is intentionally not a storage split. The shared substrate remains canonical for plan docs, feature/document/session links, normalized session ingestion, cache/provenance, and live invalidation.

## Architecture Diagrams

![CCDash split refactor shared evidence substrate](../../assets/planning-forensics-boundary-extraction-v1/shared-evidence-substrate.png)

![CCDash split refactor UI and agent flow](../../assets/planning-forensics-boundary-extraction-v1/ui-agent-flow.png)

## Architecture Direction

### Target Ownership

| Module | Owns |
| --- | --- |
| Planning | Plan docs, planning graph, raw/effective status, phases, tasks, batch/run-prep context, mismatch/provenance |
| Execution | Runs, approvals, provider/worktree context, policy, retries, run events |
| Session Forensics | Transcripts, session messages, source provenance, usage/cost, telemetry, intelligence facts, forensic detail |
| Workflow Intelligence | Workflow effectiveness, diagnostics, workflow mix, rework/failure signals |
| Shared Evidence | Feature/document/session links, bounded summaries, freshness/confidence, source refs, cache/live invalidation helpers |

### New Read Contract

Add `FeatureEvidenceSummary` as a transport-neutral service/DTO and expose it additively.

Required fields:

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

The summary must not fetch transcript logs by default. Full transcript and forensic enrichment remain behind feature-forensics/session-forensics surfaces.

## Phase Overview

| Phase | Title | Effort | Primary Owner |
| --- | --- | --- | --- |
| 0 | Contract Inventory And Guardrails | 5 pts | architecture/documentation worker |
| 1 | Shared Evidence Summary Service | 10 pts | backend boundary worker |
| 2 | Planning Query Migration | 9 pts | planning backend worker |
| 3 | Session-Feature Correlation Extraction | 9 pts | backend correlation worker |
| 4 | Frontend Feature Detail Boundary | 20 pts | frontend surface worker |
| 5 | Workflow Intelligence Ownership Cleanup | 4 pts | workflow/frontend worker |
| 6 | Validation, Compatibility, Docs Closeout | 6 pts | validation worker |

## Models & Thinking Effort

Per-phase guidance for delegation. Available models: **Opus 4.7** (orchestration / deep reasoning), **Sonnet 4.6** (default subagent implementation), **Haiku 4.5** (mechanical/extraction work), **Codex 5.5** (GPT-5.3-Codex via the `codex` skill — second-opinion review and large-surface refactor cross-validation). Thinking effort is one of `low | medium | high | xhigh | max`.

| Phase | Recommended Model | Thinking Effort | Cross-Check | Rationale |
| --- | --- | --- | --- | --- |
| 0 | Haiku 4.5 | low | — | Mechanical grep / inventory; output is a filed artifact, not synthesis. |
| 1 | Sonnet 4.6 | high | Codex 5.5 review of DTO + route shape before Phase 2 begins | **Most critical phase** — contract locks every downstream phase. Worth a second opinion. |
| 2 | Sonnet 4.6 | high | — | Import-time singleton coupling and test-isolation work make this subtler than a call-site swap. |
| 3 | Sonnet 4.6 | high | — | **Load-bearing** — must reconcile two existing correlation implementations without behavior drift. |
| 4 | Sonnet 4.6 (with Opus 4.7 plan-time review) | xhigh | Codex 5.5 cross-validation on tab ownership split + cache-bus reorg before implementation | **Most complex phase, most hidden surface area.** Opus reviews the split design; Codex 5.5 cross-checks; Sonnet executes. |
| 5 | Haiku 4.5 | low | — | Pure FE module move; Sonnet spot-check at end. |
| 6 | Sonnet 4.6 | medium | — | Validation + docs; standard. |

**Orchestration note:** Opus 4.7 only orchestrates. Do not raise subagent thinking effort to `max` without a recorded reason — the sweet spot for this plan's complexity is `high`/`xhigh`. Codex 5.5 cross-checks are opt-in, not gates; record the second-opinion output in `.claude/worknotes/planning-forensics-boundary-extraction-v1/` if invoked.

## Phase 0: Contract Inventory And Guardrails

**Goal:** Lock the exact consumers and fields before code moves.

**Tasks:**

| ID | Task | Acceptance Criteria | Assigned Subagent(s) |
| --- | --- | --- | --- |
| P0-001 | Inventory planning consumers of forensics/token/session evidence | **Artifact:** `.claude/worknotes/planning-forensics-boundary-extraction-v1/forensics-consumers-inventory.md` exists and lists every import + call site of `FeatureForensicsQueryService` across the repo. Must include: `backend/application/services/agent_queries/planning.py` (note module-level singleton at import time), `backend/routers/_client_v1_features.py`, `backend/routers/agent.py`, `backend/application/services/feature_surface/*`, `backend/cli/commands/feature.py`, `backend/mcp/server.py`. Each entry records file, line range, and whether the consumer needs full forensics or only the bounded summary. | backend-architect, documentation-writer |
| P0-002 | Inventory feature/session frontend consumers | **Artifact:** filed list under same worknotes folder. Must name `services/useFeatureModalData.ts` (the 7-section hook with internal LRU), `components/FeatureModal/TabStateView.tsx`, `services/featureSurface.ts`, `services/featureSurfaceCache.ts`, `services/featureCacheBus.ts`, and `components/ProjectBoard.tsx`. For each, record which sections need summary versus full forensics. | frontend-developer, ui-engineer-enhanced |
| P0-003 | Define compatibility fields | Existing planning DTO fields that must remain stable are documented, including the v1 client surface fields exposed via `_client_v1_features.py` and `feature_surface/dtos.py`. | backend-architect |
| P0-004 | Decide MCP/CLI transport scope | Explicit decision recorded: whether the new `FeatureEvidenceSummary` surface is wired through `backend/mcp/server.py` and `backend/cli/commands/feature.py` in this plan, or deferred — with rationale and a follow-up issue link if deferred. | backend-architect |
| P0-005 | Add guardrail notes | Note that no database split, service fork, or OTel merge-policy implementation is in this refactor. | documentation-writer |

**Quality Gate:** Implementation cannot start until (a) the two inventory artifacts are filed, (b) compatibility fields are fixed, and (c) the MCP/CLI scope decision is recorded. A verbal call-site list is not sufficient — the artifact must exist on disk.

## Phase 1: Shared Evidence Summary Service

**Goal:** Add a bounded backend evidence-summary contract.

**Tasks:**

| ID | Task | Acceptance Criteria | Assigned Subagent(s) |
| --- | --- | --- | --- |
| P1-001 | Add DTO/model types for `FeatureEvidenceSummary` | DTO includes required fields and source/freshness metadata | python-backend-engineer |
| P1-002 | Add transport-neutral query/service | Service aggregates session counts, token totals, workflow mix, latest activity, confidence, and source refs without transcript-log enrichment | backend-architect |
| P1-003 | Add additive route exposure | Agent/client route returns the summary without changing existing planning or forensics endpoints. If P0-004 marked MCP/CLI as in-scope, this task includes wiring `backend/mcp/server.py` and `backend/cli/commands/feature.py` to the new service. | python-backend-engineer |
| P1-004 | Add cache/invalidation policy | Cache key and invalidation topics are documented and covered by tests where practical | backend-architect |
| P1-005 | Stabilize contract before downstream phases | DTO field set and route shape are frozen and recorded in worknotes. Phase 3 may not begin until this task is marked complete. | backend-architect |

**Quality Gate:** Summary service works for linked sessions, empty evidence, partial/missing telemetry, and stale data without calling transcript enrichment. Contract is frozen and recorded — Phases 2 and 3 depend on this.

## Phase 2: Planning Query Migration

**Goal:** Planning consumes bounded evidence rather than full feature forensics.

**Tasks:**

| ID | Task | Acceptance Criteria | Assigned Subagent(s) |
| --- | --- | --- | --- |
| P2-001 | Replace direct forensics dependency in planning query service | Planning feature context no longer imports or calls full `FeatureForensicsQueryService` for token evidence. **Note:** the coupling in `backend/application/services/agent_queries/planning.py` is import-time (module-level `_feature_forensics_query_service` singleton constructed at import). Removing it must preserve test isolation — verify by running affected tests with `pytest -p no:randomly` and with random ordering. | python-backend-engineer |
| P2-002 | Migrate `_client_v1_features.py` consumer | The v1 feature detail route (`backend/routers/_client_v1_features.py`, including its `FeatureForensicsQueryService` import) is updated to consume the bounded summary for fields that don't require full forensics. CLI v1 contract (`/api/v1/features/*`) response shape remains stable — this is a CLI breaking-change risk. | python-backend-engineer |
| P2-003 | Preserve response compatibility | Existing planning token telemetry, total token, and token usage fields remain present | python-backend-engineer |
| P2-004 | Add compatibility tests | Tests compare old expected planning token/session fields against new summary-backed output. Include CLI v1 feature detail contract tests. | testing-specialist |
| P2-005 | Review next-run preview context selection | Selected explicit sessions still resolve correctly; richer forensic context is only loaded when explicitly requested | backend-architect |

**Quality Gate:** Existing planning APIs and `/api/v1/features/*` pass compatibility tests, planning no longer depends on transcript-heavy forensic detail for summary evidence, and import-time singleton coupling in `planning.py` is removed without breaking test isolation.

## Phase 3: Session-Feature Correlation Extraction

**Goal:** Move reusable correlation logic behind a shared boundary.

**Tasks:**

| ID | Task | Acceptance Criteria | Assigned Subagent(s) |
| --- | --- | --- | --- |
**Dependency:** Phase 1 (P1-005 contract freeze) must be marked complete before Phase 3 starts.

| ID | Task | Acceptance Criteria | Assigned Subagent(s) |
| --- | --- | --- | --- |
| P3-001 | Extract shared correlation helper/query | Explicit links, phase hints, task hints, command tokens, and lineage behavior are preserved. **Both source implementations must be reconciled:** the feature-slug token matching in `backend/application/services/agent_queries/planning_sessions.py` (`_feature_slug_tokens`, `_extract_phase_hints`, `_extract_task_hints`, `_extract_tool_summary`) and the session-loading correlation path in `backend/application/services/agent_queries/planning.py`. | backend-architect |
| P3-002 | Migrate planning session board to shared correlation | Board output remains compatible for project-wide and feature-scoped views | python-backend-engineer |
| P3-003 | Make evidence summary use shared correlation where needed | Summary and board do not duplicate correlation heuristics | python-backend-engineer |
| P3-004 | Add regression fixtures | Tests cover explicit links, inferred links, subagent sessions, missing feature links, and ambiguous hints. Fixtures must exercise both prior implementations' edge cases before consolidation. | testing-specialist |

**Quality Gate:** Old and new correlation outputs match on fixtures from both prior implementations. No projection table is added in this phase.

## Phase 4: Frontend Feature Detail Boundary

**Goal:** Separate planning, forensics, and execution UI ownership inside feature detail surfaces while preserving cache invalidation correctness.

**Named files in scope:**

- `services/useFeatureModalData.ts` — the 7-section modal data hook with internal LRU; tab ownership split must work through this file.
- `components/FeatureModal/TabStateView.tsx` — the per-tab idle/loading/error/stale/success renderer.
- `components/ProjectBoard.tsx` — the modal entry point and current cache-bus subscriber.
- `services/featureSurface.ts` + `services/featureSurfaceCache.ts` + `services/featureCacheBus.ts` — the cache + invalidation bus that fires across both feature-surface and planning caches.
- `services/featureCardAdapters.ts` — adapter layer between feature DTOs and card UI.

**Tasks:**

| ID | Task | Acceptance Criteria | Assigned Subagent(s) |
| --- | --- | --- | --- |
| P4-001 | Extract reusable feature-detail shell/data boundary | Shell owns tab frame, loading, retry, and section boundaries without owning product-specific tab internals. **Decision required:** record in worknotes whether the extracted shell (mirroring `TabStateView`'s idle/loading/error/stale/success states) is promoted to `@miethe/ui/primitives` (alongside `BaseArtifactModal`, `VerticalTabNavigation`, `Tabs`) or kept CCDash-local. Document rationale either way. | frontend-developer, ui-engineer-enhanced |
| P4-002 | Split `useFeatureModalData` ownership | The hook's 7 sections are partitioned by domain (planning vs forensics vs shared). Planning-owned sections are moved to a planning-module hook (composed by the shell); forensics-owned sections move to a forensics-module hook. The internal LRU cache is preserved or replaced with an equivalent. | frontend-developer |
| P4-003 | Preserve cache invalidation across the split | `featureCacheBus` events still invalidate both planning and feature-surface caches after the module split. Add tests proving a single mutation event fires through both caches. Subscriber location may move from `ProjectBoard.tsx` but bus semantics must not change. | frontend-developer, ui-engineer-enhanced |
| P4-004 | Move planning-native tabs/actions into planning module | Planning drawer/modal renders planning phases, tasks, docs, status provenance, and next-run controls from planning-owned components. Re-uses the shared planning metadata primitives already in `@miethe/ui` (`StatusChip`, `EffectiveStatusChips`, `BatchReadinessPill`, `MismatchBadge`, `PlanningNodeTypeIcon`). | frontend-developer |
| P4-005 | Move session evidence tabs into forensics/session module | Linked sessions, transcript evidence, usage, and forensic detail load only in forensics-owned tabs. | frontend-developer |
| P4-006 | Preserve lazy loading and encoded IDs | Tests prove no eager linked-session detail loading and path parameters are encoded. Existing `FeatureModalLazyTabs.test.tsx` and `FeatureModalEncodedIds.test.tsx` continue to pass without modification. | ui-engineer-enhanced |
| P4-007 | Retire legacy detail fetch only after equivalent v1 sections exist | `getLegacyFeatureDetail` removal is gated by feature parity and tests. | frontend-developer |

**Quality Gate:** Modal/drawer behavior remains functionally equivalent; planning and forensics tabs owned by separate modules; no eager linked-session regression; cache-bus invalidation continues to fire across both caches; @miethe/ui shell-extraction decision is recorded.

## Phase 5: Workflow Intelligence Ownership Cleanup

**Goal:** Make workflow diagnostics/effectiveness a product module rather than generic Analytics ownership.

**Tasks:**

| ID | Task | Acceptance Criteria | Assigned Subagent(s) |
| --- | --- | --- | --- |
| P5-001 | Identify current workflow diagnostics UI/routes | Existing entrypoints and Analytics dependencies are documented | frontend-developer |
| P5-002 | Move ownership to workflow-intelligence module | Workflow diagnostics/effectiveness components and hooks live under a workflow-owned boundary | frontend-developer |
| P5-003 | Preserve Analytics discoverability | Analytics links or embeds still navigate users to workflow diagnostics | ui-engineer-enhanced |

**Quality Gate:** Workflow diagnostics still render and Analytics no longer owns workflow-specific behavior.

## Phase 6: Validation, Compatibility, Docs Closeout

**Goal:** Prove behavior stability and close the planning artifacts.

**Tasks:**

| ID | Task | Acceptance Criteria | Assigned Subagent(s) |
| --- | --- | --- | --- |
| P6-001 | Run backend focused tests | Agent query, planning, feature surface, ingestion boundary, and correlation tests pass | testing-specialist |
| P6-002 | Run frontend focused tests | Modal/drawer lazy loading, encoded IDs, session detail, and workflow routing tests pass | frontend-developer |
| P6-003 | Run typecheck/build where available | Frontend build/typecheck and backend compile checks pass or environment caveats are documented | testing-specialist |
| P6-004 | Update docs and status | PRD/implementation plan status and any progress file created for implementation are updated accurately | documentation-writer |

**Quality Gate:** Validation output includes exact commands, pass counts, and any environment caveats. Broad Python collection segfaults, if still present, are recorded as environment caveats rather than regressions.

## Public Interfaces And Compatibility

Additive interfaces:

- A new backend `FeatureEvidenceSummary` DTO/model.
- A new transport-neutral query/service for evidence summaries.
- A new route for evidence summaries, preferably under the agent query surface first.
- Shared correlation helper/query callable by planning session board and evidence summary.

Compatibility requirements:

- Existing `/api/agent/planning/*` response fields remain stable.
- Existing `/api/agent/feature-forensics/{feature_id}` continues to return full forensic detail.
- Existing feature-surface v1 contracts remain available during frontend migration.
- No existing ingest adapter or JSONL persistence behavior changes.

## Validation Plan

Backend focused suites:

- Evidence summary aggregation, empty-state, partial telemetry, stale/fresh confidence, and no transcript enrichment.
- Planning query compatibility for summary/context token fields.
- Planning session board and shared correlation fixtures.
- Feature-forensics route compatibility.
- Ingestion boundary tests proving JSONL complete upsert behavior is unchanged.

Frontend focused suites:

- Planning feature detail modal/drawer lazy tab behavior.
- No eager linked-session detail loading on board/modal open.
- Encoded feature IDs across detail and write paths touched by the refactor.
- Session/forensics tabs still render linked sessions and transcript evidence.
- Workflow diagnostics route/module remains reachable from Analytics.

Commands should be chosen from existing package scripts and focused pytest targets. Avoid a broad Python 3.12 collection run if it still triggers the known runtime-bootstrap segfault.

## Rollout Strategy

1. Land backend evidence summary additively.
2. Migrate planning reads while preserving response fields.
3. Extract correlation and validate against fixtures.
4. Migrate frontend shell/tabs behind existing route behavior.
5. Move workflow diagnostics ownership.
6. Remove legacy frontend fetches only after equivalent v1 section APIs and tests exist.
7. Defer OTel partial metrics/event merge semantics to a later plan.

## Risk Mitigation

| Risk | Mitigation |
| --- | --- |
| Summary contract grows too large | Keep the DTO bounded and explicitly exclude transcript logs. |
| Planning consumers regress | Preserve response fields and add compatibility tests before deleting old code. |
| Correlation output changes | Compare old/new fixtures from both prior implementations before switching consumers. |
| Frontend lazy loading regresses | Add request-count tests and tab-level loading/error tests. |
| Workflow move hides diagnostics | Keep Analytics navigation to the workflow-intelligence surface. |
| OTel partial merge becomes entangled | Keep merge-policy support deferred and documented as out of scope. |
| `_client_v1_features.py` / CLI v1 contract drift | Treat `/api/v1/features/*` as a CLI breaking-change surface; add explicit contract tests in P2-004; do not change response shape during migration. |
| Cache invalidation bus desync after FE split | P4-003 requires explicit tests that one mutation event fires through both planning and feature-surface caches; subscriber move is allowed, semantics are not. |
| Import-time singleton coupling in `planning.py` | P2-001 ACs require running tests under both fixed and randomized order; module-level singleton removal must not change import-order behavior. |
| @miethe/ui extraction churn | P4-001 requires a recorded decision (extract vs keep local) with rationale; do not extract speculatively without consumer demand. |

## Assumptions

- This plan does not create a progress tracker until implementation begins.
- The first implementation branch should use task- or phase-scoped commits.
- Subagents should be delegated bounded backend, frontend, and validation slices.
- `entity_links` remains the v1 bridge contract.
- No new database tables are added unless later profiling proves the shared correlation query needs a projection table.
- Markdown/frontmatter artifacts remain canonical for planning.
- `backend/ingestion/SessionIngestService` remains the canonical session persistence path.
