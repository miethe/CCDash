---
schema_version: 2
doc_type: spike
title: "Remote CCDash Operation + Local Daemon Session Streaming — Findings Summary"
description: "Synthesized findings for the remote-CCDash + local-daemon SPIKE. Resolves RQ-1 through RQ-8 with go-forward recommendations, ADR pointers, benchmark targets, failure-mode matrix, and migration plan."
status: completed
created: 2026-05-10
updated: 2026-05-10
completed_date: 2026-05-10
feature_slug: remote-ccdash-streaming
charter_ref: docs/project_plans/spikes/remote-ccdash-streaming-charter.md
prd_ref: docs/project_plans/PRDs/features/remote-ccdash-streaming-v1.md
plan_ref: docs/project_plans/implementation_plans/features/remote-ccdash-streaming-v1.md
related_documents:
  - docs/project_plans/design-specs/remote-ccdash-streaming.md
  - docs/project_plans/designs/remote-ccdash-streaming/remote-ccdash-streaming-design.md
  - .claude/findings/remote-ccdash-grounding-brief.md
adrs:
  - docs/project_plans/adrs/adr-014-remote-session-ingest-transport-ndjson-http.md
  - docs/project_plans/adrs/adr-015-local-daemon-packaging-as-ccdash-cli-subcommand.md
  - docs/project_plans/adrs/adr-008-workspace-scoped-bearer-auth-v1.md
  - docs/project_plans/adrs/adr-009-session-ingest-source-port-and-cursor-table.md
  - docs/project_plans/adrs/adr-010-multi-project-routing-single-process-with-request-scoped-binding.md
---

# Remote CCDash Operation + Local Daemon Session Streaming — Findings Summary

> This document is the **single end-to-end read** for a human reviewer approving downstream PRD work. Every research question (RQ-1 through RQ-8) is resolved here with rationale and a pointer to the ADR or memo that captures the decision in detail. Code citations and current-state context are not duplicated; they live in the [grounding brief](../../.claude/findings/remote-ccdash-grounding-brief.md).

---

## Executive Summary

The SPIKE finds that running CCDash as a remote service that ingests sessions from a local daemon is feasible in v1 with **chunked NDJSON over HTTPS POST** as the transport, the **standalone `ccdash` CLI as the daemon host**, **per-workspace bearer tokens** for multi-tenant auth, a new **`SessionIngestSource` port + `ingest_cursors` watermark table** to absorb both filesystem and remote sources without a fork, and **single-process request-scoped project binding** for multi-project routing. None of the five decisions requires new external infrastructure (no broker, no IdP, no new language toolchain). The biggest implementation risk is the sync engine refactor (ADR-009) — gated by a hard "zero existing-test changes" rule — and the second-biggest is making sure every workspace-scoped repository query is audited for the predicate (ADR-008). All five gating decisions converge: each one keeps the v1 surface as additive as possible to today's runtime, and each one preserves a clean forward path to the post-v1 stretches (OIDC auth, horizontal scaling, sub-second live transcript push).

The recommended implementation order matches the existing [implementation plan skeleton](../implementation_plans/features/remote-ccdash-streaming-v1.md) with no re-ordering: **Phase 2 (sync port + cursor table) → Phase 3 (ingest endpoint + daemon) → Phase 4 (workspace auth + project routing) → Phase 5 (Entire source, sister SPIKE) → Phase 6 (frontend) → Phase 7 (hardening) → Phase 8 (docs)**. Phase 4 may run in parallel with Phase 3 once the auth ADR (ADR-008) and the routing ADR (ADR-010) are sealed; Phase 6 may begin design work concurrently with Phase 5.

---

## RQ Resolutions

### RQ-1 — Ingest transport: chunked NDJSON over HTTPS POST

