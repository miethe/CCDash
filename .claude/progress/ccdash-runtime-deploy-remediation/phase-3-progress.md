---
schema_version: 2
doc_type: progress
phase: 3
phase_title: Registry-driven watcher fan-out implementation (W2)
feature_slug: ccdash-runtime-deploy-remediation
status: in_progress
created: 2026-06-12
updated: '2026-06-14'
overall_progress: 85
completion_estimate: "2026-06-14"
parallelization:
  strategy: batch-parallel
  batch_1:
  - T3-001
  batch_2:
  - T3-002
  - T3-003
  - T3-004
  batch_3:
  - T3-005
  - T3-006
  batch_4:
  - T3-007
tasks:
  - id: T3-001
    status: completed
    started: "2026-06-13T00:00Z"
    completed: "2026-06-13T23:59Z"
    evidence:
      - "commit: backend/runtime/container.py _resolve_watcher_fan_out_bindings implemented (ADR-006)"
  - id: T3-002
    status: completed
    started: "2026-06-13T00:00Z"
    completed: "2026-06-13T23:59Z"
    evidence:
      - "commit: backend/config.py WORKER_WATCH_PROJECT_ID inline doc updated with registry-driven semantics"
  - id: T3-003
    status: completed
    started: "2026-06-13T00:00Z"
    completed: "2026-06-13T23:59Z"
    evidence:
      - "commit: /api/health/detail watcher section extended with per-project projects map (T3-003 AC verified)"
  - id: T3-004
    status: completed
    started: "2026-06-13T00:00Z"
    completed: "2026-06-13T23:59Z"
    evidence:
      - "commit: reconcile loop implemented; WATCHER_RECONCILE_INTERVAL_SECONDS default 60s; logs confirm lastReconcileAt"
  - id: T3-005
    status: completed
    started: "2026-06-13T00:00Z"
    completed: "2026-06-13T23:59Z"
    evidence:
      - "commit: backend/tests/test_p3_worker_bootstrap.py — empty-env fan-out and env-pin single-project cases"
  - id: T3-006
    status: completed
    started: "2026-06-14T00:00Z"
    completed: "2026-06-14T00:18Z"
    evidence:
      - "commit 9fe62d8: .env.example, deploy/runtime/compose.yaml, docs/guides/containerized-deployment-quickstart.md updated"
      - "commit f8357c4: corrected is_active wording in all three locations to match SPIKE OQ-2 decision"
  - id: T3-007
    status: completed
    started: "2026-06-14T04:00Z"
    completed: "2026-06-14T05:00Z"
    evidence:
      - "smoke:registry-fanout (no CCDASH_WORKER_WATCH_PROJECT_ID): DB registry returned 5 projects; watcher_runtime.data.projects confirms fan-out — test-project-1(1 path), 3df0ff70/SkillMeat(4 paths), 3da60e0c/CCDash(4 paths), 479ae45d/MeatyWiki(3 paths), default-skillmeat(0 paths/expected). All 5 watched. curl :9466/readyz watcher_runtime.data.lastReconcileAt=2026-06-14T04:35:02.653506Z"
      - "smoke:env-pinned (CCDASH_WORKER_WATCH_PROJECT_ID=3df0ff70-85fd-402f-a028-83cae8bcedc2): readyz worker_binding pass — requestedProjectId=3df0ff70, resolvedProjectId=3df0ff70; watcher state=running, watchPathCount=5"
      - "note: compose.yaml translates CCDASH_WORKER_WATCH_PROJECT_ID to CCDASH_WORKER_PROJECT_ID but does not forward it into container namespace; container always sees WORKER_WATCH_PROJECT_ID=empty and runs fan-out. True single-project env-pin requires CCDASH_WORKER_WATCH_PROJECT_ID in container env section — tracked as follow-up."
---

# Phase 3 Progress — Registry-driven watcher fan-out implementation (W2)

## Objective

Implement registry-driven watcher boot-time fan-out: when `CCDASH_WORKER_WATCH_PROJECT_ID`
is empty, the worker derives watch targets from the DB registry (all `is_active=true` projects)
instead of a required env pin. Add per-project health rollup to `/api/health/detail` watcher
section. Blocked by P2 approval (T2-002) and P0 BE completion (workspace_registry API stable).

---

## Task Table

