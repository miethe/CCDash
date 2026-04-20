---
schema_version: 2
doc_type: spike
title: "Remote CCDash Operation + Local Daemon Session Streaming"
status: draft
created: 2026-04-19
updated: 2026-04-19
feature_slug: remote-ccdash-streaming
complexity: high
estimated_research_time: "2 weeks (1 engineer) or 1 week (2 engineers in parallel on transport vs auth)"
prd_ref: null
related_documents:
  - docs/project_plans/design-specs/remote-ccdash-streaming.md
  - .claude/findings/remote-ccdash-grounding-brief.md
research_questions:
  - "RQ-1: What ingest transport should v1 use: HTTPS NDJSON POST, SSE, WebSocket, or gRPC? Decision criteria: operational simplicity, latency, existing CCDash patterns, client resilience."
  - "RQ-2: How is the local daemon packaged and run? Standalone binary, extension of `ccdash` CLI, or reuse worker runtime profile with a new `daemon` capability? Lifecycle: install, start, auto-start, status, logs, update."
  - "RQ-3: What is the minimum viable auth model for multi-workspace remote operation? Evaluate static per-workspace token, OIDC/OAuth, mTLS, and git-identity (Entire-style). What changes to `backend/adapters/auth/` are required? Does the bearer guard need to become workspace-scoped?"
  - "RQ-4: How must the sync engine be refactored to accept remote events without regression? Propose a `SessionIngestSource` port with implementations (Filesystem, RemoteIngest). Where does cursor/watermark state live — new `sync_cursor` table? How does incremental change detection work without mtime?"
  - "RQ-5: How does the API handle multi-project routing in a remote deployment? Runtime project switching via `x-project-id` header + auth-backed RLS, vs one worker process per project. Impact on `RuntimeContainer` (currently one binding per process, `container.py:67`)."
  - "RQ-6: What are the failure modes and ops posture? Daemon disconnected, server 5xx, partial batch success, schema skew between daemon and server. Propose retry/backoff, dead-letter behavior, and operator-visible health signals (extend `/api/health`)."
  - "RQ-7: What does the frontend need? 'Session source' attribution in the UI, daemon health indicator, live-update cadence (polling vs SSE subscription), handling of historical vs live sessions."
  - "RQ-8: What is the migration story for existing local-mode users? No-op by default? Opt-in flag? Dual-source (filesystem + ingest) support during transition?"
---

# SPIKE Charter: Remote CCDash Operation + Local Daemon Session Streaming

## 1. Charter Purpose

This SPIKE investigates what is required to run CCDash as a remote (non-co-located) service while a lightweight local daemon streams session events from a developer's workstation to the remote server. The outcome of this SPIKE is the technical evidence needed to unblock three downstream artifacts: (1) `docs/project_plans/PRDs/features/remote-ccdash-streaming-v1.md` (PRD approval), (2) the companion architecture document describing the ingest port and workspace-scoped auth model, and (3) `docs/project_plans/implementation_plans/features/remote-ccdash-streaming-v1.md` (phase breakdown and delivery plan). The charter defines research questions, prototypes, and deliverables only; no implementation or final recommendations are produced here.

## 2. Background

- Post-PR#30 runtime profiles (`local`, `api`, `worker`, `test`) are stable and cleanly separated; the `api` runtime serves HTTP while `worker` handles background work via `backend/worker.py` with no HTTP surface (see `backend/runtime/` and CLAUDE.md).
- Session ingestion is still filesystem-and-mtime coupled: the sync engine polls the local filesystem and relies on mtime-based change detection (`backend/db/sync_engine.py`, `backend/db/file_watcher.py`). There is no transport-neutral ingest port.
- Transport surface for live updates is REST pagination only; there is no SSE, WebSocket, or NDJSON streaming endpoint anywhere in `backend/routers/`.
- Auth is a single static bearer, not workspace-scoped (`backend/adapters/auth/bearer.py:22`, `:74-109`). There is no notion of workspace/tenant identity on a request.
- Project binding is startup-time only: `RuntimeContainer` binds one project per process (`backend/runtime/container.py:67`); the `x-ccdash-project-id` request header is only an unauthenticated hint and does not reroute data access.
- The session repository assumes a local canonical filesystem path for every row (`backend/db/repositories/sessions.py:59`); there is no analogue for "this row originated from a remote ingest stream".
- The telemetry exporter (`backend/services/integrations/telemetry_exporter.py`) already demonstrates a production "worker pushes batches outbound" pattern; inverting that shape (worker/server accepts inbound batches) is a viable precedent and should be evaluated as such during RQ-1.

## 3. Research Questions

### RQ-1: Ingest transport selection (NDJSON vs SSE vs WebSocket vs gRPC)

