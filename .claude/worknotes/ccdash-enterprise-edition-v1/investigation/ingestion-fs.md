# Ingestion / Filesystem Domain — Enterprise Edition Investigation

**Date**: 2026-05-30
**Scope**: Session JSONL ingest, sync engine, file watcher, container path access, live ingest failure theory
**DB context**: 10 GB SQLite WAL at `data/ccdash_cache.db`; enterprise target is PostgreSQL

---

## Root-Cause Theory: Why Containerized Mode FAILED to Pull Live Session Data

The container live-data failure is the convergence of **four independent defects**, each of which is sufficient on its own to cause silent ingest failure:

### Defect 1 — `CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED` defaults to `false` (CRITICAL)

**Evidence**: `backend/config.py:244–246`

```python
filesystem_source_of_truth = profile == "local"
if profile == "enterprise":
    filesystem_source_of_truth = _env_bool_from(env, "CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED", False)
```

And `backend/runtime/container.py:237–242`:

```python
def _sync_engine_enabled(self) -> bool:
    if not self.profile.capabilities.sync:
        return False
    if self.storage_profile.profile == "local":
        return True
    return bool(self.storage_profile.filesystem_source_of_truth)
```

**Impact**: When `CCDASH_STORAGE_PROFILE=enterprise` (or equivalently `CCDASH_DB_BACKEND=postgres`) and `CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED` is absent or `false`, `filesystem_source_of_truth=False`, which makes `_sync_engine_enabled()` return `False`. The `SyncEngine` is never instantiated (`container.py:204–207`). With no sync engine, no startup sync runs, no file watcher starts, and the system silently returns an empty-data API.

The `x-backend-service` anchor in `deploy/runtime/compose.yaml` sets `CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED: "${CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED:-false}"`. Any deployment where this variable is unset or not overridden will silently kill ingest with no error log.

The `worker-watch` service _does_ override it with `CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED: "${CCDASH_WORKER_WATCH_FILESYSTEM_INGESTION_ENABLED:-true}"` (`compose.yaml:~175`). But if the operator omits the `live-watch` profile, only the `enterprise` profile runs, and neither the `api` nor the default `worker` service override this to `true`.

**Severity**: CRITICAL. This is the most likely single cause of the reported container failure.

---

### Defect 2 — Source-path canonicalization produces `opaque/` keys when mount aliases are unconfigured (HIGH)

**Evidence**: `backend/services/source_identity.py:188–243`

