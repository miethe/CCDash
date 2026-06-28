---
schema_version: 2
doc_type: spike
title: "Entire.io OSS CLI Integration — Findings Summary"
description: "Synthesized findings for SPIKE-B. Resolves RQ-1 through RQ-9 with go-forward recommendations against the SessionIngestSource port (ADR-009), ingest path / identity / live-update ADRs, and supporting memos."
status: completed
created: 2026-05-11
updated: 2026-05-11
completed_date: 2026-05-11
feature_slug: remote-ccdash-streaming
charter_ref: docs/project_plans/spikes/entire-io-integration-charter.md
prd_ref: docs/project_plans/PRDs/features/remote-ccdash-streaming-v1.md
plan_ref: docs/project_plans/implementation_plans/features/remote-ccdash-streaming-v1.md
sister_spike: docs/project_plans/spikes/remote-ccdash-streaming.md
related_documents:
  - docs/project_plans/spikes/entire-io-integration/checkpoint-schema.md
  - docs/project_plans/spikes/entire-io-integration/coexistence-memo.md
  - docs/project_plans/spikes/entire-io-integration/privacy-redaction-memo.md
  - docs/project_plans/spikes/entire-io-integration/upstream-feedback-memo.md
  - docs/project_plans/spikes/entire-io-integration/commit-linkage-design.md
adrs:
  - docs/project_plans/adrs/adr-011-entire-ingest-path-decision.md
  - docs/project_plans/adrs/adr-012-entire-session-identity-unification.md
  - docs/project_plans/adrs/adr-013-entire-live-update-mechanism.md
inherits_adrs:
  - docs/project_plans/adrs/adr-009-session-ingest-source-port-and-cursor-table.md
  - docs/project_plans/adrs/adr-008-workspace-scoped-bearer-auth-v1.md
  - docs/project_plans/adrs/adr-014-remote-session-ingest-transport-ndjson-http.md
---

# Entire.io OSS CLI Integration — Findings Summary

> This document is the single end-to-end read for a human reviewer approving downstream Phase 5 work. Every research question (RQ-1 through RQ-9) is resolved here with rationale and a pointer to the ADR or memo that captures the decision in detail. SPIKE-A (`remote-ccdash-streaming`) is treated as authoritative input — ADRs 006–010 are inherited as-is and not relitigated.

---

## Executive Summary

