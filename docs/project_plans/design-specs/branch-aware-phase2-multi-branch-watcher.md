---
schema_version: 2
doc_type: design_spec
title: "Phase 2 Multi-Branch Watcher — BranchWatcherRegistry & S2 Branch-Signal Correlation"
status: draft
maturity: shaping
created: 2026-06-04
updated: 2026-06-04
feature_slug: branch-aware-planning-intelligence
feature_version: v2
prd_ref: docs/project_plans/PRDs/enhancements/branch-aware-planning-intelligence-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/branch-aware-planning-intelligence-v1.md
spike_ref: docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/r01-branch-watcher/r01-branch-watcher-brief.md
adr_refs:
- docs/project_plans/adrs/adr-006-db-authoritative-project-registry.md
- docs/project_plans/adrs/adr-007-db-write-failure-surfacing-standard.md
- docs/project_plans/adrs/adr-008-branch-watcher-registry-planning-service-seam.md
related_documents:
- docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/r01-branch-watcher/watcher-arch-findings.md
- docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/r01-branch-watcher/data-model-findings.md
- docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/risk-findings.md
- docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/tech-findings.md
priority: high
risk_level: medium
category: backend-infrastructure
tags:
- branch-watcher
- multi-branch
- session-correlation
- file-watcher
- planning
- phase-2
- deferred
effort_estimate: ~20–27 pts
problem_statement: >
  Phase 1 of Branch-Aware Planning Intelligence surfaces branch and session data that
  already exists in the DB. Phase 2 requires active filesystem watching of multiple
  concurrent worktree checkouts so that markdown docs (PRDs, progress files) on
  non-active-checkout branches are synced and correlated with planning items in real
  time. This requires a new BranchWatcherRegistry abstraction, a DB migration, an
  ADR-007 retrofit of SqliteDocumentRepository.upsert, and a branch-signal correlation
  step in session_correlation.py.
open_questions:
- "OQ-1 [UNRESOLVED]: What event mechanism drives planning_worktree_contexts INSERT/UPDATE
  notifications to BranchWatcherRegistry? Is there an existing event bus, or does the
  registry need to be called directly from the planning control plane write path
  (service-layer coupling)? This determines the proposed ADR-008 interface contract."
- "OQ-2 [UNRESOLVED]: Should BranchWatcherRegistry live in backend/db/file_watcher.py
  alongside FileWatcherRegistry, or in a new backend/db/branch_watcher.py? Each option
  has different import-graph and test-isolation implications."
- "OQ-3 [UNRESOLVED]: What is the startup sync serialization path — wired into
  _run_all_projects_sync_job or a separate startup coroutine triggered after project
  sync completes?"
- "OQ-4 [UNRESOLVED]: When a worktree_path does not exist on disk at startup (worktree
  deleted without a status update), should the registry log a warning and skip, or
  update the planning_worktree_contexts row to a terminal status?"
- "OQ-5 [UNRESOLVED]: What are the actual measured timings for sync_changed_files under
  N=3–5 simultaneous watcher events? The 0.70-confidence write-amplification estimate
  requires profiling to validate before Phase 3 N=10+ scale-out."
- "OQ-6 [UNRESOLVED]: Should exact feature-ID branch slug matches (feat/my-feature-slug
  matching feature ID my-feature-slug) be auto-promoted to confidence=high? If so, what
  constitutes an exact match (case-insensitive, hyphen/underscore normalized)?"
- "OQ-7 [UNRESOLVED]: What operator guidance is needed for --reload-exclude configuration
  in dev mode to partially mitigate the uvicorn reload hazard for branch watchers?"
- "OQ-8 (DEF-004): Cache-key strategy for branch-aware queries in multi-project/
  cross-branch scenarios. R-01 spike recommends branch_filter as a param_extractor
  dimension on the four @memoized_query-wrapped planning endpoints. See Cache Key
  Strategy section below."
explored_alternatives:
- "Option A (RECOMMENDED): Parallel BranchWatcherRegistry keyed by (project_id,
  worktree_path). New class, separate from FileWatcherRegistry. Confidence: 0.90."
