# CCDash Enterprise Edition — Completed Work Audit

**Domain:** completed-work  
**Date:** 2026-05-30  
**Investigator:** Claude (subagent, Sonnet 4.6)  
**Scope:** Ground-truth status of all prior efforts relevant to enterprise/perf readiness.  

---

## Methodology

All claims are derived from reading:
- PRD frontmatter (`status`, `summary`) in `docs/project_plans/PRDs/`
- Phase progress YAML frontmatter (`status`, `overall_progress`, `tasks[]`) in `.claude/progress/`
- Key implementation artifacts on disk (compose files, Dockerfiles, entrypoint, code files)
- Quick-feature follow-up files in `.claude/progress/quick-features/`
- Post-implementation review reports in `docs/project_plans/reports/`

Status legend: **COMPLETED** = all phases 100%, code verified on disk; **PARTIAL** = all phases marked completed but outstanding follow-ups or known code gaps remain; **IN-PROGRESS** = one or more phases still open; **SAFE-TO-BUILD-ON** / **RISKY** per cross-effort dependencies.

---

## 1. Infrastructure / Deployment

### 1.1 containerized-deployment-v1

**PRD:** `docs/project_plans/PRDs/infrastructure/containerized-deployment-v1.md`  
**Progress dir:** `.claude/progress/containerized-deployment-v1/` — all 7 phases `completed`  
**Status: COMPLETED with known skipped tests**

**What shipped:**
- Single multi-stage `Dockerfile` at `deploy/runtime/Dockerfile` (builder + runtime, non-root `ccdash:ccdash` user, `ARG BUILD_UID/BUILD_GID`)
- Entrypoint at `deploy/runtime/entrypoint.sh` — dispatches `local | api | worker` via `CCDASH_RUNTIME_PROFILE`
- `deploy/runtime/compose.yaml` — profiles: `local`, `local-sqlite`, `enterprise`, `live-watch` (worker-watch service)
- `deploy/runtime/compose.hosted.yml` — full stack with separate `api`, `worker`, `frontend`, `postgres` services using per-subdirectory Dockerfiles (`deploy/runtime/api/`, `deploy/runtime/worker/`, `deploy/runtime/frontend/`)
- `deploy/runtime/compose.external-postgres.yaml` — `!reset` workaround for `podman-compose 1.5.0` not honoring `required: false` on `depends_on`
- Frontend image trimmed to under 50 MB target

**Outstanding / Risks:**
- **CRITICAL GAP (FU-004):** 5 test classes/methods in `backend/tests/test_runtime_bootstrap.py` are permanently skipped with `@unittest.skip("FU-004: production drift…")` decorators at lines 616, 680, 716, 1057, 1333. The skip messages claim `_build_health_payload` drops `authGuardrail` and `probeDetailWarningCodes`, but the live code at `backend/runtime/bootstrap.py:176,224` **does** emit those fields. The skip decorators were added as remediation and never re-evaluated. One additional test at line 1333 skips the entire `RuntimeBootstrapLifecycleTests` class due to a macOS subprocess leak in `test_worker_process_starts_without_http_server`. This class covers worker lifecycle boot.
- **ENTRYPOINT GAP:** `deploy/runtime/entrypoint.sh` handles only `local | api | worker`. The `worker-watch` profile (`CCDASH_RUNTIME_PROFILE=worker-watch`) falls through to the `*)` error case and prints: `Unsupported CCDASH_RUNTIME_PROFILE: 'worker-watch'`. The `compose.yaml` `worker-watch` service works around this by overriding `command: ["python", "-m", "backend.worker"]` — bypassing the entrypoint entirely. This is an inconsistency: operators using the entrypoint directly or the `compose.hosted.yml` path cannot launch worker-watch without the override.

**Safe to build on:** YES, with the caveat that `worker-watch` requires compose override, and bootstrap test coverage is sparse due to FU-004 skips.

---

### 1.2 deployment-runtime-modularization-v1

