---
schema_version: 2
doc_type: implementation_plan
title: "Remote CCDash Streaming + Entire.io Integration — Implementation Plan"
description: "Skeleton implementation plan. Status: draft. Phase 1 is SPIKE execution; Phases 2–7 are sketched and re-baseline after SPIKE findings."
status: draft
created: 2026-04-19
updated: 2026-04-19
feature_slug: remote-ccdash-streaming
priority: high
risk_level: high
prd_ref: null
plan_ref: null
scope: "Transport-neutral session ingest, local daemon, workspace-scoped auth, multi-project routing, Entire branch parser, UI source attribution + daemon health, migration docs."
effort_estimate: "8–12 weeks engineering (estimate firms after SPIKEs)"
spike_refs:
  - docs/project_plans/SPIKEs/remote-ccdash-streaming-charter.md
  - docs/project_plans/SPIKEs/entire-io-integration-charter.md
related_documents:
  - docs/project_plans/design-specs/remote-ccdash-streaming.md
  - .claude/findings/remote-ccdash-grounding-brief.md
deferred_items_spec_refs: []
findings_doc_ref: null
changelog_required: true
architecture_summary: null
owner: null
contributors: []
---

# Remote CCDash Streaming + Entire.io Integration — Implementation Plan

⚠️ **DRAFT SKELETON** — This plan front-loads SPIKE execution as Phase 1. Phases 2–7 are sketched at a high level only; detailed task breakdowns will expand after SPIKE-A and SPIKE-B findings land. The effort estimate is a wide band (8–12 weeks); the final scope and timeline will firm up post-SPIKE.

---

## Executive Summary

This implementation plan orchestrates the buildout of remote CCDash operation and Entire.io session ingest. The strategy front-loads research: Phase 1 runs two parallel SPIKEs (6 weeks combined) to de-risk transport selection, auth model, sync engine refactoring, daemon packaging, and Entire branch parsing. Phases 2–7 are sequenced along the critical path: sync engine port abstraction → ingest endpoint + local daemon → workspace auth + multi-project routing → Entire parser → frontend attribution + daemon health → hardening + migration guides → docs finalization. Phase 1 explicitly gates all downstream phases; no Phase 2 work starts until both SPIKE deliverables are checked off and design decisions are locked via ADRs.

**Key Milestones:**
- Week 1–2 (parallel): SPIKE-A + SPIKE-B underway
- Week 3–4: Design meeting to resolve OQ-3, OQ-4, OQ-7; ADRs finalized
- Week 5–6: Sync engine abstraction + cursor table (Phase 2)
- Week 7–9: Ingest endpoint + daemon (Phase 3) in parallel
- Week 10–11: Auth + multi-project routing; Entire source (Phases 4–5) in parallel
- Week 12+: Frontend, hardening, docs

---

## Implementation Strategy

### Architecture Sequence

Following CCDash's layered architecture, phases are ordered to minimize coupling and enable parallel work:

1. **Phase 1 (SPIKE)** — Resolve all open questions via targeted research; produce ADRs and prototypes
2. **Phase 2** — Refactor `SyncEngine` to accept abstract `SessionIngestSource` port; preserve filesystem behavior; introduce cursor table
3. **Phase 3** — Build ingest endpoint + local daemon (parallel tracks: backend endpoint + daemon client)
4. **Phase 4** — Implement workspace-scoped auth; multi-project routing; RLS or explicit workspace filtering
5. **Phase 5** — Entire checkpoint branch parser; integrate as concrete `EntireCheckpointSource`
6. **Phase 6** — Frontend: session source attribution chip, daemon health badge, live-update cadence decisions
7. **Phase 7** — Hardening: retry/backoff, dead-letter handling, health endpoint extension, migration guides
8. **Phase 8** — Documentation finalization: CHANGELOG, README updates, context files, deferred-item design specs

### Critical Path

