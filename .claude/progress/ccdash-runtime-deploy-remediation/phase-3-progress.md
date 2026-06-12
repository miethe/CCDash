---
schema_version: 2
doc_type: progress
phase: 3
phase_title: "Registry-driven watcher fan-out implementation (W2)"
feature_slug: ccdash-runtime-deploy-remediation
status: not-started
created: 2026-06-12
updated: 2026-06-12
overall_progress: 0
completion_estimate: null
parallelization:
  strategy: batch-parallel
  batch_1: [T3-001]
  batch_2: [T3-002, T3-003, T3-004]
  batch_3: [T3-005, T3-006]
  batch_4: [T3-007]
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
    status: pending
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
    status: pending
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
    status: pending
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
    status: pending
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
    status: pending
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
    status: pending
    assigned_to: documentation-writer
    assigned_model: haiku
    model_effort: adaptive
    description: >
      Update deploy/ compose files and .env.example: CCDASH_WORKER_WATCH_PROJECT_ID
      marked optional with comment. Update watcher section in
      docs/guides/containerized-deployment-quickstart.md — optional semantics.

  - id: T3-007
    name: "Manual livewatch smoke"
    status: pending
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
| AC-T3-001 (ADR-006) | Empty env var → multiple WatcherBinding objects; env-pin → single binding; ADR-006 compliant | T3-005 (`test_p3_worker_bootstrap.py`), T3-007 (livewatch smoke) | pending |
| AC-T3-003 (R-P2) | `/api/health/detail` watcher section has `projects` map; FE missing-key resilience documented | T3-005, `GET /api/health/detail` probe | pending |

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
