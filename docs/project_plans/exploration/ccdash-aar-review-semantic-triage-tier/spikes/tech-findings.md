---
schema_version: 2
doc_type: spike_findings
title: "Semantic-Triage Tier — Tech Feasibility Leg (OQ-B)"
feature_slug: ccdash-aar-review-semantic-triage-tier
leg: tech
open_question: OQ-B
created: 2026-07-23
status: complete
---

# Tech Feasibility Leg — Semantic-Triage Job Lane (OQ-B)

Scope: Is a seam-preserving semantic-triage job lane technically feasible with the model
lane **provably off** CCDash's read/recall/compute path? Compare **Alt B** (CCDash-hosted,
embedded in the worker) vs **Alt C** (CCDash-adjacent separate service reading CCDash over
the v1 HTTP API). Anchored on v1's deterministic worker lane (H5 = P6 of
`ccdash-automated-aar-review-v1`, 6–9 pts).

---

## Feasibility Verdict

**feasible-with-constraints.**

Both alternatives are technically buildable, but they are **not equivalent on the load-bearing
criterion** ("model lane PROVABLY off the read/recall/compute path"):

- **Alt C is provably off-path by construction** and is the only option that yields a
  *process + deployment + network* separation guarantee. It reuses already-shipped,
  redaction-passed v1 endpoints and requires ~0 new CCDash code.
- **Alt B is feasible but structurally weaker on the proof**: it can only offer
  *runtime-profile + import-audit* separation, not process separation, because the `local`
  runtime profile runs the API and background jobs in **one process** and the model-client
  library would then sit in CCDash's own venv. Achieving Alt B requires **relaxing the very
  invariant test** (`test_aar_review_no_llm_imports.py`) that today makes Hard Invariant #1
  machine-checkable — that is a regression of the proof, not a way to satisfy it.

Net: a seam-preserving lane is feasible; the constraint is that only Alt C preserves the
*strongest* form of the "provably off-path" guarantee.

---

## Alt B vs Alt C

### Runtime facts that decide this (verified in code)

- Runtime profiles: `local | api | worker | worker-watch | test`
  (`backend/runtime/profiles.py`). The v1 sweep is constructed **only** for
  `_export_profiles = {"worker","worker-watch"}` and only when its flag is on
  (`backend/runtime/container.py:195-217`), with a defense-in-depth re-check inside the job.
- **`local` profile watches + runs in-process jobs AND serves HTTP** (`profiles.py:29-39`).
  So under `local`, api + worker + jobs share one OS process — profile gating cannot buy
  process isolation there.
- Hard Invariant #1 is enforced today by `backend/tests/test_aar_review_no_llm_imports.py`:
  a static AST walk of the transitive `backend/` import closure from
  `aar_review.py`, `aar_review_sweep_job.py`, and `aar_review_writeback.py` that **bans**
  `anthropic|openai|litellm|langchain|google.generativeai|genai` imports and
  `spawn_agent|dispatch_agent|invoke_agent|run_subagent|TaskDispatch|...` symbols anywhere
  in that closure.
- v1 external read surface already exists and is redaction-passed:
  `/api/v1/project/aar-review` (with `bypass_cache`), `/api/v1/sessions/{id}/detail`,
  `/api/v1/sessions/{id}/transcript`, `/api/v1/capabilities`
  (`backend/routers/_client_v1_aar_review.py`, `_client_v1_sessions.py`). Verdicts
  `deep_review_recommended` / `human_triage_required` are the natural pre-filter handoff.

### Alt B — CCDash-hosted job lane (embedded in worker)

- **Separation mechanism**: runtime-profile gating (mirror `_export_profiles`) + module
  placement outside the audited import closure. New job in `backend/adapters/jobs/`,
  constructed only under `worker`/`worker-watch`.
- **Proof-of-off-path argument (and where it fails)**: The api/read path never *constructs*
  the semantic job, so at runtime the model call is not on a request path under `api`. BUT:
  1. Under the `local` profile the model client would be importable and reachable in the same
     process that serves reads — profile gating is a runtime guard, not a static guarantee.
  2. The model-client dependency lands in CCDash's own venv/package, so the current
     **repo-global import-audit test must be carved out** (the semantic module would import
     `anthropic`/etc.). Once the audit has an exception, the "CCDash physically cannot make a
     model call" proof is gone — it degrades to "CCDash promises not to on these paths,"
     enforced by code review, not by the compiler/test.
  - **Conclusion**: Alt B's proof is *conditional and erodable*, not structural.

### Alt C — CCDash-adjacent separate service (reads CCDash over v1 HTTP)

- **Separation mechanism**: process + deployment + network boundary. The model lane runs as
  a **distinct OS process / container**, in its own package/venv, and consumes CCDash **only**
  through the read-only v1 HTTP API. It is never imported into CCDash's Python package.
- **Proof-of-off-path argument (structural)**:
  1. CCDash's package keeps **zero** model-client dependency; the existing import-audit test
     stays **unchanged and green** — the strongest possible proof: the code physically cannot
     make a model call.
  2. CCDash never imports or depends on the adjacent service (dependency arrow points one way:
     adjacent → CCDash, read-only). Removing/killing the adjacent service cannot affect any
     op/ARC/FE query path.
  3. Redaction is inherited *for free* — the session-detail HTTP egress is already
     redaction-passed, so the model lane only ever sees scrubbed evidence without a re-proof.
  - **Conclusion**: Alt C's proof is structural and matches Hard Invariant #1's spirit
    exactly — CCDash stays a pure deterministic recall surface. It also **converges with the
    deal-killer resolution** (op/ARC owning the model lane), which is the risk/ownership leg's
    call, not tech's.

