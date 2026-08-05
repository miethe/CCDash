---
it_schema: 1
schema_version: 2
feature_slug: automatic-session-naming
title: "Automatic Session Naming \u2014 implementation plan"
doc_type: implementation_plan
status: draft
prd_ref: docs/project_plans/PRDs/enhancements/automatic-session-naming-v1.md
plan_ref: null
commit_refs:
- 0de559a
pr_refs: []
files_affected: []
deferred_items_spec_refs: []
findings_doc_ref: null
changelog_required: true
tier: 2
priority: P2
points: 15
risk_level: medium
context_class: C3
created: '2026-08-04'
related_documents:
- docs/project_plans/PRDs/enhancements/automatic-session-naming-v1.md
- docs/project_plans/exploration/automatic-session-naming/automatic-session-naming-feasibility-brief.md
- docs/project_plans/exploration/automatic-session-naming/spikes/integration-spike.md
- docs/project_plans/exploration/automatic-session-naming/spikes/derived-naming-spike.md
acceptance_criteria:
- sessions.session_name + session_name_source exist in BOTH SQLite and Postgres DDL,
  with a passing COLUMN_PARITY_DRIFT_ALLOWLIST check.
- A Claude Code session with an ai-title record and a Codex session with thread_name_updated
  both surface their provider name in session detail, search, and the planning session
  board.
- Every session resolves to a better-than-UUID label; sessions with no name render
  a defined fallback, never a crash or blank.
- No read/render path triggers a model call; the naming job is worker-side and its
  result is persisted.
- Default configuration performs ZERO off-box egress of transcript content.
open_questions:
- 'OQ-C1: what triggers ai-title generation? Coverage rises with session size (29.1%/36.9%/87.2%)
  but the trigger is unobserved. Bounds the coverage ceiling; does not block.'
- 'OQ-C2: is ai-title operator-influenceable, or purely model-generated? Determines
  whether operator_set provenance is reachable now or stays reserved.'
- 'OQ-1: LinkedFeatureSessionDTO.title has unclear provenance and may already overlap
  session_name. Resolve in M1 before adding a second title field to the same DTO.'
decisions:
- decision: Lane A (local Ollama/Gemma) is the DEFAULT derived-naming backend; Lane
    B (hosted) is OPT-IN via CCDASH_SESSION_NAMING_BACKEND=local|hosted.
  rationale: Equal cost (4 pts each). ai_insight.py sends only aggregated metrics,
    so Lane B would be CCDash's FIRST transcript-content egress. Redaction mitigates
    but does not eliminate that; local keeps AOS constraint 3 intact by default.
  status: accepted
- decision: Lane C (embedding k-NN title transfer) is DEFERRED.
  rationale: "Build, not reuse \u2014 app.session_embeddings.embedding is always inserted\
    \ NULL and no embedding-generation code exists; enterprise-Postgres-only, unavailable\
    \ on local SQLite. 9 pts, as large as the base. Defer-until: session_embeddings\
    \ is populated by another feature, OR shipped title quality proves inadequate."
  status: accepted
- decision: 'Provenance rank: provider_persisted > derived_deterministic > llm_derived_local
    > llm_derived_hosted; operator_set reserved.'
  rationale: Follows the shipped skill_name_source / effort_tier_source precedent.
    Consumers treat unknown tokens as unknown provenance and never hard-fail.
  status: accepted
- decision: Coverage is judged on the nameable-session denominator, not all-files.
  rationale: Neither provider titles non-interactive sessions (subagent sidechains
    0/5,462; codex_exec 0/960); those have separate identity mechanisms. Segmented
    coverage is 87.2% / 72.4%.
  status: accepted
routing_constraints:
- "Provenance + attribution correctness (the M1 sessionId assertion) MUST stay claude-primary\
  \ \u2014 a wrong name on the wrong session is the failure mode this feature exists\
  \ to avoid."
- "The Lane B egress path and its redaction-gate wiring (M3) MUST stay claude-primary\
  \ \u2014 no offload."
- Dual-DDL mechanical sweeps, FE null-fallback wiring, and test scaffolding are offload-eligible.
- 'Capability bar: sonnet-class throughout; the M3 egress boundary requires Opus review
  before merge.'
