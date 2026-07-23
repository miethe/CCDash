---
leg: priorart
question: "OQ-E — Does the existing ARC (op council / council-review) pipeline ALREADY
  provide the 'capable model' rung v2 proposes, i.e. is the top of v2's escalation ladder
  just the existing ARC pipeline rather than a bespoke capable-model call?"
feature_slug: ccdash-aar-review-semantic-triage-tier
assigned_to: ica-executor
updated: 2026-07-23
confidence: 0.82
---

# Prior Art Findings — OQ-E (Does ARC already own the capable-model rung?)

## Internal Matches

| System | What it does | Closeness to v2's "capable model" rung (step 3-4) | Delta |
|---|---|---|---|
| **ARC / council-review** (`agentic-research` repo + `.claude/skills/council-review/`, adapter contract `docs/agentic-operator/contracts/arc.md`) | Three-step pipeline: `arc run` scaffolds an 11-artifact bundle → `council-review` skill runs independent reviewer passes + adjudication (real model work) → `arc validate` schema-gates → verdict read from `scorecard.json.recommendation` (`proceed \| proceed_with_conditions \| narrow_scope \| pause_and_validate \| redesign \| reject`), findings with severity/evidence, a decision record, and a validation plan. Adjudication runs on primary Opus (MUST-stay tier per MODEL-ROUTING), authoring lane can offload to ICA. | **HIGH.** This is structurally *more* than v2's step 3-4 asks for: full-data review (`--target`), draft recommendations (`findings.yaml.accepted[].recommendation`, `decision_record.md`), gated emission (`arc validate` + op's own approve/writeback gates), never a direct mutation. | It is heavier-weight than a single "capable model call" — multi-reviewer, adversarial, schema-bundled, explicitly invoked with a target+objective. It has no notion of a *session/AAR candidate* as its unit of work; someone (op, human) must hand it a target string. It does not run *itself* on a queue of triage candidates. |
| **op two-dial classifier** (`operator_core/core/classify.py`) | Cascade: explicit-verb (0 model calls) → deterministic keyword/tier scoring (0 model calls) → **optional Haiku structured classify** (only on ambiguous/multi-route text, only if an `llm` backend is wired) → optional Opus decomposition. Degrades to `clarify` with no backend, by design. | **MEDIUM (pattern match, not capability match).** This is the *same shape* v2 proposes (cheap deterministic pre-filter → cheap model → capable model escalation) — but it classifies **short natural-language user intent strings** (route × tier), not **full session/AAR evidence bundles**. It has never read a transcript. | Same escalation-ladder *pattern*, wrong *domain*. Reusing this classifier as-is would require feeding it AAR evidence, which it isn't built to consume, and its LLM tiers are gated behind an "ambiguous text" trigger, not "evidence warrants semantic judgment." |
| **`op story` Signal→System pipeline** (`_classify_candidate` in `operator_core/adapters/story.py`) | Sources AARs (incl. from CCDash via `ccdash report aar --feature`), scores them with a **deterministic** keyword-density heuristic (`novelty/narrative/forensic/audience/dedup` subscores, all regex/word-count based — zero model calls) into `post \| hold \| archive`, then a gated `story.review` → `story.approve_draft` → blog-draft PR. | **LOW-MEDIUM.** It is CCDash-adjacent (already consumes CCDash's AAR surface) and shares the "cheap deterministic pre-filter, gated escalation" shape, but the destination (a public blog-story draft) and the rubric (blog-worthiness: novelty/narrative-arc/audience-fit) are a categorically different judgment than "does this session merit a system-improvement review." The v1 PRD explicitly calls this out (`story.py:1462-1485`'s `_classify_candidate` "scores blog-worthiness, a different rubric entirely"). | Wrong rubric, wrong sink. Also: `_classify_candidate` has **no model-touching semantic pass at all today** — it is exactly as deterministic as CCDash's own v1 flags, just a different heuristic. It does not currently fill v2's "cheap model semantic pass" gap either. |
| **CCDash v1 AAR review loop** (this repo, shipped P1 / planned P2-P4) | Deterministic 5-flag triage over already-ingested session+AAR+task evidence → 3-verdict rollup (`surface_only \| deep_review_recommended \| human_triage_required`) → emitted as `aar_review_candidate` events; P3 (planned, not yet built) specifies that **`op`, at its own existing classify→plan→dispatch gate, routes each candidate to a surface note, `op council` (= ARC), or discard** — i.e. the v1 PRD *already* names ARC as the escalation destination. | **Directly the predecessor of this v2 spec** — v1 already draws the seam exactly where v2's step 3-4 would land ("op council invokes the ARC council pipeline"). | v1's gap (which v2 is trying to fill) is real and lives entirely **upstream of ARC**: nothing today decides, with semantic judgment, *which* `deep_review_recommended`/`human_triage_required` candidates are worth forwarding to `op council` at all. Today that decision is either (a) a human skimming the candidate list, or (b) op's classify cascade *if and only if someone hands it the candidate as a request string* — there is no automated bridge. |
| **`op persona reconcile`** (`operator_core/adapters/persona.py`) | "The only model-touching persona reconcile path" — drains a persona-fact inbox through SkillMeat extraction, model-assisted reconciliation, then pauses at a writeback gate. | **LOW.** Same cheap-artifact → model-touching-synthesis → gated-writeback shape, but scoped to persona facts, not session/AAR evidence, and it is explicitly the *only* model-touching path in that adapter (i.e. even op is disciplined about walling model calls into one narrow, gated seam per subsystem — reinforcing the "keep model calls in one named place" convention v2 itself follows). | Confirms the AOS-wide convention (narrow, named, gated model-touching seams) that v2's own step 2 (a *new* named seam) would need to match — it is not itself a reusable capable-model rung for AAR triage. |

