---
schema_version: 2
doc_type: feature_contract
title: "Feature Contract: Watcher Rebind on Active Project Switch"
status: draft
created: 2026-05-20
updated: 2026-05-20
feature_slug: watcher-rebind-on-active-project-switch
category: features
tier: 1
estimated_points: 5
owner: null
priority: high
risk_level: medium
changelog_required: true
related_documents:
  - .claude/worknotes/system-wide-live-metrics-spike/spike.md
spike_ref: .claude/worknotes/system-wide-live-metrics-spike/spike.md
prd_ref: null
plan_ref: null
commit_refs: []
pr_refs: []
files_affected: []
---

# Feature Contract: Watcher Rebind on Active Project Switch

## 1. Goal

When the user switches active project, rebind the file watcher atomically to the new project's paths and trigger a one-shot sync, so that session counts, analytics, and live metrics immediately reflect the correct project.

---

## 2. User / Actor

- **Primary user**: CCDash operator/developer switching between projects via the UI project picker or `POST /api/projects/active/{id}`.
- **Secondary users**: Any consumer of session counts, analytics, or live-agent metrics (home dashboard, MCP tools, CLI) who expects data to reflect the currently active project.

---

## 3. Job To Be Done

When the operator switches the active project, they want the file watcher to immediately observe the new project's session and doc directories, so they can trust that session counts, sync status, and live-agent data reflect the project they are actually working in — not the project that happened to be active at server startup.

---

## 4. Scope

### In Scope

1. **Watcher rebind on project switch.** `LocalWorkspaceRegistry.set_active_project()` (or its consumer in `backend/routers/projects.py`) must notify the `RuntimeJobAdapter`, which stops the existing watcher, resolves the new project's `sessions_dir`, `docs_dir`, and `progress_dir`, and starts a new watcher against those paths. The preferred pattern is a callback/observer registered by `RuntimeJobAdapter` on `LocalWorkspaceRegistry`; an acceptable alternative is direct invocation via the `RuntimeContainer` reference accessible from `backend/routers/projects.py` through `app.state.runtime_container`. Choose whichever fits the existing dependency injection pattern in `backend/runtime/container.py` without requiring circular imports.
2. **Atomic rebind.** Stop the existing watcher before starting the new one. No period during which two watcher tasks run concurrently against different project dirs (double-fire prevention). If `stop()` raises, abort the rebind and leave the previous watcher running — surface the error in the API response.
3. **One-shot sync on rebind.** Immediately after the new watcher is started, trigger a `startup_sync`-equivalent single-pass sync for the new project (reusing the existing `_run_startup_sync_pipeline` path or a light equivalent) so the `sessions` table is refreshed without waiting for the first file event.
4. **Observable runtime state.** After a successful rebind, `GET /api/health/detail` must return the new project's paths in `detail.watcher.watchPaths` (the field already exists at `backend/adapters/jobs/runtime.py:308` and `backend/runtime/container.py:916`).
5. **Integration test.** A test in `backend/tests/` that uses `AsyncClient` to: switch active project via `POST /api/projects/active/{id}`, assert `GET /api/health/detail` reflects the new `watchPaths`, then create/copy a synthetic JSONL session file into the new project's sessions directory and assert the row appears in the `sessions` table within the debounced sync window.

### Out of Scope

- Multi-project simultaneous watching (watching N projects at once). The `watchfiles.awatch` API supports multiple paths, but that topology is reserved for a future Tier 2 or Tier 3 decision when widget requirements firm up (see spike §4 Option (b)).
- Backfill sweep of all historical non-active-project session rows. Lazy or scheduled re-scan of non-active projects is a separate concern; this contract only ensures the newly active project is fresh immediately.
- Migrating the global singleton pattern of the `FileWatcher` instance (imported as `file_watcher` in `backend/db/file_watcher.py`). The singleton is retained; this contract only changes when and how `start()`/`stop()` are called.
- Changes to the `sessions.status` stale-flag display in the system-wide metrics surface (that belongs to the Tier 2 system-wide metrics PRD, which depends on this contract as a precondition).

---

