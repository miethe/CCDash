---
schema_version: 2
doc_type: prd
title: "CCDash Runtime & Deploy Remediation v1 — PRD"
status: draft
created: 2026-06-12
updated: 2026-06-12
feature_slug: ccdash-runtime-deploy-remediation
feature_version: "v1"
priority: high
risk_level: high
spike_ref: docs/project_plans/reports/investigations/ccdash-runtime-deploy-remediation-investigation.md
prd_ref: null
plan_ref: null
related_documents:
  - docs/project_plans/adrs/adr-006-db-authoritative-project-registry.md
  - docs/project_plans/adrs/adr-007-db-write-failure-surfacing-standard.md
  - .claude/findings/ccdash-core-remediation-findings.md
  - docs/guides/containerized-deployment-quickstart.md
references:
  user_docs:
    - docs/guides/containerized-deployment-quickstart.md
  context:
    - .claude/worknotes/ccdash-runtime-deploy-remediation/
  specs: []
  related_prds: []
changelog_required: true
owner: null
contributors: []
tags: [prd, deploy, registry, postgres, watcher, remediation]
---

# Feature Brief & Metadata

**Feature Name:** CCDash Runtime & Deploy Remediation v1

**Filepath Name:** `ccdash-runtime-deploy-remediation-v1`

**Date:** 2026-06-12

**Related Documents:**
- Investigation report: `docs/project_plans/reports/investigations/ccdash-runtime-deploy-remediation-investigation.md`
- ADR-006 (registry authority): `docs/project_plans/adrs/adr-006-db-authoritative-project-registry.md`
- ADR-007 (write-failure surfacing): `docs/project_plans/adrs/adr-007-db-write-failure-surfacing-standard.md`
- Open findings: `.claude/findings/ccdash-core-remediation-findings.md`

---

## 1. Executive Summary

A live-stack investigation against the enterprise+postgres+live-watch container stack
confirmed that session ingest, storage, and the API read path are all healthy (1,167 sessions
for the active project), but operators see "no data flowing" because the UI lands on a
seed/example project on startup instead of the DB-authoritative active project — an
ADR-006 violation in the runtime read path. This epic remediates that user-visible defect
(W1), extends registry authority to the watcher fan-out (W2), fixes a broken Postgres
in-place upgrade path for pre-v35 DBs (W3), and closes accumulated tooling/test debt (W4).

**Priority:** HIGH

**Key Outcomes:**
- Outcome 1: On first load the UI lands on the `is_active=true` project and sessions are
  immediately visible — no manual project switching required.
- Outcome 2: Watcher derives its watch-target set from the DB registry (ADR-006), removing
  the requirement to hand-configure `CCDASH_WORKER_WATCH_PROJECT_ID`.
- Outcome 3: A Postgres DB provisioned at any version ≥ v29 migrates to v35 in place without
  errors; operators no longer need to wipe the derived-cache volume to recover.

---

## 2. Context & Background

### Current State

The enterprise stack runs five containers (api :8843, frontend :3843, postgres :5843,
worker :9465, worker-watch :9466). Data ingest is healthy and the API returns correct
results when queried with the right `project_id`. The operator-reported "no data" symptom
is not a data-pipeline failure.

### Problem Space

Three independent registry-authority leaks cause the symptom set:

1. **Project-list ordering** (`backend/db/repositories/projects.py` line 224):
   `SELECT * FROM projects ORDER BY created_at ASC` — seed projects created first always
   sort to the top of `GET /api/projects`.

2. **Frontend scope-validation gap** (`contexts/AppSessionContext.tsx`):
   `getProjectScope()` reads a localStorage key (`PROJECT_SCOPE_STORAGE_KEY`). If the
   stored id matches any project in the list (including `default-skillmeat`), the context
   sets that project as active and returns early — `getActiveProject()` is never called,
   so the DB-authoritative `is_active` flag is silently ignored.

3. **Watcher env-pin** (`backend/config.py` line 1007,
   `backend/runtime/container.py` lines 1227–1236): `CCDASH_WORKER_WATCH_PROJECT_ID`
   is the sole watcher-binding mechanism. An empty or stale env var produces a
   "health-green / UI-empty" divergence silently.

A fourth, independent defect: `backend/db/postgres_migrations.py:_run_migrations_inner`
(line 2344) executes the full `_TABLES` DDL block — including `CREATE INDEX … ON
sessions(project_id, …)` — before the versioned v30 ALTER that adds `project_id` to the
`sessions` table in pre-existing databases. On any PG DB below v30 the index creation
raises `UndefinedColumnError` and the versioned column-adding ALTERs never run.

### Current Workarounds

- Operator manually selects the correct project in the UI switcher after each page load.
- Watcher project id is hand-copied into a gitignored env overlay; must be kept in sync
  with the DB-active project after every `ccdash project use` operation.
- Pre-existing PG volumes must be wiped before a v35 stack deployment.

