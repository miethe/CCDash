---
leg: risk
confidence: 0.72
deal_killer_assessment: partially-triggered
---

# Risk / Blast-Radius Spike — Proof → Routing Feedback Loop

## 1. Deal-killer assessment (one line)

**Partially triggered**: the charter deal-killer as literally worded ("cannot derive a
router-joinable `task_class` from already-captured fields") is a derivability question
that belongs to the `tech` leg, not this leg — but this leg finds a closely-related,
**silent** failure mode is high-likelihood absent a negotiated vocabulary: CCDash can
derive *a* `task_class` string (e.g. from `skillName`), yet nothing on this repo's side
can confirm that string equals or maps onto the delegation-router's own taxonomy. If it
doesn't join, the rollup emits real HTTP 200s with real `sample_count`s — not an error,
not an empty response — that never intersect the router's scorecard keys. That is
functionally equivalent to the deal-killer's "no actionable signal" outcome, but it fails
**quietly**, which is worse than an explicit build-time refusal. See §3.

## 2. Risk register

| Risk | Severity | Likelihood | Mitigation |
|---|---|---|---|
| `task_class` vocabulary mismatch with router taxonomy → silent non-join (rollup ships but never intersects router keys) | critical | high (unmitigated); low (if negotiated first) | Cross-repo contract negotiation *before* the router treats the rollup as authoritative (see §3); CCDash ships `task_class` as an explicit, versioned, documented field (like the AAR contract's enum fields) so a mismatch is at least detectable by a human diffing vocabularies, not undetectable |
| Guardrail bullets in design-spec §5 are split across two repos — CCDash can enforce threshold/decay/suppression on the data it emits, but "bounded adjustment" (floor) and "reversible via flag" are the *router's* implementation, unverifiable from here | high | medium | CCDash-side mitigation: never emit an adjustment-worthy signal for sub-threshold keys at all (mirror AAR's "verdict, not raw flags" pattern — see §3); document in the seam contract, as v1 AAR contract does in §5, exactly which guarantees are CCDash's (verifiable) vs. the router's (asserted, not verifiable) |
| Cross-repo invisibility — no integration test possible from CCDash repo; the router's actual consumption code is never seen here | medium | certain (structural, not avoidable) | Same mitigation the AAR contract already uses successfully: a locked, versioned, example-rich written contract (`ccdash-aar-review-consumer-contract-v1.md` pattern) is the only channel; ship a v1 routing-rollup consumer contract doc with the same rigor before declaring "closed loop" |
| Attribution granularity (OQ6) — multi-session feature outcomes mis-attributed across per-session tuples | medium | medium | Scope v1 to strictly per-session signals only (cost_index, per-session regression/error flags); explicitly exclude cross-session feature-outcome attribution from `regression_rate` in v1, revisit as v2 (spec itself flags this as unresolved, OQ6) |
| Cold-start starvation (OQ4) — new/rare routes never accumulate samples, get permanently under-explored | low-medium | medium | Explicitly named in spec as router-owned (exploration allowance is the router's job, not CCDash's); CCDash's only obligation is to not hide sub-threshold keys entirely if the router wants to see raw counts — needs pinning in the seam contract |
| Interaction with manual scorecard (OQ5) undefined — overlay vs. blend | medium | medium (router-side ambiguity, but affects what CCDash must guarantee about field semantics) | Out of CCDash's control per spec §3c ("out of scope here"); risk is that CCDash ships a field contract before this is pinned and has to break it later — sequence negotiation before first-field-freeze |
| Config-flag / capability-gate drift risk (same pattern as existing flags) | low | low | Follows proven pattern (`CCDASH_ROUTING_ROLLUP_ENABLED`, default false; `/api/v1/capabilities` negotiation) — see §6, no new risk surface vs. precedent |
| No CI-enforced no-LLM-import test exists yet for the *new* module (it doesn't exist yet) | low | low (easily closed) | Port `test_aar_review_no_llm_imports.py`'s AST-walk pattern to the new rollup module at build time — trivial, precedent exists |

## 3. Cross-repo seam analysis — is a spec-only contract sufficient?

**No, not for the `task_class` field specifically — the charter's own "conditional" branch
is the correct verdict shape, and this leg confirms why.**

The AAR-review consumer contract (`docs/project_plans/design-specs/ccdash-aar-review-consumer-contract-v1.md`)
is the precedent being cloned, and it *is* sufficient for its own seam — but the reason it
works doesn't transfer cleanly to `task_class`:

- In the AAR contract, the two routing-decision fields (`correlation.confidence`,
  `triage_verdict`) are **CCDash-owned enums**. CCDash defines both the values and their
  meaning; the consumer never needs its own competing taxonomy for these fields — it just
  maps CCDash's 3 verdict strings onto its own routing logic (§4.1 decision table). A
  spec-only contract works because there is nothing to *join*, only something to *consume*.
- `task_class` is structurally different: it is a **join key**. Its entire value depends on
  matching an external, independently-evolving vocabulary that already exists in the
  delegation-router / `model-registry.yaml` `scores:` keys (MeatySkills repo, `ibm-main`,
  not visible from this repo — confirmed absent from this codebase by search). A spec can
  describe the *field's shape* (string, non-null, stable) but cannot describe its
  *correct values* without seeing the other side's taxonomy. This is exactly what design
  spec OQ1 calls "the crux of the seam and unresolved."
- **Failure mode if CCDash ships anyway**: the rollup computes and serves cleanly (no
  error — this is why it's dangerous). `sample_count`, `success_rate`, `cost_index` are all
  real, well-formed numbers. The router polls it, tries to join on `task_class`, and either
  (a) finds zero overlapping keys → the loop is built, deployed, and demoed as "closed" while
  being **completely inert** (the exact deal-killer condition, just discovered post-hoc
  instead of pre-build), or (b) finds partial/coincidental overlap on a few common strings
  (e.g. `"refactor"`) → **worse than inert**: it applies real downweights based on an
  accidental, un-vetted mapping, which can silently mis-route.
- **Recommendation**: CCDash *can* safely build the emission machinery (schema, worker,
  endpoint, flag, capability string) speculatively and in parallel — this is low-risk and
  additive (§6). But the router should not be told to actually *consume* `task_class` as a
  join key for real routing decisions until a short, explicit negotiation (even an async doc
  exchange, not necessarily a live meeting) pins the shared vocabulary — mirroring how the
  AAR contract itself was "locked" (§12 Change Log: "Contract locked at P3 scope") only after
  its enum semantics were nailed down, not at first draft. This is precisely the charter's
  `conditional` verdict bucket, not `go` or `no-go`.

## 4. Additional deal-killers beyond the charter's

None found that are absolute (build-blocking) beyond the vocabulary-join risk in §3, which
this leg treats as a **precondition**, not an abandon signal. Two adjacent risks are worth
naming explicitly as they were not called out in the charter's single deal-killer clause:

1. **Guardrail-enforcement split** (risk register row 2): design-spec §5 lists four
   guardrails as if they are one flat set CCDash "provides," but two of the four
   (bounded-adjustment floor, human-override-always-wins) are structurally the *router's*
   responsibility per §3c/§4, not CCDash's. This is not a deal-killer for CCDash (CCDash's
   own blast radius stays zero regardless), but it means the spec's success claim in §8 —
   "reversible... a human override always wins" — is **not something CCDash can verify or
   guarantee end-to-end** from this repo. Worth flagging in the seam contract so nobody
   later blames CCDash for a router-side oscillation bug.
2. **Vocabulary drift over time**: even after an initial negotiation succeeds, the
   router's taxonomy can evolve independently (new task classes added on `ibm-main`) with
   no mechanism here to detect drift — the AAR contract's capability-gate pattern (`§1.5`,
   "absent capability = server predates feature") only detects *endpoint* absence, not
   *vocabulary* staleness. Not a deal-killer, but an open maintenance risk to name in the
   eventual seam contract's resilience section (mirroring AAR contract §7).

## 5. Constraint-4 structural guarantee

**Yes — structurally guaranteed by the offline-aggregation design, contingent on porting
one existing test.**

- `aar_review.py` (`backend/application/services/agent_queries/aar_review.py`) holds
  Constraint 4 by construction: its own module docstring states no model/LLM import exists
  anywhere on its compute path, and this is not just asserted but **CI-enforced** by
  `backend/tests/test_aar_review_no_llm_imports.py`, which performs a static AST walk of
  the transitive import graph from the module entry point and fails the build if any
  banned model-client name (`anthropic`, `openai`, `litellm`, `langchain`,
  `google.generativeai`/`genai`) or Task/Agent-dispatch symbol appears anywhere in the
  closure. `aar_review_writeback.py` (the gated escalation seam) extends the same
  invariant and the same test pattern to its own module.
- The design spec's rollup (§3a/§3d) is described as pure SQL/threshold/count aggregation
  over already-ingested rows — the same shape as `system_metrics.py` and the `aar_reviews`
  rollup, both cited directly by the spec as anchors. There is no proposed step in the
  design that requires a model call; it is arithmetic over already-materialized data,
  identical in kind to what `aar_review.py` already proves is achievable model-free.
- **Caveat**: this guarantee is *provable for CCDash's half only*. The spec's §3d claim
  that "the router reads a static rollup... no model, no network, at decision time" is an
  assertion about code CCDash cannot see (MeatySkills repo). CCDash's own Constraint-4
  guarantee is airtight (and cheaply made CI-enforced by cloning
  `test_aar_review_no_llm_imports.py` for the new module); the *end-to-end* loop's
  Constraint-4 compliance depends on the router honoring its own half, same as the
  guardrail-split risk in §4.

## 6. CCDash blast radius

**Confirmed near-zero**, consistent with every existing opt-in feature-flag precedent in
this codebase (`backend/config.py` lines ~67-249 show ~15+ similarly-shaped
`CCDASH_*_ENABLED` flags, most default `false`, e.g. `CCDASH_ARTIFACT_INTELLIGENCE_ENABLED`,
`CCDASH_AAR_REVIEW_AUTONOMOUS_WORKER_ENABLED`, `CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED`):

- **Additive only**: proposed new table/rollup (OQ2), new `agent_queries/` service module,
  new REST/MCP/CLI read surface, new capability string — no existing row schema, endpoint,
  or query is modified. Directly parallels how `aar-review` was added to `_V1_CAPABILITIES`
  in `backend/routers/client_v1.py` (append-only list) without touching prior entries.
- **Default-off**: `CCDASH_ROUTING_ROLLUP_ENABLED`, following the exact pattern of
  `CCDASH_AAR_REVIEW_AUTONOMOUS_WORKER_ENABLED` (`backend/config.py:112`, default `False`)
  and `CCDASH_ARTIFACT_INTELLIGENCE_ENABLED` (`:82`, default `False`) — proven, low-risk
  rollout convention in this codebase for exactly this class of feature.
- **No user-data migration**: the tuple's underlying fields (`modelVariant`, `modelProvider`,
  `profile`, `effortTier`, `skillName`, cost/error signals) are already captured columns on
  `AgentSession` per the spec's own framing (§1) — no backfill, no schema mutation of
  existing tables is implied by an *additive* rollup table; if a new table is chosen (OQ2),
  it is a fresh table, not a migration of existing rows.