## 5. UX / Behavior Requirements

- After the user selects a different project from the project picker (which calls `POST /api/projects/active/{id}`), subsequent data visible in the UI (session list, live counts, analytics) must reflect the new project within the normal polling interval — not the previous project.
- The API response from `POST /api/projects/active/{id}` must not be delayed by the rebind beyond the current response time budget. The rebind is initiated asynchronously after the response is returned, OR the response waits for rebind completion and returns a 4xx if the new project's paths do not exist (see AC-4 below). Choose the synchronous path for simplicity and predictability; document the choice in the Completion Report.
- If the watcher rebind fails because the new project's paths do not exist on the filesystem, the response from `POST /api/projects/active/{id}` must return HTTP 4xx (422 or 404 are both acceptable), and the watcher must remain bound to the previous project's paths without entering a half-rebound state.
- `GET /api/health/detail` reflects the rebind outcome — either updated `watchPaths` pointing at the new project, or unchanged paths with an error indicator if the rebind failed.

---

## 6. Data Requirements

- **Entities affected**: `sessions` table rows for the newly active project.
- **New fields**: None. `file_watcher.py`'s `FileWatcherSnapshot` already carries `project_id` and `watch_paths`; the rebind updates those in-place.
- **State changes**:
  - `FileWatcher._snapshot.project_id` transitions to the new project ID.
  - `FileWatcher._snapshot.watch_paths` transitions to the new project's resolved paths.
  - `RuntimeJobAdapter.state.watcher_started` remains `True` throughout a successful rebind.
- **Storage implications**: No schema migration required. The one-shot sync after rebind writes to the existing `sessions` table via the existing `SyncEngine.sync_changed_files` / `SessionsRepository.upsert` path. No new indexes are required for this contract (the composite index proposed in the spike is deferred to the Tier 2 live-counts contract).

---

## 7. API / Integration Requirements

**Modified endpoints:**

- `POST /api/projects/active/{project_id}` (`backend/routers/projects.py:124–150`) — gains a watcher rebind step after calling `workspace_registry.set_active_project(project_id)`. The response body is unchanged; add a field `watcherRebound: bool` to the existing JSON response so callers can confirm the rebind occurred. If rebind is not yet complete (async path), return `watcherRebound: null`.

**Unchanged endpoints (observable, not modified):**

- `GET /api/health/detail` (`backend/runtime/bootstrap.py:93`) — already returns `detail.watcher.watchPaths`. No structural change; the field's value changes as a result of the rebind.

**Internal service dependencies:**

- `backend/db/file_watcher.py` — `FileWatcher.stop()` and `FileWatcher.start(...)` lifecycle methods. Both are already `async`; the rebind logic calls them in sequence.
- `backend/adapters/jobs/runtime.py` — `RuntimeJobAdapter._run_startup_sync_pipeline` (or a light equivalent) for the one-shot sync.
- `backend/project_manager.py` — `ProjectManager.get_project(project_id)` to resolve the new project's `sessions_dir`, `docs_dir`, and `progress_dir` before calling `file_watcher.start(...)`.

**New dependencies:** None.

---

## 8. Architecture Constraints

**Must follow existing patterns in:**
- `backend/adapters/jobs/runtime.py` — the `start()` / `stop()` watcher lifecycle methods are already called here; any rebind logic lives in the same adapter, not in a router.
- `backend/runtime/container.py` — `RuntimeContainer` is the DI root; if direct invocation is used instead of a callback, access it via `request.app.state.runtime_container` (the existing pattern in `bootstrap.py`), not by importing the container globally.
- `backend/application/ports` — if a callback/observer pattern is chosen, define the interface in `backend/application/ports/core.py` (or a new `ports/workspace.py`) following the existing `CorePorts`/`ProjectBinding` pattern, not as a concrete dependency between adapters.
- Transport-neutral agent queries (`backend/application/services/agent_queries/`) — no new query surfaces for this contract; diagnostics are served through the existing `GET /api/health/detail`.

