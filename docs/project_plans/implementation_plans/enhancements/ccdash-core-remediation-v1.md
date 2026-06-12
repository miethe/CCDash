---
title: CCDash Core Remediation v1 - Implementation Plan
schema_version: 2
doc_type: implementation_plan
status: completed
created: '2026-06-10'
updated: '2026-06-12'
feature_slug: ccdash-core-remediation
feature_version: v1
prd_ref: /Users/miethe/dev/homelab/development/CCDash/docs/project_plans/PRDs/enhancements/ccdash-core-remediation-v1.md
plan_ref: null
scope: Restore cross-project session correctness and ship full session-detail egress (transcript/subagent/workflow)
  via REST/MCP/CLI, with detection/pricing/sync/freshness hardening and Postgres-container readiness.
effort_estimate: ~67 pts (Tier 3) + ~18% hidden plumbing
architecture_summary: Phase 0 makes session reads project-safe; Phases 1-3 expose a transport-neutral
  session_detail service (reusing SessionTranscriptService) with redaction over REST/MCP/CLI; Phases 4-8
  harden link freshness, detection, pricing, and sync; Phase 9 is the Postgres/container convergence gate;
  Phases 10-11 add external API + launch-time capture; Phase 12 closes docs + karen.
related_documents:
- /Users/miethe/dev/homelab/development/CCDash/docs/project_plans/PRDs/enhancements/ccdash-core-remediation-v1.md
- /Users/miethe/dev/homelab/development/CCDash/.claude/worknotes/ccdash-core-remediation/decisions-block.md
- docs/project_plans/reports/investigations/ccdash-core-remediation-diagnostic-v1.md
references:
  user_docs: []
  context: []
  specs: []
  related_prds:
  - /Users/miethe/dev/homelab/development/CCDash/docs/project_plans/PRDs/enhancements/ccdash-core-remediation-v1.md
