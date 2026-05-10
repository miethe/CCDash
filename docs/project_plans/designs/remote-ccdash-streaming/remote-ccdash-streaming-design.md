---
schema_version: 2
doc_type: design
title: "Remote CCDash Streaming — Architecture Design"
description: "Architecture, layer-impact map, and integration points for remote CCDash operation with local-daemon session streaming. Companion to SPIKE findings; consumed by the v1 PRD and implementation plan."
status: draft
created: 2026-05-10
updated: 2026-05-10
feature_slug: remote-ccdash-streaming
spike_ref: docs/project_plans/SPIKEs/remote-ccdash-streaming.md
prd_ref: docs/project_plans/PRDs/features/remote-ccdash-streaming-v1.md
plan_ref: docs/project_plans/implementation_plans/features/remote-ccdash-streaming-v1.md
related_documents:
  - docs/project_plans/design-specs/remote-ccdash-streaming.md
  - docs/project_plans/adrs/adr-006-remote-session-ingest-transport-ndjson-http.md
  - docs/project_plans/adrs/adr-007-local-daemon-packaging-as-ccdash-cli-subcommand.md
  - docs/project_plans/adrs/adr-008-workspace-scoped-bearer-auth-v1.md
  - docs/project_plans/adrs/adr-009-session-ingest-source-port-and-cursor-table.md
  - docs/project_plans/adrs/adr-010-multi-project-routing-single-process-with-request-scoped-binding.md
---

# Remote CCDash Streaming — Architecture Design

## 1. Purpose

This document captures the architectural shape of the v1 remote-CCDash + local-daemon system as resolved by [SPIKE findings](../../SPIKEs/remote-ccdash-streaming.md). It is the integration map a developer reads before opening any of the five ADRs in detail and the input the implementation plan refreshes against.

The decisions are sealed in the ADRs; this document explains how they fit together.

## 2. System Topology

```
┌────────────────── Workstation ──────────────────┐         ┌──────────────── Remote CCDash (api+worker) ─────────────────┐
│                                                  │         │                                                              │
│  Claude Code / Codex / Gemini CLI / etc.         │         │  ┌─────────────────────┐                                     │
│       │                                          │         │  │ FastAPI (api profile) │  routers/ingest.py  (POST NDJSON) │
│       ▼                                          │         │  │                     │  routers/v1/*  (existing read)     │
│  JSONL session files                              │         │  │  WorkspaceTokenAuth │  routers/agent/*  (existing read)  │
│       │                                          │         │  │     ↓               │  routers/health.py (extended)      │
│       ▼                                          │   POST  │  │  AuthContext        │                                     │
│  ccdash daemon ──────── chunked NDJSON ────────► │ /api/v1 │  │     ↓               │                                     │
│  (Python, supervised by                          │ /ingest │  │  RuntimeContainer.  │                                     │
│   launchd/systemd-user/                          │ /sessions│  │  resolve_binding()  │                                     │
│   Task Scheduler)                                │         │  │     ↓               │                                     │
│       │                                          │         │  │  RemoteIngestSource │ ──┐                                 │
│       │  on-disk WAL buffer                      │         │  └─────────────────────┘   │  (SessionIngestSource Protocol) │
│       │  (~/.local/state/ccdash/wal)            │         │                              ▼                                 │
│       │                                          │         │  ┌─────────────────────┐   ┌──────────────────────┐         │
│       └────────────── retry/backoff ────────────►│         │  │ Worker (worker prof.)│   │ SyncEngine          │         │
│                                                  │         │  │                     │   │                     │         │
│                                                  │         │  │ FilesystemSource    │──►│ session_repo.upsert │──►SQLite/PG│
│                                                  │         │  │ (when local FS is   │   │ + ingest_cursors    │           │
│                                                  │         │  │  source-of-truth)   │   │   advance(atomic)   │           │
│                                                  │         │  └─────────────────────┘   └──────────────────────┘         │
└──────────────────────────────────────────────────┘         │                                                              │
                                                             │  ┌─────────────────────┐                                     │
                                                             │  │ Frontend (Vite/HTTP)│  polling 5s when daemon connected   │
                                                             │  │  source chip,       │  source chip + daemon health badge  │
                                                             │  │  daemon health,     │  consumes /api/health.ingest_sources│
                                                             │  │  live/historical    │                                     │
                                                             │  └─────────────────────┘                                     │
                                                             └──────────────────────────────────────────────────────────────┘
```

