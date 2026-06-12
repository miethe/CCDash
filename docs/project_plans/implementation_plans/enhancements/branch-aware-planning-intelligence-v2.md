---
schema_version: 2
doc_type: implementation_plan
title: "Implementation Plan: Branch-Aware Planning Intelligence v2"
status: draft
created: '2026-06-11'
updated: '2026-06-11'
feature_slug: branch-aware-planning-intelligence
feature_version: v2
prd_ref: docs/project_plans/PRDs/enhancements/branch-aware-planning-intelligence-v2.md
plan_ref: null
human_brief_ref: docs/project_plans/human-briefs/branch-aware-planning-intelligence-v2.md
scope: >
  BranchWatcherRegistry infrastructure, DB migration v34, S2 branch-signal correlation,
  branch-aware cache isolation, and PlanningTopBar branch chip — closing the
  multi-worktree doc-sync and session-correlation gap left by Phase 1.
effort_estimate: "~26 pts"
architecture_summary: >
  ADR-007 retrofit + ADR-008 acceptance (P0) → DB migration v34 + cache
  branch_filter dimension (P1) → BranchWatcherRegistry infra (P2) || S2 correlation
  (P3) || frontend chip (P4) → integration + N=3–5 profiling (P5) → docs (P6).
  Critical path: P0→P1→P2→P5→P6 (~19 pts).
related_documents:
  - docs/project_plans/PRDs/enhancements/branch-aware-planning-intelligence-v2.md
  - docs/project_plans/implementation_plans/enhancements/branch-aware-planning-intelligence-v1.md
  - docs/project_plans/design-specs/branch-aware-phase2-multi-branch-watcher.md
  - docs/project_plans/design-specs/command-center-detail-panel-consolidation.md
  - docs/project_plans/exploration/branch-aware-planning-intelligence/branch-aware-planning-intelligence-charter.md
  - docs/project_plans/adrs/adr-006-db-authoritative-project-registry.md
  - docs/project_plans/adrs/adr-007-db-write-failure-surfacing-standard.md
  - docs/project_plans/adrs/adr-008-branch-watcher-registry-planning-service-seam.md
references:
  user_docs: []
  context:
    - docs/guides/feature-surface-architecture.md
    - .claude/worknotes/branch-aware-planning-intelligence/feature-guide.md
  specs:
    - docs/project_plans/design-specs/branch-aware-phase2-multi-branch-watcher.md
  related_prds:
    - docs/project_plans/PRDs/enhancements/branch-aware-planning-intelligence-v1.md
    - docs/project_plans/PRDs/enhancements/planning-agent-session-board-v1.md
    - docs/project_plans/PRDs/enhancements/multi-project-planning-command-center-v1.md
spike_ref: docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/r01-branch-watcher/r01-branch-watcher-brief.md
charter_ref: docs/project_plans/exploration/branch-aware-planning-intelligence/branch-aware-planning-intelligence-charter.md
adr_refs:
  - docs/project_plans/adrs/adr-006-db-authoritative-project-registry.md
  - docs/project_plans/adrs/adr-007-db-write-failure-surfacing-standard.md
  - docs/project_plans/adrs/adr-008-branch-watcher-registry-planning-service-seam.md  # PROPOSED — accepted by P0 exit gate
deferred_items_spec_refs:
  - docs/project_plans/design-specs/command-center-detail-panel-consolidation.md
findings_doc_ref: null
changelog_ref: null
changelog_required: true
test_plan_ref: null
plan_structure: unified
progress_init: auto
owner: null
contributors: []
priority: high
risk_level: medium
category: enhancements
tags:
  - implementation
  - planning
  - branch-watcher
  - multi-branch
  - session-correlation
  - infrastructure
  - phase-2
milestone: null
commit_refs: []
pr_refs: []
files_affected: []
wave_plan:
  serialization_barriers:
    - backend/db/sqlite_migrations.py
    - backend/db/postgres_migrations.py
    - backend/runtime/container.py
    - CHANGELOG.md
    - types.ts
  phases:
    - id: P0
      depends_on: []
      isolation: shared
      parallelizable: false
      provider: claude
      model: sonnet
      effort: adaptive        # T0-005 ADR-008 authoring uses per-task override: extended
      owner_skills: []
      files_affected:
        - backend/db/repositories/documents.py
        - docs/project_plans/adrs/adr-008-branch-watcher-registry-planning-service-seam.md
    - id: P1
      depends_on: [P0]
      isolation: shared
      parallelizable: false
      provider: claude
      model: sonnet
      effort: adaptive
      owner_skills: []
      files_affected:
        - backend/db/sqlite_migrations.py
        - backend/db/postgres_migrations.py
        - backend/application/services/agent_queries/cache.py
        - backend/application/services/agent_queries/planning_sessions.py
        - backend/application/services/agent_queries/planning_command_center.py
        - backend/application/services/agent_queries/planning.py
    - id: P2
      depends_on: [P1]
      isolation: shared
      parallelizable: true
      provider: claude
      model: sonnet
      effort: extended
      integration_owner: backend-architect
      owner_skills: []
      files_affected:
        - backend/db/branch_watcher.py
        - backend/runtime/container.py
        - backend/adapters/jobs/runtime_job_adapter.py
    - id: P3
      depends_on: [P1]
      isolation: shared
      parallelizable: true
      provider: claude
      model: sonnet
      effort: adaptive
      owner_skills: []
      files_affected:
        - backend/application/services/agent_queries/session_correlation.py
    - id: P4
      depends_on: [P1]
      isolation: shared
      parallelizable: true
      provider: claude
      model: sonnet
      effort: adaptive
      integration_owner: ui-engineer-enhanced
      ui_touched: true
      owner_skills: []
      files_affected:
        - components/Planning/PlanningTopBar.tsx
        - types.ts
    - id: P5
      depends_on: [P2, P3, P4]
      isolation: shared
      parallelizable: false
      provider: claude
      model: sonnet
      effort: adaptive
      owner_skills: []
      files_affected:
        - backend/tests/test_branch_watcher_integration.py
        - backend/tests/test_branch_correlation.py
        - .claude/worknotes/branch-aware-planning-intelligence/wamp-profiling-report-v2.md
    - id: P6
      depends_on: [P5]
      isolation: shared
      parallelizable: false
      provider: claude
      model: haiku
      effort: adaptive
      owner_skills: []
      files_affected:
        - CHANGELOG.md
        - .claude/worknotes/branch-aware-planning-intelligence/feature-guide-v2.md
        - docs/guides/
  waves:
    - [P0]
    - [P1]
    - [P2, P3, P4]
    - [P5]
    - [P6]
