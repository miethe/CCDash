# Multi-Project Investigation: Registration, Path Resolution, Session Mapping, Worker Scoping

**Domain**: multi-project
**Investigator**: claude-sonnet-4-6 (subagent)
**Date**: 2026-05-30
**Scope**: backend/project_manager.py, projects.json, backend/routers/projects.py, backend/routers/session_mappings.py, backend/db/sync_engine.py, backend/db/file_watcher.py, backend/adapters/jobs/runtime.py, backend/runtime/container.py, packages/ccdash_cli/src/ccdash_cli/commands/project.py, backend/cli/main.py, backend/application/services/agent_queries/multi_project_planning_command_center.py

---

## Executive Summary

CCDash has a partially multi-project-aware data model but fundamentally single-active-project runtime semantics. The DB schema properly partitions most data by `project_id`, the transport layer accepts a `X-CCDash-Project-Id` header, and the MPCC service fans out across all projects. However, the entire ingestion pipeline (file watcher, sync engine, startup sync) processes exactly one project at a time — the "active" project resolved at startup. Workers are bound to a single project via `CCDASH_WORKER_PROJECT_ID`. The enterprise/containerized edition therefore cannot ingest or watch multiple projects concurrently without deploying N separate worker processes — one per project. `projects.json` is a mutable file on the host that becomes a distributed-state problem in containers. Session IDs are globally unique keys (not `(project_id, session_id)`), creating a latent data-corruption risk if two projects ever share a session file.

---

## 1. Project Registration and State Storage

### Where State Lives

**File**: `backend/project_manager.py:287`
```python
project_manager = ProjectManager(config.PROJECT_ROOT / "projects.json")
```

All project registrations are persisted in `projects.json` at the repo root (`backend/project_manager.py:140-147`). The file contains:
- `activeProjectId` (process-global, single-value pointer)
- `projects[]` array with full path configs

**projects.json** currently has **5 projects** (lines confirmed via `python3` inspection):
- `default-skillmeat` at `CCDash/examples/skillmeat`
- `test-project-1` at `/tmp/test-project-1`
- `3df0ff70` — **active** — "SkillMeat" at `/Users/miethe/dev/homelab/development/skillmeat`
- `3da60e0c` — "CCDash" at `/Users/miethe/dev/homelab/development/CCDash`
- `479ae45d` — "MeatyWiki" at `/Users/miethe/dev/homelab/development/meatywiki`

**Critical enterprise gap**: `projects.json` is a flat file at `config.PROJECT_ROOT / "projects.json"` (repo root). In a containerized deployment there is no mechanism to mount or sync this file across replicas. Each API pod would fork from an independent copy. Mutations (add/switch) would diverge immediately. There is no DB-backed project registry.

### `_save()` is Synchronous and Unguarded

`backend/project_manager.py:140-147`:
```python
def _save(self):
    data = {
        "activeProjectId": self._active_project_id,
        "projects": [p.model_dump() for p in self._projects.values()]
    }
    self.storage_path.write_text(json.dumps(data, indent=2))
```

This is a synchronous `write_text` called from async context (e.g., `set_active_project` called by an async endpoint). There is no file lock, no atomic write (no temp-file + rename), and no concurrency guard. Concurrent writes from two requests racing to switch project will produce a torn file.

---

## 2. Active Project Resolution: Single-Active Assumption

The system has exactly one `_active_project_id` stored in `projects.json`. Every request without an explicit `X-CCDash-Project-Id` header falls back to this single global pointer:

**`backend/project_manager.py:192-195`**:
```python
def get_active_project(self) -> Optional[Project]:
    if self._active_project_id:
        return self._projects.get(self._active_project_id)
    return None
```

**`backend/application/services/common.py:93-120`** — `resolve_project()`:
```
1. Explicit requested_project_id → get by ID
2. context.project (from X-CCDash-Project-Id header or JWT claim) → get by ID
3. Hosted principal without project → 404
4. Fallback: workspace_registry.get_active_project()
```

