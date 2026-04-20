---
schema_version: 2
doc_type: design_spec
title: "Remote CCDash Streaming + Entire.io Integration"
description: "Umbrella design for running CCDash remotely with local-daemon session streaming, and for ingesting sessions from the Entire.io CLI. Captures shared foundational work, alternatives, and open questions."
status: draft
maturity: shaping
created: 2026-04-19
updated: 2026-04-19
feature_slug: remote-ccdash-streaming
problem_statement: "CCDash is local-first: sync engine is filesystem+mtime-coupled, auth is single-tenant, and transports are REST-pagination only. Teams want (a) a remote CCDash deployment that receives sessions streamed from developer workstations, and (b) to pull sessions captured by Entire.io's git-native CLI. Both require the same foundation: transport-neutral session ingest and de-filesystem-coupled sync."
open_questions:
  - "OQ-1: Ingest transport — HTTPS NDJSON POST vs SSE/WebSocket vs gRPC? Which for v1?"
  - "OQ-2: Daemon model — standalone binary, or reuse the CCDash CLI shell / worker runtime in 'daemon' mode?"
  - "OQ-3: Auth — per-workspace token, OIDC, mTLS, or piggyback on git identity (Entire-style)? Multi-tenant data isolation strategy (RLS vs per-tenant DBs)?"
  - "OQ-4: Sync engine refactor — introduce explicit source-of-truth abstraction (FilesystemSource / RemoteIngestSource / EntireCheckpointSource) with cursor/watermark table, or keep sync_engine filesystem-centric and add a parallel ingest path?"
  - "OQ-5: Entire ingest path — parse `entire/checkpoints/v1` branch via git plumbing, or wrap `entire` CLI commands, or wait on an upstream API? Historical vs live?"
  - "OQ-6: Session identity — Entire checkpoints have 12-hex IDs; Claude Code sessions use JSONL file paths. How do we unify in the session table without losing either's semantics?"
  - "OQ-7: Project binding — today startup-time, one project per process. Remote operation needs multi-project routing (x-project-id). Add runtime project switching, or spin per-project worker processes?"
  - "OQ-8: Frontend UX — does the dashboard show 'streaming' vs 'filesystem' sessions differently? How do we surface daemon health (connected / backed-up / disconnected)?"
  - "OQ-9: Failure modes — daemon offline, server unreachable, checkpoint branch conflicts. Retry/backoff/dead-letter strategy?"
  - "OQ-10: Entire CLI hook surface — can we register as an 'agent' in Entire's hook system to receive live events, or only consume after-the-fact from the git branch?"
explored_alternatives:
  - "Alt-A (Pull-only, conservative): Remote CCDash is read-only over VPN; no daemon; developer rsyncs/scp their session dir. Entire integration = scheduled git-fetch + branch parser. Pros: minimal new infra. Cons: no live view, no multi-tenant, doesn't solve streaming."
  - "Alt-B (HTTPS NDJSON ingest + polling, recommended): New `/api/v1/ingest/sessions` endpoint accepts NDJSON POSTs. Local daemon tails JSONL + posts. Entire ingest = periodic `git fetch` + branch parser pushing into same endpoint. Pros: simple, cache-friendly, no long-lived conns, one ingest path for both. Cons: ~seconds of latency; not truly live."
  - "Alt-C (WebSocket/SSE live streaming): Bidirectional live channel; dashboard subscribes to session updates. Pros: true live UX. Cons: substantially more infra (reconnect, backpressure, auth per socket); overkill for v1."
  - "Alt-D (Event broker): Push to Redis/Kafka/NATS; CCDash workers consume. Pros: scales, decouples producers/consumers, plays well with multi-tenant. Cons: heavy for local-first product; ops burden."
  - "Alt-E (Entire-first): Adopt Entire's git-branch model as CCDash's native session storage. Pros: free offline-sync, free Entire compat. Cons: locks us to their schema, rejects existing JSONL sources, massive migration."
related_documents:
  - ".claude/findings/remote-ccdash-grounding-brief.md"
prd_ref: null
---

# Remote CCDash Streaming + Entire.io Integration

