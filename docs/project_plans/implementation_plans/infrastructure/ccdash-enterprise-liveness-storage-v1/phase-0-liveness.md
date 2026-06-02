---
schema_version: 2
doc_type: phase_plan
title: "Phase 0 — Enterprise Liveness Hotfix"
status: approved
created: 2026-05-30
updated: 2026-05-30
phase: 0
phase_title: "Enterprise Liveness Hotfix"
feature_slug: ccdash-enterprise-edition-v1
prd_ref: docs/project_plans/PRDs/infrastructure/ccdash-enterprise-liveness-storage-v1.md
plan_ref: docs/project_plans/implementation_plans/infrastructure/ccdash-enterprise-liveness-storage-v1.md
integration_owner: devops-architect
entry_criteria:
  - PRD approved
  - Decisions block verify-state pass complete (2026-05-30)
exit_criteria:
  - P0-013 CI e2e smoke is green
  - Worker readyz returns 200 iff watch-paths > 0; zero-path returns 503 configured_no_paths
  - No PermissionError on projects.json write at boot
  - frontend depends_on api service_healthy confirmed working
  - task-completion-validator sign-off
---

# Phase 0 — Enterprise Liveness Hotfix

**Parent plan**: [ccdash-enterprise-liveness-storage-v1.md](../ccdash-enterprise-liveness-storage-v1.md)
**Integration owner**: `devops-architect` (compose↔config↔runtime seam)
**Complexity**: M (8×S + 4×M + 1×L + 1 seam task)
**Estimate**: ~14 pts

## Phase Overview

Fix the three-defect compounding wiring bug that leaves a default enterprise container serving an empty dashboard silently: (a) ingestion disabled by default, (b) host-absolute `projects.json` paths unresolvable in-container, (c) inotify dead on bind mounts + read-only `projects.json` crashing on write. All three currently pass `readyz`. Phase 0 introduces no new subsystems — only default flips, wiring, and a fail-loud readiness contract.

## Batch Dependency Graph

```
batch_0 (parallel) ──► batch_1 (sequence-sensitive) ──► batch_2 (depend on wiring) ──► batch_3 (exit gate)
P0-004                  P0-001 → P0-015                  P0-002                          P0-013
P0-005                  then parallel:                   P0-003
P0-006                    P0-008                         P0-010
P0-007                    P0-011
P0-009
P0-014
P0-SEC-CORS
```

**batch_1 sequencing note**: P0-001 must land before P0-015 (avoid heavy-sync window during the default-on flip). P0-008 and P0-011 can run after P0-001 is complete.

## Task Table

**Column conventions**:
- `Anchors` — re-verified file:line from the decisions block (2026-05-30 verify-state pass)
- `Cplx` — S/M/L/XL
- `Batch` — which parallel batch this task belongs to
- All tasks: `assigned_model: sonnet`, `Effort: adaptive`