- **Question**: Which transport should the v1 ingest pipe use between the local daemon and the remote CCDash server?
- **Why it matters**: Blocks PRD scope (client/server protocol), E1 prototype, daemon client library choice, and the ADR that will anchor multi-quarter evolution.
- **Investigation approach**: Spec review of each option against criteria (operational simplicity, latency, proxy/firewall friendliness, backpressure support, client library maturity in Go and Python, alignment with existing CCDash patterns). Build E1 as a concrete comparison point. Cross-reference the outbound telemetry exporter pattern for symmetry.
- **Success criteria**: A written decision matrix scoring all four options against the criteria; an E1 benchmark for the recommended option meeting the go/no-go thresholds in Section 4.
- **Expected deliverable**: ADR-NNNN (transport decision) + benchmark table.

### RQ-2: Daemon packaging and lifecycle

- **Question**: How is the local daemon built, distributed, started, supervised, and updated?
- **Why it matters**: Determines OS-level installer work, release pipeline changes, and whether we can reuse `packages/ccdash_cli/` or need a new artifact.
- **Investigation approach**: Compare three options: (a) standalone Go binary, (b) subcommand of `packages/ccdash_cli/` (e.g., `ccdash daemon start`), (c) new runtime profile (`daemon`) reusing `backend/runtime/` bootstrap. Evaluate each against installability (pipx/homebrew/binary), auto-start (launchd/systemd/Task Scheduler), upgrade path, and CPU/memory floor.
- **Success criteria**: Decision memo with lifecycle diagrams for install → start → auto-start → status → logs → update → uninstall; E2 prototype demonstrating the chosen shape end-to-end on one OS.
- **Expected deliverable**: ADR-NNNN (daemon packaging) + E2 prototype branch.

### RQ-3: Minimum viable auth model for multi-workspace remote operation

- **Question**: What identity/scoping model replaces the single static bearer (`backend/adapters/auth/bearer.py:22`) for v1?
- **Why it matters**: Gates multi-tenant safety; blocks the PRD's deployment model section; shapes the DB schema (workspace table, token table).
- **Investigation approach**: Evaluate four options — per-workspace static tokens, OIDC/OAuth (delegated to an IdP), mTLS with per-workspace client certs, and git-identity (Entire-style). For each, enumerate the required changes to `backend/adapters/auth/`, the request-time workspace-resolution path, and the DB scoping requirement (RLS-like predicate vs explicit workspace filter in repositories). Prototype the minimal viable option in E3.
- **Success criteria**: Comparison matrix with change surface, security posture, and ops burden; E3 prototype passing a scoped-query test (workspace A cannot read workspace B sessions); migration path from today's single bearer is documented.
- **Expected deliverable**: ADR-NNNN (auth model v1) + E3 prototype.

### RQ-4: Sync engine refactor to accept remote events

- **Question**: What is the shape of a `SessionIngestSource` port that both filesystem-watching and remote-ingest implementations satisfy without regressing local mode?
- **Why it matters**: Without this port, remote ingest will either duplicate repository logic or corrupt filesystem-derived state.
- **Investigation approach**: Design the port interface in E4. Define the cursor/watermark model (new `sync_cursor` table keyed by source + project + session) that replaces mtime as the incremental driver for non-filesystem sources. Identify the minimum set of tests in `backend/tests/` that must pass unchanged to prove local-mode parity.
- **Success criteria**: Interface spec committed on a spike branch; `FilesystemSource` implementation passes all existing sync tests; stub `RemoteIngestSource` compiles and has at least one unit test demonstrating cursor advancement.
- **Expected deliverable**: ADR-NNNN (sync engine port abstraction) + E4 spike branch.

### RQ-5: Multi-project routing in a remote deployment

- **Question**: Should a remote CCDash serve multiple projects from one process (runtime routing by `x-project-id` + auth) or one process per project?
- **Why it matters**: Directly changes `RuntimeContainer` (currently one binding per process, `backend/runtime/container.py:67`) and determines deployment footprint (one pod vs N pods).
- **Investigation approach**: Spec review + E5 prototype. In E5, introduce request-scoped project resolution (header + auth-verified) and measure cold-start, steady-state RSS, and per-request latency at 10 simulated concurrent projects.
- **Success criteria**: Benchmark at 10 projects; decision on single-process vs per-project with explicit thresholds at which we would switch models.
- **Expected deliverable**: ADR-NNNN (multi-project routing) + E5 benchmark table.

### RQ-6: Failure modes and operator posture