**Must not change (protected areas):**
- `FileWatcher.snapshot()` return shape (`watchPaths`, `projectId`, etc.) — consumers including `RuntimeJobAdapter.observe_runtime()` and `GET /api/health/detail` depend on this shape.
- `sessions` table schema and `SessionsRepository.upsert` signature.
- Existing `startup_sync` flow for the initial project at server boot — this contract adds a rebind path; it does not alter the startup path.
- `LocalWorkspaceRegistry` public interface beyond adding an optional observer registration method.

**New dependencies:** None.

---

## 9. Acceptance Criteria

#### AC-1: Health detail reflects new project paths after switch
- target_surfaces:
    - backend/adapters/jobs/runtime.py (RuntimeJobAdapter.observe_runtime — watcher snapshot)
    - GET /api/health/detail → detail.watcher.watchPaths
- propagation_contract: `POST /api/projects/active/{id}` triggers `file_watcher.stop()` then `file_watcher.start(new_project_id, new_sessions_dir, new_docs_dir, new_progress_dir, ...)` inside `RuntimeJobAdapter`; `snapshot()` is updated synchronously before `start()` returns.
- resilience: If the new project's paths do not exist, `watchPaths` remains unchanged and `lastSyncError` is populated.
- visual_evidence_required: false
- verified_by: [integration-test-switch-project, smoke-ui-project-picker]

- [ ] After `POST /api/projects/active/{id}` returns 2xx, `GET /api/health/detail` reflects the new project's `sessions_dir`, `docs_dir`, and `progress_dir` in `detail.watcher.watchPaths` within 2 seconds (measured from the `POST` response timestamp).

#### AC-2: New session in newly active project is picked up within sync latency budget
- target_surfaces:
    - backend/db/file_watcher.py (_watch_loop → sync_engine.sync_changed_files)
    - backend/db/repositories/sessions.py (SessionsRepository.upsert)
- propagation_contract: `watchfiles.awatch` emits change events; `_watch_loop` classifies and calls `sync_changed_files`; `upsert` writes the row. The one-shot sync after rebind covers files that exist before the watcher loop starts.
- resilience: FE session list must handle empty session table for a newly active project gracefully (existing empty-state handling applies).
- visual_evidence_required: false
- verified_by: [integration-test-session-pickup]

- [ ] A new JSONL session file created in the newly active project's `sessions_dir` after the rebind appears as a row in the `sessions` table within the `watchfiles` debounced change interval (the `awatch` default — no explicit debounce constant is set in `backend/db/file_watcher.py`, so the upstream `watchfiles` default of ~300 ms applies). The one-shot sync covers session files that existed before the watcher started.

#### AC-3: Mid-switch event loss is bounded
- target_surfaces:
    - backend/db/file_watcher.py (stop → task cancel → drain)
    - backend/adapters/jobs/runtime.py (rebind sequence)
- propagation_contract: `stop()` cancels the `asyncio.Task` wrapping `_watch_loop`; `awatch` cancellation does not guarantee delivery of in-flight change batches. **Chosen behavior: drain-before-rebind.** Before calling `file_watcher.stop()`, the rebind logic calls a one-shot `sync_engine.full_sync(old_project_id, ...)` (or equivalent) to flush any pending state for the outgoing project. This is documented in the Completion Report.
- resilience: Events from the previous project that are mid-flight at the moment of `task.cancel()` may be lost. This is acceptable because the drain step minimizes the window. The contract does not guarantee zero loss, only bounded loss.
- visual_evidence_required: false
- verified_by: [integration-test-switch-project]

- [ ] No in-flight events from the previous project are silently dropped without a prior drain/flush attempt. The Completion Report documents the drain strategy chosen (drain-before-rebind, cancel-and-accept-loss, or otherwise) with justification.

#### AC-4: Failed rebind leaves watcher on previous project; API returns 4xx
- target_surfaces:
    - POST /api/projects/active/{id} response
    - backend/adapters/jobs/runtime.py (watcher state after failed rebind)
