---
schema_version: 2
doc_type: worknote
title: "W2 Watcher Fan-Out SPIKE — Design Specification"
status: approved
approved_by: opus-orchestrator
approved_at: 2026-06-13
created: 2026-06-13
feature_slug: ccdash-runtime-deploy-remediation
phase: P2
task: T2-001
t3_004_scope_decision: in-P3 (periodic reconcile loop, 60s default; hot-reload signaling deferred to D-002)
watch_target_decision: all-registered-projects (is_active is a UI signal, not an ingest gate; PRD AC-W2-1 permits)
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-runtime-deploy-remediation-v1.md
impl_plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-runtime-deploy-remediation-v1.md
adr_refs:
  - docs/project_plans/adrs/adr-006-db-authoritative-project-registry.md
gates: P3
---

# W2 Watcher Fan-Out SPIKE — Design Specification

This document resolves all five open questions (OQ-2, OQ-3, OQ-4/dynamic behavior, OQ-5, and
bounded concurrency) that gate the P3 registry-driven watcher implementation. Every recommendation
is grounded in ADR-006 (the DB registry is the sole source of truth for project selection) and the
investigation report findings.

---

## Context

The current `worker-watch` runtime profile hard-pins its watch target to a single project via
`CCDASH_WORKER_WATCH_PROJECT_ID` (read at `backend/config.py:1007`) and raises a `RuntimeError` if
the env var is absent. The binding is resolved inside `_resolve_startup_project_binding` in
`backend/runtime/container.py` (~lines 1227–1246), which calls `resolve_worker_binding_config()`
and overrides with the watch-specific env var if present. This is the only watch-targeting code
path. ADR-006 mandates that all project selection be derived from the DB registry; the current
env-pinned single-project model is a registry-authority leak.

The probe contract (`_probe_watcher_detail`, container.py:984–1030) currently tracks a single
aggregated watcher state with scalar `watchPathCount`, `lastChangeSyncAt`, and `lastSyncStatus`.
There is no per-project breakdown.

---

## OQ-2 — Watch ALL registered projects vs only `is_active=true` projects

**Recommendation: Watch ALL registered projects (regardless of `is_active`).**

### Rationale

`is_active` is a UI-selection signal: it controls which project the frontend's app-shell defaults
to, not whether that project's data should be ingested. An operator who has imported two projects
but made only one "active" still expects session JSONL files from the second project to be indexed
and queryable — they just do not want it as the default view. Restricting watcher fan-out to
`is_active=true` projects would silently stop ingesting data for inactive projects, which is a
worse failure mode than the resource cost of watching additional trees.

**Resource budget rationale (watchfiles on macOS/Linux):**

- On Linux, watchfiles uses `inotify`. Each watched directory consumes one inotify watch
  descriptor. The default kernel limit (`fs.inotify.max_user_watches`) is 8,192 on many
  distributions. A typical CCDash project tree with session logs, docs, and progress files spans
  roughly 50–200 directories. At that rate, a single-process watcher covering 10 registered
  projects consumes 500–2,000 inotify watches — well within default limits. Even at 40 registered
  projects the upper bound (~8,000 watches) approaches the default ceiling, at which point the
  operator should tune `fs.inotify.max_user_watches` (a documented, standard operation).

- On macOS, watchfiles uses FSEvents. FSEvents registers at the path level (not per-file), is
  coalesced by the OS, and has no hard per-process descriptor limit. Polling overhead scales with
  the number of change events, not with the number of watched paths. Watching N inactive projects
  that never produce change events costs essentially nothing at the polling layer.

- The bounded concurrency ceiling (see OQ-5 below) caps the number of concurrent sync tasks
  spawned per-change, which is the true resource multiplier, not the watch subscription count.

**Implementation note:** The filter for `_build_worker_binding_config` should call
`workspace_registry.list_projects()` without an `is_active` filter and build one `WatcherBinding`
per returned project. If the registry is empty, the process logs a warning and waits — it does not
raise a `RuntimeError` (empty registry is a valid transient state, not a misconfiguration).

---

## OQ-3 — Backward-compatibility contract for `CCDASH_WORKER_WATCH_PROJECT_ID`

**Recommendation: env present (non-empty) → scope to that single project id; env absent or empty
string → registry-driven fan-out across all registered projects.**

### Contract specification