wave_plan:
  waves:
  - - M1
  - - M2
  - - M3
  phases:
  - id: M1
    title: Provider-set names are ingested and visible
    depends_on: []
    exit_criteria:
    - Dual DDL + parity check green; ai-title and thread_name_updated both land in
      sessions.session_name with provenance provider_persisted.
    - session_name renders in session detail, search, and the planning board; null
      renders the defined fallback.
    gate_lens:
    - validator
  - id: M2
    title: Every session has a better-than-UUID name, with zero model calls
    depends_on:
    - M1
    exit_criteria:
    - Subagent sessions inherit the parent title; Codex codex_exec sessions fall back
      to git.branch; remaining sessions fall back deterministically.
    - No session renders a bare UUID; provenance is derived_deterministic on every
      fallback.
    gate_lens:
    - validator
  - id: M3
    title: Derived naming closes the remainder, local-by-default
    depends_on:
    - M2
    exit_criteria:
    - SessionNamingSweepJob names the residual population worker-side; results persist;
      no read path calls a model.
    - Default config performs zero egress; the hosted backend is unreachable without
      an explicit opt-in flag AND the redaction gate.
    gate_lens:
    - security
    - validator
    gate_lens_reason: irreversible-outward
updated: '2026-08-05'
merge_commit: 0de559a
merge_branch: main
---

# Implementation Plan — Automatic Session Naming

Today every CCDash surface labels a session with an opaque UUID, while both Claude Code and Codex
already write a human-meaningful name into the JSONL files CCDash parses line-by-line and discards.
When this is done, every session carries a name, the strongest available source wins, and the
provenance of each name is legible.

## Scope boundary

**In:** session ingest parsers (Claude Code + Codex), `sessions` dual DDL + provenance vocabulary,
repositories, session detail/search, planning session board, REST + capabilities, `types.ts` and the
FE title chain, and a worker-side derived-naming job with two pluggable backends.

**Out (stated, not silently dropped):**
- **Lane C embedding k-NN transfer** — deferred with a named condition (see `decisions`).
- **Operator-editable names / rename UI** — a follow-on; `operator_set` provenance is reserved but unused.
- **Retroactive naming beyond a plain re-parse** — the name is in the JSONL, so history is recoverable
  by re-parse; no separate backfill machinery is in scope.
- **Propagating the name to IntentTree / SkillMeat** — CCDash's own consumption points only.

## Rubric — what "good" looks like

A reviewer should open any session and immediately know what it was about, and be able to tell *how*
that name was obtained without reading code. Names never silently degrade: a weaker source never
overwrites a stronger one, and an unnameable session looks deliberately unnamed rather than broken.
The strongest signal of success is that the default deployment sends nothing off-box and nobody had
to configure anything to get that.

Extend what exists rather than adding parallel machinery. Exploration found three reuses — the FE
title chain, the one-hop subagent inheritance call site, and the worker-sweep-job shape. A solution
that introduces new equivalents of them is worse even if its tests pass.

## Named risks

- **Wrong name on the wrong session.** Highest-consequence failure. `ai-title.sessionId` measured
  12,746/12,746 self-referential, so the parser MUST assert it equals the file's session id and skip
  on mismatch — that assertion is what keeps the property true under future provider changes. Handle
  `.orphaned-<ts>-<hash>` filename suffixes.
- **Egress by accident.** A config default flipped later would start sending transcript prose off-box
  silently. Assert the default by test, not documentation, and apply the compose env-allowlist fix for
  `CCDASH_GEMINI_API_KEY` (gap class `5cb8e00` fixed for five other flags) so the failure mode is
  "not configured", never "quietly on".
- **Column-parity drift.** New columns need SQLite + Postgres DDL in one change set plus the allowlist
  check. The node runs migrations from api and worker concurrently and has crashed on
  `DuplicateColumnError` before self-healing — expect it; don't misattribute it to this feature.
- **Stale-image deploys.** The node executes baked-image code, so node verification needs
  `podman-compose build`, not `up -d`.
- **Provenance confusion.** Four sources means a derived name can be mistaken for a provider one. The
  FE must surface provenance wherever it shows a name.

## References

- `backend/parsers/platforms/codex/parser.py` — `event_msg` branch that reads `thread_name` and drops
  it; also hardcodes `gitBranch=None` while `session_meta.payload.git.branch` is 95% present.
- `backend/db/sync_engine.py:3307` — the one-hop inheritance call site M2 extends.
- `backend/adapters/jobs/aar_review_sweep_job.py` + `backend/runtime/container.py` (~210–218) — the
  worker-job shape and registration point M3 copies.
