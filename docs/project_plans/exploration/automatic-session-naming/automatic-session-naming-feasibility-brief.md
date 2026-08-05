---
schema_version: 2
doc_type: report
report_category: feasibility
title: "Automatic Session Naming — Feasibility Brief"
status: draft
created: 2026-08-04
feature_slug: automatic-session-naming
verdict: go
verdict_confidence: 0.87
exploration_charter_ref: docs/project_plans/exploration/automatic-session-naming/automatic-session-naming-charter.md
proposed_adr_ref: null
recommended_next_action: "/plan:plan-feature --tier=2"
---

# Automatic Session Naming — Feasibility Brief

---

## 1. Synopsis

Both Claude Code and Codex already generate a human-meaningful session name and persist it inside
the same per-session JSONL files CCDash's parsers already read line-by-line — Claude Code as a
top-level `ai-title` record (`{"type":"ai-title","aiTitle":"…","sessionId":"…"}`), Codex as an
`event_msg` whose `payload.type` is `thread_name_updated` (`payload.thread_name`). CCDash currently
discards both: no `session_name` column exists, and the Codex parser's own code reads the
`thread_name` string into a local variable and throws it away. Every CCDash surface that shows a
session today shows a raw UUID instead. The exploration confirms the value is retrievable with zero
new file discovery and zero model calls on the read path — the only open questions are integration
mechanics and how to characterize coverage, not whether the data exists.

---

## 2. Investigation Summary

| Leg | Confidence | Feasibility | One-line conclusion |
|---|---:|---|---|
| tech-claude | 0.9 | feasible | Claude Code persists `ai-title` in the session JSONL, self-attributed, stable, and already-read-but-unused. |
| tech-codex | 0.9 | feasible-with-constraints | Codex persists `thread_name_updated` in the same rollout JSONL CCDash already parses, but coverage is sharply client-dependent and the current parser explicitly discards it. |
| integration | 0.82 | n/a (integration leg reports no `feasibility` field; it reports `estimated_points: 8`, `recommended_tier: 1`) | 16 required files reach the full surface via a mostly-free transport-neutral passthrough layer; no new backfill or inheritance mechanism needed. |

---

## 3. The Coverage Question

Read on the all-files denominator, coverage looks disqualifying against the charter's own bar:
Claude Code **11.29%** (850/7,531 files) and Codex **15.79%** (541/3,427 files). Both figures are
denominator artifacts, not defects. Neither provider titles non-interactive sessions: Claude Code
subagent sessions (`isSidechain`) are titled **0 of 5,462** at every size band (72.5% of the Claude
corpus; they have their own identity mechanism, `agent-name`, 4.34% coverage), and Codex's headless
`codex_exec` originator is titled **0.0%** (0/960), including its 412 spawned-subagent threads, none
of which inherit a name from a parent thread either.

On the sessions a human would actually want named — substantive, interactive work — coverage is
high on both providers: Claude Code top-level-large sessions (500+ lines) are titled **87.2%**
(251/288); Codex's `codex_vscode` originator is titled **72.4%** (257/355).

Plainly: the charter's `go` criterion of ">=50% coverage on real local data" is **not met** on the
all-files denominator, and **is met** on the nameable-session denominator (interactive/substantive
sessions). The orchestrator judges the segmented denominator correct, because non-interactive
sessions (subagent sidechains, headless `codex_exec` automation) have separate, already-shipped
identity mechanisms and were never the target of the "opaque UUID" pain the charter describes.

---

## 4. What CCDash Discards Today

- **Codex — explicit, code-level discard.** `backend/parsers/platforms/codex/parser.py`'s
  `event_msg` handling (lines ~1148–1173) computes `summary_text` from `summary`/`message`/`text`
  keys, none of which exist on a `thread_name_updated` payload, so `summary_text` is always empty;
  the branch still fires and emits an `ImpactPoint` labeled literally `"thread_name_updated"` — the
  actual `thread_name` string is read into memory and then discarded (confirmed by zero hits for
  `grep -rn "thread_name" backend/`, excluding `.venv`).