**Resolution.** Endpoint `POST /api/v1/ingest/sessions` accepting NDJSON (one event per line) with chunked transfer encoding. Statelessness on the server, symmetry with the existing outbound telemetry exporter (`backend/services/integrations/telemetry_exporter.py`), and full proxy/firewall compatibility carry the decision. Idempotency is enforced via per-event `event_id` (UUID v7 recommended) deduplicated server-side.

**Rationale.** SSE is structurally inverted for inbound (server would need to subscribe to daemon-hosted feeds). WebSocket and gRPC trade per-message latency for substantial new infrastructure that the v1 5–30s flush cadence does not justify. The decision matrix in [ADR-006](../adrs/adr-014-remote-session-ingest-transport-ndjson-http.md) scores NDJSON POST 64 vs SSE 47 vs WebSocket 41 vs gRPC 42.

**ADR.** [ADR-006](../adrs/adr-014-remote-session-ingest-transport-ndjson-http.md).

---

### RQ-2 — Daemon packaging: subcommand of the `ccdash` CLI

**Resolution.** The daemon ships as `ccdash daemon {install,start,stop,status,logs,uninstall,restart}` inside `packages/ccdash_cli/`. Supervision is delegated to host-OS user-space supervisors (launchd / systemd `--user` / Task Scheduler at logon). No new runtime profile in `backend/runtime/`.

**Rationale.** Reuses the already-`pipx`-installable CLI distribution channel and the existing HTTP client (auth, retry, version negotiation). One language for the team. Idle resource floor (<50MB RSS, <1% CPU) is well within budget for Python. The Go-binary alternative would force a second build pipeline, code-signing pipeline, and crash-reporter integration — disproportionate cost for the v1 scale target.

**ADR.** [ADR-007](../adrs/adr-015-local-daemon-packaging-as-ccdash-cli-subcommand.md).

---

### RQ-3 — Auth: workspace-scoped bearer tokens for v1

**Resolution.** Extend (do not replace) the existing bearer guard with a `workspace_tokens` table keyed by argon2id-hashed token → `(workspace_id, project_id, scope)`. Inject `AuthContext{workspace_id, project_id, token_id, scope}` per request. Every scoped repository query gains an explicit `workspace_id` predicate. RLS is deferred to v2 (SQLite has no RLS, so dual-implementation cost is unjustified for v1). The `x-ccdash-project-id` header becomes advisory and 403s on mismatch with `AuthContext.project_id`.

**Rationale.** OIDC, mTLS, and git-identity all add new runtime dependencies disproportionate to "minimum viable multi-workspace". Static tokens are headless-daemon-friendly and migrate from today's single-bearer in one schema migration + one row insert. The forward path to OIDC is preserved because the resolver can swap without touching repositories — the `AuthContext` shape is identical either way. The decision matrix in [ADR-008](../adrs/adr-008-workspace-scoped-bearer-auth-v1.md) scores per-workspace tokens 70 vs OIDC 41 vs mTLS 47 vs git-identity 47.

**ADR.** [ADR-008](../adrs/adr-008-workspace-scoped-bearer-auth-v1.md).

---

### RQ-4 — Sync engine refactor: `SessionIngestSource` port + `ingest_cursors` table

**Resolution.** Introduce a `SessionIngestSource` Python `Protocol` consumed by `SyncEngine`. Three implementations: `FilesystemSource` (wraps current logic, zero behavior change), `RemoteIngestSource` (consumes events from the new ingest endpoint), and `EntireCheckpointSource` (deferred to sister SPIKE). Add an `ingest_cursors` table that becomes the **single source of sync truth** across all source types — the filesystem source advances its own cursor row too. Add a `source_ref` column to `sessions` with URI-style scheme (`fs:`, `remote:`, `entire:`) and update the upsert key to `(project_id, workspace_id, source_ref)`.

**Rationale.** Hard gate: zero existing-test changes for `FilesystemSource` parity. The port shape is structural (a `Protocol`) rather than a class hierarchy, which keeps `FilesystemSource` from inheriting any remote-only concerns. Cursor advancement is atomic with upsert in the same DB transaction — closes the off-by-one risk in the design-spec §8 Open Risks.

