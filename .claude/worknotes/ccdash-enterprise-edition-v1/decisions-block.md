# Opus Decisions Block — CCDash Enterprise Liveness Hotfix & Storage Hygiene (Phase 0 + Phase 1)

> Architectural delta for `implementation-planner` to expand into the full plan. Anchors are **re-verified**
> (verify-state pass, 2026-05-30) and override the original bundle where they drifted. Analysis lives in the
> 7-doc bundle (`docs/project_plans/planning/ccdash-enterprise-edition-v1/`); do NOT restate it.
> PRD: `docs/project_plans/PRDs/infrastructure/ccdash-enterprise-liveness-storage-v1.md`.
> Tier 3 (Phase 0 ~M/15 tasks + Phase 1 ~L/19 tasks). Reviewer gates: `task-completion-validator` per phase;
> `karen` at feature end.

## Resolved §8 Decisions (do not re-litigate)

| Decision | Resolution |
|----------|------------|
| Worker topology | watch-all folded into default `enterprise` profile; per-project isolation stays opt-in |
| Transcript storage | canonical `session_messages` + filesystem SoT; `session_logs` DROP behind `CCDASH_DROP_SESSION_LOGS_ENABLED` (default OFF), staged after P1-010 |
| SQLite future | dev-only; pragmas gated to SQLite path (Postgres early-returns) |
| STARTUP_SYNC_LIGHT_MODE | config.py = single source of truth (default False); align getattr fallbacks to False; in-container default `=true` via compose |
| pgvector | keep `pgvector:pg17` for hosted; advisory lock needs no pgvector |

## Verify-State Corrections (load-bearing)

1. `CCDASH_WORKER_STARTUP_SYNC_ENABLED` is **compose-only**, not read by `config.py`. Real gate:
   `CCDASH_STARTUP_SYNC_ENABLED` + worker `RuntimeProfile.capabilities.sync=True`.
2. **No active light-mode mismatch** — `config.py:966` always defines the attr (False); fallbacks never fire;
   default startup currently runs FULL/heavy. Real consumer = `adapters/jobs/runtime.py` (~:730), not
   `bootstrap.py:188` (status-payload only).
3. worker-watch also overrides ingestion via `CCDASH_WORKER_WATCH_FILESYSTEM_INGESTION_ENABLED` (compose :169).
4. Drifted anchors to respect: `analytics.py get_latest_entries` now **57-83** (not 103-121);
   `entity_graph` commit at **:27**, upsert def **:41**; `sync_engine` delete-by-source at **:3939**.

---

## Phase 0 — Enterprise Liveness Hotfix

### Phase 0 Boundaries

