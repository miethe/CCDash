---
schema_version: 2
doc_type: exploration_charter
title: "Automatic Session Naming — Exploration Charter"
status: concluded
created: 2026-08-04
feature_slug: automatic-session-naming
timebox_days: 2
hypothesis: "We believe Claude Code and Codex each persist a human-meaningful session
  name/title in an on-disk artifact CCDash already reads (or reads adjacent to), and
  that ingesting it as a nullable `session_name` column is worth building because
  every CCDash surface currently identifies sessions by opaque UUID."
deal_killer: "If neither provider persists a session name/title in any CCDash-readable
  artifact (JSONL record, sidecar, or provider-local store under a path the watcher/parsers
  can reach), AND the only way to obtain one is a model call on the read path (violating
  AOS constraint 4), abandon the automatic-naming premise."
investigation_legs:
- id: tech-claude
  question: Does Claude Code persist a session name/title in any on-disk 
    artifact CCDash can read, and with what coverage, timing, and mutability?
  assigned_to: spike-writer
- id: tech-codex
  question: Does Codex persist a session name/title in any on-disk artifact 
    CCDash can read, and with what coverage, timing, and mutability?
  assigned_to: spike-writer
- id: integration
  question: What is the full CCDash wiring surface, contract shape, and 
    H5-anchored cost to carry a nullable session_name (+ provenance) from parser
    to every consumption point?
  assigned_to: backend-architect
verdict_criteria:
  go:
  - At least one provider persists a name/title in a CCDash-readable artifact 
    with >=50% coverage on real local data
  - Deal-killer condition not triggered
  - Integration leg reports confidence >= 0.7 with an H5 anchor and a named 
    provenance vocabulary
  no_go:
  - Deal-killer condition triggered (no readable artifact for either provider, 
    and only a read-path model call remains)
  - Both technical legs report the name is unreachable/absent with confidence >=
    0.8
  conditional:
  - Exactly one provider yields a readable name and the other requires a 
    separately-named follow-up (e.g., an upstream Codex feature, or a 
    launch-time capture hook extension) — ship the covered provider, defer the 
    other with the precondition named
  - A name exists but its coverage/freshness is unknown pending a measurement 
    CCDash can run
verdict: go
verdict_rationale: "Deal-killer refuted: both providers persist an auto-generated
  session name in files CCDash already parses and currently discards. Claude Code
  emits ai-title records (self-attributed 12746/12746; 87.2% coverage on top-level
  500+-line sessions; zero summary records exist, refuting the charter's compaction
  hypothesis); Codex emits thread_name_updated (72.4% codex_vscode) which its shipped
  parser already reads past. The charter's >=50% coverage gate is NOT met on the all-files
  denominator (11.29% / 15.79%) and IS met on the nameable-session denominator; the
  segmented denominator was judged correct because non-interactive sessions (subagent
  sidechains 0/5462; headless codex_exec 0/960) have separate identity mechanisms
  and were never the target pain. Integration cost 8 pts over 16 files, with CLI/MCP/contracts/ingest
  free via passthrough and a dormant deriveSessionCardTitle chain already accepting
  an explicitTitle. Human sign-off received 2026-08-04, with explicit tier escalation
  to 2 to absorb a derived-naming lane scoped as a fourth leg."
output_artifacts:
- docs/project_plans/exploration/automatic-session-naming/spikes/tech-claude-spike.md
- docs/project_plans/exploration/automatic-session-naming/spikes/tech-codex-spike.md
- docs/project_plans/exploration/automatic-session-naming/spikes/integration-spike.md
- docs/project_plans/exploration/automatic-session-naming/spikes/derived-naming-spike.md
- docs/project_plans/exploration/automatic-session-naming/automatic-session-naming-feasibility-brief.md
updated: '2026-08-04'
---

# Automatic Session Naming — Exploration Charter

## Hypothesis Context