### Architectural Context

- **Router → Service → Repository**: `projects_router` in `backend/routers/projects.py`
  delegates to `core_ports.workspace_registry`, which is backed by
  `backend/db/repositories/projects.py` (DB-authoritative, ADR-006).
- **Frontend data layer**: `AppSessionContext` (`contexts/AppSessionContext.tsx`) is the
  sole shell provider for project state. It reads `getProjectScope()` from localStorage
  and calls `client.getActiveProject()` only when no scoped project is found.
- **Watcher binding**: resolved in `backend/runtime/container.py` ~line 1227–1236 from
  `config.WORKER_WATCH_PROJECT_ID`.
- **Migrations**: `backend/db/postgres_migrations.py:_run_migrations_inner` (line 2329)
  is the single Postgres migration entry point; `SCHEMA_VERSION = 35`.

---

## 3. Problem Statement

> "As an operator, when I open the CCDash dashboard after starting the container stack, I
> see an empty session list instead of my active project's 1,167 sessions, because the UI
> defaults to the seed project `default-skillmeat` rather than the DB-authoritative active
> project. I have to manually switch projects every time."

**Technical Root Causes:**

1. `backend/db/repositories/projects.py` line 224: `ORDER BY created_at ASC` —
   seed projects always first; `is_active` is not used as a sort key.
2. `contexts/AppSessionContext.tsx`: stored localStorage scope short-circuits the
   `getActiveProject()` call even when the scoped project is `is_active=false`.
3. `backend/config.py` / `backend/runtime/container.py`: watcher is single-project,
   env-pinned; ignores the DB registry entirely (ADR-006 violation).
4. `backend/db/postgres_migrations.py`: `_TABLES` `project_id`-dependent `CREATE INDEX`
   statements execute on existing pre-v30 tables before the v30 column-adding ALTER runs,
   causing `UndefinedColumnError` on in-place upgrades.

---

## 4. Goals & Success Metrics

### Primary Goals

**G1 — Registry-authoritative default project selection**
The UI must land on the `is_active=true` project on first load. No manual switching.

**G2 — Registry-driven watcher fan-out**
The watcher must derive its target set from the DB registry. `CCDASH_WORKER_WATCH_PROJECT_ID`
is demoted to an optional scoping filter.

**G3 — Safe Postgres in-place upgrades**
Any PG DB at schema version ≥ v29 must upgrade to v35 in place without errors or volume
wipes.

**G4 — Test & tooling debt cleared**
Accumulated findings (F-W3-001/002, F-001/002/003, F-W6-001) triaged and either fixed
in-scope or explicitly deferred with documented rationale.

### Success Metrics

| Metric | Baseline | Target | How to Measure |
|--------|----------|--------|----------------|
| First-load project correctness | Lands on seed/empty project | Lands on `is_active=true` project | Runtime smoke: observe active project on load |
| Watcher config required fields | `CCDASH_WORKER_WATCH_PROJECT_ID` required | env var optional; omit → watches all active projects | `docker:livewatch:up` without env var; verify probe passes |
| PG in-place upgrade success rate | 0% (volume wipe required) | 100% for DB ≥ v29 | `docker:hosted:smoke:seeded-pg` against v29 seed volume |
| Open finding count (W4 scope) | 5 open findings | 0 open, all resolved or deferred-with-note | `.claude/findings/ccdash-core-remediation-findings.md` |

---

## 5. User Personas & Journeys

**Primary — Self-hosted operator**
- Starts the enterprise+postgres+live-watch stack via `npm run docker:livewatch:up`.
- Expects to see live sessions immediately on dashboard load.
- Does not want to configure env files for every project-id change.

**Secondary — Multi-project operator**
- Runs N projects; wants all N watched by one watcher process without N separate env
  overlays.
- Expects `/api/health/detail` to show per-project watcher health.

---

## 6. Requirements

### 6.1 Functional Requirements