> **This design-spec is at maturity: shaping. SPIKE findings may reshape §4 (Proposed Direction). Do not treat this as a final architecture.**

---

## 1. Context

### (a) Remote Operation Request

CCDash today runs alongside the developer's local filesystem: the sync engine watches
session directories by inode, computes mtime/hash deltas, and writes to a local DB.
Teams with more than one developer — or teams running CCDash in a shared cluster — want
a topology where a remote CCDash instance receives session data from multiple developer
workstations. This is currently impossible without manual file-sharing: the `SyncEngine`
couples directly to local path resolution (`sync_engine.py:28-63`), the file watcher
requires paths that `.exists()` locally (`file_watcher.py:94-99`), and project binding
is locked at startup time (`container.py:67`). There is no ingest API, no streaming
transport, and the auth model is a single static bearer token (`bearer.py:84-104`).

### (b) The Entire.io Opportunity

Entire.io is a recently launched, MIT-licensed Go CLI that captures AI agent sessions
git-natively: every git commit writes a checkpoint JSON to the dedicated branch
`entire/checkpoints/v1` (12-char hex ID, sharded by first two chars). Sessions span
multiple agents — Claude Code, Codex, Gemini CLI, Cursor — and include transcript,
token counts, and per-line agent/human attribution. Entire has 3,989 stars and was
last committed 2026-04-18. Its data is already on every developer machine that uses
it; CCDash could read that branch directly. The integration unlocks a second session
source with zero server-side cost — and with a user base that already cares about
session forensics.

### (c) Why These Are Bundled

Both problems share the same two blockers: the sync engine assumes a local filesystem
as its exclusive source of truth, and there is no transport-neutral session ingest path.
Building a remote-daemon ingest endpoint (POST NDJSON from workstation) and building
an Entire checkpoint branch parser (pull JSON from git) both require:

1. A `SessionIngestSource` abstraction that the sync engine can consume without touching
   a local file path.
2. A cursor/watermark table so ingest is resumable and idempotent regardless of source.
3. A session identity model that accommodates both JSONL-path-keyed (Claude Code) and
   12-hex-ID-keyed (Entire) sessions in the same `sessions` table.

Solving either problem alone would produce a half-baked abstraction. The shared
foundation should be designed once.

---

## 2. Problem Statement

CCDash's sync pipeline is tightly coupled to the local filesystem at three layers:
path resolution (`sync_engine.py:118-121`), change detection (mtime + `watchfiles`,
`file_watcher.py:30`), and session identity (`source_file` stored as canonical relative
path, `repositories/sessions.py:59`). Auth is single-tenant
(`bearer.py:84-104`). Project binding is process-scoped (`container.py:67`). There
are no streaming transports and no resumable sync state.

Three concrete user stories drive this work:

**US-1 — Remote team lead.** An engineering lead wants a shared CCDash deployment (VM,
k8s pod) where every developer's session data flows automatically. No manual copying.
The dashboard should show sessions from all team members in near-real-time, attributed
to the correct developer and project.

**US-2 — Ops / cluster deployment.** An operator runs CCDash in a container cluster
behind a load balancer. The `api` runtime (stateless HTTP) should serve reads while
one or more `worker` runtimes handle ingest from multiple remote sources — daemon
payloads and Entire checkpoints. Today a single `worker` process can only watch one
local project path.

**US-3 — Individual Entire.io user.** A solo developer already uses `entire enable` on
their repo. They want CCDash dashboards — session timelines, token forensics, workflow
diagnostics — over their Entire checkpoints without running a separate agent session
pipeline. The CCDash worker should be able to read `entire/checkpoints/v1` from the
local or remote git repo and synthesize it into the existing session model.

---

## 3. Current State (Grounded)

The following gaps are documented in the grounding brief
(`.claude/findings/remote-ccdash-grounding-brief.md`) and are reproduced here with
source citations for traceability.

**Gap 1 — Parser source_file assumptions.** `sync_engine.py:118-121` and
`document_linking.py` use `infer_project_root()` and canonical path transforms that
assume a local disk path. Remote events have no `__file__` analogue.