---

# Implementation Plan: Branch-Aware Planning Intelligence v2

**Plan ID**: `IMPL-2026-06-11-BRANCH-AWARE-PLANNING-INTELLIGENCE-V2`
**Date**: 2026-06-11
**Author**: Claude Sonnet 4.6 (Implementation Planner)
**Human Brief**: `docs/project_plans/human-briefs/branch-aware-planning-intelligence.md`
— Estimation sanity check (H3/H5/H6 reasoning, 26-pt breakdown) and OQ-1..OQ-7 ledger live there.

**Related Documents**:
- **PRD v2**: `docs/project_plans/PRDs/enhancements/branch-aware-planning-intelligence-v2.md`
- **Design Spec**: `docs/project_plans/design-specs/branch-aware-phase2-multi-branch-watcher.md`
- **R-01 Brief**: `docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/r01-branch-watcher/r01-branch-watcher-brief.md`
- **ADR-006**: `docs/project_plans/adrs/adr-006-db-authoritative-project-registry.md`
- **ADR-007**: `docs/project_plans/adrs/adr-007-db-write-failure-surfacing-standard.md`
- **Proposed ADR-008**: `docs/project_plans/adrs/adr-008-branch-watcher-registry-planning-service-seam.md` _(accepted by P0 exit gate)_
- **Phase 1 Plan (style anchor)**: `docs/project_plans/implementation_plans/enhancements/branch-aware-planning-intelligence-v1.md`

**Complexity**: Large
**Total Estimated Effort**: 26 pts
**Target Timeline**: ~3 weeks

---

## Executive Summary

Phase 2 closes the multi-worktree infrastructure gap left by Phase 1 (display-only). This
plan delivers: **(P0)** ADR-007 compliance on `SqliteDocumentRepository.upsert` and ADR-008
acceptance formalizing the `BranchWatcherRegistry`↔planning-service seam; **(P1)** DB migration
v34 (`documents.branch` column + 2 indexes) and branch-aware `param_extractor` cache isolation
on four `@memoized_query` planning endpoints; **(P2)** `BranchWatcherRegistry` infra
(`backend/db/branch_watcher.py`, container registration, startup lifecycle serialized against
`_run_all_projects_sync_job`); **(P3)** `_correlate_branch` step 5a in `session_correlation.py`
(medium confidence, Codex null-branch early-exit, exclusion set); **(P4)** `PlanningTopBar`
DEF-003 branch chip with resilience fallback; and **(P5/P6)** integration verification with N=3–5
write-amplification profiling and operator documentation.

**Critical path**: P0 → P1 → P2 → P5 → P6 (~19 pts). P3 and P4 run concurrently with P2 after P1.
**Reviewer gates**: `task-completion-validator` per phase; `karen` at P0, P2, P5, and feature end (P6).

---

## Implementation Strategy

### Architecture Sequence

Strict CCDash layered order:

1. **Prerequisites** — ADR-007 retrofit + ADR-008 accepted (P0)
2. **Data Layer** — Migration v34 + `branch_filter` cache dimension (P1)
3. **Infrastructure** — `BranchWatcherRegistry` class, container registration, startup lifecycle (P2 — parallel)
4. **Service Layer** — S2 `_correlate_branch` step 5a (P3 — parallel)
5. **UI Layer** — `PlanningTopBar` branch chip, DEF-003 (P4 — parallel)
6. **Verification & Profiling** — integration tests + N=3–5 write-amplification profiling (P5)
7. **Documentation** — CHANGELOG, operator guidance, feature guide, deferred-item spec refresh (P6)

### Parallel Work Opportunities

After P1 exits: **P2**, **P3**, and **P4** can run concurrently. P4 needs nothing from P2 or P3
(reads `worktree.branch` already populated in Phase 1). P3 needs only the
`idx_sessions_git_branch_project` index from P1. P2 is the longest concurrent phase (6 pts,
`extended` effort) and gates P5. P5 cannot start until P2 + P3 + P4 are all complete.

### Critical Path

P0 (4 pts) → P1 (4 pts) → P2 (6 pts) → P5 (3 pts) → P6 (2 pts) = **19 pts on the critical chain**.
Concurrently running P3 (4 pts) and P4 (3 pts) do not lengthen the critical path.

### Phase Summary

At-a-glance orchestration index. Keep in sync with per-phase task breakdowns below.

| Phase | Title | Est. | Target Subagent(s) | Model | Effort | Notes |
|-------|-------|-----:|--------------------|-------|--------|-------|
| P0 | Prerequisites & Seam Decision | 4 pts | data-layer-expert, backend-architect | sonnet | adaptive / extended | T0-005 ADR-008: extended. **karen milestone.** |
| P1 | Data Layer | 4 pts | data-layer-expert | sonnet | adaptive | Migration v34 + cache param_extractor. |
| P2 | BranchWatcherRegistry Infra | 6 pts | backend-architect, python-backend-engineer | sonnet | extended | Heaviest infra. `integration_owner: backend-architect`. **karen milestone.** |
| P3 | S2 Branch-Signal Correlation | 4 pts | python-backend-engineer | sonnet | adaptive | Parallel with P2. H3 floor: ≥3 pts for algorithmic service. |
| P4 | Frontend Surface (DEF-003) | 3 pts | ui-engineer-enhanced | sonnet | adaptive | Thin. Parallel with P2/P3. `integration_owner: ui-engineer-enhanced`. |
| P5 | Verification & Profiling | 3 pts | python-backend-engineer | sonnet | adaptive | N=3–5 write-amplification profiling (OQ-5). **karen milestone.** |
| P6 | Docs & Finalization | 2 pts | documentation-writer, changelog-generator | haiku | adaptive | CHANGELOG, operator guidance, feature guide, deferred specs. **karen feature-end.** |
| **Total** | — | **26 pts** | — | — | — | Within R-01 20–27 pt range. |

> **Estimation rationale** lives in the Human Brief §2 (H3/H5/H6 reasoning + 26-pt breakdown).
> Plan retains per-phase task estimates only.