| ID | Requirement | Priority | Owner Surface |
|:--:|------------|:--------:|--------------|
| FR-1 | `GET /api/projects` returns the `is_active=true` project as the first item in the list (ORDER BY `is_active DESC, created_at ASC`). | Must | `backend/db/repositories/projects.py` |
| FR-2 | Each project in `GET /api/projects` response includes an `is_seed` boolean field. Seed projects (`default-skillmeat`, `test-project-1`) are flagged `is_seed: true`. | Must | `backend/models.py`, `backend/db/repositories/projects.py` |
| FR-3 | `contexts/AppSessionContext.tsx:refreshProjects()`: if the localStorage-scoped project has `is_active === false` and another project in the list has `is_active === true`, clear the stale scope and switch to the active project (call `getActiveProject()`). | Must | `contexts/AppSessionContext.tsx` |
| FR-4 | `CCDASH_WORKER_WATCH_PROJECT_ID` becomes optional. When unset, the watcher watches all projects returned by the DB registry. When set, it scopes to that one project. | Must | `backend/runtime/container.py`, `backend/config.py` |
| FR-5 | Per-project watcher health (state, `watchPathCount`, `lastChangeSyncAt`) is exposed in the existing `/api/health/detail` watcher section, keyed by project id. | Should | `backend/runtime/container.py` |
| FR-6 | `backend/db/postgres_migrations.py:_run_migrations_inner` — `project_id`-dependent `CREATE INDEX` statements in `_TABLES` are deferred (moved out of `_TABLES` or gated) so they only execute after the v30 column-adding ALTERs have run. | Must | `backend/db/postgres_migrations.py` |
| FR-7 | A new compose smoke step (`docker:hosted:smoke:seeded-pg`) boots against a PG volume seeded at v29 and verifies a clean migration to v35 with no errors and `migrationStatus: "applied"` from `/api/health/ready`. | Must | `package.json`, `deploy/runtime/` |
| FR-8 | F-W3-001 (AC prose overclaim) is corrected via a doc patch; F-W3-002 (unawaited-coroutine warnings in `test_sync_all_projects.py`) is fixed; F-001/F-002/F-003 are triaged and resolved or deferred-with-note. | Should | `backend/tests/`, `.claude/findings/ccdash-core-remediation-findings.md` |

### 6.2 Non-Functional Requirements

**Resilience:**
- `is_seed` missing or null in the API response MUST be treated as `false` by the FE
  (R-P2: new optional field requires explicit FE fallback AC).
- Per-project watcher health missing or null fields MUST NOT crash the health UI;
  FE falls back to `state: "unknown"`.

**Migration Safety:**
- All migration changes must be forward-only (no destructive DDL).
- Idempotency: re-running migrations on a DB already at v35 is a no-op.
- `_ensure_column` pattern must be used for all column additions (existing pattern in
  `backend/db/postgres_migrations.py`).

**ADR Compliance:**
- ADR-006: No production read path may treat `projects.json` seed-order as registry truth.
- ADR-007: Any new DB write path added in `backend/db/repositories/` must use
  `repositories/base.py:retry_on_locked` and include a direct-count assertion test.
  Independent SQLite connections must issue `PRAGMA busy_timeout = 30000`.

**Dual DDL:**
- Any new column added for W2/W3 must appear in BOTH SQLite and Postgres DDL
  (`CREATE TABLE` + `_ensure_column` ALTERs) in the same changeset; a
  `COLUMN_PARITY_DRIFT_ALLOWLIST` check must accompany the change.

**Test Execution:**
- Tests run as named modules only: `backend/.venv/bin/python -m pytest backend/tests/test_X.py`.
- Do NOT start a dev server in tests (causes hangs with `test_runtime_bootstrap`).

**Performance:**
- `GET /api/projects` p95 latency unchanged (query is small; ORDER BY change is index-safe
  given `is_active` is a single boolean column).

---

## 7. Scope

### In Scope

- W1 Backend: `backend/db/repositories/projects.py` list ordering + `is_seed` field on
  `backend/models.py:Project`.
- W1 Frontend: `contexts/AppSessionContext.tsx` scope-validation logic.
- W2 SPIKE + implementation: watcher fan-out from DB registry (`backend/runtime/container.py`,
  `backend/config.py`, `backend/worker.py`).
- W3: `backend/db/postgres_migrations.py` migration ordering + seeded-old-volume smoke
  (`package.json`, `deploy/runtime/`).
- W4 Triage: F-W3-001, F-W3-002, F-001, F-002, F-003 (fix or defer-with-note);
  F-W6-001 (confirmed deferred, note updated).

### Out of Scope

- Full watcher-per-project container orchestration (multiple `worker-watch` containers
  is an ops/deployment decision, not a code change in this epic).
- Token-undercount remediation (shipped 2026-03-09; F-W6-001 correlation over-count
  explicitly deferred — not a data-integrity fault).
- Remote/streaming session ingest (ADR branch renumbering deferred to merge).
- New UI for the project switcher beyond the active-project default fix.
- `projects.json` writeback or dual-manager reintroduction.

---

## 8. Dependencies & Assumptions

### Internal Dependencies

- **ADR-006** (accepted): DB registry is authoritative — this epic extends that to the
  runtime read/select path and watcher boot path.
- **ADR-007** (accepted): write-failure surfacing standard applies to any new write path.
- `repositories/base.py:retry_on_locked` — already implemented (CCDash Core Remediation).
- `PRAGMA busy_timeout = 30000` pattern — already enforced in existing SQLite connections.
- `backend/db/repositories/projects.py` — DB-authoritative project repository (already exists).

### Assumptions

1. The `projects` table `is_active` column is set correctly by `ccdash project use` (or
   the UI switcher) — the registry itself is clean; only the read path needs fixing.
2. A PG seed volume at v29 can be created deterministically via a Docker Compose fixture
   (new `compose.seeded-pg.yaml` or an init-script that sets `schema_version = 29`).