The critical path runs: SPIKE findings → sync engine abstraction → ingest endpoint → auth/multi-project → Entire source → frontend → docs. All downstream phases are hard-gated on SPIKE-A and SPIKE-B completion. A design meeting post-SPIKE resolves architecture questions before Phase 2 kicks off.

### Parallel Work Opportunities

- **SPIKE-A + SPIKE-B run in parallel** (week 1–2). Three tracks within SPIKE-A (transport/ingest, auth, project routing) can be assigned to 2–3 engineers.
- **Phase 3 (daemon)** can split: backend ingest endpoint (Python) and daemon client (Go or Python, TBD by SPIKE-A) in parallel.
- **Phase 4–5** can start once Phase 2 is sealed, with auth and Entire parser on separate engineers.
- **Phase 6 (frontend)** can begin design earlier (week 6, no blocking on Phase 5 API completion).

---

## Phase Summary Table

Mandatory at-a-glance index of all phases with point estimates, target subagents, and model designations.

| Phase | Title | Effort Est. | Target Subagent(s) | Model(s) | Gate | Notes |
|-------|-------|-------------|-------------------|----------|------|-------|
| 1 | SPIKE Execution (Remote Streaming + Entire.io) | 48–60 pts | backend-typescript-architect, data-layer-expert, backend-architect, frontend-architect | sonnet/opus | Hard gate on deliverables; ADRs finalized; design meeting locked | RQ-1 to RQ-8; E1–E5; Findings synthesis |
| 2 | Sync Engine Port Abstraction | 12–16 pts | data-layer-expert, python-backend-engineer | sonnet | Phase 1 complete; ADRs locked | Introduce `SessionIngestSource` port; `FilesystemSource` wrapper; cursor table schema; zero test changes |
| 3 | Ingest Endpoint + Local Daemon | 18–24 pts | python-backend-engineer, (Go/Python daemon owner TBD) | sonnet | Phase 2 complete | POST `/api/v1/ingest/sessions` NDJSON endpoint; daemon tail + batch POST; idempotency keys; E1/E2 validation |
| 4 | Workspace Auth + Multi-Project Routing | 15–20 pts | backend-architect, data-layer-expert | sonnet | Phase 2 complete; Phase 3 working | Per-workspace token table; request-scoped project resolution; RLS enforcement; migration from single bearer |
| 5 | Entire Branch Parser + Source | 12–16 pts | python-backend-engineer, data-layer-expert | sonnet | Phase 2 complete; Phase 4 working | `EntireCheckpointSource` implementation; git plumbing + branch parser; checkpoint schema validation; E1/E4 validation |
| 6 | Frontend Source Attribution + Daemon Health | 9–12 pts | frontend-architect, ui-engineer-enhanced | sonnet (+ gemini-3.1-pro for design) | All backend phases complete | Session source chip; daemon health badge; live-update cadence; health endpoint contract |
| 7 | Hardening, Migration Guides, Telemetry | 12–16 pts | senior-code-reviewer, devops-architect, documentation-writer | sonnet/haiku | All implementation phases complete | Retry/backoff policy; dead-letter handling; failure-mode observability; v1→v2 migration guide |
| 8 | Documentation Finalization | 6–9 pts | documentation-writer, changelog-generator, ai-artifacts-engineer | haiku (sonnet for skill SPECs) | All phases complete | CHANGELOG `[Unreleased]` entry; README; context files; deferred-item design specs (DOC-006) |
| **Total** | — | **132–173 pts** | — | — | — | 8–12 weeks @3 FTE avg |

---

## Phase Details

### Phase 1: SPIKE Execution (Remote Streaming + Entire.io)

**Duration:** 6 weeks (can run both SPIKEs in parallel 1–2 weeks each)
**Owners:** backend-typescript-architect, data-layer-expert, backend-architect, frontend-architect
**Model(s):** sonnet/opus mix
**Gate:** Hard gate on SPIKE-A + SPIKE-B deliverables; ADRs finalized; design meeting locked before Phase 2 begins

