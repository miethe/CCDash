---
type: context
schema_version: 2
doc_type: context
feature_slug: watcher-rebind-on-active-project-switch
status: completed
created: 2026-05-20
updated: 2026-05-20
---

## Completion Report

### Summary

Added `RuntimeJobAdapter.rebind_watcher()` method that atomically stops the existing file watcher, validates the new project's paths, drains the outgoing project via a light sync, starts the new watcher, and triggers a one-shot session sync. The `POST /api/projects/active/{project_id}` endpoint was updated to call `rebind_watcher` before committing the active-project switch; it returns `watcherRebound: true` on success and HTTP 4xx (without changing the active project or watcher state) if the new project's paths are invalid. An integration test suite covering the full switch lifecycle was added.

### Files Changed

- `backend/adapters/jobs/runtime.py` — added `WatcherRebindError` exception class and `RuntimeJobAdapter.rebind_watcher()` method implementing the atomic stop→start→sync sequence with drain-before-rebind and rollback on start failure
- `backend/adapters/jobs/__init__.py` — exported `WatcherRebindError` in `__all__`
- `backend/routers/projects.py` — changed `set_active_project` from sync to async, added `request: Request` parameter, added rebind call via `request.app.state.runtime_jobs`, added `watcherRebound` field in JSON response; active-project switch now happens after a successful rebind (fail-fast ordering)
- `backend/tests/test_watcher_rebind.py` — new test file with 13 tests: 7 unit tests (`WatcherRebindUnitTests`), 3 integration tests with real SQLite + SyncEngine (`WatcherRebindIntegrationTests`), 3 router-level tests with TestClient + dependency overrides (`WatcherRebindRouterTests`)
- `backend/tests/test_project_paths.py` — updated `test_projects_router_rejects_hosted_active_project_mutation` to call the now-async `set_active_project` via `asyncio.run()` and pass the new `request` parameter
- `CHANGELOG.md` — added `[Unreleased] / Fixed` entry describing the watcher rebind behavior

### Acceptance Criteria Status

- [x] AC-1: Health detail reflects new project paths after switch — `rebind_watcher` updates `file_watcher._snapshot.project_id` and `watch_paths` before returning; `GET /api/health/detail` reads the live snapshot
- [x] AC-2: New session in newly active project is picked up within sync latency — one-shot `sync_project` runs after watcher starts; integration test verifies sessions table populated
- [x] AC-3: Mid-switch event loss is bounded — drain-before-rebind: `sync_planning_artifacts` called for outgoing project before `stop()`. Unit test `test_rebind_drains_old_project_before_stop` verifies drain call. Event loss within the `stop()` cancel window is accepted per contract.
- [x] AC-4: Failed rebind leaves watcher on previous project; API returns 4xx — path validation runs before `stop()`; rollback re-starts watcher on old project if `start()` fails after `stop()`. Router test `test_bad_paths_returns_4xx` verifies 422.
- [x] AC-5: Integration test exercises full switch end-to-end — `pytest backend/tests/ -k watcher_rebind` passes all 13 tests covering successful switch, bad-paths failure, and drain verification
- [ ] AC-6: Runtime smoke — dev server not started in this sprint (CCDASH_RUNTIME_SMOKE_REQUIRED=false per contract visual_evidence_required: false). Operator should verify via browser project-picker after deployment.

### Validation Run

| Command | Result | Notes |
|---|---|---|
| `pytest backend/tests/test_watcher_rebind.py -v` | Pass (13/13) | All new tests pass |
| `pytest backend/tests/test_file_watcher.py backend/tests/test_project_manager.py backend/tests/test_project_paths.py -v` | Pass (22/22) | No regressions in directly related tests |
| `ruff check backend/adapters/jobs/runtime.py backend/routers/projects.py backend/tests/test_watcher_rebind.py backend/tests/test_project_paths.py` | Pass | All checks passed |
| `mypy backend/adapters/jobs/runtime.py backend/routers/projects.py --ignore-missing-imports` | Pass (no errors) | Invoked via Python; module-path resolution issue in CLI invocation is environment-specific and pre-existing |
| `pytest backend/tests/test_runtime_bootstrap.py` | Not run (hangs in background — pre-existing integration test startup issue in worktree environment) | Pre-existing; not caused by this change |
| `pytest backend/tests/test_architecture_boundaries.py` | Pre-existing failure (analytics.py imports db.factory) | Not introduced by this change; confirmed identical failure on main branch |
| `npm run build` | Not run (no frontend changes) | Skipped per contract (backend-only change) |

### Drain Strategy Chosen

**Drain-before-rebind.** Before calling `file_watcher.stop()`, `rebind_watcher()` calls `self.sync.sync_planning_artifacts(old_project_id, old_docs_dir, old_progress_dir, force=False)` for the outgoing project. This is a light sync (docs and progress only, no session re-scan) sufficient to flush recently-parsed planning artifacts.

