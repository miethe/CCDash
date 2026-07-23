---
schema_version: 2
doc_type: spike_findings
title: "AAR Semantic-Triage Tier — Risk / Blast-Radius + Deal-Killer Ruling (OQ-A, OQ-C)"
leg: risk
feature_slug: ccdash-aar-review-semantic-triage-tier
created: 2026-07-23
assigned_to: ica-executor
deal_killer_ruling: confirm
confidence: 0.82
---

# Risk Leg — Semantic-Triage Tier (OQ-A ownership, OQ-C cost/quota/guards)

Grounded in runtime truth: the shipped v1 loop
(`backend/adapters/jobs/aar_review_sweep_job.py`, `aar_review_sweep_guards.py`,
`application/services/agent_queries/aar_review_writeback.py`,
`test_aar_review_no_llm_imports.py`, `test_aar_review_writeback_gate.py`) and the
**accepted** seam ADR (`ccdash-automated-aar-review-proposed-adr.md`, status:
accepted 2026-07-21 + human sign-off).

Key v1 facts that drive every risk below:
- **Invariant #1 is enforced by a static import-graph BFS audit**
  (`test_aar_review_no_llm_imports.py`): it walks every `backend.*` module
  transitively reachable from the AAR entry points and fails if ANY resolves a
  banned LLM-client import or an agent-dispatch symbol — checked against raw
  source, not just import names. The invariant is only as strong as "no LLM
  client exists anywhere in the reachable `backend` import graph."
- **The sweep worker never touches the writeback/escalation path.**
  `AARReviewSweepJob` computes `(correlation, flags, verdict)` deterministically,
  `upsert`s to `aar_reviews`, and emits the log-only `log_aar_review_candidate`
  event. It does **not** import `aar_review_writeback.py` and has no concept of
  `op approve`. Guard 3 (quota) lives exclusively on the writeback seam, which is
  reachable ONLY when an external caller supplies an `ApprovedRunReference`
  (i.e. downstream of a real `op approve`). There is no autonomous constructor
  of that reference anywhere in the codebase.
- **Phase 5 D5 already settled transport = PULL.** op consumes
  `GET /api/v1/project/aar-review` at its own plan gate; the redaction-passed
  evidence op would need for a semantic pass is *already exposed today* with
  zero new CCDash code.

---

## Risk Register