#### Goals

- Resolve all 10 open questions (OQ-1 through OQ-10) via targeted research and prototyping
- Produce 5 ADRs: transport selection, daemon packaging, auth model, sync engine port, multi-project routing
- Deliver 5 working experiments (E1–E5) validating the recommended path
- Produce failure-mode matrix and migration plan memos
- Clarify Entire.io checkpoint schema and session identity unification strategy

#### Entry Criteria

- Design spec at `maturity: shaping` is approved for research
- SPIKE charters finalized
- Budget and timeline allocated for 2–3 parallel engineers

#### Exit Criteria

- Both SPIKE charters completed and findings synthesized
- All 5 ADRs approved and checked into architecture directory
- Prototypes E1–E5 validated; go/no-go decisions recorded
- Design meeting held to resolve OQ-3, OQ-4, OQ-7
- Phased scope estimates for Phases 2–8 finalized
- Design spec promoted to `maturity: ready` and PRD scaffolded (draft)

#### Key Risks

- **Long SPIKE timeline** — Parallel tracking (2 engineers per SPIKE) compresses to 1.5 weeks each. Recommend overlapping end of SPIKE-A with start of SPIKE-B.
- **Open questions breed more questions** — Mid-SPIKE checkpoint (end of week 1) required to surface new blockers early.
- **Prototype fragility** — E1–E5 may expose arch gaps post-design meeting; plan for brief re-baseline if needed.

#### Subagent Assignments

- **SPIKE-A Track 1** (transport + ingest + daemon): python-backend-engineer, backend-architect
- **SPIKE-A Track 2** (auth + routing + ops): backend-architect, data-layer-expert
- **SPIKE-A Track 3** (frontend health UX): frontend-architect
- **SPIKE-B** (Entire schema + ingest path): data-layer-expert (RQ-1, RQ-4, RQ-5), python-backend-engineer (RQ-2, RQ-3, RQ-7)
- **Synthesis & ADRs**: lead-architect, backend-architect

#### Model + Effort

- SPIKE work: sonnet (RQ research) + opus (design decisions, multi-track synthesis)
- Effort: adaptive (some RQs are straightforward spec review; others need extended thinking for prototype design)

---

### Phase 2: Sync Engine Port Abstraction

**Duration:** 2 weeks
**Owners:** data-layer-expert, python-backend-engineer
**Model(s):** sonnet
**Gate:** Hard gate on Phase 1 complete; ADRs locked

#### Goals

- Introduce `SessionIngestSource` protocol (Python ABC or `Protocol`)
- Wrap current filesystem logic as `FilesystemSource` with zero behavior change
- Add `ingest_cursors` table with cursor/watermark tracking
- Ensure all existing sync tests pass unchanged

#### Entry Criteria

- Phase 1 complete; SPIKE-A ADRs finalized
- Sync engine refactor scope estimated in SPIKE findings
- Team allocation confirmed

#### Exit Criteria

- `SessionIngestSource` port committed and documented
- `FilesystemSource` implementation passes all existing tests unchanged
- `ingest_cursors` table schema defined + migration scaffolded
- Cursor advancement contract defined for remote sources
- Zero regression on local-mode sync

#### Key Risks

- **Hottest path in worker** — Subtle cursor off-by-one or event-ordering bug silently loses sessions. Hard gate: zero test changes required.
- **Migration complexity** — Dual-source (filesystem + ingest) may require dedup logic. Out of scope for v1 if SPIKE findings show it's complex.

#### Subagent Assignments

- **Port design + filesystem refactor**: data-layer-expert, python-backend-engineer
- **Cursor table + migration**: data-layer-expert
- **Testing**: both, with code-reviewer spot-check

#### Model + Effort

- Effort: adaptive (some refactoring is mechanical; cursor contract requires careful design)

---

### Phase 3: Ingest Endpoint + Local Daemon

