---
schema_version: 2
doc_type: prd
title: "Branch-Aware Planning Intelligence v2 — PRD"
status: draft
created: '2026-06-11'
updated: '2026-06-11'
feature_slug: branch-aware-planning-intelligence
feature_version: v2
prd_ref: null
plan_ref: null
spike_ref: docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/r01-branch-watcher/r01-branch-watcher-brief.md
charter_ref: docs/project_plans/exploration/branch-aware-planning-intelligence/branch-aware-planning-intelligence-charter.md
changelog_ref: null
test_plan_ref: null
priority: high
risk_level: medium
category: enhancements
changelog_required: true
tier: 2
owner: null
contributors: []
tags:
  - prd
  - branch-watcher
  - multi-branch
  - session-correlation
  - infrastructure
  - phase-2
milestone: null
commit_refs: []
pr_refs: []
files_affected: []
related_documents:
  - docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/r01-branch-watcher/r01-branch-watcher-brief.md
  - docs/project_plans/exploration/branch-aware-planning-intelligence/branch-aware-planning-intelligence-charter.md
  - docs/project_plans/design-specs/branch-aware-phase2-multi-branch-watcher.md
  - docs/project_plans/PRDs/enhancements/branch-aware-planning-intelligence-v1.md
  - docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/r01-branch-watcher/watcher-arch-findings.md
  - docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/r01-branch-watcher/data-model-findings.md
  - docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/ux-value-findings.md
  - docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/risk-findings.md
adr_refs:
  - docs/project_plans/adrs/adr-006-db-authoritative-project-registry.md
  - docs/project_plans/adrs/adr-007-db-write-failure-surfacing-standard.md
  - docs/project_plans/adrs/adr-008-branch-watcher-registry-planning-service-seam.md  # PROPOSED — not yet accepted
references:
  user_docs: []
  context:
    - docs/guides/feature-surface-architecture.md
  specs: []
  related_prds:
    - docs/project_plans/PRDs/enhancements/branch-aware-planning-intelligence-v1.md
    - docs/project_plans/PRDs/enhancements/planning-agent-session-board-v1.md
    - docs/project_plans/PRDs/enhancements/multi-project-planning-command-center-v1.md
effort_estimate: "~21–27 pts"
---

# Feature Brief & Metadata

**Feature Name:**

> Branch-Aware Planning Intelligence v2 — Multi-Branch Watcher & S2 Correlation

**Filepath Name:**

> `branch-aware-planning-intelligence-v2`

**Date:**

> 2026-06-11

**Author:**

> Claude Opus (PRD Writer)

**Related Epic(s)/PRD ID(s):**

> Phase 1 PRD: `docs/project_plans/PRDs/enhancements/branch-aware-planning-intelligence-v1.md`
> R-01 Feasibility Brief: `docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/r01-branch-watcher/r01-branch-watcher-brief.md`
> Design Spec: `docs/project_plans/design-specs/branch-aware-phase2-multi-branch-watcher.md`

---

## 1. Executive Summary

Phase 1 (v1, approved) surfaced branch/session/commit data that already existed in the CCDash
database onto planning board items. Phase 2 closes the remaining infrastructure gap: operators
running concurrent git worktrees see no synced docs or correlation from non-active-checkout
branches. Phase 2 introduces a `BranchWatcherRegistry` that actively watches docs and progress
directories for each operator-registered worktree, a DB migration (v34) adding `branch` scoping
to the `documents` table, a branch-signal correlation step in `session_correlation.py`, and
branch-aware cache-key isolation on the four planning `@memoized_query` endpoints.

**Priority:** HIGH

**Key Outcomes:**
- Markdown docs (PRDs, progress files) on non-active-checkout branches are synced into CCDash in
  real time via per-worktree watchers, scoped exclusively to operator-registered
  `planning_worktree_contexts` rows (ADR-006 compliant).
- Session-to-feature correlation gains a `_correlate_branch` step (`medium` confidence), linking
  sessions whose `git_branch` encodes a feature slug token without requiring a new write table.
- Planning `@memoized_query` endpoints gain `branch_filter` cache isolation, backward-compatible
  when `branch_filter=None` (Phase 1 default).
- `PlanningTopBar` gains a branch chip reading the already-populated `worktree.branch` field
  (DEF-003, ~0.5–1 pt frontend-only).

---

## 2. Context & Background

### Current State

Phase 1 delivered active-session chips, `git_branch` chips on session board cards,
commitRefs/prRefs dialog, per-phase session links, and 15s refetch polling. The data substrate
was already in the DB; Phase 1 was pure display work.

Phase 2 picks up **DEF-001** from the Phase 1 implementation plan: the infrastructure required
to watch filesystem changes on non-active worktree paths and populate the `documents.branch`
column so planning queries can filter by branch. The `FileWatcherRegistry` binds to one checkout
path per `project_id`. Markdown docs being edited on a feature branch are invisible to CCDash
until that branch is checked out as the primary project path.

Three DEF items carry into Phase 2:
- **DEF-001** (design spec §1): `BranchWatcherRegistry` infrastructure.
- **DEF-003** (UX leg priority 4): `PlanningTopBar` branch chip — reads existing
  `worktree.branch`, no backend change required.
- **DEF-004** (data model leg, now resolved by design spec §6): `branch_filter` as a
  `param_extractor` cache-key dimension on the four planning endpoints.

### Problem Space

Operators running multi-worktree workflows (e.g., hotfix alongside an active feature branch)
today see planning items that are not correlated to sessions or docs from non-checked-out
worktrees. PRDs and progress files being edited on a feature branch are invisible until that
branch is checked out as the main project checkout. Session-to-feature correlation has no
branch-signal step, so sessions running on `feat/my-feature` contribute no correlation evidence
that links them to the corresponding planning item.

### Current Alternatives / Workarounds

