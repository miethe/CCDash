---
schema_version: 2
doc_type: implementation_plan
title: "CCDash Runtime & Deploy Remediation v1 — Implementation Plan"
status: completed
created: 2026-06-12
updated: 2026-06-14
feature_slug: ccdash-runtime-deploy-remediation
feature_version: "v1"
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-runtime-deploy-remediation-v1.md
spike_ref: docs/project_plans/reports/investigations/ccdash-runtime-deploy-remediation-investigation.md
plan_ref: null
scope: "Fix registry-authority leaks in project selection (W1), Postgres migration ordering (W3),
  watcher fan-out (W2), and accumulated tooling/test debt (W4)."
effort_estimate: "~31 pts (Tier 3)"
architecture_summary: "DB-authoritative project ordering + is_seed field in API + FE scope guard (P0);
  Postgres _run_migrations_inner reordering + seeded-volume smoke (P1); watcher fan-out SPIKE
  then registry-driven impl with per-project health rollup (P2→P3); finding triage (P4); docs close-out (P5)."
related_documents:
  - docs/project_plans/PRDs/enhancements/ccdash-runtime-deploy-remediation-v1.md
  - docs/project_plans/adrs/adr-006-db-authoritative-project-registry.md
  - docs/project_plans/adrs/adr-007-db-write-failure-surfacing-standard.md
  - .claude/findings/ccdash-core-remediation-findings.md
  - docs/guides/containerized-deployment-quickstart.md
references:
  user_docs: [docs/guides/containerized-deployment-quickstart.md]
  context: [.claude/worknotes/ccdash-runtime-deploy-remediation/]
  specs: []
  related_prds: []
adr_refs:
  - docs/project_plans/adrs/adr-006-db-authoritative-project-registry.md
  - docs/project_plans/adrs/adr-007-db-write-failure-surfacing-standard.md
priority: high
risk_level: high
changelog_required: true
changelog_ref: CHANGELOG.md
deferred_items_spec_refs:
  - docs/project_plans/design-specs/f-w6-001-correlation-overcounting.md
  - docs/project_plans/design-specs/w2-dynamic-watcher-rebind.md
findings_doc_ref: .claude/findings/ccdash-core-remediation-findings.md
plan_structure: unified
progress_init: auto
owner: null
contributors: []
category: deploy-remediation
tags: [deploy, registry, postgres, watcher, remediation, adr-006, adr-007]
milestone: null
commit_refs: []
pr_refs: []
files_affected:
  - backend/db/repositories/projects.py
  - backend/models.py
  - backend/routers/projects.py
  - backend/db/postgres_migrations.py
  - backend/runtime/container.py
  - backend/config.py
  - backend/worker.py
  - contexts/AppSessionContext.tsx
  - package.json
  - deploy/runtime/fixtures/pg-seed-v29.sql
  - CHANGELOG.md
  - CLAUDE.md
  - docs/guides/containerized-deployment-quickstart.md
wave_plan:
  serialization_barriers: []
  phases:
    - id: P0
      depends_on: []
      isolation: shared
      parallelizable: true
      files_affected:
        - backend/db/repositories/projects.py
        - backend/models.py
        - backend/routers/projects.py
        - contexts/AppSessionContext.tsx
    - id: P1
      depends_on: []
      isolation: shared
      parallelizable: true
      files_affected:
        - backend/db/postgres_migrations.py
        - deploy/runtime/fixtures/pg-seed-v29.sql
        - package.json
    - id: P2
      depends_on: []
      isolation: shared
      parallelizable: true
      files_affected:
        - .claude/worknotes/ccdash-runtime-deploy-remediation/w2-watcher-fanout-design.md
    - id: P3
      depends_on: [P2]
      isolation: shared
      parallelizable: false
      files_affected:
        - backend/runtime/container.py
        - backend/config.py
        - backend/worker.py
    - id: P4
      depends_on: []
      isolation: shared
      parallelizable: true
      files_affected:
        - backend/tests/test_sync_all_projects.py
        - backend/tests/test_runtime_bootstrap.py
        - .claude/skills/artifact-tracking/scripts/ac-coverage-report.py
    - id: P5
      depends_on: [P0, P1, P3, P4]
      isolation: shared
      files_affected:
        - CHANGELOG.md
        - CLAUDE.md
        - docs/guides/containerized-deployment-quickstart.md
  waves:
    - [P0, P1, P2]
    - [P3, P4]
    - [P5]
---

# Implementation Plan: CCDash Runtime & Deploy Remediation v1

**Plan ID**: `IMPL-2026-06-12-CCDASH-RUNTIME-DEPLOY-REMEDIATION`
**Date**: 2026-06-12 | **Complexity**: Large (Tier 3) | **Estimated Effort**: ~31 pts
**PRD**: `docs/project_plans/PRDs/enhancements/ccdash-runtime-deploy-remediation-v1.md`
**Spike**: `docs/project_plans/reports/investigations/ccdash-runtime-deploy-remediation-investigation.md`

---

## Executive Summary

Three independent registry-authority leaks cause the operator-visible "no data" symptom:
`/api/projects` returns seed projects first (ignoring `is_active`); the FE app-shell's stored
scope short-circuits the `getActiveProject()` call even when the scoped project is inactive;
and the watcher is env-pinned to a single hand-configured project id rather than the DB registry.
A fourth independent defect (`_TABLES` `project_id`-dependent `CREATE INDEX` executing before the
v30 column-adding ALTERs) breaks all Postgres in-place upgrades on pre-v35 DBs.