- "Option B: Extend FileWatcherRegistry with composite keys
  f'{project_id}::branch::{worktree_path}'. Breaks existing snapshot() API contract.
  Confidence: 0.75."
- "Option C: Multi-path watcher on primary project. Entangles branch lifecycle with
  project lifecycle; dynamic path addition not supported post-start. Not recommended."
related_prds:
- docs/project_plans/PRDs/enhancements/planning-agent-session-board-v1.md
- docs/project_plans/PRDs/enhancements/multi-project-planning-command-center-v1.md
---

# Phase 2 Multi-Branch Watcher — BranchWatcherRegistry & S2 Branch-Signal Correlation

**Deferred item**: DEF-001 from `docs/project_plans/implementation_plans/enhancements/branch-aware-planning-intelligence-v1.md`

**Maturity**: shaping — has structure from R-01 spike; blocked on ADR-007 retrofit prerequisite and ADR-008 authoring before promotion to PRD.

**Effort estimate**: ~20–27 story points (Tier 2). Comparable to Phase 2/3 of `ccdash-planning-reskin-v2` (~15–20 pts), plus new infrastructure overhead.

---

## 1. Problem Statement

Phase 1 (Branch-Aware Planning Intelligence v1) exposes branch and session data that already exists in the CCDash DB on planning board surfaces. It does not require multi-branch filesystem watching.

Phase 2 closes the remaining gap: operators running multiple concurrent worktrees (e.g., a hotfix branch alongside an active feature branch) today see planning items that are not correlated to the sessions and docs from non-checked-out worktrees. The `FileWatcher` and `FileWatcherRegistry` bind to a single set of filesystem paths per `project_id` — only one checkout path of markdown docs is watched. PRDs and progress files being edited on a feature branch are invisible to CCDash until that branch is checked out as the main project checkout.

Phase 2 introduces:
1. **`BranchWatcherRegistry`** — a parallel registry keyed by `(project_id, worktree_path)` that watches docs and progress dirs from each operator-registered worktree. Sourced exclusively from `planning_worktree_contexts` rows (ADR-006 compliant).
2. **S2 branch-signal correlation** — a `_correlate_branch` step in `session_correlation.py` that matches `sessions.git_branch` against feature slug tokens, providing medium-confidence session-to-feature linkage for sessions whose branch names encode a feature identifier.
3. **DB migration (v34)** — `branch TEXT DEFAULT ''` column on `documents`, `idx_docs_project_branch` covering index, and `idx_sessions_git_branch_project` composite index on `sessions`.
4. **ADR-007 retrofit** of `SqliteDocumentRepository.upsert` — a prerequisite gate (see Phase-0 Task section below).

Phase 2 also covers the UX stories carried from the UX leg: active-session chips on `CommandCenterFeatureCard` (~2–3 pts), per-phase session links in `CommandCenterDetailPanel` (~3–4 pts), and the branch/commit click-dialog on feature cards (~2 pts). These UX stories were moved to Phase 1 v1 scope by the 99.1% gitBranch coverage audit; they are NOT re-scoped here. This spec covers infrastructure and correlation only.

---

## 2. Phase-0 Prerequisite: ADR-007 Retrofit of `SqliteDocumentRepository.upsert`

**This is a mandatory Phase-0 entry criterion.** No Phase 2 branch write path may ship without it.

### Current Violation

`SqliteDocumentRepository.upsert` in `backend/db/repositories/documents.py` calls `self.db.commit()` without `retry_on_locked`. Per ADR-007 §2, every write path in `backend/db/repositories/` must use `retry_on_locked`. The branch write path introduced by the Phase 2 `documents.branch` column will inherit this violation if the retrofit is not completed first.

### Required Changes

1. **Retrofit `SqliteDocumentRepository.upsert`**:
   ```python
   # before:
   await self.db.commit()
   # after:
   from backend.db.repositories.base import retry_on_locked
   await retry_on_locked(self.db.commit, repo="documents")
   ```

