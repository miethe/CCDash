---
schema_version: 2
doc_type: implementation_plan
title: "Entire.io Checkpoint Ingest — Implementation Plan"
description: "Standalone plan for EntireCheckpointSource: branch-parse ingest, session identity
  unification (source_ref entire: scheme), fs-watch + git-fetch live-update, integration testing,
  and operator docs. Extracted from remote-ccdash-streaming-v1 Phase 5."
status: draft
created: 2026-06-28
updated: '2026-06-28'
feature_slug: entire-io-checkpoint-ingest
priority: medium
risk_level: medium
prd_ref: null
plan_ref: null
scope: "EntireCheckpointSource implementation — branch-parse ingest via pygit2/dulwich, session
  identity unification (entire: source_ref scheme), fs-watch + git-fetch live-update mechanism,
  session_commit_links table, integration testing and operator docs."
effort_estimate: "12–16 pts (~2 weeks engineering)"
spike_refs:
- docs/project_plans/spikes/entire-io-integration-charter.md
- docs/project_plans/spikes/entire-io-integration.md
related_documents:
- docs/project_plans/adrs/adr-011-entire-ingest-path-decision.md
- docs/project_plans/adrs/adr-012-entire-session-identity-unification.md
- docs/project_plans/adrs/adr-013-entire-live-update-mechanism.md
- docs/project_plans/adrs/adr-009-session-ingest-source-port-and-cursor-table.md
- docs/project_plans/implementation_plans/features/remote-ccdash-streaming-v1.md
- docs/project_plans/spikes/entire-io-integration/checkpoint-schema.md
deferred_items_spec_refs: []
findings_doc_ref: null
changelog_required: true
architecture_summary: "EntireCheckpointSource subclasses the SessionIngestSource Protocol\
  \ (ADR-009), reads entire/checkpoints/v1 git branch directly via pygit2-primary/dulwich-fallback\
  \ (ADR-011), keys sessions under source_ref URI scheme entire:<12-hex> with upsert on\
  \ (project_id, workspace_id, source_ref) (ADR-012), and stays current via fs-watch on\
  \ the local ref file with periodic git-fetch poll as cross-machine fallback (ADR-013).\
  \ Introduces three env vars: CCDASH_ENTIRE_INGEST_ENABLED, CCDASH_ENTIRE_GIT_BACKEND,\
  \ CCDASH_ENTIRE_LIVE_MODE. Zero new port additions required (E4 conformance walk passed\
  \ in SPIKE-B)."
owner: null
contributors: []
---

# Entire.io Checkpoint Ingest — Implementation Plan

> **Dependency notice.** This plan builds on completed work from `remote-ccdash-streaming-v1`
> Phases 1–4: the `SessionIngestSource` Protocol and `ingest_cursors` watermark table (ADR-009,
> Phase 2), the ingest endpoint and local daemon (Phase 3), and workspace-scoped bearer auth +
> multi-project routing (Phase 4). All four phases must be merged and green before Phase 1 of
> this plan begins.

---

## Executive Summary