3. W2 watcher fan-out can be implemented without introducing cross-process state
   coordination (a DB poll on startup + periodic refresh suffices; SSE or explicit rebind
   hook is a stretch goal).
4. `CCDASH_WORKER_WATCH_PROJECT_ID` is currently used in production by some operators;
   setting it must continue to work as a scoping override (no breakage).

### Feature Flags

- `CCDASH_WORKER_WATCH_PROJECT_ID` — demoted to optional scope filter (W2; no new flag
  introduced; backward-compatible empty-string behaviour changes from "watch nothing" to
  "watch all active projects").

---

## 9. Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|:------:|:----------:|-----------|
| W3 migration reordering corrupts a partially-upgraded PG DB | High | Medium | Test against a v29-seeded volume in CI (`docker:hosted:smoke:seeded-pg`); run `_TABLES` only for fresh DBs (version = 0) OR move project_id-dependent indexes to the v30 versioned block; idempotency verified by re-run. |
| W2 watcher fan-out architecture is under-specified (unknown edge cases for N-project dynamic rebind) | High | High | Explicit SPIKE task before implementation; block Phase 4 implementation on approved SPIKE design doc. |
| Frontend localStorage scope validation change breaks project-switcher flow | Medium | Low | Targeted regression test: switch to project B, reload, assert project B is still active (if B has `is_active=true`). Runtime smoke gate on Phase 2. |
| `is_seed` field addition requires dual DDL + model change and may drift between SQLite and PG | Medium | Low | Enforce dual DDL + `COLUMN_PARITY_DRIFT_ALLOWLIST` check; add direct-count assertion test for new field. |
| W2 implementation slips (high arch complexity) | Medium | High | W2 is gated behind SPIKE approval; W1 + W3 + W4 are not blocked and deliver the highest-value fixes (user-visible "no data" symptom resolved in W1). |
| test_runtime_bootstrap segfault (F-002) causes CI flake | Low | Medium | Run only as named module; add env-guard note to test file header; do not include in unscoped test runs. |

---

## 10. Target State (Post-Implementation)

**User Experience:**
- Operator boots the stack → opens the dashboard → sees the active project's sessions
  immediately. No manual project switch needed.
- Operator starts the watcher without setting `CCDASH_WORKER_WATCH_PROJECT_ID`; the
  watcher reads the DB registry and begins watching all active projects.
- `/api/health/detail` shows per-project watcher health; the frontend/health page
  reflects any project that is not being watched.

**Technical Architecture:**
- `GET /api/projects` response is ordered `is_active DESC` so the active project is
  always first. Each item carries `is_active` (existing) and `is_seed` (new).
- `AppSessionContext.refreshProjects()` validates the localStorage scope against
  `is_active`; a stale non-active scope is silently replaced with the DB-active project.
- Watcher boot resolves its target list from `workspace_registry.list_projects()` (or
  `get_active_project()` if the registry returns a single active entry). The env var
  `CCDASH_WORKER_WATCH_PROJECT_ID` scopes but does not gate.
- `_run_migrations_inner` runs versioned column-adding ALTERs (v30+) before any
  `project_id`-dependent index creation; a v29 → v35 upgrade path is fully tested.

**Observable Outcomes:**
- `docker:hosted:smoke:seeded-pg` passes in CI without volume wipe.
- `docker:livewatch:up` (without `CCDASH_WORKER_WATCH_PROJECT_ID`) shows watcher state
  "running" for each registered project.
- All W4 findings either closed or marked `status: deferred` with documented rationale.

---

## 11. Overall Acceptance Criteria

### W1 — Registry-authoritative project resolution

**AC-W1-1 (Backend: list ordering)**
```yaml
target_surfaces:
  - backend/db/repositories/projects.py   # list_projects() query
  - backend/routers/projects.py            # GET /api/projects
verified_by:
  - backend/tests/test_projects_registry.py   # direct-count + ORDER BY assertion
  - curl GET /api/projects → first item is is_active=true project
```
`list_projects()` issues `ORDER BY is_active DESC, created_at ASC`. On a registry with
`default-skillmeat` (is_active=false, created first) and the real project (is_active=true),
the real project is list[0].

**AC-W1-2 (Backend: is_seed field)**
```yaml
target_surfaces:
  - backend/models.py                        # Project model: is_seed: bool = False
  - backend/db/repositories/projects.py     # upsert + read hydration
propagation_contract: is_seed is returned on GET /api/projects; absent/null → false (FE resilience)
resilience: FE treats missing is_seed as false — never throws, never hides the project
verified_by:
  - backend/tests/test_projects_registry.py   # assert default-skillmeat.is_seed == True
  - COLUMN_PARITY_DRIFT_ALLOWLIST check if column added to DB
```
Projects with ids in `{"default-skillmeat", "test-project-1"}` (or those with
`is_seed=1` in DB) return `is_seed: true`. FE renders them with a visual indicator
(badge or label) and excludes them from default-project resolution.