- **Codex — secondary discard, same record.** `session_meta.payload.git` (`branch`, `commit_hash`,
  `repository_url`) is present in 3,312/3,427 (96.6%) of sessions with a non-empty `branch` in
  3,256/3,427 (95.0%), yet the parser's returned `AgentSession` hardcodes `gitBranch=None`,
  `gitAuthor=None`, `gitCommitHash=None` unconditionally — the field is never read.
- **Claude Code.** No column or field named `session_name`/`sessionName` exists anywhere in the
  codebase today, so the `ai-title` record — a top-level line in a file the watcher already opens —
  never reaches `AgentSession` or the DB. The tech-claude spike did not audit the Claude parser's
  per-line handling the way the tech-codex spike did for `event_msg`, so the discard here is
  established by absence of a consuming field, not by a quoted dead-code branch.

---

## 5. Cost & Integration

**Surface list**: 16 required files for MVP wiring (schema ×2, provenance module ×1, repositories
×2, parsers ×1–2, models/routers/services ×6, FE ×5, minus overlaps) + 1 recommended
(`_V1_CAPABILITIES`) + 4–6 optional/deferred (feature-surface DTO reuse decision, secondary FE link
renderers) + 1 new test file (~250–350 lines). CLI, MCP, the standalone `packages/ccdash_cli`
formatters, and NDJSON remote ingest are dynamic passthrough layers — a field on the DTO/row reaches
all four with **zero code change**.

**Existing dormant fallback**: `components/SessionCard.tsx`'s `deriveSessionCardTitle` /
`deriveTranscriptIntelligenceTitle` chain already accepts an `explicitTitle` param and already falls
through empty-string → `sessionTypeLabel` → raw `sessionId` — predates this feature and needs no new
fallback logic; call sites just pass `session.sessionName` as `explicitTitle`.

**Provenance vocabulary recommendation**: new closed-vocabulary module
`backend/parsers/session_name_provenance.py` with three tokens — `provider_persisted` (strongest;
`ai-title`/`thread_name_updated`), `derived_deterministic` (weaker; same trust tier as the shipped
`SessionInferredTitle.source` literal but a distinct field), and `operator_set` (reserved, out of
scope per the charter).

**H5 anchor**: `skill_name_source` end-to-end (commits `2cb0df4` + `ad7c70c`, schema v49) = 5 points
shipped, 14 files, 423-line dedicated test file. Delta drivers roughly cancel: +wider cross-cutting
reach (`planning_sessions.py`, `_client_v1_sessions.py`, capabilities — none touched by the
precedent) vs. −no inheritance/backfill mechanism needed vs. −reduced uncertainty from the free
passthrough layers, with a ~20–30% net upward nudge for the genuinely new reach.

**Estimate: 8 points. Tier recommendation: Tier 1** (additive nullable columns, no destructive
migration, no cross-cutting behavioral change to routing/rollup logic).

---

## 6. Fallback Chain

This is what makes low provider coverage non-fatal — a provenance-tagged chain, not a single
source, all zero-model-call:

| Rank | Source | Provider | Coverage | Notes |
|---|---|---|---:|---|
| 1 | `ai-title.aiTitle` | Claude Code | 11.3% all / **87.2%** top-level-large | Provider-generated; highest trust |
| 1 | `thread_name_updated.thread_name` | Codex | 15.79% overall / **72.4%** `codex_vscode` | Provider-generated; highest trust; 0% on `codex_exec` |
| 2 | `agent-name` record | Claude Code | 4.34% | Correct label for subagent sessions specifically |
| 2 | `session_meta.payload.git.branch` | Codex | 95.0% | Zero model call, currently discarded; lower specificity (often `"main"`) but covers exactly the `codex_exec` population where `thread_name` is absent |
| 3 | `last-prompt` record | Claude Code | 25.51% | Deterministic, already in the JSONL |
| 3 | Extracted slash-command invocation | Codex | not measured | Parser already extracts `/command:name` tokens; coverage not scanned in this leg |
| 4 | First user message, truncated | Both | ~100% | Current de facto behaviour / counterfactual the charter asks to beat |

---

## 7. Risks & Blast Radius

From the integration spike's risk register:

| Risk | Category | Severity | Likelihood | Mitigation |
|---|---|---|---|---|
| Cross-session attribution (a name copied from/matching a different session; inheritance creep without a hop-limit) | technical | High | Low | No inheritance logic in this feature by design; if added later, mirror `skill_provenance.py`'s one-hop + `(id, project_id)`-scoped join exactly |
| Migration/column-parity drift (SQLite vs Postgres DDL diverge) | technical | Medium | Low | `COLUMN_PARITY_DRIFT_ALLOWLIST` assertion test; `skill_name_source` shipped with 0 entries as template |
| FE null-handling regression (component assumes `sessionName` always present) | technical | Medium | Medium | `deriveSessionCardTitle`'s existing empty-string-falls-through is the guard; new call sites must route through it |
| Ingest-contract versioning (old daemon never emits `sessionName`) | operational | Low | Medium | `IngestSessionEvent.payload` is `extra="allow"`; old daemon simply omits the key, no rejection |
| Node deploy drift (schema ships to main but node runs stale baked image) | operational | Medium | High (standing hazard) | `podman-compose build` (not restart) on next node redeploy; verify via `/api/health/detail` schema version |
| `LinkedFeatureSessionDTO.title` reuse ambiguity (OQ-1) creates two divergent "name" concepts | organizational | Medium | Medium | Resolve before implementation, not mid-execution |

The charter's primary feared risk was cross-session attribution. It was **directly tested and
refuted for Claude Code**: `ai-title.sessionId` matches the containing filename for **12,746 of
12,746** occurrences; the single apparent mismatch (`0eac19af-….orphaned-…jsonl`) resolves to a
filename-suffix artifact of orphan recovery, not a real cross-session pointer. `ai-title` is
self-referential, unlike a hypothetical compaction summary that would describe a pre-compaction
ancestor session.

---

## 8. Deal-Killer Assessment

Charter deal-killer, verbatim: "If neither provider persists a session name/title in any
CCDash-readable artifact (JSONL record, sidecar, or provider-local store under a path the
watcher/parsers can reach), AND the only way to obtain one is a model call on the read path
(violating AOS constraint 4), abandon the automatic-naming premise."

**Refuted.** Both providers persist a name in a JSONL file the relevant parser already opens and
reads line-by-line: Claude Code's `ai-title` record (12,746 occurrences across 850/7,531 files) and
Codex's `thread_name_updated` event (541/3,427 files, zero parse errors across the full corpus). No
model call is required on CCDash's read path in either case — the name is computed and persisted
upstream by the provider's own client; CCDash only needs to stop discarding bytes it already reads.

---

## 9. Verdict

**Verdict: go.**
**Confidence: 0.87.**

**Rationale**: The deal-killer is refuted with full-corpus evidence on both providers (tech-claude
0.9, tech-codex 0.9). The charter's coverage bar is met on the correct denominator (interactive
sessions: 87.2% Claude top-level-large, 72.4% Codex `codex_vscode`) even though the naive all-files
figures (11.29%, 15.79%) look weak in isolation, and the integration leg (0.82) delivers an
enumerated 16-file surface, a named provenance vocabulary with a valid H5 anchor (8 points, Tier 1),
and confirms zero-model-call fallback options exist for the segments where provider coverage is
genuinely absent (`codex_exec` headless, Claude subagent sidechains). Confidence is held below 0.9
because of OQ-1 (an unresolved DTO-reuse fork that could add/remove a required file) and because the
codex-side H5 estimate is provisional on parser-layer cost that the integration leg itself flags as
not fully settled.

**Recommended next action**: `/plan:plan-feature --tier=1`

---

## 10. Open Questions

**tech-claude**
- OQ-C1: What triggers `ai-title` generation? Coverage rises with session size (29.1% → 36.9% → 87.2%), suggesting a turn-count/content threshold not identified from on-disk data alone. Does not block implementation; bounds the expected coverage ceiling.
- OQ-C2: Is `ai-title` operator-influenceable (a rename affordance) or purely model-generated? Not determinable from the record shape. Affects whether `operator_set` provenance is reachable today.
- OQ-C3: Should subagent sessions inherit the parent's `ai-title`, use their own `agent-name`, or stay null? A product decision for the PRD; one-hop inheritance machinery already exists from `skill_name_source` (`2cb0df4`) if wanted.

