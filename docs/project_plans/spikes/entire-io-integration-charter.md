---
schema_version: 2
doc_type: spike
title: "Entire.io OSS CLI Integration — Session Ingest from Git-Branch Checkpoints"
status: draft
created: 2026-04-19
updated: 2026-04-19
feature_slug: remote-ccdash-streaming
complexity: medium
estimated_research_time: "1.5 weeks (1 engineer), can overlap with remote-streaming SPIKE"
prd_ref: null
related_documents:
  - docs/project_plans/design-specs/remote-ccdash-streaming.md
  - .claude/findings/remote-ccdash-grounding-brief.md
  - docs/project_plans/SPIKEs/remote-ccdash-streaming-charter.md
research_questions:
  - "RQ-1: Schema reverse-engineering — what exactly does a checkpoint JSON contain? Inventory every field across agents (Claude Code, Gemini, Cursor, Codex, Copilot). Produce a canonical schema doc with required/optional/agent-specific markers."
  - "RQ-2: Ingest path decision — read `entire/checkpoints/v1` branch via git plumbing (libgit2/pygit2/dulwich/shell-out), wrap the `entire` CLI binary, or design for both? Which is more robust, faster, and less coupled to internal layout?"
  - "RQ-3: Historical vs live ingest — what's the shortest live-update loop? Git-fetch polling, fs-watch on the ref-update, or requesting Entire maintainers add a hook? Target: <30s from checkpoint creation to CCDash visibility."
  - "RQ-4: Session identity unification — CCDash today keys sessions by `source_file` (local path). Entire keys by 12-hex checkpoint ID. How do we store both in `sessions` table without regressing existing queries? Schema change proposal: add `source_type` (enum: filesystem|remote_ingest|entire_checkpoint), `external_id`, and unique index strategy."
  - "RQ-5: Transcript fidelity — Entire stores transcript references by agent; do we resolve transcripts at ingest time (eager fetch), lazily (on session open), or mirror the git-native model? Storage size implications."
  - "RQ-6: Commit/checkpoint linkage — Entire ties checkpoints to git commits via commit trailers (`Entire-Checkpoint: [ID]`). CCDash has a `features` and `progress` model; does tying a session to a commit unlock useful CCDash views (e.g., 'which agent sessions produced PR #123')? Propose a `session_commit_links` mapping."
  - "RQ-7: Hook-based registration — can a CCDash daemon register as an 'agent' in Entire's hook system to receive live events, or is that reserved? Investigate the Agent interface in the Entire codebase."
  - "RQ-8: Coexistence with other session sources — many devs will have both Claude Code JSONL logs AND Entire checkpoints for the same work session. How do we dedupe/merge? Provenance labeling in UI."
  - "RQ-9: License, redaction, and privacy — Entire redacts secrets on its side best-effort. What does CCDash need to do on re-ingest? Any upstream telemetry concerns when CCDash parses these files?"
---

# Entire.io OSS CLI Integration — Charter

## 1. Charter Purpose