## Does ARC already provide the capable rung?

**Partial-yes, with a real gap directly upstream of it.**

- **YES** in the sense that matters most for OQ-A/OQ-E's deal-killer test: if a semantic-triage
  candidate is deemed worth a deep, full-data, capable-model review with draft recommendations,
  **that destination already exists, is already named in the shipped/planned v1 PRD's P3 scope
  ("`op council` invokes the ARC council pipeline"), and needs zero new CCDash-side or op-side
  build to serve as the "capable model rung."** ARC's `scorecard.json.recommendation` +
  `findings.yaml.accepted[].recommendation` + `decision_record.md` already are a superset of
  v2's step-3/4 ask ("full-data review + draft recommendations... emitted ONLY through the
  existing gates"). Building a bespoke capable-model call inside CCDash (or even inside op) to
  duplicate this would violate "reuse, don't rebuild" (v1 PRD's own Constraint 3) and create a
  second, parallel deep-review pipeline with a different schema/gate/audit trail than ARC's.
- **NO / gap** in the sense that matters for OQ-D and the actual "should CCDash build v2" question:
  **ARC has no autonomous entry point.** It is a two-step *verb*, not a *service* — someone
  (human or op) must hand it a `--target`/`--objective` string. There is no mechanism today,
  anywhere in the AOS (not CCDash, not op's classifier, not `op story`), that reads a queue of
  `aar_review_candidate` events and decides, with **semantic** judgment over the full evidence,
  which ones are worth spending an ARC council run on. Op's own classify cascade is the closest
  *pattern* match but is wired to natural-language intent text, not evidence bundles, and is only
  invoked reactively (something has to ask op to classify it).
- **Net**: v2's step 3-4 ("capable model full-data review + draft recommendations, emitted through
  op gates") **is not new — it is ARC, already specified as the v1 P3 destination.** v2's step 2
  ("cheap model does a bounded semantic pass over the ingested evidence... only survivors
  escalate") **is the one piece nothing in the AOS owns today.** That piece is also the one piece
  that is architecturally awkward for op to own cheaply, because op has no data-locality advantage
  over CCDash for a *per-candidate* semantic pre-filter — shipping full evidence per candidate to
  an op-side Haiku pass has the same "wasteful data shipping" cost the design spec's own
  deal-killer language raises for the opposite direction.

## External Prior Art

No web search was performed (per instructions); the following are named, well-established patterns
recalled from general knowledge, offered as comparables rather than citations to verify:

- **Cascade classification / "cheap filter, expensive judge" ladders** — the general pattern
  behind spam/abuse triage (rule-based filter → small classifier model → human/expert review),
  and behind modern LLM-ops cost control (small model does bulk triage, large model reserved for
  escalations). This is the same shape as op's own classify cascade and v2's proposed ladder;
  it is a well-known cost-control pattern, not something CCDash or op invented.
  Also matches the general "LLM router" / model-cascade literature (route requests to the
  cheapest model that can answer correctly, escalate on low confidence).
- **LLM-as-judge with escalation** — the pattern where a cheap model scores/screens outputs and
  only low-confidence or high-stakes items get a second, more capable judge pass (common in
  RLHF/eval pipelines and content-moderation systems). ARC's "independent reviewers → adjudicator"
  step is itself an instance of a **multi-reviewer LLM-as-judge with adversarial adjudication**
  pattern (closer to a "red team panel" than a single judge call), which is a stronger, more
  audited version of what v2's step 3 describes.
- **Postmortem/incident-review triage ladders** (SRE literature: PagerDuty/Google SRE postmortem
  culture) — automated log/metric anomaly detection (cheap, deterministic) feeds a triage queue;
  only incidents crossing a severity bar get a full postmortem review (expensive, human- or
  panel-driven). CCDash's v1 5-flag/3-verdict system already mirrors the "cheap deterministic
  triage" half of this pattern; ARC mirrors the "full postmortem panel" half. The literature's
  middle rung (a **semantic** triage pass between cheap detection and full review) is exactly the
  piece v2 is trying to add — and in most published incident-triage systems that middle rung is
  a narrow, purpose-built classifier (not a general capable-model call), which argues for a
  narrow, cheap, single-purpose model (Haiku-tier) if this is built at all, not a second ARC-shaped
  pipeline.
- **RAG/agent "self-critique before escalation" pattern** — an agent or pipeline does a cheap
  self-check pass before invoking an expensive tool/human; if v2's step 2 is built, it should be
  scoped this narrowly (one bounded semantic question: "does the evidence support the AAR's claim,
  yes/no + confidence"), not a general-purpose reviewer, to avoid re-implementing ARC's role.

## Build-vs-Reuse Recommendation

- **Step 3-4 (capable model full-data review + draft recommendations, gated emission): REUSE.**
  This is ARC/council-review, already named as the v1 P3 destination. No new build needed in
  CCDash or op. The only remaining work is the cross-repo wiring the v1 PRD already scopes for
  P3 (op reads `aar_review_candidate`, routes to `op council` at its own gate) — which is
  explicitly out of *this* repo's build surface already.
- **Step 2 (cheap-model semantic pre-filter over ingested evidence): BUILD, if built at all — but
  narrowly, and the ownership question (OQ-A) still needs its own answer.** Nothing in the AOS
  today performs this specific function. If CCDash builds it (per this v2 spec's alt B/C), it
  should be scoped as narrowly as the external patterns suggest — a single bounded semantic
  question per candidate, not a general reviewer — specifically to avoid duplicating ARC's role
  or op's classifier's role. If op builds it instead (alt A / status quo), it would slot in as a
  new, narrow, named model-touching seam in op's own adapter layer (matching the `op persona
  reconcile` precedent of one narrow gated seam per capability), consuming CCDash's existing
  `aar_review_candidate` events over the API — which does not require CCDash to build anything
  new at all.
- **This finding does not resolve OQ-A on its own** (that is the risk leg's job), but it
  materially **narrows the scope of what v2 needs to justify**: the deal-killer question is no
  longer "should CCDash build a whole cheap→capable ladder," it is "should CCDash build the single
  narrow cheap-model pre-filter step, or should op" — because the capable-model top rung is
  already solved by ARC regardless of who builds the middle.

## Confidence

**0.82** — High confidence on the ARC/council-review capability match (direct primary-source read
of the adapter contract, the skill definition, and the v1 PRD's own P3 scope, which independently
corroborates the same conclusion). Confidence is not higher because: (1) external prior-art claims
are from general knowledge without live web verification per instructions, so pattern names are
offered as comparables, not citations; (2) whether op's classify cascade *could* be cheaply
repurposed to consume evidence bundles (rather than intent strings) was not empirically tested,
only inferred from reading `classify.py`; (3) this leg did not independently verify the risk leg's
territory (cost/quota governance, self-recursion interaction) which could still shift the
build-vs-reuse call for step 2.