**tech-codex**
- OQ-1: Is `thread_name_updated` produced by a client-side model call or a deterministic heuristic? Not directly observable (closed-source client); inferred model-generated from value fluency. Does not affect AOS constraint 4 — the value is already computed upstream of CCDash's read path.
- OQ-2: Will a future `codex_exec`/headless mode ever populate `thread_name`? Unmeasurable locally; name as the concrete precondition for closing the `codex_exec` gap.
- OQ-3: The 4 observed renames cluster within a ~2-minute window across different threads/dates, read as a background/batch re-titling pass rather than per-turn — not confirmed without client instrumentation or vendor docs.
- OQ-4: The 72.4%/13.8% coverage figures are measured on one machine/user's real corpus (3,427 sessions, ~9 months of usage) — not verified to generalize to other users' Codex configurations.

**integration**
- OQ-1: `LinkedFeatureSessionDTO.title: str = ""` already exists on the feature-linked-sessions surface; its current population source was not traced in this leg. Needs a targeted read before the plan phase to decide reuse vs. a distinct field.
- OQ-2: Does the tech-claude/tech-codex JSONL evidence land inside the same parser pass that already produces `skillName`/`effortTier`, or a separate sidecar/store the watcher doesn't currently open? This leg assumed the former; the sibling legs must confirm.
- OQ-3: Should `"sessions:name"` be added to `_V1_CAPABILITIES` unconditionally at ship time, or gated until coverage is proven, given the charter's own conditional-verdict language about per-provider coverage landing at different times?

---

## 11. Citations