2. **Direct-count assertion test** (ADR-007 §4): after upsert, assert `SELECT COUNT(*) FROM documents WHERE project_id = ? AND branch = ?` returns the expected count.

3. **Lock-injection test** (ADR-007 §5): inject a `SQLITE_BUSY` error on the first commit attempt; assert `retry_on_locked` retries and eventually succeeds.

4. **Postgres parity**: `postgres/documents.py` must apply `ON CONFLICT DO UPDATE SET branch = EXCLUDED.branch` for the branch column addition.

### Why This Is Phase 0, Not Phase 3

The R-01 brief (section 5, risk row 1) classifies this as a HIGH-severity technical risk: "Phase 2 branch write path inherits this violation if not fixed first." A Phase 2 feature that adds a new write path on a repository with a pre-existing ADR-007 violation compounds the debt and creates a non-compliant surface during the period between Phase 2 ship and a hypothetical future retrofit. The retrofit is a small, bounded change and must be treated as a Phase 2 entry criterion, scoped as a mandatory Phase-0 task in the Phase 2 implementation plan.

---

## 3. Proposed ADR-008: BranchWatcherRegistry / Planning-Service Seam

**Status of ADR-008**: proposed. Ref: `docs/project_plans/adrs/adr-008-branch-watcher-registry-planning-service-seam.md`

### What ADR-008 Must Define

The planning service write path calling `BranchWatcherRegistry.register()` on `planning_worktree_contexts` INSERT introduces a new cross-layer dependency between two previously independent layers: the planning service layer and the watcher infrastructure layer. This does not resolve to an extension of ADR-006 or ADR-007. It requires a new ADR.

ADR-008 must specify:

1. **Ownership**: `BranchWatcherRegistry` is a runtime-infrastructure singleton, registered in `backend/runtime/container.py` alongside `FileWatcherRegistry`. It is NOT a service-layer component.

2. **Call site contract**: `BranchWatcherRegistry.register()` and `.unregister()` may only be called from the planning control plane write path (the service that INSERTs/UPDATEs `planning_worktree_contexts` rows). No other service layer may call `BranchWatcherRegistry` directly. This must be enforced by a code-review gate and a linting comment at the call site.

3. **Interface contract**:
   - `register(project_id, worktree_path, branch, feature_id, sync_engine)` on `planning_worktree_contexts` INSERT with `status='running'`
   - `unregister(project_id, worktree_path)` on UPDATE to terminal status (`'completed'`, `'cancelled'`, `'failed'`)
   - On server startup: load all active rows, call `register()` for each where `worktree_path` exists on disk

4. **Lifecycle binding**: `BranchWatcherRegistry.stop_all()` is called from `RuntimeJobAdapter.stop()` alongside `FileWatcherRegistry.stop_all()`.

5. **Prohibition**: no other service layer (e.g., analytics, document query services) may call `BranchWatcherRegistry` directly.

### Open Question: Event Mechanism (OQ-1)

The R-01 brief (section 8, OQ-1) identifies the event mechanism as unresolved: is there an existing event bus that the planning control plane can publish to, triggering the registry call? Or does the registry need to be called directly from the write path (service-layer coupling)? This is the primary blocking question for ADR-008 authoring. The direct-call model is simpler but introduces a hard cross-layer import. The event-bus model is cleaner but requires either an existing bus or a new one.

**This must be resolved before Phase 2 PRD approval.** The resolution should be recorded in ADR-008.

---

## 4. Architecture Design

### 4.1 `BranchWatcherRegistry` (Recommended Option A)

```
BranchWatcherRegistry
  _entries: dict[tuple[str, str], BranchWatcherEntry]
    key: (project_id, worktree_path)
    value: BranchWatcherEntry(
        watcher: FileWatcher,
        worktree_path: Path,
        branch: str,
        feature_id: str | None,
        docs_dir: Path,        # worktree_path / docs_subdir
        progress_dir: Path,    # worktree_path / progress_subdir
    )
  _lock: asyncio.Lock          # P3-010 pattern
```