**ADR.** [ADR-009](../adrs/adr-009-session-ingest-source-port-and-cursor-table.md).

---

### RQ-5 — Multi-project routing: single process with request-scoped binding

**Resolution.** Refactor `RuntimeContainer.bound_project` (single startup-time value) into `RuntimeContainer.resolve_binding(project_id)` (per-request lookup, LRU-cached). The `api` runtime profile serves all projects from one process. The `worker` profile retains startup-time binding for v1 (multi-project workers are out of scope; teams that want it run N worker processes). Project routing is driven exclusively by `AuthContext.project_id`; the `x-ccdash-project-id` header is honored only as a tie-break and 403s on mismatch.

**Rationale.** Operational footprint: 1 pod vs 10 pods for a 10-project team. The decision matrix in [ADR-010](../adrs/adr-010-multi-project-routing-single-process-with-request-scoped-binding.md) scores single-process 65 vs one-process-per-project 38, with the loss line on cold start, RSS, and operator burden. Hard-gate fallback: if any of (cold start ≤ +10%, RSS ≤ 2× at 10 projects, p99 ≤ +25%) is missed in load testing, ship v1 single-process and add horizontal scaling for the violated dimension in v1.1; do not silently degrade.

**ADR.** [ADR-010](../adrs/adr-010-multi-project-routing-single-process-with-request-scoped-binding.md).

---

### RQ-6 — Failure modes and ops posture

Resolved via the **failure-mode matrix** below.

---

### RQ-7 — Frontend requirements

**Resolution.** Three minimum surfaces for v1: (a) a **session-source chip** in `components/SessionInspector.tsx` and the session list row, distinguishing `fs` / `remote` / `entire` ingest origins; (b) a **daemon health badge** in the runtime/health area driven by an extended `/api/health` payload (new `ingest_sources` block with cursor-lag and last-batch timestamps, see failure-mode matrix below); (c) a **"live" vs "historical" pill** on session cards driven by whether the session's last event is within the configured live-window (default: 60s).

**Live-update cadence.** **Stay on polling for v1**, raise frequency for the sessions list to 5s when a remote source is connected (vs the current 30s for browsing). Reuse the existing TanStack Query pattern — no SSE subscription on the ingest path. The backend already has SSE infrastructure (`backend/routers/live.py`, ADR-001) used by the VSCode extension; v1 explicitly does not extend that surface to the dashboard for ingest events. Revisit in v2 if user feedback shows polling is insufficient.

**Rationale.** Polling at 5s when a daemon is connected gives a perceived "near-live" UX matching the daemon's flush cadence (5–30s). Adding an SSE subscription on the dashboard for ingest events would couple the dashboard to the SSE infrastructure and add reconnect/replay logic for sessions whose updates are not on the critical path for v1. The frontend inventory + cadence memo lives in the [design doc](../designs/remote-ccdash-streaming/remote-ccdash-streaming-design.md).

**Touchpoints.** `contexts/AppRuntimeContext.tsx` (health badge consumer), `contexts/AppEntityDataContext.tsx` (poll cadence), `services/apiClient.ts` (typed `IngestSourceHealth` model), `components/SessionInspector.tsx` (source chip + live pill).

---

### RQ-8 — Migration story for existing local-mode users

Resolved via the **migration plan memo** below.

---

## Failure-Mode Matrix (RQ-6)

Every row maps a failure class to its detection mechanism, recovery behavior, and the operator-visible signal it surfaces. Health endpoint extensions referenced here are part of Phase 7.

