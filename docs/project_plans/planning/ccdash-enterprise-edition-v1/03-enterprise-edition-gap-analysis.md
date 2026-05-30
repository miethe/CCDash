---
schema_version: 2
doc_type: report
report_category: audits
title: "CCDash Enterprise Edition Gap Analysis"
status: draft
created: 2026-05-30
updated: 2026-05-30
feature_slug: ccdash-enterprise-edition-v1
audience: [ai-agents, developers]
related_documents:
  - docs/project_plans/planning/ccdash-enterprise-edition-v1/README.md
---

# CCDash Enterprise Edition Gap Analysis

> Source evidence: 12-domain forensic investigation (2026-05-30). Steering document:
> `.claude/worknotes/ccdash-enterprise-edition-v1/synthesis-brief.md`. Issue ledger (130 issues),
> `completed-and-gaps.md`, and `investigation/*.md` provide the file:line anchors cited below.

## 0. Thesis (one paragraph)

CCDash already contains **most of the enterprise scaffolding it needs**: containerization, five explicit
runtime profiles, a data-platform capability contract, an SSE live-update platform, Postgres NOTIFY live
ingest, a query-cache layer, a completed TanStack Query migration, a planning control plane, a planning
command center (V1), and a multi-project command center (flagged off). The enterprise edition is **not
failing because the architecture is wrong** — it is failing because **the container last-mile is mis-wired
and disabled-by-default**, and because a cluster of data-volume, N+1, and cache-correctness defects make it
slow at `skillmeat` scale. The work ahead is **finishing, wiring, and hardening**, not rewriting. The single
most operationally damaging fact: a standard `docker compose --profile enterprise --profile postgres up`
**ingests nothing and reports healthy** — the headline failure this document settles definitively in §2.

This analysis is organized as: what works (§1), the definitive root-cause of the container live-data failure
(§2), what else is broken (§3), what is missing for enterprise (§4), required changes by area (§5), and a
comprehensive gap table (§6). Phase boundaries (Phase 0–6) and target-architecture decisions are inherited
verbatim from the synthesis brief.

---

## 1. What WORKS — Completed Enterprise Scaffolding Ledger

The enterprise foundation is real and largely correct. Nineteen prior efforts shipped the scaffolding below.
Evidence drawn from `completed-and-gaps.md` and `investigation/completed-work.md`.

| Capability | Status | Evidence (file:line) | Notes |
|---|---|---|---|
| **Single-image multi-stage Dockerfile** | COMPLETED | `deploy/runtime/Dockerfile`; entrypoint dispatch on `CCDASH_RUNTIME_PROFILE` | Non-root `ccdash:ccdash` user, `ARG BUILD_UID/BUILD_GID` |
| **Compose profiles** (local/enterprise/postgres/live-watch) | COMPLETED | `deploy/runtime/compose.yaml`; `x-backend-service` anchor at `compose.yaml:44–84` | Workspace/claude/codex bind mounts; podman `!reset` override in `compose.external-postgres.yaml` |
| **Five runtime profiles** (local/api/worker/worker-watch/test) | COMPLETED | `backend/runtime/profiles.py:28–89` | `RuntimeCapabilities(watch,sync,jobs,auth,integrations)`; `api` profile correctly excludes all background work |
| **Data-platform modularization** | COMPLETED | `backend/config.py` storage profile; `backend/data_domains.py`; `backend/runtime/storage_contract.py` | Canonical vs derived classification; `enterprise` requires Postgres (`config.py:213–228`) |
| **SSE live-update platform** | COMPLETED | `backend/adapters/live_updates/in_memory_broker.py`; `GET /api/live/stream` (`backend/routers/live.py`) | `useLiveInvalidation` FE hook in `services/live/` |
| **Enterprise live-session ingest** (worker-watch + Postgres NOTIFY) | COMPLETED (PRD stale at `draft`) | `profiles.py:65`; `container.py:111–118`; `postgres_listener.py`; `compose.yaml:159` | NOTIFY/LISTEN fanout: worker publishes, API listens, SSE republishes |
| **Source path canonicalization hardening** | COMPLETED | `backend/services/source_identity.py:120–138` canonical key scheme | `ccdash-source:v1/{project}/{kind}/{root}/{rel}` |
| **Session transcript append-deltas** | COMPLETED | canonical transcript repo; append-delta ingestion; FE delta via SSE | Only new JSONL lines reprocessed on change |
| **DB caching layer** (canonical session storage) | COMPLETED (phases 3–4) | `session_messages` canonical tables; Postgres-ready DDL | Phases 1–2 predate progress tracking |
| **Query cache layer** (`@memoized_query`) | COMPLETED | `backend/application/services/agent_queries/cache.py:328`; TTL default 600s (`config.py:983`) | 14 service methods cached; `bypass_cache=True` param; `POST /api/cache/invalidate` |
| **Runtime performance hardening** | COMPLETED | transcript ring-buffer cap (`contexts/dataContextShared.ts:61`); `MAX_DOCUMENTS_IN_MEMORY=2000`; react-virtual | `VITE_CCDASH_MEMORY_GUARD_ENABLED` flag |
| **TanStack Query migration** | COMPLETED (phases 0–7, 176 guardrail tests) | `services/queries/`; `services/queryKeys.ts`; `App.tsx:87` `QueryClientProvider` | Fat-read bundles: `/api/v1/dashboard`, `/api/agent/planning/view`, `/api/analytics/overview-bundle` |
| **Feature-surface data-loading redesign** | COMPLETED (documented partial gap) | feature card list/rollup/modal v1 endpoints; `useFeatureSurface` hook | `ProjectBoard` off session-summary loop; SQLite+Postgres parity |
| **Hexagonal foundation** (router→service→repo) | COMPLETED | all 6 phases | Transport-neutral `agent_queries` layer |
| **Planning control plane** | COMPLETED (all 8 phases) | `/api/agent/planning/*`; `PlanningHomePage`, `GraphPanel`, `AgentSessionBoard`, `SummaryPanel` | — |
| **Planning command center (V1)** | COMPLETED (PRD stale at `draft`) | `GET /api/agent/planning/command-center`; `PlanningCommandCenter.tsx` list/card/board | `WorktreeGitStatePanel`; AAR + impl plan both `completed` |
| **Multi-project command center** | COMPLETED — **flagged OFF** | `MultiProjectCommandCenter.tsx`; `multi_project_planning_command_center.py`; `constants.ts:399–421` | `VITE_CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED=false` default |
| **Planning forensics boundary extraction** | COMPLETED (all 6 phases) | — | — |
| **Shared auth / RBAC / SSO** | COMPLETED (phases 2–7) | `CCDASH_API_BEARER_TOKEN`; `authGuardrail` in health endpoint | Commits `68c6cdb`, `3799316`, `d42ef27` |
| **Watcher rebind** (atomic project switch) | COMPLETED (commit `b1c83e4`) | `backend/adapters/jobs/runtime.py:198–338` | Stop→drain→start; AC-1..AC-4 verified; **single-watcher only** |
| **Worker probe server** | COMPLETED | `bootstrap_worker.py:31–67`; `/livez` `/readyz` `/detailz` on port 9465/9466 | Rich job observation: `lastStartedAt`, `lastDurationMs`, `lastError`, `checkpointFreshnessSeconds` |

