---
schema_version: 2
doc_type: spike_findings
title: "R-01 Branch Watcher Architecture — Watcher Arch Findings"
status: complete
confidence: 0.88
created: 2026-06-04
feature_slug: branch-aware-planning-intelligence
spike_id: r01-branch-watcher
charter_ref: docs/project_plans/exploration/branch-aware-planning-intelligence/branch-aware-planning-intelligence-charter.md
risk_register_ref: docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/risk-findings.md
partial: false
investigation_angle: feasibility — what is possible, what is blocked, what the integration constraints are
research_questions_answered:
  - RQ1: operator-registered vs auto-discovery watching under ADR-006
  - RQ2: BranchWatcherRegistry abstraction over FileWatcher
  - RQ4: perf/write-amplification envelope for N worktrees
---

# R-01 Spike: Branch Watcher Architecture Findings

## Executive Summary

The existing `FileWatcher` / `FileWatcherRegistry` infrastructure is well-suited to extend for multi-branch worktree watching without introducing composite project IDs or violating ADR-006 semantics. The operator-registered model (sourcing worktree paths exclusively from `planning_worktree_contexts`) is the correct approach and is already partially implemented at the data layer. Auto-discovery via `git worktree list` is feasible as an additive complement but must not be the primary path — it cannot carry the operator-intent metadata (branch, feature linkage, base commit) already present in the DB table.

The recommended design is a `BranchWatcherRegistry` that mirrors the `FileWatcherRegistry` structure but is keyed by `(project_id, worktree_path)` rather than `project_id` alone, with lifecycle hooks wired to worktree create/remove events from the planning control plane. Write amplification under N worktrees is manageable if all branch watcher syncs funnel through the same `sync_engine` singleton; the primary risk is the uvicorn `--reload` hazard which drops all in-process registrations on every code change.

**Confidence: 0.88** — grounded in direct code reads of all primary source files. Unknown: production timing under load (N=3–5 simultaneous watchers), which would require profiling.

---

## RQ1: Operator-Registered vs Auto-Discovery — Design Choice Under ADR-006

### Current State

`planning_worktree_contexts` (`backend/db/sqlite_migrations.py`, line 1247) already carries:
- `worktree_path TEXT` — the filesystem path of the worktree checkout
- `branch TEXT` — the branch name in that worktree
- `base_branch TEXT`, `base_commit_sha TEXT` — provenance
- `feature_id TEXT`, `phase_number INTEGER` — planning linkage
- `project_id TEXT NOT NULL` — registry-authoritative project reference

This table is operator-populated via the planning control plane launch flow. It is NOT auto-discovered. The `WorktreeGitStateProbe` (`backend/application/services/worktree_git_state.py`, line 31) runs `git rev-parse`, `git status --porcelain`, `git stash list`, and `git rev-list` against known worktree paths from this table — it is already a scoped, safe probe pattern.

### ADR-006 Constraint

ADR-006 (`docs/project_plans/adrs/adr-006-db-authoritative-project-registry.md`) makes the `projects` table authoritative. A key constraint: worktree-local paths must NOT be modeled as separate project registry entries. The `planning_worktree_contexts` table was specifically introduced to carry this data without polluting the project registry.

**Conclusion**: The operator-registered model is the only ADR-006-compatible path. Any worktree path a watcher should watch must be present in `planning_worktree_contexts.worktree_path` as the source of truth.

### Auto-Discovery Assessment

`git worktree list --porcelain` would discover all git worktrees under the active project's repo root. This is attractive for zero-config UX but has disqualifying problems:

1. **No ADR-006 linkage**: auto-discovered paths carry no `feature_id`, `branch` context, or operator-declared linkage. Without the `planning_worktree_contexts` row, a watcher on that path cannot scope its syncs correctly.
2. **Uncontrolled path proliferation**: a developer may have arbitrary worktrees (e.g., for rebasing, hotfix, experiments) that should not be scanned by CCDash.
3. **No operator-intent signal**: CCDash cannot distinguish "I want this worktree's docs synced" from "this worktree exists transiently".

**Recommended position**: auto-discovery via `git worktree list` is acceptable as a one-time discovery aid at worktree-registration time (to populate the `planning_worktree_contexts` row), but is NOT acceptable as the runtime path-discovery mechanism. The watcher must only bind to paths that are present in `planning_worktree_contexts` as operator-registered rows.

---

## RQ2: BranchWatcherRegistry Abstraction