| # | Failure class | Detection | Recovery | Operator signal |
|---|---|---|---|---|
| F-1 | **Daemon offline / crashed** | Server: `last_ingest_at` for the workspace ages past 2× flush_interval. Daemon: supervisor-managed; auto-restart by launchd/systemd/Task Scheduler. | Daemon restart picks up from on-disk WAL buffer; cursor is server-acked, no replay needed for already-acked events. | `/api/health` `ingest_sources[i].state = "stale"` when `now - last_ingest_at > stale_threshold`. UI badge shows yellow. |
| F-2 | **Daemon network unreachable** | Daemon HTTP client returns connection error. | Exponential backoff (cap 60s) + on-disk WAL buffer; resume on connectivity restore. Hard gate: full recovery within 5s of network restore (per E1). | Daemon `ccdash daemon status` shows "buffering, N events queued". UI badge yellow. |
| F-3 | **Server returns 5xx** | HTTP status 500/502/503/504. | Same as F-2: backoff + WAL. Server returns `Retry-After` header when available. | `/api/health.ingest_sources[i].error_count` increments; if >0 in last 5min, badge yellow. |
| F-4 | **Server returns 429 (overloaded)** | Explicit backpressure signal. | Daemon honors `Retry-After`; pauses POST loop without growing buffer faster than necessary. | `/api/health` exposes a "throttling" boolean; metric `ingest_throttled_seconds_total` exported via Prometheus (existing OTEL pipeline). |
| F-5 | **Partial batch acceptance (some events 4xx)** | Server response envelope per ADR-006: `{accepted: int, rejected: [{event_id, reason}], dead_lettered: [...]}`. | Daemon: rejected events are sidelined to a local **dead-letter file** (`~/.local/state/ccdash/deadletter/`); accepted advance the cursor. | Daemon CLI `ccdash daemon status` surfaces deadletter count; server health endpoint reports cumulative dead-lettered count per workspace. |
| F-6 | **Schema skew (daemon release N posts unknown field)** | Server pydantic model validation finds unknown field. | Forward-compat: server logs warn-and-strip, accepts the event. Backward-incompatible field (e.g., a required field is missing) → reject as 4xx + dead-letter. | Server metric `ingest_schema_warning_total{event_type}`; daemon-version mismatch is exposed via `/api/health.ingest_sources[i].daemon_version`. |
| F-7 | **Schema skew (daemon release N−1 posts to server release N that requires a new field)** | Pydantic model rejection. | Server endpoint is versioned at `/v1/`. A new required field requires a new endpoint version (`/v2/`). v1 must never add required fields to existing event types. | Documented as a constraint in the operator guide; CI gate forbids field additions without version bump. |
| F-8 | **Cursor lag** (ingest is keeping up but delayed) | Server tracks `cursor_lag = now - latest_event_time` per source. | None automatic. Operator scales workers or investigates. | `/api/health.ingest_sources[i].cursor_lag_seconds`; alert threshold default 60s. |
| F-9 | **Clock skew** (daemon clock 30+ min off) | `event.occurred_at` more than ±5min from server time on a sample. | Server logs and uses server-receive time as the authoritative timestamp for ordering; daemon time is preserved in an `event_originated_at` field. | Health endpoint exposes `ingest_sources[i].clock_skew_seconds`; alert >300s. |
| F-10 | **Workspace token revoked** | `WorkspaceTokenAuthBackend` returns 401 (token row revoked, ADR-008). | Daemon stops POSTing on persistent 401; alerts user. Operator rotates the token via `ccdash daemon configure --token <new>`. | Daemon CLI surfaces "auth revoked"; server logs an audit event with `token_id`. |
| F-11 | **Server DB full / write fails** | Repository upsert raises. | Server returns 500; daemon retries (F-3). | Existing DB-error alerts (already in observability stack). |
| F-12 | **Daemon disk full (WAL cannot grow)** | Daemon write to local buffer fails. | Daemon stops accepting tail input; emits desktop notification; status command shows "buffer-full". | Daemon CLI; no server-side signal (daemon is offline by definition). |

A manual chaos run pairing E1 (server-side ingest stub) with E2 (daemon stub) is a Phase 3 acceptance test, not a SPIKE deliverable. It must exercise F-1 through F-6 explicitly.