**Duration:** 3 weeks (can split into two parallel sub-tracks)
**Owners:** python-backend-engineer, (daemon owner TBD by SPIKE-A)
**Model(s):** sonnet
**Gate:** Phase 2 complete

#### Goals

- Implement `POST /api/v1/ingest/sessions` NDJSON endpoint (backend sub-track)
- Build local daemon that tails JSONL + posts NDJSON batches (daemon sub-track)
- Implement idempotency key tracking + deduplication
- Validate against E1 + E2 prototypes from SPIKE

#### Entry Criteria

- Sync engine port from Phase 2 in place
- SPIKE-A transport + daemon packaging decisions finalized
- Auth model agreed (Phase 4 gate, but ingest endpoint must reserve auth surface)

#### Exit Criteria

- Ingest endpoint passes load test (≥500 events/sec, p99 < 200ms)
- Daemon sustains operation with <1% CPU idle, <50MB RSS
- Zero duplicate events on network retry
- Idempotency key dedup working end-to-end

#### Key Risks

- **Payload size on long sessions** — NDJSON POST may timeout on large batches. Mitigated by enforcing max-lines-per-batch (e.g., 500) in daemon config.
- **Backpressure invisibility** — Daemon may buffer indefinitely if server is slow. Mitigate via timeouts + server-side rejection signals.

#### Subagent Assignments

- **Sub-track A (ingest endpoint)**: python-backend-engineer (router), backend-architect (error handling + concurrency design)
- **Sub-track B (daemon)**: daemon owner from SPIKE-A findings (Go or Python)
- **Integration**: both, coordinate cursor table hand-off

#### Model + Effort

- Effort: adaptive (most is straightforward; backpressure handling needs care)

---

### Phase 4: Workspace Auth + Multi-Project Routing

**Duration:** 2.5 weeks
**Owners:** backend-architect, data-layer-expert
**Model(s):** sonnet
**Gate:** Phase 2 + Phase 3 complete

#### Goals

- Implement per-workspace token table (workspace_id, hashed_token → project_id)
- Request-scoped project resolution via `x-project-id` + auth verification
- Enforce workspace RLS on all data-access paths (sessions, documents, tasks, features)
- Migrate from single static bearer → per-workspace tokens
- Zero-downtime upgrade story for existing deployments

#### Entry Criteria

- SPIKE-A auth ADR finalized
- Phase 3 ingest endpoint reserved auth surface
- Multi-project routing ADR approved

#### Exit Criteria

- Per-workspace tokens working; bearer guard migration complete
- Cross-workspace read attempt returns 403 or empty
- Multi-project query tests passing (10 concurrent projects)
- Migration script from legacy bearer is idempotent
- Performance targets met (p99 latency ≤ single-project + 25%)

#### Key Risks

- **Workspace bypass via header** — `x-project-id` must not widen scope beyond authenticated workspace. High-risk commit: requires security review.
- **Scope creep on RLS** — If the team opts for explicit workspace filtering (vs RLS), every repository query needs audit. Scope this explicitly in SPIKE-A.

#### Subagent Assignments

- **Token table + migration**: data-layer-expert, backend-architect
- **Request-scoped resolution**: backend-architect
- **RLS enforcement**: data-layer-expert (audit all queries)
- **Security review**: lead-architect

#### Model + Effort

- Effort: high (RLS/filtering audit is meticulous; no regressions allowed)

---

### Phase 5: Entire Branch Parser + Source

**Duration:** 2 weeks
**Owners:** python-backend-engineer, data-layer-expert
**Model(s):** sonnet
**Gate:** Phase 2 complete; Phase 4 preferred (auth unblocks production auth for Entire fetch)

#### Goals

- Implement `EntireCheckpointSource` consuming `entire/checkpoints/v1` branch JSON
- Git plumbing parser (libgit2 or dulwich) validated against E1 prototype
- Session identity unification: `source_ref` scheme for Entire checkpoint IDs
- Checkpoint schema validation; graceful handling of unknown fields
- Historical + periodic incremental fetch (per E2 findings)