```
CCDASH_WORKER_WATCH_PROJECT_ID behavior:
  non-empty string  → single-project scope (existing operator behavior, unchanged)
  empty string      → registry-driven fan-out (NEW default behavior)
  unset             → same as empty string (registry-driven fan-out)
```

### Backward-compatibility analysis

Investigation confirmed that all known production deployments that have `CCDASH_WORKER_WATCH_PROJECT_ID`
set have it set to a non-empty project id. No operator has ever relied on the empty-string case to
mean "watch nothing" — the current code raises a `RuntimeError` when the env var is empty (and
`CCDASH_WORKER_PROJECT_ID` also resolves empty), so `empty → watch nothing` has never been an
observable, stable contract. The empty-string semantics change from "crash" to "fan-out" is
strictly an improvement and does not break any documented or observed operator behavior.

The env var comment in `backend/config.py` must be updated to read:

```
# CCDASH_WORKER_WATCH_PROJECT_ID — optional scope filter for the worker-watch profile.
# Non-empty: watcher targets exactly that project id (backward-compatible override).
# Empty or unset: watcher derives targets from the DB registry (all registered projects).
```

No compose file variable group changes are needed for existing single-project deployments; their
env var remains non-empty and the behavior is identical.

---

## OQ-4 (dynamic) — Dynamic add/remove behavior when a project is added or `is_active` flips

**Recommendation: Implement a periodic reconcile loop in P3 (in-scope for T3-004). Defer full
hot-reload signaling to D-002.**

### Decision

P3 will implement a lightweight periodic reconcile loop: the watcher process re-reads the project
registry on a configurable interval (default **60 seconds**, env var
`CCDASH_WATCHER_RECONCILE_INTERVAL_SECONDS`). On each tick it computes the symmetric difference
between the currently-watched project set and the registry-returned project set, then idempotently
adds new projects and removes deregistered ones.

This is NOT the full hot-reload design described in D-002 (which would involve inter-process
signaling so that an HTTP write on the API process can push a binding change to the worker-watch
process immediately). That belongs in D-002 and requires a separate SPIKE.

### Why in-P3 (not defer-to-D-002)

The "boot-time only, never re-check" alternative fails a core use case: an operator adds a second
project via `ccdash project add` while the watcher is already running. Without a reconcile loop,
the new project is never watched until the operator restarts the worker-watch service. Given that
CCDash targets long-running background services (compose, k8s), an up-to-60-second lag before
new-project pickup is acceptable; requiring a service restart is not.

The reconcile loop is architecturally simple: a `asyncio.sleep(interval)` loop that calls
`workspace_registry.list_projects()` and diffs against the active binding set. The implementation
complexity is low relative to the operational value.

### What is deferred to D-002

Sub-second push notification of registry changes (watcher process receives a signal or IPC message
when the API process writes a new project). This requires either a shared-memory event bus, a
filesystem sentinel file, or inter-process socket — none of which are designed in this epic.
D-002 is triggered if registry churn exceeds one change per hour in production or an operator
explicitly requests hot-reload without a restart.

### Reconcile loop specification for T3-004

- Default interval: 60 seconds (`CCDASH_WATCHER_RECONCILE_INTERVAL_SECONDS`, min 10s, max 3600s).
- Registry read: `workspace_registry.list_projects()` (all registered projects, no `is_active`
  filter, consistent with OQ-2 recommendation).
- Diff computation: `new_ids = registry_ids - active_ids`; `removed_ids = active_ids - registry_ids`.
- Add path: for each `new_id`, build and start a `WatcherBinding` identically to boot-time.
  Idempotent: if a binding for `new_id` already exists, skip.
- Remove path: for each `removed_id`, stop and discard the corresponding `WatcherBinding`.
  Idempotent: if no binding for `removed_id` exists, skip.
- Error handling: a reconcile tick failure must log a warning and schedule the next tick normally.
  One bad tick must never crash the loop or the parent process.
- Reconcile loop health: expose `lastReconcileAt` and `lastReconcileError` in the per-project
  health rollup (OQ-5), surfaced as a top-level watcher detail field.

**This decision unambiguously scopes T3-004 as in-P3.** The design spec for D-002 is authored in
P5 (T5-006) as a deferred-items deliverable.

---

## OQ-5 — Per-project probe / health rollup contract