**Gap 2 — Sync engine fs+mtime coupling.** `sync_engine.py:1-7` and
`file_watcher.py:30` use `watchfiles` and `_file_hash()` for change detection. There
is no cursor or watermark table; remote sessions have no file identity to hash.

**Gap 3 — File watcher cannot abstract source.** `file_watcher.py:94-99` iterates
paths where `.exists()` is true locally. There is no "source changed" event protocol
independent of the filesystem.

**Gap 4 — Auth is static single-tenant bearer.** `bearer.py:84-104` reads one
env-var token. The `x-ccdash-project-id` header is an unauthenticated hint. There are
no per-workspace tokens, no OIDC, no multi-tenant isolation.

**Gap 5 — No streaming transports.** All three API surfaces (REST `/api/v1/`,
agent queries `/api/agent/`, CLI HTTP client) are request/response only. No NDJSON,
SSE, WebSocket, or gRPC. The frontend polls `/api/health`
(`bootstrap.py:180`).

**Gap 6 — Single-project-per-process binding.** `container.py:67` and
`runtime.py:107-127` bind one project at startup. Multi-tenant remote scenarios
need runtime project switching or per-project worker fanout.

**Gap 7 — No resumable sync state.** Sync state is implicit in mtime + DB rows. No
explicit cursor or watermark table, no dead-letter queue, no retry backoff policy for
failed ingest events.

**Gap 8 — Hardcoded API version.** The CLI client carries a literal
`_EXPECTED_API_VERSION="v1"` (`packages/ccdash_cli/src/ccdash_cli/runtime/client.py:68`).
No negotiation, no forward/back-compat. A new ingest endpoint must not break existing
CLI consumers.

The existing capability matrix is encouraging: `api` and `worker` runtime profiles
are already decoupled from each other (`backend/runtime/profiles.py:7-26`); the sync
engine is gated on `storage_profile.filesystem_source_of_truth`
(`container.py:169-179`); and repositories are DB-agnostic. The architecture's seams
are in the right places — they just need to be cut.

---

## 4. Proposed Direction (Shaping)

> **This section describes the shape being explored, not a committed design. SPIKE
> findings (§9) may alter it materially.**

### 4.1 Shared Foundation: SessionIngestSource Abstraction

We propose introducing a `SessionIngestSource` protocol (Python abstract base class or
`typing.Protocol`) that the `SyncEngine` consumes instead of filesystem paths directly.
Three concrete implementations would be developed in phases:

- **`FilesystemSource`** — wraps current `watchfiles`-based logic; existing local mode
  continues unchanged.
- **`RemoteIngestSource`** — receives NDJSON batches posted to a new
  `/api/v1/ingest/sessions` endpoint; translates them into `ParsedSession` objects
  with a synthetic `source_ref` (e.g., `remote:<workspace-id>:<session-id>`).
- **`EntireCheckpointSource`** — reads `entire/checkpoints/v1` branch JSON via git
  plumbing (`git show` or `git cat-file`); maps 12-hex checkpoint IDs to the session
  table; supports both historical pull and periodic incremental fetch.

All three sources push into the same `SyncEngine` upsert path
(`repositories/sessions.py:17-82`, ON CONFLICT), preserving the existing DB schema
and query layer. No changes to `repositories/` or `routers/` are anticipated at this
stage.

### 4.2 Cursor / Watermark Table

A new `ingest_cursors` table (or equivalent) would track per-source, per-project
progress: `(source_id, project_id, last_cursor, last_ingest_at, error_count)`. This
replaces the implicit mtime/hash state for remote sources and enables resumable ingest
after daemon restarts or network interruptions. The `FilesystemSource` would write its
own cursor (replacing implicit mtime state) to make the table the single source of sync
truth across all source types.

### 4.3 Transport-Neutral Ingest Endpoint

A new endpoint `POST /api/v1/ingest/sessions` would accept an NDJSON body (one
`ParsedSession`-shaped object per line). This is consistent with the existing paginated
envelope pattern in `client_v1.py:138-149` and does not require long-lived connections.
Auth on this endpoint requires a per-workspace ingest token (see OQ-3). The endpoint
would be versioned under `/v1/` so the CLI's hardcoded version string is not broken.

### 4.4 Local Daemon