Operators must manually check out a branch, trigger a sync, then switch back. There is no
in-app affordance for tracking doc changes across worktrees simultaneously.

### Architectural Context

Phase 2 follows the CCDash layered architecture:

- **`BranchWatcherRegistry`** (`Option A`, design spec §4.1): a new class parallel to
  `FileWatcherRegistry`, keyed by `(project_id, worktree_path)`, using existing `FileWatcher`
  instances internally. Registered in `backend/runtime/container.py` alongside
  `FileWatcherRegistry`. Lifecycle driven by `planning_worktree_contexts` row state transitions.
- **Sync entry point** (`backend/db/sync_engine.py`): unchanged — all branch watcher events call
  `sync_changed_files(project_id, ...)` with the parent `project_id`. No new sync codepath.
- **DB migration v34** (`backend/db/sqlite_migrations.py`): additive `_ensure_column` +
  `CREATE INDEX IF NOT EXISTS` guards per established pattern.
- **S2 correlation** (`backend/application/services/agent_queries/session_correlation.py`):
  `_correlate_branch` as step 5a after `_correlate_command_tokens`.
- **Cache** (`backend/application/services/agent_queries/cache.py`): `branch_filter` param
  dimension on four `@memoized_query` endpoints; no change to `_FINGERPRINT_TABLES`.
- **Frontend** (`components/Planning/PlanningTopBar.tsx`): DEF-003 chip reads
  `PlanningCommandCenterItemDTO.worktree?.branch` (already populated in Phase 1). No backend
  change required.

---

## 3. Problem Statement

> "As an operator running concurrent git worktrees, when I view the CCDash planning board,
> docs being edited on non-active-checkout branches are missing from planning items, and
> sessions running on `feat/my-feature` contribute no branch-based correlation evidence — so
> I lose real-time visibility into work happening on branches I haven't checked out."

**Technical root cause:**
- `FileWatcherRegistry` supports one watcher per `project_id`; non-active worktree paths are
  not watched.
- `documents` table has no `branch` column, so synced docs from a worktree cannot be
  branch-scoped for query filtering.
- `session_correlation.py` has no `_correlate_branch` step; `sessions.git_branch` is in the
  DB but not used as a correlation signal.
- The four `@memoized_query` planning endpoints have no `branch_filter` cache dimension, so
  branch-filtered queries are not currently supported without cache bypass.
- `SqliteDocumentRepository.upsert` calls bare `self.db.commit()` without `retry_on_locked`,
  violating ADR-007 §2 — a pre-existing violation that any new branch write path would inherit.

---

## 4. Goals & Success Metrics

### Primary Goals

**Goal 1: Active multi-worktree doc sync**
- Docs and progress files edited on operator-registered worktrees are synced into CCDash
  within one watcher debounce cycle (≤400ms + sync time) of the file change.
- Success: a doc edit on a non-active-checkout worktree path appears in CCDash planning
  queries within ≤5s of the edit under N≤5 concurrent watchers.

**Goal 2: Branch-signal session correlation**
- Sessions whose `git_branch` encodes a feature slug token are correlated to that feature
  at `medium` confidence via the `_correlate_branch` step.
- Success: correlation pipeline produces branch-evidence entries for ≥80% of sessions with
  a non-excluded, non-trivial `git_branch` value.

**Goal 3: Branch-aware cache isolation**
- Planning `@memoized_query` endpoints support `branch_filter` as a cache-key dimension
  without breaking Phase 1 callers (backward-compatible when `branch_filter=None`).
- Success: no cache regression for existing Phase 1 consumers; branch-filtered queries
  produce distinct cache slots with correct eviction via `aclear_project_cache`.

**Goal 4: ADR-007 compliance on document write path**
- `SqliteDocumentRepository.upsert` retrofitted with `retry_on_locked` before any branch
  write path ships; direct-count assertion test and Postgres parity both pass.

### Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Non-active worktree doc sync latency | N/A (not watched) | ≤5s under N≤3 concurrent events | Integration test + timing log |
| Branch-signal correlation coverage | 0% (step absent) | ≥80% of eligible sessions get branch evidence | Correlation pipeline unit test |
| Planning query regression (p95 response) | Baseline pre-v2 | No degradation >50ms | Backend profiling pre/post |
| ADR-007 compliance on documents.upsert | Violation | Passing | Lock-injection test + direct-count test |

---

## 5. User Personas & Journeys

### Personas

**Primary persona: Multi-worktree operator**
- Role: Developer running 2–4 parallel Claude Code sessions across feature branches and
  git worktrees (e.g., `feat/auth-v2` alongside main).
- Needs: Real-time sync of PRDs/progress files from non-active worktrees into the planning
  board; branch-signal session correlation without manual tagging.
- Pain points: Today, branch-checkout docs are invisible until they become the active path;
  correlation misses sessions whose branch names encode the feature slug.

**Secondary persona: Phase-investigator**
- Role: Developer auditing session contributions to a feature phase.
- Needs: Query by branch to filter the planning session board to a specific worktree's work.
- Pain points: No `branch_filter` param on planning board; all branches mixed.

### High-level Flow

```
Operator registers worktree via planning control plane launch flow
  → planning_worktree_contexts INSERT (status='running')
  → BranchWatcherRegistry.register(project_id, worktree_path, branch, feature_id, sync_engine)
  → FileWatcher starts on (worktree_path/docs_subdir, worktree_path/progress_subdir)

Agent edits PRD on feat/my-feature branch
  → watchfiles.awatch debounce (400ms)
  → sync_changed_files(project_id, ...)  [parent project_id — ADR-006 compliant]
  → SqliteDocumentRepository.upsert with branch='feat/my-feature'
  → aclear_project_cache(project_id)

Planning board query (branch_filter='feat/my-feature')
  → @memoized_query cache miss (distinct slot for branch_filter)
  → DB query filters documents(project_id, branch='feat/my-feature')
  → Response returned; cache populated

Session from feat/my-feature branch
  → _correlate_branch: normalize 'feat/my-feature' → 'my-feature'
  → min-length 8 ✓, exclusion set ✗
  → match against feature slug tokens → confidence='medium'
```