spike_ref: null
adr_refs:
- docs/project_plans/adrs/adr-007-db-write-failure-surfacing-standard.md
deferred_items_spec_refs:
- docs/guides/redaction-tuning.md
- docs/guides/feature-surface-architecture.md
- docs/guides/sync-coalescing-recent-first.md
- docs/guides/sync-coalescing-recent-first.md
- docs/guides/launch-time-capture-convention.md
- docs/guides/external-api-lan-deployment.md
findings_doc_ref: docs/project_plans/reports/investigations/ccdash-core-remediation-diagnostic-v1.md
charter_ref: null
changelog_ref: CHANGELOG.md
changelog_required: true
test_plan_ref: null
plan_structure: independent
progress_init: pre-created
owner: null
contributors: []
priority: high
risk_level: high
category: product-planning
tags:
- implementation
- planning
- phases
- tasks
- sessions
- cross-project
- postgres
- mcp
milestone: null
commit_refs:
- 0018978
- '5287235'
pr_refs: []
files_affected:
- backend/db/repositories/sessions.py
- backend/db/repositories/postgres/sessions.py
- backend/db/repositories/base.py
- backend/routers/_client_v1_sessions.py
- backend/routers/api.py
- backend/application/services/agent_queries/feature_evidence_summary.py
- backend/application/services/agent_queries/feature_forensics.py
- backend/application/services/agent_queries/planning.py
- backend/application/services/documents.py
- backend/application/services/session_intelligence.py
- backend/services/integrations/skillmeat_memory_drafts.py
- backend/application/services/agent_queries/session_detail.py
- backend/application/services/agent_queries/redaction.py
- backend/routers/client_v1.py
- backend/mcp/tools/sessions.py
- backend/mcp/tools/__init__.py
- backend/cli/commands/session.py
- backend/cli/main.py
- packages/ccdash_cli/src/ccdash_cli/commands/session.py
- packages/ccdash_contracts/src/ccdash_contracts/__init__.py
- packages/ccdash_contracts/src/ccdash_contracts/models.py
- backend/db/sync_engine.py
- backend/document_linking.py
- backend/parsers/workflow_sidecar.py
- backend/parsers/platforms/claude_code/parser.py
- backend/parsers/platforms/codex/parser.py
- backend/db/sqlite_migrations.py
- backend/db/postgres_migrations.py
- backend/db/migration_governance.py
- backend/models.py
- backend/project_manager.py
- components/Dashboard.tsx
- components/SessionInspector.tsx
- services/queries/dashboard.ts
- types.ts
- backend/routers/analytics.py
- backend/services/pricing_catalog.py
- backend/adapters/jobs/durable_queue.py
- backend/adapters/jobs/runtime.py
- backend/config.py
- backend/db/file_watcher.py
- backend/adapters/workspaces/local.py
- backend/db/repositories/postgres/analytics.py
- backend/db/repositories/postgres/job_queue.py
- backend/runtime/bootstrap.py
- docker-compose.yml
- deploy/runtime/Dockerfile
- scripts/compose_smoke.sh
- scripts/regen-openapi-v1.py
- backend/routers/_client_v1_auth.py
- docs/openapi/ccdash-v1.json
- docs/guides/external-api-lan-deployment.md
- examples/intenttree-client/README.md
- examples/intenttree-client/client.py
- examples/intenttree-client/test_client_dry.py
- backend/parsers/capture_sidecar.py
- scripts/hooks/ccdash_capture_session_start.py
- docs/guides/launch-time-capture-convention.md
- CHANGELOG.md
- CLAUDE.md
- docs/guides/feature-surface-architecture.md
- docs/guides/redaction-tuning.md
- docs/guides/sync-coalescing-recent-first.md
- backend/observability/otel.py
- .claude/findings/ccdash-core-remediation-findings.md
- .env.example
- docs/project_plans/adrs/adr-006-db-authoritative-project-registry.md
- docs/project_plans/adrs/adr-007-db-write-failure-surfacing-standard.md
wave_plan:
  serialization_barriers:
  - backend/runtime.py
  - backend/db/sync_engine.py
  - backend/config.py
  - CLAUDE.md
  - CHANGELOG.md
  - docs/guides/feature-surface-architecture.md
  phases:
  - id: P0
    depends_on: []
    isolation: shared
    parallelizable: false
    provider: claude
    profile: null
    owner_skills:
    - dev-execution
    - artifact-tracking
    files_affected:
    - backend/db/repositories/sessions.py
    - backend/db/repositories/postgres/sessions.py
    - backend/routers/_client_v1_sessions.py
  - id: P1
    depends_on:
    - P0
    isolation: shared
    parallelizable: true
    provider: claude
    profile: null
    owner_skills:
    - dev-execution
    - artifact-tracking
    files_affected:
    - backend/application/services/agent_queries/session_detail.py
    - backend/application/services/sessions.py
  - id: P4
    depends_on:
    - P0
    isolation: shared
    parallelizable: true
    provider: claude
    profile: null
    owner_skills:
    - dev-execution
    - artifact-tracking
    files_affected:
    - backend/db/sync_engine.py
    - backend/document_linking.py
  - id: P6
    depends_on:
    - P0
    isolation: shared
    parallelizable: true
    provider: claude
    profile: null
    owner_skills:
    - dev-execution
    - artifact-tracking
    files_affected:
    - backend/routers/analytics.py
    - backend/services/pricing_catalog.py
  - id: P7
    depends_on:
    - P0
    isolation: shared
    parallelizable: true
    provider: claude
    profile: null
    owner_skills:
    - dev-execution
    - artifact-tracking
    files_affected:
    - backend/runtime.py
    - backend/db/sync_engine.py
    - backend/config.py
  - id: P2
    depends_on:
    - P1
    isolation: shared
    parallelizable: true
    provider: claude
    profile: null
    owner_skills:
    - dev-execution
    - artifact-tracking
    files_affected:
    - backend/routers/client_v1.py
    - backend/routers/_client_v1_sessions.py
    - packages/ccdash_contracts/
  - id: P5
    depends_on:
    - P0
    isolation: shared
    parallelizable: true
    provider: claude
    profile: null
    owner_skills:
    - dev-execution
    - artifact-tracking
    files_affected:
    - backend/parsers/sessions.py
    - backend/db/sync_engine.py
    - backend/db/migrations.py
    - types.ts
  - id: P8
    depends_on:
    - P0
    isolation: shared
    parallelizable: true
    provider: claude
    profile: null
    owner_skills:
    - dev-execution
    - artifact-tracking
    files_affected:
    - backend/runtime.py
    - backend/db/file_watcher.py
    - backend/config.py
  - id: P3
    depends_on:
    - P2
    isolation: shared
    parallelizable: true
    provider: claude
    profile: null
    owner_skills:
    - dev-execution
    - artifact-tracking
    files_affected:
    - backend/mcp/tools/sessions.py
    - backend/cli/commands/session.py
    - packages/ccdash_cli/
  - id: P9
    depends_on:
    - P5
    - P6
    - P7
    isolation: shared
    parallelizable: true
    provider: claude
    profile: null
    owner_skills:
    - dev-execution
    - artifact-tracking
    files_affected:
    - backend/db/repositories/postgres/sessions.py
    - docker-compose.yml
    - backend/runtime/container.py
  - id: P10
    depends_on:
    - P2
    isolation: shared
    parallelizable: true
    provider: claude
    profile: null
    owner_skills:
    - dev-execution
    - artifact-tracking
    files_affected:
    - backend/routers/client_v1.py
    - openapi.json
  - id: P11
    depends_on:
    - P3
    isolation: shared
    parallelizable: true
    provider: claude
    profile: null
    owner_skills:
    - dev-execution
    - artifact-tracking
    files_affected:
    - backend/parsers/sessions.py
    - backend/db/migrations.py
    - types.ts
  - id: P12
    depends_on:
    - P4
    - P5
    - P9
    - P10
    - P11
    isolation: shared
    parallelizable: false
    provider: claude
    profile: null
    owner_skills:
    - dev-execution
    - artifact-tracking
    - changelog-sync
    files_affected:
    - CHANGELOG.md
    - CLAUDE.md
    - docs/guides/feature-surface-architecture.md
  waves:
  - - P0
  - - P1
    - P4
    - P6
    - P7
  - - P2
    - P5
    - P8
  - - P3
    - P9
    - P10
  - - P11
  - - P12