This plan delivers four workstreams across six phases:
**P0** (W1 — registry-authoritative project resolution, highest user value, Wave 1);
**P1** (W3 — migration ordering fix + seeded-volume smoke, Wave 1);
**P2** (W2 SPIKE — watcher fan-out design doc, Wave 1);
**P3** (W2 impl — registry-driven watcher + per-project health rollup, Wave 2, SPIKE-gated);
**P4** (W4 — finding triage, Wave 2 alongside P3);
**P5** (docs + deferred specs + CHANGELOG, Wave 3).

**Success criteria**: First-load UI lands on `is_active=true` project; `docker:hosted:smoke:seeded-pg`
exits 0; `docker:livewatch:up` (no env override) shows watcher running per active project;
all W4 findings resolved or `deferred`-with-note.

---

## Implementation Strategy

### Architecture Sequence

1. **Repository layer** — `list_projects()` ORDER BY + `is_seed` computation (P0-BE)
2. **Model layer** — `Project.is_seed: bool = False` Pydantic field (P0-BE)
3. **Migration layer** — `_run_migrations_inner` index-reordering, `IF NOT EXISTS` guards (P1)
4. **App-shell context layer** — `AppSessionContext.refreshProjects()` scope guard (P0-FE)
5. **Worker runtime layer** — registry-driven watcher fan-out + health rollup (P3)
6. **Smoke / integration** — seam probe, seeded-PG smoke, livewatch smoke (P0, P1, P3)
7. **Tooling / docs** — finding triage, deferred specs, CHANGELOG (P4, P5)

### Parallel Work Opportunities

**Wave 1** (all independent, no shared files): P0 (BE + FE with internal seam), P1 (data-layer),
P2 (SPIKE/arch). P0 BE and FE legs run in parallel within the phase, joined by T0-005 (seam gate).
**Wave 2**: P3 (depends on P2 approval) + P4 (independent, fills review wait).
**Wave 3**: P5 (close-out, depends on all).

### Critical Path

**P2 → P3 → P5** (~18 pts). P0 + P1 (~10 pts) are fast-follow / highest-value delivers that
land before P3 completes. W1 resolves the user-visible symptom independently of W2.

### Estimation Sanity Check (H1–H6)

| # | Heuristic | Verdict |
|---|-----------|---------|
| H1 | Bottom-up sum: P0(5)+P1(5)+P2(3)+P3(12)+P4(3)+P5(3)=31 pts; Tier 3 (≥13) ✓ | **Pass** |
| H2 | P3 touches both worker + worker-watch runtime slices → 1.8× factor on runtime slice → ~12 pts confirmed | **Pass** |
| H3 | Watcher fan-out is orchestration polling (registry read + binding map), not a solver — no extra complexity bump | **Pass** |
| H4 | P3 spans watch-engine + probe rollup + reconcile loop + wiring — bundle floor covered at 12 pts | **Pass** |
| H5 | Top-down naive (~20 pts) < bottom-up (31 pts); trust bottom-up | **Pass** |
| H6 | ~15% plumbing (DTO/flag changes, OpenAPI, CHANGELOG) ≈ 4–5 pts of 31 ✓ | **Pass** |

No estimate adjustments; ~31 pts stands.

### Operational / Execution-Environment Note

All code-touching subagents run via ICA `~/ica-claude.sh --bare`
(`--model 'claude-sonnet-4-6[1m]'`, `--add-dir <repo-root>`, `--dangerously-skip-permissions`,
`--max-turns 60–75`). `--bare` drops CLAUDE.md; **embed these invariants in every prompt**:

- **ADR-006**: DB registry authoritative; `projects.json` is import-seed/export-only.
- **ADR-007**: every new write path in `backend/db/repositories/` uses `retry_on_locked`;
  ship direct-count assertion test; independent SQLite connections issue `PRAGMA busy_timeout = 30000`.
- **Dual DDL**: new/changed DB columns in both SQLite + Postgres DDL + `COLUMN_PARITY_DRIFT_ALLOWLIST`
  check in same changeset (N/A for `is_seed` which is model-computed, not a DB column).
- **Named-test-only**: `backend/.venv/bin/python -m pytest backend/tests/test_X.py`; no dev server during tests.
- **Forward-only migrations**: no DROP; idempotent (`IF NOT EXISTS`); both fresh-volume and
  seeded-v29-volume smoke must pass before P1 is complete.

Verify all output on disk (file read / named test run / `git status`). Do not pull agent transcripts.

### Phase Summary

| Phase | Title | Est | Target Subagent(s) | Model | Notes |
|-------|-------|-----|--------------------|-------|-------|
| **P0** | Registry-authoritative project resolution (W1) | 5 pts | `python-backend-engineer` + `ui-engineer` | sonnet | Wave 1; BE + FE parallel; seam T0-005; integration_owner=BE |
| **P1** | Postgres in-place upgrade-path fix (W3) | 5 pts | `data-layer-expert` | sonnet (extended) | Wave 1; karen milestone for migration risk |
| **P2** | Watcher fan-out SPIKE / design (W2) | 3 pts | `backend-architect` | sonnet (extended) | Wave 1; design doc gates P3 |
| **P3** | Registry-driven watcher fan-out impl (W2) | 12 pts | `python-backend-engineer` + `backend-architect` | sonnet (extended) | Wave 2; SPIKE-gated; largest build |
| **P4** | Finding triage & cleanup (W4) | 3 pts | `python-backend-engineer` + `documentation-writer` | sonnet / haiku | Wave 2 alongside P3 |
| **P5** | Docs finalization + deferred specs + CHANGELOG | 3 pts | `documentation-writer` + `changelog-generator` | haiku / sonnet | Wave 3; karen end-of-feature gate |
| **Total** | — | **~31 pts** | — | — | Tier 3 confirmed |