---

## 6. Requirements

### 6.1 Functional Requirements

| ID | Requirement | Priority | Notes |
|----|-------------|----------|-------|
| FR-P0-1 | `SqliteDocumentRepository.upsert` retrofitted with `retry_on_locked(self.db.commit, repo="documents")` per ADR-007 §2 | Must | Phase-0 gate; no branch write path ships without this |
| FR-P0-2 | Direct-count assertion test: after upsert, `SELECT COUNT(*) FROM documents WHERE project_id=? AND branch=?` returns expected count (ADR-007 §4) | Must | Phase-0 gate |
| FR-P0-3 | Lock-injection test: inject SQLITE_BUSY on first commit; assert retry succeeds (ADR-007 §5) | Must | Phase-0 gate |
| FR-P0-4 | Postgres `documents.py` applies `ON CONFLICT DO UPDATE SET branch = EXCLUDED.branch` for the branch column; Postgres direct-count test passes | Must | Phase-0 gate; ADR-007 Postgres parity |
| FR-P0-5 | Draft and accept proposed ADR-008 (`branch-watcher-registry-planning-service-seam.md`) recording: ownership (registry is runtime singleton), call-site contract (planning control plane write path only), interface contract (register on INSERT status=running, unregister on terminal UPDATE), lifecycle binding (stop_all on shutdown), and OQ-1 resolution (event mechanism) | Must | Phase-0 gate; blocks registry implementation |
| FR-DL-1 | DB migration v34: `ALTER TABLE documents ADD COLUMN branch TEXT DEFAULT ''` via `_ensure_column` helper; SQLite `CREATE INDEX IF NOT EXISTS idx_docs_project_branch ON documents(project_id, branch)` | Must | O(1) metadata-only SQLite |
| FR-DL-2 | DB migration v34: `CREATE INDEX IF NOT EXISTS idx_sessions_git_branch_project ON sessions(git_branch, project_id)` — index-only, no write path | Must | Zero ADR-007 cost |
| FR-DL-3 | Postgres parity for v34: mirror both DDL statements in `postgres_migrations.py` | Must | |
| FR-DL-4 | `branch_filter: str | None = None` added as `param_extractor` dimension on all four `@memoized_query` planning endpoints: `planning_project_summary`, `planning_project_graph`, `planning_feature_context`, `pss_session_board`. When `branch_filter=None`, cache key is identical to Phase 1 key (backward-compatible). | Must | Design spec §6, Option B |
| FR-BWR-1 | New `BranchWatcherRegistry` class (Option A, design spec §4.1) keyed by `(project_id, worktree_path: str)`. Holds `BranchWatcherEntry(watcher, worktree_path, branch, feature_id, docs_dir, progress_dir)`. `asyncio.Lock` on all mutating operations (P3-010 pattern). | Must | design spec §4.1 |
| FR-BWR-2 | `BranchWatcherRegistry.register(project_id, worktree_path, branch, feature_id, sync_engine)`: derives docs_dir and progress_dir from worktree_path; calls `sync_changed_files(project_id, ...)` with parent project_id (ADR-006 compliant). Sessions directories explicitly excluded from watch scope. | Must | ADR-006; design spec §4.2 |
| FR-BWR-3 | `BranchWatcherRegistry.unregister(project_id, worktree_path)`: stops and removes the watcher for the given key. | Must | |
| FR-BWR-4 | `BranchWatcherRegistry` registered in `backend/runtime/container.py` alongside `FileWatcherRegistry`. `stop_all()` called from `RuntimeJobAdapter.stop()`. | Must | design spec §3 |
| FR-BWR-5 | On server startup: load all active `planning_worktree_contexts` rows; call `register()` for each where `worktree_path` exists on disk; log warning and skip rows where path does not exist (see OQ-4). Startup registration serializes against `_run_all_projects_sync_job` (see OQ-3). | Must | design spec §4.2 |
| FR-BWR-6 | Snapshot extension: `_watcher_registry_snapshot()` output gains a parallel `branch_watchers` key (not composite keys in existing dict[project_id, dict] — preserves existing snapshot contract). | Must | design spec §4.1 |
| FR-BWR-7 | `BranchWatcherRegistry.register()` / `unregister()` may only be called from the planning control plane write path. No other service layer may call `BranchWatcherRegistry` directly. Code-review gate + linting comment at call site. | Must | ADR-008 |
| FR-BWR-8 | Binding source is exclusively `planning_worktree_contexts` rows. `git worktree list` auto-discovery is acceptable only as a one-time aid at operator worktree-registration time (UI helper), never as the runtime path-discovery mechanism. | Must | ADR-006 |
| FR-S2-1 | `_correlate_branch(session, feature_index)` added as step 5a in `session_correlation.py:correlate_session`, after `_correlate_command_tokens`. | Must | design spec §4.4 |
| FR-S2-2 | `_BRANCH_EXCLUSION_SET` (frozenset, module-level constant) and `_BRANCH_PREFIXES` / `_normalize_branch_for_correlation` collocated with `_correlate_command_tokens` per established extension pattern. | Must | data-model findings §RQ6 |
| FR-S2-3 | Codex null-branch early-exit: `_correlate_branch` returns `[]` immediately when `session.get("git_branch")` is None. No branch-filter logic gates planning behavior on branch presence. | Must | Charter disclosure constraint (d); design spec §4.4 |
| FR-S2-4 | Minimum-length guard: normalized branch slug < 8 characters returns `[]`. Confidence assignment: `medium` (same as `_correlate_command_tokens`). `high` confidence is reserved for explicit `entity_links`. | Must | data-model findings §RQ6 |
| FR-FE-1 | `PlanningTopBar` branch chip (DEF-003): reads `PlanningCommandCenterItemDTO.worktree?.branch` (already populated in Phase 1). Renders as a secondary metadata chip in the top bar when non-null. No backend changes required. | Should | ~0.5–1 pt; design spec §5 |
| FR-FE-2 | When `documents.branch` is empty string or null (default for pre-v34 rows), UI/query behavior: `branch_filter=None` (omitted) returns all documents across all branches (Phase 1 default, unchanged). UI must not crash or show error when `branch` field is absent from a document record. | Must | Resilience-by-default |