---

## Cross-Phase Structured Acceptance Criteria

These ACs introduce optional backend fields or span multiple owner specialties.
Declared here; referenced in per-phase task tables via `verified_by`.

#### AC BRANCH-EMPTY-FALLBACK: Frontend gracefully handles absent/empty `documents.branch` _(R-P2)_

- target_surfaces:
    - `components/Planning/PlanningTopBar.tsx`
    - `components/Planning/CommandCenter/CommandCenterFeatureCard.tsx`
    - `components/Planning/CommandCenter/CommandCenterDetailPanel.tsx`
- propagation_contract: >
    `branch_filter` flows from `@memoized_query` planning endpoints →
    `PlanningCommandCenterItemDTO.worktree.branch` → frontend via
    `services/queries/planning.ts`. When `branch_filter=None` (default), results are
    identical to Phase 1 (no branch scoping). Frontend uses `worktree?.branch` with
    optional chaining throughout.
- resilience: >
    When `documents.branch` is `''` (default) or `null`: `PlanningTopBar` chip is hidden
    — not rendered, no error thrown, no error boundary triggered.
    `CommandCenterFeatureCard` and `CommandCenterDetailPanel` render normally; missing
    branch treated as "no scoping." `branch_filter=None` cache key is byte-identical to
    Phase 1 key (regression test T1-004).
- visual_evidence_required: >
    Screenshot at desktop ≥1440px — planning command center with no active worktree
    branch (chip absent) and with an active worktree branch (chip present).
- verified_by:
    - T4-003
    - T5-003

---

#### AC BWR-SEAM: `BranchWatcherRegistry`↔planning-service call-site constraint _(R-P3, integration_owner: backend-architect)_

- target_surfaces:
    - `backend/db/branch_watcher.py`
    - `backend/runtime/container.py`
    - `backend/adapters/jobs/runtime_job_adapter.py`
    - `backend/application/services/agent_queries/planning_command_center.py`  # planning write path — sole call site
- propagation_contract: >
    `BranchWatcherRegistry.register()` is invoked ONLY from the planning control plane
    write path on `planning_worktree_contexts` INSERT with `status='running'`.
    `unregister()` is invoked only on UPDATE to a terminal status (`'completed'`,
    `'cancelled'`, `'failed'`). A linting comment marks the call site:
    `# BranchWatcherRegistry call site — ADR-008 §3`. No other service layer may call
    `register()` or `unregister()`.
- resilience: >
    If `register()` is called with a non-existent `worktree_path`, method logs a `WARNING`
    and returns without raising. Container starts cleanly with zero registered branch
    watchers. `stop_all()` on an empty registry is a no-op.
- visual_evidence_required: false
- verified_by:
    - T2-006
    - T5-001

---

#### AC DEF003-CHIP-SMOKE: `PlanningTopBar` branch chip runtime smoke _(R-P4: P4 touches `*.tsx`)_

- target_surfaces:
    - `components/Planning/PlanningTopBar.tsx`
- propagation_contract: >
    Chip reads `PlanningCommandCenterItemDTO.worktree?.branch` (already populated by
    Phase 1 backend). No backend change required for Phase 2. Uses optional chaining;
    conditionally rendered when value is non-null and non-empty string.
- resilience: >
    When `worktree` is `undefined` or `branch` is `null`/`''`: chip not rendered, no
    error thrown, no error boundary triggered. Unit test covers both states.
- visual_evidence_required: >
    Before/after screenshots at desktop ≥1440px: chip visible with an active
    `planning_worktree_contexts` row; chip absent without one.
- verified_by:
    - T4-002
    - T5-003

---

## Deferred Items & In-Flight Findings Policy

### Deferred Items Triage Table

| Item ID | Category | Reason Deferred | Trigger for Promotion | Target Spec Path |
|---------|----------|-----------------|-----------------------|------------------|
| DEF-CMDCTR-CONSOLIDATION | scope-cut | `CommandCenterDetailPanel` full replacement with board modal requires design finalization; Phase 1 "Open full detail" bridge is interim affordance | Design spec promoted to `approved` maturity; cross-feature coupling resolved | `docs/project_plans/design-specs/command-center-detail-panel-consolidation.md` _(exists; refreshed in T6-004)_ |
| DEF-OQ6-TUNING | backlog | Exact-match → `confidence=high` promotion for `feat/<slug>` branches deferred pending post-ship FP telemetry; Phase 2 ships uniform `medium` | FP rate measured; exclusion set tuning complete | OQ-6 note appended in T6-004 |
| DEF-COMPOSITE-PK | dependency-blocked | Full per-worktree document isolation (composite PK on `documents` including `branch`) is Phase 3 scope; last-writer-wins accepted as Phase 2 limitation | Phase 3 PRD authored | Phase 3 PRD |
| DEF-CWD-INFERENCE | spike-needed | `cwd`/`workingDirectories` stored in `session_forensics_json` blob; not a direct DB column; any use requires `_ensure_column` migration as prerequisite (charter disclosure constraint a) | Migration authored + tested | Phase 3 scope |

### In-Flight Findings

**Lazy-creation rule**: The findings doc is NOT pre-created. Create only on first real finding.
Path: `.claude/findings/branch-aware-planning-intelligence-findings.md`.
On creation: set `findings_doc_ref` in frontmatter; append path to `related_documents`.

### Quality Gate

P6 cannot be sealed until:
- All deferred items have a design-spec path in `deferred_items_spec_refs`, OR N/A with rationale.
- `findings_doc_ref` is null OR findings doc advanced to `accepted`.

---

## Phase Breakdown

**Column conventions**: `Estimate` = story points (size). `Effort` = reasoning budget
(`adaptive` | `extended` for Claude). Never put size in Effort.

---

### Phase 0: Prerequisites & Seam Decision

**Duration**: ~4 pts
**Dependencies**: None
**Assigned Subagent(s)**: `data-layer-expert` (T0-001..T0-004), `backend-architect` (T0-005)
**Reviewer**: `task-completion-validator` → `karen` (P0 milestone)

