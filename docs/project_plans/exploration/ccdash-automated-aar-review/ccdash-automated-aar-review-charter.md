---
schema_version: 2
doc_type: exploration_charter
title: "CCDash Automated AAR Review Loop — Exploration Charter"
status: concluded
created: 2026-07-21
feature_slug: ccdash-automated-aar-review
timebox_days: 3
hypothesis: "We believe CCDash should host the AOS's automated AAR review loop — pairing
  agent-written AARs with their session logs to auto-triage sessions (surface-level
  flag reviews vs. full ARC-driven swarm deep-dives) and emit enhancement recommendations
  into op/SkillMeat — because CCDash already ingests the sessions, documents, and
  frontmatter, making it the lowest-seam home for turning post-hoc AARs into acted-upon
  system improvements."
deal_killer: "If CCDash cannot correlate an agent-written AAR to the specific session
  log(s) it describes (no existing linkage key and no feasible way to derive one),
  abandon — automated AAR↔session review is impossible without it."
investigation_legs:
- id: tech
  question: Does CCDash already ingest/expose the raw material (AAR docs, 
    session logs, frontmatter, SkillMeat linkage) in a form an automated 
    reviewer can query, and can it (a) pair an AAR to its session log(s) and (b)
    compute surface-level flags — missing artifacts, context ballooning, 
    generic-agent usage, stack-ineffectiveness — from existing data?
  assigned_to: spike-writer
- id: reuse
  question: What already exists across the AOS that this MUST reuse or extend 
    rather than duplicate — op story (AAR→PR Signal→System pipeline), ARC 
    (adversarial review council), RF run telemetry, IntentTree, SkillMeat 
    artifact-intelligence exchange — and what is the honest delta between what 
    exists and this intent? Where are the seams?
  assigned_to: general-purpose
- id: risk
  question: What are the risks of (a) auto-triaging sessions into full swarm/ARC
    deep reviews (cost explosion, unbounded recursion, LLM-on-recall-path 
    violation) and (b) recommendations that write back into 
    SkillMeat/skills/agents (blast radius)? Where must gates sit as run-record 
    state? Confirm or refute the charter deal-killer.
  assigned_to: backend-architect
- id: scope
  question: The intent bundles many capabilities (AAR↔session pairing, swarm 
    triage, ~5 surface-level flags, SkillMeat/op feedback). Which thin vertical 
    slice delivers the most value soonest at least risk, and what is the 
    full-vision → MVP carve? What tier does the MVP land at?
  assigned_to: general-purpose
verdict_criteria:
  go:
  - tech + reuse legs report confidence >= 0.7 AND a concrete AAR↔session 
    correlation key exists (or is cheaply derivable)
  - reuse leg confirms a non-duplicative seam with op story / ARC (CCDash 
    produces evidence + triage; op/ARC own model-driven synthesis + writeback)
  - Deal-killer not triggered
  no_go:
  - Deal-killer triggered (no AAR↔session correlation feasible)
  - reuse leg shows the loop is already delivered by op story + ARC with no 
    CCDash-native gap worth closing
  conditional:
  - AAR↔session pairing feasible but requires a bounded prerequisite (e.g., an 
    AAR-linkage ingest increment) — name it and the next command
verdict: go
verdict_rationale: 'All four legs support go (tech 0.82, reuse 0.82, scope 0.80, risk
  0.65-complete). Deal-killer refuted: document->session correlation already exists
  in entity_links (sync_engine.py:6574-6656); AAR->session rides the two-hop AAR->feature->sessions
  fallback with no new ingest. Non-duplicative seam confirmed: op story sources AARs
  from CCDash but terminates in a blog PR; the AAR->system-improvement loop is unowned.
  Risks mitigable with in-repo precedent (3 self-recursion guards + producer-only
  boundary per accepted ADR). MVP Tier 1 ~10-13pt; full vision Tier 3 deferred behind
  gates. Human sign-off: approved go + Tier 1 MVP handoff 2026-07-21.'
output_artifacts: []
updated: '2026-07-21'
---

# CCDash Automated AAR Review Loop — Exploration Charter

## Hypothesis Context

