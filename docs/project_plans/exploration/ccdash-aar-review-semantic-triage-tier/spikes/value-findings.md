# Value / Desirability Findings (OQ-D) — CCDash AAR Review Semantic-Triage Tier

**Leg**: value | **Question**: Which semantic signals are actually worth a model pass (value vs.
token cost)? | **Method**: static analysis of v1's deterministic flag implementations
(`backend/application/services/agent_queries/aar_review.py`, `aar_review_enrichment.py`), the
evidence surfaces already assembled for a review candidate (`session_detail.py`,
`redaction.py`), and the PRD/guide's stated scope boundary. No live AAR corpus exists in this
repo to sample empirically (`find . -iname '*aar*.md'` returns only the operator guide itself) —
all fire-frequency estimates below are reasoned bounds from known agentic-coding failure modes,
not measured rates. This is flagged explicitly in Confidence.

---

## Candidate Semantic Signals

| Signal | Est. fire-frequency | Value-if-caught | Rough token cost (per candidate) | Worth it? |
|---|---|---|---|---|
| **S1 — Outcome-narrative mismatch (lightweight)**: AAR claims success/completion but the session's own structured signals (tool-call exit status pattern, retry count, `stack_ineffectiveness`/`context_ballooning` evidence already computed) contradict it, using only metadata already bundled by `gather_session_metadata` — no raw transcript read. | Low-medium (~5–15% of AARs; self-report positivity bias in agent-written AARs is a known pattern, but most severe mismatches already correlate with an existing deterministic flag firing) | High when caught — a false "surface_only" is the single worst outcome the whole pipeline can produce (op reads it and stops looking) | Low: AAR text (~1.5–3K tok) + existing flag evidence/rationale strings (~0.3–0.6K tok) + structured session metadata (~0.3–0.8K tok) ≈ **2–4.5K tok/candidate** | **Y** (conditionally — see Recommended Subset) |
| **S2 — Outcome-narrative mismatch (deep)**: same question as S1, but requires reading the actual transcript (tool calls + results, not just aggregate counters) to catch a subtler mismatch — e.g. AAR says "tests pass" but the transcript shows the agent never re-ran the test suite after the last edit. | Low (~3–8%); the residual after S1's cheap metadata check already catches the loud cases | Highest per-hit value (this is the signal deterministic rules structurally cannot approximate at all) | High and unbounded: full/partial transcript for N correlated sessions. Even a truncated "tool-call digest" (name+outcome per call, no payload) runs ~2–8K tok for a typical session and **scales with session count per AAR** (multi-hop correlations can span 2–5+ sessions) → **5–40K+ tok/candidate**, worst case much higher for long agentic sessions | **N** at pre-filter tier; plausible only at the capable-model escalation rung where cost is already budgeted per-candidate under quota |
| **S3 — Subtly-wrong specialist choice (beyond extension-lookup)**: the agent/skill used was plausible and "succeeded," but a domain expert would judge it as the wrong tool for the *actual* problem shape (not just file-extension mismatch, which `evaluate_generic_agent_vs_specialist` already catches deterministically). | Low (~3–7%); the static extension→specialist lookup is coarse but catches the majority of gross mismatches, leaving a narrow "technically-fine-but-suboptimal" residual | Medium — informs `new_skill_or_agent_need` aggregation and SkillMeat ranking feedback, but is a slow-burn improvement signal, not an urgent correction | Medium: AAR text + flag evidence + `subagents`/skill metadata already gathered (~2–3K tok), no transcript needed for a coarse judgment; deeper judgment converges toward S2's cost | **Marginal** — value is real but diffuse/aggregate, not per-candidate-urgent; better served by aggregating many cheap-pass verdicts over time than as a per-AAR gate |
| **S4 — Evidence-only recommendation surfacing**: a recommendation (e.g. "this stack needs a linter step," "this task should have been split") that is visible only from synthesizing the full evidence bundle, not from any single deterministic flag. | Medium (plausibly fires on a sizeable minority of AARs — recommendations are cheap for a model to generate on any input) but **low signal-to-noise**: "a model can always find *a* recommendation" is not the same as "a recommendation worth acting on" | Low-medium per instance, high variance; without a second gate this is mostly noise that competes for the same escalation quota as high-confidence flags | Medium: same bundle as S1 (~2–4.5K tok) if scoped to structured evidence; balloons to S2's cost if the model is allowed to read the transcript for "insight" | **N** — this is exactly the generative, open-ended task a *capable* model does well post-escalation; running it as a cheap pre-filter just manufactures low-value candidates that eat the escalation quota (5/24h default) that should be reserved for the 3 flag-shaped signals above |
| **S5 — Root-cause-vs-symptom mismatch**: `stack_ineffectiveness` already flags failure/retry patterns for a resolved stack, but doesn't judge whether the *eventual* fix addressed the root cause or just silenced the symptom (e.g., added a retry loop instead of fixing the underlying race). | Low (~2–5%, and only reachable when `stack_ineffectiveness` has already triggered — a narrow, already-filtered subset) | Medium-high when caught, but the volume is inherently small (gated behind an already-triggered high-severity flag) | Low: this signal only needs to run on the subset that already triggered `stack_ineffectiveness` (small N) using the flag's existing evidence + AAR text (~2–3K tok) | **Y** (conditionally) — best economics of the set: smallest applicable population (piggybacks on an existing high-severity trigger), so the marginal token spend is bounded even though per-hit cost isn't |