**AC-W1-3 (Frontend: stale-scope validation)**
```yaml
target_surfaces:
  - contexts/AppSessionContext.tsx   # refreshProjects() scope guard
  - services/apiClient.ts            # getProjectScope() / setProjectScope()
resilience: if getActiveProject() 404s (no active project), setActiveProject(null) — no crash
visual_evidence_required: screenshot showing active project's sessions on first load
verified_by:
  - Runtime smoke: start with localStorage scope = "default-skillmeat"; reload; confirm active project shown
```
In `refreshProjects()`: if `scopedProject.is_active === false` AND
`normalizedProjects.some(p => p.is_active)`, clear scope (`setProjectScope(null)`) and
proceed to `getActiveProject()`. Do NOT use a non-active scoped project as the default.

**AC-W1-4 (Integration seam)**
- `integration_owner`: W1-BE owner ensures `is_active` and `is_seed` fields are present
  and non-null in the API contract before W1-FE phase begins.
- A seam task in Phase 2 verifies the API contract with a `curl` probe before any FE
  change is merged.

---

### W2 — Registry-driven watcher fan-out

**AC-W2-SPIKE (Design deliverable)**
A SPIKE design document at `.claude/worknotes/ccdash-runtime-deploy-remediation/w2-watcher-fanout-design.md` is produced and approved before Phase 4 implementation begins. It specifies:
- Fan-out mechanism (boot-time registry poll; optional periodic refresh interval).
- Per-project probe/health rollup contract (JSON shape for `/api/health/detail`).
- Dynamic add/remove behavior when a project is added or `is_active` changes.
- Backward-compatibility contract for `CCDASH_WORKER_WATCH_PROJECT_ID` non-empty case.
- Enumerated test scenarios (happy path, empty registry, env-pin override, dynamic add).

**AC-W2-1 (Watcher fan-out)**
```yaml
target_surfaces:
  - backend/runtime/container.py       # watcher boot / _build_worker_binding_config
  - backend/config.py                  # WORKER_WATCH_PROJECT_ID semantics
verified_by:
  - backend/tests/test_p3_worker_bootstrap.py  # new: empty env var → watches active projects
  - docker:livewatch:up without env var → watcher running for each active project
```
When `CCDASH_WORKER_WATCH_PROJECT_ID` is unset (empty string), the watcher resolves its
target list from `workspace_registry.list_projects()` filtered to `is_active=true` (or all
registered projects if the SPIKE design doc recommends it). When set, the env var is a
scoping filter: only that project is watched.

**AC-W2-2 (Per-project health rollup)**
```yaml
target_surfaces:
  - backend/runtime/container.py   # _probe_watcher_detail / health check
resilience: missing per-project keys in health response treated as {state: "unknown"} by FE
verified_by: GET /api/health/detail → watcher section contains per-project entries
```
`/api/health/detail` watcher section is extended with a `projects` map keyed by
`project_id`, each entry containing `{state, watchPathCount, lastChangeSyncAt}`.

---

### W3 — Postgres in-place upgrade-path fix

**AC-W3-1 (Migration ordering)**
```yaml
target_surfaces:
  - backend/db/postgres_migrations.py   # _run_migrations_inner, _TABLES
verified_by:
  - docker:hosted:smoke:seeded-pg (new smoke step)
  - backend/tests/test_postgres_migrations.py  # new: v29→v35 in-memory PG migration test
```
`project_id`-dependent `CREATE INDEX` statements for the `sessions` table (currently in
`_TABLES` at lines ~223–237) are moved out of `_TABLES` and into the `if current_version < 30`
block in `_run_migrations_inner`, after `_migrate_v30_detail_tables_project_id` runs.
Alternatively, they are removed from `_TABLES` and replaced with `await db.execute(CREATE
INDEX IF NOT EXISTS …)` calls placed after the v30 ALTER block. Fresh DBs (version = 0)
create indexes via the v30 block; existing v35 DBs skip both (IF NOT EXISTS no-ops).

**AC-W3-2 (Idempotency)**
Re-running migrations on a DB already at `SCHEMA_VERSION = 35` is a no-op: no errors,
`migrationStatus: "applied"` unchanged. Verified by running the seeded-pg smoke twice.

**AC-W3-3 (Seeded-old-volume smoke)**
```yaml
target_surfaces:
  - package.json                    # docker:hosted:smoke:seeded-pg script
  - deploy/runtime/                 # seed fixture or init-script for v29 PG DB
verified_by: npm run docker:hosted:smoke:seeded-pg exits 0; /api/health/ready returns migrationStatus="applied"
```
`package.json` gains a `docker:hosted:smoke:seeded-pg` script that: (1) starts a PG
container initialized with a v29 schema seed (DDL snapshot at v29 + `schema_version`
row = 29), (2) starts the api container against it, (3) waits for `/api/health/ready`,
(4) asserts `migrationStatus == "applied"` and no PG errors in logs, (5) tears down.

