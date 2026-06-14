---
title: "CCDash Core Remediation — Execution-Time Findings"
doc_type: worknote
created: 2026-06-11
feature_slug: ccdash-core-remediation
findings_for: docs/project_plans/implementation_plans/enhancements/ccdash-core-remediation-v1.md
status: accepted
promoted_to: docs/project_plans/implementation_plans/enhancements/ccdash-runtime-deploy-remediation-v1.md
---

# CCDash Core Remediation — Execution-Time Findings

Lazy-created per the plan's In-Flight Findings policy. New findings surfaced during
wave execution are recorded here; load-bearing ones get a design-spec row in Phase 12.

## F-001 — Pre-existing FK-fixture failures in session-repository test suites (Phase 0)

**Discovered**: Phase 0 (Wave 1), 2026-06-11.
**Severity**: Low (pre-existing; not a Phase 0 regression).
**Status**: ✅ Resolved (T4-003, 2026-06-14).

Four tests failed with `sqlite3.IntegrityError: FOREIGN KEY constraint failed`:

- `backend/tests/test_sessions_repository_filters.py::SessionRepositoryFilterTests::test_session_detail_logs_are_limited_and_offsettable`
- `backend/tests/test_session_intelligence_repository.py::SessionIntelligenceRepositoryTests::test_replace_session_code_churn_facts_round_trips`
- `backend/tests/test_session_intelligence_repository.py::...::test_replace_session_scope_drift_facts_round_trips`
- `backend/tests/test_session_intelligence_repository.py::...::test_replace_session_sentiment_facts_replaces_existing_rows`

**Root cause (confirmed)**: fixture-seeding bug, not a product bug. `asyncSetUp` seeds
the parent `sessions` row under `project_id="project-1"`, but the child-row calls
(`upsert_logs`, `replace_session_sentiment_facts`, `replace_session_code_churn_facts`,
`replace_session_scope_drift_facts`) used the `project_id=""` default. The composite FK
`(project_id, session_id) REFERENCES sessions(project_id, id)` rejects `("", "session-1")`
because only `("project-1", "session-1")` exists.

**Fix**: passed explicit `project_id="project-1"` to each child-row call in the two test
files. All 14 tests in both suites now pass (14/14). No product-code change required.

## F-002 — `test_runtime_bootstrap.py` segfaults at pytest collection in this env

**Discovered**: Phase 0 (Wave 1).
**Severity**: Low (env/tooling, not product).
**Status**: ✅ Resolved (T4-004). Added header note to `backend/tests/test_runtime_bootstrap.py`
documenting the env hazard and the required run pattern (named-module invocation only, no dev
server running). Confirmed pre-existing at baseline `25b53e1`; not a product regression.
The correct invocation is: `backend/.venv/bin/python -m unittest backend.tests.test_runtime_bootstrap`.

## F-003 — `ac-coverage-report.py` does not parse nested-list `verified_by` in phase-spec ACs

**Discovered**: Phase 0 (Wave 1).
**Severity**: Low (tooling/format mismatch; no real coverage gap).
**Status**: ✅ Resolved (T4-005). `ac-coverage-report.py` updated to parse both the nested-list
YAML form and the inline `verified_by: [T0-005, T0-006]` form. Phase-0-completion.md AC→task
coverage now reports correctly without false "uncovered" warnings.

The phase-0 spec authors AC `verified_by` as nested YAML lists, e.g.:

```yaml
- verified_by:
    - T0-005
    - T0-006
```

Fix: parser now accepts both forms; no doc reformatting required.

---

## F-W3-001: AC 8.2 prose overclaims cross-trigger sync coalescing (non-blocking)

**Status**: ✅ Resolved (T4-001). Doc-only fix: AC 8.2 prose in the Phase 8 implementation plan
narrowed to scope coalescing to same-trigger dispatches, matching the `(project_id, trigger)`
keyed `_sync_in_flight` guard. No product-code change required.
**Surfaced**: Wave 3 validator gate (P8), 2026-06-11. **Severity**: Low (correctness-safe; prose/impl divergence).