**PRD:** `docs/project_plans/PRDs/refactors/deployment-runtime-modularization-v1.md` — `status: completed`  
**Progress dir:** `.claude/progress/deployment-runtime-modularization-v1/` — all 6 phases `completed`, `overall_progress: 100`  
**Status: COMPLETED**

**What shipped:**
- `RuntimeProfileName = Literal["local", "api", "worker", "worker-watch", "test"]` at `backend/runtime/profiles.py:7`
- `RuntimeCapabilities` dataclass defining `watch`, `sync`, `jobs`, `auth`, `integrations` booleans per profile
- `RuntimeStorageContract` per profile in `backend/runtime/storage_contract.py`
- Separate bootstrap modules: `bootstrap_local.py`, `bootstrap_api.py`, `bootstrap_worker.py`, `bootstrap_test.py`
- Worker probe FastAPI app (`/livez`, `/readyz`) in `bootstrap_worker.py`
- Health reporting and readiness gates wired per profile

**Safe to build on:** YES — this is the authoritative runtime dispatch layer.

---

### 1.3 data-platform-modularization-v1

**PRD:** `docs/project_plans/PRDs/refactors/data-platform-modularization-v1.md` — `status: completed`  
**Progress dir:** `.claude/progress/data-platform-modularization-v1/` — all 6 phases `completed`; phases 1–2 show `overall_progress: 90` due to an unrelated `pnpm typecheck` baseline failure at time of completion  
**Status: COMPLETED (minor progress note lag)**

**What shipped:**
- Storage profile capability contract (`local` vs `enterprise` vs `shared-enterprise`) in `backend/config.py`
- `backend/data_domains.py` — domain classification for canonical vs derived data
- Runtime/storage combination contracts and validation in `backend/runtime/storage_contract.py`
- Schema governance patterns and `docs/guides/data-domain-ownership-matrix.md`
- Additive canonical session tables and Postgres-ready placeholders (phases 3–4)
- Migration governance and sync boundary refactor (phase 5)

**Safe to build on:** YES — the capability/profile contract is the foundation for enterprise DB selection.

---

## 2. Live Ingest / SSE Platform

### 2.1 sse-live-update-platform-v1

**PRD:** `docs/project_plans/PRDs/enhancements/sse-live-update-platform-v1.md`  
**Progress:** `.claude/progress/sse-live-update-platform-v1/` — 2 phases, both `completed`  
**Status: COMPLETED**

**What shipped:**
- In-memory live event broker (`backend/adapters/live_updates/in_memory_broker.py`)
- `GET /api/live/stream` SSE endpoint with topic subscription, heartbeats, disconnect cleanup (`backend/routers/live.py`)
- `LiveEventBroker`, `LiveEventPublisher`, `BrokerLiveEventPublisher` contracts
- Frontend `useLiveInvalidation` hook in `services/live/`

---

### 2.2 enterprise-live-session-ingest-v1

**PRD:** `docs/project_plans/PRDs/enhancements/enterprise-live-session-ingest-v1.md` — `status: draft` (PRD not updated post-completion)  
**Progress:** `.claude/progress/enterprise-live-session-ingest-v1/` — all 5 phases `completed`, `overall_progress: 100`  
**Status: COMPLETED with outstanding surgical follow-ups**

**What shipped:**
- `worker-watch` runtime profile with `watch=True`, `sync=True`, `jobs=True` capability flags (`backend/runtime/profiles.py:65`)
- `RuntimeStorageContract` for `worker-watch` at `backend/runtime/storage_contract.py:171`
- `PostgresNotifyLiveEventBus` + `PostgresNotifyLiveEventPublisher` (worker-side, publishes via `NOTIFY`)
- `PostgresNotifyLiveEventBus` listener (api-side, subscribes via `LISTEN`) at `backend/adapters/live_updates/postgres_listener.py`
- `InMemoryLiveEventBroker` with configurable replay buffer (`CCDASH_LIVE_REPLAY_BUFFER_SIZE`)
- Container wiring in `backend/runtime/container.py:111–118`
- `CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED` env var in `backend/config.py:246,581`
- Compose profile `live-watch` with `worker-watch` service in `deploy/runtime/compose.yaml:159`