---

## Deferred Items & In-Flight Findings Policy

### Deferred Items Triage Table

| Item ID | Category | Reason Deferred | Trigger for Promotion | Target Spec Path |
|---------|-----------|-----------------|-----------------------|-----------------|
| D-001 | scope-cut | F-W6-001: correlation over-count is a counting artifact, not a data-integrity fault; no billing/quota risk confirmed by investigation | If correlation totals are used for billing or quota enforcement | `docs/project_plans/design-specs/f-w6-001-correlation-overcounting.md` |
| D-002 | spike-needed | W2 dynamic registry rebind at runtime beyond boot-time poll + periodic refresh: full hot-reload requires watcher process signaling not designed in this epic; SPIKE may scope to boot-time-only | If registry churn >1 change/hour in production OR operator requests hot-reload without restart | `docs/project_plans/design-specs/w2-dynamic-watcher-rebind.md` |
| D-003 | scope-cut | Multi-`worker-watch` container orchestration (N containers) is an ops/deployment decision, not a code change | When multi-watcher Helm/Compose template is requested | N/A — ops runbook only |

**DOC-006 rule**: D-001 and D-002 each require a design-spec authoring task in P5 (T5-005, T5-006).
D-003 is ops-only; N/A with rationale.

### In-Flight Findings

`findings_doc_ref` is pre-populated: `.claude/findings/ccdash-core-remediation-findings.md`.
On a new in-flight discovery: add entry to that file; if load-bearing (affects scope/ACs), add a
DOC-006 row in P5 and append the spec path to `deferred_items_spec_refs`.

**Quality gate**: P5 cannot be sealed until D-001 + D-002 design specs exist at the paths above
AND the findings doc is advanced to `status: accepted`.

---

## Phase Breakdown

---

### Phase P0 — Registry-authoritative project resolution (W1)

**Duration**: 1–2 days | **Effort**: 5 pts | **Workstream**: W1 (BE + FE)
**Subagents**: `python-backend-engineer` (T0-001–T0-005), `ui-engineer` (T0-006–T0-009)
**Secondary**: `code-reviewer` | **integration_owner**: W1-BE (T0-005 seam gate)
**Parallelization**: BE leg (T0-001–T0-005) and FE leg (T0-006–T0-009) run concurrently;
T0-005 (seam) must pass before any FE change merges.

**Entry criteria**: Registry `is_active` column set correctly by `ccdash project use` (registry is
clean; only the read/selection path needs fixing).

**Exit criteria**: `pytest backend/tests/test_projects_registry.py` green; runtime smoke (T0-008)
passes; regression test (T0-009) passes; first-load browser lands on `is_active=true` project.

| Task ID | Task Name | Description | Acceptance Criteria | Est | Subagent | Model | Effort | Deps |
|---------|-----------|-------------|---------------------|-----|----------|-------|--------|------|
| T0-001 | `list_projects()` ORDER BY | Change `ORDER BY created_at ASC` → `ORDER BY is_active DESC, created_at ASC` in `backend/db/repositories/projects.py` | Active project is list[0]; ADR-006 compliant; p95 latency unchanged (boolean sort, index-safe) | 1 pt | python-backend-engineer | sonnet | adaptive | — |
| T0-002 | `is_seed` model field | Add `is_seed: bool = False` to `backend/models.py:Project`; populate in `list_projects()` via allowlist check `project.id in {"default-skillmeat","test-project-1"}` (computed, no DDL change); add `COLUMN_PARITY_DRIFT_ALLOWLIST` note: model-computed, parity check N/A | `default-skillmeat.is_seed == True`; FE treats missing/null `is_seed` as `false` (R-P2) | 1 pt | python-backend-engineer | sonnet | adaptive | T0-001 |
| T0-003 | Registry tests | Add/update `backend/tests/test_projects_registry.py`: (a) first item is `is_active=true`; (b) seed projects `is_seed=True`; (c) direct-count assertion (ADR-007 pattern) | All 3 assertions pass; named-module run only | 1 pt | python-backend-engineer | sonnet | adaptive | T0-002 |
| T0-004 | `get_active()` path | Verify `SELECT … WHERE is_active=1 LIMIT 1` returns correct row after ORDER BY change; add regression test | Active project returned correctly; no side effects from T0-001 | 0.5 pt | python-backend-engineer | sonnet | adaptive | T0-002 |
| T0-005 | **Seam — API contract gate** | `curl /api/projects`: confirm active project is list[0] with `is_active=true` and `is_seed` field present; document result in P0 progress notes. FE merge **blocked** on this check passing | `integration_owner` = BE; contract verified before FE task T0-006 lands; block on failure | 0.5 pt | python-backend-engineer | sonnet | adaptive | T0-004 |
| T0-006 | App-shell scope guard | In `contexts/AppSessionContext.tsx:refreshProjects()`: if `scopedProject.is_active === false` AND `normalizedProjects.some(p => p.is_active)`, call `setProjectScope(null)` and proceed to `getActiveProject()`. Resilience: if `getActiveProject()` returns 404 → `setActiveProject(null)`, no crash | Stale non-active scope cleared; 404 resilience; `target_surfaces` noted below (R-P2) | 1 pt | ui-engineer | sonnet | adaptive | T0-005 |
| T0-007 | `is_seed` visual indicator | Add `is_seed` badge/label in project switcher component; treat missing/null as `false` — no throw, no hidden project | Badge shown for seed projects; missing field falls back gracefully | 0.5 pt | ui-engineer | sonnet | adaptive | T0-006 |
| T0-008 | **Runtime smoke gate (R-P4)** | Start dev stack; open browser: (a) active project sessions visible on first load with no manual switch; (b) clear localStorage → active project still loads; record screenshot evidence | `visual_evidence_required: true`; `target_surfaces: [contexts/AppSessionContext.tsx, project-switcher UI]`; unit pass is NOT a substitute | 0.5 pt | ui-engineer | sonnet | adaptive | T0-007 |
| T0-009 | Regression — scope persistence | Switch to non-seed `is_active=true` project B, reload, confirm project B is still selected | `is_active=true` explicit selection persists across reload; default-only logic does not stomp explicit selection | 0.5 pt | ui-engineer | sonnet | adaptive | T0-008 |