| Task ID | Title | Anchors | Change | Acceptance Criteria | Cplx | Assigned To | Depends On | Batch |
|---------|-------|---------|--------|---------------------|------|-------------|------------|-------|
| P0-004 | WATCHFILES_FORCE_POLLING default true for worker-watch | `compose.yaml:175`; `file_watcher.py:16,183` | compose default `:-true`; no code change (awatch honors env) | `WATCHFILES_FORCE_POLLING=true` present in worker-watch service env block in compose.yaml; live updates fire on Docker Desktop bind mounts | S | devops-architect | — | 0 |
| P0-005 | Writable projects.json + atomic _save() | `compose.yaml:44-48`; `project_manager.py:99-100,140-146` | compose `:48` read_only→false (scope to projects.json volume); `_save()` → temp-file + `os.replace()` + try/except | No PermissionError on boot; no torn file on concurrent write; `os.replace()` is atomic; compose volume for projects.json is not read_only | S | devops-architect | — | 0 |
| P0-006 | Read worker env vars in config.py | `config.py` (absent) | Add `CCDASH_WORKER_WATCH_PROJECT_ID`, `CCDASH_WORKER_STARTUP_SYNC_ENABLED`, `CCDASH_WORKER_WATCH_STARTUP_SYNC_ENABLED` readers | All three vars defined in config.py with correct types and defaults; behavior identical to compose-resolved values; k8s/bare-container can set them without compose | S | python-backend-engineer | — | 0 |
| P0-007 | frontend depends_on api (service_healthy) | `compose.yaml:195-217`; `compose.hosted.yml:67-80` (pattern) | Add `depends_on: {api: {condition: service_healthy}}` to frontend service | frontend service in compose.yaml has `depends_on: api: condition: service_healthy`; nginx does not serve /api 502s before api healthcheck passes | S | devops-architect | — | 0 |
| P0-009 | Reconcile CCDASH_PROJECTS_FILE dead var | `project_manager.py:287`; `compose.yaml:45` | Make ProjectManager honor `CCDASH_PROJECTS_FILE` (add to config.py, pass at :287) for mount parity; coordinate with P0-005 | `CCDASH_PROJECTS_FILE` defined in config.py; ProjectManager constructor reads it; compose.yaml `:45` and config.py align on the same var name; no dead var | S | python-backend-engineer | — | 0 |
| P0-014 | Startup fail-loud log (enterprise + ingestion-off + empty DB) | `container.py:237-243,106-108`; `config.py:246` | Loud WARNING at startup when enterprise profile + `filesystem_source_of_truth=False` + zero sessions | WARNING log emitted with exact remediation text when all three conditions hold; log includes the env var to set and the expected value; condition check is at container bootstrap | S | python-backend-engineer | — | 0 |
| P0-SEC-CORS | Gate dev CORS origins behind dev flag | `bootstrap.py:57-67` | localhost origins only in dev/local runtime; enterprise allows only `config.FRONTEND_ORIGIN` | `localhost:3000` not present in CORS allowed_origins when `CCDASH_RUNTIME_PROFILE=enterprise`; enterprise only allows `FRONTEND_ORIGIN`; local/dev profiles retain localhost origins | S | python-backend-engineer | — | 0 |
| P0-001 | Default-on ingestion + startup-sync + fold worker-watch into enterprise | `compose.yaml:27,133,157-193,169`; `config.py:246`; `container.py:237-243` | compose: `CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED:-true` (:27), add `"enterprise"` to worker-watch `profiles` (:161); `config.py:246` default→True; real gate is `CCDASH_STARTUP_SYNC_ENABLED` + profile capabilities.sync, not the phantom `CCDASH_WORKER_STARTUP_SYNC_ENABLED` | `CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED` defaults true in compose; worker-watch profile includes `enterprise`; `config.py:246` default is True; `CCDASH_STARTUP_SYNC_ENABLED`+profile.sync gate confirmed as the real mechanism; phantom var NOT used | M | devops-architect | batch_0 complete | 1 |
| P0-015 | Reconcile STARTUP_SYNC_LIGHT_MODE | `config.py:966`; `adapters/jobs/runtime.py:~730`; `sync_engine.py:4261`; compose worker/worker-watch | Align both getattr fallbacks→False (config.py is single SoT, default False); compose worker and worker-watch set `CCDASH_STARTUP_SYNC_LIGHT_MODE=true` so in-container heavy passes defer to the worker loop; sequence WITH P0-001 to avoid heavy-sync window | Both `runtime.py` (~:730) and `sync_engine.py` (:4261) getattr fallbacks read False (aligned to config.py:966); compose worker and worker-watch blocks carry `CCDASH_STARTUP_SYNC_LIGHT_MODE:-true`; default enterprise boot does not block on heavy startup sync | M | python-backend-engineer | P0-001 | 1 |
| P0-008 | entrypoint.sh worker-watch dispatch | `entrypoint.sh:8,10-25`; `compose.yaml:162,165` | Add `worker-watch)` case launching `python -m backend.worker` with the worker-watch profile; closes fall-through if command override removed | `worker-watch` case present in entrypoint.sh case statement; launches `python -m backend.worker` with correct profile env; no fall-through to default case | S | devops-architect | P0-001 | 1 |
| P0-011 | pg_advisory_lock around run_migrations() | `container.py:106-108`; `postgres_migrations.py:1497-1519` | Wrap `run_migrations()` in `pg_advisory_lock(<stable key>)` (Postgres-only; SQLite early-returns) | Advisory lock acquired before run_migrations() on Postgres; second concurrent caller waits (not races); SQLite path early-returns without lock attempt; lock key is a stable integer constant | M | python-backend-engineer | P0-001 | 1 |
| P0-002 | Auto-derive container path aliases from ResolvedProjectPaths | `project_paths/providers/filesystem.py:11-37`; `source_identity.py:247-308` | Add `source_identity_policy_from_resolved_paths(...)` beside the env builder; wire at policy construction; fall back to env for explicit overrides; `resolve()` stays a clean Path seam | `source_identity_policy_from_resolved_paths()` function exists and produces alias map from `ResolvedProjectPaths`; wired at policy construction time; falls back to explicit env overrides; derived alias map logged at startup; P0-003 readyz catches zero-path result | L | python-backend-engineer | batch_1 complete | 2 |
| P0-003 | Fail-loud readyz when watch-paths==0 | `bootstrap_worker.py:50-61`; `container.py:650-671,875-921`; `file_watcher.py:43-45,105-112,252-266` | In container.py:650-671, when `capabilities.watch` and `watchPathCount==0` → `watcher_check_status="fail"` (new `configured_no_paths` reason) → `ready.ready=False` → 503; distinguish "not configured" (warn) from "configured, zero paths" (fail) | Worker readyz returns 503 when capabilities.watch=True and resolved watch-paths=0; reason field is `configured_no_paths`; "not configured" case returns 200 with warning; intentionally unresolvable projects.json path produces non-200 readyz | M | python-backend-engineer | batch_1 complete | 2 |
| P0-010 | Repair/deprecate compose.hosted.yml | `compose.hosted.yml:1-84` | Header comment: must be used as `-f compose.yaml -f compose.hosted.yml` (lacks profiles/volumes); keep `pgvector:pg17` (vector parity); fix placeholder `CCDASH_SAM_ENDPOINT` telemetry | compose.hosted.yml has header comment explaining required compose -f invocation order; pgvector:pg17 image retained; CCDASH_SAM_ENDPOINT placeholder replaced or documented; file is usable as an override without silent breakage | M | devops-architect | batch_1 complete | 2 |
| P0-013 | CI docker compose up e2e smoke gate | `compose.yaml` enterprise topology; `bootstrap_worker.py:50-61`; `file_watcher.py:252-266`; NEW `.github/workflows/*` | New workflow: `docker compose --profile enterprise` (incl worker-watch), drop fixture `.jsonl`, assert `GET /api/sessions ≥1` AND worker readyz 200 iff watch-paths>0 | CI workflow file exists in `.github/workflows/`; workflow triggers on PRs touching `deploy/runtime/**` or `backend/runtime/**`; workflow runs docker compose enterprise profile + postgres; drops fixture .jsonl; asserts GET /api/sessions returns ≥1 row; asserts worker readyz is 200 when watch-path configured | L | devops-architect | P0-001, P0-002, P0-003, P0-004, P0-008 | 3 |