#### Entry Criteria

- SPIKE-B checkpoint schema + ingest-path ADRs finalized
- Phase 2 `SessionIngestSource` port ready for subclass
- Git plumbing library choice locked

#### Exit Criteria

- `EntireCheckpointSource` implementation complete, passing E4 integration test
- Cold-parse for 1k checkpoints <15s (per E1 go/no-go)
- Session identity unification (source_ref scheme) working; ON CONFLICT upsert validated
- Schema-validation test covering ≥3 agent types
- Zero sessions lost on daemon restart or git fetch interruption

#### Key Risks

- **Upstream schema drift** — `entire/checkpoints/v1` is not publicly versioned. Risk: minor release reorganizes sharding or adds required fields. Mitigation: schema validation + skip-on-unknown-field pattern; file upstream issue if breaking change detected.
- **Large checkpoint growth** — `entire/checkpoints/v1` has no documented retention policy. Unbounded growth on long-lived repos. Mitigation: add retention / pagination policy to operator guide (Phase 7).

#### Subagent Assignments

- **Branch parser + schema validation**: data-layer-expert, python-backend-engineer
- **Identity unification + migration**: data-layer-expert
- **Integration testing**: python-backend-engineer

#### Model + Effort

- Effort: adaptive (schema validation is straightforward; identity unification needs careful design)

---

### Phase 6: Frontend Source Attribution + Daemon Health

**Duration:** 1.5 weeks
**Owners:** frontend-architect, ui-engineer-enhanced
**Model(s):** sonnet (+ gemini-3.1-pro for design)
**Gate:** All backend phases complete preferred; can start design concurrently with Phase 5

#### Goals

- Session source chip (distinguishes fs, remote, Entire sources in session list)
- Daemon health badge (connected/backed-up/disconnected state indicator in runtime health area)
- Live-update cadence decision: extend existing polling vs add SSE subscription
- Health endpoint contract: `/api/health` extended with `ingest_sources` status object

#### Entry Criteria

- Phase 6 RQ-7, RQ-8 from SPIKE-A finalized (UI inventory, cadence decision)
- All backend phases at least 80% complete

#### Exit Criteria

- Session source chip implemented and rendering correctly in SessionInspector
- Daemon health badge integrated into AppRuntimeContext
- Live-update cadence tested (polling latency, SSE reconnect behavior if applicable)
- `/api/health` contract updated; frontend consuming new status object
- Visual design approved by product/UX

#### Key Risks

- **Late API changes** — If Phase 4–5 introduces unexpected auth or source fields, UI may need re-work. Mitigate: frequent integration checks during Phase 5.
- **Polling cadence tuning** — If live updates are insufficiently frequent, users perceive stale sessions. Tune via SPIKE findings + user feedback loop.

#### Subagent Assignments

- **UI design**: gemini-3.1-pro (wireframes), ui-designer (review + refinement)
- **Implementation**: ui-engineer-enhanced (components), frontend-developer (context + hooks)
- **Health endpoint integration**: frontend-developer, python-backend-engineer

#### Model + Effort

- Effort: adaptive (design is straightforward; polling tuning may need A/B testing)

---

### Phase 7: Hardening, Migration Guides, Telemetry

**Duration:** 2 weeks
**Owners:** senior-code-reviewer, devops-architect, documentation-writer
**Model(s):** sonnet/haiku
**Gate:** All implementation phases complete

#### Goals

- Implement retry/backoff/dead-letter for daemon failures (reference SAMTelemetryClient 10-retry pattern)
- Extend health endpoint with ingest-source health signals + cursor lag
- Operator guide covering failure scenarios, troubleshooting, rollback
- v1→v2 migration guide for existing local deployments
- Production readiness: all non-critical bugs triaged

#### Entry Criteria

- Phase 1 SPIKE-A failure-mode matrix available
- All phases 1–6 in code review or complete

