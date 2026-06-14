---
schema_version: 2
doc_type: worknote
title: "CCDash Runtime & Deploy Remediation v1 — Feature Guide"
status: published
created: 2026-06-14
feature_slug: ccdash-runtime-deploy-remediation
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-runtime-deploy-remediation-v1.md
impl_plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-runtime-deploy-remediation-v1.md
---

# CCDash Runtime & Deploy Remediation v1 — Feature Guide

This guide summarizes the four workstreams delivered in the Runtime & Deploy Remediation epic across six phases (P0–P5). The feature resolves registry-authority leaks in project selection and watcher fan-out, fixes a critical Postgres migration path, and triages accumulated findings.

---

## What Was Built

**W1: Registry-Authoritative Project Resolution (P0)**

The API `/api/projects` endpoint now honors the DB registry's `is_active` flag. Projects are ordered `ORDER BY is_active DESC, name ASC`, ensuring active projects appear first. A computed `is_seed` field identifies example projects (`default-skillmeat`, etc.) without adding a DB column. The FE app-shell scope guard (`resolveScopeOutcome` in `contexts/AppSessionContext.tsx`) clears stale non-active project scope and defaults to the first active project on load. **Seam verified**: P0-T0-005 integration test + browser smoke test confirm default landing on active project with data visible.

**W2: Registry-Driven Watcher Fan-Out (P2→P3)**

The worker-watch runtime now derives its watch target set from the DB project registry instead of a single `CCDASH_WORKER_WATCH_PROJECT_ID` env pin. The env var is now optional (backward compatible: non-empty → single-project scope override; absent/empty → registry fan-out all registered projects). Per-project watcher tasks run in isolated asyncio Tasks with supervisor quarantine for per-project failures — one project's watch error cannot cascade. A 60-second reconcile loop (`CCDASH_WATCHER_RECONCILE_INTERVAL_SECONDS`) periodically re-reads the registry and idempotently adds/removes watch bindings for new/deregistered projects. Per-project health metrics surface in `/api/health/detail` under `watcher.projects` (state, watchPathCount, lastChangeSyncAt per project). Bounded concurrency ceiling (`CCDASH_WATCHER_SYNC_CONCURRENCY`, default 20) prevents burst filesystem events from overwhelming the sync engine.

**W3: Postgres In-Place Upgrade Fix (P1)**

The migration reorder in `backend/db/postgres_migrations.py` ensures `project_id`-dependent indexes are created AFTER the v30 column-adding ALTERs complete. A deeper composite child-table FK issue (inline `REFERENCES sessions(project_id, id)`) was resolved by moving FKs out of table-creation blobs into the versioned composite-PK migration (commit acfd626). The `_run_migrations_inner` entry point now gates all index creation behind `IF NOT EXISTS` idempotency guards. Seeded-v29-volume → v35 smoke test validates the in-place path on a real pre-v35 baseline.

**W4: Finding Triage & Cleanup (P4)**

Six findings from the investigation report were triaged: F-W1-001 (seed project visibility), F-W2-001/002 (watcher capacity, boot-time-only behavior), F-W3-001/002 (correlation overcounting, dynamic registry rebind), F-001/002/003 (test tooling). Five findings were resolved in-phase (fixed or deferred with design specs). F-W6-001 (correlation over-count, maturity: idea) is deferred to D-001 design spec. F-W2-002 (dynamic hot-reload, maturity: shaping) is deferred to D-002 design spec. All remaining findings closed with no open issues.

---

## Architecture Overview

### W1 & W3 — Two-Layer Ordering Fix

**Project layer**: `DbProjectManager.list_projects()` (P0-BE) fetches from DB with `ORDER BY is_active DESC, name ASC`. The `is_seed` field is computed client-side from a hardcoded allowlist (no DB schema change). **API layer**: `routers/projects.py:get_projects()` (P0-BE) returns the ordered list. **FE app-shell**: `contexts/AppSessionContext.tsx:refreshProjects()` (P0-FE) applies scope guard logic: if a persisted scope exists AND that project is still `is_active`, use it; otherwise default to the first `is_active` project.

**Migration ordering**: `backend/db/postgres_migrations.py:_run_migrations_inner()` (P1) sequences table creation, column ALTERs (v30+), then index/FK creation. Pre-v35 baselines that hit the v29→v35 gap now migrate cleanly.