| Task ID | Task Name | Description | Acceptance Criteria | Est. | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|---------------------|------|-------------|-------|--------|--------------|
| T0-001 | ADR-007 Retrofit — upsert | Replace bare `self.db.commit()` with `retry_on_locked(self.db.commit, repo="documents")` in `SqliteDocumentRepository.upsert` (`backend/db/repositories/documents.py`). Confirm `retry_on_locked` import from `base.py`. | `upsert` uses `retry_on_locked`; no bare `self.db.commit()` remains in that method; `PRAGMA busy_timeout = 30000` confirmed on singleton connection | 1 pt | data-layer-expert | sonnet | adaptive | None |
| T0-002 | Direct-count assertion test | After upsert, `SELECT COUNT(*) FROM documents WHERE project_id=? AND branch=?` returns expected count (ADR-007 §4). Test in `backend/tests/test_documents_adr007.py`. | Test passes; count matches inserted row count exactly; ADR-007 §4 fulfilled | 0.5 pt | data-layer-expert | sonnet | adaptive | T0-001 |
| T0-003 | Lock-injection test | Inject `SQLITE_BUSY` on first `commit()` call; assert retry succeeds and the row is persisted (ADR-007 §5 pattern). | Lock-injection test passes; row present post-retry | 0.5 pt | data-layer-expert | sonnet | adaptive | T0-001 |
| T0-004 | Postgres parity — upsert | In Postgres documents repository: add `ON CONFLICT DO UPDATE SET branch = EXCLUDED.branch`; add Postgres direct-count assertion test mirroring T0-002. | Postgres direct-count test passes; `branch` included in `ON CONFLICT DO UPDATE` clause | 1 pt | data-layer-expert | sonnet | adaptive | T0-001 |
| T0-005 | Draft + Accept ADR-008 | Using `pm:create-adr` pattern, author `docs/project_plans/adrs/adr-008-branch-watcher-registry-planning-service-seam.md`. Must record: OQ-1 resolution (direct-call model — no event bus; planning write path calls `register`/`unregister` directly per decisions block §7); OQ-2 resolution (`backend/db/branch_watcher.py` — new file); OQ-3 resolution (startup coroutine after `_run_all_projects_sync_job`); OQ-4 resolution (log+skip for missing `worktree_path`; no unilateral terminal-status mutation). Set `status: accepted`. `backend-architect` review required before acceptance. | ADR-008 `status: accepted`; OQ-1/OQ-2/OQ-3/OQ-4 all recorded with resolutions matching decisions block §7; call-site contract and lifecycle binding specified | 1 pt | backend-architect | sonnet | extended | T0-001 |

**Phase 0 Exit Gate (karen milestone)**:
- [ ] `SqliteDocumentRepository.upsert` uses `retry_on_locked` (T0-001)
- [ ] Direct-count test passes on SQLite + Postgres (T0-002, T0-004)
- [ ] Lock-injection test passes (T0-003)
- [ ] ADR-008 `status: accepted`; OQ-1/OQ-2/OQ-3/OQ-4 resolved (T0-005)
- [ ] `task-completion-validator` passes; `karen` milestone sign-off required

---

### Phase 1: Data Layer

**Duration**: ~4 pts
**Dependencies**: P0 complete
**Assigned Subagent(s)**: `data-layer-expert`
**Reviewer**: `task-completion-validator`

| Task ID | Task Name | Description | Acceptance Criteria | Est. | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|---------------------|------|-------------|-------|--------|--------------|
| T1-001 | Migration v34 — documents.branch + index | `ALTER TABLE documents ADD COLUMN branch TEXT DEFAULT ''` via `_ensure_column` helper; `CREATE INDEX IF NOT EXISTS idx_docs_project_branch ON documents(project_id, branch)`. Both guarded for idempotency per established migration pattern. | Migration v34 applies cleanly on fresh + upgraded SQLite DB; `documents.branch` column present with default `''`; `idx_docs_project_branch` exists | 1 pt | data-layer-expert | sonnet | adaptive | P0 complete |
| T1-002 | Migration v34 — sessions index | `CREATE INDEX IF NOT EXISTS idx_sessions_git_branch_project ON sessions(git_branch, project_id)` — index-only, no write path, zero ADR-007 cost. | Index exists post-migration; `EXPLAIN QUERY PLAN` on `WHERE git_branch=? AND project_id=?` uses index | 0.5 pt | data-layer-expert | sonnet | adaptive | T1-001 |
| T1-003 | Migration v34 — Postgres parity | Mirror both DDL statements in `backend/db/postgres_migrations.py`: `ALTER TABLE documents ADD COLUMN IF NOT EXISTS branch TEXT DEFAULT ''`; composite index; sessions index. | Postgres migration v34 applies clean; column + indexes present; Postgres direct-count parity confirmed | 1 pt | data-layer-expert | sonnet | adaptive | T1-001 |
| T1-004 | branch_filter param_extractor on 4 endpoints | Add `branch_filter: str \| None = None` as `param_extractor` dimension on `planning_project_summary`, `planning_project_graph`, `planning_feature_context`, and `pss_session_board` in `backend/application/services/agent_queries/`. Design spec §6 shape (see PRD §9 cache code shape). When `branch_filter=None`, cache key MUST be byte-identical to Phase 1 key. `aclear_project_cache(project_id)` evicts all branch slots. | Backward-compat regression test: `branch_filter=None` key == Phase 1 key on all 4 endpoints. `branch_filter='feat/x'` produces distinct slot. `aclear_project_cache` evicts branch-filtered slots correctly. | 1.5 pt | data-layer-expert | sonnet | adaptive | T1-002 |

**Phase 1 Exit Gate**:
- [ ] Migration v34 applies cleanly on SQLite + Postgres (T1-001 through T1-003)
- [ ] `branch_filter=None` cache key byte-identical to Phase 1 key — regression test passes (T1-004)
- [ ] `branch_filter='feat/x'` produces a distinct cache slot (T1-004)
- [ ] `aclear_project_cache(project_id)` evicts all branch-filtered slots (T1-004)
- [ ] `task-completion-validator` passes

---

### Phase 2: BranchWatcherRegistry Infrastructure

**Duration**: ~6 pts
**Dependencies**: P1 complete (runs parallel with P3 and P4 after P1)
**Assigned Subagent(s)**: `backend-architect` (primary), `python-backend-engineer` (secondary)
**integration_owner**: `backend-architect`
**Reviewer**: `task-completion-validator` → `karen` (P2 milestone)

> **R-P3 trigger**: P2 has ≥2 owner specialties (backend-architect + python-backend-engineer)
> with overlapping files (`container.py`, `runtime_job_adapter.py`).
> `integration_owner: backend-architect`. Seam task: T2-006.