**Key constraints**:
- Registry key is `(project_id, worktree_path)`, NOT a composite project ID (ADR-006 compliance).
- Sessions directories are NOT watched by branch watchers — sessions live at `~/.claude/sessions/` globally and are already covered by the primary project watcher.
- `sync_engine.sync_changed_files(project_id, ...)` is called with the PARENT `project_id`, not a per-branch ID.
- The `branch` label in `BranchWatcherEntry` is for logging and snapshot metadata only.
- `asyncio.Lock` on all mutating operations (P3-010 pattern from `FileWatcherRegistry`).

**Module placement**: Either `backend/db/file_watcher.py` (alongside `FileWatcherRegistry`) or a new `backend/db/branch_watcher.py`. See OQ-2.

**Snapshot extension**: Use a parallel `branch_watchers` key in `_watcher_registry_snapshot()` output rather than composite keys in the existing `dict[project_id, dict]` structure. This preserves the existing snapshot contract for downstream consumers.

### 4.2 Lifecycle

```
On planning_worktree_contexts INSERT (status='running'):
  → BranchWatcherRegistry.register(project_id, worktree_path, branch, feature_id, sync_engine)

On planning_worktree_contexts UPDATE (status='completed'|'cancelled'|'failed'):
  → BranchWatcherRegistry.unregister(project_id, worktree_path)

On server startup:
  → Load all active planning_worktree_contexts rows
  → Call register() for each with existing worktree_path
  → Skip rows where worktree_path does not exist on disk (log warning; see OQ-4)

On server shutdown:
  → BranchWatcherRegistry.stop_all()
```

### 4.3 DB Migration (v34)

```sql
-- documents.branch column (O(1) metadata-only in SQLite)
ALTER TABLE documents ADD COLUMN branch TEXT DEFAULT '';
CREATE INDEX IF NOT EXISTS idx_docs_project_branch
    ON documents(project_id, branch);

-- sessions branch index (already has git_branch column; index-only, no write path)
CREATE INDEX IF NOT EXISTS idx_sessions_git_branch_project
    ON sessions(git_branch, project_id);
```

Migration is implemented using the existing `_ensure_column` helper + `CREATE INDEX IF NOT EXISTS` guards per the established pattern in `sqlite_migrations.py`.

**Last-writer-wins collision**: Documents from two worktrees on different branches with the same file path share a `documents.id` (slug/hash). The `branch` column disambiguates for query filtering but does NOT change identity. Last-writer-wins at upsert is an accepted Phase 2 limitation. Full per-worktree document isolation (composite PK including `branch`) is Phase 3 scope.

### 4.4 S2 Branch-Signal Correlation in `session_correlation.py`

Add `_correlate_branch` as step 5a in `session_correlation.py:correlate_session`, after `_correlate_command_tokens`:

```python
_BRANCH_EXCLUSION_SET: frozenset[str] = frozenset({
    "main", "master", "develop", "development",
    "staging", "production", "release", "prod",
    "dev", "fix", "wip", "hot", "tmp", "temp",
    "hotfix", "bugfix", "update", "patch", "chore",
    "refactor", "cleanup", "rebase", "merge",
    "ci", "cd", "deploy", "build", "test", "tests",
    "gh-pages", "gh_pages",
})

_BRANCH_PREFIXES = ("feat/", "feature/", "fix/", "hotfix/", "bugfix/",
                    "chore/", "refactor/", "release/", "wip/")

def _normalize_branch_for_correlation(branch: str) -> str:
    for prefix in _BRANCH_PREFIXES:
        if branch.startswith(prefix):
            return branch[len(prefix):]
    return branch

def _correlate_branch(
    session: dict[str, Any],
    feature_index: dict[str, dict[str, Any]],
) -> list[SessionCorrelationEvidence]:
    raw_branch = _safe_str(session.get("git_branch")).lower()
    if not raw_branch:
        return []
    normalized = _normalize_branch_for_correlation(raw_branch)
    if len(normalized) < 8 or normalized in _BRANCH_EXCLUSION_SET:
        return []
    # match normalized branch slug against feature slug tokens
    # confidence: "medium" (same as _correlate_command_tokens)
    ...
```