| Risk | Severity | Likelihood | Mitigation |
|---|---|---|---|
| **R1 — Import-audit erosion (Invariant #1 blast radius).** Introducing a real LLM client anywhere in the `backend` package makes the `test_aar_review_no_llm_imports.py` BFS audit fragile: one shared helper module bridging the deterministic path and the model lane silently re-connects the graph and defeats the audit. The invariant flips from "no LLM import exists" (structurally trivial) to "no LLM import is *reachable*" (a live refactor hazard forever). | **Critical** | High (any future shared-util refactor) | Only Alt C (fully separate process/repo, no shared `backend` import surface) preserves the trivial-audit property; Alt B (in-process job lane) cannot. Best mitigation = don't put a model in `backend` at all. |
| **R2 — Guard 1 (provenance) defeat by mistagged model output.** Guard 1 keys ONLY on `skill_name == "aar-review"` / `workflow_id` prefix `aar-review-` (column check, never content-sniff, by design). A CCDash-hosted semantic tier producing model-authored review artifacts/sessions must tag every output with the reserved markers or those outputs re-enter triage → unbounded self-reference loop. A single mistag silently defeats the guard. | High | Medium | If op owns synthesis, model outputs are op-side downstream artifacts op is responsible for tagging; CCDash's fail-closed column guard stays correct. A CCDash-hosted lane owns a new correctness obligation on a shipped safety guard. |
| **R3 — Guard 2 (dedup PK) collision between deterministic + semantic verdicts.** Dedup ledger IS the `(aar_document_id, session_id)` composite PK of `aar_reviews`. A semantic verdict on the SAME pair would either be deduped against the deterministic row (lost) or overwrite it. Supporting both requires a new PK dimension `(aar_document_id, session_id, tier)` → schema migration on a shipped table (dual SQLite+PG DDL, ADR-007, `COLUMN_PARITY_DRIFT_ALLOWLIST`). | High | High (any CCDash-side semantic verdict) | op-owned tier persists its own verdicts in op's store; CCDash's `aar_reviews` schema stays untouched. CCDash-side lane forces a migration + write-path on a live table. |
| **R4 — Cost/quota governance CCDash does not own.** CCDash has NO model-cost budgeting, token accounting, or model-routing infrastructure. Guard 3's quota is a per-project *escalation-count* gate on the op-gated writeback seam — it is NOT a *token/dollar* budget and does not sit on any autonomous compute path. A CCDash-hosted model lane would need net-new cost governance duplicating op's `MODEL-ROUTING.md` + budget machinery. | High | High | op already owns model routing, effort tiers, and budget. Ownership by op reuses existing governance; CCDash-side rebuilds it. |
| **R5 — New secret/egress surface in CCDash's blast radius.** An in-process (Alt B) model lane adds an API-key secret + outbound model-provider egress to a local-first, LAN-only dashboard that today has none on its read path. Widens attack/leak surface; interacts with redaction (must guarantee only redaction-passed evidence ever reaches the provider). | Medium | Medium | Redaction layer already gates `session_detail` egress; but a model call is a new exfiltration path. Alt C isolates it to a separate process; op ownership keeps it entirely outside CCDash. |
| **R6 — Re-litigating an ACCEPTED ADR.** The seam ADR (accepted + signed off) states op/ARC own ALL model-driven synthesis; the charter explicitly lists "re-litigating v1's deterministic seam ADR" as Out of Scope. Any CCDash-hosted/adjacent model lane reopens Decision §2 ("model-free on the CCDash side"). | Medium | High if B/C chosen | Alt C framed as an *op-operated consumer deployed near CCDash* does not reopen the ADR (it's op's process, not CCDash's). Alt B does reopen it. |
| **R7 — Data-locality premise is quantitatively false.** The "shipping all evidence to op per candidate is wasteful" case assumes high volume. Reality: the deterministic pre-filter + Guard 3 quota (default 5/project/24h) yield a *tiny* survivor set. Shipping ~5 already-redacted transcripts/day over LAN via the existing PULL endpoint is trivial. | Medium (to the hypothesis) | — | The premise that justifies CCDash ownership does not survive the numbers. See ruling. |

---

## Hard-Invariant Blast Radius

**Invariant #1 (no LLM on recall/compute path)** is the load-bearing constraint,
and its enforcement mechanism is the decisive factor. Today the invariant is
*structurally trivial*: no LLM client exists anywhere in `backend`, so the BFS
import audit passes by construction and can never regress without a very loud,
obvious new dependency. This is the strongest possible form of the invariant.

- **Alt B (CCDash-hosted job lane)** demotes the invariant from "structurally
  trivial" to "reachability-fragile." Once a legitimate LLM client lives in
  `backend`, the audit must prove the *deterministic* entry points never
  transitively reach it. Every future shared-util extraction, DI wiring change,
  or `ports` refactor becomes a potential silent invariant breach. This is a
  **Critical**, permanent erosion vector (R1) — the invariant stops being a
  property of the codebase's *shape* and becomes a property of a test's *graph
  walk* that a single import can defeat. **Rejected on this basis alone.**
- **Alt C (separate process/repo reading CCDash over the API)** keeps the LLM
  client out of `backend` entirely, preserving the trivial-audit property. The
  model lane sits behind the existing v1 PULL boundary (redaction-passed
  evidence only). This is viable *for the invariant* — but see the ruling: a
  process with no CCDash-specific code is not a CCDash deliverable.
- **Alt A / op ownership** leaves Invariant #1 exactly as shipped: untouched,
  trivially audited, zero blast radius.

Redaction (Invariant #3) is a secondary blast surface: any model call must
consume `session_detail` output, never raw JSONL. This holds for both Alt C and
op ownership (both read the redaction-passed PULL surface); Alt B would need to
re-prove it inside a new in-process call path.

---

## Cost/Quota Governance + Self-Recursion Guard Interaction

**Governance gap.** CCDash owns *no* token/dollar budgeting. v1's quota (Guard 3)
is a **count-based escalation gate on the op-approve-gated writeback seam**, not a
compute-cost budget, and it does not sit on any autonomous path (the sweep worker
cannot reach it). A CCDash-hosted semantic tier would run models on an *autonomous
cadence* — precisely the path v1 keeps model-free — and would therefore need
net-new cost governance that duplicates op's existing `MODEL-ROUTING.md`, effort
tiers, and budget controls. This is R4 (High): building cost governance is a
non-trivial subsystem, and op already has it.

**Guard-by-guard interaction (all three v1 guards are impacted by a CCDash-side tier):**

1. **Guard 1 — provenance self-exclusion.** Column-only check on
   `skill_name`/`workflow_id`, fail-closed, *never* content-sniffs. A CCDash-hosted
   model lane producing review artifacts must tag every output with the reserved
   markers or trigger an unbounded self-reference loop (R2). Ownership by op moves
   this obligation downstream where op already owns provenance tagging.
2. **Guard 2 — dedup ledger.** The ledger IS the `(aar_document_id, session_id)`
   composite PK. Adding a *second* (semantic) verdict class on the same pair
   collides with the deterministic verdict — either lost to dedup or overwriting
   it. Correct support demands a `tier` PK dimension → migration on a shipped
   table under ADR-007 + dual DDL parity (R3, High). op-owned verdicts live in
   op's store; CCDash's schema is untouched.
3. **Guard 3 — escalation quota.** Lives on the writeback seam, gated by
   `ApprovedRunReference` (op approve). It is *count*-based and *per-project*, not
   token-aware. A semantic tier that auto-escalates cannot reuse it (it's on the
   wrong path and measures the wrong thing) and would need its own token budget —
   which CCDash lacks (R4).

**Net:** all three guards were designed for a deterministic producer. A CCDash-side
model tier forces either a schema/write-path change (Guard 2), a new correctness
obligation on a safety guard (Guard 1), or a net-new governance subsystem
(Guards 3/cost). op ownership leaves all three intact and correct.

---

## DEAL-KILLER RULING

**CONFIRM the deal-killer. op should own the semantic-triage tier. CCDash builds
nothing new (verdict tilts Alt A / status quo, with a note that any locality
benefit is captured by Alt C-as-an-op-consumer, not by CCDash).**

**Reasoning:**

1. **The data-locality premise — the sole argument for CCDash ownership — is
   quantitatively false (R7).** The deterministic pre-filter is already the cheap
   rung, and the survivor set that would warrant a model pass is tiny (Guard 3's
   default is 5 escalations/project/24h; deterministic-flag survivors are a small
   fraction of AARs). "Shipping all evidence to op per candidate is wasteful"
   assumes bulk transport; the reality is a handful of *already-redaction-passed*
   transcripts pulled over LAN through an endpoint that **exists and is
   live-verified today** (`GET /api/v1/project/aar-review`, Phase 4/5). The
   transport cost is negligible; the locality argument does not survive contact
   with the volume numbers.

2. **The blast radius on Invariant #1 is asymmetric and permanent (R1, Critical).**
   op ownership costs the invariant *nothing* — it stays structurally trivial to
   audit. A CCDash-hosted (Alt B) lane converts the hardest AOS constraint from a
   property of the code's shape into a fragile reachability check that any future
   refactor can silently defeat. You do not take on a permanent Critical erosion
   vector to save a negligible transport cost.

3. **op already owns every rung of the proposed ladder.** The v2 escalation ladder
   (deterministic pre-filter → cheap-model semantic pass → capable-model review)
   maps cleanly onto shipped ownership: **CCDash's deterministic rung is already
   built (v1)**; op owns the cheap-model pass; ARC/op-council owns the
   capable-model rung (the priorart leg's OQ-E almost certainly confirms this).
   Only the CCDash rung is CCDash's, and it exists. There is no new *CCDash* rung
   to build — the two model rungs already have an owner with the governance
   (`MODEL-ROUTING.md`, budget, ARC gates) to run them.

4. **The accepted ADR already answers this (R6).** Decision §2 ("model-free on the
   CCDash side"; "if establishing a flag requires semantic judgment... it belongs
   to the synthesis tier upstream") is *exactly* this case. The v2 spec's lost
   signals (claimed-outcome-vs-transcript mismatch, subtly-wrong-but-successful
   choice, evidence-only recommendation) are the ADR's own "not a triage flag"
   examples. The ADR already routed them upstream. v2 re-asks a settled question.

**On Alt B vs Alt C (since ruling is confirm, not a clean refute):** If any
locality benefit is ever pursued, it is **Alt C only** — and even Alt C is
correctly framed as *an op-owned consumer that happens to be deployed on the LAN
node near CCDash*, reading the existing PULL endpoint. Alt C contains **zero
CCDash-specific code**: it is op's semantic tier with a deployment-locality note,
not a CCDash deliverable. **Alt B is rejected outright** (R1 Critical import-audit
erosion + R3 schema blast + R4 governance gap). So: CCDash-side build = no; if the
locality note matters at all, it lands as an op consumer co-located on the node
(Alt C-as-op), requiring nothing from CCDash beyond what Phase 4/5 already shipped.

**Bottom line:** v2 collapses into an op-side feature. CCDash's contribution is
complete at v1. Recommend **no-go** on any CCDash-side semantic-triage build.

---

## Confidence

**0.82** — The risk picture is complete on the two decisive axes (Invariant #1
blast radius and the three-guard interaction are grounded directly in the shipped
code, not inferred), and the deal-killer ruling is robust because it rests on a
*quantitative* refutation of the locality premise plus an *asymmetric* invariant
cost. The <1.0 residual: OQ-E (does ARC already provide the capable-model rung) is
owned by the priorart leg and only assumed here, and I have not independently
enumerated op's cost-governance internals beyond `MODEL-ROUTING.md` — a surprising
gap there is the only realistic path to reopening the ruling.