### 6.2 Non-Functional Requirements

**Performance and operational range:**
- Supported operational range: **N≤5 branch watchers per project**. N=10+ requires
  write-amplification profiling (OQ-5) before any Phase 3 scale-out. Profiling is a
  verification task, not a Phase 2 blocker.
- Startup registration of N≤5 active worktrees adds ≤5s additional startup cost with
  `CCDASH_STARTUP_SYNC_LIGHT_MODE=false`; light-mode path is safe (manifest is path-keyed,
  no collision with branch worktree paths).
- N=3 simultaneous watcher events: worst-case ~1–4.5s lock contention window;
  `busy_timeout=30000ms` provides headroom. All branch watcher syncs funnel through the
  shared `sync_engine` singleton.
- `CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED`: currently OFF by default. Branch watcher events
  will trigger full link rebuilds until incremental rebuild is validated. Not a Phase 2 blocker.

**Resilience (mandatory per project rule):**
- **AC-BRANCH-EMPTY-FALLBACK**: when `documents.branch` is `''` (default) or null, all
  planning queries with `branch_filter=None` behave identically to Phase 1 (no regression).
  The frontend must not render an error or blank state when the `branch` field is absent from
  a document record; treat missing as `''` (no branch scoping).
- **AC-NULLBRANCH-CODEX-V2**: Codex sessions hardcode `git_branch=NULL`
  (`parsers/platforms/codex/parser.py:1244`). `_correlate_branch` must return `[]` for these
  sessions. The UI must not hide this structural null or treat it as a data-quality error.
  This constraint carries forward from Phase 1 AC-NULLBRANCH-1.

**Charter disclosure constraints (non-functional ACs):**
- **(a) cwd lives in a JSON blob**: `session_forensics_json.workingDirectories` is not a
  direct DB column. No Phase 2 story may use cwd for branch inference, worktree matching,
  or filterable queries without a `_ensure_column` migration as a prerequisite task.
- **(b) Operator-gated worktree contexts**: `planning_worktree_contexts` is operator-populated
  via the planning control plane launch flow. No silent auto-registration of worktrees at
  runtime. `git worktree list` is only acceptable as a one-time UI registration aid.
- **(c) SSE/live-update in-process-only under SQLite**: live planning board updates from
  branch-watcher-triggered syncs are in-memory-bus only. Under SQLite with worker and API
  as separate processes, cross-process fanout is not guaranteed. Must be documented at call
  sites and in operator guide (extends Phase 1 AC-SSE-TOPOLOGY).
- **(d) Codex structural null-branch**: Codex sessions always have `git_branch=NULL`. No
  branch-filter or correlation logic may assume branch presence for Codex sessions.

**ADR compliance:**
- ADR-006: Watcher binds exclusively to paths in `planning_worktree_contexts`; parent
  `project_id` used in all `sync_engine` calls. No composite project IDs.
- ADR-007: Every new write path uses `retry_on_locked`; direct-count assertion test required.
  Each new independent SQLite connection (if any) must issue `PRAGMA busy_timeout = 30000`.

**Observability:**
- New backend query methods in `agent_queries/` include OpenTelemetry spans consistent with
  existing planning query instrumentation.
- Branch-signal correlation evidence entries include branch slug and normalized slug in
  structured log output.

---

## 7. Scope

### In Scope (Phase 2, ~21–27 pts)

- **Phase 0 (~4 pts)**: ADR-007 retrofit of `SqliteDocumentRepository.upsert`; direct-count
  and lock-injection tests; Postgres parity. Draft, review, and accept proposed ADR-008
  (`branch-watcher-registry-planning-service-seam.md`); record OQ-1 resolution.
- **Data layer (~4 pts)**: DB migration v34 (`documents.branch` column + covering index +
  `sessions(git_branch, project_id)` index); Postgres v34 parity; `branch_filter`
  `param_extractor` dimension on four `@memoized_query` planning endpoints.
- **`BranchWatcherRegistry` infra (~5 pts)**: new class, container registration, startup
  lifecycle (load active rows, register, serialize against startup sync), snapshot extension
  (`branch_watchers` key), `stop_all` on shutdown, call-site linting comment.
- **S2 correlation (~3 pts)**: `_correlate_branch` step 5a in `session_correlation.py`;
  exclusion set; prefix normalization; min-length guard; Codex null-branch early-exit.
- **Frontend DEF-003 (~1 pt)**: `PlanningTopBar` active branch chip reading existing
  `worktree.branch` data; resilience fallback when field is missing.
- **Verification (~3 pts)**: integration tests (watcher lifecycle, ADR-007 direct-count,
  lock-injection, correlation pipeline, cache isolation); N≤5 write-amplification profiling
  task (timing report for `sync_changed_files` under N=3–5 simultaneous events; OQ-5
  resolution data for Phase 3).
- **Docs (~1 pt)**: CHANGELOG entry; operator guidance update (N≤5 operational range,
  uvicorn `--reload` hazard, SSE topology for branch-watcher syncs, `--reload-exclude`
  guidance for OQ-7).

### Out of Scope

- **Phase 3 / full per-worktree document isolation**: composite PK including `branch` on
  `documents`; full `session_branch_links` join table; N=10+ scale-out.