A local daemon process (shape TBD per OQ-2) would run on the developer's workstation,
tail JSONL session files, and POST batches to the remote CCDash ingest endpoint. The
daemon is the logical successor to the current `worker` runtime's file-watcher; it
would use the `FilesystemSource` logic extracted from `SyncEngine` and wrap it with
HTTP transport instead of direct DB writes. It would carry a per-workspace ingest token
and support configurable flush intervals and backoff (OQ-9).

### 4.5 Pluggable Auth

The current single-tenant bearer guard (`bearer.py:84-104`) would be extended — not
replaced — with a per-workspace token table. For v1 this is likely a simple DB table
mapping `(workspace_id, hashed_token)` to a `project_id`. OIDC and mTLS are deferred
to post-v1 (see Non-Goals §7). The `x-project-id` routing header becomes authenticated
once per-workspace tokens are in place, unblocking multi-project routing (OQ-7).

### 4.6 Session Identity Unification

The `sessions` table currently uses `source_file` (canonical relative path) as a
logical key (`repositories/sessions.py:59`). We propose adding a `source_ref` column
with a URI-style scheme: `fs:<relative-path>` for filesystem sessions,
`remote:<workspace>:<id>` for daemon-ingest sessions, and `entire:<checkpoint-hex-id>`
for Entire checkpoints. The ON CONFLICT upsert key would be `(project_id, source_ref)`.
This preserves backward compatibility for existing filesystem sessions while
accommodating both new source types.

---

## 5. Alternatives Considered

**Alt-A — Pull-only, conservative.** The remote CCDash deployment is read-only; no
ingest endpoint; developers `rsync` their session directories on a schedule. Entire
integration is a cron job running `git fetch` + a branch parser that writes directly
to the local DB. This has the lowest implementation cost and zero new infra. However,
it does not address multi-tenant auth, does not enable live views, and requires manual
orchestration on each developer machine. It does not compose into a team dashboard.
Not recommended for the target use cases.

**Alt-B — HTTPS NDJSON ingest + polling (currently favored).** A new
`POST /api/v1/ingest/sessions` endpoint accepts NDJSON batches. The local daemon
tails JSONL and posts on flush intervals. Entire ingest uses the same endpoint, fed by
a periodic `git fetch` + branch parser. This approach reuses the existing HTTP
infrastructure, is stateless on the server side (no long-lived connections), is
cache-friendly, and produces a single ingest path for both remote daemon and Entire
sources. Latency is bounded by the flush interval (configurable, likely 5–30s), which
is acceptable for session forensics. This is the favored shape pending SPIKE-A findings.

**Alt-C — WebSocket / SSE live streaming.** A bidirectional channel where the
dashboard subscribes to session updates in real time. This would unlock live transcript
views (sub-second latency). However, it requires substantial new infra: per-socket
auth, reconnect/backpressure handling, and a push path in the server. The current
frontend polls `/api/health`; adding a live subscription surface is a larger UX
commitment than v1 warrants. Not recommended for v1; revisit if US-1 teams require
it.

**Alt-D — Event broker (Redis / Kafka / NATS).** Daemon and Entire parsers produce
events; CCDash workers consume from a queue. This is the most scalable architecture
and naturally supports multi-tenant fan-in. For a local-first product with small team
deployments, the operational burden (broker provisioning, schema registry, consumer
group management) outweighs the benefit. Revisit if CCDash moves toward a SaaS
multi-tenant deployment model post-v1.

**Alt-E — Entire-first: adopt `entire/checkpoints/v1` as CCDash's native session
storage.** Entire's git-branch model is elegant: merge-conflict-free, offline,
semantically linked to commits. Adopting it as CCDash's native session store would
give free Entire compat and offline sync. However, it locks CCDash to Entire's schema,
rejects the existing JSONL session source, and requires a significant migration of
existing data. It also creates a hard dependency on a third-party project. Not
recommended.

---

## 6. Open Questions