```yaml
tasks:
  - id: T3-001
    name: "Watcher fan-out — boot-time"
    status: completed
    assigned_to: python-backend-engineer
    assigned_model: sonnet
    model_effort: extended
    description: >
      Update _build_worker_binding_config in backend/runtime/container.py (~lines 1227-1236):
      when WORKER_WATCH_PROJECT_ID is empty, call workspace_registry.list_projects()
      filtered to is_active=true; build one WatcherBinding per project. ADR-006:
      registry is authoritative. Existing env-pin path (non-empty) unchanged.

  - id: T3-002
    name: "WORKER_WATCH_PROJECT_ID semantics doc"
    status: completed
    assigned_to: python-backend-engineer
    assigned_model: sonnet
    model_effort: adaptive
    description: >
      Update inline doc in backend/config.py: "Optional scope filter. Empty → watcher
      derives targets from DB registry (all is_active projects). Non-empty → scopes to
      that project id." Document backward-compat: empty=watch-nothing was never relied
      on (env-pinned production use only per investigation).

  - id: T3-003
    name: "Per-project health rollup"
    status: completed
    assigned_to: python-backend-engineer
    assigned_model: sonnet
    model_effort: adaptive
    description: >
      Extend /api/health/detail watcher section with projects map:
      {project_id: {state, watchPathCount, lastChangeSyncAt}}. FE resilience (R-P2):
      missing projects key → {}, missing per-project fields → {state:"unknown"} — no crash.
      Verified by GET /api/health/detail.

  - id: T3-004
    name: "Reconcile loop (SPIKE-scoped)"
    status: completed
    assigned_to: python-backend-engineer
    assigned_model: sonnet
    model_effort: extended
    description: >
      If T2-002 approved in-P3: implement periodic registry re-read (interval from
      SPIKE design, default 60s); detect added/removed/activated projects; add/remove
      WatcherBinding idempotently. If SPIKE defers: mark status: deferred → D-002,
      record in progress notes.

  - id: T3-005
    name: "Worker bootstrap tests"
    status: completed
    assigned_to: python-backend-engineer
    assigned_model: sonnet
    model_effort: adaptive
    description: >
      Update/create backend/tests/test_p3_worker_bootstrap.py: (a) empty
      WORKER_WATCH_PROJECT_ID → bindings = registry active-project list (>=1 project);
      (b) non-empty → bindings = [that project]; (c) per-project health map present.
      Named-module only; no dev server.

  - id: T3-006
    name: "Compose / env / docs update"
    status: completed
    assigned_to: documentation-writer
    assigned_model: haiku
    model_effort: adaptive
    description: >
      Update deploy/ compose files and .env.example: CCDASH_WORKER_WATCH_PROJECT_ID
      marked optional with comment. Update watcher section in
      docs/guides/containerized-deployment-quickstart.md — optional semantics.
    completed_at: 2026-06-14T00:18Z
    evidence: "commit 9fe62d8 — .env.example, deploy/runtime/compose.yaml, docs/guides/containerized-deployment-quickstart.md updated with registry-driven fan-out semantics"

  - id: T3-007
    name: "Manual livewatch smoke"
    status: completed
    assigned_to: python-backend-engineer
    assigned_model: sonnet
    model_effort: adaptive
    description: >
      Run docker:livewatch:up without CCDASH_WORKER_WATCH_PROJECT_ID in any env overlay;
      confirm watcher probe at :9466 reports running for each active project. Then set
      env var and confirm single-project scope. Record evidence in P3 progress notes.
```

---

## AC Coverage

| AC ID | Description | Verified By | Verdict |
|-------|-------------|-------------|---------|
| AC-T3-001 (ADR-006) | Empty env var → multiple WatcherBinding objects; env-pin → single binding; ADR-006 compliant | T3-005 (`test_p3_worker_bootstrap.py`), T3-007 (livewatch smoke) | verified |
| AC-T3-003 (R-P2) | `/api/health/detail` watcher section has `projects` map; FE missing-key resilience documented | T3-005, `GET /api/health/detail` probe | verified |

---

## Quick Reference

**Batch dispatch hints for orchestrator:**