#### Exit Criteria

- Retry contract documented + tested (daemon reconnect < 5s, max 10 retries)
- Dead-letter queue or observability (failed batches logged + alerted)
- Health endpoint instrumented; /api/health returns `ingest_sources` status
- Migration guide reviewed by ops/devops team
- Failure scenario chaos test executed; results documented

#### Key Risks

- **Cursor lag metrics** — If ingest is significantly behind real time, operators need clear visibility. Ensure cursor table is queryable for lag dashboard.
- **Rollback complexity** — If Phase 4 (auth) forced a schema migration, rollback may require downtime. Document rollback playbook clearly.

#### Subagent Assignments

- **Retry/backoff implementation**: python-backend-engineer, backend-architect
- **Health instrumentation**: python-backend-engineer, devops-architect
- **Operator guide**: devops-architect, documentation-writer
- **Migration guide**: senior-code-reviewer, documentation-writer

#### Model + Effort

- Effort: adaptive (retry patterns are well-known; migration guide is documentation-heavy)

---

### Phase 8: Documentation Finalization

**Duration:** 1 week
**Owners:** documentation-writer, changelog-generator, ai-artifacts-engineer
**Model(s):** haiku (most), sonnet (skill SPECs)
**Gate:** All implementation phases complete

#### Goals

- CHANGELOG `[Unreleased]` entry (user-facing feature summary)
- README updates if CLI commands, daemon, or new auth model affects user instructions
- Context file updates (CLAUDE.md pointers, key-context/ detail)
- Deferred-item design specs (DOC-006) for any research items pushed to post-v1
- Updated project-level custom skills (if any domain affected)

#### Entry Criteria

- All implementation and hardening complete
- Feature guide drafted by implementation team
- Deferred items list finalized

#### Exit Criteria

- CHANGELOG entry under `[Unreleased]` with correct categorization (per `.claude/specs/changelog-spec.md`)
- README reflects daemon CLI and new auth model (if changed)
- Context files updated with progressive disclosure
- All deferred items have design-spec paths OR documented as N/A with rationale
- Plan frontmatter complete: `status: completed`, `commit_refs`, `files_affected`, `updated` date
- Plan linked in any skill SPEC changes

#### Key Risks

- **Late deferred-item discovery** — If implementation surfaces new research needs, must still author design-spec in this phase. Scope per SPIKE findings to minimize surprise.

#### Subagent Assignments

- **CHANGELOG**: changelog-generator (haiku)
- **README + context**: documentation-writer (haiku)
- **Deferred-item specs**: documentation-writer (sonnet, 0.5–2 pts each)
- **Skill SPEC updates**: ai-artifacts-engineer (sonnet) + documentation-writer (haiku)

#### Model + Effort

- Effort: low (most is documentation); medium (skill SPEC updates need careful review)

---

## Deferred Items & In-Flight Findings Policy

### Deferred Items

The following work is acknowledged but intentionally deferred to post-v1 phases. Each item has a design-spec authoring task (DOC-006) in Phase 8.

| Item ID | Category | Title | Reason Deferred | Trigger for Promotion | Target Spec Path |
|---------|----------|-------|-----------------|----------------------|------------------|
| DEF-001 | scope-cut | Cloud-Entire backend integration | Requires upstream API + SaaS auth; out of scope for local-first v1 | Entire.io API released & documented | `docs/project_plans/design-specs/cloud-entire-integration.md` |
| DEF-002 | scope-cut | Sub-second live transcript streaming | Requires WebSocket/SSE live push; polling is sufficient for v1 | User demand for true live UX | `docs/project_plans/design-specs/live-transcript-streaming.md` |
| DEF-003 | research-needed | Claude Code JSONL + Entire checkpoint record-level merge | Overlapping sessions on same work; dedup strategy TBD | Post-v1 investigation | `docs/project_plans/design-specs/session-record-merge.md` |
| DEF-004 | scope-cut | SaaS multi-tenant billing & orgs | Self-serve provisioning, plan tiers; post-v1 infrastructure | Product/business decision | `docs/project_plans/design-specs/saas-multi-tenant.md` |
| DEF-005 | scope-cut | Bidirectional CCDash → Entire sync | Read-only for v1; write-back requires Entire API + merge strategy | Entire API stabilization + demand | `docs/project_plans/design-specs/bidirectional-sync.md` |