**AC-W3-4 (Rollback / verification plan)**
- All DDL changes in W3 are additive only (no `DROP`, no `ALTER COLUMN TYPE`).
- If the migration run fails mid-stream (e.g., partial index creation), the advisory lock
  is released and the next boot re-attempts from the stored `schema_version`.
- A pre-migration DB dump (`pg_dump`) is the operator-recommended rollback path (documented
  in `docs/guides/containerized-deployment-quickstart.md` update).

---

### W4 — Finding triage & cleanup

**AC-W4-1** F-W3-001: AC-8.2 prose in the ccdash-core-remediation implementation plan is
corrected to remove the overclaim ("across all sync triggers"); a targeted clarification
note is appended. No code change required.

**AC-W4-2** F-W3-002: The three unawaited-coroutine `RuntimeWarning`s in
`backend/tests/test_sync_all_projects.py` are resolved (coroutines awaited or test
restructured); `pytest -W error::RuntimeWarning backend/tests/test_sync_all_projects.py`
passes with exit 0.

**AC-W4-3** F-001: FK fixture failures in session-repository test suites are triaged.
If fixable in ≤1 hour of effort, fix is applied. Otherwise, finding is updated to
`status: deferred` with a one-line root-cause note and a `target_epic` reference.

**AC-W4-4** F-002: `test_runtime_bootstrap.py` segfault note is added as a header comment
in `backend/tests/test_runtime_bootstrap.py` specifying: "Run as named module only; do not
run with a dev server active." No code fix required.

**AC-W4-5** F-003: `ac-coverage-report.py` nested-list `verified_by` parsing is fixed so
that structured AC blocks (with nested YAML lists) are recognized as covered, not reported
as "uncovered."

**AC-W4-6** F-W6-001: Finding is updated to `status: deferred` with documented rationale
(correlation over-count is not a data-integrity fault; promotion trigger: if totals used
for billing/quota).

---

## 12. Assumptions & Open Questions

### Open Questions

- [ ] **Q1**: Should `is_seed` be a DB column (persistent, survives reimport) or computed
  from a hardcoded id allowlist (`{"default-skillmeat", "test-project-1"}`) in the
  repository layer?
  - **A**: Computed from allowlist for Phase 1 (no DDL change, no dual-DDL risk); promote
    to DB column if operator-configurable seed flagging is needed in a future epic.

- [ ] **Q2**: W2 fan-out — should the watcher watch all *registered* projects or only
  `is_active=true` projects?
  - **A**: SPIKE task in Phase 4 must enumerate this. Operator preference from investigation:
    *"it should just work based on what's configured in app."* Likely answer: watch all
    `is_active=true` projects; env pin remains valid override.

- [ ] **Q3**: W3 smoke — what is the fastest way to produce a v29-seeded PG volume for CI?
  - **A**: An init-script (`deploy/runtime/fixtures/pg-seed-v29.sql`) that creates
    `schema_version` table and inserts `version = 29` is sufficient; the migration runner
    then runs the full v29→v35 upgrade path on first boot.

---

## 13. Appendices & References

### Related Documentation

- **Investigation Report**: `docs/project_plans/reports/investigations/ccdash-runtime-deploy-remediation-investigation.md`
- **ADR-006**: `docs/project_plans/adrs/adr-006-db-authoritative-project-registry.md`
- **ADR-007**: `docs/project_plans/adrs/adr-007-db-write-failure-surfacing-standard.md`
- **Open Findings**: `.claude/findings/ccdash-core-remediation-findings.md`
- **Deployment guide**: `docs/guides/containerized-deployment-quickstart.md`

### Key Files

| File | Relevance |
|------|-----------|
| `backend/db/repositories/projects.py` | `list_projects()` ORDER BY, `is_seed` hydration |
| `backend/models.py` | `Project` model — add `is_seed: bool = False` |
| `backend/routers/projects.py` | `GET /api/projects`, `GET /api/projects/active` |
| `contexts/AppSessionContext.tsx` | `refreshProjects()` scope-validation guard |
| `services/apiClient.ts` | `getProjectScope()`, `setProjectScope()`, `getActiveProject()` |
| `backend/runtime/container.py` | Watcher binding (~lines 1227–1236), health probe |
| `backend/config.py` | `WORKER_WATCH_PROJECT_ID` (~line 1007) |
| `backend/db/postgres_migrations.py` | `_run_migrations_inner` (~line 2329), `_TABLES`, `SCHEMA_VERSION=35` |
| `package.json` | `docker:hosted:smoke:*` scripts |

---

## Implementation

### Phase Overview