**Outstanding (per `.claude/progress/quick-features/live-ingest-review-followups.md`, `status: in-progress`):**
- **FU-2 (DEFERRED):** Postgres NOTIFY listener has no reconnect/exponential backoff logic (`backend/adapters/live_updates/postgres_listener.py` — confirmed empty on search). A transient DB disconnect permanently breaks live ingest until container restart.
- **FU-4 (DEFERRED):** No real wire-boundary smoke test for `SessionInspector` SSE path; only unit-level coverage.
- **FU-1 (CODE DONE, DOC unclear):** `compose.yaml:187` healthcheck reads `CCDASH_WORKER_WATCH_PROBE_PORT` correctly.
- **FU-3 (UNVERIFIED):** Publish exception isolation audit for `LiveEventBus.publish()` call sites — grep confirms no try/except at `backend/db/sync_engine.py` call sites.
- **FU-5 (UNVERIFIED):** OTel instruments for fanout + watcher latency (`ccdash_live_fanout_publish_latency_ms` etc.) not confirmed present.
- **FU-7 (UNVERIFIED):** `_COMPACT_PAYLOAD_KEYS` extension contract documentation not confirmed.

**Safe to build on:** CONDITIONALLY YES — core plumbing works, but no reconnect backoff means production resilience is fragile.

---

### 2.3 live-ingest-source-path-canonicalization-hardening-v1

**Progress:** `.claude/progress/live-ingest-source-path-canonicalization-hardening-v1/` — all 5 phases `completed`  
**Status: COMPLETED**

**What shipped:**
- Source identity contract and canonical path normalization for session JSONL paths
- Duplicate migration and backfill (phase 3)
- Runtime guardrails preventing duplicate ingestion on alias paths
- Performance validation: stable CPU/memory after 10-minute watcher idle

**Safe to build on:** YES — prerequisite for reliable enterprise ingest.

---

### 2.4 session-transcript-append-deltas-v1

**Progress:** `.claude/progress/session-transcript-append-deltas-v1/` — all 5 phases `completed`  
**Status: COMPLETED**

**What shipped:**
- Canonical transcript repository with message-level storage
- Append-delta ingestion (only new JSONL lines reprocessed on file change)
- Frontend delta application via SSE events

---

## 3. Backend Performance / Caching

### 3.1 db-caching-layer-v1

**Progress:** `.claude/progress/db-caching-layer-v1/` — only phases 3–4 present (phases 1–2 predate progress file system or were merged into hexagonal-foundation)  
**Status: COMPLETED (phases 3–4 cover modern session storage)**

**What shipped (phases 3–4):**
- Canonical transcript repository and compatibility read seam (`DB-P3-01`)
- Transcript ordering, provenance, root-session lineage, conversation-family IDs (`DB-P3-02`)
- Additive canonical session tables and future-fact placeholders for Postgres (`DB-P3-03`)

---

### 3.2 ccdash-query-caching-and-cli-ergonomics-v1

**PRD:** `docs/project_plans/PRDs/enhancements/ccdash-query-caching-and-cli-ergonomics-v1.md`  
**Progress:** `.claude/progress/ccdash-query-caching-and-cli-ergonomics/` — 5 phases + phases 2.5 and 3.5, all `completed`  
**Status: COMPLETED**

**What shipped:**
- `@memoized_query` decorator at `backend/application/services/agent_queries/cache.py:328` — wraps async service methods with TTL-based `TTLCache(maxsize=512)` keyed by project+params
- Default TTL `CCDASH_QUERY_CACHE_TTL_SECONDS` changed to 600s (was 60s) in `backend/config.py:978`
- Background warm interval `CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS`
- `--no-cache` CLI flag and `CCDASH_TIMEOUT` env var
- `POST /api/cache/invalidate` endpoint

**Safe to build on:** YES — this is the primary query acceleration layer.

---

### 3.3 runtime-performance-hardening-v1