**Net assessment**: every enterprise-tier subsystem exists as a working skeleton. The defects are at the
seams — defaults, path translation, cache sharing, multi-project orchestration, and storage hygiene — not in
the core design.

---

## 2. WHY CONTAINERIZED MODE FAILS (the headline)

**Definitive answer**: A default enterprise deployment pulls no live data because of **three independent,
compounding defects**. Each one is **independently sufficient** to leave the container database empty, and
all three are present simultaneously in the shipped `compose.yaml`. The system fails **silently** — `readyz`
returns 200, no error is logged, and the dashboard shows an empty (or stale) state with no diagnostic.
Confidence: **HIGH** (corroborated by `container-deploy`, `ingestion-fs`, `multi-project`, and
`workers-runtime` domain agents independently).

### 2(a). Ingestion is disabled by default

Three settings combine so that **no sync engine is ever instantiated** in a default enterprise run:

1. **`CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED` defaults to `false`.** In the compose anchor,
   `CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED: "${...:-false}"` (`compose.yaml:~27`). This flows into
   `config.py:244–246`:
   ```python
   filesystem_source_of_truth = profile == "local"
   if profile == "enterprise":
       filesystem_source_of_truth = _env_bool_from(env, "CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED", False)
   ```
   With `filesystem_source_of_truth=False`, `_sync_engine_enabled()` returns `False`
   (`backend/runtime/container.py:237–242`), so the `SyncEngine` is **never constructed**
   (`container.py:204–207`). No sync engine → no startup sync, no watcher, empty API.

2. **`CCDASH_WORKER_STARTUP_SYNC_ENABLED` defaults to `false` for the `worker` service.** The standard worker
   maps `CCDASH_STARTUP_SYNC_ENABLED: "${CCDASH_WORKER_STARTUP_SYNC_ENABLED:-false}"` (`compose.yaml:133`).
   Even if a sync engine existed, the enterprise worker performs **no initial filesystem scan**
   (`workers-runtime.md` §"Enterprise Worker Does NOT Own Startup Sync by Default", `config.py:961`).

3. **The `live-watch` profile is NOT in the default startup command.** Only the `worker-watch` service
   overrides both flags on (`CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED=true`,
   `CCDASH_STARTUP_SYNC_ENABLED=true` — `compose.yaml:159–193`), and it lives behind
   `profiles: ["live-watch"]`. The standard enterprise command is
   `docker compose --profile enterprise --profile postgres up` — which **does not start the watcher**
   (`container-deploy.md` §6, §7). The operator must additionally pass `--profile live-watch`, which is not in
   the default enterprise docs.

**Why independently sufficient**: With all three at their shipped defaults, the `api` profile has
`sync=False` by design (`profiles.py:47–51`), the `worker` does no startup sync, and `worker-watch` does not
run. The result: **zero ingestion paths are active**. The DB starts empty and stays empty.

### 2(b). Host paths are unresolvable in-container, and the alias is not auto-derived

Even after (a) is fixed, the second defect prevents the watcher from observing anything:

1. **`projects.json` stores host-absolute paths.** Actual data (`projects.json:338`, confirmed by inspection):
   ```
   [3df0ff70] SkillMeat  root.filesystemPath: /Users/miethe/dev/homelab/development/skillmeat
                         sessions.filesystemPath: ~/.claude/projects/-Users-miethe-dev-homelab-development-skillmeat
   [479ae45d] MeatyWiki  sessions.filesystemPath: /Users/miethe/.claude/projects/-Users-miethe-dev-homelab-development-meatywiki
   ```
   Inside the container, `/Users/miethe/...` paths **do not exist** — they were never mounted at that path
   (`container-deploy.md` §3.2).

2. **`FilesystemProjectPathProvider.resolve()` opens raw paths with no alias translation.** At
   `backend/services/project_paths/providers/filesystem.py:25–28` it calls `Path(raw_value).expanduser()` then
   `.resolve(strict=False)` — which **lexically** resolves a non-existent path without raising
   (`ingestion-fs.md` Finding 11). The source-identity aliasing in `source_identity.py:271–308` exists, but it
   only canonicalizes session **keys** during sync; it does **not** rewrite the directory paths the watcher
   opens (`container-deploy.md` §3.2). The alias depends entirely on the operator setting ~6 env vars
   (`CCDASH_WORKSPACE_HOST_ROOT`/`_CONTAINER_ROOT`, `CCDASH_CLAUDE_HOME`/`_CONTAINER_HOME`, 6 extra slots)
   correctly — it is **not auto-populated from `ResolvedProjectPaths`** (synthesis §1.2).