---

# Implementation Plan: CCDash Core Remediation v1

**Plan ID**: `IMPL-2026-06-10-CCDASH-CORE-REMEDIATION`
**Date**: 2026-06-10
**Author**: Implementation Planner Agent
**Human Brief**: N/A — scaffold authored as decisions block (`.claude/worknotes/ccdash-core-remediation/decisions-block.md`)
**Related Documents**:
- **PRD**: `/Users/miethe/dev/homelab/development/CCDash/docs/project_plans/PRDs/enhancements/ccdash-core-remediation-v1.md`
- **Diagnostic / findings**: `docs/project_plans/reports/investigations/ccdash-core-remediation-diagnostic-v1.md`
- **ADRs**: ADR-006 (DB-authoritative registry), ADR-007 (DB write-failure surfacing)

**Complexity**: XL
**Total Estimated Effort**: ~67 pts (+ ~18% hidden plumbing)
**Target Timeline**: One orchestrated effort, six waves (Phases 0–12)

## Executive Summary

CCDash was optimized for a single active project but is now asked to serve every project, every agent, and external consumers (IntentTree). This program restores the broken core workflows surfaced by the diagnostic and delivers the operator's top deliverable: **any agent can pull full session detail — transcript, subagents, workflow content, tokens, artifacts, links — for any session in any project via REST, MCP, and CLI, with secret/PII redaction**. It executes in 13 phases across six waves: Phase 0 makes session reads project-safe (hard prerequisite), Phases 1–3 expose a transport-neutral `session_detail` service over all three surfaces, Phases 4–8 harden link freshness, detection, pricing, and sync, Phase 9 is the Postgres/container convergence gate, Phases 10–11 add the external API and launch-time profile/effort capture, and Phase 12 closes docs + CHANGELOG + a karen end-of-feature pass.

## Implementation Strategy

### Architecture Sequence

The work follows the CCDash layered architecture (Router → Service → Repository) but sequences by **correctness dependency**, not by layer:

1. **Repository correctness (Phase 0)** — `project_id` enforcement on `get_by_id` / `get_many_by_ids` (SQLite + Postgres) and family anchor `project_id` propagation. Nothing cross-project ships until this is green.
2. **Service layer (Phase 1)** — `agent_queries/session_detail.py` reuses the existing transport-neutral `SessionTranscriptService.list_session_logs`; adds include-flags, cursor pagination, and the redaction layer.
3. **Transport surfaces (Phases 2–3)** — REST `/api/v1` detail/transcript endpoints, then MCP tools + repo-CLI `session` group, with a three-surface parity test.
4. **Freshness + detection + pricing + sync (Phases 4–8)** — independent hardening streams, run in parallel after Phase 0 where files do not collide.
5. **Postgres / container convergence (Phase 9)** — validates all column-adding phases on Postgres behind a Bash-enabled PG seam review; ships compose e2e smoke + durable coalescing + `/readyz`.
6. **External API + capture (Phases 10–11)** — IntentTree contract + OpenAPI; launch-time profile/effort sidecar.
7. **Docs finalization (Phase 12)** — CHANGELOG, feature-surface-architecture, CLAUDE.md, observability probes, karen pass.

