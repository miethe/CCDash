---
schema_version: 2
doc_type: report
report_category: feasibility
title: "CCDash AAR Review — Autonomous Semantic-Triage Tier (v2) — Feasibility Brief"
status: finalized
created: 2026-07-23
updated: '2026-07-23'
feature_slug: ccdash-aar-review-semantic-triage-tier
verdict: no-go
verdict_confidence: 0.8
exploration_charter_ref: 
  docs/project_plans/exploration/ccdash-aar-review-semantic-triage-tier/ccdash-aar-review-semantic-triage-tier-charter.md
proposed_adr_ref:
recommended_next_action: 'archive'
related_documents:
- docs/project_plans/design-specs/ccdash-aar-review-semantic-triage-tier.md
- docs/project_plans/PRDs/features/ccdash-automated-aar-review-v1.md
- docs/project_plans/implementation_plans/features/ccdash-automated-aar-review-v1.md
- docs/project_plans/exploration/ccdash-automated-aar-review/ccdash-automated-aar-review-proposed-adr.md
---

# CCDash AAR Review — Autonomous Semantic-Triage Tier (v2) — Feasibility Brief

<!-- verdict and verdict_confidence populated; ready for review. -->

---

## 1. Synopsis

v1's AAR↔session triage is deterministic-only by design (Hard Invariant #1: no LLM on CCDash's
read/recall/compute path). Signals needing semantic judgment — a claimed outcome not matching the
transcript, a subtly-wrong "successful" agent/skill choice, an evidence-only recommendation — are
structurally invisible at the CCDash layer. v2 proposed a seam-preserving, opt-in, flag-gated
SYNTHESIS job lane (deterministic pre-filter → cheap-model semantic pass → capable-model
escalation, output only through existing op gates), close to CCDash's data on the premise that
data locality makes a local semantic pre-filter cheaper than shipping evidence to op. The
load-bearing question this exploration exists to answer is **ownership** — CCDash (data locality)
vs op (single synthesis owner) — *before* any tier classification or PRD. The four legs converge:
a CCDash-side build is feasible only in its weakest form, and it is not desirable. **No-go.**

---

## 2. Investigation Summary

| Leg | Agent | Confidence | Findings | Conclusion |
|-----|-------|-----------|----------|------------|
| tech | ica-executor | 0.82 | [tech-findings](spikes/tech-findings.md) | Feasible-with-constraints; only **Alt C** yields a structural "provably off-path" proof (Alt B forces relaxing the CI-enforced no-LLM import audit). Feasibility ≠ desirability. |
| risk | ica-executor | 0.82 | [risk-findings](spikes/risk-findings.md) | **CONFIRMS the deal-killer.** Data-locality premise is quantitatively false (tiny survivor set; live PULL endpoint already exists); Invariant #1 blast radius is asymmetric + permanent for a CCDash-hosted lane. op should own the tier. |
| value | ica-executor | 0.55 | [value-findings](spikes/value-findings.md) | Only S1 + S5 clear value>cost, narrowly scoped to structured evidence and gated on population. Residual value is thin; no in-repo AAR corpus to measure fire-rates. |
| priorart | ica-executor | 0.82 | [priorart-findings](spikes/priorart-findings.md) | The capable-model rung (step 3–4) **IS ARC/council-review**, already named as the v1 P3 destination → REUSE, no new build. The only unowned piece is the cheap-model pre-filter (step 2), for which op has no data-locality disadvantage. |

---

## 3. Cost Estimate

**H5 anchor** (tech leg): v1 P6 (autonomous worker + gated writeback + 3 guards) = **6–9 pts**;
v1 remaining total = 26–34 pts.

| Alt | CCDash-side build | Position vs H5 anchor |
|-----|-------------------|-----------------------|
| **Alt B** (CCDash-hosted job lane) | **13–21 pts** | *Above* anchor — inherits full P6 worker cost + model-client integration + cost/quota fold-in with the 3 guards + **re-scoping the CI-enforced no-LLM import audit** (architecturally expensive, unquantifiable regression risk) + redaction re-proof. |
| **Alt C** (CCDash-adjacent worker over v1 API) | **2–5 pts** | *Below* anchor — endpoints, redaction egress, and capability discovery already shipped; only optional `?verdict=`/`?since=` filter + pagination hardening + contract/docs. The model lane itself moves off CCDash's ledger entirely (op-owned estimate). |

**Cost verdict**: The only *cheap* CCDash-side option (Alt C, 2–5 pts) is cheap precisely because
it builds nothing new — it exposes what Phase 4/5 already shipped. Alt C's CCDash content is a
deployment-locality note, not a deliverable. Alt B's cost is dominated not by LOC but by the
permanent architectural cost of weakening the machine-checked invariant.

---

## 4. Value Statement

**Primary beneficiaries**: op (single synthesis owner) and the human operator reviewing AAR
candidates; secondarily SkillMeat ranking feedback loops.