*All items with `N/A` in Target Spec Path will be marked "N/A — deferred post-v1" in Phase 8 exit criteria.*

### In-Flight Findings

Findings doc is **not pre-created**. On the first load-bearing finding discovered during execution:

1. Create `.claude/findings/remote-ccdash-streaming-findings.md`
2. Set `findings_doc_ref: .claude/findings/remote-ccdash-streaming-findings.md` in this plan's frontmatter
3. If the finding affects scope/arch/acceptance criteria, author a corresponding design-spec (DOC-006 task in Phase 8)

---

## Risk Mitigation

| # | Risk | Type | Likelihood | Impact | Mitigation Strategy |
|---|------|------|-----------|--------|-------------------|
| R-1 | SPIKE timeline extends (unknowns surface) | Schedule | Medium-High | High | Parallel tracking (2 eng/SPIKE); mid-SPIKE checkpoint; re-baseline if needed |
| R-2 | SyncEngine refactor breaks local mode | Technical | Medium | High | Hard gate: zero test changes required; feature flag for new code; regression test suite |
| R-3 | Entire checkpoint schema breaking changes | Technical/Ext | Medium | Medium | Snapshot schema in SPIKE-B; add validation + skip-on-unknown; file upstream issue |
| R-4 | Cursor/watermark off-by-one loses sessions | Technical | High (if skipped) | High | Prerequisite gate: cursor table working before any external ingest; thorough testing |
| R-5 | Multi-project routing scope explosion | Ops/Schedule | Medium | Medium | SPIKE-A decision explicit: runtime switching vs per-process fanout; if complex, Phase 2 ships fanout |
| R-6 | Daemon distribution underestimated | Ops | Medium | Low-Medium | Prefer reusing CCDash CLI shell in daemon mode (vs new binary); evaluate in SPIKE-A |
| R-7 | Entire hook system unavailable for push | Product | Medium | Low | Fallback: periodic git-fetch polling (E2 sufficient); live mode is stretch goal |
| R-8 | Cross-workspace auth bypass | Security | Low-Medium | Critical | Require security review on Phase 4 PRs; audit `x-project-id` resolution path |
| R-9 | Performance regression on multi-project | Technical | Low-Medium | Medium | SPIKE-A E5: benchmark 10 projects; if p99 > target, revert to per-project model |
| R-10 | Phase 1 findings reshape architecture | Technical | Medium | High | Plan for brief post-SPIKE design meeting; re-baseline Phases 2–8 if needed |

---

## Resource Requirements

**Team Composition** (across 8–12 weeks at ~3 FTE average):

- **Backend Lead** (1 FTE) — Architect, SPIKE-A leads, Phase 2–4, senior review
- **Backend Engineer** (1–2 FTE) — SPIKE implementation, Phases 2–5, 7
- **Data Layer Engineer** (0.5 FTE) — SPIKE, Phases 2, 4–5
- **Frontend Engineer** (0.5 FTE) — SPIKE-A frontend track, Phase 6
- **DevOps / SRE** (0.5 FTE) — Phase 7 ops/health/monitoring, Phase 8
- **Documentation** (0.25 FTE) — Phase 8

**Total Capacity:** ~4 FTE-weeks per phase; SPIKE is highest intensity (6 FTE-weeks parallel).

---

## Success Metrics

### Delivery Metrics

- Phase 1: Both SPIKEs complete, all ADRs approved (week 6)
- Phases 2–7: On-time delivery within ±2 weeks of plan
- Zero P0 bugs in first 2 weeks post-launch
- Rollback procedure exercised at least once in staging