### Critical Path

**0 → 1 → 2 → 3** (the top deliverable: full session detail over REST → MCP/CLI). Phases 2 and 3 are blocked until Phase 0 is green (zero-leak contract). Phase 9 is the Postgres/enterprise convergence gate for every column-adding phase (5, 6, and later 11). Phase 12 + karen close.

### Parallel Work Opportunities

After Phase 0 lands, four independent streams open: the **{1→2→3} session-detail chain**, **{4} link freshness**, **{6} pricing**, and **{7} sync coalescing**. Phase 5 (detection) and Phase 8 (freshness hardening) join in Wave 3; Phases 9/10 in Wave 4. See the `wave_plan` frontmatter for the machine-consumable graph.

### Single-Thread Note — Sync/Runtime File Editors

**Phases 5, 7, and 8 all touch `backend/runtime.py`, `backend/db/sync_engine.py`, and `backend/config.py`.** These files are declared serialization barriers in the `wave_plan`. The two-pass wave algorithm already keeps them out of the same wave: Phase 7 owns `runtime.py`/`sync_engine.py`/`config.py` edits in Wave 2, Phase 5 edits `sync_engine.py`/`migrations.py` in Wave 3, and Phase 8 edits `runtime.py`/`file_watcher.py`/`config.py` in Wave 3 (single-threaded against Phase 5). **No two of {5,7,8} may run concurrently against these shared files** — explicit file ownership per phase, no parallel agents on barrier files. If a scheduler ever co-locates two barrier-touching phases in one wave, split them into adjacent waves.

### Contending / Unmerged Work — remote-ccdash-streaming (READ BEFORE WAVE 3)

A paused-but-substantially-built effort, **remote-ccdash-streaming**, has shipped Phases 1–3 on the unmerged branches `feat/remote-ccdash-streaming{,-phase3,-phase4}` (SPIKE + ADRs at `29633f7`; `SessionIngestSource` port + `ingest_cursors` table + `source_ref` helper + `FilesystemSource`/`RemoteIngestSource` closed at `7e16d0f`; `POST /api/v1/ingest/sessions` + `ccdash daemon` at `0a38de6`). **None of that code is in `main` or this epic branch** — only the `project_id` persistence fixes (`299f7bc`, `5daed98`) were merged forward, and those are *complementary* to Phase 0, not contended. This epic was authored without reference to that branch; the guards below exist so executors do not refactor shared surfaces in a direction that fights the unmerged work at eventual merge.

| Shared surface | Streaming branch (built, unmerged) | This epic | Executor guard |
|----------------|------------------------------------|-----------|----------------|
| `backend/db/sync_engine.py` | Refactored behind a `SessionIngestSource` port; `FilesystemSource` wrapper; cursor table is the single source of sync truth | Phases 4/7/8 harden the *filesystem-coupled* engine directly; Phase 5 adds a sidecar→record join | Keep edits **behaviorally additive and localized**; do not re-architect the source/cursor boundary. Phase 5's sidecar join must be expressible as a discrete step that can later move behind the port. |
| `sessions` schema | Adds `source_ref` URI column; upsert key → `(project_id, source_ref)` | Phases 5/6/11 add columns; Phase 0 changes read/write paths | **Do not** add a `source_ref`/`source_type` column or change the upsert key — that identity model is owned by the streaming branch (ADR-009). New detection columns are independent and fine. |
| `/api/v1` namespace + auth | `POST /api/v1/ingest/sessions` (write); reserved a **workspace-scoped token** auth surface (ADR-008, unbuilt) | Phase 2 read endpoints; Phase 10 OpenAPI + **single optional `CCDASH_API_TOKEN`** (OQ-6) | Phase 2/10 own only **read** routes + the version constant; Phase 10's auth must be **forward-compatible** with a future workspace-token layer (see Phase 10 note), not a contradictory replacement. |
| ADR numbers 006/007 | Streaming branch defines ADR-006..010 for ingest/daemon/auth/port/routing | Main's **accepted, operator-ratified** ADR-006 (registry) / ADR-007 (write-failure) — depended on by this epic | **Number collision.** Resolution: the streaming branch renumbers its set (currently 006–010) to the next free block (**011–015**) on resume/merge. No action required inside this epic beyond awareness. |