---

## Migration Plan Memo (RQ-8)

### Default behavior post-upgrade

**No-op.** Existing single-user local deployments running the `local` runtime profile see zero behavior change. The `FilesystemSource` continues to be the only ingest source. The legacy `CCDASH_AUTH_TOKEN` continues to work in `local` profile. No new tables are populated unless the operator opts in.

### Opt-in path to remote ingest

A deployment opts into remote ingest by:

1. Switching to the `api` and/or `worker` runtime profile (already supported).
2. Running the auth migration script `backend/scripts/migrate_bearer_to_workspace_token.py` once. This creates a `default-local` workspace, mints one workspace token equivalent to today's `CCDASH_AUTH_TOKEN`, and backfills `workspace_id = 'default-local'` on every existing scoped row.
3. Setting `CCDASH_REMOTE_INGEST_ENABLED=true` to register the `RemoteIngestSource` alongside (or instead of) the `FilesystemSource`.
4. On the developer's workstation: `pipx upgrade ccdash-cli && ccdash daemon install --server-url <url> --token <token> --project-id <id>`.

Steps 2 and 3 are independent: an operator may issue workspace tokens (closing the single-bearer hole) without enabling remote ingest. This is the recommended first step on the path.

### Dual-source policy during transition

A workspace may run **both** a `FilesystemSource` and a `RemoteIngestSource` simultaneously when `CCDASH_DUAL_SOURCE_INGEST=true`. The cursor model + `source_ref` upsert key (ADR-009) handles deduplication: filesystem-keyed sessions and remote-keyed sessions land in distinct rows even if they describe the same underlying session, and the UI source chip distinguishes them. Operators should treat dual-source mode as a transient state used during cutover, not a steady state. Default off.

### Rollback story

Every step is reversible:

- Disable remote ingest: unset `CCDASH_REMOTE_INGEST_ENABLED`.
- Revert auth model: switch the auth backend wiring back to `SingleBearerAuthBackend` in the runtime composition.
- Drop the new tables (`workspaces`, `workspace_tokens`, `ingest_cursors`) and the `workspace_id` / `source_ref` columns: the legacy code paths tolerate their absence (forward-tolerable migrations).

### User-facing communication

CHANGELOG entry (see Phase 8) summarizes:

- New: `POST /api/v1/ingest/sessions` endpoint; `ccdash daemon` subcommand; workspace-scoped tokens.
- Behavior: local single-user deployments unchanged.
- Action required: none for `local` profile users; operators of `api`/`worker` deployments run the auth migration script.

---

## Benchmark Targets Table (E1, E5)

These are **targets for downstream load testing**, not measurements taken in this SPIKE. The Phase 3 and Phase 4 acceptance gates validate them against an actual implementation.

### E1 — NDJSON ingest throughput

| Metric | Target | Notes |
|---|---|---|
| Sustained ingest throughput | ≥ 500 events/sec on a single `worker` process | 2-core machine; covers ~20 active developers @ 25 events/sec |
| p99 batch latency (100-event batches) | < 200ms | Server-side processing only; excludes network |
| Reconnect after forced TCP reset | Daemon resumes within 5s of network restore | Tests F-2 path |
| Server memory high-water-mark, 10 daemons × 500 evt/s each | ≤ 2× single-daemon-idle baseline | Validates streaming parse |

### E2 — Daemon resource floor

| Metric | Target | Notes |
|---|---|---|
| Daemon CPU at idle (60s no events) | < 1% on M-series Mac / equivalent | `watchfiles` not poll-loop |
| Daemon RSS at idle (10min steady) | < 50 MB | Confirms lean dependency closure |
| Duplicate events after forced network blip | 0 | Idempotency via `event_id` |
| Lost events after `kill -9` of daemon | 0 | WAL is fsync'd before ack |
| Cold start (boot to first POST) | < 2s | One-time cost; supervised |

### E3 — Auth (no perf gates beyond regression)