| Task | Title | Cplx | Anchors (re-verified) | Change |
|------|-------|------|-----------------------|--------|
| P0-001 | Default-on ingestion + startup-sync + fold worker-watch into enterprise | M | `compose.yaml:27,133,157-193,169`; `config.py:246`; `container.py:237-243` | compose: `CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED:-true` (:27), add `"enterprise"` to worker-watch `profiles` (:161); `config.py:246` default→True. Worker sync via `CCDASH_STARTUP_SYNC_ENABLED`+profile, not the phantom var. |
| P0-002 | Auto-derive container path aliases from ResolvedProjectPaths | L | `project_paths/providers/filesystem.py:11-37`; `source_identity.py:247-308` | Add `source_identity_policy_from_resolved_paths(...)` beside the env builder; wire at policy construction; fall back to env for explicit overrides. `resolve()` stays a clean Path seam. |
| P0-003 | Fail-loud readyz when watch-paths==0 | M | `bootstrap_worker.py:50-61`; `container.py:650-671,875-921`; `file_watcher.py:43-45,105-112,252-266` | In container.py:650-671, when `capabilities.watch` and `watchPathCount==0` → `watcher_check_status="fail"` (new `configured_no_paths` reason) → `ready.ready=False` → 503. Distinguish "not configured" (warn) from "configured, zero paths" (fail). |
| P0-004 | WATCHFILES_FORCE_POLLING=true default for worker-watch | S | `compose.yaml:175`; `file_watcher.py:16,183` | compose default `:-true`; no code change (awatch honors env). |
| P0-005 | Writable projects.json + atomic _save() | S | `compose.yaml:44-48`; `project_manager.py:99-100,140-146` | compose `:48` read_only→false (scope to projects.json); `_save()` → temp-file + `os.replace()` + try/except. |
| P0-006 | Read worker env vars in config.py | S | `config.py` (absent) | Add `CCDASH_WORKER_WATCH_PROJECT_ID`, `CCDASH_WORKER_STARTUP_SYNC_ENABLED`, `CCDASH_WORKER_WATCH_STARTUP_SYNC_ENABLED` readers for k8s/bare-container. Keep behavior identical to compose-resolved values. |
| P0-007 | frontend depends_on api (service_healthy) | S | `compose.yaml:195-217`; `compose.hosted.yml:67-80` (pattern) | Add `depends_on: {api: {condition: service_healthy}}`. Confirm api healthcheck reachable in enterprise. |
| P0-008 | entrypoint.sh worker-watch dispatch | S | `entrypoint.sh:8,10-25`; `compose.yaml:162,165` | Add `worker-watch)` case launching `python -m backend.worker` with the worker-watch profile; closes the fall-through if the command override is removed. |
| P0-009 | Reconcile CCDASH_PROJECTS_FILE dead var | S | `project_manager.py:287`; `compose.yaml:45` | Prefer (a): make ProjectManager honor `CCDASH_PROJECTS_FILE` (add to config.py, pass at :287) for mount parity. Coordinate with P0-005. |
| P0-010 | Repair/deprecate compose.hosted.yml | M | `compose.hosted.yml:1-84` | Header comment: must be used as `-f compose.yaml -f compose.hosted.yml` (lacks profiles/volumes). Keep `pgvector:pg17` (vector parity). Fix placeholder `CCDASH_SAM_ENDPOINT` telemetry. |
| P0-011 | pg_advisory_lock around run_migrations() | M | `container.py:106-108`; `postgres_migrations.py:1497-1519` | Wrap `run_migrations()` in `pg_advisory_lock(<stable key>)` (Postgres-only; SQLite skips). Second caller waits. |
| P0-012 | Canonical-source-key delete path | M | `sync_engine.py:3939` (delete), `:4135` (upsert canonical), `:1292` (`_canonical_source_key`) | Change session + document delete to use `_canonical_source_key(project_id, path, kind)` matching upsert. Fixes orphaned rows. **Implement in Phase 1 batch (schema-adjacent, data-integrity).** |
| P0-013 | CI docker compose up e2e smoke gate | L | `compose.yaml` enterprise topology; `bootstrap_worker.py:50-61`; `file_watcher.py:252-266`; NEW `.github/workflows/*` | New workflow: `docker compose --profile enterprise` (incl worker-watch), drop fixture `.jsonl`, assert `GET /api/sessions ≥1` AND worker readyz 200 iff watch-paths>0. Depends P0-001/003/008. |
| P0-014 | Startup fail-loud log (enterprise + ingestion-off + empty DB) | S | `container.py:237-243,106-108`; `config.py:246` | Loud WARNING at startup with exact remediation when enterprise + `filesystem_source_of_truth=False` + zero sessions. |
| P0-015 | Reconcile STARTUP_SYNC_LIGHT_MODE | M | `config.py:966`; `adapters/jobs/runtime.py:~730`; `sync_engine.py:4261`; compose worker/worker-watch | Align both getattr fallbacks→False (config single SoT); compose worker/worker-watch default `CCDASH_STARTUP_SYNC_LIGHT_MODE=true`. Sequence WITH P0-001 (avoid heavy-sync window). |
| P0-SEC-CORS | Gate dev CORS origins behind dev flag | S | `bootstrap.py:57-67` | localhost origins only in dev/local; enterprise allows only `config.FRONTEND_ORIGIN`. |

### Phase 0 Batches (dependency-ordered)