Every CCDash surface that references a session today shows an opaque UUID: the session inspector,
session links from features/documents/tasks, the planning session board cards, CLI `session search`
results, and the MCP `ccdash_session_detail` / `ccdash_session_search` envelopes. Both Claude Code
and Codex appear to generate human-meaningful session names/titles for their own UIs, which implies
the value already exists somewhere on disk — CCDash is simply not reading it. If true, this is the
cheapest possible legibility win: the same nullable-column + provenance pattern CCDash has now
shipped five times (`skill_name`/`skill_name_source` at schema v49, `effort_tier`/
`effort_tier_source` at v44, `model_variant`, `launcher`, `profile`).

The counterfactual today is manual correlation: an operator reads the first user message in a
transcript to work out what a session was about.

---

## Investigation Legs

### Leg: tech-claude — Claude Code Session Naming (technical)

**Question**: Does Claude Code persist a session name/title in any on-disk artifact CCDash can read,
and with what coverage, timing, and mutability?
**Assigned to**: `spike-writer`
**Expected output**: `docs/project_plans/exploration/automatic-session-naming/spikes/tech-claude-spike.md`

Unknowns this leg must resolve, **with evidence from real local data, not documentation**:
- Is there a name/title inside the session JSONL itself (e.g., a `summary`-typed record, a
  `title` field on the first/meta record, a leaf-summary pointer)?
- Is it in a separate store instead (`~/.claude/__store.db`, `~/.claude/projects/**` sidecars,
  `~/.claude/history.jsonl`, a `.capture.json`-adjacent file)?
- **Coverage**: what fraction of local sessions actually have one? Count it.
- **Timing**: is it written at session start, at first turn, or only on resume/compaction? A name
  that only lands after compaction has very different ingest semantics.
- **Mutability**: can it change mid-session or be rewritten later? Does a resumed session inherit,
  replace, or append?
- Does the name relate to Claude Code's `/rename`-style affordances or is it purely model-generated?

### Leg: tech-codex — Codex Session Naming (technical)

**Question**: Does Codex persist a session name/title in any on-disk artifact CCDash can read, and
with what coverage, timing, and mutability?
**Assigned to**: `spike-writer`
**Expected output**: `docs/project_plans/exploration/automatic-session-naming/spikes/tech-codex-spike.md`

Unknowns this leg must resolve, **with evidence from real local data**:
- Where do Codex rollout/session files live locally, and does any record carry a name/title/summary?
- CCDash already ships a Codex parser (commit `9ab006c`) — what does it currently discard that
  might carry a name?
- Same coverage / timing / mutability questions as `tech-claude`.
- If no name exists: is there a deterministic, no-model-call derivation already present in the
  payload (a task/prompt title, a `turn_context` label) that is materially better than a truncated
  first message?

### Leg: integration — CCDash Wiring Surface & Contract (risk)

**Question**: What is the full CCDash wiring surface, contract shape, and H5-anchored cost to carry
a nullable `session_name` (+ provenance) from parser to every consumption point?
**Assigned to**: `backend-architect`
**Expected output**: `docs/project_plans/exploration/automatic-session-naming/spikes/integration-spike.md`

Unknowns this leg must resolve:
- The **exact** surface list, enumerated as file paths: dual DDL (SQLite + Postgres + `_ensure_column`
  + `COLUMN_PARITY_DRIFT_ALLOWLIST`), parsers, repositories, `session_detail`, `session_search`,
  planning session-board cards, REST `/api/v1/sessions/*`, `/api/v1/capabilities`, CLI, MCP tools,
  the NDJSON remote-ingest contract, and every FE component that renders a session identity.
- **Provenance vocabulary**: does this need a `session_name_source` column following the
  `skill_name_source` / `effort_tier_source` precedent (provider-set vs derived vs operator-set),
  and what are the trust tiers?
- **Resilience AC** (CLAUDE.md rule): what does each surface render when `session_name` is null?
  Missing is a contract state, not a bug — name the fallback per surface.
- **Backfill**: is historical backfill possible, or is this write-path-forward-only like launch-time
  capture? If a name lives in the JSONL, backfill is a re-parse; if it lives in a launch hook, it is
  permanently impossible for existing rows. This materially changes the value.