**PRD:** `docs/project_plans/PRDs/infrastructure/runtime-performance-hardening-v1.md`  
**Progress:** `.claude/progress/runtime-performance-hardening-v1/` — all 6 phases `completed`  
**Status: COMPLETED**

**What shipped:**
- Frontend transcript ring-buffer cap (5000 rows max; `transcriptTruncated` marker) — `contexts/dataContextShared.ts:61`
- `react-virtual` log list virtualization (`FE-102`)
- `MAX_DOCUMENTS_IN_MEMORY` (2000) with lazy-load beyond cap (`FE-103`)
- Link rebuild dedup and throttling (phase 2)
- `CCDASH_QUERY_CACHE_TTL_SECONDS` default bumped to 600s (phase 3, overlaps with query-caching PRD)
- `VITE_CCDASH_MEMORY_GUARD_ENABLED` flag wired in `contexts/__tests__/transcriptRingBuffer.test.ts`
- OTel instrumentation pass (phase 4)

**Safe to build on:** YES.

---

## 4. Frontend Data Layer

### 4.1 ccdash-frontend-data-layer-refactor (TanStack Query migration)

**PRD:** `docs/project_plans/PRDs/refactors/ccdash-frontend-data-layer-refactor-v1.md` — `status: draft` (stale; implementation is complete)  
**Progress:** `.claude/progress/ccdash-frontend-data-layer-refactor/` — all 8 phases (0–7) `completed`, `overall_progress: 100`  
**Status: COMPLETED with one outstanding bug (dashboard-kpi-tq-migration)**

**What shipped:**
- TanStack Query `QueryClient` provider wrapping the app
- Domain query hooks in `services/queries/` (sessions, features, analytics, documents, tasks, planning, projects, health)
- Query key registry at `services/queryKeys.ts`
- `backend/application/services/agent_queries/` bundle endpoints for Planning, Analytics, Feature Surface
- Hand-rolled LRU/featureCacheBus caches REMOVED (phase 3)
- Eager-load removal from `AppEntityDataContext` (phase 4 — renamed/split)
- Backend fat-read bundles collapsing N+1 waterfall calls (phase 5)
- `react-virtual` list virtualization (phase 6)
- 176 guardrail tests green (commit `6c91218`)
- Legacy `getFeatures()` moved to 100-row default (`services/apiClient.ts:421–423`); note: was 5000-row

**Outstanding:**
- **DASHBOARD KPI MIGRATION (in-progress):** `.claude/progress/quick-features/dashboard-kpi-tq-migration.md` — `status: in_progress`. `components/Dashboard.tsx` was NOT migrated to `useAnalyticsOverviewQuery`; it still calls the legacy `getOverview()` imperative path which takes 20.5s cold / 9.7s warm. KPI cards show literal `0` while in-flight (no loading skeleton), and an aborted request permanently shows zeros. Tasks T0-001, T0-002, T0-003 are all `pending`.
- **RUNTIME SMOKE SKIPPED (T7-002):** Phase 7 runtime smoke was substituted with vitest; the note says `runtime_smoke: SKIPPED (headless bg exec)`. Dashboard, Analytics, Planning cross-surface rendering was not browser-validated.

**Safe to build on:** YES for the refactored surfaces. Dashboard remains a pre-refactor regression.

---

### 4.2 feature-surface-data-loading-redesign-v1

**PRD:** `docs/project_plans/PRDs/refactors/feature-surface-data-loading-redesign-v1.md` — `status: completed`  
**Progress:** `.claude/progress/feature-surface-data-loading-redesign-v1/` — all 6 phases `completed`  
**Status: COMPLETED with documented partial gap**

**What shipped:**
- Backend v1 endpoints: feature card list, rollups, modal overview/sections, paginated session pages
- `useFeatureSurface` hook replacing per-card linked-session calls
- `ProjectBoard` renders from `surfaceCards` and `surfaceRollups` (not session-summary loop)
- Modal lazy section loading by active tab
- SQLite + Postgres repository parity for feature queries