- **Auto-discovery of worktrees via `git worktree list` as a runtime binding path**: allowed
  only as a UI registration aid (one-time helper at worktree-registration time).
- **cwd-based branch inference** from `session_forensics_json`: not a direct DB column;
  requires a migration as a prerequisite. Not in Phase 2 scope.
- **Command-center detail-panel consolidation** (DEF-002): full `CommandCenterDetailPanel`
  replacement with the board modal (`docs/project_plans/design-specs/command-center-detail-panel-consolidation.md`)
  is deferred. Out of scope for v2.
- **OQ-6 tuning (exact-match high-confidence promotion)**: whether `feat/my-feature-slug`
  matching exact feature ID should auto-promote to `confidence=high` is deferred to post-ship
  tuning. Phase 2 ships uniform `medium` confidence for all branch-signal correlations.
- **Remote GitHub/GitLab API integration**, non-git VCS support, Postgres NOTIFY new topics.
- **UX stories carried into Phase 1** (S-ACT, S1, S3, S4): active-session chips, per-phase
  session links, branch/commit click-dialog. These shipped in Phase 1 and are NOT re-scoped.

---

## 8. Dependencies & Assumptions

### Internal Dependencies

- **Phase 1 (shipped)**: `PlanningAgentSessionCardDTO.git_branch`, `PlanningCommandCenterItemDTO.worktree`,
  Phase 1 null-branch ACs (AC-NULLBRANCH-1/2). Phase 2 assumes these are in production.
- **`planning_worktree_contexts` table** (pre-existing): operator-populated source of truth
  for worktree registration; required for `BranchWatcherRegistry.register()`.
- **`FileWatcher` / `FileWatcherRegistry`** (`backend/db/file_watcher.py`): Phase 2 reuses
  `FileWatcher.start()` unchanged in each `BranchWatcherEntry`. No modification to
  `FileWatcher` is required.
- **`sync_engine.sync_changed_files()`** (`backend/db/sync_engine.py`): shared sync entry
  point for all branch watcher events. No new sync codepath introduced.
- **`RuntimeJobAdapter`** (`backend/adapters/jobs/`): Phase 2 adds `stop_all()` call for
  `BranchWatcherRegistry` alongside `FileWatcherRegistry`.
- **`retry_on_locked`** (`backend/db/repositories/base.py`): must be confirmed present and
  correct before Phase 0 retrofit ships.
- **`@memoized_query` / `aclear_project_cache`** (`backend/application/services/agent_queries/cache.py`):
  Phase 2 adds `branch_filter` as a param_extractor dimension. Event-driven eviction via
  `aclear_project_cache(project_id)` already in place post-sync (no changes needed).
- **`session_correlation.py`**: `_correlate_command_tokens` is the insertion point for the
  new `_correlate_branch` step 5a. Extension pattern already established.
- **Proposed ADR-008** (`docs/project_plans/adrs/adr-008-branch-watcher-registry-planning-service-seam.md`):
  **does not exist yet**. Drafting and accepting it is a Phase-0 plan task. Must be accepted
  before `BranchWatcherRegistry` implementation begins.

### Assumptions

- Phase 1 ACs (including AC-NULLBRANCH-1/2 and AC-SSE-TOPOLOGY) are confirmed shipped.
- `planning_worktree_contexts` is populated by operators via the planning control plane launch
  flow; operators who do not use the launch flow will see no branch-watcher registrations.
- Codex sessions will always have `git_branch = NULL` (hardcoded, structural constraint).
- `documents.branch = ''` (empty string default) for all pre-v34 rows is not a data error;
  queries and UI treat it as "no branch scoping."
- `busy_timeout=30000ms` is already set on the singleton async connection; branch watcher
  syncs inherit this without additional configuration.
- OQ-4 (worktree_path not on disk at startup): default behavior is log warning + skip. No
  automatic status update to terminal status unless explicitly gated by operator input.
  This assumption is recorded as a decision required during Phase 0 ADR-008 authoring.

### Feature Flags

- `CCDASH_PLANNING_CONTROL_PLANE_ENABLED` (existing, parent gate): gates the planning
  control plane launch flow that populates `planning_worktree_contexts`. No new flags for
  Phase 2 unless OQ-2 (module placement) drives a toggle during development.
- `CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED` (existing, default OFF): branch watcher events
  fall back to full link rebuilds. Phase 2 does not change this default.

---

## 9. Data Contracts

### BranchWatcherRegistry / Planning-Service Seam (Proposed ADR-008)

**Status: PROPOSED** — ADR-008 does not exist. It must be drafted and accepted as a Phase-0
task before registry implementation begins.

**What ADR-008 must specify:**

| Contract element | Specified value |
|---|---|
| Ownership | `BranchWatcherRegistry` is a runtime-infrastructure singleton, registered in `container.py` — NOT a service-layer component |
| Call-site constraint | `register()` / `unregister()` called **only** from the planning control plane write path (`planning_worktree_contexts` INSERT/UPDATE). No other service layer may call these methods directly. Code-review gate + linting comment at call site. |
| `register()` trigger | `planning_worktree_contexts` INSERT with `status='running'` |
| `unregister()` trigger | `planning_worktree_contexts` UPDATE to terminal status (`'completed'`, `'cancelled'`, `'failed'`) |
| Startup population | Load all active rows; call `register()` for each with existing path; skip + warn for paths not on disk |
| Lifecycle binding | `BranchWatcherRegistry.stop_all()` called from `RuntimeJobAdapter.stop()` alongside `FileWatcherRegistry.stop_all()` |

**OQ-1 (primary blocking question for ADR-008)**: What event mechanism drives
`planning_worktree_contexts` INSERT/UPDATE notifications to `BranchWatcherRegistry`? Is there
an existing event bus, or does the registry need to be called directly from the planning
control plane write path (service-layer coupling)? This is the key architectural decision
ADR-008 must record. ADR-008 must choose between:
- **Direct-call model**: simpler, but introduces a hard cross-layer import from planning
  service to watcher infrastructure.
