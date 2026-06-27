# Workers & Runtime Orchestration — Enterprise Investigation Findings

**Domain:** workers-runtime  
**Date:** 2026-05-30  
**Investigator:** Claude Sonnet 4.6 (subagent)

---

## Summary

CCDash has a well-designed five-profile runtime separation (`local`, `api`, `worker`, `worker-watch`, `test`) declared in `backend/runtime/profiles.py`. The `api` profile cleanly excludes all background work; the `worker` and `worker-watch` profiles own ingestion, jobs, and telemetry export. The container/compose split is present and documented. However, the architecture is **fundamentally one-project-per-worker-process** (no multi-project dispatch within a single worker), the job scheduler is a trivial `InProcessJobScheduler` backed by bare `asyncio.create_task()` with no queue, priority, backpressure, or retry logic at the scheduler level, the startup sync runs as a fire-and-forget `asyncio.Task` scheduled immediately at lifespan startup (does not block serving, which is correct), and multiple enterprise-critical configuration env vars documented in deploy are not wired into `backend/config.py` Python code (`CCDASH_WORKER_WATCH_PROJECT_ID`, `CCDASH_WORKER_STARTUP_SYNC_ENABLED`, `CCDASH_WORKER_WATCH_STARTUP_SYNC_ENABLED`). The `bootstrap_worker.py` module executes `container = build_worker_runtime()` at import time (line 86), creating a double-instantiation risk. Worker health/status is surfaced well through a dedicated probe HTTP server on port 9465/9466 with `/livez`, `/readyz`, and `/detailz` endpoints. The live-fanout mechanism (Postgres NOTIFY for enterprise) is correctly partitioned: workers publish, the API container listens.

---

## Runtime Profile Matrix

| Profile | watch | sync | jobs | auth | Recommended Storage | Container Role |
|---------|-------|------|------|------|---------------------|----------------|
| `local` | yes | yes | yes | no | local (SQLite) | single all-in-one |
| `api` | **no** | **no** | **no** | yes | enterprise (Postgres) | HTTP server only |
| `worker` | no | yes | yes | no | enterprise | scheduler + sync |
| `worker-watch` | yes | yes | yes | no | enterprise | live watcher + sync |
| `test` | no | no | no | no | local | stripped |

Source: `backend/runtime/profiles.py:28–89`

---

## Startup Sequence (Container Startup)

All profiles execute `RuntimeContainer.startup()` (container.py:72) during FastAPI lifespan. The sequence is:

1. **Sync validation** (blocking): `validate_runtime_storage_pairing`, `validate_migration_governance_contract`, `config.validate_runtime_environment_contract` — all three are synchronous Python calls, fast in practice but run in the async event loop without `run_in_executor`.
2. **DB connection** (async): `await connection.get_connection()` — async, correct.
3. **Migrations** (async): `await migrations.run_migrations(self.db)` — async, correct.
4. **Core ports built** (sync): `self._build_core_ports()` — sync, fast.
5. **Live event broker/publisher/listener**: Postgres NOTIFY listener started for `api` profile only.
6. **SyncEngine instantiated** (sync): No IO, just a Python object.
7. **Telemetry coordinator and settings store**: Sync construction, no IO.
8. **`RuntimeJobAdapter.start()`** (async, critical): Schedules all background tasks as `asyncio.create_task()` via `InProcessJobScheduler.schedule()`. This returns control immediately — sync and ingestion run entirely in the background.

Key observation: **The startup sync does NOT block request serving.** It is scheduled as an `asyncio.Task` via `InProcessJobScheduler.schedule()` (adapters/jobs/local.py:9–10) and runs concurrently. The worker is technically "not ready" (`startup_sync` readiness check) until it completes, but the probe server remains responsive and returns 503 until done.

Source: `backend/runtime/container.py:72–168`, `backend/adapters/jobs/local.py:9–10`, `backend/adapters/jobs/runtime.py:143–196`

---

## Background Job Inventory (per RuntimeJobAdapter)

Five job slots exist in `RuntimeJobState` (runtime.py:79–85):

| Job | Profile | Interval | Purpose |
|-----|---------|---------|---------|
| `startupSync` | worker, worker-watch, local | once at startup | Full filesystem→DB sync for bound project |
| `analyticsSnapshots` | all with jobs | `CCDASH_ANALYTICS_SNAPSHOT_INTERVAL_SECONDS` (default 900s) | Periodic analytics rollup |
| `telemetryExports` | `worker` only | `CCDASH_TELEMETRY_EXPORT_INTERVAL_SECONDS` (default 900s, min 60s) | Batch export to SAM endpoint |
| `artifactRollupExports` | `worker` only | `CCDASH_ARTIFACT_ROLLUP_EXPORT_INTERVAL_SECONDS` (default 3600s, min 60s) | SkillMeat artifact rollup push |
| `cacheWarming` | all with jobs | `CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS` (default 300s) | Pre-warm `@memoized_query` caches |