Step 4 is the dangerous global fallback. Without a project header, all API calls resolve to whichever project was last set active on the server — a process-global side-channel that is completely invisible to the caller.

**Hosted/Enterprise mode**: `backend/routers/projects.py:138-147` blocks `POST /api/projects/active/{id}` for hosted requests (returns HTTP 409). This is correct behavior, but it means there is no mechanism at all to switch the active project in enterprise mode — the per-request `X-CCDash-Project-Id` header must carry the project scope for every request.

**`backend/runtime/container.py:415-425`** — project_id extraction from request:
```python
def _request_project_id(self, metadata, claim_scope):
    header_project_id = self._header(metadata, "x-ccdash-project-id")
    if header_project_id:
        return header_project_id
    if claim_scope is None:
        return None
    return claim_scope.project_id or claim_scope.workspace_id
```

The header wins over JWT claims, which is correct. But if neither is present and `allow_active_fallback=True` (which it is for non-hosted principals), the global active project is used. In a containerized multi-project API serving concurrent requests from multiple projects, this is a silent data-routing bug.

**Frontend (`services/apiClient.ts:178-231`)**: The client stores the selected project in `localStorage` under `ccdash:selected-project-id:v2` and attaches it as `X-CCDash-Project-Id` header via `setApiProjectScope()`. This is correct for single-tab use. Multi-tab use with different projects in different tabs will use the same `localStorage` slot — last writer wins.

---

## 3. Session → Project Mapping: Path-Based Assignment at Ingest Time

Sessions are NOT mapped to projects by path analysis at query time. They are assigned a `project_id` at ingest time based on which project's `sessions_dir` the sync engine was scanning:

**`backend/db/sync_engine.py:4107-4119`** — `_sync_sessions`:
```python
async def _sync_sessions(self, project_id: str, sessions_dir: Path, force: bool) -> dict:
    for jsonl_file in sorted(self._rglob(sessions_dir, "*.jsonl"), ...):
        await self._sync_single_session(project_id, jsonl_file, force)
```

The `project_id` is inherited from the caller (`sync_project` → `_sync_sessions`), which receives it from the active project binding at startup. There is no path analysis to discover which project a session JSONL file belongs to.

**`backend/db/repositories/sessions.py:20-87`** — `upsert()`:
```python
INSERT INTO sessions (id, project_id, ...) VALUES (?, ?, ...)
ON CONFLICT(id) DO UPDATE SET ...
```

**Critical schema gap**: The `sessions` table has `id TEXT PRIMARY KEY` (global uniqueness). The `ON CONFLICT(id)` clause does NOT include `project_id`. If two projects ever share a session ID (e.g., from symlinked directories, shared `.claude/` parent, or copy of session data), the second sync will silently overwrite the first project's session with the second project's `project_id`. The session is "stolen" from project A to project B with no error.

**`session_logs`, `session_tool_usage`, `session_file_updates`, `session_artifacts` have no `project_id` column**. All queries are `WHERE session_id = ?`. These tables have no project-level isolation at all — a cross-project session ID collision is undetectable.

---

## 4. Ingestion and Sync: Single-Project-at-a-Time

### Startup Sync

**`backend/adapters/jobs/runtime.py:118-196`** — `RuntimeJobAdapter.start()`:
```python
resolved_binding = workspace_registry.resolve_project_binding()  # active project only
# ...
await self.sync.sync_project(active_project, sessions_dir, docs_dir, progress_dir, ...)
```

Only the active project is synced at startup. All other registered projects are not synced, not watched, and will have stale (or empty) data in the DB until the active project is switched to them and a sync is triggered.

### File Watcher

**`backend/db/file_watcher.py:307`**:
```python
file_watcher = FileWatcher()  # module-level singleton
```