- **Question**: How do daemon-server failures manifest, and what observability and recovery does the operator get?
- **Why it matters**: Remote ingest introduces new partial-failure classes absent from pure filesystem mode (network loss, partial batch, schema skew, reorder).
- **Investigation approach**: Enumerate failure classes (daemon offline, server 5xx, 4xx on a single event, partial batch accepted, schema version skew, clock skew between daemon and server). For each, propose detection, retry/backoff, dead-letter behavior, and surfaced signal. Extend `/api/health` and (if applicable) `/api/runtime/health` with ingest-source status.
- **Success criteria**: Failure-mode matrix with detection mechanism, recovery behavior, and operator-visible signal for every row; one manual chaos test run against E1+E2.
- **Expected deliverable**: Failure-mode matrix (decision memo).

### RQ-7: Frontend requirements for remote + live sessions

- **Question**: What must the frontend add to represent remote ingest, daemon health, and live session updates?
- **Why it matters**: Users must be able to distinguish local-filesystem sessions from remote-streamed sessions and diagnose daemon problems.
- **Investigation approach**: Inventory touchpoints in `contexts/`, `components/SessionInspector.tsx`, `services/apiClient.ts`. Decide live-update cadence: extend existing polling vs add SSE subscription for the active project. Propose minimum UI surfaces: session-source chip, daemon health indicator in the runtime badge, "live" vs "historical" session distinction.
- **Success criteria**: UI inventory + cadence decision memo; mockup-level (not final design) acceptance of the minimum indicators needed for PRD.
- **Expected deliverable**: Decision memo for frontend scope + updated PRD requirements section.

### RQ-8: Migration story for existing local-mode users

- **Question**: How do existing single-user local deployments upgrade without disruption?
- **Why it matters**: Any behavior change to the default runtime is a breaking change for every current user.
- **Investigation approach**: Propose default behavior (no-op: filesystem source remains the only source unless remote ingest is explicitly enabled). Define the opt-in flag/config. Decide whether dual-source (filesystem + remote) is supported during transition and, if so, how deduplication works given RQ-4's cursor model.
- **Success criteria**: Migration plan memo covering default behavior, opt-in switch, dual-source policy, and upgrade instructions; zero regressions demonstrated in E4's local-mode test pass.
- **Expected deliverable**: Migration plan memo.

## 4. Prototypes & Experiments

### E1: NDJSON ingest prototype (RQ-1)

- **Hypothesis**: A minimal HTTPS NDJSON POST endpoint can sustain expected session-event volume with acceptable latency and trivial client complexity.
- **Method**: Add `POST /api/v1/ingest/sessions` accepting one JSON event per line; write to a shadow `ingest_events` table (no repository integration yet). Load-test with a scripted producer.
- **Metrics**: events/sec sustained, p99 latency, reconnect behavior after forced TCP reset, memory high-water mark on server.
- **Go/no-go threshold**: ≥500 events/sec sustained on a single worker, p99 < 200ms, clean reconnect within 5s of network restore. Below threshold → re-evaluate against SSE/WebSocket in RQ-1.

### E2: Daemon spike (RQ-2)

- **Hypothesis**: A ~200-line daemon (Go or Python) can tail local JSONL session files and POST NDJSON to E1 with acceptable resource floor and correct recovery semantics.
- **Method**: Tail one JSONL file; handle rotation; on network failure, buffer to disk and resume; include an idempotency key per event.
- **Metrics**: CPU at idle (<1%), RSS at idle (<50MB), zero duplicate events after forced network blip, zero lost events after forced daemon restart.
- **Go/no-go threshold**: All metrics met on one OS (macOS or Linux) end-to-end.

### E3: Auth prototype (RQ-3)

- **Hypothesis**: Workspace-scoped static tokens are the smallest viable step from today's single bearer that supports multi-workspace ingest safely.
- **Method**: Extend `backend/adapters/auth/bearer.py` with a workspace-scoped token table (token → workspace_id). Add request-time workspace resolution to the auth dependency. Enforce workspace filtering on one representative query path.
- **Metrics**: Cross-workspace read attempt returns 403 (or empty set); token revocation takes effect within one request; migration script from legacy single bearer is idempotent.
- **Go/no-go threshold**: All three met; no regression in existing bearer auth tests.

### E4: Sync engine refactor spike (RQ-4)

- **Hypothesis**: Introducing a `SessionIngestSource` port with a `FilesystemSource` implementation is behavior-preserving for local mode.
- **Method**: On a spike branch, extract the port, reimplement the current engine as `FilesystemSource`, and add a stub `RemoteIngestSource`. Introduce a `sync_cursor` table (or equivalent).
- **Metrics**: All sync-engine tests pass unchanged; at least one new unit test covers cursor advancement for the stub remote source.
- **Go/no-go threshold**: Zero test changes required to prove local-mode parity. Any required change must be justified and reviewed.

### E5: Multi-project routing spike (RQ-5)