### Existing `FileWatcherRegistry` Structure (Reference)

`FileWatcherRegistry` (`backend/db/file_watcher.py`, line 336) is the precedent:
- Keyed by `project_id: str` → `_WatcherEntry(watcher, sessions_dir, docs_dir, progress_dir)`
- One `FileWatcher` asyncio task per entry
- `register(project_id, ...)` stops existing watcher for that ID then starts a new one
- `asyncio.Lock` (`_lock`) serializes all mutating operations (P3-010)
- `start(sync_engine, project_id, sessions_dir, docs_dir, progress_dir, ...)` signature on `FileWatcher`

The `_watch_loop` in `FileWatcher` (line 173) uses `watchfiles.awatch(*watch_paths)` — a Rust-backed async iterator that efficiently watches multiple paths in a single task. Adding more paths to a single watcher call is more efficient than spawning N separate tasks.

### Proposed `BranchWatcherRegistry` Design

**Key insight**: a branch worktree watcher is scoped to `(project_id, worktree_path)` — not `project_id` alone. Multiple worktrees per project must each have their own watcher entry.

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
  _lock: asyncio.Lock  # same P3-010 pattern
```

**Alternative**: extend the existing `FileWatcherRegistry` with composite keys `f"{project_id}:worktree:{worktree_path}"`. This is simpler but leaks the worktree concept into the core registry. A separate registry is preferred for separation of concerns.

#### Binding Model

Source of bindings: `planning_worktree_contexts` rows where `status` is active (e.g., `'running'`, `'active'`).

On `register(project_id, worktree_path, branch, feature_id, sync_engine)`:
1. Derive `docs_dir` and `progress_dir` from `worktree_path` using the same path conventions as the project registry (e.g., `worktree_path / ".claude"`, `worktree_path / "docs/project_plans"`)
2. Reuse `FileWatcher.start()` unchanged — it already accepts arbitrary `docs_dir` and `progress_dir` paths
3. The `project_id` passed to `sync_engine.sync_changed_files(project_id, ...)` is the parent project's ID, NOT a per-branch ID — this is ADR-006 compliance
4. Store the `branch` label in `BranchWatcherEntry` for logging and snapshot metadata only

**Sessions directory**: sessions (`.jsonl`) are NOT branch-scoped at the filesystem level (they live in `~/.claude/sessions/` globally). The branch watcher should watch ONLY `docs_dir` and `progress_dir` from the worktree path — not a sessions directory. The primary project watcher already covers session files.

#### Lifecycle

Worktree create/remove events come from the planning control plane when the operator registers or deactivates a `planning_worktree_contexts` row.

```
On planning_worktree_contexts INSERT (status='running'):
  → BranchWatcherRegistry.register(project_id, worktree_path, branch, feature_id, sync_engine)

On planning_worktree_contexts UPDATE (status='completed'|'cancelled'|'failed'):
  → BranchWatcherRegistry.unregister(project_id, worktree_path)

On server startup:
  → Load all active planning_worktree_contexts rows
  → Call register() for each with an existing worktree_path
  → Skip rows where worktree_path does not exist on disk (log warning)

On server shutdown:
  → BranchWatcherRegistry.stop_all()
