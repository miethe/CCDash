---
schema_version: 2
doc_type: prd
title: "Remote CCDash Streaming + Entire.io Integration"
description: "Run CCDash as a remote service that ingests session data from local developer daemons over a transport-neutral channel, and add Entire.io git-branch checkpoints as a first-class session source. Draft pending SPIKE findings."
status: draft
created: 2026-04-19
updated: 2026-04-19
feature_slug: remote-ccdash-streaming
feature_version: "v1"
priority: high
risk_level: high
owner: nick
contributors: []
prd_ref: null
plan_ref: null
related_documents:
  - docs/project_plans/design-specs/remote-ccdash-streaming.md
  - docs/project_plans/SPIKEs/remote-ccdash-streaming-charter.md
  - docs/project_plans/SPIKEs/entire-io-integration-charter.md
  - .claude/findings/remote-ccdash-grounding-brief.md
spike_refs:
  - docs/project_plans/SPIKEs/remote-ccdash-streaming-charter.md
  - docs/project_plans/SPIKEs/entire-io-integration-charter.md
adr_refs: []
changelog_required: true
deferred_items_spec_refs: []
findings_doc_ref: null
commit_refs: []
pr_refs: []
files_affected: []
---

# Remote CCDash Streaming + Entire.io Integration

> **⚠️ DRAFT — gated on SPIKE-A (`remote-ccdash-streaming-charter.md`) and SPIKE-B (`entire-io-integration-charter.md`) findings. Do not promote to `approved` or begin implementation until both SPIKEs land all deliverables and this document is re-baselined against their ADRs.**

---

# Feature brief & metadata

**Feature name:** Remote CCDash Streaming + Entire.io Integration

**Filepath name:** `remote-ccdash-streaming-v1`

**Date:** 2026-04-19

**Author:** Claude Sonnet 4.6 (claude-code)

**Related EPICs / PRD IDs:** N/A (first version)

**Related documents:**
- Design spec: `docs/project_plans/design-specs/remote-ccdash-streaming.md`
- SPIKE-A charter: `docs/project_plans/SPIKEs/remote-ccdash-streaming-charter.md`
- SPIKE-B charter: `docs/project_plans/SPIKEs/entire-io-integration-charter.md`
- Grounding brief: `.claude/findings/remote-ccdash-grounding-brief.md`

---

## 1. Executive summary

CCDash today is a local-first tool: its sync engine is filesystem-and-mtime coupled, auth is single-tenant, and there is no mechanism to receive session data from a remote source. This feature delivers two complementary tracks on a single shared foundation. Track 1 (remote operation) enables teams to run one CCDash server and have N developer workstations stream their session data to it via a transport-neutral `SessionIngestSource` port — unlocking shared team dashboards, multi-project routing, and workspace-scoped auth without disrupting any existing local-mode workflow. Track 2 (Entire.io integration) treats Entire's `entire/checkpoints/v1` git branch as a first-class CCDash session source, letting developers who already use the Entire.io CLI obtain CCDash's session forensics — token analysis, workflow diagnostics, session timelines — over their existing checkpoint data with no additional agent pipeline.

Both tracks require exactly the same two foundational changes: (a) a `SessionIngestSource` abstraction that decouples the sync engine from filesystem paths, and (b) a cursor/watermark table that makes ingest resumable and idempotent regardless of source. By building that shared foundation once, CCDash gains an extensible ingest architecture that can accommodate future session sources (other AI tools, cloud agents) with no further core changes.

**Priority:** HIGH

**Key outcomes:**
- Outcome 1: Teams can run a shared remote CCDash instance fed by multiple developer daemons.
- Outcome 2: Entire.io users get full CCDash forensics over their checkpoint data.
- Outcome 3: Existing local-mode users see zero behavior or performance change.

---

## 2. Context & background

### Current state

From the grounding brief (`.claude/findings/remote-ccdash-grounding-brief.md`, Leg 1) and design-spec §1–3, post-PR-#30 CCDash has cleanly separated runtime profiles (`local`, `api`, `worker`, `test`) and DB-agnostic repositories, but the sync pipeline remains tightly filesystem-coupled at every layer.

Eight concrete gaps block remote operation and Entire integration (all cited to source files):