- Exploration charter: `docs/project_plans/exploration/automatic-session-naming/automatic-session-naming-charter.md`
- tech-claude SPIKE: `docs/project_plans/exploration/automatic-session-naming/spikes/tech-claude-spike.md`
- tech-codex SPIKE: `docs/project_plans/exploration/automatic-session-naming/spikes/tech-codex-spike.md`
- integration SPIKE: `docs/project_plans/exploration/automatic-session-naming/spikes/integration-spike.md`
- Commit SHAs named in the integration spike: `2cb0df4`, `ad7c70c` (the real `skill_name_source`
  end-to-end commits — the charter's originally-cited `ad9a733` does not exist in this repo),
  `5cb8e00` (compose env-allowlist precedent for any future feature flag)

---

## Addendum — 4th Leg: Derived Naming to ~100% Coverage (added 2026-08-04, post-verdict)

Added at operator request after the `go` verdict, to close the naming gap on sessions no provider
titles. Source: `spikes/derived-naming-spike.md` (confidence 0.8, `feasible-with-constraints`).

### Target population is much smaller than the raw gap

Only **28.7% (3,145 / 10,958)** of the local corpus is a genuine derived-naming candidate. The rest
is excluded deterministically, with **zero model calls**:

| Segment | Share | Deterministic treatment |
|---|---:|---|
| Claude Code subagent sidechains | 49.8% | Parent-title inheritance — extends the existing one-hop call site at `backend/db/sync_engine.py:3307` (`backfill_skill_name_inheritance`) |
| Codex headless `codex_exec` | 8.8% | `session_meta.payload.git.branch` (95% present, currently hardcoded to `None`) |
| Provider-titled | remainder | `ai-title` / `thread_name` |

**This revises the base estimate.** The integration leg assumed "no inheritance mechanism needed";
subagent exclusion reintroduces one, at +1 pt.

### Constraint compliance

- **Constraint 4 (no model call on the read path) — satisfied.** A new `SessionNamingSweepJob` lives
  beside `backend/adapters/jobs/aar_review_sweep_job.py`, registered in `backend/runtime/container.py`
  (~lines 210–218) next to the existing `aar_review_sweep_job=` conditional block. Results persist to
  `sessions.session_name`; reads never trigger a model call. Mirrors the AAR sweep exactly.
- **Constraint 3 (never exfiltrate) — the decisive finding.** CCDash's existing hosted-LLM path
  (`backend/routers/ai.py` + `backend/services/ai_insight.py`, Gemini) sends **only aggregated
  metrics — never transcript content**. A hosted naming lane would therefore be CCDash's *first*
  transcript-content egress. The 4th leg initially recommended hosted-only on the grounds that the
  redaction gate "closes that gap"; the orchestrator rejected that reasoning — redaction strips
  known-pattern secrets, it does not make sending arbitrary transcript prose to a third party
  equivalent to not sending it.

### Lane decision (operator, 2026-08-04): **Lane A default + Lane B opt-in**

One `SessionNamingSweepJob` with two pluggable backends, selected by
`CCDASH_SESSION_NAMING_BACKEND=local|hosted`:

| Lane | Role | Egress | Notes |
|---|---|---|---|
| **A — local (Gemma/Ollama)** | **default** | none | New Ollama HTTP client (no repo precedent); requires a local model daemon; ~79 min full local backfill (untested estimate) |
| **B — hosted (Gemini/Haiku)** | **opt-in** | transcript prose | Reuses `ai_insight.py` transport; requires redaction-gate wiring **and** a compose-allowlist fix for `CCDASH_GEMINI_API_KEY` (currently `.env.example`-only — same gap class `5cb8e00` fixed for five other flags); full backfill $0.06–$1.19 |

**Constraint 3 stays intact unless explicitly opted in.** That is the reason for this shape.

**Lane C (embedding k-NN title transfer) — deferred.** It is a *build*, not a reuse: `app.session_embeddings`
DDL exists (`backend/db/postgres_migrations.py:1945`) but the `embedding` column is **always inserted
as NULL** (`backend/db/repositories/postgres/session_embeddings.py:58`; `embedding_model` /
`embedding_dimensions` hardcoded empty at `backend/application/services/session_intelligence.py:1117-1118`),
and no embedding-generation code exists anywhere in the repo. It is also enterprise/Postgres-only
(`backend/db/migration_governance.py:112`), unavailable on local SQLite — the majority deployment
target. At 9 pts it is as large as the entire base feature.
**Defer-until**: `session_embeddings` is populated by an unrelated feature (making the generation
half free), **or** the shipped lanes' title quality proves inadequate in practice.

### Provenance vocabulary (extended)

`provider_persisted` > `derived_deterministic` > `llm_derived_local` > `llm_derived_hosted`,
with `operator_set` reserved. Consumers MUST treat unknown tokens as "unknown provenance" and never
hard-fail — per the `effort_tier_source` / `skill_name_source` invariant.

### Guards (all required)

Idempotency (never derive for a session that already has any name, from any source); kill-switch +
quota following the AAR-loop pattern (`CCDASH_SESSION_NAMING_ENABLED` / `_QUOTA` / `_WINDOW_HOURS`);
fail-open (a naming failure never blocks sync); offline-CLI degradation → field stays null, which is
a contract state, not a bug.

### Revised scope

| Item | Points |
|---|---:|
| Base provider ingest (integration leg) | 8 |
| Deterministic exclusion / inheritance | 1 |
| Dual-backend naming job (Lane A default + Lane B opt-in) | ~6 |
| **Total** | **~15** |

**Tier note**: ~15 pts is formally Tier 3 (Tier 2 tops at 13). Planning proceeds at operator-directed
Tier 2 because Tier 3's SPIKE prerequisite is already satisfied by this exploration's four spikes, and
the Lane B milestone independently trips the `irreversible-outward` gate trigger (effect leaves the
system) — so it carries `gate_lens: [security]` with `gate_lens_reason: irreversible-outward`
regardless of tier.

### Added risks

| Risk | Severity | Mitigation |
|---|---|---|
| Title quality / hallucination on thin input | medium | First-message-only input; provenance column makes derived names distinguishable from provider-set; low-trust rank |
| Cost/time runaway on backfill | low | Quota + window flags; 28.7% target population, not 100% |
| Transcript egress via Lane B | **high** | Default-off; redaction gate mandatory on that path; opt-in is explicit operator action |
| Provenance confusion (provider vs derived) | medium | Four-token vocabulary with documented trust rank; FE surfaces provenance |
| Re-derivation churn | low | Idempotency guard keyed on "any name already present" |