**Confidence assignment**: `medium`. `high` is reserved for explicit `entity_links`. Promoting exact slug matches (where `normalized == feature_id`) to `high` is an open tuning question (OQ-6).

**Codex null-branch**: `session.get("git_branch")` returns `None` for all Codex sessions (hardcoded in `parsers/platforms/codex/parser.py:1244`). The `_correlate_branch` step returns `[]` immediately when `git_branch` is None. No branch-filter logic gates planning behavior on branch presence — this is consistent with Phase 1 AC-CWD-EXCLUSION and the charter disclosure constraints.

---

## 5. DEF-003 Coverage: `PlanningTopBar` Branch Chip

**DEF-003** (scope-cut from Phase 1): `PlanningTopBar` top-level active branch chip. UX leg priority 4, confidence 0.65.

The Phase 2 implementation plan must include a UX task for `PlanningTopBar` active branch chip display. The chip reads `PlanningCommandCenterItemDTO.worktree?.branch` (already populated in Phase 1) and renders it in the top bar context. No backend changes are required; the data is already available from the existing `planning_worktree_contexts` query. This is a low-effort (~0.5–1 pt) frontend-only task, suitable for inclusion in the Phase 2 UX wave.

**Trigger for inclusion**: post-Phase 1 backlog review confirms operator demand. No separate spec required — covered here.

---

## 6. DEF-004 Coverage: Cache-Key Strategy

**DEF-004** (research-needed from Phase 1): Cache-key strategy for branch-aware queries in multi-project/cross-branch scenarios.

The R-01 data-model spike (RQ5) resolved this question. The recommended approach:

**Option B (Recommended)**: Add `branch_filter` as a `param_extractor` dimension on the four `@memoized_query`-wrapped planning endpoints (`planning_project_summary`, `planning_project_graph`, `planning_feature_context`, `pss_session_board`).

```python
@memoized_query(
    "pss_session_board",
    param_extractor=lambda self, ctx, ports, *, project_id=None, feature_id=None,
        grouping="state", cursor=None, limit=500, branch_filter=None: {
        "project_id": project_id,
        "feature_id": feature_id,
        "grouping": grouping,
        "branch_filter": branch_filter,
        "cursor": cursor,
        "limit": limit,
    },
)
```

When `branch_filter=None` (Phase 1 default), the cache key is identical to the current key — fully backward-compatible. When `branch_filter="feat/my-feature"`, a distinct cache slot is created.

**Event-driven invalidation**: `aclear_project_cache(project_id)` is already called after every `sync_project()`. Branch-watcher-triggered syncs funnel through `sync_changed_files(project_id, ...)` with the parent `project_id`, so they naturally evict the correct project cache slot.

**Fingerprint coverage**: `_FINGERPRINT_TABLES` already includes `sessions.updated_at` and `planning_worktree_contexts.updated_at`. No changes to `_FINGERPRINT_TABLES` are needed for Phase 2 Option A (composite index only, no new write tables).

---

## 7. Performance Envelope and Constraints

| Scenario | Estimated Cost | Confidence |
|----------|---------------|------------|
| N=1–3 branch watchers, sparse file changes | Negligible; `retry_on_locked` headroom at max-3-retries, 3s window | 0.90 |
| N=3 simultaneous watcher events | ~1–4.5s lock contention window; `busy_timeout=30000ms` provides headroom | 0.75 |
| N=5 branch watchers, startup sync (no light-mode) | ~1–5s additional startup cost | 0.80 |
| N=10+ branch watchers | Write amplification not measured; profiling required before Phase 3 | 0.60 |
| Full link rebuild per branch watcher sync (incremental OFF) | Same cost as primary project sync; N×rebuild at N watchers | 0.85 |

**Supported operational range**: N≤5 branch watchers per project. N=10+ requires profiling (OQ-5) before Phase 3 scale-out.

**`CCDASH_STARTUP_SYNC_LIGHT_MODE`**: compatible with branch watchers. Manifest keys are path-keyed (`filesystem_scan_manifest.path PRIMARY KEY`); branch worktree paths produce distinct manifest entries with no collision.