- **H5 anchor**: cite the closest shipped comparable (`skill_name_source` end-to-end, commits
  `2cb0df4` + `ad7c70c`, schema v49) and justify any delta >30%.
  <!-- Corrected 2026-08-04: charter originally cited `ad9a733`, which does not exist in this repo;
       the integration leg verified `ad7c70c` as the real end-to-end commit. -->

- **Node/PG delivery**: does this need container rebuild + compose env-allowlist plumbing to reach
  the agentic node, per the known deploy hazard?

---

## Verdict Criteria Narrative

**Go** if at least one provider demonstrably persists a name in a file CCDash can read, measured
coverage on real local data is >=50%, and the integration leg produces an enumerated surface list
plus a provenance vocabulary with an H5 anchor.

**No-go** if neither provider persists a readable name and the only remaining path is a model call
on the read/render path — that violates AOS constraint 4 and makes this a different (and worse)
feature than the one hypothesized.

**Conditional** if exactly one provider yields a name, or if a name exists but its coverage cannot
be measured within the timebox. The conditional must name the concrete precondition and the command
that resolves it — not "revisit later".

---

## Out of Scope

- Operator-editable session names (rename UI, persistence of human overrides) — a follow-on, not
  this question.
- Model-generated naming inside CCDash (would violate AOS constraint 4 on the read path).
- Renaming or restructuring session **IDs**; this is a display/label field only.
- Retroactive naming of the ~16.6K historical sessions beyond whatever a plain re-parse yields.
- IntentTree/SkillMeat propagation of the name beyond CCDash's own consumption points.

---

## Citations / Prior Art

- `docs/project_plans/exploration/routing-key-skill-attribution/` — the `skill_name_source`
  provenance exploration, the closest structural precedent (concluded, shipped at schema v49).
- CLAUDE.md § "Session columns — detection, pricing, capture" — the dual-DDL + parity-allowlist rule
  every new column must satisfy.
- CLAUDE.md § "Launch-time capture" — the sidecar convention (`<session-id>.capture.json`,
  `schemaVersion` 2) and the precedent that some provenance is forward-only with no backfill.
- `docs/project_plans/PRDs/enhancements/jsonl-shape-gap-coverage-v1.md` — prior inventory of what
  the JSONL carries versus what CCDash currently ingests.

---

## Notes

- 2026-08-04: Charter scaffolded. Timebox set to 2 days (not the default 3) — the dominant unknown
  is a bounded empirical measurement over local files, not an open design question.
- 2026-08-04: All three legs concluded inside the timebox. `tech-codex` 0.9, `integration` 0.82,
  `tech-claude` 0.9.
- 2026-08-04: **Leg recovery** — the delegated `tech-claude` agent terminated on an API timeout with
  no output written. Because that leg was a bounded scripted measurement rather than an open
  investigation, it was re-run directly by the orchestrator instead of re-delegated (four full-corpus
  probe passes over 7,531 files). Recorded in the spike's Recovery note.
- 2026-08-04: **Charter criterion mis-specified, discovered by measurement.** The `go` gate
  ">=50% coverage on real local data" assumed a single-source name over an undifferentiated corpus.
  Both providers turn out to title interactive sessions and skip non-interactive ones, so the
  all-files denominator (Claude Code 11.29%, Codex 15.79%) measures the wrong population. On nameable
  sessions the same data reads 87.2% (Claude Code top-level-large) and 72.4% (`codex_vscode`). The
  verdict was taken on the segmented denominator; the discrepancy is stated explicitly in the
  feasibility brief rather than resolved silently.
- 2026-08-04: Tooling gap — `artifact-tracking/scripts/update-field.py` cannot write to
  `doc_type: exploration_charter` files (no matching schema in `schemas/`), so `output_artifacts`
  was edited directly. Worth a follow-up if exploration charters are to be CLI-managed.
</content>
</invoke>