**Structured ACs:**

> **T0-002 — `is_seed` resilience (R-P2)**
> ```yaml
> propagation_contract: is_seed on GET /api/projects response; absent/null → false
> resilience: FE treats missing is_seed as false — never throws, never hides the project
> verified_by: [backend/tests/test_projects_registry.py, GET /api/projects contract probe]
> ```

> **T0-006 — Scope guard (R-P2, R-P3, R-P4)**
> ```yaml
> target_surfaces: [contexts/AppSessionContext.tsx, services/apiClient.ts]
> resilience: getActiveProject() 404 → setActiveProject(null) no crash; no active project → graceful fallback to first project
> visual_evidence_required: true
> verified_by: [runtime smoke T0-008, regression T0-009]
> ```

**Quality Gates:**
- [ ] `pytest backend/tests/test_projects_registry.py` passes (named module)
- [ ] `curl GET /api/projects` → `[0].is_active==true`, `is_seed` field present
- [ ] Runtime smoke screenshot on file (T0-008); `runtime_smoke: skipped` + reason if unavailable
- [ ] Regression T0-009 passes; scope persistence confirmed

**Key Files**: `backend/db/repositories/projects.py`, `backend/models.py`,
`backend/routers/projects.py`, `contexts/AppSessionContext.tsx`, `services/apiClient.ts`

---

### Phase P1 — Postgres in-place upgrade-path fix (W3)

**Duration**: 2–3 days | **Effort**: 5 pts | **Workstream**: W3
**Subagents**: `data-layer-expert` (primary), `backend-architect` (review)
**Parallelization**: Independent of P0 and P2; runs in Wave 1. karen milestone at exit.
**Risk**: **HIGH** — migration reorder must fix old-DB path without breaking fresh-DB path.

**Entry criteria**: `backend/db/postgres_migrations.py` accessible; current migration tests passing.

**Exit criteria**: `npm run docker:hosted:smoke:seeded-pg` exits 0; re-run exits 0 (idempotency);
`pytest backend/tests/test_postgres_migrations_upgrade.py` passes; karen milestone review done.

| Task ID | Task Name | Description | Acceptance Criteria | Est | Subagent | Model | Effort | Deps |
|---------|-----------|-------------|---------------------|-----|----------|-------|--------|------|
| T1-001 | Audit `_TABLES` indexes | Identify every `CREATE INDEX` stmt in `_TABLES` (lines ~223–237) that references `sessions.project_id` (e.g. `idx_sessions_project`, `idx_sessions_project_status_updated`, `idx_sessions_project_source_file`; any composite FKs in child tables). Document the full list in task notes (answers OQ-4) | Exhaustive list; nothing missed; sets scope for T1-002 | 0.5 pt | data-layer-expert | sonnet | adaptive | — |
| T1-002 | Migration reorder | Move identified `CREATE INDEX IF NOT EXISTS` stmts out of `_TABLES`; add as `await db.execute(…)` calls inside `if current_version < 30:` block in `_run_migrations_inner`, placed **after** `await _migrate_v30_detail_tables_project_id(db)` returns. Use `IF NOT EXISTS` throughout. Fresh DBs (version=0): indexes created via v30 block. Existing v35 DBs: `IF NOT EXISTS` no-ops. No `DROP`; no `ALTER COLUMN TYPE` | Identified indexes absent from `_TABLES`; present in `<30` block post-v30 ALTER; `IF NOT EXISTS` on all; verified by T1-005 smoke + T1-006 test | 1.5 pt | data-layer-expert | sonnet | extended | T1-001 |
| T1-003 | Verify fresh-DB path | Create a fresh PG DB from scratch; confirm `_TABLES` + v30 block jointly produce a complete v35 schema with no `UndefinedColumnError` | Fresh DB reaches `SCHEMA_VERSION=35` cleanly; no errors in logs | 0.5 pt | data-layer-expert | sonnet | adaptive | T1-002 |
| T1-004 | `pg-seed-v29.sql` fixture | Create `deploy/runtime/fixtures/pg-seed-v29.sql`: minimal DDL snapshot with `schema_version.version=29` and pre-v30 `sessions` table (no `project_id` column). Header comment: "TEST FIXTURE ONLY — not production DDL" | File exists; PG container initialised with it shows `schema_version=29`; fixture documented | 1 pt | data-layer-expert | sonnet | adaptive | T1-001 |
| T1-005 | Seeded-PG smoke script | Add `docker:hosted:smoke:seeded-pg` to `package.json`: boot PG with `pg-seed-v29.sql` init-script, start api, wait 30s, call `/api/health/ready`, assert `migrationStatus=="applied"`, grep PG logs for `UndefinedColumnError` (must be absent), tear down. Re-run must exit 0 (idempotency) | Script exits 0; re-run exits 0; `UndefinedColumnError` absent; `migrationStatus=="applied"` | 1 pt | data-layer-expert | sonnet | adaptive | T1-004 |
| T1-006 | Upgrade path unit test | Add `backend/tests/test_postgres_migrations_upgrade.py`: mock `current_version=29`, run `_run_migrations_inner`, assert no exception and final version=35 | `pytest backend/tests/test_postgres_migrations_upgrade.py` passes (named module) | 1 pt | data-layer-expert | sonnet | adaptive | T1-002 |
| T1-007 | Deployment quickstart update | Add "Rollback plan" section to `docs/guides/containerized-deployment-quickstart.md` noting pre-migration `pg_dump` as recommended operator backup before in-place upgrades | Section exists; doc concise; merge after T1-005 passes | 0.5 pt | documentation-writer | haiku | adaptive | T1-005 |