| Task ID | Task Name | Description | Acceptance Criteria | Est. | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|---------------------|------|-------------|-------|--------|--------------|
| T2-001 | BranchWatcherRegistry class | New `backend/db/branch_watcher.py` (OQ-2 resolution — NOT in `file_watcher.py`). Class keyed by `(project_id: str, worktree_path: str)`. `asyncio.Lock` on all mutating ops. `BranchWatcherEntry(watcher, worktree_path, branch, feature_id, docs_dir, progress_dir)`. Reuses existing `FileWatcher` instances unchanged — no modification to `FileWatcher.start()`. See design spec §4.1 (Option A). | Class instantiates; key tuple uniquely identifies entries; `asyncio.Lock` present; `BranchWatcherEntry` defined; no modification to `FileWatcher.start()` | 2 pt | backend-architect | sonnet | extended | P1 complete, ADR-008 accepted |
| T2-002 | register() / unregister() | `register(project_id, worktree_path, branch, feature_id, sync_engine)`: derives `docs_dir` and `progress_dir` from `worktree_path`; calls `sync_changed_files(project_id, ...)` with parent `project_id` (ADR-006); sessions directory explicitly excluded from watch scope. `unregister(project_id, worktree_path)`: stops and removes entry. `asyncio.Lock` held during mutation. | `register()` starts `FileWatcher` on `(docs_dir, progress_dir)` only; sessions dir absent from watch scope; `sync_changed_files` uses parent `project_id`; `unregister()` stops + removes entry; lock held | 1.5 pt | backend-architect | sonnet | extended | T2-001 |
| T2-003 | Container registration + stop_all() | Register `BranchWatcherRegistry` in `backend/runtime/container.py` alongside `FileWatcherRegistry`. Wire `stop_all()` from `RuntimeJobAdapter.stop()`. `stop_all()` on empty registry is a no-op. Existing `FileWatcherRegistry` lifecycle unaffected. | `BranchWatcherRegistry` in `container.py`; `RuntimeJobAdapter.stop()` calls `stop_all()`; empty-registry no-op; existing `FileWatcherRegistry` lifecycle unchanged | 0.5 pt | python-backend-engineer | sonnet | adaptive | T2-001 |
| T2-004 | Startup hydration + serialization | Startup coroutine (OQ-3 resolution) runs **after** `_run_all_projects_sync_job` completes. Loads all active `planning_worktree_contexts` rows. Calls `register()` for each where `worktree_path` exists on disk. Logs `WARNING` and skips rows with missing paths (OQ-4 resolution — no unilateral terminal-status update per ADR-006 spirit). | Startup registers all valid active rows; missing-path rows produce exactly one `WARNING` log and no crash; coroutine serialized after `_run_all_projects_sync_job`; no race with per-project sync | 1.5 pt | backend-architect | sonnet | extended | T2-002, T2-003 |
| T2-005 | Snapshot API extension | `_watcher_registry_snapshot()` output gains a parallel `branch_watchers: dict[str, dict]` key. Existing `dict[project_id, dict]` structure unchanged (no composite keys). Snapshot contract test confirms existing consumers receive unchanged output. | `branch_watchers` key present in snapshot; existing `project_id`-keyed dict unchanged; snapshot contract test passes | 0.5 pt | python-backend-engineer | sonnet | adaptive | T2-001 |
| T2-006 | Seam integration test _(R-P3 seam task)_ | Integration test verifying `planning_worktree_contexts` INSERT with `status='running'` triggers `BranchWatcherRegistry.register()`; UPDATE to terminal status triggers `unregister()`. Add linting comment at call site in planning write path: `# BranchWatcherRegistry call site — ADR-008 §3`. No other service layer path exercised in test. Verifies AC BWR-SEAM. | Seam integration test passes; linting comment present at call site; no other service layer can reach `register()`/`unregister()` without violating the comment gate | 0.5 pt | backend-architect | sonnet | adaptive | T2-002, T2-004 |

**Phase 2 Exit Gate (karen milestone)**:
- [ ] `BranchWatcherRegistry` class in `backend/db/branch_watcher.py`; key tuple correct (T2-001)
- [ ] `register()` / `unregister()` unit tests pass; sessions dir excluded (T2-002)
- [ ] Container registration + shutdown `stop_all()` wired (T2-003)
- [ ] Startup hydration serialized after `_run_all_projects_sync_job`; missing-path warning fires (T2-004)
- [ ] `branch_watchers` snapshot key present; existing snapshot contract unchanged (T2-005)
- [ ] Seam integration test passes; linting comment at call site (T2-006)
- [ ] AC BWR-SEAM target surfaces verified (see §Cross-Phase Structured ACs)
- [ ] `task-completion-validator` passes; `karen` milestone sign-off required

---

### Phase 3: S2 Branch-Signal Correlation

**Duration**: ~4 pts
**Dependencies**: P1 complete (runs parallel with P2 and P4)
**Assigned Subagent(s)**: `python-backend-engineer`
**Reviewer**: `task-completion-validator`

> **H3 floor**: `_correlate_branch` is an algorithmic correlation service → ≥3 pts floor
> honored (P3 = 4 pts per decisions block §4).