- propagation_contract: If `file_watcher.start(new_project)` encounters no existing watch paths (all dirs missing), `stop()` is called only after `start()` confirms it can proceed. If `stop()` has already been called and `start()` fails, `RuntimeJobAdapter` must re-start the watcher on the old project's paths (rollback).
- resilience: `watcher_started` state must remain `True` after rollback; `watchPaths` must reflect the old project's paths.
- visual_evidence_required: false
- verified_by: [integration-test-bad-project-paths]

- [ ] If `POST /api/projects/active/{id}` is called with a project whose `sessions_dir` / `docs_dir` do not exist on disk, the API returns HTTP 4xx (404 or 422), `GET /api/health/detail` still shows the previous project's `watchPaths`, and no half-rebound state occurs (the watcher is running and watching the previous project's paths).

#### AC-5: Integration test exercises full switch end-to-end
- target_surfaces:
    - backend/tests/ (new test file or new test case in existing integration suite)
- propagation_contract: Test uses in-process `AsyncClient` (or `httpx.AsyncClient` against a test app instance), synthetic temp dirs for sessions, and the existing SQLite test DB setup.
- resilience: N/A — test infrastructure.
- visual_evidence_required: false
- verified_by: [pytest backend/tests/ -k watcher_rebind]

- [ ] A test in `backend/tests/` (named `test_watcher_rebind.py` or similar) passes `pytest backend/tests/ -k watcher_rebind` and covers:
  - Successful switch: `watchPaths` updates, one-shot sync populates the `sessions` table.
  - Failed switch (bad paths): API returns 4xx, watcher remains on old project.
  - (Optional, if feasible in unit-test context) Mid-switch drain: previous project's session row is present after the switch.

#### AC-6: Runtime smoke — project picker switch flows to new project
- target_surfaces:
    - frontend project picker (UI component that calls POST /api/projects/active/{id})
    - GET /api/health/detail (observable via browser dev tools Network tab)
- propagation_contract: User action in UI → fetch POST → backend rebind → subsequent GET /api/sessions or GET /api/health/detail returns new project data.
- resilience: N/A — smoke test.
- visual_evidence_required: false
- verified_by: [smoke-ui-project-picker]

- [ ] With the dev server running (`npm run dev`), switch projects via the UI project picker. Observe in the browser Network tab that a subsequent `GET /api/health/detail` (polled by the frontend runtime health check) returns `watchPaths` matching the new project's paths. Verify session events in the session list are from the newly active project, not the previous one.

---

## 10. Validation Requirements

- [ ] **Typecheck** passes: `backend/.venv/bin/python -m mypy backend/` (or equivalent type check for modified files — match whatever the CI baseline is for the backend).
- [ ] **Lint** passes: `flake8` or `ruff` over modified files — no new lint violations.
- [ ] **Tests added**: `backend/tests/test_watcher_rebind.py` (or equivalent) with at minimum the two cases from AC-5.
- [ ] **Existing tests pass**: `backend/.venv/bin/python -m pytest backend/tests/ -v` — no regressions in `test_runtime_bootstrap`, `test_mcp_server`, or any test touching `file_watcher`, `sync_engine`, or `projects` router.
- [ ] **Build passes**: `npm run build` succeeds (no FE changes expected; this is a regression guard).
- [ ] **CHANGELOG updated**: A `[Unreleased]` entry is added under the `Fixed` category describing that session data now reflects the active project correctly after a project switch. See `.claude/specs/changelog-spec.md` for categorization rules.
- [ ] **No unrelated changes** introduced. Scope drift must be documented in the Completion Report.

---

## 11. Risk Areas

- **Thread/async safety of watcher stop/start.** `FileWatcher.stop()` cancels an `asyncio.Task` and awaits the cancellation. If `stop()` is called from within the event loop while the task is also awaiting `awatch(...)`, the cancel propagates as `CancelledError` through `watchfiles`. This is the expected path and is tested by the existing `stop()` implementation, but the rebind adds a new caller context (a router coroutine, not a shutdown handler). Verify that `stop()` followed immediately by `start()` does not leave the `_running` flag or `_task` in an inconsistent state. Guard with `_running = False` before `_task.cancel()` (already the case in current `stop()` at `file_watcher.py:139`).