Source: `backend/adapters/jobs/runtime.py:108–116`, `984–1082`

---

## InProcessJobScheduler — The Core Problem

The only job scheduler implementation is `InProcessJobScheduler` (`backend/adapters/jobs/local.py`):

```python
class InProcessJobScheduler:
    def schedule(self, job: Awaitable[Any], *, name: str | None = None) -> asyncio.Task[Any]:
        return asyncio.create_task(job, name=name)
```

This is 2 lines. There is no:
- Job queue (no bounded concurrency)
- Retry policy (errors are caught by individual job loops but the scheduler never retries a crashed task)
- Priority (startup sync and analytics fire at the same priority as telemetry export)
- Backpressure signal feeding back into the scheduler
- Dead letter / failure escalation at the scheduler level
- Task supervision (if a task crashes with an unhandled exception, it is silently lost — asyncio `CancelledError` is handled but `RuntimeError`/`OSError` etc. terminate the task and the job stops running forever until restart)

For enterprise at scale (10 GB SQLite → Postgres, many projects), this means heavy startup syncs and periodic analytics snapshots compete with cache warming on the same single-threaded asyncio event loop with no isolation or throttling.

Source: `backend/adapters/jobs/local.py:8–10`, `backend/application/ports/core.py:207–210`

---

## One-Project-Per-Worker Constraint

Workers are hard-bound to a single project at startup:

- `_resolve_startup_project_binding()` (container.py:1111) reads `CCDASH_WORKER_PROJECT_ID` via `config.resolve_worker_binding_config()` and raises `RuntimeError` if unresolved.
- The project binding is locked for the lifetime of the container process.
- `worker-watch` profile uses `CCDASH_WORKER_PROJECT_ID` from the compose env (which is aliased from `CCDASH_WORKER_WATCH_PROJECT_ID` in compose.yaml:166 via shell substitution — this is a compose-level trick, not Python config).
- Multi-project coverage requires N separate worker containers, each with a distinct `CCDASH_WORKER_PROJECT_ID` and distinct probe port.
- Watcher rebind (`rebind_watcher()`) exists at runtime.py:198 but is an in-process project switch (stop old watcher, start new), not a multi-project model.

Quotes from documentation confirming this is by-design for v1:  
`docs/guides/containerized-deployment-quickstart.md:86`:  
> "In v1, a watcher worker binds one project id for the life of that container"  
`deploy/runtime/README.md:61`:  
> "worker-watch binds one project per worker process in v1"

Source: `backend/runtime/container.py:1111–1142`, `backend/adapters/jobs/runtime.py:118–134`, `deploy/runtime/compose.yaml:130,166`

---

## Issues: WORKER_WATCH_PROJECT_ID Not in Python Config

[SEVERITY: high] The env var `CCDASH_WORKER_WATCH_PROJECT_ID` is documented in `deploy/runtime/.env.example:91` and `deploy/runtime/README.md:61` as the canonical variable for the watcher worker's project binding. However, it does not exist anywhere in `backend/config.py`. The compose.yaml resolves this at the Docker layer:

```yaml
# compose.yaml:166
CCDASH_WORKER_PROJECT_ID: "${CCDASH_WORKER_WATCH_PROJECT_ID:-${CCDASH_WORKER_PROJECT_ID:-smoke-stack}}"
```

This means the watcher container receives `CCDASH_WORKER_PROJECT_ID` (the standard var), not `CCDASH_WORKER_WATCH_PROJECT_ID`. The Python code only reads `CCDASH_WORKER_PROJECT_ID`. If someone runs the worker outside compose (e.g., k8s, direct pod exec), setting `CCDASH_WORKER_WATCH_PROJECT_ID` alone will not work — they must also set `CCDASH_WORKER_PROJECT_ID`.

Source: `backend/config.py:149`, `deploy/runtime/compose.yaml:166`, `deploy/runtime/.env.example:91`

---

## Issues: CCDASH_WORKER_STARTUP_SYNC_ENABLED Not Read by Python Config

[SEVERITY: high] The compose.yaml maps per-service startup-sync control:

```yaml
# compose.yaml:133 (worker service)
CCDASH_STARTUP_SYNC_ENABLED: "${CCDASH_WORKER_STARTUP_SYNC_ENABLED:-false}"
# compose.yaml:170 (worker-watch service)  
CCDASH_STARTUP_SYNC_ENABLED: "${CCDASH_WORKER_WATCH_STARTUP_SYNC_ENABLED:-true}"
```

The Python `config.py:961` reads only `CCDASH_STARTUP_SYNC_ENABLED`. The compose variable translation is entirely at the Docker/compose layer. This is functionally correct when using compose, but:
- Operators running workers in Kubernetes or bare containers must set `CCDASH_STARTUP_SYNC_ENABLED` directly.
- The script `container_project_onboarding.py:122–123` writes `CCDASH_WORKER_STARTUP_SYNC_ENABLED=false` and `CCDASH_WORKER_WATCH_STARTUP_SYNC_ENABLED=true` into env overlay files — these would be silently ignored unless consumed by compose.

Source: `backend/config.py:961`, `deploy/runtime/compose.yaml:133,170`, `backend/scripts/container_project_onboarding.py:122`

---

## Issues: Module-Level `container = build_worker_runtime()` in bootstrap_worker.py

[SEVERITY: medium] `backend/runtime/bootstrap_worker.py:86` instantiates a `RuntimeContainer` at module import time:

```python
container = build_worker_runtime()
```

`build_worker_runtime()` calls `RuntimeContainer(profile=get_runtime_profile(...))` — at this point only `__init__` runs (no async startup), so no IO happens. However:

1. It reads `os.getenv(CCDASH_RUNTIME_PROFILE_ENV, "worker")` at import time, not at call time. Any test that imports this module before setting env vars will get the wrong profile.
2. `backend/worker.py:11` imports `build_worker_probe_app, build_worker_runtime` from this module, which triggers the module-level `container = build_worker_runtime()` side effect at import time. Then `serve_worker()` calls `build_worker_runtime()` again, creating a second container that goes through full startup. The module-level container is never started and is orphaned.
3. Tests importing `build_worker_probe_app` (`test_cache_warming_job.py:28`, `test_runtime_bootstrap.py:31`) trigger this side effect.

Source: `backend/runtime/bootstrap_worker.py:86`, `backend/worker.py:11`

---

## Issues: Single-Process Sync Competes With Request Serving on Local Profile

[SEVERITY: high for local/dev, medium for enterprise] In the `local` profile (and in `worker`/`worker-watch`), the startup sync, periodic analytics, and cache warming all run as asyncio tasks in the same event loop as HTTP request handlers. SQLite is not async-native — the `aiosqlite` adapter uses a background thread per connection, but large scans (10 GB DB, thousands of JSONL files) produce sustained CPU bursts that starve coroutines. On the reported 10 GB SQLite database with `skillmeat` project, startup sync can take many minutes, during which all HTTP handlers experience elevated latency.

The `STARTUP_SYNC_DELAY_SECONDS` (config.py:962, default 2s) and `STARTUP_SYNC_LIGHT_MODE` (config.py:966, default false) flags mitigate this but are not the default for local mode.

Source: `backend/adapters/jobs/runtime.py:727–732`, `backend/config.py:961–966`

---

## Issues: Analytics Snapshot and Cache Warming Operate Only on Single Active Project

[SEVERITY: medium] The periodic analytics snapshot (runtime.py:796–838) and cache warming (runtime.py:840–982) both call:

```python
current_project = bound_project or workspace_registry.get_active_project()
```

In `worker` profile, `bound_project` is the single startup-bound project. In `local` profile, it is `workspace_registry.get_active_project()` — the single active project from `projects.json`. There is no iteration over all registered projects. If the operator has 10 projects and switches the active one, analytics and cache warming only cover the currently-active project.

Source: `backend/adapters/jobs/runtime.py:794–799`, `backend/adapters/jobs/runtime.py:894–895`

---

## Issues: No Task Supervision — Silent Task Death

[SEVERITY: high] All job tasks are bare `asyncio.create_task()` calls. If a job loop raises an unhandled exception (beyond the `try/except Exception` blocks in the periodic loops, e.g., a `BaseException` subclass, or an exception inside `_run_startup_sync_pipeline()` that reaches the outer `_run_startup_sync_job()` coroutine), the asyncio task terminates. There is no watchdog that detects task death and either restarts it or surfaces an alarm.

The `status_snapshot()` method (runtime.py:385–420) checks `task.done()` and reports `"idle"` rather than `"dead"` — an operator looking at the probe endpoint would see `startupSync: idle` rather than `startupSync: failed` if the task died after already being marked succeeded.