| Phase | Workstream | Title | Risk | Owner Specialty | Blocked By |
|:-----:|:----------:|-------|:----:|----------------|------------|
| 1 | W1-BE | Registry API — list ordering + is_seed field | Low | BE | — |
| 2 | W1-FE | App-shell default-project resolution + smoke | Low | FE | Phase 1 (API contract) |
| 3 | W3 | Postgres upgrade-path fix + seeded-volume smoke | High | BE/Deploy | — |
| 4 | W2 | Watcher fan-out SPIKE + implementation | High | BE/Arch | SPIKE approval |
| 5 | W4 | Finding triage & cleanup | Low | BE/Tooling | — |

---

### Phase 1 — W1-BE: Registry API ordering + is_seed field

**Duration:** 1–2 days  
**Owner specialty:** Backend  
**Delivers:** AC-W1-1, AC-W1-2

**Tasks:**
- [ ] T1-001: Update `list_projects()` in `backend/db/repositories/projects.py` —
  change `ORDER BY created_at ASC` → `ORDER BY is_active DESC, created_at ASC`.
- [ ] T1-002: Add `is_seed: bool = False` field to `backend/models.py:Project`.
  Populate in `list_projects()` by checking `project.id in {"default-skillmeat",
  "test-project-1"}` (computed, no DDL change). Document in `COLUMN_PARITY_DRIFT_ALLOWLIST`
  note that `is_seed` is model-computed, not a DB column, so parity check is N/A.
- [ ] T1-003: Add / update `backend/tests/test_projects_registry.py` — assert:
  (a) first item in `list_projects()` is `is_active=true` project, (b) seed projects
  have `is_seed=True`, (c) direct-count assertion for new ordering (ADR-007 pattern).
- [ ] T1-004: Update `backend/db/repositories/projects.py:get_active()` to verify the
  `SELECT … WHERE is_active = 1 LIMIT 1` path returns the correct row; add test.

**Exit criteria:** `pytest backend/tests/test_projects_registry.py` passes; `curl
GET /api/projects` returns active project first with `is_seed` field present.

---

### Phase 2 — W1-FE: App-shell default-project resolution + runtime smoke

**Duration:** 1–2 days  
**Owner specialty:** Frontend  
**Blocked by:** Phase 1 (requires `is_active` and `is_seed` fields in API response)  
**Delivers:** AC-W1-3, AC-W1-4, R-P4 smoke

**Tasks:**
- [ ] T2-001 (Seam): Before any FE change, verify Phase 1 API contract:
  `curl /api/projects` returns `is_active=true` project first with `is_seed` field.
  Document result in Phase 2 progress notes. Block on failure.
- [ ] T2-002: Update `contexts/AppSessionContext.tsx:refreshProjects()` — add scope guard:
  ```
  if (scopedProject && !scopedProject.is_active) {
    const hasActive = normalizedProjects.some(p => p.is_active);
    if (hasActive) { client.setProjectScope(null); scopedProject = null; }
  }
  ```
  Then proceed to `getActiveProject()` as before.
- [ ] T2-003: Add `is_seed` visual indicator in the project switcher (badge or label).
  FE treats `is_seed` missing/null as `false` (resilience AC-W1-2).
- [ ] T2-004: Runtime smoke gate — start dev stack, open browser, confirm:
  (a) active project's sessions are visible on first load (no manual switch),
  (b) localStorage cleared of stale scope shows active project correctly.
  Record screenshot or browser test evidence.
- [ ] T2-005: Regression test — switch to project B (non-seed, non-active), reload,
  confirm project B is still selected (scope persists for valid active projects).

**Exit criteria:** Runtime smoke passes (T2-004); regression test passes (T2-005).

---

### Phase 3 — W3: Postgres upgrade-path fix + seeded-volume smoke

**Duration:** 2–3 days  
**Owner specialty:** Backend / Deploy  
**Delivers:** AC-W3-1, AC-W3-2, AC-W3-3, AC-W3-4

**Tasks:**
- [ ] T3-001: Identify all `CREATE INDEX` statements in `_TABLES` (lines ~223–237 in
  `backend/db/postgres_migrations.py`) that reference `sessions.project_id` and would
  fail on a pre-v30 table. List: `idx_sessions_project`, `idx_sessions_project_status_updated`,
  `idx_sessions_project_source_file` (and any composite FKs in child tables).
- [ ] T3-002: Move the identified `CREATE INDEX IF NOT EXISTS` calls out of `_TABLES`
  (remove from the `_TABLES` string literal) and add them as `await db.execute(…)` calls
  inside the `if current_version < 30:` block in `_run_migrations_inner`, placed AFTER
  `await _migrate_v30_detail_tables_project_id(db)` returns. Use `IF NOT EXISTS` so
  they are no-ops on re-run.
- [ ] T3-003: Verify fresh-DB path still works — create a new PG DB from scratch; confirm
  `_TABLES` creates the base schema and the v30 block creates the missing indexes.
- [ ] T3-004: Create PG seed fixture `deploy/runtime/fixtures/pg-seed-v29.sql` — a minimal
  DDL snapshot setting `schema_version.version = 29` (and the pre-v30 `sessions` table
  without `project_id`). Document that this is a test fixture, not production DDL.
