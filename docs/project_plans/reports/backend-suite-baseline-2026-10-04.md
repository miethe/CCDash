---
doc_type: report
title: CCDash backend suite baseline — 2026-10-04
node: node_01M24XJTDBWC6DR4B5WCK4HPXQ
base: origin/development @ 8b9150d
---

# CCDash backend suite baseline (2026-10-04)

Command (fresh venv: `backend/requirements.txt` + pytest, pytest-asyncio, pytest-xdist,
pytest-timeout, plus editable `packages/ccdash_contracts` and `packages/ccdash_cli`):

    python -m pytest backend/tests --ignore=backend/tests/perf -n 6 --timeout=180

| State | failed | errors | passed |
|---|---|---|---|
| 8b9150d, venv without local packages | 170 | 14 | 4731 |
| 8b9150d, venv with local packages (MCP 23 + tomli_w 2 clear) | ~145 | 12 | n/a |
| this branch | 116 | 6 | 4792 |

`test_watcher_reconcile_db_fallback` (2) times out only under `-n 6` load; it passes 8/8 in isolation.

## Root-cause classes, in repair order

0. **Environment (25, not code).** The `backend.mcp.server` subprocess imports `ccdash_contracts`.
   `pytest.pythonpath` exposes that package to the test process but not to a child process.
   `tomli_w` arrives through `packages/ccdash_cli`. Fix: install both local packages in the venv.
1. **Composite-PK/child-FK fixture drift (v31/v48), FIXED HERE (~37).** Seed helpers used
   `ON CONFLICT(id)` against `sessions PRIMARY KEY (project_id, id)`. They also called
   `upsert_logs` / `upsert_artifacts` / `upsert_file_updates` without `project_id`, so the
   composite FK `(project_id, session_id) -> sessions(project_id, id)` failed.
2. **Workspace-scoping kwargs (#51) not mirrored in test fakes (~40).** Fake repos reject
   `workspace_id=` / `project_id=` (sessions, features, analytics, pricing and feature-execution routers).
   Fix (test-only): make the fakes accept the kwarg.
3. **Hand-built test schemas missing `workspace_id` columns (~17).** Affects test_live_metrics,
   test_repositories_bulk_fetch and test_feature_list_query.
4. **FK enforcement is ON after run_migrations (4).** test_mapping_resolver and
   test_test_visualizer_performance insert mappings/results without `test_definitions` and
   `test_domains` parent rows. Fix: seed the parents.
5. **Possible production defects (these need a real fix, not a fixture edit).**
   `SqliteTestDomainRepository.list_paginated()` rejects the `workspace_id` its caller passes.
   The observability backfill is not idempotent (`{'sessions': 1}` on rerun). The postgres
   migration upgrade re-runs `_TABLES`. `test_migration_governance` reports drift.
6. **Mode-D surface (auth/identity, Nick-gated).** test_storage_profiles auth-contract tuples
   (`CCDASH_API_TOKEN`), test_workspace_auth_integration (event loop), and the `/api/auth/session` route.
7. **Assorted single-file staleness (~20).** sync_coalescing mocks (`skip_manifest`,
   `_sync_in_flight`), data_domain layout/ownership sets, planning `object.execute`,
   visualizer DTO `latest_collected_at`, and request_context StopIteration.

Everything still open is tracked in one follow-up node (see the PR body).