---

## Integration Points (files / layers)

### Alt B (CCDash-hosted)
- **New**: `backend/adapters/jobs/aar_semantic_triage_job.py` (mirrors `aar_review_sweep_job.py`).
- **Wire**: `backend/runtime/container.py` (~L195-217) — new gated construction + `_export_profiles`.
- **Config**: `backend/config.py` — new enable flag + model/cost/quota knobs.
- **Reads (deterministic pre-filter)**: `AARReviewQueryService.get_review` output +
  `agent_queries/session_detail.py` (redaction-passed evidence). New semantic module reads,
  then calls a model client (NEW dependency).
- **Emit path**: must route through existing op gates only (`aar_review_writeback.py` seam,
  currently dormant); never CCDash-initiated writeback (Hard Invariant #2).
- **Test debt (the constraint)**: `backend/tests/test_aar_review_no_llm_imports.py` must be
  carved out / re-scoped — a direct erosion of the machine-checked invariant.

### Alt C (CCDash-adjacent)
- **CCDash-side (near-zero new code)**: reuse `/api/v1/project/aar-review`,
  `/api/v1/sessions/{id}/detail`, `/api/v1/sessions/{id}/transcript`, `/api/v1/capabilities`
  (all shipped, redaction-passed). Optional small increments: a `?verdict=` filter +
  `?since=` watermark on the aar-review list, and pagination (v1 explicitly has **none** —
  `docs/guides/aar-review-loop.md`), if sweep-at-scale needs it.
- **Optional capability string** advertisement remains a CCDash concern only if we choose to
  signal availability; the model owner advertises nothing to CCDash.
- **Adjacent service (out of CCDash scope; op/ARC-owned)**: new repo/package/container that
  polls `deep_review_recommended`/`human_triage_required` candidates, pulls redaction-passed
  detail, runs the cheap→capable model ladder, and emits through op's own gates.

---

## Story-Point Estimate

**H5 anchor**: v1 P6 (autonomous worker + gated writeback + 3 guards) = **6–9 pts**;
v1 remaining total = 26–34 pts (`ccdash-automated-aar-review-v1.md`).

| Alt | CCDash-side build | Delta vs H5 anchor | Off-CCDash build |
|-----|-------------------|--------------------|------------------|
| **B** | **13–21 pts** | H5 job scaffold (6–9) **+** model-client integration **+** cost/quota fold-in with the 3 existing guards **+** re-scoping the no-LLM import audit (architecturally expensive; re-litigates the invariant) **+** redaction re-proof for the semantic pass | — (all in-repo) |
| **C** | **2–5 pts** | Far *below* H5: endpoints + redaction + capability discovery already shipped; only optional `verdict`/`since` filter + pagination hardening + contract/docs | Adjacent worker (cheap→capable ladder) is a **separate, op-owned** estimate NOT on CCDash's ledger |

**Delta justification**: Alt B is *above* the anchor because it inherits the full P6 worker
cost and then adds the model lane, cost governance, and — critically — the cost of weakening a
CI-enforced invariant (unquantifiable review/regression risk, not just LOC). Alt C is *below*
the anchor on the CCDash side because the read/evidence surface P6 needed is already built;
the expensive part (the model lane) moves off CCDash's books entirely, which is precisely the
deal-killer convergence.

---

## Open Architectural Questions

- **OQ-B1 (Alt B, blocking)**: Under the `local` profile, api + jobs share one process; profile
  gating cannot isolate the model lane there. Is `local` an out-of-scope deployment for the
  semantic tier, and even so, is a venv-resident model client acceptable given it forces
  relaxing `test_aar_review_no_llm_imports.py`? (Leans strongly toward Alt C.)
- **OQ-B2 (Alt C)**: The v1 `/api/v1/project/aar-review` list has **no pagination**. Does the
  adjacent sweep need pagination + a `?since=` watermark + `?verdict=` filter, and is that a
  small in-scope CCDash increment (2–5 pts) or deferrable?
- **OQ-B3 (Alt C)**: Are `deep_review_recommended` / `human_triage_required` verdicts a
  *sufficient* candidate queue for the semantic pass, or does the adjacent service also need
  `surface_only` rows (to catch claimed-outcome-vs-transcript mismatches the deterministic
  flags cannot see)? If it needs all rows, the read-volume cost rises. (Overlaps value leg / OQ-D.)
- **OQ-B4 (Alt B)**: Alt B must re-prove "consumes only redaction-passed `session_detail`" at
  each new call site; Alt C inherits redaction from HTTP egress with zero re-proof. Is the
  recurring re-proof burden acceptable?
- **OQ-B5 (ownership handoff to risk leg / OQ-A)**: If Alt C, the adjacent worker is naturally
  op/ARC-owned — is CCDash's tech-leg output simply "expose, don't build"? This is the
  deal-killer convergence; tech defers the ruling to the risk leg.
- **OQ-B6 (cost/quota, OQ-C)**: Alt B would fold model-cost quota into CCDash's existing
  escalation-quota Guard 3; Alt C keeps cost governance entirely in op's domain. Which is the
  intended home for the token/cost budget?

---

## Confidence

**0.82** — High confidence Alt C is feasible with true process/deployment separation and
near-zero CCDash build (all required v1 endpoints, redaction egress, and capability discovery
are shipped and directly reusable); the residual uncertainty is minor endpoint gaps
(pagination/filters) and the ownership ruling, which is the risk leg's call, not tech's.