**Structured ACs (T1-002):**

> ```yaml
> target_surfaces: [backend/db/postgres_migrations.py]   # _run_migrations_inner, _TABLES
> verified_by:
>   - npm run docker:hosted:smoke:seeded-pg (fresh-volume + seeded-v29-volume both pass)
>   - backend/tests/test_postgres_migrations_upgrade.py
> resilience: IF NOT EXISTS on all index DDL; advisory lock released on failure; next boot
>   re-attempts from stored schema_version (no data loss)
> ```

**Quality Gates:**
- [ ] `npm run docker:hosted:smoke:seeded-pg` exits 0; re-run exits 0
- [ ] `pytest backend/tests/test_postgres_migrations_upgrade.py` passes (named module)
- [ ] `UndefinedColumnError` absent from PG container logs
- [ ] karen milestone review completed (migration risk gate)

**Key Files**: `backend/db/postgres_migrations.py`, `deploy/runtime/fixtures/pg-seed-v29.sql`,
`package.json`, `docs/guides/containerized-deployment-quickstart.md`

---

### Phase P2 — Watcher fan-out SPIKE / design (W2)

**Duration**: 1 day | **Effort**: 3 pts | **Workstream**: W2 (design only)
**Subagents**: `backend-architect` (primary), `data-layer-expert` (registry read patterns)
**Parallelization**: Independent; Wave 1. Design doc approval gates P3.
**Risk**: **HIGH** — design must answer all 5 OQs; under-specified design causes P3 rework.

**Entry criteria**: Investigation report and PRD W2 scope readable; `backend/runtime/container.py`
lines 1227–1236 and `backend/config.py` line 1007 reviewed by SPIKE author.

**Exit criteria**: `w2-watcher-fanout-design.md` approved; P3 implementation unblocked.

| Task ID | Task Name | Description | Acceptance Criteria | Est | Subagent | Model | Effort | Deps |
|---------|-----------|-------------|---------------------|-----|----------|-------|--------|------|
| T2-001 | SPIKE design doc | Author `.claude/worknotes/ccdash-runtime-deploy-remediation/w2-watcher-fanout-design.md`. Must answer all 5 OQs: (OQ-2) watch all registered vs `is_active=true` — recommend with resource-budget rationale; (OQ-3) backward-compat contract for non-empty `WORKER_WATCH_PROJECT_ID`; (OQ-5) aggregate `/readyz` + per-project `/detailz` breakdown; dynamic add/remove behavior + scope decision (in-P3 or defer to D-002); bounded concurrency ceiling; enumerated test scenarios (happy path, empty registry, env-pin override, dynamic add) | All 5 OQs answered; test scenarios enumerable; `status: draft` on creation; ≥400 words | 2.5 pt | backend-architect | sonnet | extended | — |
| T2-002 | SPIKE approval gate | Operator reviews T2-001; doc advances to `status: approved`; decision on T3-004 (reconcile loop in-scope vs D-002 deferred) recorded in progress notes; P3 unblocked | `w2-watcher-fanout-design.md status == approved`; T3-001 unblocked | 0.5 pt | backend-architect | sonnet | adaptive | T2-001 |

**Quality Gates:**
- [ ] `w2-watcher-fanout-design.md` exists, answers all 5 OQs, approved
- [ ] T3-004 scope decision recorded (in-P3 or defer D-002)

**Key Files**: `.claude/worknotes/ccdash-runtime-deploy-remediation/w2-watcher-fanout-design.md`

---

### Phase P3 — Registry-driven watcher fan-out implementation (W2)

**Duration**: 3–4 days | **Effort**: 12 pts | **Workstream**: W2 (impl)
**Subagents**: `python-backend-engineer` (impl), `backend-architect` (design oversight)
**Secondary**: `code-reviewer`
**Blocked by**: P2 approval (T2-002). Internal split: watch-engine (T3-001, T3-002) and
probe rollup (T3-003) are splittable after T2-002. Reconcile loop (T3-004) follows T3-001.

**Entry criteria**: `w2-watcher-fanout-design.md` approved; P0 BE complete (`workspace_registry` API stable).

**Exit criteria**: `pytest backend/tests/test_p3_worker_bootstrap.py` green; manual livewatch smoke
(T3-007) passes; env-pin override still works; `/api/health/detail` has per-project watcher map.