Source: `backend/adapters/jobs/runtime.py:385–420`, `backend/adapters/jobs/local.py:9–10`

---

## Issues: Enterprise Worker Does NOT Own Startup Sync by Default

[SEVERITY: critical for enterprise data freshness] In the compose enterprise profile, the standard `worker` service has `CCDASH_STARTUP_SYNC_ENABLED` mapped to `${CCDASH_WORKER_STARTUP_SYNC_ENABLED:-false}` — **startup sync is OFF by default for the enterprise worker** (compose.yaml:133). Only `worker-watch` has it on by default.

If an operator runs the enterprise profile **without** the `live-watch` profile (no watcher worker), and does not explicitly set `CCDASH_WORKER_STARTUP_SYNC_ENABLED=true`, the standard worker will never sync the filesystem into Postgres. The database starts empty and stays empty. This is the likely cause of the reported "enterprise/containerized edition failed to pull live session/filesystem data."

Source: `deploy/runtime/compose.yaml:133`, `backend/config.py:961`

---

## Issues: Postgres Live Fanout Wired to `worker`/`worker-watch` But Not the Standard Worker

[SEVERITY: medium for live updates] `_build_postgres_live_event_bus()` (container.py:216–223) only creates a Postgres NOTIFY bus for profiles in `{"worker", "worker-watch"}`. The standard worker (profile `worker`) gets the bus. The `api` profile gets the listener. However, if startup sync is disabled on the standard worker (default), events are never published because there is nothing to ingest.

Source: `backend/runtime/container.py:216–223`, `backend/runtime/container.py:225–235`

---

## Issues: Telemetry/Artifact Export Jobs Only Wire When `profile.name == "worker"`

[SEVERITY: low for worker-watch] `TelemetryExporterJob` and `ArtifactRollupExportJob` are only created when `profile.name == "worker"` (container.py:144, 149). The `worker-watch` profile does NOT run telemetry exports. In a deployment where only `worker-watch` is running (no standard `worker` container), telemetry will never be flushed.

Source: `backend/runtime/container.py:144–156`

---

## Issues: No External Job Queue / Durable Task Storage

[SEVERITY: high for enterprise at scale] All background work uses `asyncio.create_task()`. There is no durable task queue (Celery, ARQ, Dramatiq, Redis queue, etc.). If the worker container crashes mid-sync, all in-flight work is lost without a checkpoint. The sync engine has an operation log in the DB (`_start_operation`, `_update_operation`) but it is purely informational — the worker does not resume partial syncs on restart; it runs a fresh full sync.

For large projects (10 GB sessions corpus), a full startup sync can take tens of minutes. A container OOM or pod eviction partway through means the entire sync restarts, causing sustained high DB write load at container startup.

Source: `backend/adapters/jobs/local.py:8–10`, `backend/db/sync_engine.py:2966–2984`

---

## Issues: No Project-Scoped Worker Isolation for Analytics

[SEVERITY: medium] Analytics snapshots (`capture_analytics_snapshot`) run only for the active/bound project. In local mode with multiple projects, switching the active project does not trigger analytics catchup for the previously-active project. In enterprise mode, the worker is project-scoped so this only affects operators who switch which project the worker is bound to.

Source: `backend/adapters/jobs/runtime.py:796–829`

---

## Worker Health Surface Assessment

### What Works

- Probe HTTP server on dedicated port (`CCDASH_WORKER_PROBE_PORT`, default 9465) exposing `/livez`, `/readyz`, `/detailz` — implemented in `bootstrap_worker.py:31–67`.
- `RuntimeJobAdapter.status_snapshot()` returns rich job observation state: `lastStartedAt`, `lastFinishedAt`, `lastSuccessAt`, `lastFailureAt`, `lastOutcome`, `lastDurationMs`, `lastError`, `backlogCount`, `checkpointFreshnessSeconds`.
- `workerProbe` blob in `/detailz` includes sync lag, backpressure, and per-job states.
- OTEL + Prometheus metrics for job freshness (`ccdash_worker_job_freshness_ms`) and backpressure (`ccdash_worker_job_backpressure_ratio`).
- Worker readiness check includes `worker_binding` (project must resolve before ready).
- `worker-watch` readiness check includes `watcher_runtime` and `startup_sync`.

### What Is Missing

- No metric/alarm when a job task dies silently — probe shows `idle` not `dead`.
- No cross-project job progress aggregation (only bound project visible from probe).
- No job queue depth metric for analytics and cache-warming (only telemetry export has queue depth).
- No "stale since" threshold alarm in the probe contract (an operator must compute staleness manually from `checkpointFreshnessSeconds`).