Phase 8 AC 8.2 resilience prose says a coinciding *watcher* event and *reconcile* tick for the same
project "coalesce via the Phase 7 guard (no double-scan)." In implementation, the Phase 7 guard
`_sync_in_flight` keys on `(project_id, trigger)`. Watcher dispatches `trigger="watcher"`, reconcile
dispatches `trigger="reconcile"` — so the two do NOT coalesce against each other; only same-trigger
dispatches deduplicate.

Safe because upserts are idempotent (`ON CONFLICT(project_id, id)`), run through `retry_on_locked`,
and `context_window` uses `COALESCE(excluded, existing)`. A rare same-project watcher+reconcile overlap
performs at most one redundant idempotent pass — never a correctness fault. The binding requirement
("reconcile dispatches go through the guard; no double-scan reintroduced") is fully met.

Promotion options: (1) tighten AC 8.2 prose to scope coalescing to same-trigger dispatches [recommended, Phase 12];
(2) widen guard key to `(project_id)` only if redundant cross-trigger passes become measurable load [deferred, YAGNI].

## F-W3-002: test_sync_all_projects.py emits 3 unawaited-coroutine RuntimeWarnings (test hygiene)

**Status**: ✅ Resolved (T4-002). Coroutine fix applied: `asyncSetUp` now properly `await`s
`adapter.start()`, eliminating the 3 `RuntimeWarning: coroutine … was never awaited` emissions.
Tests continue to pass (21/21 P8 suite); no behaviour change.

## F-W6-001: Correlation-tab "Observed Workload" multi-feature session over-count (out of scope)

**Status**: Deferred (T4-006, 2026-06-14). **Surfaced**: T12-006 audit, 2026-06-12. **Severity**: Low/Med (display over-count, not a data-integrity fault).

The T12-006 audit (AC R12.6) confirmed the audited per-lifecycle-event in+out sum at `backend/routers/analytics.py` (≈ line 553/570, `session_metrics().total_tokens`) is **NOT** surfaced as a workload/total metric in any panel — that key is never accessed; aggregation loops read `token_input`/`token_output` separately into deduplicated per-dimension buckets. **AC R12.6 = PASS.**

Tangential discovery (distinct code path, NOT caused by the audited line): the **Correlation tab "Observed Workload" MetricCard** (`components/Analytics/AnalyticsDashboard.tsx` ≈ line 1142) sources `correlationSummary.totalTokens` from `/analytics/correlation` (`_session_usage_metrics` over session rows). A session linked to multiple features appears to be counted once per feature, producing a multi-feature over-count in that summary total.

**Rationale for deferral**: Phase 12 is docs/close-out only; the token-undercount remediation was explicitly out of scope (shipped 2026-03-09). This is a separate display-only over-count in the correlation path. No data-integrity or correctness impact on any current surface. No fix applied in Wave 6 or this epic.

**Promotion trigger**: if correlation totals are used for billing or quota enforcement, OR when operators report inflated workload numbers from the Correlation tab. Owner: analytics.

---

## F-DEPLOY-001: compose `*backend-build` anchor had no build `target` (RESOLVED 2026-06-12)

**Status**: ✅ Resolved (this change set). **Surfaced**: post-epic live-watch stack bring-up, 2026-06-12. **Severity**: High (enterprise stack non-functional).

The shared `x-backend-build: &backend-build` anchor in `deploy/runtime/compose.yaml` set `context`/`dockerfile`/`args` but no `target`. With no target, `docker build` selects the Dockerfile's **last stage** (`worker`). Every service — `api`, `backend` (local), and both watchers — therefore built the worker image and ran `python -m backend.worker`. The `api` container crashed at boot (`RuntimeError: CCDASH_RUNTIME_PROFILE must be one of: worker, worker-watch`) because it was a worker image being handed `CCDASH_RUNTIME_PROFILE=api`.