Both the workstation daemon and the server's `worker` runtime can host a `SessionIngestSource`. The same `Protocol` (defined in ADR-009) is implemented by `FilesystemSource` (server-side, when filesystem is the source of truth) and `RemoteIngestSource` (server-side, fed by the ingest endpoint). The daemon itself does **not** implement the protocol — it is a thin tailing-and-POSTing client whose only contract is "produce NDJSON events conforming to the `IngestSessionEvent` schema". Source identity, deduplication, and cursor advancement are server-side responsibilities.

## 3. Layer Impact Map

Following CCDash's layered architecture (routers → services → repositories → DB):

### Frontend (`/`, `components/`, `contexts/`, `services/`)

| Component | Change |
|---|---|
| `services/apiClient.ts` | Add typed `IngestSourceHealth` model (cursor lag, last batch, daemon version, schema warnings, throttle state). |
| `contexts/AppRuntimeContext.tsx` | Consume new `ingest_sources` block from `/api/health`; expose health state for the runtime badge. |
| `contexts/AppEntityDataContext.tsx` | Bump session-list polling cadence from 30s → 5s when any `ingest_sources[i].state == 'connected'`. |
| `components/SessionInspector.tsx` | Add **session-source chip** (`fs` / `remote` / `entire`) and **live/historical pill** (live = last event within 60s). |
| `components/Dashboard.tsx` (or equivalent) | Surface daemon health badge (yellow when stale, red when offline, green when healthy). |

No new SSE subscription on the dashboard for ingest events. The existing SSE infrastructure (ADR-001) is untouched.

### API routers (`backend/routers/`)

| Router | Change |
|---|---|
| `backend/routers/ingest.py` (new) | `POST /api/v1/ingest/sessions` accepting NDJSON. Streams the request body line-by-line; calls into `IngestService`. |
| `backend/routers/health.py` | Extend `/api/health` payload with `ingest_sources: list[IngestSourceHealth]` per (source_id, project_id, workspace_id). |
| `backend/routers/v1/*.py`, `backend/routers/agent/*.py` | Add `Depends(get_project_binding)` to every project-scoped endpoint; replace any direct `RuntimeContainer.bound_project` access with the per-request binding. |

### Services (`backend/application/services/`, `backend/services/`)

| Service | Change |
|---|---|
| `IngestService` (new, `backend/services/ingest_service.py`) | Validates batches, applies dedup against `event_id`, hands events to the appropriate `RemoteIngestSource` instance, returns the partial-success envelope. |
| `backend/application/services/agent_queries/*.py` | Take `binding: ProjectBinding` (from `Depends`) instead of reading a global. |
| `backend/services/integrations/telemetry_exporter.py` | Unchanged (precedent only; symmetric reverse pattern in `IngestService`). |

### Repositories (`backend/db/repositories/`)

| Repository | Change |
|---|---|
| `sessions.py` | Add `workspace_id`, `source_ref` columns; new upsert key `(project_id, workspace_id, source_ref)`. Backfill `source_ref = 'fs:' + source_file` for existing rows. Every read method gains `workspace_id` parameter. |
| `documents.py`, `tasks.py`, `features.py`, `links.py`, `analytics.py` | Add `workspace_id` parameter to every method. Audit every SELECT for the predicate. |
| `ingest_cursors.py` (new) | CRUD over the new `ingest_cursors` table; `advance(source_id, project_id, workspace_id, cursor_value)` is atomic with the session upsert. |
| `workspace_tokens.py` (new) | Argon2id hash storage + verification; rotation; revocation. |
| `workspaces.py` (new) | One row per workspace; tied to project_id in v1. |

### Sync engine (`backend/db/sync_engine.py`, `backend/db/file_watcher.py`)

| Component | Change |
|---|---|
| `SyncEngine` | Refactor to consume `list[SessionIngestSource]` instead of filesystem paths. Hard gate: zero existing-test changes. |
| `FilesystemSource` (new) | Wraps current logic; advances its own row in `ingest_cursors` for observability parity. |
| `RemoteIngestSource` (new) | Consumes events from `IngestService`; no filesystem touchpoints. |
| `EntireCheckpointSource` (new, deferred to sister SPIKE) | Third implementation; out of scope for this design doc. |

### Auth (`backend/adapters/auth/`)

| Adapter | Change |
|---|---|
| `bearer.py` | Existing `SingleBearerAuthBackend` retained for `local` profile. New `WorkspaceTokenAuthBackend` swaps in for `api`/`worker`. |
| `auth_context.py` (new) | `AuthContext` dataclass; FastAPI dependency. |

### Runtime (`backend/runtime/`)

| Module | Change |
|---|---|
| `container.py` | `bound_project` → `resolve_binding(project_id) -> ProjectBinding`; LRU cache. |
| `bootstrap.py` | Wire the auth backend by profile; register `RemoteIngestSource` when `CCDASH_REMOTE_INGEST_ENABLED=true`. |
| `profiles.py` | No change. (Daemon is not a runtime profile per ADR-007.) |