This plan implements `EntireCheckpointSource`, a concrete `SessionIngestSource` that reads the
`entire/checkpoints/v1` git branch produced by the [Entire.io OSS CLI](https://github.com/entireio/cli)
and ingests its checkpoint files into the CCDash session database. SPIKE-B (`entire-io-integration`)
fully resolved all nine research questions; the three resulting ADRs (011–013) define the contracts
this plan implements. No new external infrastructure is required, no new auth surfaces are added
(workspace bearer per ADR-008 covers it), and zero port additions to the `SessionIngestSource`
Protocol are needed (E4 conformance walk passed).

The work is decomposed into three sequential phases:

1. **Branch Parser + Schema Validation** — `GitReader` interface with pygit2/dulwich backends,
   `EntireCheckpointSource` class, checkpoint schema parsing with dead-letter on unknown fields,
   E1-PERF and E3-CONFORMANCE hard gates.
2. **Session Identity Unification + Source Migration** — `source_file` nullability migration
   (ADR-012), `entire:` source_ref scheme wired into upsert, `session_commit_links` table, E4
   integration tests on SQLite and PostgreSQL.
3. **Live-Update Mechanism, Integration Testing + Operator Polish** — fs-watch and git-fetch poll
   drivers inside `EntireCheckpointSource.stream()` (ADR-013), E2 latency gates, `/api/health`
   `ingest_sources` entry, operator guide and env var documentation.

**Key Milestones:**

- Phase 1 complete: `EntireCheckpointSource` reads and parses checkpoints; E1-PERF cold-parse gate
  passes; E3-CONFORMANCE corpus gate passes.
- Phase 2 complete: Session identity unified under `entire:` scheme; Alembic migration validated
  on SQLite and PostgreSQL; all existing session-listing tests unchanged.
- Phase 3 complete: End-to-end live-update latency targets met; operator guide published.

---

## Implementation Strategy

### Architecture Sequence

This plan slots entirely into the CCDash ingest layer. No new ports, no new external infrastructure.
The `SessionIngestSource` seam introduced in `remote-ccdash-streaming-v1` Phase 2 is the only
integration point.

1. **Phase 1** — Implement `GitReader` interface + `EntireCheckpointSource` skeleton; wire into
   `SyncEngine` behind `CCDASH_ENTIRE_INGEST_ENABLED` flag; run E1-PERF + E3-CONFORMANCE gates.
2. **Phase 2** — Alembic migration for `source_file` nullability + partial unique index (ADR-012);
   extend `source_ref` upsert to the `entire:` scheme; add `session_commit_links` table; validate
   with E4 integration test.
3. **Phase 3** — Add fs-watch driver and git-fetch poll driver inside
   `EntireCheckpointSource.stream()`; auto-dispatch logic; E2 latency benchmark; health endpoint
   integration; operator guide.

### Critical Path

Phase 1 → Phase 2 → Phase 3. Each phase gates the next: the parser must exist before identity
can be tested, and identity must be stable before live-update latency can be measured end-to-end.

### Parallel Work Opportunities

- **Phase 1 sub-tracks:** Parser implementation (python-backend-engineer) and schema validation
  test corpus (data-layer-expert) can run in parallel.
- **Phase 3:** Operator guide drafting (documentation-writer) can begin concurrently while E2 gate
  benchmark runs.

### Environment Variables Introduced

| Variable | Default | Purpose |
|---|---|---|
| `CCDASH_ENTIRE_INGEST_ENABLED` | `false` | Master feature flag; gates all Entire ingest paths |
| `CCDASH_ENTIRE_GIT_BACKEND` | `auto` | `auto\|pygit2\|dulwich` — library selection for branch-parse |
| `CCDASH_ENTIRE_LIVE_MODE` | `auto` | `auto\|watch\|poll` — live-update trigger mechanism |
| `CCDASH_ENTIRE_FETCH_INTERVAL_SECONDS` | `30` | Polling interval when `poll` mode is active |
| `CCDASH_ENTIRE_BACKFILL_BATCH_SIZE` | `200` | Checkpoint batch size during cold-start backfill |
| `CCDASH_ENTIRE_WATCH_RECONCILE_SECONDS` | `300` | Backstop reconcile interval for fs-watch mode |

---

## Phase Summary Table

| Phase | Title | Effort Est. | Target Subagent(s) | Model(s) | Gate | Notes |
|-------|-------|-------------|-------------------|----------|------|-------|
| 1 | Branch Parser + Schema Validation | 5–7 pts | python-backend-engineer, data-layer-expert | sonnet | remote-ccdash-streaming-v1 Phases 1–4 complete; ADRs 009 + 011 locked | `GitReader`, `EntireCheckpointSource` skeleton; E1-PERF + E3-CONFORMANCE gates |
| 2 | Session Identity Unification + Source Migration | 4–5 pts | data-layer-expert, python-backend-engineer | sonnet | Phase 1 complete | ADR-012 migration; `entire:` source_ref; `session_commit_links`; E4 integration test |
| 3 | Live-Update, Integration Testing + Operator Polish | 3–4 pts | python-backend-engineer, documentation-writer | sonnet / haiku | Phase 2 complete | ADR-013 drivers; E2 latency gates; health endpoint; operator guide + env var docs |
| **Total** | — | **12–16 pts** | — | — | — | ~2 weeks @1 FTE |

---

## Phase Details

### Phase 1: Branch Parser + Schema Validation

**Duration:** ~1 week
**Owners:** python-backend-engineer, data-layer-expert
**Model(s):** sonnet
**Gate:** `remote-ccdash-streaming-v1` Phases 1–4 merged; `SessionIngestSource` Protocol and
`ingest_cursors` table in place; ADR-011 library choice locked.

#### Goals

- Implement `GitReader` interface with `pygit2` primary, `dulwich` pure-Python fallback; backend
  selection controlled by `CCDASH_ENTIRE_GIT_BACKEND=auto` (try pygit2, fall back on import failure)
- Implement `EntireCheckpointSource` as a `SessionIngestSource` subclass per the ADR-009 contract
- Wire `EntireCheckpointSource` into `SyncEngine` behind `CCDASH_ENTIRE_INGEST_ENABLED` flag;
  `false` (default) is a zero-overhead no-op
- Checkpoint JSON parsing per `checkpoint-schema.md`; Pydantic `extra="allow"` with warn-and-strip
  on unknown additive fields; dead-letter path for breaking renames (mirrors SPIKE-A F-5 pattern)
- E1-PERF gate: cold-parse 1,000 checkpoints <15s (pygit2) / <60s (dulwich); peak memory <200 MB
- E3-CONFORMANCE gate: schema-validation test covering ≥3 agent types against live multi-agent
  corpus

#### Entry Criteria

- `remote-ccdash-streaming-v1` Phases 1–4 merged and green; `SessionIngestSource` Protocol and
  `ingest_cursors` table exist in the backend ingest layer
- SPIKE-B findings (`docs/project_plans/spikes/entire-io-integration.md`) and checkpoint schema
  (`docs/project_plans/spikes/entire-io-integration/checkpoint-schema.md`) available as reference
- ADR-011 accepted; git library choice finalized

#### Exit Criteria

- `EntireCheckpointSource` committed; `CCDASH_ENTIRE_INGEST_ENABLED=true` enables it, `false`
  is confirmed zero-overhead
- `CCDASH_ENTIRE_GIT_BACKEND=auto` selects pygit2 when available; falls back to dulwich without
  manual configuration (unit test)
- E1-PERF gate passed: cold-parse benchmark output attached to PR
- E3-CONFORMANCE gate passed: ≥3 agent types parse correctly in CI corpus test
- Malformed-JSON checkpoint: dead-lettered; other checkpoints in the same batch unaffected
  (integration test)
- Missing `entire/checkpoints/v1` branch: source reports zero events, no error, cursor unchanged
  (unit test)
- Partial-fetch / shallow-clone: operator-visible warning surfaced; affected checkpoints skipped;
  ingest continues (integration test)
- Windows + dulwich smoke test: single checkpoint parse succeeds end-to-end (CI matrix)

#### Key Risks

- **Upstream schema drift** — `entire/checkpoints/v1` has no public stability contract.
  Mitigation: `extra="allow"` parsing, warn-and-strip on additive fields, dead-letter path for
  breaking renames; file upstream issue if breaking change detected (upstream-feedback memo).
- **Large checkpoint growth** — No documented retention policy; unbounded growth on long-lived
  repos. Mitigation: cursor-based incremental ingest (ADR-013 backfill batch capped at
  `CCDASH_ENTIRE_BACKFILL_BATCH_SIZE`); retention guidance in Phase 3 operator docs.

#### Subagent Assignments

- **`GitReader` + `EntireCheckpointSource` skeleton**: python-backend-engineer
- **Schema validation, dead-letter, CI test corpus**: data-layer-expert
- **`SyncEngine` wiring + feature flag**: python-backend-engineer

#### Model + Effort

- Effort: adaptive (parser is well-structured per checkpoint-schema.md; dead-letter pattern
  copies the existing SPIKE-A F-5 implementation)

---

### Phase 2: Session Identity Unification + Source Migration

**Duration:** ~3–4 days
**Owners:** data-layer-expert, python-backend-engineer
**Model(s):** sonnet
**Gate:** Phase 1 complete.

#### Goals

- Alembic migration: `source_file` nullable; partial unique index on
  `(project_id, workspace_id, source_file) WHERE source_file IS NOT NULL` (ADR-012)
- Extend upsert key to handle `entire:` source_ref scheme: upsert on
  `(project_id, workspace_id, source_ref)` per ADR-009; `source_file` excluded from the
  `ON CONFLICT` target
- Add `session_commit_links(session_id, commit_sha, project_id, workspace_id, link_source,
  detected_at)` table; populate from `repo.commits[]` at ingest; backfill script at
  `backend/scripts/backfill_session_commit_links.py`
- Resolve `project_id` from `repo.remoteUrl` against projects registry; fallback to active
  request binding
- E4 integration test: upsert validated; ON CONFLICT behavior correct; cross-source listing
  query returns expected sessions

#### Entry Criteria

- Phase 1 complete; `EntireCheckpointSource` parsing checkpoints correctly
- ADR-012 accepted; migration strategy reviewed by data-layer-expert before authoring

#### Exit Criteria

- Migration applied cleanly on SQLite (12-step `batch_alter_table`) and PostgreSQL (direct ALTER)
- Pre-existing `source_file`-bearing rows unaffected: 100% have `source_file IS NOT NULL AND
  source_ref = 'fs:' + source_file` post-migration
- New `entire:` rows: 100% have `source_ref LIKE 'entire:%' AND source_file IS NULL`
- Downgrade script tested: `entire:` rows removed; `source_file NOT NULL` constraint restored
- `session_commit_links` populated at ingest; backfill script committed and tested
- All existing session-listing tests pass without modification (zero test diff)
- E4 integration test: cross-source listing query (`WHERE source_ref LIKE 'entire:%' OR
  source_ref LIKE 'fs:%'`) returns expected sessions
- `(project_id, workspace_id, source_ref)` uniqueness enforced by ADR-009 index
- `backend/services/source_identity.py` fallback to `source_ref` when `source_file IS NULL`

#### Key Risks

- **SQLite 12-step rewrite** — `batch_alter_table` is error-prone if not exercised in CI.
  Mitigation: dedicated SQLite CI test job against seeded DB; assert row counts pre/post.
- **`source_file` display paths** — NULL `source_file` must fall back to `source_ref` in display
  code. Mitigation: grep audit required as part of exit criteria; `source_identity.py` fallback
  already in scope per ADR-009.

#### Subagent Assignments

- **Alembic migration + partial index**: data-layer-expert
- **Upsert extension + `session_commit_links`**: data-layer-expert, python-backend-engineer
- **E4 integration test**: python-backend-engineer

#### Model + Effort

- Effort: adaptive (migration is mechanical; identity unification requires careful design review)

---

### Phase 3: Live-Update Mechanism, Integration Testing + Operator Polish

**Duration:** ~4 days
**Owners:** python-backend-engineer, documentation-writer
**Model(s):** sonnet / haiku
**Gate:** Phase 2 complete.

#### Goals

- Implement fs-watch driver inside `EntireCheckpointSource.stream()` using existing `watchfiles`
  dependency; coalesce events within 250ms; watch `packed-refs` as well as the loose ref file
  (ADR-013)
- Implement git-fetch poll driver using `pygit2.Remote.fetch()` with refspec-restricted fetch;
  interval via `CCDASH_ENTIRE_FETCH_INTERVAL_SECONDS` (default 30s; min 10, max 600)
- Auto-dispatch logic: local repo with accessible ref → fs-watch; bare clone or inaccessible ref
  → poll; explicit override via `CCDASH_ENTIRE_LIVE_MODE`
- Backstop reconcile timer at `CCDASH_ENTIRE_WATCH_RECONCILE_SECONDS` (default 300s) to recover
  from silently dropped fs-watch events
- Populate `ingest_sources[i]` health entry in `/api/health` response (source_id, mode,
  last_ingest_at, cursor_lag_seconds, error_count, branch_head_sha, last_cursor)
- E2 latency gates: fs-watch p50 <10s, p95 <30s; git-fetch poll @ 30s interval p50 <30s, p95 <45s
- Rapid-fire test: 50 checkpoints in 30s — all ingested, no duplicate rows, cursor advances
  monotonically
- Operator guide at `docs/guides/entire-io-ingest.md`: all 6 env vars, failure modes, auth
  credential setup, retention guidance

#### Entry Criteria

- Phase 2 complete; session identity working end-to-end
- ADR-013 accepted; live-update mechanism choice finalized

#### Exit Criteria

- E2 latency gate passed: benchmark results attached to PR
- Rapid-fire test: 50 checkpoints in 30s — all ingested, no duplicates, cursor monotonic (both
  modes, integration test)
- Auto-selection: local repo → fs-watch; bare clone → poll (unit tests)
- `CCDASH_ENTIRE_LIVE_MODE=poll` honored even on a local repo (unit test)
- `/api/health` returns `ingest_sources` entry with all specified fields for `source_id: "entire"`
- Zero sessions lost on daemon restart or git fetch interruption (integration test)
- Operator guide committed at `docs/guides/entire-io-ingest.md`; covers all env vars, failure
  modes, git credential pre-configuration, checkpoint retention guidance

#### Key Risks

- **macOS fsevents resource pressure** — `watchfiles` may silently drop events under heavy I/O.
  Mitigation: backstop reconcile timer (default 5min, configurable via
  `CCDASH_ENTIRE_WATCH_RECONCILE_SECONDS`).
- **git-fetch auth prompts** — Non-interactive daemon process cannot respond to interactive auth.
  Mitigation: document credential pre-configuration in operator guide; surface `error_count` in
  health endpoint for auth failures.

#### Subagent Assignments

- **fs-watch + poll driver implementation**: python-backend-engineer
- **Health endpoint integration (`/api/health` ingest_sources)**: python-backend-engineer
- **E2 latency test suite**: python-backend-engineer
- **Operator guide**: documentation-writer (haiku)

#### Model + Effort

- python-backend-engineer: adaptive (driver loops are fully specified by ADR-013)
- documentation-writer: adaptive / haiku

---

## Deferred Items & In-Flight Findings Policy

### Deferred Items

The following items were deferred from the parent plan (`remote-ccdash-streaming-v1`) and are
carried forward here as acknowledged post-v1 scope. None are active implementation targets for
this plan. Each has a design-spec path for when the trigger condition is met.

| Item ID | Category | Title | Reason Deferred | Trigger for Promotion | Target Spec Path |
|---------|----------|-------|-----------------|----------------------|------------------|
| DEF-001 | scope-cut | Cloud-Entire backend integration | Requires upstream API + SaaS auth; out of scope for local-first v1 | Entire.io API released & documented | `docs/project_plans/design-specs/cloud-entire-integration.md` |
| DEF-002 | scope-cut | Sub-second live transcript streaming | Requires WebSocket/SSE live push; polling is sufficient for v1 | User demand for true live UX | `docs/project_plans/design-specs/live-transcript-streaming.md` |
| DEF-003 | research-needed | Claude Code JSONL + Entire checkpoint record-level merge | Overlapping sessions on same work; dedup strategy TBD | Post-v1 investigation | `docs/project_plans/design-specs/session-record-merge.md` |
| DEF-004 | scope-cut | SaaS multi-tenant billing & orgs | Self-serve provisioning, plan tiers; post-v1 infrastructure | Product/business decision | `docs/project_plans/design-specs/saas-multi-tenant.md` |
| DEF-005 | scope-cut | Bidirectional CCDash → Entire sync | Read-only for v1; write-back requires Entire API + merge strategy | Entire API stabilization + demand | `docs/project_plans/design-specs/bidirectional-sync.md` |

*All items with `N/A` in Target Spec Path will be marked "N/A — deferred post-v1" at plan
completion.*

### In-Flight Findings

Findings doc is not pre-created. On the first load-bearing finding discovered during execution:

1. Create `.claude/findings/entire-io-checkpoint-ingest-findings.md`
2. Set `findings_doc_ref` in this plan's frontmatter to that path
3. If the finding affects scope, architecture, or acceptance criteria, author a corresponding
   design-spec stub

---

## Risk Mitigation

| # | Risk | Type | Likelihood | Impact | Mitigation Strategy |
|---|------|------|-----------|--------|-------------------|
| R-1 | Upstream schema drift breaks checkpoint parsing | Technical/Ext | Medium | Medium | Pydantic `extra="allow"`, warn-and-strip on additive; dead-letter for breaking renames; upstream stability request filed in upstream-feedback memo |
| R-2 | pygit2 native build unavailable on target platform | Technical | Medium | Low-Medium | dulwich pure-Python auto-fallback via `CCDASH_ENTIRE_GIT_BACKEND=auto`; CI matrix includes Windows + dulwich smoke test |
| R-3 | SQLite 12-step migration regression | Technical | Low-Medium | High | Dedicated SQLite CI job with seeded DB; pre/post row-count assertion |
| R-4 | `source_file` display paths not updated for NULL | Technical | Low | Medium | `backend/services/source_identity.py` fallback already in scope per ADR-009; grep audit required as Phase 2 exit criterion |
| R-5 | fs-watch silent event drop under macOS fsevents pressure | Technical | Low-Medium | Medium | Backstop reconcile timer (5min default); configurable via `CCDASH_ENTIRE_WATCH_RECONCILE_SECONDS` |
| R-6 | Unbounded `entire/checkpoints/v1` growth | Ops | Medium | Medium | Cursor-based incremental ingest; backfill batch size capped; retention guide in Phase 3 operator docs |

---

## Success Metrics

### Delivery Metrics

- Phase 1: E1-PERF and E3-CONFORMANCE gates pass in CI
- Phase 2: Alembic migration applied clean on SQLite and PostgreSQL; all existing tests unchanged
- Phase 3: E2 latency gates pass; operator guide published at `docs/guides/entire-io-ingest.md`

### Technical Metrics (from ADR hard gates)

- Cold-parse 1,000 checkpoints (pygit2): <15s; peak memory <200 MB
- Cold-parse 1,000 checkpoints (dulwich): <60s
- End-to-end latency fs-watch: p50 <10s, p95 <30s
- End-to-end latency git-fetch poll @ 30s interval: p50 <30s, p95 <45s
- CPU at idle 1 hour: fs-watch <0.5%; poll <2%
- Session identity: zero duplicate rows on rapid-fire ingest (50 checkpoints / 30s)
- Migration: 100% existing `fs:` rows unaffected; 100% `entire:` rows have NULL `source_file`
- Auth: cross-workspace `entire:` session query returns 403 or empty (inherited from Phase 4 of
  parent plan)

---

## Relationship to Existing Code

- **Seam:** `SessionIngestSource` Protocol in `backend/db/ingest/` or
  `backend/application/services/ingest/` (introduced in `remote-ccdash-streaming-v1` Phase 2).
  `EntireCheckpointSource` subclasses this protocol — zero changes to the port interface itself.
- **Builds on:** `ingest_cursors` table (ADR-009, parent Phase 2); workspace-scoped bearer auth
  (ADR-008, parent Phase 4); `watchfiles` dependency already present in the sync engine.
- **Introduces:** `EntireCheckpointSource`, `GitReader` interface (pygit2 + dulwich backends),
  `session_commit_links` table, nullable `source_file` Alembic migration, `CCDASH_ENTIRE_INGEST_ENABLED`,
  `CCDASH_ENTIRE_GIT_BACKEND`, and `CCDASH_ENTIRE_LIVE_MODE` env vars.
- **Preserves:** Local-mode behavior via `FilesystemSource` wrapper; no breaking changes to
  existing repositories, queries, or the auth model.

---

## Next Steps

1. Confirm `remote-ccdash-streaming-v1` Phases 1–4 are merged and green
2. Assign Phase 1 owners; schedule a reading of SPIKE-B findings + ADRs 011–013 +
   checkpoint-schema.md as the input package
3. Phase 1 implementation begins; establish E1-PERF benchmark baseline early (reference corpus
   from `docs/project_plans/spikes/entire-io-integration/checkpoint-schema.md`)
4. Phase 2 Alembic migration reviewed by data-layer-expert before merge; PostgreSQL seeded-smoke
   test required (`npm run docker:hosted:smoke:seeded-pg`)
5. Phase 3 E2 latency benchmark against a local Entire.io checkout (minimum 100-checkpoint corpus)

---

**Implementation Plan Version:** 1.0 (Draft)
**Last Updated:** 2026-06-28
**Status:** Draft — awaiting completion of `remote-ccdash-streaming-v1` Phases 1–4 as prerequisite