| Task ID | Task Name | Description | Acceptance Criteria | Est. | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|---------------------|------|-------------|-------|--------|--------------|
| T3-001 | Module-level correlation constants | Add to `backend/application/services/agent_queries/session_correlation.py`: `_BRANCH_EXCLUSION_SET: frozenset[str]` (noise branches: `main`, `master`, `develop`, `dev`, `HEAD`, `release`, `hotfix`, `staging`, `prod`, `production`); `_BRANCH_PREFIXES: list[str]` (`feat/`, `feature/`, `fix/`, `bug/`, `chore/`, `refactor/`, `hotfix/`); `_normalize_branch_for_correlation(branch: str) -> str` (strip prefix, lowercase, normalize `_`→`-`). Collocated with `_correlate_command_tokens` per established extension pattern. | Constants defined at module level; `_normalize_branch_for_correlation` strips listed prefixes, lowercases, normalizes hyphens/underscores; exclusion set is a `frozenset`; collocated with `_correlate_command_tokens` | 0.5 pt | python-backend-engineer | sonnet | adaptive | P1 complete |
| T3-002 | _correlate_branch() implementation | Implement `_correlate_branch(session: dict, feature_index: dict) -> list[CorrelationEvidence]` as step 5a in `correlate_session()`, inserted after `_correlate_command_tokens`. Logic: (1) Codex null-branch early-exit: `session.get("git_branch") is None` → return `[]`; (2) normalize via `_normalize_branch_for_correlation`; (3) min-length guard: normalized slug < 8 chars → `[]`; (4) exclusion set check → `[]`; (5) match normalized slug tokens against feature slug tokens in `feature_index`; (6) return evidence entries with `confidence='medium'`. No `confidence='high'` assigned (reserved for `entity_links`). | Function present as step 5a; Codex early-exit on None; `[]` on normalized slug < 8 chars; `[]` for exclusion-set branches; `medium` confidence evidence returned for matching feature slug tokens; no `high` confidence assigned | 2 pt | python-backend-engineer | sonnet | adaptive | T3-001 |
| T3-003 | Correlation unit tests | `backend/tests/test_branch_correlation.py`: (1) positive match: `feat/my-feature` → `medium` evidence for feature slug `my-feature`; (2) exclusion-set reject: `main`, `develop` → `[]`; (3) min-length: 7-char slug → `[]`; 8-char slug (non-excluded) → evidence; (4) regression: existing `_correlate_command_tokens` test suite still passes unmodified. | All 4 test cases pass; zero regression on existing correlation pipeline tests | 1 pt | python-backend-engineer | sonnet | adaptive | T3-002 |
| T3-004 | Codex null-branch disclosure AC _(R-01 precondition 4)_ | `test_codex_null_branch_no_correlation`: Codex session (`git_branch=None`) produces `[]` from `_correlate_branch`. `test_codex_null_branch_ui_disclosure`: assert `branch_filter=None` planning query returns Codex sessions (planning behavior not gated on branch presence). AC-S2-CODEX verified. Structured log output for branch-signal evidence includes `branch_slug` and `normalized_slug` fields per PRD §6 observability req. | Codex null-branch test passes; planning queries with `branch_filter=None` include Codex sessions; structured log fields present; AC-S2-CODEX met | 0.5 pt | python-backend-engineer | sonnet | adaptive | T3-002 |

**Phase 3 Exit Gate**:
- [ ] `_correlate_branch` present as step 5a in `correlate_session()`, after `_correlate_command_tokens` (T3-002)
- [ ] Exclusion set, prefix normalization, min-length guard all implemented and tested (T3-001, T3-003)
- [ ] Codex null-branch early-exit test passes; planning behavior not gated on branch presence (T3-004)
- [ ] No regression in existing correlation pipeline tests (T3-003)
- [ ] `task-completion-validator` passes

---

### Phase 4: Frontend Surface (DEF-003)

**Duration**: ~3 pts
**Dependencies**: P1 complete (runs parallel with P2 and P3)
**Assigned Subagent(s)**: `ui-engineer-enhanced`
**integration_owner**: `ui-engineer-enhanced`
**Reviewer**: `task-completion-validator`

> **Scope guard**: P4 is intentionally thin. Phase 1 v1 shipped active-session chips,
> per-phase session links, branch/commit click-dialog, and SSE topology. P4 = DEF-003
> chip + verified-unshipped gaps only. Do NOT re-author Phase 1 UI.
>
> **R-P3 trigger**: P4 touches `*.tsx` and `types.ts` (serialization barrier). `integration_owner:
> ui-engineer-enhanced`. Seam task: T4-003 (DTO field contract verification).
>
> **R-P4 trigger**: P4 touches `*.tsx` → authoritative runtime smoke is T5-003 in Phase 5
> (not in P4 itself). See AC DEF003-CHIP-SMOKE.

| Task ID | Task Name | Description | Acceptance Criteria | Est. | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|---------------------|------|-------------|-------|--------|--------------|
| T4-001 | Phase 1 reconciliation | Inspect shipped `PlanningTopBar.tsx` and `CommandCenterFeatureCard.tsx` against v1 plan `files_affected` list. Confirm DEF-003 chip is genuinely absent or incomplete. Record one-paragraph reconciliation note; any confirmed-shipped item is explicitly excluded from T4-002 scope. No Phase-1-shipped UI re-authored. | Reconciliation note written; confirmed-shipped items explicitly excluded; no Phase 1 UX re-authored in this phase | 0.5 pt | ui-engineer-enhanced | sonnet | adaptive | P1 complete |
| T4-002 | PlanningTopBar branch chip | Implement DEF-003 chip in `components/Planning/PlanningTopBar.tsx`. Reads `PlanningCommandCenterItemDTO.worktree?.branch` (optional chaining). Renders a secondary metadata chip when value is non-null and non-empty. Chip is hidden (not rendered, no error) when value is null/absent. Unit test: chip renders with `branch: 'feat/my-feature'`; chip absent with `worktree: undefined`. | Chip renders when `worktree.branch` non-null/non-empty; chip absent (no error) when field null/absent; unit test covers both states | 1.5 pt | ui-engineer-enhanced | sonnet | adaptive | T4-001 |
| T4-003 | Resilience + DTO seam verification _(R-P3 seam task)_ | Verify `PlanningCommandCenterItemDTO.worktree.branch` propagation contract from `types.ts` → `services/queries/planning.ts` hook → `PlanningTopBar`. Add resilience test: UI renders without crash when `worktree` field is entirely absent from DTO. Cross-reference with AC BRANCH-EMPTY-FALLBACK `PlanningTopBar.tsx` target surface. | Resilience test passes (no crash on absent `worktree`); `types.ts` type shape verified; optional chaining present; AC BRANCH-EMPTY-FALLBACK `PlanningTopBar.tsx` surface met | 0.5 pt | ui-engineer-enhanced | sonnet | adaptive | T4-002 |
| T4-004 | R-P4 smoke pointer task | Document that the authoritative runtime smoke for P4's `*.tsx` changes is T5-003 (Phase 5), per project rule ("runtime smoke gate"). Confirm `PlanningTopBar` and `CommandCenter` are the target surfaces for AC DEF003-CHIP-SMOKE. No `status: completed` on P4 or P5 without T5-003 smoke result. | T5-003 identified as R-P4 smoke owner; `PlanningTopBar.tsx` and `CommandCenter` documented as target surfaces | 0.5 pt | ui-engineer-enhanced | sonnet | adaptive | T4-003 |