There is exactly one `FileWatcher` instance for the entire process. It watches exactly one set of paths (one project's sessions/docs/progress dirs) at a time. Switching projects stops the watcher and restarts it on the new project's paths (`rebind_watcher`).

**Consequence**: In a 5-project deployment, 4 projects receive zero real-time updates at any given time. Their data in the DB is frozen at the last sync timestamp.

### Worker Binding

**`backend/runtime/container.py:1111-1142`** — `_resolve_startup_project_binding()`:
```python
if self.profile.name not in {"worker", "worker-watch"}:
    return None
binding_config = config.resolve_worker_binding_config()
if not binding_config.configured:
    raise RuntimeError(f"... requires a non-empty {config.CCDASH_WORKER_PROJECT_ID_ENV}")
```

The worker runtime REQUIRES `CCDASH_WORKER_PROJECT_ID` env var. One worker = one project. To watch N projects in enterprise mode, you must run N worker containers, each with a different `CCDASH_WORKER_PROJECT_ID`.

**`backend/config.py:149,409`**:
```python
CCDASH_WORKER_PROJECT_ID_ENV = "CCDASH_WORKER_PROJECT_ID"
project_id=str(env.get(CCDASH_WORKER_PROJECT_ID_ENV, "")).strip(),
```

There is no configuration for multiple project IDs or a "watch all" mode.

### Analytics Snapshot and Cache Warming: Single Active Project

**`backend/adapters/jobs/runtime.py:793-838`** — periodic analytics:
```python
current_project = bound_project or workspace_registry.get_active_project()
```

Both the analytics snapshot task and the cache warming task use `get_active_project()` as their fallback. In an enterprise multi-project deployment where the "active project" is undefined (no mutations allowed), these jobs silently no-op.

---

## 5. Isolation Gaps and Blast Radius

### Gap 1: No Cross-Project Query Isolation at API Layer

Most endpoints use `resolve_project()` which falls back to the global active project. Without the `X-CCDash-Project-Id` header, all requests from all clients will route to the same project. A large-dataset project (e.g., skillmeat with a 10 GB SQLite DB) being the active project means all other projects' requests also hit slow queries against that project's rows.

### Gap 2: Shared SQLite Connection (10 GB DB)

**`backend/db/connection.py`** provides a singleton connection. With a 10 GB SQLite database and a 1.7 MB WAL, all projects share the same write-ahead log. A large sync for one project (e.g., full scan of skillmeat's sessions) will block writes for all other projects and all API reads that need consistent data.

### Gap 3: No Per-Project Sync Concurrency Limit

**`backend/db/sync_engine.py:4107-4119`** iterates all `*.jsonl` files in `sessions_dir` synchronously within a single async task. A large project scan (thousands of JSONL files) occupies the event loop (via `asyncio.to_thread`) and blocks other project syncs or API queries.

### Gap 4: `_rglob_cache` is Instance-Level (Not Project-Scoped)

**`backend/db/sync_engine.py:2994`**:
```python
self._rglob_cache = {}
```

The rglob memo table is reset at the start of each `sync_project` call. In a hypothetical concurrent multi-project sync, cache entries from one project would intermix with another. (Currently not a race condition because syncs are sequential, but will become one when parallelized.)

### Gap 5: `session_mappings` Table is Project-Scoped, But Diagnostics Are Not

**`backend/routers/session_mappings.py:165-172`** — diagnostics fetches up to 200 sessions using `project.id` for pagination, but the individual log queries (`repo.get_logs(session_id)`) are NOT project-scoped (just `WHERE session_id = ?`). If a session ID collision exists, the diagnostics endpoint would silently analyze the wrong project's logs.

### Gap 6: `analytics_snapshot_task` Warms Only One Project's Cache

**`backend/adapters/jobs/runtime.py:878-877`**:
```python
_project_status_svc = ProjectStatusQueryService()
_workflow_svc = WorkflowDiagnosticsQueryService()
...
await _project_status_svc.get_status(context, self.ports)
await _workflow_svc.get_diagnostics(context, self.ports)
```

Cache warming constructs a single `RequestContext` from the active/bound project and warms only that project's query cache slots. The other N-1 projects get cold cache on every request.

---

## 6. The Watcher Rebind Fix (commit b1c83e4)

The recent `rebind_watcher` feature (`backend/adapters/jobs/runtime.py:198-338`) correctly implements atomic stop→drain→start for switching the single watcher to a new project. Acceptance criteria AC-1 through AC-4 are verified. This is **completed and correct** for single-active-at-a-time semantics.

However, it does not change the fundamental architecture: there is still only one watcher. The fix is a quality improvement for local mode users who switch projects frequently; it does not enable concurrent multi-project watching.

**Concurrent rebind race** (noted in the completion report, line 73): no mutex guards `rebind_watcher`. Two simultaneous `POST /api/projects/active/` calls can race. For enterprise multi-operator mode this is a correctness issue, not just a risk.

---

## 7. Multi-Project MPCC: What IS Working

**`backend/application/services/agent_queries/multi_project_planning_command_center.py`** implements a genuine multi-project fan-out:
- `list_projects()` returns all registered projects
- Fan-out uses `asyncio.gather` with a semaphore (`_MAX_CONCURRENCY=4`)
- Git probes are deferred for off-page items (MPCC-206 pattern)
- Project summaries use `count_active` per project
- `ProjectWarning` is emitted per-project on failure so other projects proceed

This surface **works correctly** for read queries because it queries the DB by `project_id`. The limitation is that the DB data itself may be stale if a project's worker hasn't run recently.

---

## 8. Enterprise Container Failure Mode: Why Live Data Was Missing

**Root cause**: When containerized, `CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED` defaults to `False` (`backend/config.py:246`). With `filesystem_source_of_truth=False` (enterprise profile), the sync engine is disabled:

**`backend/runtime/container.py:237-242`**:
```python
def _sync_engine_enabled(self) -> bool:
    if not self.profile.capabilities.sync:
        return False
    if self.storage_profile.profile == "local":
        return True
    return bool(self.storage_profile.filesystem_source_of_truth)
```

In enterprise mode without explicitly enabling `CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED=true`, no sync engine is built, no startup sync runs, and no file watcher starts. The DB stays empty. This is the container mode failing silently — the operator must know to set this flag, and there is no warning emitted at startup for "enterprise + no ingestion + empty DB."

---

## 9. Frontend: Project Switching Side-Effects

**`contexts/AppSessionContext.tsx:20-75`** — `activeProject` state:
- On mount: fetches `/api/projects` and `/api/projects/active`
- `switchProject()` calls `POST /api/projects/active/{id}` then calls `setApiProjectScope(project.id)` to update the header

The TanStack Query cache is NOT invalidated project-specifically on switch. All cached queries for the previous project remain stale in the client cache. The next polling cycle will re-fetch with the new project header, but there's a window (up to `staleTime` seconds) where the UI shows data from the old project with a new project label.

---

## 10. Gaps for Enterprise Multi-Project Command Center

| Gap | Severity | Notes |
|-----|----------|-------|
| `projects.json` is a local file; no DB-backed registry | Critical | Breaks in multi-replica containers |
| Single worker per project (`CCDASH_WORKER_PROJECT_ID`) | Critical | N projects → N worker processes, no orchestration |
| No "watch all" mode; watcher is a singleton | High | N-1 projects always have stale data |
| Enterprise profile disables ingestion by default (silent) | High | Was the container failure root cause |
| Session primary key is globally unique (not per-project) | High | Cross-project ID collision = silent data corruption |
| `session_logs` has no `project_id` column | High | Isolation is only at `sessions` table level |
| Active-project global fallback bypasses project isolation | High | Multi-tenant API routes all anonymous requests to one project |
| No per-project analytics warming; warm only active project | Medium | 4 of 5 projects get cold cache on every request |
| Concurrent `rebind_watcher` has no mutex | Medium | Race condition in multi-operator scenarios |
| `_rglob_cache` not project-scoped | Low | Latent race for future parallel syncs |
| TanStack Query cache not invalidated on project switch | Low | Stale UI data window after switch |