## Seam Task

| Task ID | Title | Change | Acceptance Criteria | Cplx | Assigned To | Batch |
|---------|-------|--------|---------------------|------|-------------|-------|
| P0-SEAM-0 | Compose↔config↔runtime integration verification | Review that P0-001, P0-006, P0-015, and P0-008 share a coherent env contract: every var set in compose is read in config.py, every config.py default matches compose default, and the worker profile chain (entrypoint → profile → capabilities) is consistent end-to-end | All compose env vars for worker-watch are defined in config.py with matching defaults; no phantom vars; worker startup sequence documented; integration_owner (devops-architect) signs off | S | devops-architect | after batch_2 |

## Phase 0 Quality Gates

- [ ] `docker compose --profile enterprise --profile postgres up` ingests ≥1 session with no extra flags (P0-013 passes)
- [ ] Worker `readyz` returns 503 with `configured_no_paths` when watch-paths=0; returns 200 when configured correctly
- [ ] No `PermissionError` on `projects.json` write at boot; atomic write confirmed
- [ ] `frontend` service does not serve nginx 502s before `api` healthcheck passes
- [ ] CORS: `localhost:3000` absent from enterprise allowed origins; present in local/dev
- [ ] `CCDASH_STARTUP_SYNC_LIGHT_MODE=true` in compose worker/worker-watch; heavy passes deferred
- [ ] Derived path alias map logged at startup
- [ ] compose.hosted.yml has correct usage header and functional pgvector image
- [ ] `task-completion-validator` sign-off
- [ ] `pg_advisory_lock` confirmed on Postgres; SQLite early-returns without lock

## Key Files

| File | Tasks | Notes |
|------|-------|-------|
| `compose.yaml` | P0-001, P0-004, P0-005, P0-007, P0-008, P0-009, P0-015 | Multiple tasks touch this file; sequence batch_0 changes then batch_1 |
| `entrypoint.sh` | P0-008 | Add worker-watch case |
| `backend/config.py` | P0-001, P0-006, P0-009, P0-015 | Single source of truth for all env defaults |
| `backend/runtime/container.py` | P0-003, P0-011, P0-014 | readyz contract, advisory lock, startup log |
| `backend/runtime/bootstrap.py` | P0-SEC-CORS | CORS origin gating |
| `backend/project_manager.py` | P0-005, P0-009 | Atomic _save(), CCDASH_PROJECTS_FILE |
| `backend/project_paths/providers/filesystem.py` | P0-002 | Path alias derivation |
| `backend/application/services/source_identity.py` | P0-002 | source_identity_policy_from_resolved_paths() |
| `backend/db/file_watcher.py` | P0-003 | watchPathCount seam |
| `backend/db/postgres_migrations.py` | P0-011 | advisory lock insertion point |
| `backend/adapters/jobs/runtime.py` | P0-015 | getattr fallback alignment (~:730) |
| `.github/workflows/` | P0-013 | New CI workflow |
| `compose.hosted.yml` | P0-010 | Header comment + pgvector fix |

## Rollback

All changes are default flips, compose edits, or additive guards. Rollback = revert env-var defaults + compose anchors. No schema migration, no data change. Path-alias derivation is additive (falls back to existing env-var path if derivation yields nothing).