**Documented gap (per `docs/project_plans/reports/feature-surface-data-loading-redesign-review-2026-04-24.md`):**
- Global feature provider `getFeatures()` was not fully retired — the review confirms the legacy full-feature-list path was reduced from 5000 to 100 rows but the provider-level refresh still exists in the app shell. This is partially mitigated but not closed.

**Safe to build on:** YES for ProjectBoard and modal paths. App-shell global refresh still runs.

---

## 5. Planning / Command Center

### 5.1 ccdash-planning-control-plane-v1

**PRD:** `docs/project_plans/PRDs/enhancements/ccdash-planning-control-plane-v1.md` — `status: completed`  
**Progress:** `.claude/progress/ccdash-planning-control-plane-v1/` — all 8 phases `completed`, `overall_progress: 100`  
**Status: COMPLETED**

**What shipped:**
- Planning graph derived state (`/api/agent/planning/*` endpoints)
- `PlanningHomePage`, `PlanningGraphPanel`, `TrackerIntakePanel`, `PlanningSummaryPanel`, `PlanningAgentSessionBoard`
- `PlanningNextRunPreview`, `PlanningLaunchSheet`, `PlanningQuickViewPanel`
- Phase operations integration
- Planning reskin (v2 + interaction/performance addendum — separate progress dirs, all phases completed)

---

### 5.2 planning-command-center-v1

**PRD:** `docs/project_plans/PRDs/enhancements/planning-command-center-v1.md` — `status: draft` (PRD not updated post-completion)  
**Progress dir:** DOES NOT EXIST (no `.claude/progress/planning-command-center-v1/`)  
**Implementation plan:** `docs/project_plans/implementation_plans/enhancements/planning-command-center-v1.md` — `status: completed`  
**AAR:** `docs/project_plans/reports/planning-command-center-v1-aar-2026-05-29.md`  
**Status: COMPLETED (PRD status stale)**

**What shipped (from AAR and code inspection):**
- `GET /api/agent/planning/command-center` and `GET /api/agent/planning/command-center/{feature_id}` endpoints in `backend/application/services/agent_queries/planning_command_center.py`
- `services/planningCommandCenter.ts` frontend service
- `PlanningCommandCenter.tsx` with list/card/board views + `CommandCenterDetailPanel`, `CommandCenterToolbar`
- `WorktreeGitStatePanel`, `RelatedFilesPicker`, `QuickCommandBar`, `EditableCommandField`
- `PlanningLaunchSheet` integration (launch + PR/review affordances)
- Embedded in `PlanningHomePage` at lines 842 and 1057 via `PlanningCommandCenterShell`
- Commits: `d903b55`, `1cfc537`, `3847ca1`, `baa6ce2`, `645e1b7`

---

### 5.3 multi-project-planning-command-center-v1

**PRD:** `docs/project_plans/PRDs/enhancements/multi-project-planning-command-center-v1.md` — `status: completed`  
**Progress:** `.claude/progress/multi-project-planning-command-center-v1/` — all 7 phases `completed`, `overall_progress: 100`  
**Status: COMPLETED — feature-flagged, OFF by default**

**What shipped:**
- `MultiProjectCommandCenter.tsx` with `MultiProjectFilterRail`, `MultiProjectSessionBoard`, `MultiProjectWorkItemCard`, `MultiProjectDetailRail`
- Backend `multi_project_planning_command_center.py` and `multi_project_planning_sessions.py` in agent_queries layer
- Aggregate DTOs (`AggregateSessionCard`, `AggregateWorkItem`, `ProjectWarning`) in `backend/models.py:3367` and `types.ts:3796`
- `MULTI_PROJECT_COMMAND_CENTER_ENABLED` feature flag at `constants.ts:395–421` — **defaults to `false`**
- `PlanningCommandCenterShell` wrapper gating single vs multi mode (`components/Planning/CommandCenter/PlanningCommandCenter.tsx:43`)
- `useMultiProjectCommandCenterQuery` and `useMultiProjectSessionBoardQuery` TQ hooks in `services/queries/planning`

**Risk:** Feature flag is `false` by default. Operators must set `VITE_CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED=true` to activate. No route-level access point other than the mode toggle inside `/planning`.