- **No auth/payment/deletion surface touched**: the feature is read-only observability
  turned into a read-only PULL surface. No write, no dispatch — CCDash's own consumer-facing
  guarantee (§4/§6.1 of the design spec: "CCDash produces evidence only... never routes,
  dispatches, mutates the registry, or writes RoutingRecords") is the same non-actuating
  posture already shipped and verified for AAR-review (§5.2 of the AAR consumer contract:
  "no `op_client`, `arc_client`, `swarm`, or `skillmeat_api` imports").
- **Reversible instantly**: flipping the flag off reverts to current behavior with zero
  residual state change on CCDash's side (no write path exists to leave residue).

Net: the risk this leg is actually worried about is not "CCDash breaks something" — it's
"CCDash builds a correct, safe, zero-blast-radius feature that is *functionally inert or
silently miscalibrated* on the consumer side because the join key was never negotiated."
That is a **value/effectiveness** risk wearing a **blast-radius** costume, not a
blast-radius risk in the traditional (breakage/security/data-loss) sense.

## 7. Confidence score + justification

**0.72** — reasonably confident the risk *picture* (not the risk *level*) is complete for
what's discoverable from this repo alone. The two biggest sources of residual uncertainty
are structural, not investigative gaps: (1) the router's actual taxonomy and merge-math
implementation live in an unreachable repo, so any claim about the true join-failure
probability is an inference from spec text, not a fact I can verify; (2) the `value` leg's
sample-density findings (not yet read by this leg) could materially change whether the
minimum-sample-threshold guardrail is adequate in practice for a single-operator workload —
if density is provably too sparse, that risk register row's likelihood should be revised
upward independent of this leg's own analysis.