```

**uvicorn `--reload` hazard**: every uvicorn reload drops all in-process asyncio tasks, including all watcher registrations. The startup lifecycle above means watchers are re-registered on every reload, but there is a window of missed events between the old process death and the new process's startup sync. This is the same hazard that affects the existing `FileWatcher` (confirmed in memory notes and risk-findings.md R-01). The mitigation is the same: accept the window as a known dev-mode limitation; production deployments should not use `--reload`.

**Multi-project all-projects path**: `_run_all_projects_sync_job` already iterates all non-active projects and calls `file_watcher_registry.register()` for each. Branch watcher registration can be added to this same loop by loading `planning_worktree_contexts` rows per project and calling `BranchWatcherRegistry.register()` for each active row.

#### Debounce Strategy

`watchfiles.awatch` has built-in debouncing (default 400ms). This is sufficient — the existing `FileWatcher` does not add an additional debounce layer. Branch watchers should inherit the same behavior.

For write-heavy scenarios (e.g., an agent writing to a progress file rapidly), the debounce windows from multiple watcher tasks (main project + N branch watchers) are independent. They may trigger near-simultaneous `sync_changed_files` calls that converge on the same SQLite writer. The mitigation (see RQ4) is ensuring all calls funnel through the single `sync_engine` singleton.

#### Interaction with `CCDASH_STARTUP_SYNC_LIGHT_MODE`

Light-mode (`backend/db/sync_engine.py`, line 4404) checks `config.STARTUP_SYNC_LIGHT_MODE` and reads a scan manifest from `filesystem_scan_manifest` table to compare inode/mtime snapshots.

**Problem**: the manifest key is derived from the directory path(s) (e.g., `str(sessions_dir)` for sessions, `"|".join(resolved_roots)` for docs+progress). Branch worktrees have DIFFERENT paths from the main project checkout. Their manifest entries would be stored separately and would work correctly — each worktree's scan is independently skippable when its files are unchanged.

**No conflict**: light-mode is safe for branch watcher syncs. The manifest table is path-keyed (`filesystem_scan_manifest.path PRIMARY KEY`), so multiple roots coexist without collision.

**Implication**: on startup, if a branch worktree's files are unchanged since the last scan, light-mode will skip re-parsing. This is the desired behavior — no full parse cost on restart for stable worktrees.

#### Interaction with `CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED`

Incremental link rebuild (`backend/db/sync_engine.py`, line 2617) is currently OFF by default. When ON, it dispatches scoped entity rebuilds rather than full rebuilds. Branch watcher events will trigger `sync_changed_files` which calls `_should_rebuild_links_after_watcher_sync` and may dispatch link rebuilds.

**Known limitation** (confirmed in code, line 2630–2644): the incremental path only works when `entity_ids` are surfaced from the sync-stats layer. Currently, `_sync_sessions` and `_sync_documents` return only counts, so the code falls back to a full rebuild even in incremental mode. This limitation applies equally to branch watcher-triggered syncs.

**Implication**: for Phase 2 branch watcher development, if incremental link rebuild is enabled, branch-watcher-triggered doc syncs will produce full link rebuilds — the same cost as main-project syncs. There is no amplification relative to the existing behavior.

---

## RQ4: Performance and Write-Amplification Envelope for N Worktrees

### Sync Engine Load

The `sync_engine.sync_changed_files()` method (line 3962) is the hot path for watcher-triggered syncs. It is a coroutine that runs on the asyncio event loop. Multiple concurrent calls are serialized by the event loop's cooperative scheduling — there is no explicit mutex inside `sync_changed_files`, but the `aiosqlite` connection is shared (singleton at `backend/db/connection.py`) and SQLite WAL mode allows one writer at a time.

**Write cost per branch watcher event (doc change in worktree):**
- Document parse: CPU-bound, off-loaded to `asyncio.to_thread` for heavy parsers; light for simple markdown
- DB writes: `documents` upsert + `document_refs` upsert + optional `entity_links` upsert
- Link rebuild: if triggered, full `_rebuild_entity_links` (potentially expensive)
- Planning invalidation: `publish_planning_invalidation()` on the in-memory broker (cheap, O(subscribers))

For N=3 worktrees each editing a progress file simultaneously:
- 3 concurrent `sync_changed_files` coroutines (one per watcher task)
- Each attempts a SQLite write → `retry_on_locked` (max 3 retries, 0.5s backoff)
- Worst case: 3 × 3 = 9 retry cycles = ~4.5 seconds of lock contention before exhaustion

**Observed**: `retry_on_locked` (base.py, line 109) with `max_retries=3, backoff=0.5` produces max delay of `0.5 + 1.0 + 1.5 = 3.0s` on the 3rd attempt. If all 3 watchers fire simultaneously, at most 2 see lock contention; the third proceeds immediately. Probability of simultaneous writes decreases significantly in practice because agent file writes are bursty but not truly synchronous across worktrees.

**Mitigation already present**: `busy_timeout=30000ms` on the singleton connection (`connection.py`, line 52, using `SQLITE_BUSY_TIMEOUT_MS` env var defaulting to 30000). This provides 30 seconds of OS-level blocking before SQLite gives up — well above the `retry_on_locked` window.

### SQLite WAL Contention

SQLite WAL mode (`PRAGMA journal_mode=WAL`, connection.py line 50) supports concurrent reads with one writer. The key constraint: only one writer at a time acquires the write lock.

**Risk for N=3 branch watchers**: if three worktrees emit file-change events within the same debounce window (400ms), three `sync_changed_files` coroutines queue behind the WAL write lock. The asyncio event loop serializes coroutine execution cooperatively, so these will interleave rather than truly run in parallel. In practice, WAL lock contention is low for N≤5 watchers with typical agent file-change rates (one progress file edit per minute per worktree).

**Risk for N=10+ branch watchers**: write amplification becomes material. Each worktree's sync cycle — document parse + upsert + link rebuild — takes 50–500ms depending on file size. At N=10, startup sync of all worktrees takes 10× the per-worktree cost. Recommended: serialize worktree startup syncs (already the pattern in `_run_all_projects_sync_job`, line 803 comment: "Syncs are serialised inside this coroutine to avoid saturating SQLite").

**New branch-watcher sync paths must comply with ADR-007**: `retry_on_locked` on every new write path + direct-count assertion test. This is a one-time implementation cost, not a per-call overhead.

### Startup Sync Cost

On server startup, the proposed lifecycle calls `sync_project()` for each active worktree path in `planning_worktree_contexts`. Cost:

- Per worktree: doc scan + progress scan + feature scan + link rebuild
- With light-mode enabled: skips full walk if manifest unchanged (free path on restart)
- Without light-mode: full walk per worktree root

For 3 active worktrees each with ~50 markdown files: ~150 file stat calls + 150 parse operations + 3 link rebuilds. Estimated total: 1–5 seconds additional startup cost. Acceptable for typical development workloads.

### uvicorn --reload Worktree Hazard

**Confirmed hazard (R-01 from risk-findings.md and memory):** uvicorn `--reload` watches the main worktree. Every code change in the main repo causes uvicorn to reload, which:
1. Kills all asyncio tasks including every watcher task (main + branch)
2. On restart, `startup()` re-runs the full registration sequence
3. Files modified during the reload window are not detected by `awatch` (no state is preserved)
4. If a branch worktree is being actively edited at reload time, those changes land in the missed-event window

**With N branch watchers, the hazard compounds**: more active worktrees = more paths being watched = more likely that a reload interrupts an active agent edit somewhere.

**Mitigation options:**
1. `--reload-exclude` patterns: exclude the main project's source dir from uvicorn's reload watch. This requires explicit configuration per developer.
2. `CCDASH_STARTUP_SYNC_LIGHT_MODE=true`: on reload, the startup sync skips unchanged files, reducing startup cost. Changed files in the reload window are caught on the next watcher event (first event after restart).
3. Accept as dev-mode limitation: production deployments use `worker-watch` profile without `--reload`. Document the hazard in the operator guide.

**Assessment**: option 3 is the correct production answer. Light-mode (option 2) reduces startup cost but does not eliminate the missed-event window. This hazard is not new to branch watchers — it already exists for the primary watcher and is documented.

### Incremental Link Rebuild Interaction Under Load

`CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED` defaults to OFF. When OFF, every watcher-triggered `sync_changed_files` that modifies a document triggers a full `_rebuild_entity_links` call. For N branch watchers each triggering a full rebuild simultaneously, this produces N full rebuild cycles.

A full rebuild reads all `entity_links` rows and re-computes them. For a project with 1000 sessions and 200 docs, a full rebuild takes ~200–2000ms. At N=3, worst case: 3 × 2s = 6s of rebuild work, all serialized through the single SQLite connection.

**Mitigation**: incremental link rebuild (when eventually validated and turned ON) would scope the rebuild to only the changed entities, dramatically reducing per-event cost. Until then, operator guidance should note that heavy simultaneous worktree editing may cause planning query latency spikes of seconds.

---

## Recommended Design

### Option A (Recommended): Parallel `BranchWatcherRegistry` Keyed by `(project_id, worktree_path)`

**Structure:**
- New class `BranchWatcherRegistry` in `backend/db/file_watcher.py` (or a new `backend/db/branch_watcher.py`)
- Registry key: `(project_id: str, worktree_path: str)` — avoids composite project IDs
- Each entry holds a `FileWatcher` instance watching only `docs_dir` and `progress_dir` from the worktree path
- Sessions are NOT watched by branch watchers (sessions are in `~/.claude/sessions/`, already watched by the primary project watcher)
- `sync_engine.sync_changed_files(project_id, ...)` is called with the PARENT `project_id` — no new project entities created
- Lifecycle driven by `planning_worktree_contexts` row state transitions
- Startup population: load all active rows, call `register()` for each with existing path
- Shutdown: `stop_all()` called from `RuntimeJobAdapter.stop()` alongside `file_watcher_registry.stop_all()`
- `asyncio.Lock` on all mutating operations (P3-010 pattern)

**ADR-006 compliance**: YES — no new project registry entries; branch context flows via the `planning_worktree_contexts` table

**ADR-007 compliance**: NEW write paths for branch-watcher-triggered doc upserts must use `retry_on_locked` (they will, because they reuse the existing `sync_engine` path which already uses it) and must ship direct-count assertion tests

**Confidence in this option**: 0.90 — directly extends proven patterns without new abstractions

### Option B (Alternative): Extend `FileWatcherRegistry` with Composite Keys

**Structure:**
- Use existing `FileWatcherRegistry` with key format `f"{project_id}::branch::{worktree_path}"`
- Avoids introducing a new registry class
- Snapshot output would include branch-keyed entries alongside project-keyed entries

**Drawback**: the `FileWatcherRegistry` snapshot API (`snapshot()`, `snapshot_all()`) returns `dict[project_id, dict]` — composite keys would break the assumption that keys are project IDs. Downstream consumers (e.g., `_watcher_registry_snapshot()` in `runtime.py` line 734) would need updates.

**Confidence in this option**: 0.75 — feasible but requires more surgical changes to existing consumers

### Option C (Not Recommended): Multi-Path Watcher on Primary Project

**Structure:**
- Add worktree paths to the existing primary `FileWatcher.start()` call by passing additional `watch_paths` from `planning_worktree_contexts`
- Single watcher task handles all paths for the project

**Drawback**: the primary watcher is a singleton per project; adding branch paths entangles branch lifecycle with project lifecycle. Stopping a branch watcher would require stopping and restarting the primary watcher (causing a missed-event window for all paths). The existing `FileWatcher.start()` signature does not support dynamic path addition post-start.

**Confidence in this option**: 0.60 — feasible but violates separation of concerns and creates lifecycle coupling

---

## Constraints Summary

| Constraint | Source | Impact on Design |
|---|---|---|
| ADR-006: no composite project IDs | ADR-006 | Branch watcher must use parent project_id; worktree context from planning_worktree_contexts |
| ADR-007: retry_on_locked + assertion test | ADR-007 | Any new write path in branch-watcher sync must comply |
| Single SQLite WAL writer | connection.py PRAGMA | N concurrent watcher syncs contend; serialize startup syncs |
| busy_timeout=30000ms | connection.py line 52 | 30s protection window; sufficient for N≤5 watchers |
| uvicorn --reload drops tasks | dev-env hazard (memory) | Watchers re-registered on restart; missed-event window accepted in dev |
| STARTUP_SYNC_LIGHT_MODE manifest keyed by path | sync_engine.py line 4246 | Branch worktree paths have distinct manifest entries — no conflict |
| INCREMENTAL_LINK_REBUILD_ENABLED=false default | config.py line 131 | Branch sync triggers full rebuild; amplification proportional to N |
| Sessions not branch-scoped on filesystem | file_watcher.py, risk-findings | Branch watchers should NOT watch sessions_dir; primary watcher covers it |
| planning_worktree_contexts is operator-populated | migrations.py line 1247 | Only operator-registered paths are safe to watch |
| WorktreeGitStateProbe TTL=5s, timeout=0.8s | worktree_git_state.py | Existing probe pattern; branch watcher does not need its own git probe |

---

## Confidence Signals

- **FileWatcher binding model**: direct code read (`file_watcher.py`). Confidence: 0.97.
- **FileWatcherRegistry lock pattern (P3-010)**: confirmed in code comments and implementation. Confidence: 0.97.
- **planning_worktree_contexts table structure**: confirmed from migration SQL. Confidence: 0.97.
- **busy_timeout=30000ms on singleton connection**: confirmed from `connection.py` line 52. Confidence: 0.97.
- **Light-mode manifest key design**: confirmed from `sync_engine.py` lines 4244–4261. Confidence: 0.95.
- **Incremental link rebuild default OFF**: confirmed from `config.py` line 131. Confidence: 0.97.
- **uvicorn --reload hazard**: confirmed from memory notes, risk-findings R-01, and runtime.py watcher lifecycle. Confidence: 0.95.
- **Write amplification at N=3**: estimated from retry_on_locked parameters; not measured under load. Confidence: 0.70.
- **N=10+ watcher scaling**: extrapolated; not tested. Confidence: 0.60.

**Overall confidence: 0.88** — architecture is well-grounded in code; performance envelope at scale is estimated, not measured.