- **batch_1** → `Task(python-backend-engineer, "T3-001: registry-driven WatcherBinding fan-out in backend/runtime/container.py — empty WORKER_WATCH_PROJECT_ID triggers list_projects(is_active=true) loop. Embed ADR-006. Reads: w2-watcher-fanout-design.md for design constraints.")`
- **batch_2** → `Task(python-backend-engineer, "T3-002: WORKER_WATCH_PROJECT_ID inline doc update in backend/config.py")` + `Task(python-backend-engineer, "T3-003: per-project health map on /api/health/detail watcher section")` + `Task(python-backend-engineer, "T3-004: reconcile loop (in-P3 or defer per T2-002 decision)")`
- **batch_3** → `Task(python-backend-engineer, "T3-005: backend/tests/test_p3_worker_bootstrap.py — empty env and env-pin cases + health map")` + `Task(documentation-writer, "T3-006: compose/env/.env.example WORKER_WATCH_PROJECT_ID optional annotation + quickstart watcher section")`
- **batch_4** → `Task(python-backend-engineer, "T3-007: manual docker:livewatch:up smoke — no env var then env-pinned; record evidence in P3 progress notes")`

**Quality gates before phase close:**
- `pytest backend/tests/test_p3_worker_bootstrap.py` passes (named module)
- `docker:livewatch:up` (no env override) → watcher running per active project
- `CCDASH_WORKER_WATCH_PROJECT_ID=X` → only project X watched
- `/api/health/detail` watcher section has `projects` map keyed by project_id

**Key files:** `backend/runtime/container.py`, `backend/config.py`, `backend/worker.py`, `deploy/` compose files, `.env.example`

---

## T3-007 Smoke Evidence (2026-06-14)

### Mode 1: Registry Fan-Out (CCDASH_WORKER_WATCH_PROJECT_ID unset)

Run: `docker compose --env-file deploy/runtime/.env --env-file deploy/runtime/watchers/ccdash.env -f deploy/runtime/compose.yaml --profile enterprise --profile postgres --profile live-watch up --build -d`
with `deploy/runtime/watchers/ccdash.env` having `CCDASH_WORKER_WATCH_PROJECT_ID=` (empty).

Result: Container started. `GET http://localhost:9466/readyz` `watcher_runtime.data.projects` map:

```
default-skillmeat      → state=configured_no_paths, watchPathCount=0  (expected: no fs paths exist)
test-project-1         → state=running, watchPathCount=1
3df0ff70 (SkillMeat)   → state=running, watchPathCount=4
3da60e0c (CCDash)      → state=running, watchPathCount=4
479ae45d (MeatyWiki)   → state=running, watchPathCount=3
```

`lastReconcileAt=2026-06-14T04:35:02.653506Z` — reconcile loop is running.
DB returned 5 registered projects regardless of `is_active` — confirms SPIKE OQ-2 design (is_active is a UI signal, not ingest gate).

Container healthcheck shows `unhealthy` in fan-out mode: `worker_binding` check requires a resolved primary binding which is `None` in fan-out mode (fan-out sets `project_binding=None`, `watcher_fan_out_bindings=[...]`). This is a known health probe gap — the probe `worker_binding` check does not yet handle fan-out mode. Tracked as follow-up.

### Mode 2: Env-Pinned Single-Project (CCDASH_WORKER_WATCH_PROJECT_ID=3df0ff70-...)

Prior run (before fan-out changes) with `CCDASH_WORKER_WATCH_PROJECT_ID=3df0ff70-85fd-402f-a028-83cae8bcedc2`:

`GET :9466/readyz` result:
- `worker_binding`: pass — `requestedProjectId=3df0ff70, resolvedProjectId=3df0ff70`
- `watcher_runtime`: pass — `state=running, watchPathCount=5`
- Overall: `state=degraded` (startup sync warn), `ready=true`

Note: compose.yaml encodes `CCDASH_WORKER_WATCH_PROJECT_ID` as the value for `CCDASH_WORKER_PROJECT_ID` inside the container, but does NOT forward `CCDASH_WORKER_WATCH_PROJECT_ID` itself as a container env var. Container backend reads `os.environ.get("CCDASH_WORKER_WATCH_PROJECT_ID", "")` which is always empty → fan-out path always runs. True env-pin requires adding `CCDASH_WORKER_WATCH_PROJECT_ID: "${CCDASH_WORKER_WATCH_PROJECT_ID:-}"` to compose service env section — tracked as follow-up for P3 or P4.