### Business Metrics

- **US-1 (team lead):** Remote CCDash serving ≥3 concurrent developer workstations with <30s ingest latency
- **US-2 (cluster ops):** Single `worker` process managing 5+ projects + 10+ daemon sources simultaneously
- **US-3 (Entire user):** Entire checkpoint branch fully parsed; sessions appear in CCDash UI within 1 minute of checkpoint creation

### Technical Metrics

- Ingest endpoint: ≥500 events/sec sustained, p99 < 200ms
- Daemon: <1% CPU idle, <50MB RSS, zero duplicate events on retry
- Multi-project: p99 latency ≤ single-project + 25% at 10 concurrent projects
- Session parser: cold-parse 1k Entire checkpoints in <15s
- Auth: cross-workspace query returns 403 or empty
- Cursor: zero sessions lost on daemon restart
- Documentation: migration guide walkthrough successful for 1 existing user

---

## Communication Plan

### Weekly Cadence (SPIKEs & Implementation)

- **Daily Slack standups** during SPIKE weeks 1–2 (parallel tracks)
- **Monday 10am SPIKE sync** (week 1–2): blockers, checkpoints
- **Thursday design meeting** (week 3): ADR review, Phase 2 kickoff decision
- **Biweekly phase reviews** (weeks 5+): phase quality gates, next-phase readiness

### Escalation Path

- SPIKE blockers → lead-architect (same-day)
- Security concerns (Phase 4) → security-review-champion (before commit)
- Scope changes → lead-pm (change request process)

---

## Post-Implementation Plan

### Monitoring & Observability

- Extend `/api/health` with `ingest_sources` status (cursor lag, last_ingest_at per source)
- Prometheus metrics: ingest events/sec, batch latency, dedup cache hit rate, cursor advancement rate
- Alert thresholds: ingest latency >60s, daemon offline >5min, cursor lag >2x session creation rate

### Maintenance & Iteration

- **Month 1:** Monitor daemon uptime, ingest p99, user bug reports; patch as needed
- **Month 2–3:** Gather user feedback on daemon UX, Entire coexistence, auth model; plan v1.1
- **Quarter 2:** Evaluate deferred items (DEF-001–DEF-005) based on usage; prioritize next SPIKE

### Feedback Loop

- Weekly ops metrics dashboard (ingest health, error rates)
- Quarterly review of SPIKE assumptions vs production reality
- Ad-hoc user interviews with US-1 (team lead) and US-3 (Entire user) cohorts

---

## Relationship to Existing Code

- **Builds on:** `backend/runtime/profiles.py` (api/worker/test split), `backend/db/sync_engine.py` (filesystem source), `backend/adapters/auth/bearer.py` (single-tenant model)
- **Introduces:** `SessionIngestSource` port, `ingest_cursors` table, `RemoteIngestSource`, `EntireCheckpointSource`, per-workspace token table, `/api/v1/ingest/sessions` endpoint
- **Preserves:** Local-mode behavior via `FilesystemSource` wrapper; no breaking changes to existing repos or queries (v1 release)

---

## Next Steps

1. **SPIKE execution begins** — Assign SPIKE-A + SPIKE-B owners; schedule kick-off meetings (week 1)
2. **Mid-SPIKE checkpoint** — End of week 1: surface new blockers, re-estimate if needed
3. **ADR review & design meeting** — Week 3: finalize transport, auth, project-routing decisions; lock Phase 2 scope
4. **Phase 2 kickoff** — Week 4: sync engine refactor begins
5. **Phase 1 findings → PRD** — Week 4: scaffold PRD at `docs/project_plans/PRDs/features/remote-ccdash-streaming-v1.md` and promote design-spec to `maturity: ready`

---

**Implementation Plan Version:** 1.0 (Draft)  
**Last Updated:** 2026-04-19  
**Status:** Draft — awaiting SPIKE completion