**`CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED`**: currently OFF by default. Branch-watcher events will trigger full link rebuilds until incremental rebuild is validated. Not a Phase 2 blocker.

**uvicorn `--reload` hazard**: same hazard as primary watcher; N branch watchers compound missed-event windows during development reloads. Accept as dev-mode limitation. Production worker-watch profile is unaffected. Operator guidance for `--reload-exclude` is OQ-7.

---

## 8. Preconditions for Phase 2 PRD Approval

The following must be resolved before a Phase 2 implementation plan can be authored:

1. **ADR-007 retrofit design** for `SqliteDocumentRepository.upsert` is scoped as a mandatory Phase-0 task (not deferred to Phase 3).
2. **OQ-1 resolved**: the `BranchWatcherRegistry` lifecycle notification mechanism (`planning_worktree_contexts` INSERT/UPDATE → register/unregister path) is explicitly designed, with proposed ADR-008 accepted.
3. **OQ-2 resolved**: `BranchWatcherRegistry` module placement (`file_watcher.py` vs. new `branch_watcher.py`) decided.
4. **OQ-3 resolved**: startup sync serialization path specified.
5. **Phase 1 ACs**: Codex null-branch graceful-empty-state handling confirmed shipped in Phase 1.
6. **N≤5 operational range** documented in operator guidance before Phase 2 merges.

---

## 9. Risks Carried Forward from R-01

| Risk | Severity | Status |
|------|----------|--------|
| ADR-007 retrofit debt on `SqliteDocumentRepository.upsert` | H | Phase-0 prerequisite; blocks Phase 2 branch write path |
| Codex null-branch structural limitation (`parsers/platforms/codex/parser.py:1244`) | H | Handled by `_correlate_branch` early-exit; Phase 1 chips handle gracefully |
| Document identity collision (last-writer-wins across worktrees at same path) | M | Accepted Phase 2 limitation; Phase 3 scope for composite PK |
| Write amplification at N=10+ branch watchers | M | Profiling required (OQ-5); enforce N≤5 operational range |
| uvicorn `--reload` drops all watcher registrations | M | Dev-mode accepted limitation; production unaffected |
| Branch correlation FP rate: <5% subjective estimate, unvalidated | M | Add telemetry hook post-ship; make exclusion set configurable |
| Cross-layer dependency: planning service → BranchWatcherRegistry | M | Requires ADR-008 acceptance before implementation |
| BranchWatcherRegistry snapshot API breaks existing dict[project_id, dict] contract | L | Use parallel `branch_watchers` key in snapshot output |
| Auto-discovery via `git worktree list` as runtime binding path (ADR-006 violation risk) | M | Allowed only as registration-time aid; code-review gate at call site |
| Incremental link rebuild entity_ids gap (full rebuild even with INCREMENTAL=true) | L | Known limitation; Phase 3 dependency if incremental rebuild ships |

---

## 10. Related Specs and References

- **Watcher architecture findings**: `docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/r01-branch-watcher/watcher-arch-findings.md`
- **Data model findings** (RQ3 cache strategy, RQ5 branch column, RQ6 linkage model): `docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/r01-branch-watcher/data-model-findings.md`
- **R-01 feasibility brief**: `docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/r01-branch-watcher/r01-branch-watcher-brief.md`
- **Risk findings**: `docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/risk-findings.md`
- **ADR-006**: `docs/project_plans/adrs/adr-006-db-authoritative-project-registry.md`
- **ADR-007**: `docs/project_plans/adrs/adr-007-db-write-failure-surfacing-standard.md`
- **Proposed ADR-008**: `docs/project_plans/adrs/adr-008-branch-watcher-registry-planning-service-seam.md`
- **Phase 1 implementation plan**: `docs/project_plans/implementation_plans/enhancements/branch-aware-planning-intelligence-v1.md`
- **DEF-002 spec** (CommandCenterDetailPanel consolidation): `docs/project_plans/design-specs/command-center-detail-panel-consolidation.md`