- **Event-bus model**: cleaner separation, but requires an existing bus or a new one.

**OQ-3 (startup sync serialization)**: `BranchWatcherRegistry` startup registration must
serialize against `_run_all_projects_sync_job` to avoid races. ADR-008 or the Phase 2
implementation plan must specify whether serialization is achieved by wiring registration
into `_run_all_projects_sync_job` or by a separate startup coroutine triggered after project
sync completes.

### Cache Key Extension (DEF-004, resolved)

`branch_filter: str | None = None` is added as a `param_extractor` dimension on four endpoints:

```python
@memoized_query(
    "pss_session_board",
    param_extractor=lambda self, ctx, ports, *, project_id=None, feature_id=None,
        grouping="state", cursor=None, limit=500, branch_filter=None: {
        "project_id": project_id,
        "feature_id": feature_id,
        "grouping": grouping,
        "branch_filter": branch_filter,   # new dimension
        "cursor": cursor,
        "limit": limit,
    },
)
```

When `branch_filter=None`, the cache key is identical to the Phase 1 key — fully
backward-compatible. `aclear_project_cache(project_id)` already evicts by project_id prefix
match; no changes to `_FINGERPRINT_TABLES` required.

---

## 10. Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| ADR-007 violation in `SqliteDocumentRepository.upsert` inherits into branch write path | High | Certain (without Phase 0) | Phase-0 prerequisite gate: retrofit ships in same PR as `documents.branch` write path |
| Codex structural `git_branch=NULL` breaks branch correlation/filter | High | Certain | `_correlate_branch` early-exit on `None`; UI treats null as first-class state per Phase 1 ACs |
| Document identity collision (same-path docs across worktrees, last-writer-wins) | Medium | Medium (shared doc paths) | Accepted Phase 2 known limitation; documented for operators; Phase 3 scope for composite PK |
| Write amplification at N=10+ branch watchers | Medium | Low (N≤5 operational range enforced) | Enforce N≤5 as supported operational range; profiling task in verification phase gates Phase 3 |
| uvicorn `--reload` drops all watcher registrations | Medium | High (dev mode) | Accepted dev-mode limitation (same hazard as primary watcher); production unaffected; document `--reload-exclude` guidance (OQ-7) |
| ADR-008 not yet accepted — blocks registry implementation | High | Certain (without Phase 0) | Phase-0 task: draft and accept ADR-008 before any registry code ships |
| OQ-1 (event mechanism) unresolved — may require event-bus work | Medium | Medium | Record resolution in ADR-008 before implementation; direct-call is acceptable interim if no bus exists |
| Branch correlation FP rate (subjective <5% estimate, unvalidated) | Medium | Medium | Enforce 8-char minimum + exclusion set; add telemetry hook post-ship; make exclusion set configurable via env var |
| Cross-layer dependency: planning service → BranchWatcherRegistry | Medium | Medium | ADR-008 acceptance + code-review gate enforces call-site constraint |
| Snapshot API contract break if composite keys used | Low | Low | Use parallel `branch_watchers` key in snapshot output; do not composite-key the existing dict[project_id] structure |
| Postgres parity gap on v34 migration | Medium | Low | Treat Postgres parity as co-equal deliverable; Postgres direct-count assertion test per ADR-007 |

---

## 11. Target State (Post-Implementation)

**User experience:**
- Docs and progress files edited on any operator-registered worktree path appear in CCDash
  planning queries within seconds of the file change, without requiring a branch checkout.
- Session-to-feature correlation on the planning session board shows branch-signal evidence
  for sessions running on feature-named branches (e.g., `feat/auth-v2 → auth-v2 → medium`).
- The `PlanningTopBar` shows the active branch chip for features with registered worktrees,
  giving operators a top-level branch context signal without opening the detail panel.
- Planning board queries support optional `branch_filter` to scope results to a specific branch,
  with a distinct cache slot per filter value and correct eviction on sync.

**Technical architecture:**
- `BranchWatcherRegistry` runs as a runtime singleton alongside `FileWatcherRegistry`,
  holding one `FileWatcher` per active `planning_worktree_contexts` row. It watches only
  `docs_dir` and `progress_dir` from each worktree path — sessions directories are excluded.
- All branch watcher syncs call `sync_changed_files(project_id, ...)` with the parent
  `project_id`, maintaining ADR-006 compliance. No new project registry entries are created.
- `documents.branch` (default `''`) allows branch-scoped document queries while preserving
  last-writer-wins semantics for same-path docs across worktrees (accepted Phase 2 limitation).
- `session_correlation.py` step 5a (`_correlate_branch`) links sessions to features via
  branch-name token matching at `medium` confidence, with Codex null-branch early-exit.

**Observable outcomes:**
- Zero "plan docs not visible" reports for operator-registered worktrees under N≤5.
- N≤5 write-amplification profiling report available as Phase 3 gate input (OQ-5 resolved).
- ADR-007 compliance on document write path: lock-injection test passes; direct-count test passes.

---

## 12. Overall Acceptance Criteria (Definition of Done)

### Phase 0: ADR-007 Retrofit + ADR-008

- [ ] **AC-P0-ADR007**: `SqliteDocumentRepository.upsert` uses `retry_on_locked(self.db.commit, repo="documents")`. Direct-count assertion test passes. Lock-injection test passes. Postgres `ON CONFLICT DO UPDATE SET branch = EXCLUDED.branch` applied.
- [ ] **AC-P0-ADR008**: ADR-008 (`branch-watcher-registry-planning-service-seam.md`) drafted, reviewed, and status set to `accepted`. OQ-1 (event mechanism) resolution recorded. OQ-3 (startup sync serialization path) specified.

### Data Layer