| Gap | Location | Description |
|-----|----------|-------------|
| 1 | `sync_engine.py:118-121`, `document_linking.py` | `infer_project_root()` + canonical path transforms assume a local disk path; remote events have no `__file__` analogue |
| 2 | `sync_engine.py:1-7`, `file_watcher.py:30` | `watchfiles` + `_file_hash()` change detection; no cursor/watermark table; remote sessions lack file identity |
| 3 | `file_watcher.py:94-99` | Iterates only paths where `.exists()` locally; no abstract "source changed" event protocol |
| 4 | `bearer.py:84-104` | One env-var static bearer token; `x-ccdash-project-id` is an unauthenticated hint; no per-workspace tokens |
| 5 | All routers | REST pagination only; no NDJSON, SSE, WebSocket, or gRPC; frontend polls `/api/health` |
| 6 | `container.py:67`, `runtime.py:107-127` | Single-project-per-process binding at startup; no runtime project switching |
| 7 | Sync state implicit in mtime + DB rows | No cursor/watermark table, no dead-letter queue, no retry backoff |
| 8 | `packages/ccdash_cli/…/client.py:68` | Hardcoded `_EXPECTED_API_VERSION="v1"`; no negotiation; new ingest endpoint must not break CLI consumers |

### Architectural context

CCDash follows a layered architecture: routers → services/repositories → DB. The `api` runtime profile is already stateless HTTP-only; the `worker` profile handles background ingest. Repositories are DB-agnostic (SQLite + Postgres). The seams exist — they need to be cut and a transport-neutral port inserted upstream of the sync engine.

### Entire.io context