- **Hypothesis**: Request-scoped project resolution (auth-verified `x-project-id`) in a single process scales linearly to at least 10 concurrent projects without unacceptable latency.
- **Method**: Modify `RuntimeContainer` (or add a sibling router-scoped resolver) to pick per-request project bindings. Simulate 10 projects and measure steady-state.
- **Metrics**: Cold start ≤ current + 10%, steady-state RSS ≤ 2× single-project baseline, p99 request latency ≤ current + 25%.
- **Go/no-go threshold**: All three met → single-process routing viable; any miss → reconsider one-process-per-project.

## 5. Out of Scope for This SPIKE

- SaaS billing, metering, plan tiers.
- Organization federation, SSO chaining, cross-org sharing.
- Sub-1-second live session streaming (v1 targets "near-live", not true low-latency streaming).
- Replacing or deprecating the `local` runtime profile.
- UI polish beyond the minimum indicators required for operator clarity (attribution chip, daemon health badge).
- Entire.io ingest compatibility — covered by a separate sister SPIKE.

## 6. Deliverables Checklist

- [ ] ADR-NNNN: Ingest transport decision (NDJSON vs SSE vs WS vs gRPC) — TBD via research
- [ ] ADR-NNNN: Daemon packaging + lifecycle — TBD via research
- [ ] ADR-NNNN: Auth model v1 (workspace scoping, migration from single-tenant) — TBD via research
- [ ] ADR-NNNN: Sync engine port abstraction (`SessionIngestSource`) — TBD via research
- [ ] ADR-NNNN: Multi-project routing model — TBD via research
- [ ] Benchmark table for E1 + E5 (throughput, latency, memory) — TBD via research
- [ ] Failure-mode matrix (RQ-6 answer) — TBD via research
- [ ] Migration plan memo (RQ-8 answer) — TBD via research
- [ ] Findings summary: `docs/project_plans/SPIKEs/remote-ccdash-streaming.md`

## 7. Timeline & Owners

Suggested duration: 2 calendar weeks. Three parallel tracks:

- **Track A — Transport & ingest plumbing** (RQ-1, RQ-2, RQ-4; E1, E2, E4): backend engineer (`python-backend-engineer`).
- **Track B — Auth, routing, ops posture** (RQ-3, RQ-5, RQ-6; E3, E5): `backend-architect` with `data-layer-expert` support for workspace-scoped schema and query changes.
- **Track C — Frontend health UX & migration** (RQ-7, RQ-8): `frontend-architect`.

Mid-SPIKE checkpoint at end of week 1: Track A has E1+E2 running end-to-end; Track B has E3 enforcing scoping; Track C has draft UI inventory. End-of-SPIKE synthesis occupies the last two days.

## 8. Open Risks to Surface During Research

- **Duplicate events under poor networks**: NDJSON-over-HTTP with retries will duplicate on partial upload; the session event schema must carry an idempotency key the server can dedupe on. Probe during E1+E2.
- **Schema skew between daemon and server**: A daemon shipped in release N may post events a server at release N−1 does not understand. Probe: does the ingest endpoint version its payload contract? What happens to forward-incompatible events — drop, dead-letter, or hard-fail?
- **Cursor semantics without mtime**: The filesystem source relies on mtime; the remote source has no analogue. If the cursor model is wrong, either events are lost (cursor advances past un-ingested events) or replayed forever (cursor never advances). Probe in E4.
- **Workspace resolution bypass via `x-ccdash-project-id`**: The header is currently unauthenticated (`container.py:67`). Any auth model must ensure the header cannot widen scope beyond the authenticated workspace. Probe in E3+E5.
- **Backpressure invisibility**: NDJSON POST has no native backpressure signal beyond HTTP status; the daemon may keep buffering to disk indefinitely if the server is slow-but-accepting. Probe during E2 by throttling the server.
- **Local-mode regression via shared sync engine**: E4's port extraction changes the hottest path in the worker. A subtle regression here (e.g., cursor off-by-one) would silently lose sessions for every existing user. Require zero test changes as a hard gate.

## 9. Cross-References

- Grounding brief: `/Users/miethe/dev/homelab/development/CCDash/.claude/findings/remote-ccdash-grounding-brief.md`
- Design spec: `docs/project_plans/design-specs/remote-ccdash-streaming.md`
- Sister SPIKE (Entire.io ingest): `docs/project_plans/SPIKEs/entire-io-integration-charter.md`
- Downstream PRD (gated on this charter): `docs/project_plans/PRDs/features/remote-ccdash-streaming-v1.md`
- Downstream implementation plan (gated on PRD): `docs/project_plans/implementation_plans/features/remote-ccdash-streaming-v1.md`