**Evidence of demand** (value leg, 0.55 — reasoned bounds, not measured rates; no in-repo AAR
corpus exists to sample):
- Only **S1** (lightweight outcome-narrative mismatch, structured evidence only, ~2–4.5K tok/candidate)
  and **S5** (root-cause-vs-symptom, piggybacking the already-triggered `stack_ineffectiveness` subset)
  clear value>cost — and only when scoped to structured evidence (never raw transcript) and gated
  on population (not universal `surface_only` scans).
- **S2, S3, S4 do not clear the bar** as pre-filter signals: S2/S4 balloon to transcript-read cost
  (capable-model-tier, not cheap-pre-filter), S3's value is diffuse/aggregate, S4 is a noise
  generator that competes for the 5/24h escalation quota reserved for flag-shaped signals.

**Counterfactual**: If not built, `deep_review_recommended`/`human_triage_required` verdicts still
route to a human or to op's downstream pipeline (which already runs a model-driven reconciliation
via `op story capture/scan` → gated Signal→System). The marginal, non-duplicated value of a
CCDash-side tier is a narrow slice (false-negative catching on `surface_only`), not the broad
"run a model over every AAR" framing — and that slice is precisely what op can serve from its own
side over the existing API.

---

## 5. Risks & Blast Radius

| Risk | Category | Severity | Mitigation |
|------|----------|---------|------------|
| **R1 — Import-audit erosion (Invariant #1).** A real LLM client anywhere in `backend` demotes the invariant from "structurally trivial" (no LLM import exists) to "reachability-fragile" (a graph-walk any future shared-util refactor can silently defeat). Permanent, asymmetric. | technical | **Critical** | Only Alt C (fully separate process/repo, no shared `backend` import surface) preserves the trivial-audit property. Alt B cannot. Best mitigation: no model in `backend` at all → op ownership. |
| **R2 — Guard 1 (provenance) defeat by mistagged model output.** A CCDash-hosted lane producing model-authored artifacts must tag every output with reserved markers or re-enter triage (unbounded self-reference). | technical | High | op-owned synthesis tags its own downstream artifacts; CCDash's fail-closed column guard stays correct. |
| **R3 — Guard 2 (dedup PK) collision.** A semantic verdict on the same `(aar_document_id, session_id)` pair collides with the deterministic row → requires a `tier` PK dimension → migration on a shipped table (dual DDL, ADR-007). | technical | High | op persists its own verdicts in op's store; CCDash's `aar_reviews` schema stays untouched. |
| **R4 — Cost/quota governance CCDash does not own.** CCDash has no token/dollar budgeting; Guard 3 is a count-based escalation gate, not a compute budget. A CCDash model lane needs net-new governance duplicating op's `MODEL-ROUTING.md`. | operational | High | op already owns model routing, effort tiers, and budget. |
| **R5 — New secret/egress surface.** An in-process model lane adds an API key + outbound provider egress to a local-first, LAN-only dashboard that has none on its read path. | operational | Medium | Alt C isolates to a separate process; op ownership keeps it entirely outside CCDash. |
| **R6 — Re-litigating an ACCEPTED ADR.** The seam ADR (accepted + signed off) states op/ARC own all model-driven synthesis; charter lists re-litigation as Out of Scope. | organizational | Medium | Alt C-as-op-consumer does not reopen the ADR; Alt B does. |
| **R7 — Data-locality premise quantitatively false.** The deterministic pre-filter + Guard 3 quota yield a tiny survivor set (~5/project/24h). Shipping a handful of already-redacted transcripts over LAN via the live `GET /api/v1/project/aar-review` endpoint is trivial. | technical | Medium (to the hypothesis) | The premise that justifies CCDash ownership does not survive the volume numbers. |

**Blast-radius summary**: op ownership leaves Invariant #1 exactly as shipped (untouched, trivially
audited, zero blast radius) and all three v1 self-recursion guards intact and correct. A
CCDash-hosted (Alt B) lane forces a schema/write-path change (Guard 2), a new correctness
obligation on a safety guard (Guard 1), and a net-new governance subsystem (Guards 3/cost) — and
converts the hardest AOS constraint into a fragile reachability check. Rejected on R1 alone.

---

## 6. Architectural Implications

The escalation ladder maps cleanly onto **already-shipped ownership** — no new pipeline is
warranted:

- **Step 1 (deterministic pre-filter): already CCDash's, already built (v1).** The 5-flag/3-verdict
  rollup, the `aar_review_candidate` events, and the redaction-passed read surface
  (`GET /api/v1/project/aar-review`, `/api/v1/sessions/{id}/detail`, `/transcript`, `/capabilities`)
  are all live and directly reusable.