**Phase 4 Exit Gate**:
- [ ] DEF-003 chip renders on `PlanningTopBar` when `worktree.branch` is non-null/non-empty (T4-002)
- [ ] Chip absent and no crash when `worktree` absent or `branch` null/empty (T4-002, T4-003)
- [ ] Resilience unit test passes (T4-003)
- [ ] No Phase-1-shipped UI re-authored; reconciliation note present (T4-001)
- [ ] AC BRANCH-EMPTY-FALLBACK `PlanningTopBar.tsx` surface verified (T4-003)
- [ ] T5-003 identified as R-P4 runtime smoke owner (T4-004)
- [ ] `task-completion-validator` passes

---

### Phase 5: Verification & Profiling

**Duration**: ~3 pts
**Dependencies**: P2 + P3 + P4 all complete
**Assigned Subagent(s)**: `python-backend-engineer` (profiling harness + integration), `karen` (milestone review)
**Reviewer**: `karen` (P5 milestone)

> **R-P4 runtime smoke**: T5-003 is the mandatory runtime smoke task for P4's `*.tsx`
> changes. Target surfaces: `PlanningTopBar.tsx` and `CommandCenter` components.
> Per project rule: if runtime unavailable, document `runtime_smoke: skipped` with
> reason; clean unit-test pass is NOT a substitute for marking P5 complete.

| Task ID | Task Name | Description | Acceptance Criteria | Est. | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|---------------------|------|-------------|-------|--------|--------------|
| T5-001 | Multi-watcher integration tests | `backend/tests/test_branch_watcher_integration.py`: (1) N=2 watchers register/unregister cleanly; (2) startup hydration with N=2 active `planning_worktree_contexts` rows registers both; (3) missing-path row at startup produces `WARNING` and no crash; (4) AC BWR-SEAM: INSERT triggers `register()`, terminal UPDATE triggers `unregister()`; (5) snapshot includes `branch_watchers` key with N=2 entries; correct `project_id`-keyed structure unchanged. | All 5 integration scenarios pass; snapshot contract confirmed | 1.5 pt | python-backend-engineer | sonnet | adaptive | P2, P3, P4 complete |
| T5-002 | Write-amplification profiling (OQ-5) | Profiling harness: simulate N=3, 4, 5 simultaneous `sync_changed_files` invocations via `asyncio.gather`; record p50/p95/p99 timings per N. Commit timing report to `.claude/worknotes/branch-aware-planning-intelligence/wamp-profiling-report-v2.md`. Record OQ-5 as resolved (N≤5 envelope confirmed) or flagged (if p95 degradation > 50ms vs baseline). This report is the Phase 3 gate input for any N=10+ scale-out. | Timing report committed with p50/p95/p99 data at N=3,4,5; OQ-5 recorded as resolved or flagged with evidence; `wamp-profiling-report-v2.md` path added to plan `related_documents` | 1 pt | python-backend-engineer | sonnet | adaptive | T5-001 |
| T5-003 | Runtime smoke check _(R-P4 mandatory)_ | Start dev stack (`npm run dev`). Navigate to planning command center with `CCDASH_PLANNING_CONTROL_PLANE_ENABLED=true` and ≥1 active `planning_worktree_contexts` row. Verify: (1) `PlanningTopBar` branch chip renders with non-null branch; (2) chip absent on feature with no registered worktree; (3) no console errors on navigation; (4) planning board loads without regression. If runtime unavailable: document `runtime_smoke: skipped` with reason in the phase progress file. | Smoke result documented (pass or skipped-with-reason); both chip states verified; AC DEF003-CHIP-SMOKE visual evidence criterion met (or skipped-with-reason) | 0.5 pt | python-backend-engineer | sonnet | adaptive | T5-001 |

**Phase 5 Exit Gate (karen milestone)**:
- [ ] Multi-watcher integration tests pass (N=2–3 scenarios, T5-001)
- [ ] Profiling report committed; OQ-5 recorded as resolved or flagged with data (T5-002)
- [ ] N≤5 envelope confirmed or flagged with evidence (T5-002)
- [ ] Runtime smoke completed or `runtime_smoke: skipped` with documented reason (T5-003)
- [ ] AC DEF003-CHIP-SMOKE verified (T5-003)
- [ ] `task-completion-validator` passes; `karen` milestone sign-off required

---

### Phase 6: Docs & Finalization

**Duration**: ~2 pts
**Dependencies**: P5 complete
**Assigned Subagent(s)**: `documentation-writer`, `changelog-generator`
**Reviewer**: `task-completion-validator` → `karen` (feature-end)

> **OQ-6 deferred tuning note** (decisions block §7): exact-match → `high` confidence
> promotion deferred to post-v2 tuning. Append as `open_questions` entry in T6-004.
> **OQ-7 operator docs** (decisions block §7): `--reload-exclude` guidance in T6-002.