- **batch_0 (parallel, no cross-deps):** P0-004, P0-005, P0-006, P0-007, P0-009, P0-014, P0-SEC-CORS
- **batch_1 (core wiring; sequence-sensitive):** P0-001 → then P0-015 (paired, avoid heavy-sync window) → P0-008, P0-011
- **batch_2 (depend on wiring):** P0-002 (path alias), P0-003 (readyz; needs watchPathCount seam), P0-010
- **batch_3 (exit gate):** P0-013 (after 001/002/003/004/008 land)

### Phase 0 Agent Routing

| Tasks | Primary | Model |
|-------|---------|-------|
| Compose/entrypoint (001,004,005,007,008,009,010,015 compose half) | `devops-architect` | sonnet |
| Backend wiring (001 config half, 002, 003, 006, 011, 014, 015 code half, SEC-CORS) | `python-backend-engineer` | sonnet |
| Path alias derivation (002) | `python-backend-engineer` (+`backend-architect` review) | sonnet |
| e2e smoke gate (013) | `devops-architect` | sonnet |

---

## Phase 1 — Storage Hygiene & DB Performance

### Phase 1 Boundaries

| Task | Title | Cplx | Destructive | Depends | Anchors (re-verified) |
|------|-------|------|-------------|---------|------------------------|
| P1-019 | entity_links.project_id + idx_links_project (Phase 2 prereq) | M | no | P1-008 | `sqlite_migrations.py:37-56`; pg entity_links DDL; `entity_graph.py` |
| P1-004 | Backfill idx_sessions_project_status_updated via _ensure_index | S | no | — | `sqlite_migrations.py:161-162,1362-1367` |
| P1-005 | idx_sessions_source_file (+composite) | S | no | — | `repositories/sessions.py:161-167`; `sync_engine.py:4121-4130` |
| P1-006 | SQLite pragmas (dev-only) | S | no | — | `connection.py:50-54` |
| P1-008 | entity_graph.upsert single-tx executemany | M | no | — | `entity_graph.py:27,41` |
| P1-009 | executemany inserts (telemetry/attribution/session-log) | M | no | — | `sync_engine.py:1428-1456`; `usage_attribution.py:26,53`; `repositories/sessions.py:730-753` |
| P1-010 | Materialize session badge columns | L | no | — | `api.py:624-660`; `services/sessions.py:87-118`; sessions DDL; `repositories/sessions.py` |
| P1-011 | Postgres atomic upsert_logs/file_updates | M | no | — | `repositories/postgres/sessions.py:88+`; `_transactions.py` |
| P1-012 | Postgres entity_links UNIQUE into initial DDL | M | no | — | `postgres_migrations.py:1491-1498` |
| P1-001 | analytics_entries retention DELETE + ON CONFLICT upsert | L | **yes** | — | `analytics.py:20,47`; `sync_engine.py:5802-5812`; `base.py` Protocol |
| P1-003 | telemetry_events TTL retention | M | **yes** | — | `sqlite_migrations.py:501-542`; `sync_engine.py:1428-1456,1495-1527` |
| P1-007 | _capture_analytics N+1 → batched CTE/JOIN | L | no | P1-004 | `sync_engine.py:5787,5876-5972`; `analytics.py` |
| P1-013 | get_latest_entries HAVING fix | S | no | P1-001 | `analytics.py:57-83` |
| P1-014 | partial indexes (analytics period='point', telemetry event_type) | S | no | P1-001 | `analytics.py:57-83`; index sections |
| P1-017 | manifest JSONL session-scan skip | M | no | — | `sync_engine.py:4107-4119,4239-4278` |
| P1-018 | batch startup backfill loops | M | no | — | `sync_engine.py:2058-2095` |
| P1-010→P1-002 | Drop session_logs (staged, flag-gated default-OFF) | XL | **yes (gated)** | P1-010 | `sqlite_migrations.py:165-220`; `services/sessions.py:87-118`; 6 consumers (api.py:626,660,812,844,956; `_client_v1_features.py:814,849`; `feature_forensics.py:167`; `skillmeat_memory_drafts.py:269`) |
| P1-016 | FTS5/tsvector on session_messages.content | L | no | P1-002 | session_messages DDL; LIKE path. **DEFER if P1-002 staging incomplete.** |
| P1-015 | Reconcile SQLite(27)/Postgres(28) SCHEMA_VERSION | M | no | 004,005,010,012,014,019 | `sqlite_migrations.py:16`; `postgres_migrations.py:11`. **Lands LAST.** |