The AOS produces AARs everywhere (every `op story capture`, every retro), and CCDash already ingests
the session JSONL, markdown docs (with frontmatter), features, and SkillMeat artifact-intelligence.
The intent: close the seam between *post-hoc AAR* and *acted-upon improvement* by having CCDash
autonomously pair each AAR with its session log(s), triage sessions into either a cheap surface-level
flag review (missing artifacts, context ballooning, generic-agent-where-a-specialist-was-needed, tech-
stack ineffectiveness) or a full ARC-driven swarm deep-dive, and route enhancement recommendations
(new skills/agents, config changes) back through `op`/SkillMeat. The load-bearing assumption is that
CCDash *already holds the material* — this exploration verifies that and maps reuse vs. build.

---

## Investigation Legs

### Leg: tech — CCDash Data & Query-Surface Feasibility
**Question**: (see frontmatter) — data readiness + AAR↔session pairing + surface-flag computability.
**Assigned to**: `spike-writer`
**Expected output**: `docs/project_plans/exploration/ccdash-automated-aar-review/spikes/tech-findings.md`
- Enumerate existing surfaces: `agent_queries/` (feature_forensics, generate_aar, workflow_failure_patterns, session_detail, artifact_intelligence, system_metrics), MCP tools, session/document/feature/link repositories.
- Is there a correlation key AAR-doc → session(s)? (document_linking, feature linkage, frontmatter refs, cwd/session-id.)
- Which surface-level flags are computable from data already in the DB vs. need new derivation?

### Leg: reuse — AOS Seam-Mapping (op story / ARC / RF / SkillMeat / IntentTree)
**Question**: (see frontmatter) — reuse-vs-duplicate + seam ownership.
**Assigned to**: `general-purpose`
**Expected output**: `docs/project_plans/exploration/ccdash-automated-aar-review/spikes/reuse-findings.md`
- Read `../agentic_meta_dev` for `op story` (Signal→System AAR→PR), ARC/council-review, RF telemetry, IntentTree.
- Read `../skillmeat` for the artifact-intelligence exchange contract CCDash already integrates.
- Draw the ownership line: what should CCDash own (evidence, correlation, triage flags) vs. delegate.

### Leg: risk — Autonomous Orchestration Cost & Feedback Blast Radius
**Question**: (see frontmatter) — cost/recursion/gates/writeback blast radius; deal-killer check.
**Assigned to**: `backend-architect`
**Expected output**: `docs/project_plans/exploration/ccdash-automated-aar-review/spikes/risk-findings.md`
- Honor AOS constraints: no LLM on recall path; cheap-extract/expensive-synthesize; gates as run-record state; CLIs are the contract.

### Leg: scope — Value Slice & MVP Carve
**Question**: (see frontmatter) — thin vertical + tier classification.
**Assigned to**: `general-purpose`
**Expected output**: `docs/project_plans/exploration/ccdash-automated-aar-review/spikes/scope-findings.md`

---

## Verdict Criteria Narrative

**Go** if: an AAR↔session correlation key exists or is cheaply derivable, surface flags are computable
from existing data, and the reuse leg confirms CCDash fills a real, non-duplicative seam (CCDash =
evidence + deterministic triage; `op`/ARC = model-driven synthesis + gated writeback).
**No-go** if: no correlation is feasible (deal-killer), or op story + ARC already deliver the loop
end-to-end with no CCDash-native gap.
**Conditional** if: pairing is feasible but gated behind a bounded prerequisite (name it + next command).

---

## Out of Scope

- Building a new model-driven synthesis engine inside CCDash (op/ARC own that).
- Changing the `op story` gate semantics or the persona/memory pipeline.
- Any autonomous writeback that bypasses existing HITL gates.

---

## Citations / Prior Art

- `~/.claude/CLAUDE.md` — Operator (`op story` AAR pipeline), ARC, RF telemetry, model routing.
- CCDash `CLAUDE.md` — agent_queries intelligence layer, `ccdash_generate_aar`, artifact-intelligence exchange.
- Recent CCDash work: RF run telemetry (9594fcc), session-detail/transcript endpoints, redaction layer.

---

## Notes
- 2026-07-21: Charter scaffolded via `/plan:explore`. 4 legs selected (Tier-3 greenfield, cross-system).