- [ ] T3-005: Add `docker:hosted:smoke:seeded-pg` script to `package.json`. Script:
  starts PG with init-script = `pg-seed-v29.sql`, starts api, waits 30s, calls
  `/api/health/ready`, asserts `migrationStatus == "applied"`, checks pg logs for
  `UndefinedColumnError` (must be absent), tears down.
- [ ] T3-006: Add `backend/tests/test_postgres_migrations_upgrade.py` — unit test that
  simulates a v29 schema state (mock `current_version = 29`), runs `_run_migrations_inner`,
  and asserts no exception and final version = 35.
- [ ] T3-007: Update `docs/guides/containerized-deployment-quickstart.md` — add
  "Rollback plan" section noting pre-migration `pg_dump` as the recommended backup.

**Exit criteria:** `npm run docker:hosted:smoke:seeded-pg` exits 0; re-run exits 0
(idempotency); `test_postgres_migrations_upgrade.py` passes.

---

### Phase 4 — W2: Registry-driven watcher fan-out (SPIKE + implementation)

**Duration:** 3–5 days (SPIKE: 1 day; implementation: 2–4 days)  
**Owner specialty:** Backend / Architecture  
**Delivers:** AC-W2-SPIKE, AC-W2-1, AC-W2-2

> **High-risk workstream.** Implementation is blocked on SPIKE approval. W1 and W3 are
> not blocked by W2 and should be shipped first.

**Tasks:**
- [ ] T4-001 (SPIKE): Author `.claude/worknotes/ccdash-runtime-deploy-remediation/w2-watcher-fanout-design.md`.
  Specify fan-out mechanism, per-project probe contract, dynamic add/remove behavior,
  env-pin backward-compatibility, and enumerated test scenarios. Requires operator
  approval before T4-002 begins.
- [ ] T4-002: Update `backend/runtime/container.py` (~lines 1227–1236) — when
  `WORKER_WATCH_PROJECT_ID` is empty, resolve watch targets from
  `workspace_registry.list_projects()` filtered to `is_active=true`. Build one
  `WatcherBinding` per target project.
- [ ] T4-003: Update `backend/config.py` — add inline doc to `WORKER_WATCH_PROJECT_ID`
  clarifying it is now an optional scope filter.
- [ ] T4-004: Extend `/api/health/detail` watcher section — add `projects` map per
  AC-W2-2. FE resilience: missing `projects` key treated as `{}` (no crash).
- [ ] T4-005: Update `backend/tests/test_p3_worker_bootstrap.py` — add test:
  empty `WORKER_WATCH_PROJECT_ID` → watcher binding resolves to registry active-project
  list (≥1 project). Update existing test (`test_worker_watch_uses_worker_watch_project_id_when_set`)
  to confirm env-pin override still works.
- [ ] T4-006: Manual smoke — `docker:livewatch:up` without `ccdash.env` watcher file;
  confirm watcher probe at :9466 reports `running` for the active project.

**Exit criteria:** SPIKE approved (T4-001); `test_p3_worker_bootstrap.py` passes;
T4-006 smoke passes; `CCDASH_WORKER_WATCH_PROJECT_ID` set vs. unset both work.

---

### Phase 5 — W4: Finding triage & cleanup

**Duration:** 1 day  
**Owner specialty:** Backend / Tooling  
**Delivers:** AC-W4-1 through AC-W4-6

**Tasks:**
- [ ] T5-001: F-W3-001 — patch AC-8.2 prose in ccdash-core-remediation implementation plan (doc edit only).
- [ ] T5-002: F-W3-002 — fix unawaited-coroutine warnings in `backend/tests/test_sync_all_projects.py`.
  Verify: `pytest -W error::RuntimeWarning backend/tests/test_sync_all_projects.py` exits 0.
- [ ] T5-003: F-001 — triage FK fixture failures. Attempt fix ≤1 hour; if not fixable,
  update finding to `status: deferred` with root-cause note.
- [ ] T5-004: F-002 — add header comment to `backend/tests/test_runtime_bootstrap.py`
  documenting named-module-only execution and no-dev-server requirement.
- [ ] T5-005: F-003 — fix `ac-coverage-report.py` nested-list `verified_by` parsing.
  Verify: running the script against a phase file with structured ACs reports them as covered.
- [ ] T5-006: F-W6-001 — update finding to `status: deferred`; add promotion trigger note.
- [ ] T5-007: Close-out — update `.claude/findings/ccdash-core-remediation-findings.md`
  with final status for all six findings.

**Exit criteria:** All W4 findings have `status: resolved` or `status: deferred` with rationale.
`test_sync_all_projects.py` passes with `-W error::RuntimeWarning`.

---

**Progress Tracking:**

See progress tracking: `.claude/progress/ccdash-runtime-deploy-remediation/`

---

*End of PRD — ccdash-runtime-deploy-remediation-v1*