| ID | Question | Category | Blocks | Resolution Method | SPIKE |
|----|----------|----------|--------|-------------------|-------|
| OQ-1 | Ingest transport — HTTPS NDJSON POST vs SSE/WebSocket vs gRPC for v1? | Transport | §4.3, daemon design, frontend UX | SPIKE-A: transport + daemon prototyping | §9 remote charter |
| OQ-2 | Daemon model — standalone binary vs CCDash CLI / worker in daemon mode? | Ops | Daemon packaging, distribution, update model | SPIKE-A: prototype both; evaluate maintenance surface | §9 remote charter |
| OQ-3 | Auth — per-workspace token, OIDC, mTLS, or git identity piggyback? Multi-tenant isolation (RLS vs per-tenant DBs)? | Auth/Security | §4.5, multi-project routing, ingest endpoint hardening | SPIKE-A: auth threat model + ADR | §9 remote charter |
| OQ-4 | Sync engine refactor — `SessionIngestSource` abstraction vs parallel ingest path alongside unchanged `SyncEngine`? | Schema/Arch | Scope of §4.1; migration risk for existing local deployments | SPIKE-A: prototype abstraction; measure regression risk | §9 remote charter |
| OQ-5 | Entire ingest path — git plumbing, wrap `entire` CLI, or wait for upstream API? Historical vs live? | Transport | §4.1 `EntireCheckpointSource` design; OQ-10 dependency | SPIKE-B: parse branch JSON directly; assess hook surface | §9 Entire charter |
| OQ-6 | Session identity — unify 12-hex Entire IDs and JSONL-path CCDash IDs in `sessions` table without semantic loss? | Schema | §4.6, ON CONFLICT key, query compatibility | SPIKE-B: schema mapping + migration plan | §9 Entire charter |
| OQ-7 | Project binding — runtime switching vs per-project worker fanout for multi-project remote? | Arch/Ops | Multi-tenant routing, `x-project-id` auth, ops complexity | Design meeting after SPIKE-A auth findings | §9 remote charter |
| OQ-8 | Frontend UX — differentiate streaming vs filesystem sessions? Surface daemon health? | Product | Dashboard component changes, health endpoint contract | Design meeting + UX prototype after SPIKE-A | §9 remote charter |
| OQ-9 | Failure modes — retry/backoff/dead-letter for daemon offline, server unreachable, checkpoint branch conflicts? | Ops/Reliability | §4.2 cursor table design; daemon resilience spec | SPIKE-A: define retry contract; reference `SAMTelemetryClient` 10-retry pattern (`sam_telemetry_client.py:25`) | §9 remote charter |
| OQ-10 | Entire CLI hook surface — can CCDash register as an agent to receive live events, or is post-commit branch read the only path? | Transport/Ext | §4.1 `EntireCheckpointSource` live mode; OQ-5 | SPIKE-B: read Entire hook system source; probe agent interface | §9 Entire charter |

---

## 7. Non-Goals (v1)

The following are explicitly out of scope for the first release of this work:

- **SaaS multi-tenant billing and org management.** Per-workspace tokens provide
  functional isolation; a billing layer and self-serve org provisioning are post-v1.
- **Replacing or deprecating local mode.** The `FilesystemSource` / local profile
  must remain fully functional. Remote mode is additive, not a migration.
- **Rebuilding or forking Entire.io.** CCDash reads Entire's data; it does not
  reimplement checkpoint capture, git hooks, or cloud sync.
- **Real-time sub-second live transcript streaming.** Session forensics tolerate
  5–30s flush latency. True live streaming (Alt-C) is out of scope for v1.
- **Cross-org or cross-cluster federation.** Multiple CCDash deployments do not sync
  with each other. Scoped to single-cluster multi-project in v1.
- **gRPC or event-broker transports.** Alt-D (broker) and the gRPC variant of Alt-C
  are out of scope pending post-v1 scale evidence.
- **Entire CLI modification or upstream contribution.** CCDash is a consumer of
  Entire's git branch data. We do not propose changes to Entire's codebase.

---

## 8. Risks