| Task ID | Task Name | Description | Acceptance Criteria | Est | Subagent | Model | Effort | Deps |
|---------|-----------|-------------|---------------------|-----|----------|-------|--------|------|
| T3-001 | Watcher fan-out — boot-time | Update `_build_worker_binding_config` in `backend/runtime/container.py` (~lines 1227–1236): when `WORKER_WATCH_PROJECT_ID` is empty, call `workspace_registry.list_projects()` filtered to `is_active=true`; build one `WatcherBinding` per project. ADR-006: registry is authoritative. Existing env-pin path (non-empty) unchanged | Empty env var → multiple `WatcherBinding` objects; env-pin → single binding; ADR-006 compliant | 3 pt | python-backend-engineer | sonnet | extended | T2-002 |
| T3-002 | `WORKER_WATCH_PROJECT_ID` semantics | Update inline doc in `backend/config.py`: "Optional scope filter. Empty → watcher derives targets from DB registry (all is_active projects). Non-empty → scopes to that project id." Backward-compat: no existing operator relied on empty=watch-nothing (investigation confirmed env-pinned production use only) | Doc updated; empty-string semantics change documented | 0.5 pt | python-backend-engineer | sonnet | adaptive | T3-001 |
| T3-003 | Per-project health rollup | Extend `/api/health/detail` watcher section with `projects` map: `{project_id: {state, watchPathCount, lastChangeSyncAt}}`. FE resilience (R-P2): missing `projects` key → `{}`, missing per-project fields → `{state:"unknown"}` — no crash | Health endpoint returns `projects` map; FE resilience ACs documented; verified by GET /api/health/detail | 2.5 pt | python-backend-engineer | sonnet | adaptive | T3-001 |
| T3-004 | Reconcile loop (SPIKE-scoped) | If T2-002 approved in-P3: implement periodic registry re-read (interval from SPIKE design, default 60s); detect added/removed/activated projects; add/remove `WatcherBinding` idempotently. If SPIKE defers: mark task `status: deferred → D-002`, record in progress notes | If in-scope: reconcile loop adds new active projects without restart; idempotent. If deferred: D-002 note in findings | 3 pt | python-backend-engineer | sonnet | extended | T3-001 |
| T3-005 | Worker bootstrap tests | Update/create `backend/tests/test_p3_worker_bootstrap.py`: (a) empty `WORKER_WATCH_PROJECT_ID` → bindings = registry active-project list (≥1 project); (b) non-empty → bindings = [that project]; (c) per-project health map present. Named-module only; no dev server | Both cases pass: `pytest backend/tests/test_p3_worker_bootstrap.py` | 2 pt | python-backend-engineer | sonnet | adaptive | T3-003 |
| T3-006 | Compose / env / docs update | Update `deploy/` compose files and `.env.example`: `CCDASH_WORKER_WATCH_PROJECT_ID` marked optional with comment. Update watcher section in `docs/guides/containerized-deployment-quickstart.md` | Compose starts without env var set; docs reflect optional semantics; `.env.example` comment added | 1 pt | documentation-writer | haiku | adaptive | T3-002 |
| T3-007 | Manual livewatch smoke | Run `docker:livewatch:up` without `CCDASH_WORKER_WATCH_PROJECT_ID` in any env overlay; confirm watcher probe at :9466 reports `running` for each active project. Then set env var and confirm single-project scope. Record evidence in P3 progress notes | Both paths (no env + env-pinned) verified; evidence on file | 1 pt | python-backend-engineer | sonnet | adaptive | T3-005 |

**Structured ACs (T3-001, T3-003):**

> **T3-001 — ADR-006 compliance:**
> ```yaml
> target_surfaces: [backend/runtime/container.py, backend/config.py]
> verified_by:
>   - backend/tests/test_p3_worker_bootstrap.py
>   - docker:livewatch:up without env var
> ```

> **T3-003 — Per-project health resilience (R-P2):**
> ```yaml
> target_surfaces: [backend/runtime/container.py]
> resilience: FE treats missing `projects` key as {}; per-project missing fields default to {state:"unknown"}
> verified_by: GET /api/health/detail → watcher section has `projects` map keyed by project_id
> ```

**Quality Gates:**
- [ ] `pytest backend/tests/test_p3_worker_bootstrap.py` passes (named module)
- [ ] `docker:livewatch:up` (no env override) → watcher running per active project
- [ ] Env-pin `CCDASH_WORKER_WATCH_PROJECT_ID=X` → only project X watched
- [ ] `/api/health/detail` watcher section has `projects` map

**Key Files**: `backend/runtime/container.py`, `backend/config.py`, `backend/worker.py`,
`deploy/` compose files, `.env.example`

---

### Phase P4 — Finding triage & cleanup (W4)

**Duration**: 1 day | **Effort**: 3 pts | **Workstream**: W4
**Subagents**: `python-backend-engineer` (code fixes), `documentation-writer` (doc patches)
**Parallelization**: Independent; schedule in Wave 2 alongside P3 to fill review wait.

**Entry criteria**: `.claude/findings/ccdash-core-remediation-findings.md` accessible.

**Exit criteria**: All 6 W4 findings have `status: resolved` or `status: deferred` with rationale;
`pytest -W error::RuntimeWarning backend/tests/test_sync_all_projects.py` passes.