- **Listener registration leaks on repeated rebinds.** If a callback/observer approach is used to notify `RuntimeJobAdapter` from `LocalWorkspaceRegistry`, repeated project switches must not register the same callback multiple times. Use a single-slot observer (`_on_active_changed: Callable | None`) rather than a list; re-registering overwrites the previous callback. Alternatively, the direct-invocation approach (calling `runtime_container.job_adapter.rebind_watcher(...)` from the router) avoids the registration concern entirely.

- **Double-fire window.** If the rebind starts the new watcher before the old one is fully stopped, both tasks could fire `sync_changed_files` simultaneously. The guard is strict sequencing: await `file_watcher.stop()` before calling `file_watcher.start()`. Current `stop()` awaits `task.cancel()` and sets `_running = False` before returning — confirm this is sufficient to prevent the new `_watch_loop` from racing the old one.

- **Failed rebind leaving both watchers dead.** If `stop()` succeeds but `start()` fails (e.g., all paths missing), the watcher is in a stopped state with no rollback. The rollback path (re-start on the old project) requires the old project's path configuration to be preserved before `stop()` is called. Capture `old_project_id` and old paths from `file_watcher.snapshot()` before the rebind sequence; use them to re-invoke `file_watcher.start()` in the exception handler.

- **One-shot sync contention.** The post-rebind one-shot sync runs in the same event loop as the new watcher's `_watch_loop`. If a file change arrives immediately after the watcher starts, both the one-shot sync and the watcher-driven sync may call `sync_changed_files` concurrently. The `SyncEngine` must be re-entrant or the one-shot sync must be serialized via the existing `asyncio.Lock` already present in `sync_engine.py` (verify this lock exists; if not, add one to `sync_changed_files`).

---

## 12. Implementation Notes

**Suggested approach:**

1. **Preserve old-project snapshot before rebind.** At the start of the rebind, call `file_watcher.snapshot()` and capture `old_project_id` and `old_watch_paths`. This is the rollback target.

2. **Resolve new project paths.** Call `ProjectManager.get_project(new_project_id)` (available via `CorePorts.workspace_registry` → `LocalWorkspaceRegistry` → `LocalProjectManager`) to get `sessions_dir`, `docs_dir`, `progress_dir`. If any required path is missing, return a 4xx immediately — do not proceed to `stop()`.

3. **Drain the outgoing project.** Before `stop()`, optionally trigger a light sync for the outgoing project so recent changes are not lost. Evaluate whether `sync_engine.sync_planning_artifacts(old_project_id, ...)` is sufficient or a full `sync_all` is needed. If the cost is too high, document "cancel-and-accept-loss" in the Completion Report.

4. **Stop → Start atomically.** `await file_watcher.stop()` then `await file_watcher.start(sync_engine, new_project_id, sessions_dir, docs_dir, progress_dir)`. Wrap in `try/except`; on `start()` failure, re-invoke `file_watcher.start(old_project_id, old_paths...)` as rollback.

5. **One-shot sync for new project.** After `file_watcher.start()` returns, call the startup sync pipeline (or a trimmed equivalent) with `new_project_id`. This ensures the `sessions` table is populated before the first watcher event fires.

6. **Wire the rebind call site.** The cleanest non-circular path is to add a `async def rebind_watcher(self, new_project_id: str) -> None` method to `RuntimeJobAdapter` and call it from `backend/routers/projects.py` via `request.app.state.runtime_container.job_adapter.rebind_watcher(new_project_id)`. This avoids a new abstract port for a single call site.

**Similar existing code:**
- Reference: `backend/adapters/jobs/runtime.py:110–190` (`RuntimeJobAdapter.start()`) — the existing startup sequence for watcher + sync is the template for the rebind sequence.
- Reference: `backend/adapters/jobs/runtime.py:190–235` (`RuntimeJobAdapter.stop()`) — the teardown sequence that calls `file_watcher.stop()`.
- Reference: `backend/runtime/bootstrap.py:93` — how `app.state.runtime_container` is accessed from a router context.