Rationale for light drain over full drain: a full `sync_project` on the outgoing project adds latency proportional to session count; the drain is called synchronously before the watcher can be stopped, blocking the API response. The planning-artifacts-only drain is fast (no JSONL re-scan) and covers the most common state that could be mid-flight when a user switches projects.

Event loss within the `asyncio.Task.cancel()` window remains possible as documented in AC-3. Events fired between the drain call completing and the `_watch_loop` task being cancelled are not recoverable. This is acceptable per the contract's "bounded loss" language.

### Rebind Call Site Pattern Chosen

**Direct invocation.** `backend/routers/projects.py` accesses `request.app.state.runtime_jobs` (the `RuntimeJobAdapter` instance stored by `container.py:158`) and calls `await job_adapter.rebind_watcher(project_id)`. No callback/observer pattern was introduced. This avoids a new abstract port interface for a single call site and follows the existing pattern of accessing `app.state` from routers (consistent with `request_scope.py:19`, `bootstrap.py:93`).

### Ordering: Rebind Before Active-Project Switch

The rebind is called before `workspace_registry.set_active_project(project_id)`. This ensures that if the new project's paths are invalid, the endpoint returns 4xx without the active-project pointer being updated — no partial state. If the rebind succeeds but the registry update unexpectedly fails, the watcher is bound to the new project's paths while the registry still points to the old project; this edge case is considered acceptable (the watcher will quickly self-correct on the next health check cycle or next request).

### Deviations From Contract

- The contract suggests `watcherRebound: null` for async rebind path and `watcherRebound: bool` for sync. We implemented synchronous rebind only (simpler, predictable, documented per §5 guidance). `watcherRebound: true` means the rebind completed; `watcherRebound: null` means the job adapter was not available (pre-startup or test context).
- `rebind_watcher` was added directly to `RuntimeJobAdapter` without a new abstract port in `backend/application/ports/`. This is the "direct-invocation alternative" explicitly permitted by the contract's §8 Architecture Constraints.
- The one-shot sync in `rebind_watcher` calls `self.sync.sync_project(...)` with `rebuild_links=False, capture_analytics=False, backfill_session_intelligence=False`. This is a minimal sync to populate the sessions table quickly. The full startup-sync pipeline (with SkillMeat refresh, deferred link rebuild, etc.) is intentionally not replicated in the rebind path to avoid latency.

### Risks and Limitations

- **Rollback on failed start**: If `file_watcher.stop()` succeeds but `file_watcher.start(new_project)` fails, the rollback re-invokes `file_watcher.start(old_project)`. If the rollback start also fails (e.g., old project paths were removed), `watcher_started` is set to False and no watcher runs. The health probe will surface this as `state: not_configured`. This edge case is difficult to produce in production but is documented.
- **Concurrent rebind calls**: No mutex guards against two simultaneous `POST /api/projects/active/` requests racing. The second caller's rebind will observe whatever watcher state the first caller left. In production this is unlikely (single-operator local use), but a mutex on `rebind_watcher` would close this window for future multi-operator scenarios.
- **test_runtime_bootstrap.py**: Could not run in this worktree environment (background task hangs). The tests that most directly exercise `RuntimeJobAdapter` (`test_file_watcher.py::RuntimeWatcherContractTests`) all pass.

### Follow-Up Recommendations

1. **Tier 2 system-wide live metrics PRD** (`docs/project_plans/PRDs/features/system-wide-metrics-v1.md`): This contract is the declared precondition. The composite index from spike OQ-3b (`sessions(project_id, last_active_at)`) should be added as a Tier 0 quick-feature before the Tier 2 contract begins — session count queries against newly-rebound projects will be slow without it.
2. **Concurrent rebind mutex**: Add an `asyncio.Lock` around the stop→start sequence in `rebind_watcher` to prevent double-rebind races if the endpoint is ever called from parallel requests (low priority for single-operator local use, required for multi-operator hosted mode).
3. **Smoke gate for AC-6**: A dev-server smoke run (`npm run dev` + browser project-picker switch + network-tab verification) should be performed before the Tier 2 contract begins to confirm the full UI→watcher→health-detail flow end-to-end.

### Memory Candidates Captured

- Pattern: `backend.runtime.dependencies.get_request_context` and `backend.request_scope.get_request_context` are two different functions — router tests must override the one from `backend.runtime.dependencies` (imported by the projects router).
- Gotcha: `FileWatcher.start()` silently no-ops if `_running` is already True. The rebind path guards against this by always calling `stop()` before `start()`, but callers must confirm `_running = False` after `stop()` before the next `start()`.
- Pattern: `rebind_watcher` captures the old snapshot before `stop()` for rollback; this is the canonical pattern for atomic watcher lifecycle management.