### W2 — Registry-Driven Watcher Architecture

**Registry binding**: `backend/runtime/container.py:_build_worker_binding_config()` (P3-T3-001) reads the project registry, builds one `WatcherBinding` per project (or just the pinned project if `CCDASH_WORKER_WATCH_PROJECT_ID` is non-empty). **Per-project isolation**: each binding runs in its own `asyncio.Task` (`ccdash:watcher:{project_id}`). A supervisor catches failures via `task.add_done_callback`, marks the project state as `degraded`, and schedules restart with exponential backoff (30s → 5min). **Reconcile loop** (P3-T3-004): every 60s, re-read registry, compute diff, idempotently add/remove bindings. **Health rollup** (P3-T3-003): aggregate `/readyz` check (`pass`/`warn`/`fail` per OQ-5 semantics); per-project breakdown in `/api/health/detail` → `watcher.projects` map (state, watchPathCount, lastChangeSyncAt). **Bounded sync**: `asyncio.Semaphore(CCDASH_WATCHER_SYNC_CONCURRENCY, default 20)` caps simultaneous sync executions.

---

## How to Test

**Test suite coverage:**

1. **test_projects_registry.py** (23 tests): P0 project ordering, `is_seed` computation, FE scope guard fallback behavior, active-project default resolution.
2. **test_p3_worker_bootstrap.py** (33 tests): W2 multi-project fan-out, env-pin override backward-compat, empty-registry warning, per-project isolation, reconcile loop add/remove, health rollup structure.
3. **test_p3_watcher_registry.py** (55 tests): reconcile diff computation, idempotent binding add/remove, supervisor failure quarantine, task restart backoff, per-project state tracking.
4. **test_postgres_migrations_upgrade.py** (26 tests): fresh-DB and seeded-v29-volume upgrade to v35, column-parity checks, index idempotency, FK composite-key ordering.
5. **test_sync_all_projects.py** (13 tests with `-W error::RuntimeWarning`): sync coalescing across N projects, bounded-concurrency semaphore enforcement, per-project error isolation.

**Integration smoke:**

```bash
npm run docker:hosted:smoke:seeded-pg
```

Runs a real Postgres v29 → v35 migration in a container, validates applied state, tears down. Non-zero exit on any failure.

**Live watcher smoke** (requires clean 5432):

```bash
npm run docker:livewatch:up  # or with env override: CCDASH_WORKER_WATCH_PROJECT_ID=<id>
```

Boots multi-project worker-watch, verifies per-project health in `/api/health/detail`, confirms registry reconcile loop picks up new projects added via CLI while running.

---

## Coverage Summary

| Workstream | Scope | Coverage | Evidence |
|-----------|-------|----------|----------|
| **W1** | Active-project first-load; is_seed filtering | Covered | P0-T0-003 registry tests (23); P0-T0-006 scope guard test (P0-T0-006); browser smoke |
| **W2** | Multi-project fan-out, per-project isolation, reconcile, health rollup, backward-compat | Covered | P3-T3-001/002 bootstrap (33), P3-T3-003/004 watcher/reconcile (55), health rollup in test_p3_watcher_registry.py |
| **W3** | v29→v35 upgrade, index reordering, FK composite-key ordering | Covered | P1-T1-001/002 migrations (26); seeded-pg smoke test |
| **W4** | Finding triage, design spec links | Covered | P4 all 6 findings dispositioned; D-001 & D-002 design specs at docs/project_plans/design-specs/ |

---

## Known Limitations

- **D-001** (correlation over-count): deferred as design spec. Promotion trigger: when cross-session aggregation inaccuracy impacts user-facing analytics; investigate at that time (not anticipated in current roadmap).
- **D-002** (dynamic watcher rebind): boot-time-only with 60s periodic reconcile; full hot-reload signaling deferred. Reconcile loop introduces up-to-60s lag for new-project pickup. Promotion trigger: if registry churn exceeds one change per hour in production or operator explicitly requests sub-second rebind.
- **Live-watch smoke not run in CI**: conflicts with a running stack on macOS port 5432 (test isolation issue, not a product limitation). CI runs named-test suites only; local operator can run `docker:livewatch:up` for manual verification.