| Task ID | Task Name | Description | Acceptance Criteria | Est | Subagent | Model | Effort | Deps |
|---------|-----------|-------------|---------------------|-----|----------|-------|--------|------|
| T4-001 | F-W3-001 doc patch | Remove overclaim "across all sync triggers" from AC-8.2 prose in ccdash-core-remediation implementation plan; append targeted clarification note. No code change | Overclaim text removed; clarification note present; no regression in coverage report | 0.5 pt | documentation-writer | haiku | adaptive | — |
| T4-002 | F-W3-002 coroutine fix | Fix three unawaited-coroutine `RuntimeWarning`s in `backend/tests/test_sync_all_projects.py` (await coroutines or restructure); `pytest -W error::RuntimeWarning backend/tests/test_sync_all_projects.py` exits 0 | Named-module run exits 0 with `-W error::RuntimeWarning` | 1 pt | python-backend-engineer | sonnet | adaptive | — |
| T4-003 | F-001 FK fixture triage | Investigate FK fixture failures in session-repository test suites (≤1 hour effort cap). Fix if feasible; otherwise update finding to `status: deferred` with root-cause note and `target_epic` reference | Finding dispositioned: `resolved` or `deferred`-with-note and `target_epic` set | 1 pt | python-backend-engineer | sonnet | adaptive | — |
| T4-004 | F-002 test_runtime_bootstrap note | Add header comment to `backend/tests/test_runtime_bootstrap.py`: "Run as named module only (`python -m pytest backend/tests/test_runtime_bootstrap.py`). Do NOT run with a dev server active — causes segfault." | Header comment present; no code change required | 0.5 pt | python-backend-engineer | sonnet | adaptive | — |
| T4-005 | F-003 ac-coverage-report fix | Fix `ac-coverage-report.py` nested-list `verified_by` parsing so structured YAML AC blocks (with nested lists) are classified as covered, not "uncovered" | Script run against a phase file with structured ACs reports them as covered | 1 pt | python-backend-engineer | sonnet | adaptive | — |
| T4-006 | F-W6-001 deferred note | Update finding to `status: deferred`; add promotion trigger: "if correlation totals are used for billing or quota enforcement" | Finding shows `status: deferred` + promotion trigger | 0.5 pt | documentation-writer | haiku | adaptive | — |
| T4-007 | Findings close-out | Update `.claude/findings/ccdash-core-remediation-findings.md` with final status for all 6 findings (F-W3-001, F-W3-002, F-001, F-002, F-003, F-W6-001) | All 6 findings have `status: resolved` or `status: deferred` + rationale | 0.5 pt | documentation-writer | haiku | adaptive | T4-006 |

**Quality Gates:**
- [ ] `pytest -W error::RuntimeWarning backend/tests/test_sync_all_projects.py` passes (named module)
- [ ] All 6 findings in `.claude/findings/ccdash-core-remediation-findings.md` dispositioned
- [ ] `ac-coverage-report.py` correctly classifies structured AC blocks as covered

**Key Files**: `backend/tests/test_sync_all_projects.py`, `backend/tests/test_runtime_bootstrap.py`,
`.claude/skills/artifact-tracking/scripts/ac-coverage-report.py`,
`.claude/findings/ccdash-core-remediation-findings.md`

---

### Phase P5 — Docs finalization, deferred specs, and CHANGELOG

**Duration**: 0.5–1 day | **Effort**: 3 pts | **Workstream**: Close-out
**Subagents**: `documentation-writer` (haiku), `changelog-generator` (haiku), `karen` (opus, final gate)
**Blocked by**: P0, P1, P3, P4 all complete.

**Entry criteria**: All implementation phases (P0–P4) have passed their exit criteria.

**Exit criteria**: `CHANGELOG.md [Unreleased]` entry present; D-001 + D-002 design specs committed;
findings doc `status: accepted`; plan frontmatter `status: completed`; karen APPROVED.

| Task ID | Task Name | Description | Acceptance Criteria | Est | Subagent | Model | Effort | Deps |
|---------|-----------|-------------|---------------------|-----|----------|-------|--------|------|
| T5-001 | CHANGELOG `[Unreleased]` | Add entry under `[Unreleased]` per Keep A Changelog: `### Fixed` for W1 (active-project first-load), W3 (PG migration path); `### Changed` for W2 (watcher env var demoted to optional); `### Maintenance` for W4 | Entry present with correct categorization; set `changelog_ref: CHANGELOG.md` in plan frontmatter | 0.5 pt | changelog-generator | haiku | adaptive | all impl |
| T5-002 | Deployment guide update | Update `docs/guides/containerized-deployment-quickstart.md`: registry-driven watcher section; `CCDASH_WORKER_WATCH_PROJECT_ID` optional semantics; seeded-PG smoke command; rollback plan (addendum to T1-007) | Guide reflects post-implementation state; rollback plan present | 0.5 pt | documentation-writer | haiku | adaptive | all impl |
| T5-003 | CLAUDE.md pointer | Add ≤3-line entry to CLAUDE.md: watcher fan-out is registry-driven (ADR-006); `CCDASH_WORKER_WATCH_PROJECT_ID` is optional scope filter; seeded-PG smoke at `npm run docker:hosted:smoke:seeded-pg` | Pointer ≤3 lines; progressive-disclosure rule honoured | 0.5 pt | documentation-writer | haiku | adaptive | all impl |
| T5-004 | Plan frontmatter close-out | Set `status: completed`, populate `commit_refs`, `updated`, `deferred_items_spec_refs` (D-001 + D-002 paths) | All frontmatter fields complete per lifecycle spec | 0.5 pt | documentation-writer | haiku | adaptive | T5-001 |
| T5-005 | DOC-006: F-W6-001 design spec | Author `docs/project_plans/design-specs/f-w6-001-correlation-overcounting.md` (`maturity: idea`): describe the over-count finding, why deferred, investigation needed if promoted, promotion trigger. Append path to `deferred_items_spec_refs` | Spec at path; `prd_ref` set; appended to `deferred_items_spec_refs` | 0.5 pt | documentation-writer | sonnet | adaptive | T4-006 |
| T5-006 | DOC-006: W2 dynamic rebind spec | Author `docs/project_plans/design-specs/w2-dynamic-watcher-rebind.md` (`maturity: shaping`): boot-time-only limitation, rebind signaling design options, promotion trigger. Append path to `deferred_items_spec_refs` | Spec at path; promotion trigger documented; appended to `deferred_items_spec_refs` | 0.5 pt | documentation-writer | sonnet | adaptive | T3-004 |
| T5-007 | Findings doc finalize | Advance `.claude/findings/ccdash-core-remediation-findings.md` from `draft` → `accepted`; populate `promoted_to` with this plan's path | Findings doc `status: accepted`; `promoted_to` set | 0.5 pt | documentation-writer | haiku | adaptive | T4-007 |
| T5-008 | Feature guide | Author `.claude/worknotes/ccdash-runtime-deploy-remediation/feature-guide.md` (≤200 lines, 5 required sections: What Was Built, Architecture Overview, How to Test, Coverage Summary, Known Limitations). Commit before PR open | Feature guide exists at path; all 5 sections present | 0.5 pt | documentation-writer | haiku | adaptive | T5-007 |