SPIKE-B finds that Entire.io ingest is feasible as a third implementation of the `SessionIngestSource` port defined in [ADR-009](../adrs/adr-009-session-ingest-source-port-and-cursor-table.md) with **zero port additions**. The integration ships as an `EntireCheckpointSource` that reads the `entire/checkpoints/v1` git branch directly via **pygit2-primary, dulwich-fallback** (ADR-011), keys sessions under the existing `source_ref` URI scheme with prefix `entire:` (ADR-012; explicitly supersedes the charter's draft `source_type` enum language), and stays current via **fs-watch on the local ref file with periodic git-fetch poll as the cross-machine fallback** (ADR-013). The charter's three nominated ADRs (ingest path, identity, live-update) are authored as ADRs 011–013; no fourth ADR is needed.

The biggest implementation risk is **upstream schema drift** without a public stability contract — the checkpoint-schema document anticipates this via Pydantic `extra="allow"` parsing, warn-and-strip on unknown additive fields, and a dedicated dead-letter path for breaking renames (mirroring SPIKE-A F-5). The second-biggest risk is the dependency footprint of pygit2 on Windows/locked-down Macs — addressed by auto-falling-back to pure-Python dulwich. A v2 stretch is a read-side push hook from upstream (filed in the upstream-feedback memo); v1 does not depend on it.

The integration **adds zero new external infrastructure**, **adds zero net new auth surfaces** (workspace bearer per ADR-008 covers it), and **adds three env vars** (`CCDASH_ENTIRE_INGEST_ENABLED`, `CCDASH_ENTIRE_GIT_BACKEND`, `CCDASH_ENTIRE_LIVE_MODE`) plus their downstream knobs. The recommended implementation order is **Phase 5 of the existing remote-ccdash-streaming-v1 plan**, immediately after Phase 4 (workspace auth + multi-project routing) lands. Phase 5 effort estimate from the parent plan (12–16 pts) is unchanged by SPIKE-B; the scope is bounded enough that no re-baseline is needed.

---

## RQ Resolutions

### RQ-1 — Checkpoint schema (canonical reference)

**Resolution.** A canonical schema document captures the stable top-level union: identity/timing (`id`, `sessionId`, `schemaVersion`, RFC3339 timestamps), agent identity (`agent.kind` enum of seven), repo/worktree context (`repo.{branch, worktreeId, commitBefore, commitAfter, commits[]}`), conversation `turns[]`, per-turn `toolCalls[]`, transcript references (`<ref>.{kind, locator, size}`), and per-agent extension surface (`agentSpecific.<kind>.*`). Required/optional/agent-specific markers are explicit per field with provenance pointers. Verification gate **E3-CONFORMANCE** runs in Phase 5 against a live multi-agent corpus before `EntireCheckpointSource` is marked ready.

**Deliverable.** [`docs/project_plans/spikes/entire-io-integration/checkpoint-schema.md`](./entire-io-integration/checkpoint-schema.md).

---

### RQ-2 — Ingest path: branch-parse primary, CLI-wrap escape hatch only

**Resolution.** Read `entire/checkpoints/v1` directly via pygit2 (primary) / dulwich (fallback). Auto-select via `CCDASH_ENTIRE_GIT_BACKEND=auto`. CLI-wrap is opt-in only behind `CCDASH_ENTIRE_CLI_WRAP_ENABLED=true` for the narrow shadow-branch-pruned recovery case. The decision matrix scores branch-parse 52–53 vs CLI-wrap 34 across seven weighted criteria.

**ADR.** [ADR-011](../adrs/adr-011-entire-ingest-path-decision.md).

---

### RQ-3 — Live ingest: fs-watch primary, git-fetch poll fallback

**Resolution.** fs-watch on `{repo}/.git/refs/heads/entire/checkpoints/v1` (and `packed-refs`) using the existing `watchfiles` dependency for the local case (p50 <10s, p95 <30s); periodic `git fetch` of the v1 refspec for cross-machine deployments at default 30s interval (p50 <30s). Auto-dispatch via `CCDASH_ENTIRE_LIVE_MODE=auto`. **Upstream-hook path is declined for v1** — see RQ-7 below — but is filed as a v2 upstream feedback item.

**ADR.** [ADR-013](../adrs/adr-013-entire-live-update-mechanism.md).

---

### RQ-4 — Session identity: reuse ADR-009 `source_ref` with `entire:` scheme

**Resolution.** No new columns. `source_ref` carries `entire:<12-hex>`; upsert key `(project_id, workspace_id, source_ref)` per ADR-009. The charter's draft language proposing `source_type` enum + `external_id` column is **explicitly superseded** by this ADR. `source_file` becomes nullable to accommodate non-fs sources; a partial unique index preserves the historical uniqueness guarantee for fs rows.

**Migration.** Single-statement Alembic delta on top of ADR-009: nullable `source_file` + partial unique index. SQLite uses `batch_alter_table` (12-step rewrite); PostgreSQL is direct. Zero-downtime; reversible via downgrade.

**ADR.** [ADR-012](../adrs/adr-012-entire-session-identity-unification.md).

---

### RQ-5 — Transcript fidelity: git-native pointer with lazy resolution

**Resolution.** Persist the checkpoint's `<ref>` object verbatim into `session_forensics_json`. Resolve via the same `GitReader` interface on demand. Avoids the storage blow-up of eager fetch (multi-MB per session × thousands of sessions). Degrades gracefully when shadow branches are pruned (UI affordance: "rerun `entire fetch <id>` to recover"). Soft 5 MB streaming cap with `Content-Range` support is a Phase 6 detail.

**Deliverable.** [ADR-011 §Transcript Resolution Policy](../adrs/adr-011-entire-ingest-path-decision.md).

---

### RQ-6 — Commit linkage: `session_commit_links` join table

**Resolution.** Add a `session_commit_links(session_id, commit_sha, project_id, workspace_id, link_source, detected_at)` table. `link_source` discriminates `entire-trailer` (deterministic from the `Entire-Checkpoint: <id>` commit trailer) vs `mtime-heuristic` (existing CCDash inference) vs `manual`. Populated by `EntireCheckpointSource` at ingest from `repo.commits[]`; backfilled by `backend/scripts/backfill_session_commit_links.py`. Three prioritized UI affordances: "sessions for this commit" panel, "commits from this session" sidebar, "agent attribution" chip on commit hover. No conflict with `session_mappings` (orthogonal: planning-artifact join vs git-commit join).

**Deliverable.** [`docs/project_plans/spikes/entire-io-integration/commit-linkage-design.md`](./entire-io-integration/commit-linkage-design.md).

---

### RQ-7 — Hook-based registration: declined for v1

**Resolution.** Per upstream Agent Hooks documentation, the "external agent plugin interface" is a **write-side** integration — registering an agent whose sessions Entire captures, not a read-side "subscribe to new checkpoints" surface for third-party consumers. There is no current upstream API for CCDash to receive push events when checkpoints are written. **Fallback (and v1 default) is branch-watch (ADR-013).** A v2 feature request to add a read-side hook is filed in the upstream-feedback memo.

**Deliverable.** [Upstream-feedback memo §1](./entire-io-integration/upstream-feedback-memo.md).

---

### RQ-8 — Coexistence: provenance over dedup

**Resolution.** Two rows (fs-keyed + entire-keyed) for the same underlying work are **expected and correct**. No automatic dedup. The `source_ref` chip ("Local" / "Daemon" / "Entire") from SPIKE-A RQ-7 carries provenance. A presentational soft-grouping in the session list uses a 4-condition heuristic (same project, agent match, ±5s timestamps, commit-hash correspondence). Three deployment modes via env: "Native only" (default), "Entire only", "Both".

**Deliverable.** [Coexistence memo](./entire-io-integration/coexistence-memo.md).

---

### RQ-9 — License, redaction, telemetry

**Resolution.** Entire is MIT-licensed; compatible with CCDash. **License action: none.** Entire-side redaction is treated as advisory; CCDash applies a second-pass redactor on ingest using the existing `secrets` ruleset and logs `ingest_redaction_secondary_hits_total{source_id="entire"}` for operators. CCDash does **not** inherit Entire's PostHog telemetry — parsing checkpoint JSON does not initialize an Entire client. The branch-parse path reads local git objects only; the git-fetch poll path uses the user's own remote with the user's own git credentials. CCDash's local-first invariant is preserved.

**Deliverable.** [Privacy/redaction memo](./entire-io-integration/privacy-redaction-memo.md).

---

## ADR-009 Conformance Check (Charter E4)

The charter (E4) gates this SPIKE on whether `EntireCheckpointSource` can implement the ADR-009 `SessionIngestSource` Protocol with **zero port additions**. The conformance walk:

| ADR-009 contract | `EntireCheckpointSource` implementation | Additions required? |
|---|---|---|
| `source_id: str` attribute | Literal `"entire"` | No |
| `async def stream(self, *, since: IngestCursor) -> AsyncIterator[IngestEvent]` | Internal driver = fs-watch loop or git-fetch poll loop (per ADR-013); both yield `IngestEvent`s | No |
| `async def ack(self, event: IngestEvent) -> None` | No-op; cursor is advanced atomically by the engine via `_cursor_repo.advance`, and the source's internal "highest seen" is reconstructed from the cursor on next stream | No |
| `IngestEvent.source_ref` shape (`<scheme>:<opaque>`) | `"entire:<12-hex>"` (ADR-012) | No |
| `IngestEvent.cursor_value` opaque, monotonic per (source, project) | `"<branch-commit-sha>:<checkpoint-id>"` — branch SHA monotonic via git's append-only semantics; checkpoint-id disambiguates within one commit | No |
| `IngestEvent.payload: dict` | Parsed checkpoint JSON, mapped per [checkpoint-schema.md §6](./entire-io-integration/checkpoint-schema.md#6-ccdash-mapping-crib-sheet) | No |
| `IngestEvent.workspace_id` populated | From `AuthContext.workspace_id` per ADR-008 | No |
| `IngestEvent.occurred_at` from the event itself | `checkpoint.endedAt` (fallback: `checkpoint.updatedAt`) | No |
| `IngestEvent.schema_version` | `checkpoint.schemaVersion` (expected `"v1"`) | No |

**Result: zero port additions required.** The port shape designed by SPIKE-A admits Entire cleanly. This was the strongest contingent risk in the charter (§8 "If port additions are needed, surface them explicitly") and it is resolved.

---

## Risks Surfaced (Charter §9 ↔ Decisions)

| Charter risk | Where addressed |
|---|---|
| Branch layout drift (`v1` is path-versioned, not field-versioned) | Checkpoint schema §5 versioning posture; warn-and-strip on additive; dead-letter on breaking; upstream-feedback §2 asks for explicit stability statement |
| Best-effort redaction from upstream | Privacy memo §2; CCDash second-pass redactor on ingest; `ingest_redaction_secondary_hits_total` metric |
| Unbounded growth of `entire/checkpoints/v1` | Cursor model handles incremental ingest; cold-start backfill batched at 200 (ADR-013); no full re-enumerate per cycle |
| Closed hook surface (third-party registration may be reserved) | RQ-7 resolved: not available for read-side; branch-parse is the contracted path; upstream feedback filed |
| Upstream product pivot | Branch path is `v1`-versioned; CCDash depends only on git artifacts (no live RPC dependency on Entire's roadmap); CLI-wrap is opt-in only |
| Per-agent transcript-format long tail | `agentSpecific.<kind>` opaque blob means new agents land without parser changes; agent-specific decoding can be added incrementally |
| Git plumbing portability (pygit2 native-build complexity) | dulwich pure-Python auto-fallback per ADR-011 |
| Charter `source_type` vs ADR-009 `source_ref` conflict | ADR-012 explicitly reconciles: ADR-009 wins |

---

## Open Questions Resolved vs Deferred

| Tag | Question | Status |
|---|---|---|
| RQ-1 | Canonical checkpoint schema | **Resolved** (schema doc; E3-CONFORMANCE corpus gate at Phase 5) |
| RQ-2 | Ingest path (branch-parse vs CLI-wrap vs hybrid) | **Resolved** (ADR-011: branch-parse primary, CLI-wrap escape hatch) |
| RQ-3 | Live update mechanism | **Resolved** (ADR-013: fs-watch + poll auto-dispatch) |
| RQ-4 | Session identity unification | **Resolved** (ADR-012: reuse ADR-009 `source_ref`) |
| RQ-5 | Transcript fidelity | **Resolved** (git-native lazy pointer; ADR-011) |
| RQ-6 | Commit/checkpoint linkage | **Resolved** (commit-linkage-design memo) |
| RQ-7 | Hook-based agent registration | **Resolved as "no" for v1**, filed as v2 upstream request |
| RQ-8 | Coexistence with other sources | **Resolved** (coexistence memo: provenance over dedup) |
| RQ-9 | License, redaction, privacy | **Resolved** (privacy memo: MIT-compatible, second-pass redactor, telemetry isolated) |

No open questions are deferred from SPIKE-B. Items filed upstream (read-side hook, branch stability statement, telemetry env var doc) are improvements that would shrink CCDash's surface area if accepted, but do not block v1.

---

## Decisions Requiring ADRs

All three are authored as part of this SPIKE (allocated 011–013, the next free ADR numbers; ADR-010 was the previous high-water mark):

1. [ADR-011](../adrs/adr-011-entire-ingest-path-decision.md) — Entire ingest path: branch-parse primary, CLI-wrap fallback.
2. [ADR-012](../adrs/adr-012-entire-session-identity-unification.md) — Session identity unification: reuse ADR-009 `source_ref` with `entire:` scheme.
3. [ADR-013](../adrs/adr-013-entire-live-update-mechanism.md) — Live-update mechanism: fs-watch primary, git-fetch poll fallback.

Inherited as authoritative input from SPIKE-A (not authored here):
- [ADR-006](../adrs/adr-014-remote-session-ingest-transport-ndjson-http.md) — transport (orthogonal to Entire path).
- [ADR-008](../adrs/adr-008-workspace-scoped-bearer-auth-v1.md) — auth surface that Entire ingest respects.
- [ADR-009](../adrs/adr-009-session-ingest-source-port-and-cursor-table.md) — the port `EntireCheckpointSource` implements.

---

## Handoff

Downstream artifacts are ready to be promoted/refreshed:

1. **Parent implementation plan** (`docs/project_plans/implementation_plans/features/remote-ccdash-streaming-v1.md`) — Phase 1 status block flips from "SPIKE-B still draft" to "SPIKE-B complete"; Phase 5 detail block links ADRs 011–013 and the checkpoint schema.
2. **Charter** (`docs/project_plans/spikes/entire-io-integration-charter.md`) — status `in-progress` → `completed`; deliverables checklist filled in.
3. **PRD** (`docs/project_plans/PRDs/features/remote-ccdash-streaming-v1.md`) — Phase 5 acceptance criteria can now be locked against the ADRs and schema; no scope change.
4. **Phase 5 implementation plan** — Phase 5 owner reads this findings doc + ADR-011/012/013 + checkpoint-schema as the input package. Estimated effort (12–16 pts) is unchanged.

---

## Sources

- Sister SPIKE: [remote-ccdash-streaming findings](./remote-ccdash-streaming.md)
- Charter: [entire-io-integration-charter.md](./entire-io-integration-charter.md)
- [entireio/cli on GitHub (MIT, charter §2)](https://github.com/entireio/cli)
- [Entire docs — Installation](https://docs.entire.io/cli/installation)
- [Agent Hooks blog post](https://entire.io/blog/agent-hooks-the-integration-layer-between-entire-cli-and-your-agent)
- [Mager.co — Entire CLI: Version Control for Your Agent Sessions (2026-02-10)](https://www.mager.co/blog/2026-02-10-entire-cli/)