**Recommendation: Aggregate `/readyz` (degraded if any project watcher is degraded) plus
per-project breakdown in `/api/health/detail` under the `watcher` section.**

### Aggregate `/readyz` behavior

The existing `watcher_runtime` check in `_build_probe_contract` aggregates to a single
`watcher_check_status`. Post-P3, the aggregation rule becomes:

- `pass` — all per-project watcher states are `running`.
- `warn` — at least one per-project state is `degraded` or `stopped` but the profile does not
  require watcher (local profile).
- `fail` — at least one per-project state is not `running` and the profile requires watcher
  (`worker-watch` profile where `watcher_runtime` is a required check).

This preserves the existing single-signal aggregate contract for all consumers of `/readyz` and
`/api/health/ready`. No consumer needs to parse per-project state to determine overall readiness.

### Per-project breakdown in `/api/health/detail`

The `watcher` section of `/api/health/detail` gains a `projects` map. The exact JSON shape is:

```json
{
  "watcher": {
    "state": "running",
    "watchPathCount": 42,
    "lastChangeSyncAt": "2026-06-13T10:00:00Z",
    "lastChangeCount": 7,
    "lastSyncStatus": "ok",
    "lastSyncError": null,
    "lastReconcileAt": "2026-06-13T10:01:00Z",
    "lastReconcileError": null,
    "projects": {
      "proj-abc123": {
        "state": "running",
        "watchPathCount": 22,
        "lastChangeSyncAt": "2026-06-13T10:00:00Z"
      },
      "proj-def456": {
        "state": "running",
        "watchPathCount": 20,
        "lastChangeSyncAt": "2026-06-13T09:58:30Z"
      }
    }
  }
}
```

**Field semantics:**
- `state`: one of `running | degraded | stopped | unknown`. Derived from the per-project watcher
  binding's internal state machine.
- `watchPathCount`: integer count of filesystem paths actively watched for this project. Zero is
  valid for a just-registered project whose root path does not yet exist.
- `lastChangeSyncAt`: ISO-8601 UTC timestamp of the most recent sync triggered by a filesystem
  event for this project. `null` if no sync has occurred since boot.

**Frontend resilience contract (R-P2 — required):**

Every frontend consumer of the `/api/health/detail` watcher section MUST apply these fallbacks:

| Missing field | Fallback value |
|---|---|
| `projects` key absent from `watcher` object | `{}` (treat as no per-project data; do not crash) |
| Per-project entry missing `state` | `"unknown"` |
| Per-project entry missing `watchPathCount` | `0` |
| Per-project entry missing `lastChangeSyncAt` | `null` |
| `projects` value is not an object | `{}` |

These fallbacks apply for both API versions that predate P3 (server does not yet emit `projects`)
and for the transient window between P3 deployment and FE refresh. The server emitting an older
response shape must never crash the frontend.

---

## OQ-Concurrency — Bounded concurrency ceiling and per-project isolation

**Recommendation: One asyncio Task per project watcher, with a supervisor that catches and
quarantines per-project failures. Set a bounded concurrency ceiling of `N_projects` concurrent
sync tasks capped at 20 simultaneous sync executions.**

### Per-project isolation

Each project's file-watcher subscription runs in its own `asyncio.Task` (named
`ccdash:watcher:{project_id}`). If a project's watcher task raises an unhandled exception:

1. The task is caught by the supervisor loop via `task.add_done_callback`.
2. The supervisor logs the exception at ERROR level, including the `project_id`.
3. The supervisor marks that project's state as `degraded` in the health map.
4. The supervisor schedules a restart of that project's watcher task after a backoff period
   (default: 30 seconds, increasing to 5 minutes on repeated failure within 10 minutes).
5. Sibling project watcher tasks are completely unaffected — they continue running.

This means one corrupt watch path (e.g. a project whose root directory has been deleted) cannot
cascade a `RuntimeError` that kills all watchers. The failure is isolated, logged, and
health-surfaced.

### Bounded sync concurrency ceiling

Filesystem change events may burst (e.g. a `git pull` touching hundreds of JSONL files). Without a
ceiling, all N projects could fire sync tasks simultaneously, each spawning multiple sync workers.