**Net**: no deliverable in this epic duplicates streaming intent — the overlaps are file/schema/namespace adjacency, not redundant work. The guards keep both efforts mergeable.

## Deferred Items & In-Flight Findings Policy

### Deferred Items

Every deferred item must have a design-spec authoring task in Phase 12 with its path appended to `deferred_items_spec_refs`. The six open questions (OQ-1..6) are tracked as design-spec tasks DOC-001..DOC-006 — each resolved in its owning phase and documented at close-out.

#### Deferred Items Triage Table

| Item ID | Category | Reason Deferred | Trigger for Promotion | Target Spec Path |
|---------|----------|-----------------|-----------------------|-----------------|
| — | — | — | — | — |

*No pre-planned deferrals beyond the OQ design-spec tasks. Populate if execution surfaces scope cuts.*

### In-Flight Findings

The diagnostic report (`findings_doc_ref`) already captures the nine verified findings that seeded this plan. Any **new** execution-time finding follows the lazy-creation rule into `.claude/findings/ccdash-core-remediation-findings.md`; load-bearing findings add a design-spec row in Phase 12.

**Reference**: `.claude/skills/planning/references/deferred-items-and-findings.md`

## Phase Summary

Canonical orchestration index. Detail lives in the linked phase files. Default executor model **sonnet / adaptive**; docs **haiku / adaptive**.

| Phase | Title | Points | Target Subagent(s) | Model | Phase File |
|:-----:|-------|:------:|--------------------|-------|------------|
| 0 | Cross-project session correctness | ~3 | data-layer-expert | sonnet | [phase-0-correctness.md](./ccdash-core-remediation-v1/phase-0-correctness.md) |
| 1 | Transport-neutral transcript service + redaction | ~5 | python-backend-engineer | sonnet | [phase-1-3-session-access.md](./ccdash-core-remediation-v1/phase-1-3-session-access.md) |
| 2 | REST v1 detail + transcript endpoints | ~3 | python-backend-engineer | sonnet | [phase-1-3-session-access.md](./ccdash-core-remediation-v1/phase-1-3-session-access.md) |
| 3 | MCP session tools + repo-CLI session group | ~5 | python-backend-engineer | sonnet | [phase-1-3-session-access.md](./ccdash-core-remediation-v1/phase-1-3-session-access.md) |
| 4 | Live link freshness | ~3 | data-layer-expert | sonnet | [phase-4-link-freshness.md](./ccdash-core-remediation-v1/phase-4-link-freshness.md) |
| 5 | Detection (log-derivable) | ~8 | python-backend-engineer + ui-engineer-enhanced | sonnet | [phase-5-6-detection-pricing.md](./ccdash-core-remediation-v1/phase-5-6-detection-pricing.md) |
| 6 | Pricing correctness | ~3 | python-backend-engineer | sonnet | [phase-5-6-detection-pricing.md](./ccdash-core-remediation-v1/phase-5-6-detection-pricing.md) |
| 7 | Sync coalescing + recent-first + startup hygiene | ~5 | python-backend-engineer / backend-architect | sonnet | [phase-7-8-sync-freshness.md](./ccdash-core-remediation-v1/phase-7-8-sync-freshness.md) |
| 8 | Cross-project freshness hardening | ~5 | python-backend-engineer | sonnet | [phase-7-8-sync-freshness.md](./ccdash-core-remediation-v1/phase-7-8-sync-freshness.md) |
| 9 | Postgres parity + container/compose | ~8 | data-layer-expert + devops-architect | sonnet | [phase-9-postgres-container.md](./ccdash-core-remediation-v1/phase-9-postgres-container.md) |
| 10 | External API (IntentTree) | ~5 | api-designer / python-backend-engineer | sonnet | [phase-10-external-api.md](./ccdash-core-remediation-v1/phase-10-external-api.md) |
| 11 | Launch-time profile/effort capture | ~8 | python-backend-engineer | sonnet | [phase-11-capture.md](./ccdash-core-remediation-v1/phase-11-capture.md) |
| 12 | Docs finalization + CHANGELOG + karen | ~3 | documentation-writer + changelog-generator | haiku | [phase-12-docs.md](./ccdash-core-remediation-v1/phase-12-docs.md) |
| **Total** | — | **~67** | — | — | — |