- **Steps 3–4 (capable-model full-data review + draft recommendations, gated emission): REUSE ARC.**
  The priorart leg confirms ARC/council-review is structurally a *superset* of v2's ask
  (`scorecard.json.recommendation` + `findings.yaml.accepted[].recommendation` + `decision_record.md`,
  all schema-gated through op's approve/writeback gates) and is **already named as the v1 P3
  destination** ("`op council` invokes the ARC council pipeline"). Building a bespoke capable-model
  call would violate "reuse, don't rebuild" and create a second, parallel deep-review pipeline with
  a divergent schema/gate/audit trail.
- **Step 2 (cheap-model semantic pre-filter): the one piece nothing in the AOS owns today** — but
  op has *no* data-locality disadvantage for a per-candidate pass (it reads the same redaction-passed
  evidence over the existing API). It slots naturally as a narrow, named, gated op-side seam
  (matching the `op persona reconcile` precedent), consuming CCDash's existing `aar_review_candidate`
  events over the API. **This requires CCDash to build nothing new.**

Net architectural implication: CCDash's contribution to the ladder is complete at v1. The residual
capability is an op-side seam, not a CCDash layer change.

---

## 7. Verdict

**Verdict**: no-go (for the CCDash-side build)
**Confidence**: 0.8

**Rationale**: The charter's deal-killer `no_go` gate is triggered — the risk leg (0.82) confirms
op should own the semantic-triage tier and CCDash builds nothing new. Three converging findings
drive this: (1) the **data-locality premise is quantitatively false** (R7) — the survivor set is
tiny and the live PULL endpoint already provides redaction-passed transport at negligible cost;
(2) the **Invariant #1 blast radius is asymmetric and permanent** (R1, Critical) — op ownership
costs the invariant nothing, while a CCDash-hosted lane converts a structurally-trivial audit into
a fragile reachability check that any future refactor can silently defeat; (3) **op already owns
every model rung** — ARC is the capable rung (priorart, 0.82) and the only unowned piece (the cheap
pre-filter) is one for which op has no locality disadvantage. The value leg (0.55) independently
shows residual value is thin and narrowly scoped. Feasibility (tech, 0.82) is real but only in the
Alt C form, whose CCDash content is a deployment note, not a deliverable — so feasibility does not
rescue desirability. The go criteria (deal-killer refuted; data locality justifies a B/C lane) are
not met.

**Recommended next action**: `archive` this CCDash-side exploration. See §8-adjacent pointer below.

---

## 8. Recommended Next Action & Op-Side Pointer

**Archive** the CCDash-side exploration `ccdash-aar-review-semantic-triage-tier`. CCDash's
contribution to the AAR review loop is complete at v1; no v2 CCDash build is warranted.

**Op-side pointer (residual value — capture in op's backlog, NOT a CCDash build):** The one piece
nothing in the AOS owns today is a **narrow cheap-model semantic pre-filter** (a single bounded
question per candidate: "does the evidence support the AAR's claim, yes/no + confidence"), scoped
to the S1 + S5 signals over **structured evidence only** (never raw transcript), population-gated to
the `deep_review_recommended`/`human_triage_required` + `stack_ineffectiveness`-triggered subsets.
It should be built — **if at all** — as an **op-side feature**: a narrow, named, gated model-touching
seam in op's own adapter layer (matching the `op persona reconcile` precedent), consuming CCDash's
**existing** `aar_review_candidate` events over the already-live `GET /api/v1/project/aar-review`
PULL endpoint, and feeding **ARC/council-review as the capable rung** (already the v1 P3 destination).
This requires **zero new CCDash code**. Suggested capture: `op capture` this as an op backlog idea
referencing this brief and the design spec.

---

## 9. Citations

- Exploration charter: `docs/project_plans/exploration/ccdash-aar-review-semantic-triage-tier/ccdash-aar-review-semantic-triage-tier-charter.md`
- Tech leg SPIKE: `docs/project_plans/exploration/ccdash-aar-review-semantic-triage-tier/spikes/tech-findings.md`
- Risk leg SPIKE: `docs/project_plans/exploration/ccdash-aar-review-semantic-triage-tier/spikes/risk-findings.md`
- Value leg SPIKE: `docs/project_plans/exploration/ccdash-aar-review-semantic-triage-tier/spikes/value-findings.md`
- Prior-art leg SPIKE: `docs/project_plans/exploration/ccdash-aar-review-semantic-triage-tier/spikes/priorart-findings.md`
- Design spec: `docs/project_plans/design-specs/ccdash-aar-review-semantic-triage-tier.md`
- v1 PRD: `docs/project_plans/PRDs/features/ccdash-automated-aar-review-v1.md`
- v1 implementation plan: `docs/project_plans/implementation_plans/features/ccdash-automated-aar-review-v1.md`
- Accepted seam ADR: `docs/project_plans/exploration/ccdash-automated-aar-review/ccdash-automated-aar-review-proposed-adr.md`