The ceiling is enforced via an `asyncio.Semaphore(CCDASH_WATCHER_SYNC_CONCURRENCY, default=20)`.
Each per-project sync task acquires the semaphore before starting a sync and releases it on
completion. This bounds total simultaneous sync executions to 20 regardless of how many projects
or change events are in flight. The semaphore is shared across all project watcher tasks.

`CCDASH_WATCHER_SYNC_CONCURRENCY` is a new config var (int, default 20, min 1, max 200). Operators
with many active projects and high-throughput writes can tune this up; constrained environments can
tune it down.

---

## Test Scenarios for P3 Implementation

The following scenarios must be covered by `backend/tests/test_p3_worker_bootstrap.py` and the
manual livewatch smoke (T3-007). Each scenario is a named test or a documented smoke step.

### Scenario 1 — Happy path: multi-project fan-out (unit + livewatch smoke)

**Setup:** Registry contains two projects, `CCDASH_WORKER_WATCH_PROJECT_ID` is unset (empty).
**Assert:** `_build_worker_binding_config` (or equivalent) returns two `WatcherBinding` objects,
one per project. Health map `projects` has two entries, both `state: running` after startup.
Watcher aggregate state is `running`.

### Scenario 2 — Empty registry (unit)

**Setup:** Registry returns zero projects, `CCDASH_WORKER_WATCH_PROJECT_ID` is unset.
**Assert:** Process does NOT raise `RuntimeError`. Zero `WatcherBinding` objects created. A warning
is logged at WARN level. Health map `projects` is `{}`. Aggregate `watcher` state is `stopped` or
`configured_no_paths`, not `fail` (the `fail` state requires the profile to require watcher AND a
non-zero expected binding count).

### Scenario 3 — Env-pin override (unit + livewatch smoke)

**Setup:** Registry contains two projects. `CCDASH_WORKER_WATCH_PROJECT_ID=proj-abc123`.
**Assert:** Exactly one `WatcherBinding` created for `proj-abc123`. The second project is not
watched. Health map `projects` has one entry. Aggregate state `running` after startup.
(This is the backward-compatibility regression guard for OQ-3.)

### Scenario 4 — Dynamic add via reconcile loop (unit)

**Setup:** Boot with one project in registry. After `CCDASH_WATCHER_RECONCILE_INTERVAL_SECONDS`
elapses (or tick is triggered manually in test), add a second project to the registry mock.
**Assert:** After the next reconcile tick, a second `WatcherBinding` is created. The first binding
is unaffected (still running, `state: running` in health map). `lastReconcileAt` is updated.

### Scenario 5 — Per-project watcher failure isolation (unit)

**Setup:** Two project watchers running. Inject an exception into one project's watcher task.
**Assert:** The other project's watcher task continues running (`state: running` in health map).
The failed project transitions to `state: degraded`. The supervisor schedules a restart.
The aggregate `/readyz` transitions to `warn` (or `fail` if profile requires watcher), not
unhandled-crash. The main asyncio event loop remains alive.

### Scenario 6 — `/api/health/detail` `projects` map structure (integration)

**Setup:** Multi-project fan-out running.
**Assert:** `GET /api/health/detail` returns a JSON body where `watcher.projects` is an object
keyed by project id, each value containing `state`, `watchPathCount`, and `lastChangeSyncAt`.
Missing fields on individual entries fall back as specified in OQ-5.

---

## Summary Table

| OQ | Recommendation | Key constraint |
|---|---|---|
| OQ-2 | Watch ALL registered projects (not filtered by `is_active`) | inotify/FSEvents budget safe up to ~40 projects; `is_active` is a UI signal only |
| OQ-3 | env non-empty → single-project scope (unchanged); env empty/unset → registry fan-out | No operator relied on empty=watch-nothing; current empty raises RuntimeError |
| OQ-4/dynamic | Periodic reconcile loop in P3 (T3-004 in-scope); 60s default interval; D-002 defers hot-reload signaling | Boot-time-only is insufficient for long-running services; reconcile loop is low complexity |
| OQ-5 | Aggregate `/readyz` (degraded if any project degraded) + `projects` map in `/api/health/detail` per-project breakdown | FE resilience: missing `projects` → `{}`; missing per-entry fields → `{state:"unknown"}` |
| Concurrency | One asyncio Task per project; supervisor quarantines per-project failures; `asyncio.Semaphore(20)` shared sync ceiling | One project failure must NOT kill siblings; burst sync bounded by semaphore |