**Model column conventions**: all executors default to `sonnet / adaptive`; Phase 12 docs default to `haiku / adaptive`. Phase 5 mixes backend (`python-backend-engineer`) with FE (`ui-engineer-enhanced`) — both sonnet. No external-model tasks in this program except optional Codex debug-escalation if Phase 4 causal-link proof or Phase 7 concurrency guard stalls >2 cycles.

## Wave Plan

Consumable by `/dev:execute-plan` from the `wave_plan` frontmatter above. Summary:

| Wave | Phases | Rationale |
|:----:|--------|-----------|
| W1 | 0 | Blocking prerequisite — zero-leak cross-project session reads. |
| W2 | 1, 4, 6, 7 | Independent streams after Phase 0. Phase 7 owns runtime/sync/config barrier edits this wave. |
| W3 | 2, 5, 8 | REST chain tail + detection + freshness hardening. 5 and 8 touch sync/runtime barriers single-threaded vs. each other and vs. W2 Phase 7. |
| W4 | 3, 9, 10 | MCP/CLI surface + Postgres convergence gate + external API. |
| W5 | 11 | Launch-time capture fast-follow (depends on Phase 3 surfaces). |
| W6 | 12 | Docs finalization + karen end-of-feature pass. |

## Risk Mitigation

Derived from the decisions-block risk hotspots and PRD §risks.

| Risk | Severity | Mitigation |
|------|:--------:|------------|
| Shared-file collisions: Phases 5/7/8 all edit `runtime.py`, `sync_engine.py`, `config.py` | High | Single-thread sync/runtime edits; explicit file ownership per phase; barriers declared in `wave_plan`; no parallel agents on these files. |
| Postgres column drift (Phases 5, 6, 11 add columns) | High | Dual SQLite + PG DDL + `COLUMN_PARITY_DRIFT_ALLOWLIST` update **in the same change**; Phase 9 Bash-enabled PG seam review as hard gate. |
| Cross-project read leak returns wrong project's rows | High | Phase 0 is a hard prerequisite; collision tests assert `project_id` never returns another project's rows; Phases 2/3 blocked until Phase 0 green. |
| Transcript egress leaks secrets/PII | High | Redaction layer is a Phase 1 deliverable (not optional); redaction unit tests required; local-trust documented. |
| Incremental link rebuild default-on regresses perf (global fingerprint scan) | Med | Phase 4 proves scoped path and asserts no global scan **before** flipping default. |
| Recent-first backfill silently partial | Med | Backfill count == baseline full-scan assertion; log dropped/deferred counts (no silent caps). |
| Runtime smoke gate bypassed for UI phases (3, 5, 6, 11) | Med | Dev server up + browser smoke per `target_surfaces`; no phase `completed` on unit tests alone; `runtime_smoke: skipped` requires explicit reason. |
| MCP transcript payload size causes client timeout | Med | Defined chunk/pagination budget + documented max in Phase 3 (OQ-2). |
| PG seam reviewer in edit-less mode misses PG-only bugs | High | Phase 9 seam review must be **Bash-enabled** (per memory: edit-less reviewer missed 3 PG-only bugs). |
| Unmerged `remote-ccdash-streaming` branch contends on `sync_engine.py`, `sessions` schema, `/api/v1`, ADR 006/007 | Med | See **Contending / Unmerged Work** above: no `source_ref`/upsert-key changes (ADR-009-owned), additive-only sync edits, forward-compat `/api/v1` auth, streaming renumbers ADRs 006–010 → 011–015 on merge. |

## Open Questions

Each OQ resolves in its owning phase and is documented via a Phase 12 design-spec task (DOC-001..DOC-006). Resolution rows feed `deferred_items_spec_refs`.