3. **`readyz` passes with zero watch paths (silent failure).** `_resolve_watch_paths` discards non-existent
   paths: `watch_paths = [p for p in [sessions_dir, docs_dir, progress_dir] if p.exists()]`
   (`file_watcher.py:252–266`). When all paths are filtered out, the watcher logs "File watcher configured
   with no existing paths" (`file_watcher.py:108–112`), enters `configured_no_paths` state, and **still passes
   `readyz`** (`ingestion-fs.md` GAP: "No readiness probe failure when worker-watch has zero valid watch
   paths"). The operator sees a healthy container watching nothing.

**Why independently sufficient**: With (a) fixed but paths unresolved, the watcher watches **zero
directories** and the startup scan finds **zero files** — and reports healthy. This is the "second-most-likely
cause" called out explicitly in `ingestion-fs.md` Finding 11.

### 2(c). inotify is dead on bind mounts, and a read-only `projects.json` write crashes startup

Even after (a) and (b) are fixed (paths resolve, ingestion enabled), live updates still fail on the most
common operator platform:

1. **`watchfiles` inotify does not fire on Docker Desktop bind mounts.** `file_watcher.py:16,183` uses
   `awatch(*watch_paths, ...)`, which defaults to inotify/kqueue. Docker Desktop on macOS uses VirtioFS /
   gRPC-FUSE; inotify events are **not delivered** through that layer (`ingestion-fs.md` Defect 3). The watcher
   reports `running`, logs "File watcher started", and silently receives no events.

2. **`WATCHFILES_FORCE_POLLING` defaults to `false`.** The fix is documented (`deploy/runtime/README.md:178`)
   and the env var is plumbed (`compose.yaml:175`), but compose passes it **only** to `worker-watch` and
   defaults it `false`. Any operator on macOS Docker Desktop without explicitly setting
   `WATCHFILES_FORCE_POLLING=true` gets a healthy-looking watcher with no events.

3. **`projects.json` is mounted `read_only:true` but `ProjectManager._save()` writes on startup.**
   `compose.yaml:48` mounts the file read-only. `_load()` detects a schema migration and calls `_save()`
   (`project_manager.py:100,114–127`), which executes `self.storage_path.write_text(...)`
   (`project_manager.py:140–146`). On a read-only mount this raises **`PermissionError` at startup**,
   corrupting the boot flow (`container-deploy.md` §3.3). `_save()` is also non-atomic and unguarded — no
   temp-file+rename, no lock (`multi-project.md` §1).

**Why independently sufficient**: With (a) and (b) fixed, a macOS-Docker-Desktop operator still gets no live
updates (inotify dead), and any operator whose `projects.json` triggers migration crashes on startup
(read-only write).

### 2-Summary: the compounding failure chain

```
docker compose --profile enterprise --profile postgres up
        │
        ▼
(a) CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED=false  ──► _sync_engine_enabled()=False ──► no SyncEngine
        │  (worker STARTUP_SYNC=false; live-watch not in command)            │
        ▼                                                                    ▼
   even if enabled:                                                    DB stays EMPTY
(b) projects.json host paths unresolvable in-container ──► watch_paths == 0 ──► readyz still 200 (SILENT)
        │
        ▼
   even if paths resolve:
(c) inotify dead on bind mount (WATCHFILES_FORCE_POLLING=false) ──► no events
    + projects.json read_only + _save() on migration ──► PermissionError crash
```

The fix is **defaults + wiring + a fail-loud readiness contract + an e2e smoke test** — this is **Phase 0
(Enterprise Liveness Hotfix)** in the roadmap, the highest-ROI, lowest-risk first phase. It introduces **no
new subsystems**.

---

## 3. What is BROKEN (beyond §2)

These are confirmed defects independent of the empty-DB headline. They degrade correctness or block specific
deployment topologies.

| Defect | Severity | Evidence (file:line) | Effect |
|---|---|---|---|
| **`projects.json` read-only mount + `_save()` write on migration** | HIGH | `compose.yaml:48`; `project_manager.py:100,140–146` | `PermissionError` crash at startup on modified schemas; non-atomic torn writes |
| **`CCDASH_PROJECTS_FILE` is a dead env var** | MEDIUM | documented in `container_project_onboarding.py`; never read in `config.py` or `ProjectManager.__init__` (`project_manager.py:287`) | No way to override projects.json path; operators set a var that does nothing |
| **`frontend` service has no `depends_on: api`** | HIGH | `compose.yaml:195–217` | nginx serves 502 Bad Gateway until API becomes healthy; no startup ordering |
| **`entrypoint.sh` missing `worker-watch` case** | MEDIUM | `entrypoint.sh:10–24` handles only `local\|api\|worker`; `compose.yaml:165` sets `worker-watch` | Falls through to error case; compose works around via `command:` override (`compose.yaml:162`); `compose.hosted.yml` path cannot launch worker-watch |
| **`compose.hosted.yml` diverged / broken** | HIGH | `container-deploy.md` §9; `deploy/runtime/api/Dockerfile`, `worker/Dockerfile` | No filesystem volume mounts → no ingestion; worker runs as root (no `USER`); no `CCDASH_WORKER_PROJECT_ID` → `RuntimeError` on boot |
| **No Postgres migration advisory lock** | MEDIUM | `container.py:106–108`; `postgres_migrations.py:1497` | Both `api` and `worker` run `run_migrations()` on startup; DDL race on fresh DB (mitigated by `CREATE TABLE IF NOT EXISTS`, but `schema_version` insert not atomic) |
| **CORS always allows localhost** | MEDIUM | `bootstrap.py:57–66` | `http://localhost:3000` + `http://127.0.0.1:3000` always permitted regardless of `CCDASH_FRONTEND_ORIGIN` — insecure in production |
| **Watcher delete uses raw `str(path)` not canonical key** | HIGH | `sync_engine.py:3944` (raw) vs `sync_engine.py:4171` (canonical) | Watcher-triggered deletes leave orphaned DB rows after file deletion |
| **`CCDASH_WORKER_WATCH_PROJECT_ID` / `_STARTUP_SYNC_ENABLED` not read by Python** | HIGH | resolved only at compose layer (`compose.yaml:166,170`); absent from `config.py` | k8s / bare-container operators get silent misconfiguration; `container_project_onboarding.py:122` writes vars compose ignores |
| **Module-level `container = build_worker_runtime()`** | MEDIUM | `bootstrap_worker.py:86`; re-imported by `worker.py:11` | Orphaned `RuntimeContainer` at import time; reads profile env at import not call time; double-instantiation |
| **No task supervision (dead task → `idle`)** | HIGH | `runtime.py:385–420`; `local.py:9–10` bare `asyncio.create_task()` | A crashed job reports `idle`, not `dead`/`failed`; silent permanent stoppage until restart |
| **`STARTUP_SYNC_LIGHT_MODE` triple default mismatch** | MEDIUM | `config.py:966` (`False`); `runtime.py:731` getattr (`True`); `sync_engine.py:4261` getattr (`False`) | Behavior depends on which path reads the flag; full blocking sync on large DB if `False` |
| **Postgres NOTIFY listener has no reconnect/backoff** | HIGH | `postgres_listener.py` (deferred FU-2) | A transient DB disconnect permanently kills live fanout until API restart |
| **FU-004 bootstrap test skips on now-fixed code** | HIGH | `test_runtime_bootstrap.py:616,680,716,1057,1333` | 5 test classes/methods permanently skipped; fields they assert missing are present at `bootstrap.py:176,224`; lifecycle coverage gone |
| **`session_messages` duplicates `session_logs` content** | HIGH (storage) | `sqlite_migrations.py:192–225`; ~1.2–1.75 GB dead storage | Two full copies of transcript data; `session_logs` never purged after canonical messages written |
| **`idx_sessions_project_status_updated` absent from live DB** | HIGH | declared in `_TABLES` (`sqlite_migrations.py:161–162`) but never `_ensure_index` backfilled; `_TABLES` only runs on version bump (`sqlite_migrations.py:1362–1367`) | `count_active`/`list_active` fall back to partial index; residual status filter |
| **`entity_graph.upsert()` commits per link** | HIGH | `entity_graph.py:40` | 25K individual commits during link rebuild; unbounded WAL writes |
| **`_capture_analytics` triple N+1** | CRITICAL | `sync_engine.py:5874–5960` | ~12K–15K DB queries per snapshot (367 features × task list + link list + per-session `get_by_id`) |
| **Schema version mismatch SQLite(27) vs Postgres(28)** | MEDIUM | `sqlite_migrations.py:16`; `postgres_migrations.py:11` | SQLite path thinks DB already at 27, skips `_TABLES`; `source_ref` column drift |
| **Postgres `upsert_logs`/`upsert_file_updates` not transactional** | HIGH | `postgres/sessions.py:88+`; `_transactions.py` helper exists but unused | DELETE + N INSERT not atomic on Pool; partial failure = data loss |
| **`entity_links` UNIQUE constraint added post-initial DDL (Postgres)** | HIGH | `postgres_migrations.py:1491–1498` | Fresh install: `ON CONFLICT` silently inserts duplicates before constraint applied; backfill fails if dupes exist |

---

## 4. What is MISSING for Enterprise

These are net-new capabilities required for multi-replica, multi-project, production-scale operation. They are
the substance of Phases 2–6.

| Missing capability | Why enterprise needs it | Evidence (file:line) |
|---|---|---|
| **DB-backed project registry** | `projects.json` is a host file; multi-replica API pods fork independent copies that diverge on every add/switch | `project_manager.py:287`; `multi-project.md` §1; synthesis §6.1 |
| **Shared distributed cache (Redis/Valkey or Postgres-backed)** | In-process `TTLCache(maxsize=512)` is per-process; api+worker and api replicas each have a private, cold, inconsistent cache; no invalidation propagation | `cache.py:50`; `caching.md` §"In-process cache broken across enterprise containers"; synthesis §6.1 |
| **Durable task queue** | Bare `asyncio.create_task()` has no queue/retry/priority/backpressure; container crash mid-sync loses all in-flight work and forces full re-sync | `local.py:8–10`; `workers-runtime.md` §"No External Job Queue"; synthesis §3 |
| **Multi-project worker orchestration** | `FileWatcher` is a process-level singleton (`file_watcher.py:307`); one project watched at a time; multi-project = N containers with no shared scheduler or cross-project analytics | `multi-project.md` §4; `workers-runtime.md` §"One-Project-Per-Worker" |
| **OQ-overlay persistence (DB)** | Open-question resolutions live in process memory (`_OQ_OVERLAY`), lost on restart, multi-instance-incompatible | synthesis §4; `completed-and-gaps.md` data-contracts; `planning.py:1567` `clear_cache()` |
| **Retention / TTL policies** | `analytics_entries` (1.8M rows, 466 MB, zero retention, +3,313/sync) and `telemetry_events.payload_json` (1.6 GB) grow unbounded | `database.md` §2c, §8; `analytics.py` (no DELETE/prune method exists) |
| **Container e2e smoke test** | No CI test runs `docker compose up` and asserts sessions appear in the API; the §2 failure shipped undetected | `ingestion-fs.md` GAP "No end-to-end container smoke test"; synthesis §6.2 |
| **`tokenUsageByModel` on `Feature`** | `PlanningTokenTelemetry.source` is always `unavailable` — a planning KPI is structurally broken | `data-contracts.md`; synthesis §4; `planning.py` |
| **Per-metric TTL enforcement** | `CCDASH_LIVE_COUNT_CACHE_TTL_SECONDS` / `CCDASH_SYSTEM_METRICS_CACHE_TTL_SECONDS` are phantom config — read but never fed into a TTL slot | `caching.md` §"Documented-but-Broken Per-Metric TTLs"; `cache.py:50` |
| **Sync-triggered cache invalidation** | No hook from `sync_project()` to evict project cache after ingestion; results stale up to 600s | `caching.md` §"Invalidation on Write"; `routers/cache.py:363–424` |
| **Project-scoped `entity_links` fingerprint** | `entity_links` has no `project_id`; fingerprint does a global `GROUP_CONCAT` scan on every cached request | `cache.py:258–289`; `sqlite_migrations.py:37–56` |
| **Session PK project isolation** | `sessions.id` is a global PK; `ON CONFLICT(id)` omits `project_id`; cross-project session-ID collision silently steals a session | `multi-project.md` §3; `repositories/sessions.py:20–87` |
| **`project_id` on detail tables** | `session_logs`/`session_tool_usage`/`session_file_updates`/`session_artifacts` have no `project_id` | `multi-project.md` §3 |
| **Multi-project cache warming / analytics loop** | Warmer + analytics cover only the bound/active project; N-1 projects always cold/stale | `runtime.py:794–799,894–895`; `multi-project.md` Gap 6 |
| **Cross-project token/cost aggregate + ranked next-work endpoint** | Command-center KPIs incomplete; no priority-ordered execution backlog | `data-contracts.md` GAPs; synthesis §4 |
| **ARC council + MeatyWiki integrations** | Registered as projects only; zero model/client/table/endpoint | `data-contracts.md` GAPs; synthesis §4 (Phase 5+) |
| **Manifest-based session scan skip** | Full `rglob("*.jsonl")` + N DB lookups on every startup; documents have light-mode skip, sessions do not | `sync_engine.py:4107–4119`; `ingestion-fs.md` Finding 5 |
| **SQLite production pragmas** | `cache_size` (8 MB for 10 GB DB), `synchronous`, `mmap_size`, `wal_autocheckpoint`, `temp_store` untuned | `connection.py:52–54`; `database.md` §5e |
| **`executemany` batch inserts + FTS5** | Row-by-row INSERT across telemetry/attribution/logs; no FTS5 on `session_messages.content` (O(n) search) | `database.md` §4; `perf-evidence.md` GAPs |
| **Scheduled VACUUM / ANALYZE** | 157 free pages, no statistics refresh; no retention job scheduler | `perf-evidence.md` GAP |

---

## 5. Required Changes Grouped by Area

The full target design lives in **doc 05 (target architecture)**. This section maps gaps to areas and phases.
Phase boundaries are inherited verbatim from synthesis §7.

### 5.1 Container topology — **Phase 0 (Enterprise Liveness Hotfix)**

Lowest-risk, highest-ROI. Resolves §2 (a)(b)(c) and the §3 topology defects.

- Flip the enterprise-path default for worker ingestion/startup sync on, or fold `live-watch` into the default
  enterprise topology so `docker compose --profile enterprise --profile postgres up` ingests. (`compose.yaml:27,133`)
- Auto-derive container path aliases from `ResolvedProjectPaths` at `SyncEngine` construction, not from env
  vars (`source_identity.py:271–308`; `providers/filesystem.py:25–28`).
- Make `readyz` **FAIL** when `worker-watch` has zero watch paths (`file_watcher.py:108–112,252–266`).
- Default `WATCHFILES_FORCE_POLLING=true` for `worker-watch` on non-Linux hosts (`compose.yaml:175`).
- Make project registry writable (mount `projects.json` read-write or DB-back it); fix `_save()` to atomic
  temp-file+rename (`project_manager.py:140–146`).
- Add `frontend depends_on: api` (`compose.yaml:195–217`); add `worker-watch` to `entrypoint.sh` (`entrypoint.sh:10–24`).
- Add a `pg_try_advisory_lock` guard around `run_migrations()` (`container.py:106–108`).
- Add a CI `docker compose up` smoke test asserting sessions appear in the API.

### 5.2 Postgres / data hygiene — **Phase 1 (Storage Hygiene & DB Performance)**

- Retention/TTL jobs for `analytics_entries` (90-day window, ~50× reduction) and `telemetry_events`
  (`database.md` §8; `analytics.py`).
- Drop duplicate `session_logs` after canonical `session_messages` written (`sqlite_migrations.py:192–225`).
- Tune SQLite pragmas: `cache_size` ≥ 32768 pages, `synchronous=NORMAL` (`connection.py:52–54`).
- Backfill `idx_sessions_project_status_updated` via `_ensure_index`; add `idx_sessions_source_file`,
  analytics partial index for `period='point'` (`database.md` §3a,3b,7).
- `executemany` + single-transaction upserts; wrap Postgres `upsert_logs`/`upsert_file_updates` in
  transactions (`postgres/sessions.py:88+`); batch `entity_graph.upsert()` (`entity_graph.py:40`).
- Fix `_capture_analytics` N+1 (`sync_engine.py:5874–5960`); materialize session badge metadata; add FTS5 on
  `session_messages.content`.
- Reconcile SQLite(27)/Postgres(28) schema version (`sqlite_migrations.py:16`); move `entity_links` UNIQUE into
  initial Postgres DDL (`postgres_migrations.py:1491–1498`).

### 5.3 Caching — **Phase 2 (Cache & Query Correctness)**

- Shared cache (Valkey for enterprise, Postgres-cache fallback for single-node) replacing `TTLCache` singleton
  (`cache.py:50`).
- Add `project_id` to `entity_links` and project-scope + cache the fingerprint (`cache.py:258–289`).
- Sync-triggered invalidation: call project-scoped eviction after `sync_project()` (`routers/cache.py:363–424`).
- Summary/detail endpoint split + column projection (replace `SELECT *` `list_all`); parallelize bundle
  sub-calls with `asyncio.gather` (`completed-and-gaps.md` backend-api GAPs).
- Enforce per-metric TTLs; raise `maxsize` (512→2048+); extend warming beyond 2/14 endpoints; precompute the
  planning graph in DB via the worker.

### 5.4 Workers / multi-project — **Phase 3 (DB-backed Registry & Multi-Project Worker)**

- `projects` table replacing `projects.json` (`project_manager.py:287`); `_OQ_OVERLAY` → DB.
- Per-project `FileWatcher` registry (dict-keyed) replacing the singleton (`file_watcher.py:307`); support
  "watch all registered projects" in one worker AND keep one-container-per-project as a valid isolation
  deployment.
- Durable task queue + supervision (detect dead task → `dead` not `idle`) (`runtime.py:385–420`).
- Multi-project analytics/warming loop iterating `workspace_registry.list_projects()` (`runtime.py:794–799`).
- Session PK isolation `(project_id, id)`; add `project_id` to detail tables; `rebind_watcher` mutex
  (`multi-project.md` §3, §6).
- Read `CCDASH_WORKER_WATCH_PROJECT_ID` / `_STARTUP_SYNC_ENABLED` in `config.py` (`workers-runtime.md` issues).

### 5.5 Frontend + command center — **Phases 4–5**

Out of scope for this gap analysis's depth (see docs 04 and the command-center deliverable), but the contract
gaps that block enterprise are: migrate V1 command center to TQ, server pagination + virtualization on the
session board, kill `setInterval` sprawl, make `useData` reactive, runtime capability flag for multi-project
(replacing the build-time `VITE_CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED`), `tokenUsageByModel` on
`Feature`, move the Gemini key server-side, self-host fonts.

### 5.6 Observability & validation — **Phase 6**

OTEL gaps (`_capture_analytics` duration histogram, live-fanout latency instruments), scheduled
retention/VACUUM, skillmeat-scale load test, container e2e CI gate.

---

## 6. Comprehensive Gap Table

Status legend: **works** = shipped and correct; **partial** = shipped with a documented gap; **broken** =
shipped but defective; **missing** = not implemented. Priority: **P0** = blocks enterprise usability now;
**P1** = blocks scale/correctness; **P2** = polish/hardening. Phase = synthesis §7 roadmap phase.

### 6.1 Container topology & ingestion liveness (§2 headline)

| Capability | Status | Evidence (file:line) | Required change | Priority | Phase |
|---|---|---|---|---|---|
| Enterprise filesystem ingestion default | broken | `config.py:244–246`; `compose.yaml:27` | Flip default on / fold live-watch into default topology | P0 | 0 |
| Worker startup sync default | broken | `compose.yaml:133`; `config.py:961` | Default `CCDASH_WORKER_STARTUP_SYNC_ENABLED=true` for enterprise worker | P0 | 0 |
| `live-watch` in default command | missing | `compose.yaml:159–193`; `container-deploy.md` §6 | Include watcher in default enterprise topology | P0 | 0 |
| Container path alias auto-derivation | missing | `providers/filesystem.py:25–28`; `source_identity.py:271–308` | Populate aliases from `ResolvedProjectPaths` at sync construction | P0 | 0 |
| `readyz` fail on zero watch paths | broken | `file_watcher.py:108–112,252–266` | `readyz` FAILS when watch_paths == 0 | P0 | 0 |
| `WATCHFILES_FORCE_POLLING` default | broken | `compose.yaml:175`; `file_watcher.py:183` | Default `true` for worker-watch on bind mounts | P0 | 0 |
| `projects.json` read-only + `_save()` crash | broken | `compose.yaml:48`; `project_manager.py:140–146` | Mount RW or DB-back; atomic write | P0 | 0 |
| Container e2e smoke test | missing | `ingestion-fs.md` GAP | CI `docker compose up` asserting sessions appear | P0 | 0 |
| Startup warning: enterprise + ingestion off + empty DB | missing | `multi-project.md` Gap 4 | Fail-loud actionable error/log | P0 | 0 |

### 6.2 Container topology defects (§3)

| Capability | Status | Evidence (file:line) | Required change | Priority | Phase |
|---|---|---|---|---|---|
| `frontend depends_on: api` | broken | `compose.yaml:195–217` | Add health-gated dependency | P1 | 0 |
| `entrypoint.sh` worker-watch case | broken | `entrypoint.sh:10–24` | Add `worker-watch` dispatch | P1 | 0 |
| `compose.hosted.yml` parity | broken | `container-deploy.md` §9 | Add mounts, `WORKER_PROJECT_ID`, user hardening; or deprecate | P1 | 0 |
| Migration advisory lock | missing | `container.py:106–108` | `pg_try_advisory_lock` around `run_migrations` | P1 | 0 |
| CORS localhost-always | broken | `bootstrap.py:57–66` | Gate localhost behind dev flag | P1 | 0 |
| `CCDASH_PROJECTS_FILE` dead var | broken | `config.py` (unread) | Wire into `ProjectManager.__init__` or remove | P2 | 0 |
| Watcher delete canonical key | broken | `sync_engine.py:3944` vs `4171` | Use `_canonical_source_key` in watcher delete | P1 | 1 |
| `WORKER_WATCH_PROJECT_ID` Python config | broken | `compose.yaml:166`; absent in `config.py` | Read in `config.py` for k8s/bare-container | P1 | 3 |
| Module-level orphaned container | broken | `bootstrap_worker.py:86` | Lazy-construct at call time | P2 | 3 |
| Postgres NOTIFY reconnect/backoff | broken | `postgres_listener.py` (FU-2) | Exponential backoff + supervisor reconnect | P1 | 6 |
| FU-004 bootstrap test skips | broken | `test_runtime_bootstrap.py:616,680,716,1057,1333` | Unskip; verify against `bootstrap.py:176,224` | P2 | 6 |

### 6.3 Database / storage hygiene

| Capability | Status | Evidence (file:line) | Required change | Priority | Phase |
|---|---|---|---|---|---|
| `analytics_entries` retention | missing | `analytics.py` (no prune); `database.md` §2c | 90-day TTL job (~50× reduction) | P1 | 1 |
| `telemetry_events.payload_json` TTL | missing | `sqlite_migrations.py:500–542` | TTL/compression/offload (1.6 GB) | P1 | 1 |
| `session_logs`/`session_messages` dedupe | broken | `sqlite_migrations.py:192–225` | Drop duplicate logs after canonical messages (~1.75 GB) | P1 | 1 |
| `idx_sessions_project_status_updated` | broken | `sqlite_migrations.py:161–162,1362–1367` | `_ensure_index` backfill on existing DBs | P1 | 1 |
| `idx_sessions_source_file` | missing | `repositories/sessions.py:161–167` | Add index (file-watch full-scan) | P1 | 1 |
| analytics partial index `period='point'` | missing | `database.md` §7 | Add partial index | P2 | 1 |
| SQLite pragmas (cache_size/synchronous) | missing | `connection.py:52–54` | `cache_size≥32768`, `synchronous=NORMAL` | P1 | 1 |
| `_capture_analytics` N+1 | broken | `sync_engine.py:5874–5960` | Batch task/link/session loads | P1 | 1 |
| `entity_graph.upsert()` per-link commit | broken | `entity_graph.py:40` | Single-transaction batch upsert | P1 | 1 |
| `executemany` batch inserts | missing | `perf-evidence.md` GAP | Batch telemetry/attribution/log writes | P1 | 1 |
| Session badge materialization | missing | `completed-and-gaps.md` backend-api GAP | Materialize models/agents/skills on `sessions` | P1 | 1 |
| FTS5 on `session_messages.content` | missing | `perf-evidence.md` GAP | FTS5 virtual table | P2 | 1 |
| Postgres `upsert_logs` transaction | broken | `postgres/sessions.py:88+` | Wrap DELETE+INSERT in `_transactions.py` helper | P1 | 1 |
| `entity_links` UNIQUE in initial DDL | broken | `postgres_migrations.py:1491–1498` | Move UNIQUE into `_TABLES` | P1 | 1 |
| SQLite(27)/Postgres(28) version mismatch | broken | `sqlite_migrations.py:16`; `postgres_migrations.py:11` | Reconcile; resolve `source_ref` drift | P2 | 1 |
| Manifest-based session scan skip | missing | `sync_engine.py:4107–4119` | Inode/mtime manifest like documents | P2 | 1 |
| Scheduled VACUUM/ANALYZE | missing | `perf-evidence.md` GAP | Periodic worker job | P2 | 6 |

### 6.4 Caching & query correctness

| Capability | Status | Evidence (file:line) | Required change | Priority | Phase |
|---|---|---|---|---|---|
| Shared distributed cache | missing | `cache.py:50`; `caching.md` CRITICAL | Valkey (or Postgres-cache fallback) | P0 | 2 |
| API-container cache warming | broken | `profiles.py:41–52` (`jobs=False`); `runtime.py:192` | Warm via shared cache from worker | P1 | 2 |
| `entity_links` fingerprint project-scope | broken | `cache.py:258–289`; `sqlite_migrations.py:37–56` | Add `project_id`; scope + cache fingerprint | P1 | 2 |
| Fingerprint caching | missing | `cache.py:84–142` | Cache fingerprint with 5–10s TTL | P1 | 2 |
| Per-metric TTL enforcement | broken | `cache.py:50`; `config.py:987–1023` | Per-prefix TTL buckets | P1 | 2 |
| Sync-triggered invalidation | missing | `routers/cache.py:363–424`; `planning.py:1567` | Evict project keys after `sync_project()` | P1 | 2 |
| Project-scoped eviction | missing | `cache.py:73–79` (full clear) | Selective `*:{project_id}:*` eviction | P2 | 2 |
| `maxsize=512` for multi-project | partial | `cache.py:50` | Raise to 2048+ (interim) / unbounded shared | P2 | 2 |
| Warming coverage (2/14 endpoints) | partial | `runtime.py:840–982` | Add summary/dashboard/analytics endpoints | P2 | 2 |
| Legacy `/api/features` uncached + 5s poll | broken | `features.py:837`; `services/queries/features.ts:85` | `@memoized_query` + staleTime 30s | P1 | 2 |
| `feature_phases` fingerprint O(N) GROUP_CONCAT | broken | `cache.py:195–255` | Replace with `MAX(updated_at)+COUNT(*)` | P2 | 2 |
| Bundle parallel sub-calls | missing | `completed-and-gaps.md` backend-api GAP | `asyncio.gather` + shared data pass | P1 | 2 |
| `SELECT *` `list_all` column projection | broken | `completed-and-gaps.md` backend-api GAP | `list_summary` projected variants | P1 | 2 |

### 6.5 Multi-project & worker orchestration

| Capability | Status | Evidence (file:line) | Required change | Priority | Phase |
|---|---|---|---|---|---|
| DB-backed project registry | missing | `project_manager.py:287`; `multi-project.md` §1 | `projects` table | P0 | 3 |
| Per-project FileWatcher registry | missing | `file_watcher.py:307`; singleton | Dict-keyed watcher registry / watch-all | P1 | 3 |
| Durable task queue | missing | `local.py:8–10` | Redis/Postgres-backed queue + retry | P1 | 3 |
| Task supervision (idle vs dead) | broken | `runtime.py:385–420` | Watchdog; report `dead`/`failed` | P1 | 3 |
| Multi-project analytics/warming loop | broken | `runtime.py:794–799,894–895` | Iterate `list_projects()` | P1 | 3 |
| Session PK project isolation | broken | `repositories/sessions.py:20–87` | `(project_id, id)` PK / conflict | P1 | 3 |
| `project_id` on detail tables | missing | `multi-project.md` §3 | Add column to logs/tools/files/artifacts | P1 | 3 |
| Active-project global fallback removal | broken | `common.py:93–120` step 4 | Fail-fast headerless requests in enterprise | P1 | 3 |
| `rebind_watcher` mutex | missing | `multi-project.md` §6 | `asyncio.Lock` for multi-operator | P2 | 3 |
| `_OQ_OVERLAY` persistence | broken | `planning.py:1567`; synthesis §4 | Move OQ resolutions to DB | P1 | 3 |
| TQ invalidation on project switch | partial | `AppSessionContext.tsx`; `multi-project.md` §9 | `invalidateQueries` after `setApiProjectScope` | P2 | 4 |

### 6.6 Data contracts & command center

| Capability | Status | Evidence (file:line) | Required change | Priority | Phase |
|---|---|---|---|---|---|
| SkillMeat artifact intelligence | works | snapshot/ranking/recommendation/rollup tables | — | — | — |
| Planning DTOs (item/board/context/phase-ops) | works | `planning.py`; `planning_command_center.py`; `planning_sessions.py` | — | — | — |
| `tokenUsageByModel` on `Feature` | missing | `data-contracts.md`; synthesis §4 | Add field; wire `PlanningTokenTelemetry.source` | P1 | 5 |
| `Feature.data_json` BLOB → SQL filtering | broken | `data-contracts.md` GAP | Promote tags/owners/phases to columns | P1 | 5 |
| Cross-project token/cost aggregate | missing | `ProjectWorkItemCounts`; `data-contracts.md` | Add aggregate to MPCC rollups | P1 | 5 |
| Ranked "next work" backlog endpoint | missing | `data-contracts.md` GAP | Priority-ordered execution queue | P2 | 5 |
| Multi-project runtime capability flag | partial | `constants.ts:399–421` build-time flag | Runtime capability endpoint | P1 | 5 |
| Deep-linkable feature detail route | missing | synthesis §5 | `/planning/feature/:id` + modal | P2 | 5 |
| PR status live | missing | `data-contracts.md` GAP | GitHub API live status | P2 | 5 |
| ARC council / MeatyWiki integrations | missing | `data-contracts.md` GAPs; synthesis §4 | Scaffold behind capability flags | P2 | 5 |
| Planning graph DB precompute | missing | `data-contracts.md` GAP | Worker-precomputed graph cache | P2 | 2 |

### 6.7 Frontend performance

| Capability | Status | Evidence (file:line) | Required change | Priority | Phase |
|---|---|---|---|---|---|
| `useData` reactive subscription | broken | `completed-and-gaps.md` frontend-core GAP | `useQuery` not `getQueryData` snapshot | P1 | 4 |
| V1 command center on TQ | broken | `planning-frontend` GAP | Migrate raw `useEffect` to TQ | P1 | 4 |
| Server pagination/virtualization (V1 board) | missing | `planning-frontend` GAP | Cursor pagination + virtual list | P1 | 4 |
| `setInterval` sprawl | broken | `frontend-core` GAP (8+ components) | TQ `refetchInterval`/SSE invalidation | P1 | 4 |
| `features` 5s refetchInterval | broken | `services/queries/features.ts:85` | 30s minimum when SSE off | P1 | 4 |
| `useFeatureSurface` list `staleTime:0` | broken | `useFeatureSurface.ts:348` | 10–30s staleTime | P2 | 4 |
| Dashboard KPI TQ migration | broken | `dashboard-kpi-tq-migration.md` (in-progress) | Migrate to `useAnalyticsOverviewQuery` | P1 | 4 |
| `AnalyticsDashboard` outside TQ | broken | `frontend-core` GAP (7 raw fetches) | Migrate to TQ | P2 | 4 |
| Viewport-deferred mounting | missing | `planning-frontend` GAP | Defer board/command-center mount | P2 | 4 |
| `GEMINI_API_KEY` in Vite bundle | broken | `frontend-core` GAP | Move server-side | P1 | 4 |
| Self-hosted fonts | missing | `planning-frontend` GAP | Eliminate Google Fonts CDN | P2 | 4 |

### 6.8 Observability & ops

| Capability | Status | Evidence (file:line) | Required change | Priority | Phase |
|---|---|---|---|---|---|
| OTEL hit/miss + sync latency | works | `otel.py:327–332,430,934–944` | — | — | — |
| Worker probe rich job state | works | `bootstrap_worker.py:31–67`; `runtime.py:385–420` | — | — | — |
| `_capture_analytics` duration histogram | missing | `perf-evidence.md` GAP | Add OTEL histogram | P2 | 6 |
| Live-fanout latency instruments (FU-5) | missing | `completed-and-gaps.md` completed-work | `ccdash_live_fanout_*` metrics | P2 | 6 |
| "Stale since" threshold alarm | missing | `workers-runtime.md` §Missing | Probe-contract staleness alarm | P2 | 6 |
| Wire-boundary SSE smoke test (FU-4) | missing | `completed-and-gaps.md` | Real-browser SSE path test | P2 | 6 |
| skillmeat-scale load test | missing | synthesis §6.2 | Container e2e load gate | P1 | 6 |

---

## 7. Bottom Line

The CCDash enterprise edition is **finishable, not rewritable**. The headline container failure (§2) is a
**three-defect compounding wiring bug** — disabled-by-default ingestion, unresolvable host paths with a
silent-pass readiness probe, and dead inotify plus a read-only write crash — all addressable in **Phase 0**
with defaults, path-alias derivation, a fail-loud `readyz`, and a CI smoke gate, introducing **no new
subsystems**. Everything beyond it is the well-understood scale work of Phases 1–6: storage retention,
batch/index fixes, a shared cache, a DB-backed project registry with multi-project workers, and the
command-center control-plane finish. The architecture decisions are settled (synthesis §6); this document is
the evidence-backed gap inventory those decisions resolve.