- [ ] **AC-DL-MIGRATION**: `documents.branch TEXT DEFAULT ''` column present after v34 migration (`_ensure_column`); `idx_docs_project_branch` index created; `idx_sessions_git_branch_project` index created. All use `IF NOT EXISTS` / `_ensure_column` guards. Postgres parity migration lands in same PR.
- [ ] **AC-DL-CACHE**: `branch_filter=None` produces no change to existing cache key on all four `@memoized_query` planning endpoints (regression test passes). `branch_filter='feat/x'` produces a distinct cache slot. `aclear_project_cache(project_id)` correctly evicts branch-filtered slots.
- [ ] **AC-BRANCH-EMPTY-FALLBACK**: When `documents.branch` is `''` or null, all planning queries with `branch_filter=None` return identical results to Phase 1. Frontend renders no error or blank state when `branch` field is absent from a document record.

### BranchWatcherRegistry

- [ ] **AC-BWR-REGISTER**: `BranchWatcherRegistry.register()` starts a `FileWatcher` on `(docs_dir, progress_dir)` derived from `worktree_path`. Sessions directory is NOT in watch scope. `sync_changed_files(project_id, ...)` is called with the parent `project_id`.
- [ ] **AC-BWR-LIFECYCLE**: On server startup, all active `planning_worktree_contexts` rows with existing paths are registered. Rows with missing paths produce a warning log and are skipped (no crash). `stop_all()` is called on server shutdown alongside `FileWatcherRegistry.stop_all()`.
- [ ] **AC-BWR-CALLSITE**: `register()` / `unregister()` are called only from the planning control plane write path. A linting comment is present at the call site. Integration test confirms a `planning_worktree_contexts` INSERT triggers register and an UPDATE to terminal status triggers unregister.
- [ ] **AC-BWR-SNAPSHOT**: `_watcher_registry_snapshot()` output includes a `branch_watchers` key without breaking the existing `dict[project_id, dict]` structure. Snapshot contract test passes.
- [ ] **AC-BWR-ADR006**: `sync_engine.sync_changed_files()` is invoked with the parent `project_id` (not a per-branch ID) for all branch watcher events. No new project registry entries are created.

### S2 Correlation

- [ ] **AC-S2-STEP**: `_correlate_branch` is present as step 5a in `session_correlation.py:correlate_session`, after `_correlate_command_tokens`. Exclusion set, prefix normalization, and min-length guard are module-level constants collocated with `_correlate_command_tokens`.
- [ ] **AC-S2-CODEX**: `_correlate_branch` returns `[]` immediately when `session.get("git_branch")` is `None`. Integration test confirms Codex session produces no branch correlation evidence. Planning behavior is not gated on branch presence.
- [ ] **AC-S2-CONFIDENCE**: Branch-signal evidence entries have `confidence='medium'`. No branch-signal evidence is assigned `confidence='high'` (reserved for `entity_links`).
- [ ] **AC-S2-MINLENGTH**: A branch slug of fewer than 8 characters (after prefix normalization) produces no correlation evidence. A slug of ≥8 characters not in the exclusion set and matching a feature slug token produces a `medium` evidence entry.

### Frontend DEF-003

- [ ] **AC-DEF003-CHIP**: `PlanningTopBar` renders a branch chip when `PlanningCommandCenterItemDTO.worktree?.branch` is non-null and non-empty. Chip is not rendered when field is null/absent (no error thrown). Unit test for both states.
- [ ] **AC-DEF003-MISSING**: Frontend handles missing `worktree` field on `PlanningCommandCenterItemDTO` gracefully (field absent = chip hidden; no crash, no blank page).

### Verification

- [ ] **AC-VERIFY-PROFILE**: Write-amplification profiling task completes: timing data for `sync_changed_files` under N=3–5 simultaneous watcher events is recorded and committed to `.claude/worknotes/branch-aware-planning-intelligence/` as a verification note. OQ-5 is recorded as resolved-or-deferred with evidence.
- [ ] **AC-VERIFY-N5**: Operator guidance documents N≤5 as the supported operational range. N=10+ is documented as requiring profiling before Phase 3 scale-out.
- [ ] **AC-VERIFY-SMOKE**: Runtime smoke check performed on the planning command center with `CCDASH_PLANNING_CONTROL_PLANE_ENABLED=true` and at least one active `planning_worktree_contexts` row before marking Phase 2 complete.

### Docs & Changelog

- [ ] `CHANGELOG.md` entry added for Branch-Aware Planning Intelligence v2.
- [ ] Operator guidance updated: N≤5 operational range, uvicorn `--reload` hazard for branch watchers, `--reload-exclude` guidance (OQ-7), SSE in-process-only constraint (extends Phase 1 AC-SSE-TOPOLOGY).
- [ ] `CLAUDE.md` pointer updated: `CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED` note updated to reference branch watcher interaction.

---

## 13. Assumptions & Open Questions

### Assumptions

- Phase 1 AC-NULLBRANCH-1/2 and AC-SSE-TOPOLOGY are confirmed shipped in production.
- `planning_worktree_contexts` is the sole runtime binding source for worktree paths.
- `documents.branch = ''` is a valid "no branch" sentinel (not NULL) per migration default.
- `busy_timeout=30000ms` is already set on the singleton async connection (confirmed in
  `connection.py` line 52); no new connection configuration required for Phase 2.
- OQ-4 resolution: missing `worktree_path` on disk at startup → log warning + skip (no
  automatic terminal status update). This is a pragmatic default; ADR-008 may refine it.

### Open Questions

- [ ] **OQ-1 (blocking)**: What event mechanism drives `planning_worktree_contexts` INSERT/UPDATE
  notifications to `BranchWatcherRegistry`? Direct-call vs. event-bus? **Must be resolved
  in ADR-008 before registry implementation.**
  - **A**: TBD — resolved in Phase-0 ADR-008 authoring.