**Known gotchas:**
- `FileWatcher.start()` early-returns with a warning (not an exception) if `_running` is already `True` (`file_watcher.py:83–88`). After `stop()` sets `_running = False`, the subsequent `start()` call will proceed normally — but if `stop()` is somehow skipped, the guard will silently no-op. Add an assertion or explicit check in the rebind path.
- The `awatch` call in `_watch_loop` does not use a `stop_event` in the current implementation (`file_watcher.py:183` passes `stop_event=asyncio.Event() if not self._running else None` — this evaluates to `None` when `_running` is `True` at loop start, meaning cancellation relies solely on `task.cancel()`). This is fine; `CancelledError` propagates correctly through `async for`.
- `watchfiles` will raise if all supplied watch paths are non-existent. The `_resolve_watch_paths` helper at `file_watcher.py:90–96` filters to existing paths; the existing early-return guard handles the all-missing case. The rebind path should rely on this same guard — if `_resolve_watch_paths` returns an empty list for the new project, surface a 4xx before `stop()` is called.

---

## 13. Completion Report Required

The executing agent must produce a Completion Report including:

- **Files changed**: List of all modified/new files with brief reason.
- **Tests run**: `pytest backend/tests/ -k watcher_rebind -v` output and overall suite pass status.
- **Validation results**: Table of all validation commands (mypy, lint, pytest, build) and pass/fail.
- **Drain strategy chosen**: Document which of drain-before-rebind, cancel-and-accept-loss, or a hybrid was implemented and why.
- **Rebind call site pattern chosen**: Document whether callback/observer or direct-invocation was used and why.
- **Deviations from contract**: Any material changes and justification.
- **Risks / Limitations**: Any remaining risks (e.g., race conditions not fully closed, rollback not tested for all failure modes).
- **Follow-up recommendations**: At minimum, note the Tier 2 system-wide metrics PRD as the next dependent item, and flag whether the composite index from spike §3 OQ-3b should be added as a Tier 0 or bundled into the Tier 2 contract.

See `.claude/skills/dev-execution/validation/completion-criteria.md` for the full Completion Report template.

---

## Metadata & References

**Tier**: 1 (5 points)

**Execution Mode**: Autonomous Feature Sprint (Mode C) — single sprint to completion, no phase orchestration.

**Reviewer**: `task-completion-validator` (mandatory before Opus commits).

**Related Documents**:
- `.claude/worknotes/system-wide-live-metrics-spike/spike.md` — OQ-3 / OQ-3a Runtime Verification (2026-05-20) is the primary evidence for this bug.
- `backend/db/file_watcher.py` — watcher lifecycle implementation.
- `backend/adapters/jobs/runtime.py` — `RuntimeJobAdapter` watcher start/stop orchestration.
- `backend/routers/projects.py:124–150` — `set_active_project` router endpoint.
- `backend/adapters/workspaces/local.py:27–28` — `LocalWorkspaceRegistry.set_active_project`.
- `backend/runtime/container.py` — DI container and `app.state.runtime_container` access pattern.

**Precondition for**:
- Tier 2 PRD: system-wide live metrics (`docs/project_plans/PRDs/features/system-wide-metrics-v1.md`, not yet authored) — the cross-project live-agent counts in that PRD depend on watcher state reflecting the correct active project.

---

## Notes for Agents

This contract is your specification. Implement to satisfy the acceptance criteria and pass validation. If you find:

- **Scope ambiguity**: Make a conservative assumption and document it in the Completion Report rather than asking. The drain strategy and call-site pattern are the two most likely decision points — the Implementation Notes section gives directional guidance, but you may deviate with justification.
- **Impossible constraints**: Flag in the Completion Report before attempting workarounds. The rollback-on-failed-start requirement (AC-4) is the most likely candidate for complexity — document the trade-off if a simplified approach is taken.
- **Better implementation path**: Document the deviation in the Completion Report with justification. The suggested rebind approach (direct `RuntimeJobAdapter.rebind_watcher(...)` call from the router) is preferred but not mandatory if a cleaner seam exists.

Stay within scope. Do not add new observability surfaces, new CLI commands, or new query services in this sprint — those belong to the Tier 2 contract. The reviewer will check for scope drift.