### CLI / Daemon (`packages/ccdash_cli/`)

| Module | Change |
|---|---|
| `src/ccdash_cli/commands/daemon.py` (new) | `install`, `start`, `stop`, `status`, `logs`, `restart`, `uninstall`, `configure`. |
| `src/ccdash_cli/daemon/tail.py` (new) | JSONL tailing with `watchfiles`, file rotation handling. |
| `src/ccdash_cli/daemon/wal.py` (new) | On-disk write-ahead buffer; fsync-then-ack; cap at 500MB default. |
| `src/ccdash_cli/daemon/shipper.py` (new) | Batched chunked NDJSON POST via existing `ccdash_cli.runtime.client`. |
| `src/ccdash_cli/daemon/supervisors/` (new) | Templates for launchd plist, systemd `--user` unit, Task Scheduler XML. |

### Database schema (Alembic migration)

New tables:

- `workspaces (workspace_id PK, name, created_at, status)`
- `workspace_tokens (token_id PK, workspace_id, project_id, hashed_token, scope, created_at, last_used_at, revoked_at, description)`
- `ingest_cursors (source_id, project_id, workspace_id, last_cursor, last_ingest_at, error_count, last_error, last_error_at; PK on the triple)`

New columns on existing tables:

- `sessions.workspace_id` (NOT NULL after backfill); `sessions.source_ref` (NOT NULL after backfill); new unique index `(project_id, workspace_id, source_ref)`.
- `documents.workspace_id`, `tasks.workspace_id`, `features.workspace_id`, `links.workspace_id`, `progress_files.workspace_id` — backfilled to `default-local`.

## 4. Data Flow — Successful Ingest

1. Daemon tails `~/.claude/projects/<proj>/sessions/*.jsonl`; new lines are appended to its WAL.
2. Daemon batches up to 500 events (or flushes after 5–30s, whichever first); marks them as "in-flight" in WAL.
3. Daemon POSTs `Content-Type: application/x-ndjson` to `https://ccdash.example.com/api/v1/ingest/sessions` with `Authorization: Bearer <workspace_token>`.
4. Server: `WorkspaceTokenAuthBackend` resolves `AuthContext{workspace_id, project_id, ...}`. `Depends(get_project_binding)` resolves `ProjectBinding`.
5. Server: `routers/ingest.py` streams the request body, parses one event per line, validates against `IngestSessionEvent` Pydantic model, hands each to `IngestService`.
6. `IngestService` deduplicates on `(workspace_id, event_id)`, calls `RemoteIngestSource.feed(event)` (or equivalent push pattern).
7. `SyncEngine` (running in `worker` profile, or in-process for `api+worker` co-located deployments) drains the source: calls `session_repo.upsert(...)` and `ingest_cursors.advance(...)` in the same DB transaction.
8. Server returns `{accepted: N, rejected: [], dead_lettered: [], cursor_value: <last>}`.
9. Daemon: on success, removes acked events from WAL; advances local cursor.

## 5. Data Flow — Daemon Restart

1. Daemon process killed (kill -9 or supervisor restart).
2. WAL on disk is intact; in-flight events are still marked "in-flight" (not "acked").
3. Daemon restarts; reads WAL; sends a `cursor probe` request first: `GET /api/v1/ingest/cursor/{workspace_id}/{source_id}/{project_id}` (auth required).
4. Server returns current cursor value from `ingest_cursors`.
5. Daemon resends every event in WAL with `cursor_value > server_cursor` (could be all, could be none).
6. Server dedup is keyed by `(workspace_id, event_id)`; double-send is a no-op.
7. Cursor advances atomically with each successful upsert; daemon clears acked events from WAL.

This guarantees zero data loss on daemon restart and zero duplicate rows in the DB.

## 6. Concurrency & Backpressure

- The ingest endpoint is **stateless per request**. N concurrent daemons → N concurrent FastAPI requests → bounded by uvicorn worker concurrency. There is no shared state between requests except the DB.
- Each batch is processed sequentially within its request; concurrency comes from N independent requests.
- When server load is high, the endpoint can return `429 + Retry-After` and the daemon backs off without growing its WAL faster than the network allows.
- On the daemon side, the WAL is a single-writer / single-reader queue; tailing and shipping are independent async tasks coordinated through the WAL.

## 7. Observability

The existing OTEL pipeline (`backend/observability/otel.py`) gains:

- **Metrics**:
  - `ingest_events_received_total{source_id, workspace_id}` (counter)
  - `ingest_events_accepted_total{source_id, workspace_id}` (counter)
  - `ingest_events_dead_lettered_total{source_id, workspace_id, reason}` (counter)
  - `ingest_batch_latency_seconds{source_id, workspace_id}` (histogram)
  - `ingest_cursor_lag_seconds{source_id, project_id, workspace_id}` (gauge)
  - `ingest_throttled_seconds_total{source_id, workspace_id}` (counter)
  - `ingest_schema_warning_total{event_type}` (counter)
- **Spans**: every batch is a span (`ingest.batch.process`) with attributes `workspace_id`, `source_id`, `event_count`, `accepted`, `rejected`.
- **Traces**: daemon adds a `traceparent` header per batch; server propagates per the existing OTEL middleware.

The daemon side keeps a small Prometheus-style metrics file at `~/.local/state/ccdash/metrics.prom` for `ccdash daemon status` to read.

## 8. Security Posture

| Surface | Posture |
|---|---|
| Workspace token at rest on workstation | `~/.config/ccdash/daemon.toml` mode 0600; never written to project files |
| Workspace token in transit | TLS (HTTPS) only; daemon refuses plain HTTP except when `CCDASH_DAEMON_ALLOW_INSECURE=true` (dev only) |
| Server-side hashing | argon2id with default cost params; rotation does not require re-hashing existing tokens (each row carries its own params) |
| Audit | Every workspace token has a `token_id`; `last_used_at` updates on each accepted batch; revocation logs an audit event |
| Cross-workspace bypass | `x-ccdash-project-id` is honored only if equal to `AuthContext.project_id`; mismatch is `403` |
| Logs | Auth backend truncates token secrets to first 6 chars in any log line; structured logging fields are `token_id` not `token` |

## 9. Compatibility Matrix

| Mode | `local` profile | `api` profile | `worker` profile |
|---|---|---|---|
| Auth backend | `SingleBearerAuthBackend` (legacy) | `WorkspaceTokenAuthBackend` | `WorkspaceTokenAuthBackend` |
| Project binding | Startup-time | Per-request via `AuthContext` | Startup-time (one project per worker process) |
| `FilesystemSource` | Active when `storage_profile.filesystem_source_of_truth = true` | Inactive (server has no local FS) | Active when `storage_profile.filesystem_source_of_truth = true` |
| `RemoteIngestSource` | Inactive (no remote ingest in local) | Active when `CCDASH_REMOTE_INGEST_ENABLED=true` | Active when `CCDASH_REMOTE_INGEST_ENABLED=true` |
| Daemon | N/A (user uses local CCDash directly) | N/A (server-side profile) | N/A (server-side profile) |

The `local` profile is unchanged in v1.

## 10. Known Limitations Carried Forward

- No bidirectional command channel (daemon → server only). Server cannot push `rotate-token` or `backfill` to a daemon. Operator initiates via `ccdash daemon configure`.
- No per-workspace rate limiting in v1; relies on global server rate limit. v1.1 adds per-token quota.
- Sub-second live transcript streaming is explicitly out of scope (design-spec §7).
- Multi-project workers are out of scope; teams that want multi-project ingest run N worker processes.

## 11. References

- SPIKE findings: [`docs/project_plans/SPIKEs/remote-ccdash-streaming.md`](../../SPIKEs/remote-ccdash-streaming.md)
- ADR-006 transport: [`docs/project_plans/adrs/adr-006-remote-session-ingest-transport-ndjson-http.md`](../../adrs/adr-006-remote-session-ingest-transport-ndjson-http.md)
- ADR-007 daemon packaging: [`docs/project_plans/adrs/adr-007-local-daemon-packaging-as-ccdash-cli-subcommand.md`](../../adrs/adr-007-local-daemon-packaging-as-ccdash-cli-subcommand.md)
- ADR-008 auth: [`docs/project_plans/adrs/adr-008-workspace-scoped-bearer-auth-v1.md`](../../adrs/adr-008-workspace-scoped-bearer-auth-v1.md)
- ADR-009 sync port: [`docs/project_plans/adrs/adr-009-session-ingest-source-port-and-cursor-table.md`](../../adrs/adr-009-session-ingest-source-port-and-cursor-table.md)
- ADR-010 routing: [`docs/project_plans/adrs/adr-010-multi-project-routing-single-process-with-request-scoped-binding.md`](../../adrs/adr-010-multi-project-routing-single-process-with-request-scoped-binding.md)
- Design spec (parent): [`docs/project_plans/design-specs/remote-ccdash-streaming.md`](../../design-specs/remote-ccdash-streaming.md)
- Grounding brief: [`.claude/findings/remote-ccdash-grounding-brief.md`](../../../../.claude/findings/remote-ccdash-grounding-brief.md)