Source: `backend/runtime/bootstrap_worker.py:31–67`, `backend/adapters/jobs/runtime.py:385–420`, `backend/observability/otel.py:379–390`

---

## Recommended: Project-Scoped Worker Execution Model

Three viable architectures for multi-project enterprise workers:

### Option A: One Worker Per Project (Current v1 Design, Scale Horizontally)

**Status:** shipped, working, documented.  
**Mechanism:** Deploy N `worker` containers, each with `CCDASH_WORKER_PROJECT_ID=<project-id>`.  
**Pros:** Full isolation, independent failure domains, zero code change.  
**Cons:** N containers per project, no shared scheduler, no cross-project analytics aggregation. Operational burden grows linearly with projects.  
**Best for:** < 5 projects, or projects with very different ingest rates.

### Option B: Single Worker With Per-Project Job Dispatch Loop

**Mechanism:** Worker reads all registered projects and loops over them in the analytics/sync task. The job scheduler remains `asyncio.create_task()` but each task internally iterates projects.  
**Pros:** 1 worker container for all projects, no per-project deployment.  
**Cons:** No isolation — one slow project blocks all others (asyncio, no true parallelism). Watcher still needs 1 process per project (filesystem events are bound to paths, not multiplexed).  
**Complexity:** M (1–2d for analytics/cache loop; watcher is separate concern).  
**Key change needed:** `_start_analytics_snapshot_task()` and `_start_cache_warming_task()` iterate `workspace_registry.list_projects()` instead of using a single active project.

### Option C: Shared Postgres Worker Pool With External Queue (ARQ/Celery)

**Mechanism:** Workers become stateless runners consuming jobs from a Redis/Postgres-backed queue. Projects enqueue sync/analytics jobs; workers pick them up from the queue.  
**Pros:** True horizontal scaling, project-level concurrency control, backpressure, retries, durable state.  
**Cons:** Adds Redis or Postgres queue dependency; large refactor of `RuntimeJobAdapter`; watcher workers still need per-project filesystem access.  
**Complexity:** XL (> 1 week).  
**Best for:** > 10 projects, SLA requirements, enterprise tier.

**Recommendation for enterprise v1 target:**  
Implement Option B for analytics/cache-warming loops (low risk, Option A remains valid for watcher workers). Add task supervision to detect silent task death (low complexity). Fix the `CCDASH_WORKER_STARTUP_SYNC_ENABLED` default gap for the enterprise worker (critical, 1 line).

---

## Key File:Line Anchors

| Finding | Location |
|---------|----------|
| Profile definitions with capability matrix | `backend/runtime/profiles.py:28–89` |
| Startup sequence (DB, migration, jobs) | `backend/runtime/container.py:72–168` |
| InProcessJobScheduler (bare create_task) | `backend/adapters/jobs/local.py:8–10` |
| Job scheduling and all five jobs | `backend/adapters/jobs/runtime.py:118–196` |
| Startup sync pipeline (light mode, SkillMeat refresh, deferred rebuild) | `backend/adapters/jobs/runtime.py:716–784` |
| Analytics snapshot periodic loop | `backend/adapters/jobs/runtime.py:786–838` |
| Cache warming periodic loop | `backend/adapters/jobs/runtime.py:840–982` |
| Telemetry export periodic loop | `backend/adapters/jobs/runtime.py:984–1035` |
| Worker project binding (hard fail if missing) | `backend/runtime/container.py:1111–1142` |
| Sync engine enabled gate (enterprise) | `backend/runtime/container.py:237–242` |
| Postgres live event bus (worker-only) | `backend/runtime/container.py:216–223` |
| Postgres listener (api-only) | `backend/runtime/container.py:225–235` |
| Module-level orphaned container | `backend/runtime/bootstrap_worker.py:86` |
| Worker probe HTTP server | `backend/runtime/bootstrap_worker.py:31–67` |
| Job status snapshot (idle vs dead ambiguity) | `backend/adapters/jobs/runtime.py:385–420` |
| STARTUP_SYNC_ENABLED default off for enterprise worker | `deploy/runtime/compose.yaml:133` |
| WORKER_WATCH_PROJECT_ID compose-layer mapping | `deploy/runtime/compose.yaml:166` |
| Worker/watcher one-project doc | `docs/guides/containerized-deployment-quickstart.md:86` |
| Enterprise filesystem ingestion flag | `backend/config.py:246` |
| Worker telemetry jobs restricted to profile=worker | `backend/runtime/container.py:144–156` |