- `components/SessionCard.tsx` — `deriveSessionCardTitle` / `deriveTranscriptIntelligenceTitle`, the
  dormant chain that already accepts `explicitTitle`.
- `backend/application/services/agent_queries/redaction.py` — the gate Lane B must pass through.
- H5 anchor: commits `2cb0df4` + `ad7c70c` (`skill_name_source`, schema v49) — 5 pts, 14 files.

## Milestones

### M1 — Provider-set names are ingested and visible

Both provider names reach the database and every read surface. Schema carries `session_name` and
`session_name_source` in both backends; the Claude Code parser consumes `ai-title` and the Codex
parser stops discarding `thread_name_updated`; the FE title chain is fed, not replaced.

**Mode-D**: performs a schema migration — halts for explicit human approval.

**AC:** dual DDL present and parity check green; a real Claude Code session and a real Codex session
each surface their provider name in detail, search, and the planning board; `session_name` is escaped
on render (it can arrive caller-controlled via the NDJSON ingest path); null renders the defined
per-surface fallback; OQ-1 resolved before a second title field is added to the same DTO.

### M2 — Every session has a better-than-UUID name, with zero model calls

The deterministic chain closes most of the gap with no model call: subagent sessions inherit the
parent title, Codex headless sessions use `git.branch`, the remainder falls through `last-prompt`
then a truncated first message.

**AC:** no surface renders a bare UUID; each fallback writes `derived_deterministic`; subagent
inheritance reuses the existing call site rather than a new mechanism; a weaker source never
overwrites a stronger one.

### M3 — Derived naming closes the remainder, local-by-default

A worker-side `SessionNamingSweepJob` names the residual population (28.7% of the local corpus) via
one of two pluggable backends. Local is the default and sends nothing off-box.

**AC:** job is worker-side and persists results — no read/render path calls a model, asserted by
test; default config performs zero egress, asserted by test; the hosted backend requires both an
explicit opt-in flag and the redaction gate; idempotency holds (never re-derive when any name is
present from any source); quota + kill-switch flags follow the AAR-loop pattern; failures fail open
and never block sync; the offline CLI leaves the field null as a contract state.

## AC -> command -> evidence

| AC | Command | Evidence of pass |
|---|---|---|
| Dual DDL + parity | `backend/.venv/bin/python -m pytest backend/tests/ -k "column_parity" -v` | Parity test passes; allowlist unchanged or explicitly amended |
| Provider names ingest | `backend/.venv/bin/python -m pytest backend/tests/test_session_naming.py -v` | Claude `ai-title` and Codex `thread_name_updated` fixtures both yield `provider_persisted` |
| Attribution assertion | same file, mismatch case | A record whose `sessionId` differs from the file's id is skipped, not stored |
| No bare UUID / fallbacks | `backend/.venv/bin/ccdash session search "" --limit 50 --json` | Every row has a non-UUID `session_name` with a provenance token |
| Null resilience (FE) | `npx vitest run components/__tests__` | Null `session_name` renders the fallback on every surface; no crash |
| Zero egress by default | `backend/.venv/bin/python -m pytest backend/tests/ -k "naming_egress" -v` | Default config resolves to the local backend; hosted path unreachable without the opt-in flag |
| No model call on read path | `backend/.venv/bin/python -m pytest backend/tests/ -k "naming_read_path" -v` | Read/render paths make no client call; job is worker-registered only |
| Runtime smoke (UI) | `npm run dev` + browser check | Names render on session inspector, session links, and planning board |

## Sequencing (only if load-bearing)

M1 → M2 → M3 is load-bearing, not house style: M2's fallback chain must not overwrite a
provider-set name, so the provenance rank M1 establishes has to exist before fallbacks are written;
and M3's idempotency guard is defined as "any name already present", which requires M1 and M2 to be
populating names first. The schema migration in M1 is also a serialization barrier — nothing else
may land against the `sessions` table concurrently.

## Execution ledger

Deviations and conservative choices are logged with rationale to
`.claude/worknotes/automatic-session-naming/implementation-notes.md` and reviewed at each milestone
boundary — rather than halting on them.

**Blockers still stop** (work that cannot correctly proceed: a failing test on current work, an
unsatisfiable declared artifact, exhausted recovery). Beyond those, mid-milestone halts are only for:
destructive action, real scope change, or input only the operator has.

**Mode-D boundaries are unchanged and non-negotiable** — **auth · payments/billing · schema
migrations · data deletion · secret rotation · infrastructure**. M1 touches schema migrations and
says so in its AC.
