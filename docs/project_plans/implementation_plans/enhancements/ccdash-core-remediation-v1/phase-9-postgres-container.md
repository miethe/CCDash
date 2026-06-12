---
schema_version: 2
doc_type: phase_plan
title: "Phase 9 — Postgres Parity + Container/Compose"
status: draft
created: 2026-06-10
updated: 2026-06-10
phase: 9
phase_title: "Postgres Parity + Container/Compose"
prd_ref: /Users/miethe/dev/homelab/development/CCDash/docs/project_plans/PRDs/enhancements/ccdash-core-remediation-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-core-remediation-v1.md
feature_slug: ccdash-core-remediation
integration_owner: devops-architect
entry_criteria:
  - Phase 5 (detection columns) merged: all new columns present in SQLite DDL + COLUMN_PARITY_DRIFT_ALLOWLIST updated.
  - Phase 6 (pricing) merged: any pricing-related schema/column changes landed in SQLite DDL.
  - Phase 7 (sync coalescing) merged: in-proc coalescing guard exists; durable-queue path identified.
  - ADR-007 retry_on_locked pattern available for any new write paths.
  - Postgres 15+ and Docker / Docker Compose available in the validation environment.
exit_criteria:
  - All new columns from Phases 5/6 (and earlier) present and parity-clean in Postgres DDL; parity tests green on both backends.
  - COLUMN_PARITY_DRIFT_ALLOWLIST reflects the true intentional drift set (no stale entries; no undocumented drift).
  - `docker compose up` e2e smoke green for `api + worker + postgres` (compose stack boots, /readyz returns 200, a cross-project session detail call succeeds).
  - Durable-queue coalescing validated: zero duplicate full-sync per project/trigger under `JOB_QUEUE_BACKEND != memory` (postgres).
  - `/readyz` fails loud (non-200) when DB/migrations/queue dependencies are unhealthy; returns 200 only when all are healthy.
  - Mandatory Bash-enabled `senior-code-reviewer` PG seam review signed off (NOT edit-less — per memory: edit-less reviewer missed 3 PG-only bugs).
  - karen end-of-phase pass recorded.
---

# Phase 9 — Postgres Parity + Container/Compose

**Plan ID**: `IMPL-2026-06-10-CCDASH-CORE-REMEDIATION` (Phase 9)
**PRD**: `/Users/miethe/dev/homelab/development/CCDash/docs/project_plans/PRDs/enhancements/ccdash-core-remediation-v1.md`
**Decisions block**: `.claude/worknotes/ccdash-core-remediation/decisions-block.md`
**Architecture / conventions**: see root `CLAUDE.md` (DB backend, dual-DDL parity, ADR-006/007, durable queue, runtime profiles). Do not restate.

## Overview

Phase 9 is the **Postgres / enterprise convergence gate** for every column-adding phase in this program. It does not add product features; it proves CCDash is correct and operable on Postgres and inside containers. Three workstreams:

1. **Postgres column parity** — verify all new columns introduced by Phases 5/6 (and any earlier residual) exist in the Postgres DDL with matching types/nullability, that the `COLUMN_PARITY_DRIFT_ALLOWLIST` accurately describes the intentional drift set, and that parity tests pass on both backends.
2. **Container / compose** — author a `docker compose` stack for `api + worker + postgres`, and an end-to-end smoke that boots the stack, waits for `/readyz`, and exercises a cross-project session-detail call (the program's top deliverable) against Postgres.
3. **Durable queue + coalescing + readyz fail-loud** — validate the Phase 7 coalescing guard under the durable (`JOB_QUEUE_BACKEND != memory`) queue backend so no duplicate full-sync fires per project/trigger, and make `/readyz` fail loud on unhealthy DB/migration/queue dependencies.

Per the decisions block, the real double-scan only exists under the durable/postgres queue backend (no coalescing there until Phase 7 lands), so this phase is the place that backend-specific behavior is exercised end-to-end. The PG seam is historically where edit-less reviewers missed bugs, so the quality gate here is a **Bash-enabled** senior-code-reviewer, not a read-only review.

Dependency context (decisions block § Dependency Map): `5 → 9`, `6 → 9`, `7 → 9`. Phase 9 must run after those three merge. It runs in Wave 4 alongside Phases 3 and 10.

## Entry Criteria

See frontmatter `entry_criteria`. In short: Phases 5/6/7 merged (columns in SQLite DDL + allowlist updated; coalescing guard present), Postgres 15+ and Docker available, ADR-007 retry pattern available.

## Exit Criteria

See frontmatter `exit_criteria`. Hard gates: parity tests green both backends; compose e2e smoke green; durable coalescing = zero duplicates; `/readyz` fail-loud verified; Bash-enabled PG seam review signed off; karen pass.

## Risk Notes (phase-local)

- **Postgres column drift** (decisions block Risk Hotspots; PRD §9): Phases 5/6/11 add columns. This phase's job is to catch any drift that slipped through and to assert the allowlist is the *only* intentional drift. Mitigation: parity test compares introspected PG schema vs SQLite schema and fails on any diff not in `COLUMN_PARITY_DRIFT_ALLOWLIST`.
- **Edit-less reviewer misses PG-only bugs** (PRD §9, memory): the seam review MUST run with Bash so the reviewer can actually spin up Postgres and run the parity + compose smoke, not just read diffs.
- **Shared-file edits**: Phase 9 touches `config.py` (queue/readyz config) and DDL/parity modules. Per decisions block, sync/runtime edits are single-threaded across phases — Phase 9 runs after 5/7/8, so no concurrent contention on `sync_engine.py` / `runtime.py`.

## Files Affected (from decisions block key-files; not read during planning)

- `backend/db/repositories/postgres/sessions.py` — Postgres session repo (parity target for new columns).
- `backend/db/repositories/sessions.py` — SQLite session repo (parity baseline).
- `backend/db/migrations.py` — migration runner / dual-DDL definitions.
- `backend/db/connection.py` — async connection (SQLite/Postgres selection, `PRAGMA busy_timeout`).
- `backend/config.py` — `CCDASH_DB_BACKEND`, `CCDASH_DATABASE_URL`, `JOB_QUEUE_BACKEND`, readyz/queue config.
- `backend/db/sync_engine.py` — sync dispatch + coalescing guard (durable-backend behavior).
- `backend/adapters/jobs/` — in-process scheduler + durable job adapter (coalescing under durable queue).
- `backend/runtime/` — runtime profiles (`api`, `worker`), FastAPI app bootstrap, container composition; `/readyz` handler wiring.
- `backend/worker.py` — worker runtime entrypoint (container worker process).
- Parity allowlist module containing `COLUMN_PARITY_DRIFT_ALLOWLIST` (co-located with parity check; confirm exact path during implementation — do not assume).
- `docker-compose.yml` (new) + `Dockerfile`(s) for api/worker (new or extended).
- `backend/tests/` — parity tests, durable-coalescing test, readyz tests, compose-smoke harness.

> Exact module paths for the allowlist and `/readyz` handler are to be located by the executor via grep at implementation time; the decisions block guarantees the surrounding directories above.

## Task Table

Models/effort per decisions block § Agent Routing + Model Routing: executors **sonnet/adaptive**; docs **haiku/adaptive**. Primary: `data-layer-expert` + `devops-architect`. Mandatory gate: **`senior-code-reviewer` WITH Bash** (PG seam) + `karen`.

| Task ID | Name | Description | Acceptance Criteria | Estimate | Assigned Subagent(s) | Model | Effort |
|---|---|---|---|---|---|---|---|
| T9-001 | Inventory new columns + audit allowlist | Enumerate every column added by Phases 5/6 (and earlier residual). Cross-check each appears in both SQLite and Postgres DDL. Audit `COLUMN_PARITY_DRIFT_ALLOWLIST` for stale/undocumented entries. Produce inventory as test fixtures, not a doc. | AC-1 | 1 pt | data-layer-expert | sonnet | adaptive |
| T9-002 | Add/repair Postgres DDL for any missing columns | For any column present in SQLite DDL but absent/mistyped in `postgres/sessions.py` / migrations, add matching Postgres DDL (type + nullability + default) in the same change as the allowlist update. Use ADR-007 `retry_on_locked` if any new write path. | AC-1, AC-7 | 2 pts | data-layer-expert | sonnet | adaptive |
| T9-003 | Dual-backend column parity test | Introspect live schema on both backends; assert SQLite↔Postgres column set/types match except entries in `COLUMN_PARITY_DRIFT_ALLOWLIST`; fail on any undocumented drift. Include a direct-count assertion per ADR-007 for any touched write path. | AC-1 | 1.5 pts | data-layer-expert | sonnet | adaptive |
| T9-004 | Dockerfile(s) for api + worker | Author/extend Dockerfile(s) producing `api` (uvicorn, port 8000) and `worker` (`backend/worker.py`, no HTTP) images from the `api`/`worker` runtime profiles. Non-root, pinned base, healthcheck hook for api. | AC-2 | 1.5 pts | devops-architect | sonnet | adaptive |
| T9-005 | docker-compose stack (api + worker + postgres) | Compose `api`, `worker`, `postgres` services with `CCDASH_DB_BACKEND=postgres`, `CCDASH_DATABASE_URL`, `JOB_QUEUE_BACKEND` durable, shared volume for session-log mount, depends_on + healthchecks. Document env in compose comments. | AC-2 | 1.5 pts | devops-architect | sonnet | adaptive |
| T9-006 | Compose e2e smoke harness | Script that runs `docker compose up`, waits for api `/readyz` 200, then issues a cross-project `/api/v1` session-detail call against Postgres and asserts a non-empty detail envelope; tears stack down; non-zero exit on any failure. | AC-3 | 1.5 pts | devops-architect | sonnet | adaptive |
| T9-007 | Durable-queue coalescing validation | Under `JOB_QUEUE_BACKEND != memory` (postgres), drive concurrent sync triggers for the same project and assert the Phase 7 coalescing guard yields exactly one full-sync per project/trigger (log assertion + dispatch count). Cover ≥2 projects to prove project_id keying. | AC-4 | 1.5 pts | data-layer-expert | sonnet | adaptive |
| T9-008 | `/readyz` fail-loud implementation + tests | Ensure `/readyz` checks DB connectivity, migration head applied, and queue backend reachable; returns non-200 with a structured reason when any is unhealthy; 200 only when all healthy. Tests cover each unhealthy path (DB down, migration behind, queue unreachable). | AC-5 | 1.5 pts | devops-architect | sonnet | adaptive |
| T9-009 | Mandatory Bash-enabled PG seam review | `senior-code-reviewer` runs WITH Bash: spins up Postgres + compose, executes T9-003/T9-006/T9-007/T9-008 tests, inspects PG-only code paths (`postgres/sessions.py`, durable adapter). Sign-off blocks phase exit. Edit-less mode is NOT acceptable. | AC-6 | 1 pt | senior-code-reviewer (Bash) | sonnet | adaptive |
| T9-010 | Phase validation + karen pass | `task-completion-validator` confirms all ACs evidenced; `karen` end-of-phase reality check on parity + compose claims. Block `status: completed` on any failing parity/smoke/coalescing/readyz test. | AC-1..AC-7 | 0.5 pts | task-completion-validator; karen | sonnet | adaptive |
| T9-011 | Phase docs + operator notes | Capture compose run instructions, env matrix, and parity/coalescing/readyz validation commands in the feature guide / worknotes (not a standalone report). Update CLAUDE.md conventions deferred to Phase 12. | AC-2, AC-3 | 0.5 pts | documentation-writer | haiku | adaptive |

**Total estimate**: ~8 pts (matches decisions block anchor for Phase 9).

## Acceptance Criteria

#### AC-1: All new columns parity-clean across SQLite and Postgres
- propagation_contract: >
    Every column added in Phases 5/6 (and any earlier residual) exists in both the SQLite DDL
    (`backend/db/repositories/sessions.py` / `migrations.py`) and Postgres DDL
    (`backend/db/repositories/postgres/sessions.py` / `migrations.py`) with matching type and
    nullability. The dual-backend parity test (T9-003) introspects both live schemas and fails on
    any column-set or type diff not enumerated in `COLUMN_PARITY_DRIFT_ALLOWLIST`. The allowlist is
    audited (T9-001) to contain only intentional, documented drift — no stale and no undocumented entries.
- resilience: >
    Backend-only contract. If a column is present in one backend but missing in the other and not
    in the allowlist, the parity test fails loud (no silent skip). Allowlist additions must be made
    in the same change set as the column addition (PRD §6 Postgres parity).
- visual_evidence_required: false
- verified_by:
    - T9-001
    - T9-003
    - T9-010

#### AC-2: docker compose stack boots api + worker + postgres
- propagation_contract: >
    `docker compose up` starts three services — `api` (uvicorn :8000, `api` runtime profile),
    `worker` (`backend/worker.py`, `worker` runtime profile, no HTTP), and `postgres` 15+ —
    with `CCDASH_DB_BACKEND=postgres`, a valid `CCDASH_DATABASE_URL`, and a durable
    `JOB_QUEUE_BACKEND`. Services declare healthchecks and `depends_on` ordering so the api/worker
    wait for Postgres readiness.
- resilience: >
    If Postgres is not yet ready, api/worker retry connection (bounded) rather than crash-looping
    silently; compose healthchecks surface unhealthy state. Missing required env (`CCDASH_DATABASE_URL`)
    causes a fail-loud startup error, not a degraded default.
- visual_evidence_required: false
- verified_by:
    - T9-004
    - T9-005
    - T9-006

#### AC-3: Compose e2e smoke green (boot → readyz → cross-project detail)
- propagation_contract: >
    The smoke harness (T9-006) brings the compose stack up, polls api `/readyz` until 200 (bounded
    timeout), then calls a `/api/v1` session-detail endpoint for a session in a NON-active project
    and asserts a non-empty detail envelope returned from Postgres. Harness exits non-zero on any
    step failure and tears the stack down.
- resilience: >
    If `/readyz` never reaches 200 within the timeout, the harness fails loud with the last
    `/readyz` body for diagnosis. A 200 with empty/invalid detail envelope is a failure, not a pass.
- visual_evidence_required: false
- verified_by:
    - T9-006
    - T9-010

#### AC-4: Durable-queue coalescing emits zero duplicate full-sync per project/trigger
- propagation_contract: >
    Under `JOB_QUEUE_BACKEND != memory` (postgres durable queue), concurrent sync triggers for the
    same `project_id` are coalesced by the Phase 7 guard into exactly one full-sync per project per
    trigger. The test (T9-007) drives concurrent triggers across ≥2 projects and asserts dispatch
    count == 1 per project via dispatch counter + log assertion.
- resilience: >
    The guard is keyed by `project_id` so coalescing for project A never suppresses a legitimate
    sync for project B. If the durable backend is unavailable, the test fails loud (no fallback to
    the in-memory path that would mask the durable behavior).
- visual_evidence_required: false
- verified_by:
    - T9-007
    - T9-010

#### AC-5: `/readyz` fails loud on unhealthy dependencies
- propagation_contract: >
    `/readyz` evaluates DB connectivity, migration-head applied, and queue-backend reachability.
    It returns 200 only when all three are healthy; otherwise it returns a non-200 status with a
    structured reason naming the failing dependency. Tests (T9-008) cover DB-down, migration-behind,
    and queue-unreachable paths independently.
- resilience: >
    A partial-health state (e.g. DB up, migrations behind) MUST return non-200, not a soft 200 —
    silence/false-green is a contract violation per the program's resilience-by-default rule.
- visual_evidence_required: false
- verified_by:
    - T9-008
    - T9-010

#### AC-6: Bash-enabled PG seam review signed off
- propagation_contract: >
    `senior-code-reviewer` runs WITH Bash (T9-009): spins up Postgres + the compose stack, executes
    the parity (T9-003), compose-smoke (T9-006), durable-coalescing (T9-007), and readyz (T9-008)
    tests, and inspects PG-only code paths in `backend/db/repositories/postgres/sessions.py` and the
    durable job adapter. Sign-off is a hard exit gate.
- resilience: >
    Edit-less / read-only review is explicitly NOT acceptable for this phase (PRD §9; memory:
    edit-less reviewer previously missed 3 PG-only bugs). If the reviewer cannot run Postgres, the
    gate is blocked, not waived.
- visual_evidence_required: false
- verified_by:
    - T9-009
    - T9-010

#### AC-7: New PG write paths use retry_on_locked + direct-count assertion (ADR-007)
- propagation_contract: >
    Any new or modified write path introduced while repairing Postgres DDL (T9-002) uses
    `backend/db/repositories/base.py:retry_on_locked` and ships a direct-count assertion test, per
    ADR-007. Independent SQLite connections (if any added) issue `PRAGMA busy_timeout = 30000`.
- resilience: >
    Write-failure surfacing follows ADR-007 — failures are surfaced, not swallowed. Backend-only;
    no FE surface.
- visual_evidence_required: false
- verified_by:
    - T9-002
    - T9-003

## Quality Gates

- **task-completion-validator** (T9-010): confirms every AC has evidence; blocks `status: completed` on any failing parity / compose-smoke / coalescing / readyz test.
- **senior-code-reviewer WITH Bash** (T9-009, mandatory PG seam gate): per decisions block § Agent Routing and PRD §9 — edit-less mode disallowed; reviewer must execute the PG/compose tests.
- **karen** (T9-010): end-of-phase reality check on parity and container-readiness claims.
- No UI surfaces in this phase → no runtime browser smoke required (CLAUDE.md runtime-smoke gate applies only to UI-touching phases 3/5/6/11).

## Notes on Sequencing & Ownership

- `integration_owner: devops-architect` (R-P3): this phase has ≥2 owner specialties (`data-layer-expert` for parity/DDL + `devops-architect` for container/compose/readyz) with intersecting `files_affected` (`config.py`, `runtime/`). The seam tasks are T9-005/T9-006 (compose wiring the runtime profiles) and T9-008 (readyz spanning DB + queue + runtime).
- Runs in **Wave 4** (decisions block) alongside Phases 3 and 10; depends on Phases 5/6/7 merged.
- Do not begin until Phase 0 is green and the column-adding phases (5/6) have landed their SQLite DDL + allowlist updates — otherwise parity tests have nothing authoritative to compare against.