**Quality Gates:**
- [ ] `CHANGELOG.md [Unreleased]` contains entry for this feature
- [ ] `deferred_items_spec_refs` populated with D-001, D-002 spec paths
- [ ] `.claude/findings/ccdash-core-remediation-findings.md` `status: accepted`
- [ ] Plan frontmatter `status: completed`
- [ ] Feature guide committed
- [ ] karen end-of-feature APPROVED

**Key Files**: `CHANGELOG.md`, `CLAUDE.md`, `docs/guides/containerized-deployment-quickstart.md`,
`docs/project_plans/design-specs/f-w6-001-correlation-overcounting.md`,
`docs/project_plans/design-specs/w2-dynamic-watcher-rebind.md`,
`.claude/worknotes/ccdash-runtime-deploy-remediation/feature-guide.md`

---

## Risk Mitigation

### HIGH Risks

| Risk | Severity | Mitigation | Owning Phase |
|------|----------|------------|-------------|
| **P1 migration reorder breaks fresh DBs while fixing old ones** | HIGH | Require BOTH fresh-volume (T1-003) AND seeded-v29-volume smoke (T1-005) green before P1 closes; `IF NOT EXISTS` on all index DDL (no-op on re-run); forward-only (no `DROP`, no `ALTER COLUMN TYPE`); karen milestone gates P1 completion | P1 |
| **P3 watcher fan-out resource / backpressure with N projects** | HIGH | Per-project isolation enforced in T3-001 (one project's watch failure cannot kill siblings); bounded concurrency ceiling specified in SPIKE design (T2-001); probe rollup (T3-003) surfaces per-project state so operators see degraded early; SPIKE-first gates implementation | P2 → P3 |

### MED Risks

| Risk | Mitigation |
|------|-----------|
| Dynamic registry change handling (P3) | Reconcile loop (T3-004) re-reads registry on interval; idempotent add/remove; SPIKE decides in-scope vs defer; D-002 tracks if deferred |
| W1 scope-validation regression (P0) | Regression test T0-009: explicit `is_active=true` selection persists across reload; default logic does not stomp explicit selection |
| Seed/test project pollution (P0) | `is_seed` computed from hardcoded allowlist (no DDL risk); FE guard (T0-006) excludes seeds from default-candidate resolution |
| `is_seed` model vs DB drift | Computed field (no DB column added); documented in `COLUMN_PARITY_DRIFT_ALLOWLIST` note as "model-computed, parity check N/A" |

### ADR Enforcement Checkpoints

| ADR | Enforced In |
|-----|------------|
| ADR-006 | T0-001 (list ordering), T0-005 (seam gate), T3-001 (watcher registry read) — each task AC cites ADR-006 |
| ADR-007 | Any new write path added in P3; if T3-001 introduces a new repository write (e.g., watcher state persistence) it must use `retry_on_locked` + direct-count assertion test |

---

## Success Metrics

| Metric | Baseline | Target | Measured By |
|--------|----------|--------|-------------|
| First-load project correctness | Lands on seed/empty project | Lands on `is_active=true` project with sessions | Runtime smoke T0-008; screenshot on file |
| Watcher config required fields | `CCDASH_WORKER_WATCH_PROJECT_ID` required | env var optional; omit → all active projects watched | `docker:livewatch:up` without env var (T3-007) |
| PG in-place upgrade success rate | 0% (volume wipe required for pre-v35 DBs) | 100% for DB ≥ v29 | `npm run docker:hosted:smoke:seeded-pg` exits 0 (T1-005) |
| Open finding count (W4 scope) | 5 open | 0 open — all resolved or `deferred`-with-note | `.claude/findings/ccdash-core-remediation-findings.md` (T4-007) |

---

## Wrap-Up

After P5 quality gates pass and T5-008 (feature guide) is committed:

```bash
gh pr create \
  --title "fix(deploy): registry-authoritative project selection, PG upgrade path, watcher fan-out" \
  --body "$(cat .claude/worknotes/ccdash-runtime-deploy-remediation/feature-guide.md)"
```

PR summary bullets (from Executive Summary + CHANGELOG entry): active-project first-load fix (W1);
PG in-place upgrade unblocked for any DB ≥ v29 (W3); registry-driven watcher — env var now
optional (W2); accumulated finding triage closed (W4).

---

**Progress Tracking**: `.claude/progress/ccdash-runtime-deploy-remediation/`

---
*Implementation Plan Version: 1.0 — Last Updated: 2026-06-12*