| Task ID | Task Name | Description | Acceptance Criteria | Est. | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|---------------------|------|-------------|-------|--------|--------------|
| T6-001 | DOC-001 CHANGELOG entry | Add entry under `[Unreleased]` in `CHANGELOG.md` for Branch-Aware Planning Intelligence v2. Categories: `Added` (BranchWatcherRegistry, `_correlate_branch` S2 step, `documents.branch` column, `PlanningTopBar` branch chip, `branch_filter` cache dimension) + `Note` (N≤5 operational range; last-writer-wins Phase 2 limitation). Follow Keep A Changelog format per `.claude/specs/changelog-spec.md`. Set `changelog_ref: CHANGELOG.md` in plan frontmatter. | `[Unreleased]` entry present with correct categorization; `changelog_ref` set in plan frontmatter | 0.5 pt | changelog-generator | haiku | adaptive | P5 complete |
| T6-002 | DOC-003+DOC-004 Operator guidance + CLAUDE.md | (a) Update/create operator guidance covering: N≤5 branch watchers per project (supported operational range); uvicorn `--reload` hazard — OQ-7 resolution: `--reload-exclude` guidance (e.g., `--reload-exclude backend/db/branch_watcher.py`); SSE in-process-only constraint (extends Phase 1 AC-SSE-TOPOLOGY); worktree registration flow via planning control plane. (b) Update `CLAUDE.md` pointer: add ≤3-line note that `CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED` interacts with branch watcher events (full link rebuilds until incremental rebuild validated). | Operator guidance doc written/updated; `--reload-exclude` guidance present; SSE topology note updated; CLAUDE.md pointer updated ≤3 lines | 0.5 pt | documentation-writer | haiku | adaptive | P5 complete |
| T6-003 | Feature guide v2 | Create `.claude/worknotes/branch-aware-planning-intelligence/feature-guide-v2.md` with: (1) What Was Built (BranchWatcherRegistry, migration v34, `_correlate_branch`, branch chip, cache isolation); (2) Architecture Overview (key files, ADR references); (3) How to Test (register worktree via planning control plane, edit doc on branch, observe sync ≤5s); (4) Test Coverage Summary; (5) Known Limitations (N≤5 range, last-writer-wins, Codex null-branch). Under 200 lines total. | Feature guide committed under 200 lines; all 5 sections present; path added to plan `related_documents` | 0.5 pt | documentation-writer | haiku | adaptive | T6-001 |
| T6-004 | DOC-006 Deferred items spec refresh _(DOC-006 requirement)_ | (1) Refresh `docs/project_plans/design-specs/command-center-detail-panel-consolidation.md`: add Phase 2 context note (BranchWatcherRegistry now live; consolidation priority unchanged; trigger: spec promoted to `approved` maturity). (2) Append OQ-6 tuning note as `open_questions` entry in design spec or separate note: "exact-match `feat/<slug>` → `confidence=high` deferred to post-v2 tuning pending FP telemetry." (3) Promote `docs/project_plans/design-specs/branch-aware-phase2-multi-branch-watcher.md` to `maturity: promoted`. (4) Append both paths to `deferred_items_spec_refs` in this plan's frontmatter. | `command-center-detail-panel-consolidation.md` refreshed with Phase 2 context; OQ-6 tuning note appended; `branch-aware-phase2-multi-branch-watcher.md` `maturity: promoted`; `deferred_items_spec_refs` updated in plan frontmatter | 0.5 pt | documentation-writer | sonnet | adaptive | T6-003 |
| T6-005 | DOC-005 Plan + charter finalization | Set this plan `status: completed`; populate `commit_refs` and `files_affected`; set `updated: <date>`. Update charter Notes with Phase 2 completion reference. Confirm ADR-008 `status: accepted` final. Confirm all `deferred_items_spec_refs` are populated. | Plan `status: completed`; `commit_refs` populated; charter Notes updated; `deferred_items_spec_refs` fully populated; all deferred items have spec paths or N/A rationale | 0.5 pt | documentation-writer | haiku | adaptive | T6-004 |

**Phase 6 Exit Gate (karen feature-end)**:
- [ ] `CHANGELOG.md` `[Unreleased]` entry present with correct categorization (T6-001)
- [ ] Operator guidance includes N≤5 range + `--reload-exclude` (OQ-7) + SSE topology note (T6-002)
- [ ] CLAUDE.md pointer updated ≤3 lines for `CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED` interaction (T6-002)
- [ ] Feature guide v2 committed and under 200 lines (T6-003)
- [ ] `command-center-detail-panel-consolidation.md` refreshed; OQ-6 tuning note appended (T6-004)
- [ ] `branch-aware-phase2-multi-branch-watcher.md` `maturity: promoted` (T6-004)
- [ ] Plan `status: completed`; `deferred_items_spec_refs` fully populated (T6-005)
- [ ] All deferred items in triage table have spec paths or explicit N/A rationale
- [ ] `task-completion-validator` passes; `karen` feature-end sign-off required

---

## Wrap-Up: Feature Guide & PR

After all phase quality gates pass and `karen` feature-end sign-off is obtained:

**Feature Guide**: T6-003 authors `.claude/worknotes/branch-aware-planning-intelligence/feature-guide-v2.md`.

**Open PR**:
```bash
gh pr create \
  --title "feat(planning): Branch-Aware Planning Intelligence v2 — BranchWatcherRegistry & S2 Correlation" \
  --body "$(cat <<'EOF'
## Summary
- New BranchWatcherRegistry (backend/db/branch_watcher.py): per-worktree docs/progress watching (N≤5)
- DB migration v34: documents.branch column + idx_docs_project_branch + idx_sessions_git_branch_project
- S2 _correlate_branch step 5a: medium-confidence session↔feature linkage via git_branch tokens
- PlanningTopBar DEF-003 branch chip with resilience fallback (reads existing worktree.branch)
- branch_filter cache isolation on 4 @memoized_query planning endpoints (backward-compatible)
- ADR-007 retrofit on SqliteDocumentRepository.upsert; ADR-008 accepted

## Feature Guide
.claude/worknotes/branch-aware-planning-intelligence/feature-guide-v2.md

## Test plan
- [ ] All unit + integration tests pass
- [ ] Smoke-tested locally (CCDASH_PLANNING_CONTROL_PLANE_ENABLED=true, ≥1 active worktree)
- [ ] N≤5 write-amplification profiling report committed

🤖 Generated with Claude Code
EOF
)"
```

---

## Risk Mitigation Summary

| Risk | Severity | Phase Guard | Mitigation Task |
|------|----------|-------------|-----------------|
| ADR-007 violation compounds on branch write path | H | P0 exit gate | T0-001 through T0-004 |
| ADR-008 not accepted before registry implementation | H | P0 exit gate | T0-005 |
| Startup-sync ↔ watcher-registration race | M→H | P2 exit gate | T2-004 (OQ-3 serialization) |
| Codex null-branch silently degrades correlation/UI | H | P3 exit gate | T3-004 (OQ-4 disclosure AC) |
| Write amplification at N≥10 watchers | M | P5 exit gate | T5-002 (OQ-5 profiling) |
| Document identity collision (last-writer-wins) | M | P6 docs | T6-003 (known-limitations note) |
| Branch-correlation false positives | M | P3 exit gate | T3-001 (exclusion set + ≥8-char guard) |
| uvicorn `--reload` drops watcher registrations | M | P6 docs | T6-002 (OQ-7 `--reload-exclude` guidance) |
| Snapshot API contract break | L | P2 exit gate | T2-005 (parallel `branch_watchers` key only) |

---

**Progress Tracking:**

See `.claude/progress/branch-aware-planning-intelligence-v2/`