| OQ | Question | Owning Phase | Resolution Path | Design-Spec Task |
|:--:|----------|:-----------:|-----------------|:----------------:|
| OQ-1 | Redaction strategy: pattern-based secret scan vs allowlist field redaction vs layered? | 1 | Recommend layered: known secret patterns + tool-name-aware payload field redaction; configurable via env. | DOC-001 |
| OQ-2 | MCP transcript chunk size / max envelope bytes? | 3 | Pick a concrete default in Phase 3 design. | DOC-002 |
| OQ-3 | Recent-first window: N most-recent vs last-K-days vs mtime budget? | 7 | Decide in Phase 7. | DOC-003 |
| OQ-4 | Periodic reconcile cadence; registry-change-event-driven feasibility? | 8 | Decide in Phase 8. | DOC-004 |
| OQ-5 | Launch-time capture transport: wrapper script vs SessionStart hook vs sidecar convention? | 11 | Decide in Phase 11. | DOC-005 |
| OQ-6 | Auth for LAN `/api/v1`: bearer token vs none-on-LAN under local-trust? | 10 | Decide in Phase 10. | DOC-006 |

### Open Question Design-Spec Tasks (Phase 12 close-out)

| Task ID | Description | AC | Estimate | Subagent | Model | Effort |
|---------|-------------|----|:--------:|----------|-------|--------|
| DOC-001 | Author/append redaction-strategy design spec resolving OQ-1; link from Phase 1 progress. | Spec records chosen layered approach + env config; path in `deferred_items_spec_refs`. | 0.25 pts | documentation-writer | haiku | adaptive |
| DOC-002 | Author MCP transcript chunk/envelope-budget design spec resolving OQ-2. | Concrete default + documented max recorded. | 0.25 pts | documentation-writer | haiku | adaptive |
| DOC-003 | Author recent-first window design spec resolving OQ-3. | Window definition + backfill semantics recorded. | 0.25 pts | documentation-writer | haiku | adaptive |
| DOC-004 | Author reconcile-cadence design spec resolving OQ-4. | Cadence + event-driven feasibility verdict recorded. | 0.25 pts | documentation-writer | haiku | adaptive |
| DOC-005 | Author launch-time capture transport design spec resolving OQ-5. | Chosen transport + sidecar convention recorded. | 0.25 pts | documentation-writer | haiku | adaptive |
| DOC-006 | Author LAN `/api/v1` auth design spec resolving OQ-6. | Bearer-vs-none decision under local-trust recorded. | 0.25 pts | documentation-writer | haiku | adaptive |

## Reviewer Gates

| Gate | When | Reviewer | Mode |
|------|------|----------|------|
| Per-phase completion validation | End of every phase before `status: completed` | task-completion-validator | Standard; runs `validate-phase-completion.py` + `ac-coverage-report.py` |
| Phase 0 collision review | Phase 0 exit | senior-code-reviewer | **Bash-enabled** (PG collision tests must run) |
| Phase 9 Postgres seam review | Phase 9 exit (hard gate) | senior-code-reviewer | **Bash-enabled, mandatory** — must run PG parity/compose smoke; edit-less mode prohibited (memory: edit-less missed 3 PG-only bugs) |
| Causal-link proof | Phase 4 exit | ultrathink-debugger | Proves scoped rebuild fires on watcher path, no global scan |
| FE+BE seam | Phase 5 exit | integration_owner (required) | Backend columns ↔ FE fallback contract |
| Runtime smoke | Phases 3, 5, 6, 11 exit | phase owner | Dev server up + browser smoke per `target_surfaces`; `runtime_smoke: skipped` requires reason |
| End-of-feature | After Phase 12 | karen | Full-feature acceptance pass; CHANGELOG present |

## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| MCP `session_detail` returns transcript for non-active project | Not supported | 100% of calls with valid project_id | MCP parity test |
| Cross-project row leak in session reads | Present (unguarded) | Zero (2 projects, shared IDs) | ADR-007 collision test |
| Link freshness: new subagent JSONL → linked | Requires restart | ≤ 1 watcher cycle (~30 s) | Integration test |
| Novel model ID pricing | Silent Sonnet default | Flagged `unpriced` | Regression fixture |
| Duplicate full-sync under Postgres | Unguarded | Zero per project/trigger | Coalescing unit test |
| compose e2e smoke | No container support | Green on `api + worker + postgres` | CI/manual smoke |
| OpenAPI spec committed | None | Committed and contract-pinned | PR gate |
| Code coverage on new modules | — | >80% | Backend test suite |

## Progress Tracking

`.claude/progress/ccdash-core-remediation/phase-N-progress.md` (one per phase, schema_version: 2).

---

**Implementation Plan Version**: 1.0
**Last Updated**: 2026-06-10