| # | Risk | Type | Likelihood | Impact | Mitigation |
|---|------|------|-----------|--------|-----------|
| R-1 | `SyncEngine` refactor breaks existing local-mode deployments | Technical | Medium | High | Keep `FilesystemSource` as a pass-through wrapper; gate new code behind `CCDASH_INGEST_SOURCE` feature flag; add regression tests against existing `test` runtime profile |
| R-2 | Entire `entire/checkpoints/v1` branch schema changes without notice (MIT, active project) | Technical/Ext | Medium | Medium | Pin against a versioned snapshot in SPIKE-B; add schema-validation step to `EntireCheckpointSource`; emit warning and skip on unknown fields rather than crash |
| R-3 | Per-workspace auth token surface introduces credential leakage if stored in daemon config | Security | Low-Medium | High | Token stored only in OS keychain or env var; never written to project files; rotate on compromise; scope token to write-only ingest (no read) |
| R-4 | Cursor/watermark table absent causes duplicate session rows on daemon restart | Technical | High (if skipped) | Medium | Cursor table is a prerequisite for the ingest endpoint, not an optimization; implement before any external ingest |
| R-5 | Project binding refactor (OQ-7) required before multi-project remote is usable; underestimated scope | Ops/Schedule | Medium | Medium | SPIKE-A scopes this explicitly; if complex, v1 ships per-project worker processes (simpler fanout) rather than runtime switching |
| R-6 | Daemon distribution and update lifecycle is underestimated for Go/Python binary | Ops | Medium | Low-Medium | Prefer reusing the existing CCDash CLI shell in daemon mode (Alt-B daemon shape) to avoid new distribution channel; evaluate in SPIKE-A |
| R-7 | Entire's agent hook system is not a public API (OQ-10); live ingest not achievable | Product | Medium | Low | Fallback to periodic branch poll (already sufficient for US-3); live mode is a stretch goal, not a v1 requirement |
| R-8 | NDJSON POST payloads grow large for long sessions; timeout or request size limits on reverse proxies | Technical | Low | Medium | Enforce max-lines-per-batch in daemon (e.g., 500 lines); server-side request size limit documented in operator guide |

---

## 9. Downstream SPIKEs

Two time-boxed SPIKEs should precede PRD authoring. Their charters are scaffolded as
drafts alongside this spec.

**SPIKE-A — Remote Streaming & Daemon**
Path: `docs/project_plans/SPIKEs/remote-ccdash-streaming-charter.md`

Covers: transport selection (OQ-1), daemon model (OQ-2), auth threat model and
per-workspace token design (OQ-3), `SessionIngestSource` abstraction scope and
migration risk (OQ-4), project binding approach for multi-project remote (OQ-7),
frontend health surface (OQ-8), and retry/backoff contract for daemon resilience (OQ-9).

Deliverables: transport recommendation (ADR), daemon packaging decision, auth ADR,
cursor/watermark table schema, scope estimate for sync engine refactor.

**SPIKE-B — Entire.io Integration**
Path: `docs/project_plans/SPIKEs/entire-io-integration-charter.md`

Covers: `entire/checkpoints/v1` branch JSON schema (full field inventory), git
plumbing feasibility vs CLI wrapping (OQ-5), session identity mapping strategy (OQ-6),
and hook surface probe for live ingest possibility (OQ-10).

Deliverables: `EntireCheckpointSource` data contract, `source_ref` scheme for Entire
sessions, schema-migration plan for `sessions` table, go/no-go on live hook ingest.

---

## 10. Next Steps

Both SPIKEs are scaffolded as drafts. The sequencing is:

1. **Run SPIKE-A and SPIKE-B in parallel** (recommended 1–2 weeks each).
2. **Hold a design meeting** after SPIKE findings land to resolve OQ-3 (auth), OQ-4
   (abstraction vs parallel path), and OQ-7 (project binding).
3. **Update §4 (Proposed Direction)** with findings; promote any resolved open
   questions to ADRs.
4. **Promote this spec to `maturity: ready`** and set `prd_ref` once both SPIKEs have
   landed findings and §4 reflects the resolved direction.
5. **Scaffold PRD and implementation plan** after promotion; the implementation plan
   should phase work as: (a) cursor table + `SessionIngestSource` abstraction,
   (b) ingest endpoint + daemon, (c) Entire checkpoint source, (d) auth hardening +
   multi-project routing.

**Gate:** PRD and implementation plan are scaffolded as drafts; promote to
`maturity: ready` and set `prd_ref` after both SPIKEs land findings.