### Phase 1 Batches (dependency-ordered)

- **batch_0 (parallel, additive/non-destructive, no cross-deps):** P1-004, P1-005, P1-006, P1-008, P1-009, P1-011, P1-012, P1-017, P1-018
- **batch_1 (schema/materialization; depends batch_0 seams):** P1-019 (after 008), P1-010 (badge materialization)
- **batch_2 (destructive retention — flag-gated, batched, worker-scheduled):** P1-001 (+ then P1-013, P1-014), P1-003
- **batch_3 (N+1 perf, needs indexes):** P1-007 (after P1-004)
- **batch_4 (staged drop — flag-gated default-OFF):** P1-002 (after P1-010 + all 6 consumers migrated), then P1-016 (optional; defer if staging incomplete)
- **batch_5 (version bump — LAST):** P1-015 (after every additive DDL)
- **P0-012** (canonical delete) folds into batch_1 (data-integrity, schema-adjacent).

### Phase 1 Agent Routing

| Tasks | Primary | Model |
|-------|---------|-------|
| Schema/migrations/indexes (004,005,012,015,019) | `data-layer-expert` | sonnet |
| Retention/TTL + repo Protocol (001,003,013,014) | `data-layer-expert` | sonnet |
| N+1 rewrite + batching (007,008,009,018) | `python-backend-engineer` | sonnet |
| Badge materialization + consumer migration (010,002) | `python-backend-engineer` (+`data-layer-expert` for DDL) | sonnet |
| Postgres atomicity (011) | `data-layer-expert` | sonnet |
| Pragmas + scan-skip (006,017) | `python-backend-engineer` | sonnet |
| Canonical delete (P0-012) | `python-backend-engineer` | sonnet |
| FTS5 (016) | `data-layer-expert` | sonnet |

## Risk Hotspots

| Risk | Severity | Mitigation |
|------|----------|------------|
| Default-on ingestion triggers heavy blocking startup sync | HIGH | P0-015 light-mode reconcile lands WITH P0-001; in-container light defers heavy passes |
| session_logs drop irreversible | HIGH | flag-gated default-OFF, staged after P1-010, DB snapshot, filesystem JSONL = re-derivable SoT |
| retention DELETE locks SQLite under load | MED | batched (batch_size=1000), busy_timeout, worker-scheduled off request path |
| SCHEMA_VERSION no-op on existing DBs | MED | P1-015 lands LAST, accounts for all additive DDL; `_ensure_index` idempotent backfills |
| Cross-owner seams (compose↔config↔runtime) | MED | P0-001/006/015 share env contract — one integration_owner; e2e smoke is the seam test |
| Path-alias mis-map | MED | log derived alias map at startup; fail-loud readyz (P0-003) catches zero-path result |

## Estimation Anchor

Phase 0 ≈ M (mostly default flips + 1 L path-alias + e2e harness); Phase 1 ≈ L. Comparable: prior
`containerized-deployment-v1` (compose/runtime wiring) and `runtime-performance-hardening-v1` (FE memory caps).
No SPIKE needed — all tasks have enumerable test scenarios; anchors re-verified.

## Plan Skeleton Pointer

- Template: `.claude/skills/planning/templates/implementation-plan-template.md`
- Output: `docs/project_plans/implementation_plans/infrastructure/ccdash-enterprise-liveness-storage-v1.md`
  (split into `ccdash-enterprise-liveness-storage-v1/phase-0-liveness.md` and `phase-1-storage.md` if >800 lines)
- Progress: `.claude/progress/ccdash-enterprise-edition-v1/phase-0-progress.md` + `phase-1-progress.md`