**Fix**: pinned an explicit `build.target` per service via the `<<: *backend-build` merge — `backend`→`runtime`, `api`→`api`, `worker`/`worker-watch`→`worker`. Verified post-rebuild: api container `Cmd=[python -m uvicorn backend.runtime.bootstrap_api:app …]`, all 5 containers healthy. The enterprise/postgres/live-watch stack had never been validated end-to-end before this (only the hosted `compose.hosted.env.example` smoke path, which builds the same way — it would have hit this too on a real run).

## F-DEPLOY-002: Postgres in-place upgrade path is broken below SCHEMA_VERSION 35 (DEFERRED)

**Status**: Open — deferred (worked around by volume wipe). **Surfaced**: live-watch bring-up against a pre-existing PG volume, 2026-06-12. **Severity**: Medium (only affects existing Postgres DBs; fresh DBs unaffected).

`backend/db/postgres_migrations.py:_run_migrations_inner` executes the full `_TABLES` DDL batch **before** the versioned 29→35 ALTERs. The `_TABLES` batch now embeds `project_id`-dependent objects (e.g. `CREATE INDEX … ON sessions(project_id, status, updated_at)`, composite `PRIMARY KEY (project_id, id)`). On a pre-existing DB below v35, the `sessions` table already exists, so `CREATE TABLE IF NOT EXISTS` no-ops — but the standalone `CREATE INDEX` against `project_id` runs against the *old* table that lacks the column, failing with `UndefinedColumnError: column "project_id" does not exist`. The ALTERs that would add `project_id` never get a chance to run. Net effect: **only freshly-created Postgres DBs migrate; in-place upgrades from older schema versions fail.**

Worked around here by `docker volume rm ccdash_ccdash-postgres` (the DB is a derived, rebuildable cache — safe to wipe). Real impact is low today because the PG path was effectively dead-on-arrival pre-epic, so stale dev volumes are the only victims.

**Promotion trigger**: before any deployment that must preserve an existing Postgres CCDash DB across an upgrade. **Fix direction**: split `_TABLES` so column-dependent indexes/constraints are created *after* the versioned column ALTERs, or make the index creation idempotent/ordered behind the version gate. Owner: data-layer. Add a `compose_smoke` step that boots against a *seeded older-version* PG volume, not just a fresh one.

## F-DEPLOY-003: worker-watch binds exactly one hardcoded project id per process (DESIGN LIMITATION)

**Status**: Open — design limitation flagged by operator, 2026-06-12. **Severity**: Medium (operability / multi-project UX).

Each `worker-watch` process binds exactly one project via `CCDASH_WORKER_WATCH_PROJECT_ID`, set in a gitignored env overlay (`deploy/runtime/watchers/*.env`). Consequences operators hit: (1) the watched project must be hand-copied into an env file and kept in sync with the app's **DB-authoritative** active project (ADR-006) — a silent "health-green but UI-empty" mismatch when they drift; (2) watching N projects means hand-running N watcher services with N probe ports. Operator question, verbatim: *"I don't like needing to set that in a config file. It should really just work based on what's configured in app. Otherwise, what's the point of multiple watchers and projects?"*

The current single-project binding is documented as a v1 limitation (`deploy/runtime/.env` comments, `containerized-deployment-quickstart.md` data-visibility checks), not a bug — but the operator's critique is sound. **Fix direction**: let a watcher derive its target set from the DB-authoritative project registry (watch all registered, or all `active`, projects in one process) instead of a single env-pinned id; env override becomes an optional scoping filter, not a requirement. This is an architecture change (registry-driven watch fan-out + per-project probe/health rollup), not a quick fix — needs a PRD/plan. **Promotion trigger**: next multi-project enterprise deployment, or when planning the watcher's v2.