This charter scopes research to determine whether and how CCDash can consume agent sessions captured by the Entire.io OSS CLI (https://github.com/entireio/cli) as a first-class session source. Outputs unblock:

- Entire integration PRD and implementation plan
- A go/no-go decision on whether Entire is supported in CCDash v1, a later phase, or declined
- Architectural decisions on session identity, ingest path, and live-update mechanism that shape `remote-ccdash-streaming` as well

Research is scoped to **ingest only** (Entire → CCDash). Bidirectional sync, replacing Entire, and cloud-Entire integration are out of scope.

## 2. Background

Grounded in `.claude/findings/remote-ccdash-grounding-brief.md` (Leg 2).

**Entire.io CLI facts (cite: https://github.com/entireio/cli, brief Leg 2):**
- MIT-licensed, Go, ~4k stars, active
- Git-integrated AI session capture: stores checkpoint JSON on a dedicated branch `entire/checkpoints/v1`, sharded by first-2-chars of a 12-hex ID (e.g., `entire/checkpoints/v1/a3/a3b2c4d5e6f7.json`)
- Session IDs: `YYYY-MM-DD-<UUID>`; transcripts are agent-specific (Gemini: `session-*-<shortid>.json`; others typically JSONL)
- Commands: `enable`, `status`, `rewind`, `resume`, `configure`
- Shadow branches `entire/<sessionID>-<worktreeID>` hold ephemeral per-session working state
- Per-agent hook system under `.claude/`, `.gemini/` — third-party agent registration unclear
- Cloud opt-in via `ENTIRE_API_BASE_URL`; default is local + git only
- Auth: local git identity; API key for cloud
- Telemetry: PostHog, likely env-var opt-out
- **No documented third-party consumer API.** Ingest paths are: (a) read the `entire/checkpoints/v1` branch JSON directly, (b) wrap the `entire` CLI, or (c) request an upstream API

**CCDash facts (cite: brief Leg 1):**
- Session parser dispatch by extension in `backend/parsers/sessions.py:11-13`
- `SyncEngine` is filesystem+mtime coupled (`backend/db/sync_engine.py:1-50`)
- Sessions currently keyed by local canonical path (`backend/db/repositories/sessions.py:59`)
- A sister SPIKE (`remote-ccdash-streaming-charter.md`) proposes a `SessionIngestSource` port abstraction; **this SPIKE assumes that port exists and designs `EntireCheckpointSource` against it**

## 3. Research Questions

### RQ-1: Checkpoint schema reverse-engineering

- **Why it matters:** Without a canonical schema, parser code is fragile to upstream changes.
- **Approach:** Read `entireio/cli` source (checkpoint write paths, Go structs); run CLI locally against multiple agents; capture and diff real checkpoint JSON.
- **Success criteria:** Canonical schema doc covering ≥3 agents; every field marked required/optional/agent-specific with provenance (source file/line in Entire repo).
- **Deliverable:** `docs/project_plans/SPIKEs/entire-io-integration/checkpoint-schema.md`.

### RQ-2: Ingest path decision (branch-parse vs CLI-wrap vs hybrid)

- **Why it matters:** Determines coupling to Entire internals, cross-platform reliability, and operational surface area.
- **Approach:** Prototype both (E1, E5); compare on robustness (upstream-break resilience), latency, dependencies (Go binary presence), platform portability (macOS/Linux/Windows), auth surface.
- **Success criteria:** Decision matrix scoring ≥5 criteria; recommended path with ADR-ready rationale.
- **Deliverable:** ADR draft + matrix table in findings.

### RQ-3: Historical vs live ingest

- **Why it matters:** CCDash value-add depends on near-real-time session visibility.
- **Approach:** Benchmark E2 variants: (a) periodic `git fetch` + ref comparison, (b) fs-watch on `.git/refs/heads/entire/checkpoints/v1` (local repo case), (c) upstream-hook proposal. Measure end-to-end latency from `entire` checkpoint write to CCDash DB row.
- **Success criteria:** p50 latency <30s under normal dev workload; documented tail behavior and CPU/network cost.
- **Deliverable:** Benchmark table + recommended mechanism.

### RQ-4: Session identity unification

- **Why it matters:** CCDash's existing `source_file`-keyed model cannot represent checkpoints (git objects, no filesystem path). A schema migration is in scope.
- **Approach:** Read `backend/db/repositories/sessions.py`, `backend/parsers/sessions.py`; propose additive schema: `source_type` enum (`filesystem|remote_ingest|entire_checkpoint`), `external_id` (nullable, indexed), and updated uniqueness constraint `(source_type, external_id) OR (source_type, source_file)`. Audit all call sites that read `source_file` for regression risk.
- **Success criteria:** Migration proposal with backfill plan, zero-downtime story, and impact list for existing queries.
- **Deliverable:** ADR draft; Alembic migration sketch.

### RQ-5: Transcript fidelity & resolution strategy

- **Why it matters:** Transcripts can be large (MBs per session); eager fetch bloats DB, lazy fetch complicates offline UX.
- **Approach:** Measure transcript sizes across agents (E3 corpus); prototype eager, lazy, and git-native (keep pointer, resolve via libgit2 on demand) modes.
- **Success criteria:** Recommendation with storage/latency/UX tradeoff table; strategy for shadow-branch transcripts that may be pruned.
- **Deliverable:** Design note in findings.

### RQ-6: Commit/checkpoint linkage

- **Why it matters:** Entire commit trailers (`Entire-Checkpoint: [ID]`) give CCDash a free join between sessions and git commits/PRs — potentially unlocking "which sessions produced PR #123" views.
- **Approach:** Survey existing CCDash `features` and `progress` models; sketch a `session_commit_links(session_id, commit_sha, link_source)` table; identify 2–3 concrete UI affordances this enables.
- **Success criteria:** Schema sketch + prioritized UI affordance list; confirm no conflict with `session_mappings`.
- **Deliverable:** Design note + schema sketch.

### RQ-7: Hook-based agent registration

- **Why it matters:** If CCDash can register as an "agent," we get push-based events instead of git polling — significantly simpler live ingest.
- **Approach:** Read the Agent interface in `entireio/cli` (likely `internal/agents/`); attempt to register a noop CCDash agent (E5); if ambiguous, file an upstream issue.
- **Success criteria:** Clear yes/no on third-party registration; if no, documented fallback.
- **Deliverable:** Upstream-feedback memo; capability note.

### RQ-8: Coexistence with other session sources

- **Why it matters:** Developers will frequently have both native Claude Code JSONL and Entire checkpoints covering the same work — unmanaged this creates duplicate sessions.
- **Approach:** Enumerate overlap scenarios; propose provenance labeling (`source_type` badge in UI), soft-dedup heuristics (timestamp + agent + project match), and explicit user-facing policy.
- **Success criteria:** Written coexistence/dedup policy; UI spec sketch for provenance.
- **Deliverable:** Coexistence memo.

### RQ-9: License, redaction, privacy

- **Why it matters:** Re-ingest of potentially sensitive content from a third-party tool must not regress CCDash's local-first privacy posture.
- **Approach:** Review Entire MIT license compatibility; identify Entire's redaction scope from source; evaluate whether CCDash needs a second-pass redactor; verify CCDash does not inherit PostHog telemetry by parsing files.
- **Success criteria:** License compatibility confirmed; redaction gap list; privacy statement addendum for CCDash docs.
- **Deliverable:** Privacy/redaction memo.

## 4. Prototypes & Experiments

### E1: Branch parser prototype

- **Hypothesis:** A Python-only reader over `entire/checkpoints/v1` is sufficient for historical ingest with acceptable latency.
- **Method:** Python module using `pygit2` (primary) and `dulwich` (fallback, pure-Python) — clone/fetch a seeded repo, enumerate sharded paths, parse one checkpoint, surface structured record.
- **Metrics:** Cold-parse time for 100 and 1,000 checkpoints; peak memory; failure modes (missing branch, malformed JSON, partial/shallow fetch, very large checkpoints).
- **Go/no-go:** Go if cold-parse for 1k <15s and no library blocker on macOS+Linux; else reassess (E5 / CLI-wrap).

### E2: Live-update loop prototype

- **Hypothesis:** Fs-watch on `.git/refs/heads/entire/checkpoints/v1` beats polling for local repos; polling is acceptable fallback for remotes.
- **Method:** Two variants — (a) `watchdog` fs-watch on the ref file, (b) periodic `git fetch` with configurable interval. Measure end-to-end latency from `entire` write to CCDash row insert.
- **Metrics:** p50/p95 latency; CPU/network over 1-hour idle; behavior under rapid-fire checkpoints.
- **Go/no-go:** Go with fs-watch if p50 <10s local; polling variant acceptable if p50 <30s.

### E3: Cross-agent schema inventory

- **Hypothesis:** Checkpoint schemas are stable with a small agent-specific extension surface.
- **Method:** Install `entire` locally, enable on a scratch repo, run paired sessions with Claude Code + Gemini CLI + (best-effort) Cursor/Codex/Copilot. Capture checkpoints, diff JSON.
- **Metrics:** Field-level union/intersection; count of agent-specific fields; detection of breaking differences.
- **Go/no-go:** Go if core schema is ≥80% shared and agent-specific extensions are clearly scoped.

### E4: Ingest-into-CCDash prototype

- **Hypothesis:** The `SessionIngestSource` port from the sister SPIKE admits an `EntireCheckpointSource` with no port changes.
- **Method:** Skeleton `EntireCheckpointSource` implementing the port; push one real checkpoint end-to-end; verify session renders in CCDash UI.
- **Metrics:** Port surface additions needed (target: 0); UI render parity vs native sessions.
- **Go/no-go:** Go if port is unchanged or requires only additive changes; else feed back to sister SPIKE.

### E5: Hook registration investigation

- **Hypothesis:** Third-party agent registration is either supported or mockable with a thin shim.
- **Method:** Read Agent interface in `entireio/cli`; attempt a noop CCDash agent; if blocked, file an upstream discussion/issue.
- **Metrics:** Yes/no registration; if yes, event surface coverage for live ingest.
- **Go/no-go:** Go for hook-based live ingest if supported; else rely on E2 mechanism.

## 5. Out of Scope

- Bidirectional sync (CCDash → Entire writes) — not v1
- Replacing Entire as the primary agent-capture tool
- Cloud-Entire integration (requires paid backend) — defer
- Record-level merge of Claude Code JSONL with Entire checkpoints — follow-up SPIKE
- UI for configuring Entire itself — deferred; we only consume its artifacts

## 6. Deliverables Checklist

- [ ] Canonical Entire checkpoint schema doc (RQ-1, E3)
- [ ] ADR-NNNN: Ingest path decision (branch-parse vs CLI-wrap vs hybrid)
- [ ] ADR-NNNN: Session identity unification (schema change proposal)
- [ ] ADR-NNNN: Live-update loop mechanism
- [ ] Prototype branch with `EntireCheckpointSource` skeleton (E4)
- [ ] Upstream-feedback memo (any issues/PRs filed with `entireio/cli`)
- [ ] Coexistence / dedup policy memo (RQ-8)
- [ ] Privacy/redaction memo (RQ-9)
- [ ] Findings summary at `docs/project_plans/SPIKEs/entire-io-integration.md`

## 7. Timeline & Owners

Total: **1.5 weeks, 1 engineer**; can overlap with `remote-ccdash-streaming` SPIKE.

| Track | RQs / Experiments | Owner |
|-------|-------------------|-------|
| Data / schema | RQ-1, RQ-4, RQ-5, RQ-6, E1, E3 | data-layer-expert |
| Ingest / live-loop | RQ-2, RQ-3, RQ-7, E2, E5 | python-backend-engineer (or backend-architect) |
| Policy / product | RQ-8, RQ-9 | product + architect |
| Integration | E4 | coordinated with sister-SPIKE owner |

Suggested sequencing:
- Days 1–3: E1, E3 in parallel; begin RQ-1
- Days 4–6: E2, E5; RQ-4 migration sketch
- Days 7–8: E4 integration; RQ-6, RQ-8, RQ-9 memos
- Days 9–10: ADRs, findings synthesis, upstream-feedback memo

## 8. Dependencies on Sister SPIKE

This SPIKE assumes the `SessionIngestSource` port from `docs/project_plans/SPIKEs/remote-ccdash-streaming-charter.md` is being defined concurrently.

- **If the sister SPIKE lands first:** E4 becomes a direct implementation conformance test against the finalized port.
- **If run concurrently:** coordinate on the port signature — especially the identity contract (`source_type`, `external_id`), transcript-resolution hook, and live-event delivery shape. RQ-4 and RQ-5 findings here directly feed that signature.
- **If this SPIKE lands first:** surface proposed port additions to the sister SPIKE rather than forking.

## 9. Open Risks to Surface

- **Branch layout drift:** `entire/checkpoints/v1` is a `v1`-versioned path but has no public schema contract; minor releases could reorganize sharding or fields.
- **Best-effort redaction:** Entire's redaction is not a guarantee; CCDash may need a second-pass redactor before ingest.
- **Unbounded growth:** `entire/checkpoints/v1` has no documented retention; large repos could grow without bound. Need pagination / retention policy on the CCDash side.
- **Closed hook surface:** Third-party agent registration may be reserved; fallback is branch-parse only (RQ-7, E5).
- **Upstream product pivot:** Entireio is a well-funded startup; OSS CLI priorities could shift. Integration must degrade gracefully if Entire stalls or forks.
- **Transcript opacity:** Agent-specific transcript formats (Gemini vs JSONL) require per-agent parsers; long tail of agents is an ongoing maintenance risk.
- **Git plumbing portability:** `pygit2`/`libgit2` has native-build complexity; pure-Python `dulwich` fallback adds perf risk.

## 10. Cross-References

- Grounding brief: `.claude/findings/remote-ccdash-grounding-brief.md` (Leg 2 primary, Leg 1 for CCDash facts)
- Design spec: `docs/project_plans/design-specs/remote-ccdash-streaming.md`
- Sister SPIKE: `docs/project_plans/SPIKEs/remote-ccdash-streaming-charter.md`
- Entire repo: https://github.com/entireio/cli
- CCDash ingest touchpoints: `backend/parsers/sessions.py:11-13`, `backend/db/sync_engine.py:1-50`, `backend/db/repositories/sessions.py:59`