Entire.io (https://github.com/entireio/cli) is an MIT-licensed, Go CLI with ~4k stars (last commit 2026-04-18). It captures AI agent sessions git-natively: every checkpoint is a JSON file on branch `entire/checkpoints/v1`, sharded by first two chars of a 12-hex ID. Sessions span Claude Code, Gemini CLI, Cursor, Codex, and Copilot. There is no documented third-party consumer API; the primary ingest path for CCDash is reading the branch JSON directly via git plumbing. Details in grounding brief Leg 2.

---

## 3. Problem statement

CCDash's sync pipeline is filesystem-and-mtime coupled at path resolution (`sync_engine.py:118-121`), change detection (`file_watcher.py:30`), and session identity (`repositories/sessions.py:59`). Auth is single-tenant (`bearer.py:84-104`). Project binding is process-scoped (`container.py:67`). There are no streaming transports and no resumable sync state. The quantified pain: today zero remote-team sessions are visible in any shared dashboard, and zero Entire.io checkpoints are ingestible by CCDash.

Three user stories drive this work (from design-spec §2):

**US-1 — Remote team lead.** As an engineering lead, when I deploy CCDash on a shared VM, my developers' session data does not flow to it automatically — I see zero team sessions instead of a shared timeline. Expected: every developer's sessions appear in the dashboard within seconds of capture, attributed to the correct developer and project.

**US-2 — Ops / cluster deployment.** As an operator running CCDash in a container cluster, when multiple developer streams arrive simultaneously, a single `worker` process can only watch one local project path — I must run N processes per project manually. Expected: one `worker` runtime handles ingest from M remote sources across N projects without per-process project binding.

**US-3 — Individual Entire.io user.** As a solo developer using `entire enable`, when I want CCDash forensics over my checkpoint data, there is no path from `entire/checkpoints/v1` into the CCDash session model. Expected: the CCDash worker reads my git branch directly and renders full session timelines, token analysis, and workflow diagnostics with no additional pipeline.

---

## 4. Goals & success metrics

**G1 — Remote team ingest.** A team can run a single CCDash server (Postgres backend) and have N developer daemons stream sessions to it.

**G2 — Entire checkpoint ingest.** CCDash ingests Entire checkpoints from one or more git repos and renders them as sessions.

**G3 — Local-mode backward compatibility.** Existing local-mode users see zero behavior change.

**G4 — Multi-tenant safety.** Workspace A can never see workspace B's data.

| Metric | Baseline | Target | Method |
|--------|----------|--------|--------|
| Daemon install → first session visible | N/A (feature does not exist) | ≤5 min | Timed end-to-end test |
| Ingest latency p50 (daemon flush → DB row) | N/A | ≤10 s | Load test benchmark (SPIKE-A E1) |
| Entire checkpoint → visible p50 | N/A | ≤30 s | Branch-parse latency test (SPIKE-B E2) |
| Well-formed Entire checkpoint JSON parsed | 0% | 100% | Parser unit test corpus |
| Local-mode regression rate | 0 failures | 0 failures | Existing sync test suite + E4 gate |
| Cross-workspace data leak | 0 | 0 | Dedicated security test suite (E3) |

---

## 5. User personas & journeys

**Primary — Remote team lead (US-1)**
- Role: Engineering lead or DevOps, deploys shared infra
- Needs: Zero-configuration daemon on each developer machine; shared dashboard with per-developer attribution
- Pain: Today must manually rsync session dirs; no live view; no team aggregation

**Secondary — Cluster operator (US-2)**
- Role: Platform/SRE, manages CCDash in k8s or Compose
- Needs: One CCDash API pod, one or more worker pods, multi-project routing without per-project container
- Pain: Single-project-per-process binding forces one container per project

**Tertiary — Individual Entire.io user (US-3)**
- Role: Solo developer using Entire CLI
- Needs: CCDash session analytics over existing git-branch checkpoints without a separate pipeline
- Pain: Two separate tools; no cross-tool session visibility

### System flow (target state preview)

```
Developer workstation
  └─ daemon (tails JSONL) ──HTTPS POST NDJSON──► CCDash API (api profile)
                                                       │
                                          auth: per-workspace token
                                                       │
                                               ingest worker
                                                       │
                                          SessionIngestSource port
                                           ┌──────────┴──────────┐
                                  FilesystemSource        RemoteIngestSource
                                           │                      │
                                           └──────────┬──────────┘
                                                  SyncEngine
                                                       │
                                                  Postgres DB
                                                       │
                                              CCDash Web (reads)

git repo (entire/checkpoints/v1 branch)
  └─ EntireCheckpointSource ──────────────────────────► same SessionIngestSource port ──► Postgres
       (worker job: periodic git fetch + branch parser)
```

---

## 6. Requirements

### 6.1 Functional requirements

| ID | Requirement | Priority | SPIKE gate | Notes |
|:--:|-------------|:--------:|-----------|-------|
| FR-1 | New `POST /api/v1/ingest/sessions` endpoint accepts NDJSON body (one `ParsedSession`-shaped object per line) and writes through the `SessionIngestSource` port | Must | SPIKE-A: RQ-1 (transport), RQ-4 (port) | Endpoint versioned under `/v1/` to avoid breaking CLI `_EXPECTED_API_VERSION` |
| FR-2 | `SessionIngestSource` protocol abstraction; `FilesystemSource`, `RemoteIngestSource`, `EntireCheckpointSource` implementations | Must | SPIKE-A: RQ-4 (port shape); SPIKE-B: RQ-2 (Entire path) | `FilesystemSource` must be a pass-through wrapper preserving all existing behavior |
| FR-3 | `ingest_cursors` table (or equivalent) keyed `(source_id, project_id)` storing `last_cursor`, `last_ingest_at`, `error_count`; replaces implicit mtime/hash state for non-filesystem sources | Must | SPIKE-A: RQ-4 (cursor model) | `FilesystemSource` also writes cursor to make it the single source of sync truth |
| FR-4 | Local daemon process tails JSONL session files and POSTs NDJSON batches to `FR-1` endpoint; per-workspace ingest token; configurable flush interval and reconnect/backoff | Must | SPIKE-A: RQ-1, RQ-2 (daemon shape), RQ-6 (failure modes) | Shape (standalone binary vs `ccdash daemon` subcommand) decided by SPIKE-A ADR |
| FR-5 | Workspace-scoped auth: per-workspace token table `(workspace_id, hashed_token)` extends (not replaces) existing bearer guard; `x-project-id` routing header becomes authenticated once workspace token is in place | Must | SPIKE-A: RQ-3 (auth model ADR) | Migration from legacy single bearer must be idempotent; OIDC and mTLS deferred |
| FR-6 | Multi-project routing: remote deployment routes ingest events to the correct project via authenticated `x-project-id` header; resolution model (single-process vs per-process fanout) per SPIKE-A ADR | Must | SPIKE-A: RQ-5 (multi-project ADR) | |
| FR-7 | `EntireCheckpointSource`: reads `entire/checkpoints/v1` branch JSON via git plumbing; maps 12-hex checkpoint IDs to `source_ref = entire:<hex-id>`; supports historical pull and periodic incremental fetch | Must | SPIKE-B: RQ-1 (schema), RQ-2 (ingest path ADR), RQ-3 (live-loop) | |
| FR-8 | Session identity unification: `source_ref` URI-scheme column added to `sessions` table (`fs:<path>`, `remote:<workspace>:<id>`, `entire:<hex-id>`); ON CONFLICT upsert key becomes `(project_id, source_ref)` | Must | SPIKE-B: RQ-4 (identity schema ADR) | Backfill existing rows with `fs:` prefix; zero-downtime migration |
| FR-9 | Session-source attribution in all session DTOs: `source_type` field (`filesystem \| remote_ingest \| entire_checkpoint`) returned by `/api/v1/sessions` and agent query surfaces | Should | SPIKE-A: RQ-7 (frontend scope) | |
| FR-10 | Dashboard health indicator: source attribution chip per session card; daemon health badge (`connected / backed-up / disconnected`) in runtime header; fed by extended `/api/health` response | Should | SPIKE-A: RQ-7 (frontend scope memo) | Minimum viable per RQ-7 decision memo |
| FR-11 | Entire commit/checkpoint linkage: `session_commit_links(session_id, commit_sha, link_source)` table populated from `Entire-Checkpoint:` git commit trailers | Could | SPIKE-B: RQ-6 (linkage schema) | Enables "sessions that produced PR #N" view |
| FR-12 | Migration documentation: upgrade guide for local-mode users; daemon install → config → verify workflow; operator deployment guide (docker-compose + helm-friendly patterns) | Must | SPIKE-A: RQ-8 (migration memo) | |

### 6.2 Non-functional requirements

**Performance:**
- Ingest throughput: target set by SPIKE-A E1 go/no-go threshold (≥500 events/sec sustained, p99 ≤200 ms per the SPIKE charter). Final NFR pinned after SPIKE-A lands.
- Daemon resource floor: ≤1% CPU at idle, ≤50 MB RSS at idle (SPIKE-A E2 threshold).
- Branch parse time: 1,000 Entire checkpoints cold-parsed in ≤15 s (SPIKE-B E1 threshold).

**Security:**
- Workspace A requests with workspace A's token must never return workspace B's data; enforced by RLS predicate or explicit workspace filter in all repositories touching session data (SPIKE-A: RQ-3 E3 gate).
- Ingest token stored only in OS keychain or env var on the developer workstation; never written to project files.
- Ingest endpoint write-scoped token (no read access); token rotation must take effect within one request.
- Dedicated security test suite covering cross-workspace isolation (FR-5 gate).

**Reliability:**
- Daemon reconnect within ≤5 s of network restore (SPIKE-A E1 threshold).
- Idempotent ingest: each event carries an idempotency key; duplicate POST after retry must not create a duplicate session row.
- Dead-letter behavior and operator-visible backpressure signal per SPIKE-A RQ-6 failure-mode matrix.
- `FilesystemSource` must pass all existing sync tests unchanged (SPIKE-A E4 hard gate: zero test changes).

**Deployment:**
- `api` and `worker` runtime profiles remain independently deployable; docker-compose and helm-friendly topology documented.
- Postgres required for any production remote deployment; SQLite supported for local mode only.
- Feature flag `CCDASH_INGEST_SOURCE` gates new code paths; disabling returns exact current behavior.

**Observability:**
- Extended `/api/health` response includes per-source ingest status (SPIKE-A RQ-6).
- OTEL spans for all ingest operations; structured logs with `workspace_id`, `source_type`, `trace_id`.
- Audit log for workspace token issuance and revocation.

---

## 7. Scope

### In scope

- Transport-neutral `SessionIngestSource` port and `FilesystemSource` / `RemoteIngestSource` / `EntireCheckpointSource` implementations
- `POST /api/v1/ingest/sessions` NDJSON endpoint
- Daemon binary or `ccdash daemon` CLI subcommand (shape per SPIKE-A ADR)
- `ingest_cursors` watermark table
- Workspace-scoped token auth (`bearer.py` extension)
- Multi-project routing (single-process or per-project worker per SPIKE-A ADR)
- Entire `entire/checkpoints/v1` branch parser (`EntireCheckpointSource`)
- `source_ref` schema migration on `sessions` table
- Session-source attribution in DTOs and UI (source chip, daemon health badge)
- Migration documentation and operator deployment guide

### Out of scope (v1)

- SaaS billing, self-serve org provisioning, usage metering
- Sub-second live transcript streaming (Alt-C WebSocket / SSE; deferred post-v1)
- Bidirectional CCDash → Entire sync (read-only integration in v1)
- Cloud-Entire backend integration (`ENTIRE_API_BASE_URL`)
- Record-level merge of Claude Code JSONL with Entire checkpoints (overlap dedup beyond `source_type` labeling)
- Cross-cluster CCDash federation (multiple CCDash deployments syncing each other)
- OIDC, OAuth, mTLS auth (static per-workspace tokens only in v1)
- Event broker transports (Redis / Kafka / NATS)
- gRPC transport
- Entire CLI modification or upstream contribution

---

## 8. Dependencies & assumptions

### External dependencies

- **Entire.io CLI** (`github.com/entireio/cli`, MIT): `entire/checkpoints/v1` branch layout must be stable enough to parse without a public schema contract. Schema validated in SPIKE-B RQ-1; parser emits warning and skips on unknown fields rather than crashing (R-2 mitigation).
- **pygit2 / libgit2** (or `dulwich` fallback): required for Python branch parsing in `EntireCheckpointSource`. Platform portability (macOS/Linux) validated in SPIKE-B E1.
- **Postgres** (production remote deployments): assumed for any multi-tenant deployment. SQLite is not supported for remote multi-workspace operation.

### Internal dependencies

- **SPIKE-A** must land all 5 ADRs before implementation begins: transport (RQ-1), daemon packaging (RQ-2), auth model (RQ-3), sync engine port abstraction (RQ-4), multi-project routing (RQ-5). SPIKE-A is a hard gate on Phases 2–5.
- **SPIKE-B** must land schema doc + ingest path ADR + session identity ADR before Phase 5 (Entire parser) begins.
- **PR #30 runtime modularization** (merged, commit 451f958): assumed stable; `api`/`worker` profile separation is a prerequisite for the remote deployment topology.

### Assumptions

- Postgres is available and configured (`CCDASH_DB_BACKEND=postgres`) for any production remote deployment; SQLite remains for local mode.
- Entire's `entire/checkpoints/v1` branch layout is stable at the `v1` path level for the duration of this feature (assessed in SPIKE-B; schema-version check added at parse time).
- The `CCDASH_INGEST_SOURCE` feature flag defaults to `filesystem`, preserving all current behavior for users who do not opt in.
- Daemon distribution reuses existing release infrastructure (pip / pipx or binary); no new distribution channel unless SPIKE-A RQ-2 evaluation requires one.

### Feature flags

- `CCDASH_INGEST_SOURCE`: `filesystem` (default) | `remote` | `entire` | `all`; gates new ingest code paths.
- `CCDASH_REMOTE_INGEST_ENABLED`: boolean shorthand for enabling the `RemoteIngestSource` path.

---

## 9. Risks & mitigations

From design-spec §8 plus draft-stage additions:

| # | Risk | Impact | Likelihood | Mitigation |
|---|------|:------:|:----------:|-----------|
| R-1 | `SyncEngine` refactor breaks local-mode deployments | High | Medium | `FilesystemSource` is a pass-through wrapper; gated behind `CCDASH_INGEST_SOURCE` flag; E4 hard gate (zero test changes) |
| R-2 | Entire `entire/checkpoints/v1` schema changes without notice (MIT, active project) | Medium | Medium | Pin against SPIKE-B schema snapshot; schema-validation step in `EntireCheckpointSource`; skip + warn on unknown fields |
| R-3 | Per-workspace ingest token credential leakage via daemon config | High | Low–Medium | Token stored only in OS keychain or env var; write-only scope; rotate on compromise |
| R-4 | Absent cursor table causes duplicate rows on daemon restart | Medium | High (if skipped) | Cursor table is a prerequisite for ingest endpoint; implemented before any external ingest (FR-3 blocks FR-1) |
| R-5 | Project binding refactor (OQ-7) underestimated in scope | Medium | Medium | SPIKE-A RQ-5 explicitly sizes this; fallback to per-project worker processes if single-process routing proves risky |
| R-6 | Daemon distribution lifecycle underestimated | Low–Medium | Medium | Prefer reusing `ccdash` CLI shell as `ccdash daemon` subcommand; evaluated in SPIKE-A RQ-2 |
| R-7 | Entire's agent hook system is not a public API; live ingest unreachable | Low | Medium | Fallback to periodic branch poll (SPIKE-B E2); live mode is stretch goal, not v1 requirement |
| R-8 | NDJSON POST payload size exceeds reverse-proxy limits for long sessions | Medium | Low | Max-lines-per-batch enforced in daemon (≤500 lines); server-side request size limit documented |
| R-9 | SPIKE outcomes materially change transport or auth decisions invalidating PRD sections 6–8 | High | Medium | Explicit re-baseline of this PRD after both SPIKEs land; promote from `draft` only after re-baseline |
| R-10 | Schema skew between daemon version N and server version N−1 | Medium | Medium | Ingest endpoint validates payload version field; forward-incompatible events dead-lettered, not hard-failed |

---

## 10. Target state

After delivery, CCDash supports three ingest topologies simultaneously:

**Topology 1 — Unchanged local mode**
```
Developer workstation (filesystem)
  └─ FilesystemSource (watchfiles) ──► SyncEngine ──► SQLite/Postgres ──► CCDash Web
```

**Topology 2 — Remote team deployment**
```
Developer workstation
  └─ daemon (tails JSONL) ──HTTPS POST NDJSON──► /api/v1/ingest/sessions
                                                   │  (auth: per-workspace token)
                                                   ▼
                                         RemoteIngestSource
                                                   │
                                          SessionIngestSource port
                                                   │
                                            SyncEngine + ingest_cursors
                                                   │
                                              Postgres
                                                   │
                                           CCDash Web (api profile, stateless)
```

**Topology 3 — Entire checkpoint ingest**
```
git repo
  └─ entire/checkpoints/v1 branch
       └─ EntireCheckpointSource (periodic git fetch + branch parser)
                │   (worker job)
                ▼
      SessionIngestSource port ──► SyncEngine + ingest_cursors ──► Postgres ──► CCDash Web
```

The dashboard presents all three source types in a unified session list. Each session card carries a `source_type` chip (`filesystem`, `remote`, `entire`). The runtime header shows a daemon health badge for operators who have configured the remote topology. The Entire checkpoint source surfaces full CCDash forensics — token counts, workflow diagnostics, session timelines — over checkpoint data with no additional agent pipeline.

Existing local-mode users see no change unless they explicitly set `CCDASH_INGEST_SOURCE`.

---

## 11. Acceptance criteria

| # | Criterion | Test method |
|:--:|-----------|-------------|
| AC-1 | `POST /api/v1/ingest/sessions` with a valid workspace token and well-formed NDJSON body returns 200 and a session row appears in the DB within p50 ≤10 s | Integration test + load benchmark |
| AC-2 | `POST /api/v1/ingest/sessions` with workspace A's token cannot create or read sessions in workspace B; cross-workspace attempt returns 403 | Security test suite (per SPIKE-A E3 gate) |
| AC-3 | All existing sync-engine tests pass without modification after `FilesystemSource` port extraction (SPIKE-A E4 hard gate) | CI test run on spike branch |
| AC-4 | Daemon reconnects within ≤5 s of forced TCP reset and zero events are lost or duplicated after reconnect (idempotency key dedup) | Chaos test (SPIKE-A E2) |
| AC-5 | 100% of well-formed Entire checkpoint JSON (≥3 agents per SPIKE-B E3 corpus) parsed and visible as CCDash sessions within ≤30 s of branch fetch | Branch parser integration test |
| AC-6 | `source_ref` migration backfill runs to completion on a 10k-session SQLite DB with zero downtime (no table lock held for >1 s) | Migration test |
| AC-7 | Session list API returns `source_type` field on every session; frontend session card renders source chip correctly for all three source types | API + component test |
| AC-8 | `/api/health` response includes per-source ingest status; daemon health badge reflects `connected / backed-up / disconnected` states in the UI | Health endpoint + UI E2E test |
| AC-9 | Daemon resource floor at idle: ≤1% CPU, ≤50 MB RSS on macOS and Linux (per SPIKE-A E2 thresholds) | E2 benchmark |
| AC-10 | Full local-mode backward-compat test suite passes with `CCDASH_INGEST_SOURCE=filesystem` (default); no regressions in existing integration or E2E tests | CI test run |
| AC-11 | Transport decision, daemon packaging, auth model, sync engine port, and multi-project routing are each recorded in a numbered ADR (per SPIKE-A deliverables checklist) | ADR files present and linked in `adr_refs` |
| AC-12 | Operator deployment guide documents docker-compose topology (api pod + worker pod + Postgres) and daemon install → configure → verify workflow | Docs review |

---

## 12. Implementation phases (preview)

Full breakdown in `docs/project_plans/implementation_plans/features/remote-ccdash-streaming-v1.md` (created after PRD approval).

| Phase | Title | Key outputs | Gate / notes |
|:-----:|-------|-------------|-------------|
| 1 | SPIKE execution | SPIKE-A + SPIKE-B findings, 5 ADRs from SPIKE-A, 2 ADRs from SPIKE-B | **Hard gate** — Phases 2–7 cannot begin until all SPIKE deliverables land |
| 2 | Sync-engine refactor | `SessionIngestSource` port, `FilesystemSource`, `ingest_cursors` table, zero regression on E4 | Unlocks Phases 3 and 5 in parallel |
| 3 | Ingest endpoint + daemon | `POST /api/v1/ingest/sessions`, daemon binary/subcommand, SPIKE-A ADR transport | Depends on Phase 2 |
| 4 | Auth + multi-project routing | Workspace token table, `bearer.py` extension, authenticated `x-project-id` routing, security test suite | Depends on Phase 2; can overlap with Phase 3 |
| 5 | Entire branch parser | `EntireCheckpointSource`, `source_ref` schema migration, `session_commit_links` sketch | Depends on Phase 2; needs SPIKE-B ADRs |
| 6 | Frontend + health | Source attribution chip, daemon health badge, `/api/health` extension, UI E2E tests | Depends on Phases 3–5 |
| 7 | Hardening + docs | Chaos tests, failure-mode matrix validation, operator guide, migration docs, CHANGELOG entry | Final gate before promotion to `approved` |

---

## 13. Open questions

All ten open questions from design-spec §6 are reproduced here with the SPIKE RQ that resolves each.

| ID | Question | Resolved by |
|----|----------|-------------|
| OQ-1 | Ingest transport — HTTPS NDJSON POST vs SSE/WebSocket vs gRPC for v1? | SPIKE-A: RQ-1 (transport decision matrix + ADR); E1 benchmark |
| OQ-2 | Daemon model — standalone binary vs `ccdash` CLI subcommand vs worker runtime in daemon mode? | SPIKE-A: RQ-2 (lifecycle memo + ADR); E2 prototype |
| OQ-3 | Auth — per-workspace token, OIDC, mTLS, or git identity? Multi-tenant isolation (RLS vs per-tenant DBs)? | SPIKE-A: RQ-3 (auth ADR + E3 prototype); scoping model confirmed by E3 gate |
| OQ-4 | Sync engine refactor — `SessionIngestSource` abstraction vs parallel ingest path alongside unchanged `SyncEngine`? | SPIKE-A: RQ-4 (port abstraction ADR); E4 zero-test-change gate |
| OQ-5 | Entire ingest path — git plumbing, wrap `entire` CLI, or wait for upstream API? Historical vs live? | SPIKE-B: RQ-2 (ingest path ADR); E1 branch-parser prototype |
| OQ-6 | Session identity — unify 12-hex Entire IDs and JSONL-path CCDash IDs in `sessions` table without semantic loss? | SPIKE-B: RQ-4 (identity schema ADR); migration plan |
| OQ-7 | Project binding — runtime switching vs per-project worker fanout for multi-project remote? | SPIKE-A: RQ-5 (multi-project routing ADR); E5 benchmark |
| OQ-8 | Frontend UX — differentiate streaming vs filesystem sessions? Surface daemon health? | SPIKE-A: RQ-7 (frontend scope decision memo); UX prototype |
| OQ-9 | Failure modes — retry/backoff/dead-letter for daemon offline, server unreachable, checkpoint branch conflicts? | SPIKE-A: RQ-6 (failure-mode matrix); chaos test in E1+E2 |
| OQ-10 | Entire CLI hook surface — can CCDash register as an agent to receive live events, or is post-commit branch read the only path? | SPIKE-B: RQ-7 (hook registration probe); E5 agent registration attempt |

---

## 14. Deferred items & findings policy

The following items are out of scope for v1 and require follow-on design specs before they can be planned. Each deferred item generates a `DOC-006` design-spec authoring task in Phase 7.

| # | Deferred item | Reason deferred | DOC-006 task (Phase 7) |
|:--:|---------------|----------------|----------------------|
| D-1 | Sub-second live transcript streaming (Alt-C WebSocket/SSE) | Substantially more infra than v1 warrants; forensics tolerate 5–30 s flush | Author `design-specs/live-session-streaming.md` |
| D-2 | Bidirectional CCDash → Entire sync | Read-only integration sufficient for v1; write-back raises schema ownership questions | Author `design-specs/entire-bidirectional-sync.md` |
| D-3 | Record-level merge of Claude Code JSONL + Entire checkpoints | Overlap dedup at the record level requires agent-specific logic; SPIKE-B RQ-8 scopes coexistence policy only | Author `design-specs/cross-source-session-merge.md` |
| D-4 | Cloud-Entire backend integration (`ENTIRE_API_BASE_URL`) | Requires Entire API key and paid backend; local-only ingest sufficient for v1 | Author `design-specs/entire-cloud-integration.md` |
| D-5 | SaaS multi-tenant billing, org management, plan tiers | Out of scope for local-first product in v1 | Author `design-specs/saas-multi-tenant.md` |
| D-6 | OIDC / OAuth / mTLS auth | Static per-workspace tokens sufficient for v1 team deployments | Author `design-specs/oidc-auth-integration.md` after v1 auth lands |

**Findings doc ref:** `findings_doc_ref: null` — to be populated if material findings emerge during SPIKE execution or Phase 2–5 implementation.

**Deferred items spec refs:** `deferred_items_spec_refs: []` — to be populated as `DOC-006` design specs are authored in Phase 7.

---

## Appendices & references

### Related documentation

- **Design spec (canonical source):** `docs/project_plans/design-specs/remote-ccdash-streaming.md`
- **SPIKE-A charter:** `docs/project_plans/SPIKEs/remote-ccdash-streaming-charter.md`
- **SPIKE-B charter:** `docs/project_plans/SPIKEs/entire-io-integration-charter.md`
- **Grounding brief:** `.claude/findings/remote-ccdash-grounding-brief.md`
- **Runtime modularization:** PR #30, commit 451f958; `backend/runtime/`
- **Telemetry exporter pattern (inversion precedent):** `backend/services/integrations/telemetry_exporter.py`

### Prior art & external references

- Entire.io CLI: https://github.com/entireio/cli
- Entire.io docs: https://docs.entire.io/introduction
- CCDash ingest touchpoints: `backend/parsers/sessions.py:11-13`, `backend/db/sync_engine.py:1-50`, `backend/db/repositories/sessions.py:59`
- CCDash auth: `backend/adapters/auth/bearer.py:22,74-109`
- CCDash project binding: `backend/runtime/container.py:67`, `backend/runtime/profiles.py:7-26`

---

**Progress tracking:** `.claude/progress/remote-ccdash-streaming/all-phases-progress.md` (to be created after PRD approval and SPIKE completion)