---

### 5.4 Overlap: planning-command-center-v1 vs multi-project-planning-command-center-v1

These are NOT overlapping implementations — they are a proper parent/child lineage. The multi-project PRD explicitly cites planning-command-center-v1 as `lineage_parent`. The shell (`PlanningCommandCenterShell`) gates between them via feature flag. There is no duplicate code risk, but the PRD status drift (planning-command-center-v1 still says `draft`) creates confusion.

---

## 6. Auth / RBAC

### 6.1 shared-auth-rbac-sso-v1

**Progress:** `.claude/progress/shared-auth-rbac-sso-v1/` — phases 2–7 `completed` (phase 1 presumably pre-dates progress tracking)  
**Status: COMPLETED**

**What shipped:**
- RBAC middleware and bearer token auth wired to `api` runtime profile
- `CCDASH_API_BEARER_TOKEN` env var required for enterprise
- Auth guardrail surfaced in health endpoint (`authGuardrail.mode`, `bearerProtectedPathPrefix`)
- Commits: `68c6cdb`, `3799316`, `d42ef27`

---

## 7. Supporting Features

### 7.1 ccdash-hexagonal-foundation-v1

**Progress:** `.claude/progress/ccdash-hexagonal-foundation-v1/` — all 6 phases `completed`  
**Status: COMPLETED — foundational prerequisite for all subsequent refactors**

### 7.2 planning-forensics-boundary-extraction-v1

**Progress:** `.claude/progress/planning-forensics-boundary-extraction-v1/` — all 6 phases `completed`  
**Status: COMPLETED**

### 7.3 ccdash-query-caching-and-cli-ergonomics (db-caching-layer overlap)

Both `ccdash-query-caching-and-cli-ergonomics` and `runtime-performance-hardening-v1` (phase 3) shipped the same default TTL change (`CCDASH_QUERY_CACHE_TTL_SECONDS = 600`). This is a benign duplicate — same value, same config variable, no conflict.

---

## 8. Critical Open Work (Not Completed)

| Item | Status | File |
|------|--------|------|
| Dashboard KPI TanStack Query migration | IN-PROGRESS | `.claude/progress/quick-features/dashboard-kpi-tq-migration.md` |
| Live ingest review follow-ups (FU-2, FU-3, FU-5, FU-7) | IN-PROGRESS | `.claude/progress/quick-features/live-ingest-review-followups.md` |
| Bootstrap test unskip (FU-004 skip decorators on fixed code) | OPEN | `backend/tests/test_runtime_bootstrap.py:616,680,716,1057,1333` |
| Postgres NOTIFY listener reconnect / backoff | NOT STARTED (deferred FU-2) | `backend/adapters/live_updates/postgres_listener.py` |
| Wire-boundary SSE smoke test | NOT STARTED (deferred FU-4) | (test infra gap) |
| Multi-project command center enablement (feature flag OFF) | GATED | `constants.ts:399,418` |
| App-shell global feature refresh retirement | PARTIAL | `services/apiClient.ts:421-423` |

---

## 9. Overlap / Confusion Risk Summary

| Risk | Severity | Detail |
|------|----------|--------|
| planning-command-center-v1 PRD says `draft` but code is complete | LOW | Stale doc; AAR + implementation plan both say `completed`. No code risk. |
| db-caching-layer-v1 phases 1–2 missing from progress | LOW | Probably predate progress-file system; phases 3–4 cover modern work. |
| data-platform-modularization-v1 phases 1–2 show `overall_progress: 90` | LOW | Noted as "waiting on unrelated typecheck cleanup"; code tasks all `completed`. |
| live-ingest-review-followups.md `status: in-progress` but FU-1 appears fixed in code | MEDIUM | Progress file is stale; FU-3/5/7 are genuinely open. |
| bootstrap FU-004 skip decorators on code that appears fixed | HIGH | Tests skip coverage that is now wrong (the fields ARE present). Should be unskipped and verified. |
| Two TTL default changes (query-caching + runtime-perf-hardening) | NONE | Identical value; no conflict. |