- [ ] **OQ-2**: Should `BranchWatcherRegistry` live in `backend/db/file_watcher.py` (alongside
  `FileWatcherRegistry`) or a new `backend/db/branch_watcher.py`?
  - **A**: TBD — resolved during Phase-0 or early implementation planning. Both options are
    feasible; import-graph and test-isolation implications determine the choice.
- [ ] **OQ-3 (blocking)**: What is the startup sync serialization path — wired into
  `_run_all_projects_sync_job` or a separate startup coroutine after project sync completes?
  **Must be specified in ADR-008 or implementation plan before BWR implementation.**
  - **A**: TBD — resolved in Phase-0 ADR-008 authoring.
- [ ] **OQ-4**: When `worktree_path` does not exist on disk at startup, should the registry
  log a warning and skip, or update the `planning_worktree_contexts` row to terminal status?
  - **A**: Default: log warning + skip. ADR-008 may refine. Do not silently transition to
    terminal status without operator input in Phase 2.
- [ ] **OQ-5**: What are the actual measured timings for `sync_changed_files` under N=3–5
  simultaneous watcher events? (Verification task, not a Phase 2 blocker.)
  - **A**: TBD — profiling output from verification phase.
- [ ] **OQ-6 (deferred)**: Should exact feature-ID branch slug matches be auto-promoted to
  `confidence='high'`? Deferred to post-ship tuning. Phase 2 ships uniform `medium`.
  - **A**: Deferred.
- [ ] **OQ-7**: What `--reload-exclude` configuration is recommended for dev mode to partially
  mitigate the uvicorn reload hazard for branch watchers?
  - **A**: TBD — resolved in operator docs during verification phase.

---

## 14. Deferred Items

| Item | Blocked on | Phase target | Notes |
|------|-----------|--------------|-------|
| Full per-worktree document isolation (composite PK on `documents` including `branch`) | Phase 3 scope | Phase 3 | Last-writer-wins collision is accepted Phase 2 limitation |
| `session_branch_links` join table | Phase 3 if multi-branch attribution needed | Phase 3+ | Index on `sessions(git_branch, project_id)` is sufficient for Phase 2 |
| N=10+ branch watcher scale-out | OQ-5 profiling data | Phase 3 | Enforcing N≤5 operational range for Phase 2 |
| OQ-6: exact-match high-confidence promotion | Post-ship telemetry data | Post-Phase 2 tuning | Phase 2 ships uniform `medium` confidence |
| `CommandCenterDetailPanel` full consolidation with board modal | `docs/project_plans/design-specs/command-center-detail-panel-consolidation.md` | Post-Phase 2 | Out of scope for v2; Phase 1 "Open full detail" bridge affordance is the interim |
| cwd/workingDirectories branch inference | `_ensure_column` migration prerequisite | Phase 3+ | Not a direct DB column; any use requires migration first (charter disclosure constraint a) |
| Postgres NOTIFY cross-process branch-event topic | No new engineering required | Operator docs | Pre-existing constraint; document alongside AC-SSE-TOPOLOGY |

---

## 15. Appendices & References

### Key Files

| Concern | File |
|---------|------|
| Document repository (Phase-0 retrofit target) | `backend/db/repositories/documents.py` |
| Session correlation (S2 extension point) | `backend/application/services/agent_queries/session_correlation.py` |
| File watcher / registry (Phase 2 BWR parallel) | `backend/db/file_watcher.py` |
| Sync engine (shared entry point) | `backend/db/sync_engine.py` |
| DB migrations | `backend/db/sqlite_migrations.py` |
| Query cache / memoized_query | `backend/application/services/agent_queries/cache.py` |
| Planning session board queries | `backend/application/services/agent_queries/planning_sessions.py` |
| Planning command center queries | `backend/application/services/agent_queries/planning_command_center.py` |
| Container registration | `backend/runtime/container.py` |
| RuntimeJobAdapter | `backend/adapters/jobs/` |
| Frontend planning hooks | `services/queries/planning.ts` |
| PlanningTopBar (DEF-003 target) | `components/Planning/PlanningTopBar.tsx` |
| Frontend type definitions | `types.ts` |
| retry_on_locked | `backend/db/repositories/base.py` |
| planning_worktree_contexts source of truth | `backend/db/sqlite_migrations.py` (migration ~line 1247) |

### Related Documentation

- **Design spec (primary)**: `docs/project_plans/design-specs/branch-aware-phase2-multi-branch-watcher.md`
- **R-01 feasibility brief**: `docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/r01-branch-watcher/r01-branch-watcher-brief.md`
- **Watcher arch findings**: `docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/r01-branch-watcher/watcher-arch-findings.md`
- **Data model findings**: `docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/r01-branch-watcher/data-model-findings.md`
- **UX value findings**: `docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/ux-value-findings.md`
- **Risk findings**: `docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/risk-findings.md`
- **Phase 1 PRD (anchor)**: `docs/project_plans/PRDs/enhancements/branch-aware-planning-intelligence-v1.md`
- **Exploration charter**: `docs/project_plans/exploration/branch-aware-planning-intelligence/branch-aware-planning-intelligence-charter.md`
- **ADR-006**: `docs/project_plans/adrs/adr-006-db-authoritative-project-registry.md`
- **ADR-007**: `docs/project_plans/adrs/adr-007-db-write-failure-surfacing-standard.md`
- **Proposed ADR-008**: `docs/project_plans/adrs/adr-008-branch-watcher-registry-planning-service-seam.md` (does not yet exist; Phase-0 task)
- **Feature surface architecture**: `docs/guides/feature-surface-architecture.md`
- **CommandCenterDetailPanel consolidation** (deferred/related): `docs/project_plans/design-specs/command-center-detail-panel-consolidation.md`

---

**Progress Tracking:**

See progress tracking: `.claude/progress/branch-aware-planning-intelligence-v2/`