The `resolve_source_identity()` function attempts to match an `observed_path` against configured `SourceRootAlias` entries. When no aliases match (policy has empty `aliases` tuple or the aliases don't cover the observed path), it falls back to a SHA-256 hash-based `opaque/` key (`source_identity.py:175–185`):

```python
def _opaque_source_key(...) -> SourceKey:
    digest = hashlib.sha256(observed_path.as_posix().encode("utf-8")).hexdigest()[:32]
    return SourceKey(f"{SOURCE_KEY_SCHEME}:{SOURCE_KEY_VERSION}/{project_id}/{artifact_kind}/opaque/{digest}")
```

The `source_identity_policy_from_env()` reads `CCDASH_WORKSPACE_HOST_ROOT`, `CCDASH_WORKSPACE_CONTAINER_ROOT`, `CCDASH_CLAUDE_HOME`, `CCDASH_CLAUDE_CONTAINER_HOME`, and up to 6 extra mount slots (`source_identity.py:271–308`).

**The critical gap**: When the container observes a file at e.g. `/home/ccdash/.claude/projects/-Users-miethe-.../session.jsonl`, but `CCDASH_CLAUDE_CONTAINER_HOME` is not set (or set to a different path), the alias lookup fails and the source key is `opaque/<hash>`. Meanwhile the previous sync run (local or prior run with different container paths) stored the record under a `claude_home/...` or `workspace/...` key. On re-sync, the sync state lookup (`_sync_single_session`: `sync_repo.get_sync_state(sync_file_path)`) uses the opaque key, finds no prior state, re-parses the file — but writes the new result under the opaque key. If later the alias IS configured, the same file gets a different key and is treated as a new session, resulting in duplicates. Conversely, `delete_by_source(str(path))` at `sync_engine.py:4171` passes the raw `str(path)` (absolute container path), not the canonical key — causing delete-by-source failures that leave stale rows after file deletion.

**Evidence for the delete-by-source path mismatch**: `sync_engine.py:3944` calls `await self.session_repo.delete_by_source(str(path))` (raw path), while `sync_engine.py:4171` calls `await self.session_repo.delete_by_source(sync_file_path)` (canonical key). The watcher-triggered delete path (`sync_changed_files` → line 3944) uses the raw string, not the canonical key. This means watcher-triggered deletes can leave orphaned DB rows.

**Severity**: HIGH. Silent data duplication and stale rows under path-remapping scenarios.

---

### Defect 3 — `watchfiles` inotify backend does not work on Docker Desktop bind mounts (HIGH)

**Evidence**: `backend/db/file_watcher.py:16,183`

```python
from watchfiles import awatch, Change
...
async for changes in awatch(*watch_paths, stop_event=...):
```

`watchfiles` defaults to `inotify` (Linux) or `kqueue` (macOS). Docker Desktop on macOS uses a virtual filesystem (VirtioFS or gRPC-FUSE) for bind mounts; inotify events are **not reliably delivered** through this layer. The watcher loop starts, logs "File watcher started", and then silently receives no events. The watcher is technically `running` (the health probe returns `running`), but filesystem changes never reach `sync_changed_files()`.

**Evidence from documentation**: `deploy/runtime/README.md:178` explicitly documents this failure mode and prescribes `WATCHFILES_FORCE_POLLING=true`. The compose file passes this only to `worker-watch` and defaults it to `false` (`compose.yaml:175`). Any developer running on macOS Docker Desktop without explicitly setting `WATCHFILES_FORCE_POLLING=true` will get a silent watcher that appears healthy but delivers no events.

**The `stop_event` bug**: `file_watcher.py:183` passes `stop_event=asyncio.Event() if not self._running else None`. When `self._running` is `True` (which it is at startup), `stop_event=None` is passed. This means the `awatch` call has no external stop mechanism; stopping the watcher relies entirely on `asyncio.CancelledError` from task cancellation. This is likely intentional, but worth noting for supervisor-style deployments.

**Severity**: HIGH. Silent watcher failure on macOS Docker Desktop / any bind-mount path that doesn't deliver inotify events.

---

### Defect 4 — `STARTUP_SYNC_LIGHT_MODE` default mismatch between `config.py` and `runtime.py` (MEDIUM)

**Evidence**:

- `backend/config.py:966`: `STARTUP_SYNC_LIGHT_MODE = _env_bool("CCDASH_STARTUP_SYNC_LIGHT_MODE", False)` — **default False**
- `backend/adapters/jobs/runtime.py:731`: `light_mode = bool(getattr(config, "STARTUP_SYNC_LIGHT_MODE", True))` — **getattr fallback True**

`getattr(config, "STARTUP_SYNC_LIGHT_MODE", True)` reads the module attribute which is `False` (from the env var default in config.py). The `True` fallback in `getattr` is never reached when the module loads successfully. However the semantics differ: if the attribute ever becomes unavailable (e.g., dynamic config reload, mock injection), the runtime defaults to `light_mode=True` while `config.py` defaults to `False`.

More importantly, the `_run_startup_sync_pipeline` at `runtime.py:731` treats `STARTUP_SYNC_LIGHT_MODE=True` as meaning:
1. Run only `sync_planning_artifacts` first
2. Pass `rebuild_links=False`, `capture_analytics=False`, `backfill_session_intelligence=False` to `sync_project`
3. Then run a deferred link rebuild after a stagger delay

When `light_mode=False` (the config default), `sync_project` gets `rebuild_links=True, capture_analytics=True, backfill_session_intelligence=True`. On a 10 GB db with thousands of sessions, this is a **blocking startup sync** that can take tens of minutes, during which the API is technically up but data is being written (under the local profile this is a serial SQLite write workload).

**Related**: `backend/db/sync_engine.py:4261` reads `light_mode: bool = bool(getattr(config, "STARTUP_SYNC_LIGHT_MODE", False))` — the `_sync_documents` call path uses `False` as the getattr fallback, diverging from the `runtime.py` fallback of `True`. These two fallback disagreements mean behavior depends on which code path reads the flag.

**Severity**: MEDIUM. Startup sync regression risk; full sync on large datasets blocks responsiveness. Also indicates the config flag is not a single source of truth.

---

## Additional Performance and Architecture Findings

### Finding 5 — Full filesystem scan on every startup with no incremental-only option (HIGH)

**Evidence**: `sync_engine.py:4107–4119`

```python
async def _sync_sessions(self, project_id: str, sessions_dir: Path, force: bool) -> dict:
    for jsonl_file in sorted(self._rglob(sessions_dir, "*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True):
        synced = await self._sync_single_session(project_id, jsonl_file, force)
```

This calls `rglob("*.jsonl")` over the entire `sessions_dir` on every startup sync. For the `skillmeat` project at `~/.claude/projects/-Users-miethe-dev-homelab-development-skillmeat`, this scans potentially thousands of JSONL files. Each `sync_single_session` call does `path.stat().st_mtime` and then `sync_repo.get_sync_state(sync_file_path)` — two I/O ops per file just to skip unchanged files. With a 10 GB SQLite WAL, the sync state lookups themselves are slow.

The light-mode scan skip (`_light_mode_scan_skip`) applies only to documents/progress (`.md` files), **not** to JSONL sessions. There is no equivalent manifest-based skip for sessions. On a directory with 5,000 JSONL files, startup will stat all 5,000 files + do 5,000 DB lookups before determining all are unchanged.

**Severity**: HIGH for large projects. A manifest/inode snapshot for sessions analogous to the document light-mode would reduce startup cost from O(n×2 I/O) to a single stat-walk comparison.

---

### Finding 6 — Per-run `_rglob_cache` does not span `sync_sessions` and `sync_documents` call chains under `sync_project` (LOW)

**Evidence**: `sync_engine.py:1277–1290,2992–2994`

The `_rglob_cache` is reset at the start of `sync_project` (`self._rglob_cache = {}`). Within a single `sync_project` call, multiple phases (documents, progress, features) that use the same root with the same pattern pay the OS traversal cost only once. However `_sync_sessions` uses `_rglob(sessions_dir, "*.jsonl")` and document phases use `_rglob(root, "*.md")` — these are different patterns and roots, so the cache does not overlap between phases. The memo is still beneficial for the document/feature/progress phases that share roots, but the benefit is partial.

---

### Finding 7 — Watcher-triggered `delete_by_source` uses raw path strings, not canonical source keys (HIGH)

**Evidence**: `sync_engine.py:3943–3945`

```python
if path.suffix == ".jsonl":
    sync_state_key = self._canonical_source_key(project_id, path, "session")
    await self.sync_repo.delete_sync_state(sync_state_key)
    # ...
    await self.session_repo.delete_by_source(str(path))  # <-- raw path, not canonical key
```

The sync state is deleted by canonical key, but the session repo is deleted by raw string path. If `session_repo.delete_by_source` filters on `source_file` stored as the canonical key (`ccdash-source:v1/...`), the delete will not find any matching rows. Sessions from deleted files remain in the DB as orphans.

Contrast with `_sync_single_session` (`sync_engine.py:4171`) which correctly uses:
```python
await self.session_repo.delete_by_source(sync_file_path)  # canonical key
```

This inconsistency between the full-sync and watcher-triggered delete paths is a confirmed bug.

---

### Finding 8 — SyncEngine instantiated per-process; one `worker-watch` supports only one project (MEDIUM)

**Evidence**: `backend/adapters/jobs/runtime.py:118–134, 170–180`

The `RuntimeJobAdapter.start()` resolves a single `active_project` and starts one `file_watcher.start()` call. `file_watcher` is a module-level singleton (`backend/db/file_watcher.py:307`). Only one project can be watched per `worker-watch` process. The `CCDASH_WORKER_PROJECT_ID` binding is required for worker profiles (`config.py:780`). Multi-project enterprise setups require one `worker-watch` container per project.

This is documented as a known limitation but has no explicit error when attempting to use a `projects.json` with multiple projects — the system silently picks the first active project.

---

### Finding 9 — Listener reconnect is deferred/unimplemented (MEDIUM)

**Evidence**: `enterprise-live-session-ingest-v1/phase-4-progress.md:152–154`, `phase-5-progress.md:198–199`

The Postgres `NOTIFY` listener (`backend/adapters/live_updates/postgres_listener.py`) has no exponential backoff or supervisor-managed reconnect. If the listener connection drops (network partition, Postgres restart), it silently fails and live updates stop flowing from `worker-watch` to the API SSE stream. The `last_sync_error` probe field will show the disconnect, but there is no automatic recovery. Deferred to FU-2.

---

### Finding 10 — Startup sync is a blocking operation within the async event loop (HIGH)

**Evidence**: `backend/adapters/jobs/runtime.py:731–784`

`_run_startup_sync_pipeline` awaits `sync_project` directly on the main event loop. `sync_project` calls `asyncio.to_thread(parse_session_file, path)` for each JSONL file (`sync_engine.py:4156`), which is good. However, the `sqlite3`/`aiosqlite` writes are serialized on a single connection (`backend/db/connection.py` singleton). With thousands of sessions and the full backfill pipeline (`_maybe_backfill_telemetry_events`, `_maybe_backfill_commit_correlations`, etc. — `sync_engine.py:3011–3024`), startup sync holds the SQLite connection for the entire duration. API requests that also need DB access are not blocked (async I/O), but SQLite's write serialization means the backfill contends with any concurrent API writes.

For PostgreSQL, the connection pool (`asyncpg.Pool`) allows parallelism, but the backfill loops (`_backfill_telemetry_events_for_project`, `_backfill_commit_correlations_for_project`) iterate sessions one-by-one in a sequential loop (`sync_engine.py:2061–2097`, `2252–2284`), not concurrently. These are O(N×sessions) sequential Postgres round-trips.

---

### Finding 11 — `FilesystemProjectPathProvider` calls `.resolve(strict=False)` on host paths; container paths fail silently (MEDIUM)

**Evidence**: `backend/services/project_paths/providers/filesystem.py:25–28`

```python
candidate = Path(raw_value).expanduser()
if not candidate.is_absolute():
    candidate = (Path(project.path).expanduser().resolve(strict=False) / candidate).resolve(strict=False)
else:
    candidate = candidate.resolve(strict=False)
```

`resolve(strict=False)` does not raise if the path doesn't exist — it just lexically resolves the path. If `projects.json` records a `sessionsPath` as `~/.claude/projects/-Users-...` (a host path), inside a container where `/home/user/.claude` doesn't exist, the path resolves to a non-existent directory. The file watcher's `_resolve_watch_paths` silently discards non-existent paths (`file_watcher.py:260`):

```python
watch_paths = [p for p in [sessions_dir, docs_dir, progress_dir] if p.exists()]
```

So the watcher logs "File watcher configured with no existing paths" (`file_watcher.py:108–112`) and stops. But there is no error raised to the operator — readiness simply shows `configured_no_paths` state.

**This is the second-most-likely cause of the container live-data failure**: even when `CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED=true` is set, if `projects.json` records host-absolute session paths and the container mounts are not set up to mirror those paths exactly, the watcher silently watches zero directories.

---

### Finding 12 — No session scan at filesystem path registered in `projects.json` vs. where Claude Code actually writes sessions (MEDIUM)

**Evidence**: `projects.json:338`

The skillmeat project has:
```json
"sessionsPath": "~/.claude/projects/-Users-miethe-dev-homelab-development-skillmeat"
```

This is the Claude Code session directory convention (project path hash). Inside the container, `CCDASH_CLAUDE_CONTAINER_HOME=/home/ccdash/.claude` is set, but the source identity alias map pairs `CCDASH_CLAUDE_HOME` (host) with `CCDASH_CLAUDE_CONTAINER_HOME` (container) at the `.claude` root level. The `sessionsPath` value does not reference `.claude/projects/...` directly — it references the full tilde-expanded path. Unless `~` expands to the same value inside and outside the container, the path resolution diverges.

**Evidence**: `deploy/runtime/.env:26-29` (the active real .env):
```
CCDASH_WORKSPACE_HOST_ROOT=/Users/miethe/dev/homelab/development
CCDASH_WORKSPACE_CONTAINER_ROOT=/Users/miethe/dev/homelab/development   # SAME as host!
CCDASH_CLAUDE_HOME=/Users/miethe/.claude
CCDASH_CLAUDE_CONTAINER_HOME=/home/ccdash/.claude
```

The workspace host/container roots are **identical** in the active .env (`/Users/miethe/dev/homelab/development`). This means the source-identity alias for `workspace` collapses identically — the path never actually remaps. But the `claude_home` alias DOES remap from `/Users/miethe/.claude` to `/home/ccdash/.claude`. If the container mount at `/home/ccdash/.claude` maps to the host's `~/.claude`, then `sessionsPath: "~/.claude/projects/..."` (which expands to `/Users/miethe/.claude/projects/...` on the host) is mapped into the container at `/home/ccdash/.claude/projects/...`. The source identity system would map this correctly IF the alias is active. But if `~` in the container expands to `/home/ccdash` (the non-root container user), then `~/.claude` expands to `/home/ccdash/.claude`, which matches the container alias, and the path IS found.

However, `FilesystemProjectPathProvider.resolve` calls `Path(raw_value).expanduser()` — inside the container, `~` expands to `/home/ccdash`. So `~/.claude/projects/...` → `/home/ccdash/.claude/projects/...`. If the bind mount is present, the path exists. But the `sessionsPath` in `projects.json` is stored as `~/.claude/projects/-Users-miethe-dev-homelab-development-skillmeat` with the host user's home directory embedded in the project hash. This tilde-expanded path will be `/home/ccdash/.claude/projects/-Users-miethe-dev-homelab-development-skillmeat` inside the container — and the mount at `/home/ccdash/.claude` would make this exist if the bind mount covers the `~/.claude` directory from the host.

The alias source identity system (`source_identity.py:271–308`) would then correctly canonicalize file paths under this directory to `claude_home/...` keys. **This specific setup may work correctly** — but it is fragile: any change to the host user UID, home directory path, or mount path would silently break it.

---

## Completed / Shipped (Evidence)

| Status | Component | Evidence |
|--------|-----------|---------|
| DONE | `worker-watch` runtime profile with `capabilities.watch=True` | `backend/runtime/profiles.py:65–72` |
| DONE | `SyncEngine._sync_engine_enabled()` enterprise guard | `container.py:237–242` |
| DONE | Source identity `SourceRootAlias` + `source_identity_policy_from_env()` | `backend/services/source_identity.py:271–308` |
| DONE | `WATCHFILES_FORCE_POLLING` env var plumbed through compose | `compose.yaml:175`, `README.md:178` |
| DONE | Postgres NOTIFY fanout (worker→API live events) | `enterprise-live-session-ingest-v1/phase-3-progress.md` |
| DONE | Watcher health probe fields (running state, watch paths, last sync) | `phase-4-progress.md`, `runtime.py:422–463` |
| DONE | Incremental `_light_mode_scan_skip` for document/progress scans | `sync_engine.py:4239–4278` |
| DONE | Deferred link rebuild with stagger delay | `runtime.py:774–784` |
| PARTIAL | Source path alias canonicalization (contract defined, aliases wired from env) | `source_identity.py`; **gaps**: alias not populated from `projects.json` path config, delete-by-source path mismatch |
| PARTIAL | `WATCHFILES_FORCE_POLLING=true` for macOS Docker Desktop | Documented in README, compose passes it to `worker-watch` only; default is `false` |
| BROKEN | Watcher-triggered delete uses raw path, not canonical key | `sync_engine.py:3944` vs `sync_engine.py:4171` |
| NOT STARTED | Listener reconnect with backoff | Deferred per `phase-4-progress.md:FU-2` |
| NOT STARTED | Session scan light-mode (manifest skip for JSONL, same as for MD) | Only `_sync_documents` has this; `_sync_sessions` does full rglob every startup |

---

## Concrete Theory for Container Live-Data Failure

The most probable failure scenario (consistent with "containerized mode FAILED to pull live session/filesystem data"):

1. **Primary cause**: `CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED` not set (or inherited as `false` from the shared service anchor default). `_sync_engine_enabled()` returns `False`. No `SyncEngine` is created. `worker-watch` starts up, but `file_watcher.start()` is not called because `self.sync is None` (`runtime.py:170`). The `api` profile also has no sync engine. Zero sessions are ever ingested.

2. **Secondary cause**: Even if `CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED=true` is set, `projects.json` contains host-absolute session paths (`~/.claude/projects/-Users-miethe-...`). In a container where the `.claude` bind mount is absent or mounted at a different path, `p.exists()` returns `False` for all watch paths. The file watcher silently watches zero directories, logging "File watcher configured with no existing paths" with no error escalation.

3. **Tertiary cause** (if running macOS Docker Desktop): `watchfiles` defaults to inotify which does not receive events from Docker Desktop bind mounts. Watcher shows `running` in the health probe but never fires `sync_changed_files()`. `WATCHFILES_FORCE_POLLING=true` must be set explicitly.

4. **Compounding issue** (if paths are partially correct): Container paths may not match the `CCDASH_WORKSPACE_HOST_ROOT`/`CCDASH_CLAUDE_HOME` alias pairs, causing source keys to fall through to `opaque/<hash>`. Startup sync initially populates the DB under opaque keys. After an alias is added (or paths change), the same files produce different canonical keys, treated as new sessions, causing duplication without the prior rows being cleaned up.

---

## Reliable Ingestion Design for Container Deployments

### Minimum viable fix (unblocks the reported failure)

1. Change the `x-backend-service` anchor default: `CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED: "${CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED:-true}"` when under the enterprise profile. Better: make the `api` and `worker` services NOT set this flag (inherit from operator), and add a readiness gate that fails with an actionable error when sync should be enabled but isn't.

2. Add a startup log (or readiness probe failure) when `_sync_engine_enabled()` returns `False` under a `worker-watch` profile. Currently the system starts successfully with no sync, no error, and an empty dashboard.

3. For the watcher "no paths" case: surface this as a `readyz` failure, not just a log line. A `worker-watch` container with zero watch paths is misconfigured and should fail readiness.

### Reliable container ingest design

| Layer | Recommendation |
|-------|---------------|
| Path resolution | Store `projects.json` session paths as relative-to-root or canonicalize them through `FilesystemProjectPathProvider` at register time, not at ingest time |
| Source identity | Populate `SourceIdentityPolicy.aliases` from the resolved `ResolvedProjectPaths` at `SyncEngine` construction, not just from env vars; this decouples identity from mount configuration |
| Session scan | Add a manifest-based inode snapshot skip for sessions (analogous to `_light_mode_scan_skip` for documents); store last-seen `(path, mtime, size)` tuples to avoid full-rglob on unchanged directories |
| Watcher backend | Default `WATCHFILES_FORCE_POLLING=true` for the `worker-watch` compose service on non-Linux hosts; detect bind-mount type at startup and emit a warning if inotify is selected on a virtual FS |
| Delete consistency | `sync_changed_files` watcher delete path (`sync_engine.py:3944`) must use `self._canonical_source_key(project_id, path, "session")`, not `str(path)`, to match the source key written by `_sync_single_session` |
| Multi-project | Document explicitly that one `worker-watch` container handles one project; add a `CCDASH_WORKER_PROJECT_IDS` multi-value env for operators who want one container to watch multiple projects |
| Listener reconnect | Implement exponential backoff for the Postgres NOTIFY listener (FU-2); without this, a Postgres restart silently drops live fan-out permanently until the API container is restarted |
| Startup gate | Before starting the file watcher, verify at least one watch path exists and is readable; emit a structured error to the health probe if not |

---

## Key Files and Line Anchors

| File | Lines | Topic |
|------|-------|-------|
| `backend/config.py` | 244–246 | `CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED` default logic |
| `backend/runtime/container.py` | 237–242 | `_sync_engine_enabled()` gate |
| `backend/db/file_watcher.py` | 252–266 | `_resolve_watch_paths` — silently drops non-existent paths |
| `backend/db/file_watcher.py` | 183 | `awatch` call — no explicit inotify vs. polling selection |
| `backend/services/source_identity.py` | 271–308 | `source_identity_policy_from_env()` — alias construction |
| `backend/services/source_identity.py` | 175–185 | Opaque key fallback when no alias matches |
| `backend/db/sync_engine.py` | 3943–3945 | Watcher delete uses `str(path)` not canonical key (bug) |
| `backend/db/sync_engine.py` | 4171 | Full-sync delete uses `sync_file_path` (canonical, correct) |
| `backend/db/sync_engine.py` | 4107–4119 | `_sync_sessions` full rglob — no manifest skip |
| `backend/db/sync_engine.py` | 4239–4278 | `_light_mode_scan_skip` — documents only |
| `backend/adapters/jobs/runtime.py` | 731 | `getattr(config, "STARTUP_SYNC_LIGHT_MODE", True)` — wrong fallback default |
| `backend/adapters/jobs/runtime.py` | 170–180 | Watcher start gating on `self.sync is not None` |
| `backend/config.py` | 966 | `STARTUP_SYNC_LIGHT_MODE` module default `False` |
| `deploy/runtime/compose.yaml` | ~27–32 | `x-backend-service` anchor sets `CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED: false` |
| `deploy/runtime/compose.yaml` | ~175 | `worker-watch` overrides to `true` only when `live-watch` profile is active |
| `deploy/runtime/.env` | 26–29 | Active host/container path alias config (workspace root identical on both sides) |
| `backend/services/project_paths/providers/filesystem.py` | 25–29 | `expanduser().resolve(strict=False)` — silently resolves non-existent paths |
| `projects.json` | 338 | `sessionsPath: "~/.claude/projects/..."` — tilde-path in container context |