---

## What v1 Deterministic Flags Already Cover (so we don't double-count)

All five flags are **mechanical set/threshold/lookup operations over already-ingested rows** —
none of them ever performs semantic judgment, and each is explicitly documented as "byte-for-byte"
stable across phases (no flag has ever changed its trigger/severity logic when new evidence
inputs were added):

| Flag | Mechanism | What it CANNOT see |
|---|---|---|
| `missing_artifacts` | Set-difference: AAR frontmatter `files_affected` vs. session-produced file paths (+ linked task's declared files) | Whether the files that *were* produced actually implement the claim — only checks existence, not correctness or completeness of change |
| `context_ballooning` | Threshold check on `context_utilization_pct` vs. a configured percentage | Whether the ballooning correlates with anything the AAR claims or omits |
| `generic_agent_vs_specialist` | Static `_EXTENSION_STACK_LOOKUP` keyed on dominant file extension vs. a fixed generic-agent-name list | Any judgment finer than "extension X usually implies specialist Y" — cannot detect a *specialist* agent applied with the wrong methodology, or a generic agent that happened to do fine work |
| `stack_ineffectiveness` | Correlates a resolved stack against pre-existing `failure_items` (retry/failure-pattern records) by session-id membership | Whether the eventual outcome (pass/fail) matches the AAR's claim, and whether the fix was a root-cause fix or a symptom patch (S5) |
| `new_skill_or_agent_need` | Rolling-window count of `generic_agent_vs_specialist` + `missing_artifacts` triggers vs. a threshold | Anything beyond aggregate frequency of the two upstream mechanical flags — pure counting, zero new judgment |

**Conclusion**: every deterministic flag answers "does X match Y by lookup/threshold," never "is
this claim/choice actually *right*." The three problem-statement signals (a/b/c) — and the
S1–S5 decomposition above — are each, by construction, outside what v1 can ever catch; there is
no overlap to worry about double-counting. The risk is not double-counting the deterministic
layer, it's **conflating "not caught by v1" with "worth a model pass"** — which is exactly what
this leg is testing.

---

## Recommended Signal Subset

**Conditional subset, not an unconditional yes**: **S1 + S5**, and only if both preconditions hold:

1. **Scope the pre-filter to structured evidence, never raw transcript.** S1 and S5 are the only
   two signals in the set whose value/cost ratio survives when the semantic pass is bounded to
   the AAR text + the deterministic flags' own evidence/rationale strings + `gather_session_metadata`'s
   already-materialized fields (~2–4.5K tokens/candidate — the same evidence tier v1 P2 already
   assembles for the flags themselves, so no new evidence-gathering machinery is needed). The
   moment the pass needs to read a transcript (S2, and S4 if done "properly"), token cost scales
   with session count and un-truncated tool-call volume — that is a capable-model-escalation-tier
   cost, not a cheap-pre-filter cost.
2. **Gate the pass on population, not on universality.** S1 only pencils out if it runs on the
   `deep_review_recommended` / `human_triage_required` population (already small, already headed
   for a human/op look) plus a *sampled* slice of `surface_only` to hunt false negatives — not on
   100% of `surface_only` candidates. S5 already inherits this for free (it only fires on the
   `stack_ineffectiveness`-triggered subset). Running S1 unconditionally over every `surface_only`
   AAR to catch the "false negative" case is the single most expensive posture in this table and
   is explicitly NOT recommended — see Counterfactual below for why the marginal value there is
   thin.

**S2, S3, S4 do not clear the bar as pre-filter signals.** S2's real value is genuine but belongs
at the capable-model escalation rung (where a bigger per-candidate budget is already the design),
not the cheap pre-filter. S3's value is real but diffuse/aggregate — better captured by improving
the existing `new_skill_or_agent_need` rolling-window aggregation than by a per-AAR model call. S4
is the clearest **non-winner**: an open-ended "find a recommendation" pass on bounded evidence
will always produce *something*, and that something will compete for the same escalation quota
(`CCDASH_AAR_ESCALATION_QUOTA=5`/24h default) that should be reserved for the flag-shaped signals
above — it is a noise generator dressed as a feature unless it is explicitly deferred to the
capable-model rung where a human/ARC gate can discard low-value output before it costs quota.

**If forced to name exactly one signal for a v2 MVP**: **S1**, scoped to the `deep_review_recommended`
/ `human_triage_required` population only (never the full `surface_only` volume). It has the best
value/cost ratio of the set, needs zero new evidence-gathering machinery, and directly attacks the
problem statement's example (a) without requiring transcript reads.

---

## Counterfactual: what op does today without this

Per the PRD/guide, `human_triage_required` and `deep_review_recommended` verdicts already route to
a human or to op's own downstream pipeline ("escalate immediately," "queue for manual review or
light-touch automation" — `docs/guides/aar-review-loop.md` § Read Endpoint). Separately, per the
injected global operator context, **every AAR is already supposed to flow through `op story
capture`/`scan`** into a gated Signal→System pipeline that does its own model-driven reconciliation
before a draft PR — i.e. op already has a downstream point where a model reads the AAR narrative.

This matters for the value case in two ways:

- For the **already-flagged** population (`deep_review_recommended`/`human_triage_required`), a
  CCDash-side semantic pre-filter is not adding a capability that's otherwise *absent* — it's
  adding *earlier/cheaper triage* ahead of a review that (per design) already happens somewhere
  downstream. The value here is ranking/prioritization and reduced human/op cycles-per-candidate,
  not "catching what would otherwise never be caught."
- For the **`surface_only`** population (the majority of AARs, by construction — v1's flags are
  tuned so the common case clears cleanly), the counterfactual today is genuinely "nobody looks
  unless op happens to" — this is the one bucket where S1/S5-style false-negative catching has
  unique, non-duplicated value. But it is also the highest-volume, and thus highest-aggregate-cost,
  bucket to run a model pass over — which is exactly why the Recommended Subset above gates S1 to
  a *sampled* slice of `surface_only`, not the full population.

**Bottom line**: the marginal, non-duplicated value of this tier is concentrated in a narrow slice
(false-negative catching on `surface_only`, plus root-cause depth on the already-small
`stack_ineffectiveness`-triggered subset) — not in the broad "run a model over every AAR" framing
implied by the design spec's problem statement.

---

## Confidence

**0.55** — moderate-low. This leg's estimates are architecturally grounded (the deterministic
flags' exact mechanisms and the evidence-bundle shapes are read directly from source, not
guessed), but every fire-frequency number is a reasoned bound, not a measured rate: no AAR corpus
exists in-repo to sample (`find . -iname '*aar*.md'` returns zero real AAR documents), and no
telemetry on `triage_verdict` distribution across real projects was available to this leg. The
ranking/subset conclusion (S1+S5 conditional yes; S2/S3/S4 no) is robust to reasonable variation in
the exact frequency numbers because it rests on a structural argument (bounded-evidence cost vs.
transcript-read cost, and population-gating vs. universal-gating) rather than on the point
estimates themselves — that structural argument is the part I'd defend at 0.8+ confidence. The
frequency table entries specifically should be treated as priors to be replaced by real
`aar_reviews` distribution data (`triage_verdict` counts by project) before any implementation
commitment, not as measured facts.