| Gate | Target |
|---|---|
| Cross-workspace read attempt | 403 or empty result |
| Token revocation latency | Effective on next request |
| Migration script idempotency | Two runs ≡ one run |
| Legacy single-bearer tests | Pass unchanged in `local` profile |

### E5 — Multi-project routing

| Metric | Target | Fallback if missed |
|---|---|---|
| Cold start (boot to ready) | ≤ existing baseline + 10% | Stays single-process |
| Steady-state RSS at 10 concurrent projects | ≤ 2× single-project baseline | Horizontal scale in v1.1 |
| p99 latency at 10 concurrent projects | ≤ baseline + 25% | Per-tenant rate limit in v1.1 |
| Forged `x-ccdash-project-id` rejection | 403 | Hard gate; no fallback |

---

## Decisions Requiring ADRs

All five are **authored as part of this SPIKE** (allocated 006–010, the next free ADR numbers; the directory was empty above 005):

1. [ADR-006](../adrs/adr-014-remote-session-ingest-transport-ndjson-http.md) — Remote session ingest transport: chunked NDJSON over HTTPS POST.
2. [ADR-007](../adrs/adr-015-local-daemon-packaging-as-ccdash-cli-subcommand.md) — Local daemon packaging: subcommand of `ccdash` CLI.
3. [ADR-008](../adrs/adr-008-workspace-scoped-bearer-auth-v1.md) — Workspace-scoped bearer tokens for v1.
4. [ADR-009](../adrs/adr-009-session-ingest-source-port-and-cursor-table.md) — `SessionIngestSource` port + `ingest_cursors` watermark table.
5. [ADR-010](../adrs/adr-010-multi-project-routing-single-process-with-request-scoped-binding.md) — Multi-project routing: single process with request-scoped binding.

---

## Risks Surfaced (Charter §8 ↔ Decisions)

| Charter risk | Where addressed |
|---|---|
| Duplicate events under poor networks | ADR-006 idempotency (`event_id`); F-2 path; E2 hard gate |
| Schema skew between daemon and server | ADR-006 versioned endpoint + warn-and-strip; F-6, F-7 |
| Cursor semantics without mtime | ADR-009: per-source cursor; cursor advances atomically with upsert; E4 hard gate |
| Workspace resolution bypass via header | ADR-008 + ADR-010: header is advisory, scope follows token, mismatch returns 403 |
| Backpressure invisibility | ADR-006: server returns 429 with `Retry-After`; F-4; daemon enforces local buffer cap |
| Local-mode regression via shared sync engine | ADR-009: zero existing-test-change hard gate; corpus-equality test |

---

## Open Questions Deferred to Sister SPIKE

OQ-5 (Entire ingest path), OQ-6 (Entire session identity), and OQ-10 (Entire hook surface) are explicitly out of scope per charter §5 and remain open against the `entire-io-integration-charter.md` SPIKE. The `EntireCheckpointSource` lands as a third implementation of the `SessionIngestSource` protocol defined in ADR-009 — no further engine-side work is required when that SPIKE resolves.

---

## Handoff

The downstream artifacts are ready to be promoted from draft to active:

1. **Design spec** `docs/project_plans/design-specs/remote-ccdash-streaming.md` — promote `maturity: shaping` → `maturity: ready` once the SPIKE Resolutions section is added (covered in Phase 4 of this SPIKE flow).
2. **PRD** `docs/project_plans/PRDs/features/remote-ccdash-streaming-v1.md` — scaffold using the resolved direction in this findings document.
3. **Implementation plan** `docs/project_plans/implementation_plans/features/remote-ccdash-streaming-v1.md` — already drafted; refresh `architecture_summary` and lock the Phase 2–8 estimates against the ADRs.
4. **Architecture design doc** `docs/project_plans/designs/remote-ccdash-streaming/remote-ccdash-streaming-design.md` — companion design document with the integration sequence diagram and per-layer impact map.
