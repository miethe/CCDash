---
schema_name: ccdash_document
schema_version: 2
doc_type: human_brief
title: "Proof → Routing Loop — Human Brief"
status: draft
category: human-briefs
feature_slug: proof-to-routing-loop
feature_family: aos-backward-pass
feature_version: v1
prd_ref: docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md
plan_ref: docs/project_plans/implementation_plans/infrastructure/proof-to-routing-loop-v1.md
intent_ref: null
epic_ref: null
owner: nick
contributors: []
audience: [humans]
priority: medium
confidence: 0.75
created: 2026-07-29
updated: 2026-07-29
tags: [human-brief, infrastructure, routing-feedback, cross-repo, no-llm]
---

# Proof → Routing Loop — Human Brief

> Living document for human orchestrators. Agents: do not load unless explicitly instructed.
> Status: draft | Updated: 2026-07-29

---

## 1. Context Pointers

One-line pointers. Do not restate content.

- **PRD**: `docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md` — full feature spec, goals, acceptance criteria, open questions.
- **Implementation Plan**: `docs/project_plans/implementation_plans/infrastructure/proof-to-routing-loop-v1.md` — 6-phase rollout with per-phase task breakdown, estimates, and model routing.
- **Decisions Block**: `.claude/worknotes/proof-to-routing-loop/decisions-block.md` — 9 locked decisions (D1–D8) + 1 pending (D9), phase boundaries, risk hotspots, estimation anchors.
- **Feasibility Brief**: `docs/project_plans/exploration/proof-to-routing-loop/proof-to-routing-loop-feasibility-brief.md` — exploration verdict `conditional` (confidence 0.75), precondition cleared 2026-07-26.
- **Cross-repo Contract**: `agentic_meta_dev/docs/agentic-operator/contracts/routing-feedback.md` (v1.0.0) + `routing-feedback-task-map.v1.json` — pinned join envelope and skill_name→task_class mapping.

---

## 2. Estimation Sanity Check

**Bottom-up total**: 16 points (6 phases: 2+3+4+2+3+2) / ~3.5 engineer-weeks (assuming ~4.5 pts/week sustained)

**Top-down anchor**: Automated AAR Review Loop v1 (merged `7d96c3e`) ran ~30–45 pts across 7 phases. This feature skips AAR's two heaviest phases (multi-hop feature→plan→task traversal + SkillMeat semantic 5th-flag linkage) because the rollup is a flat GROUP BY over already-typed session rows. Discount: ~55% off AAR's total → 16 pts baseline.

**Reconciliation (corrected)**: The feasibility brief's original 10–16 pt range assumed a read-time-only
aggregation path. We instead committed to the **persisted** path (D4), whose comparable AAR-review-clone
expectation is actually ~16–20 pts — **16 pts is the floor of that 16–20 range, not the ceiling of the
brief's original 10–16 range.** Primary basis remains the AAR-review-clone discount anchor (H5). Three
named contingencies could push the total toward 20: (1) Phase 3 is tied to D9 socialization risk (the
metric-payload shape may need revision after router-owner feedback); (2) Phase 4's rolling-window UPSERT
identity (post-B2 grain fix) differs from the AAR-review job's simpler append-only triage pattern, so it
isn't a pure mechanical clone; (3) Phase 6's DOC-006 task authors three design specs (including DI-1, the
router-merge-math handoff, which requires real synthesis), not one boilerplate stub.

The 16-pt estimate sits at the Tier 2/3 boundary (threshold is typically 16 pts) but is held at Tier 2 due to:
- **Complexity**: Only 1 algorithmic phase (P3: aggregation + mapping + coverage + metric design). The rest are near-exact clones of shipped AAR-review surfaces.
- **Risk**: Exploration (feasibility brief) cleared the blocking precondition (cross-repo vocabulary join via pinned v1.0.0 contract, 2026-07-26), leaving technical risk as "did-we-clone-AAR-correctly," not "does-the-feature-even-work."
- **Scope**: No LLM, no UI, no auth/payment/deletion — purely additive data layer + worker + read-only REST/MCP/CLI.

**H1–H6 application**:
- **H1 (scope clarity)**: High — PRD, plan, and decisions are all locked; cross-repo contract is pinned; no ambiguity. ✅ **Drives LOW complexity.**
- **H2 (tech risk)**: Medium-low — clone of shipped precedent (AAR-review), but cross-repo seam needs precision (digest verification, mapping application). Handled by Phase 1 gate + Phase 6 parity test. ✅
- **H3 (integration surface)**: Medium — 6 integration points (table DDL, query service, worker, REST, MCP, CLI) but all follow the AAR template. Clone-discounted. ✅
- **H4 (team familiarity)**: High — backend team has built 7-phase AAR loop; this team knows the pattern. ✅ **Drives LOWER complexity.**
- **H5 (external dependencies)**: Medium — depends on agentic_meta_dev + MeatySkills repo contracts (already pinned, not fetch-able at runtime). Router-side consumption is out of scope, so no critical-path blocker. ✅
- **H6 (test/QA overhead)**: Medium — requires CI guards (no-LLM AST walk, digest parity, determinism test, disabled-state contract test), plus consumer-contract docs and operator guide. But no end-to-end UI smoke test or integration environment needed (no FE surface). ✅

---

## 3. Wave & Orchestration Notes

**Critical path**: P1 → P2 → P3 → (P4 ∥ P5) → P6

Each serial phase freezes a contract that the next consumes:
- **P1 (2 pts, 3–4 days)**: Vendor the `routing-feedback-task-map.v1.json` contract file, pin digest constants, add capability string, register default-off flag. Gate: digest-parity test green.
- **P2 (3 pts, 4–5 days)**: `routing_rollup` table (dual SQLite+PostgreSQL DDL), repository with `retry_on_locked`, migration governance. Additive-only (not a Mode-D schema migration). Gate: dual-DDL parity + repo tests green (ADR-006/007 discipline).
- **P3 (4 pts, 5–7 days)**: Core algorithmic phase — RoutingRollupQueryService in `agent_queries/`, pure SQL aggregation at `(project_id, source_skill_name, model)` grain, apply the pinned mapping to derive `task_class`, compute metric payload (sample_count, success_rate, cost_index, regression_rate, confidence, window, freshness). Gate: determinism test + no-LLM import test + mapping-fidelity test all green. **Elevated review** (karen, not just validator).
- **P4 ∥ P5 (2+3 pts, 5–7 days parallel)**: After P3's contracts freeze, worker sweep job (P4, writes to `routing_rollup`) and transport surfaces (P5, reads from `routing_rollup`) touch disjoint files and can run in parallel.
  - **P4 (Worker)**: RoutingRollupSweepJob cloning AARReviewSweepJob — multi-project sweep via `workspace_registry.list_projects()`, incremental/idempotent, flag-gated, cache-invalidate on write.
  - **P5 (Transports)**: REST GET `/api/v1/routing/rollup`, MCP tool, CLI `ccdash routing rollup`. One shared DTO shape, capability-advertised.
- **P6 (2 pts, 3–4 days)**: Validation, guards, docs. No-LLM CI guard port, DTO contract-lock test, disabled-state contract test across all three transports, digest-parity test, sparse-key visibility test. Docs: consumer-contract doc (mirroring `ccdash-aar-review-consumer-contract-v1.md`), operator guide (mirroring `aar-review-loop.md`), DOC-006 deferred-items design spec (router-side merge + window/decay defaults placeholder). Gate: task-completion-validator + karen (feature end) both pass.

**Merge order**: All to main in a single PR (additive-only, no schema migration of existing rows, no risky seams post-P1).

**Cross-feature coupling**: None within CCDash. The feature depends on pinned contracts from agentic_meta_dev (already vendored in P1). The router (MeatySkills) is out of scope for this execution; router-side merge + live consumption remain disabled.

---

## 4. Open Questions Ledger

| ID | Source | Question | Status | Resolved By | Notes |
|----|--------|----------|--------|------------|-------|
| OQ-1 | PRD §12 | Is skill_name (bucketed via pinned v1 mapping) an acceptable v1 task_class source? | ✅ Resolved | D3 | CCDash applies the exact pinned mapping; never emits raw skill_name as task_class; unmapped → _unclassified coverage-only. |
| OQ-2 | PRD §12 | Exact metric-payload schema — concrete field names/types for sample_count/success_rate/cost_index/regression_rate/confidence/window/freshness, and which are router-consumed vs CCDash-diagnostic. | ✅ Resolved | P3 task design | PRD §6.3 defines: sample_count:int, success_rate:float, cost_index:float, regression_rate:float, confidence:float, window_start/window_end (ISO 8601), freshness_ts (ISO 8601). All router-consumed as evidence; none are router-diagnostic. |
| OQ-3 | PRD §12 | Minimum-sample eligibility_hint semantics, default threshold, and override env var name. | ✅ Resolved | P3 task design | eligible_for_adjustment = sample_count >= CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE (default 5, anchored to value-findings N≥5). Router may apply its own threshold independently. |
| OQ-4 | PRD §12 | Protected-class (orchestration, mode_d) and _unclassified emission policy — confirm coverage-only row shape and config gate name. | ✅ Resolved | P3 task design | _unclassified always emitted (visibility). orchestration/mode_d emitted iff CCDASH_ROUTING_FEEDBACK_INCLUDE_PROTECTED_ROWS=true (default true). All three carry hardcoded eligible_for_adjustment=false, never addressable as routing keys by compliant consumers. |
| OQ-5 | PRD §12 | Vendored-mapping file path inside CCDash and the version/digest-bump refresh procedure. | ✅ Resolved | P1 task | backend/application/services/agent_queries/routing_task_map_v1.json. Refresh = re-vendor JSON + bump mapping_version + mapping_digest constants together in routing_feedback_contract.py. CI parity test fails if digests don't match. |
| OQ-6 | PRD §12 | Rolling window length default and decay-input representation (contract leaves this to CCDash; no length is fixed here). | 🔄 Deferred | P3 design + DOC-006 | Candidate default: 30 days (from value-findings spike). Window/decay numeric finalization is a DOC-006 deferred item (DI-3) pending router-side consumption empirics. P1 records the placeholder in the seam doc. |

---

## 5. Deferred Items Rationale

**DI-1: Router-side empirical merge + live consumption** (cross-repo, MeatySkills/ibm-main)
- *Why deferred*: This repo ships only the CCDash producer surface. Router-side merge math (bounded-adjustment cap, effective-score floor, minimum-sample re-gate, decay blend, RoutingRecord provenance) is owned by MeatySkills and is currently `live_consumption_disabled`.
- *Trigger for promotion*: Router owner implements merge logic and flips live_consumption_disabled → enabled.
- *Captured as*: D1, D8, and a DOC-006 design-spec stub in Phase 6 (`routing-feedback-router-merge-handoff.md`).

**DI-2: Model/provider cross-repo namespacing**
- *Why deferred*: The contract does not pin a canonical `model` string format. CCDash emits its captured value verbatim and derives `provider` via `derive_model_identity()`. Any cross-repo canonicalization of model naming is a future negotiation between CCDash and router owners.
- *Trigger for promotion*: Cross-repo model-naming negotiation is opened.
- *Captured as*: A DOC-006 design-spec stub in Phase 6 (`routing-feedback-model-provider-namespacing.md`).

**DI-3: Window/decay numeric defaults**
- *Why deferred*: The contract explicitly leaves rolling-window length, freshness, and decay-input representation to CCDash but fixes no length. The `30`-day candidate here is spike-anchored (value-findings) but not a locked requirement. Implementation plan finalizes the actual default and any override knob.
- *Trigger for promotion*: Router-side consumption goes live and empirically validates (or invalidates) the candidate defaults.
- *Captured as*: A DOC-006 design-spec stub in Phase 6 (`routing-feedback-window-decay-defaults.md`).

---

## 6. Risk Narrative

**Risk 1: Silent non-join / cross-repo vocabulary drift (seam risk, R-P3) — HIGH impact, LOW likelihood (post-contract)**

A well-formed rollup that the router cannot join is inert; a coincidental mis-join is a correctness bug. The join key lives in an external repo (MeatySkills) that CCDash cannot see at runtime.

*Mitigation*:
- Emit canonical `task_class` via the exact pinned mapping only (never raw `skill_name`).
- Carry all three digests verbatim in every response: `contract_digest`, `taxonomy_digest`, `mapping_digest`.
- **Phase 1 & 6 CI parity test**: Assert vendored mapping file's SHA-256 == normative `mapping_digest` on every build.
- Router's implemented fail-closed `validateFeedbackJoin()` is the ultimate backstop (router re-verifies each row's mapping independently).
- **P6 integration-owner declaration**: The engineer who lands P6 owns the parity test; they coordinate with the router team to confirm digest alignment.

**Risk 2: Per-key sparsity for a single-operator workload (effectiveness risk) — MEDIUM impact, MEDIUM likelihood**

If every `(task_class × model)` key is too thin to clear the router's minimum-sample threshold, the signal never actuates.

*Mitigation*:
- Value-findings spike validated the coarsened tuple: 40 keys, 52% clearing N≥5 (30-day window). Density deal-killer is refuted for the achievable tuple.
- Every emitted key carries `sample_count` + `eligible_for_adjustment` so the router applies its own threshold independently.
- Thin keys simply don't route (safe, not wrong).
- `_unclassified` and coverage counts surface skill-name capture gaps for operator tuning.

**Risk 3: Constraint-4 violation (LLM on compute/read path) — MEDIUM impact, LOW likelihood**

An accidental model import anywhere in the worker or service transitive closure breaks the AOS invariant (Constraint 4: no LLM on the decision path).

*Mitigation*:
- Pure-SQL aggregation (no model-instance creation).
- Worker and service import nothing from `backend.adapters.agents` or `services.agents`.
- **Phase 3 no-LLM AST-walk CI guard** (port of `test_aar_review_no_llm_imports.py`): fails the build if a banned symbol is detected anywhere in the import graph.
- **Phase 6 determinism test**: two sweeps over an unchanged window produce field-identical rows (rules out any stochastic/model-based logic).

**Risk 4: Metric-payload shape unconsumable by router (seam/schedule risk) — MEDIUM impact, MEDIUM likelihood**

The contract leaves the numeric payload unspecified. A unilaterally-designed shape may not match what the router's future merge logic needs.

*Mitigation*:
- D5 metric payload is **additive-versioned** — fields can be added without breaking old consumers.
- **D9 (pending): Socialize the metric-payload shape with the router owner before Phase 5 ships** (P5 is the last phase before the feature is complete).
- Keep metrics evidence-only so a mismatch is inert, never harmful (router can ignore unexpected fields).
- Record the payload in a CCDash-authored addendum to the seam contract in Phase 1.

**Risk 5: Blast radius on CCDash (new table/worker/endpoints regress existing reads) — LOW impact, LOW likelihood**

New schema, worker, and API surfaces could regress the `sessions` or `aar_reviews` read paths.

*Mitigation*:
- Additive-only DDL (zero `ALTER TABLE` on existing rows).
- Default-off flag; disabled state returns a deterministic empty envelope.
- Zero mutation of `sessions.*, aar_reviews.*` anywhere in the codebase.
- Instant env-var revert reverses all emission and returns disabled responses.
- **P6 regression test suite**: existing `sessions` and `aar_reviews` tests remain green post-merge.

---

## 7. What to Watch For

**During execution**:
1. **Phase 1 digest alignment**: The vendored `routing_task_map_v1.json` file must match the canonical copy in agentic_meta_dev *before* the Phase 1 engineer lands it. If the digest in the file's header doesn't match `mapping_digest` in the constants, the parity test fails and P1 does not seal.
2. **Phase 3 metric-payload finalization**: This is the only algorithmic phase and the moment of truth for D5. Watch for scope creep (temptation to add correlation fields, weighted averages, decay curves — all live in the router's merge phase, not here). Keep it evidence-only.
3. **D9 socialization timing**: Before Phase 5 lands, the engineer must document at least one attempt to socialize the D5 metric payload with the router owner. If D9 remains "pending" and P5 ships, leave a note in the phase-5 completion document explaining the attempt (success or blockers). Do not seal P5 without at least documenting the socialization attempt.
4. **P6 parity test coordination**: The Phase 6 engineer owns the CI parity test; they need to confirm with the agentic_meta_dev team that the contract digests haven't drifted since P1 vendored them.
5. **Coverage counters in live data**: Once Phase 5 ships and the feature is enabled in a test environment, check the `mapped_count` vs `unclassified_count` ratio. If unclassified is >80% of all sessions, it signals a capture or mapping gap (e.g., new skill names not yet in the v1.0.0 mapping, or sessions launched without skill_name capture).

---

## 8. Expected Success Behaviors

Human-verifiable, post-ship outcomes from PRD AC-1..AC-8:

- [ ] **Envelope completeness (AC-1)**: Hit `GET /api/v1/routing/rollup` (or `ccdash routing rollup` or MCP tool) and verify all 11 pinned envelope fields are present in at least one key, plus top-level `mapped_count`, `unclassified_count`, and `distinct_unmapped_skill_names`.
- [ ] **Mapping fidelity (AC-2)**: Run the Phase 1 digest-parity CI test locally; confirm the vendored `routing_task_map_v1.json` file's SHA-256 matches the hardcoded `mapping_digest` constant.
- [ ] **Determinism (AC-3)**: Run the Phase 3 determinism test (two sweeps on fixture DB produce identical rollup rows).
- [ ] **Disabled-state consistency (AC-4)**: Set `CCDASH_ROUTING_FEEDBACK_ENABLED=false`, restart the server, and hit all three transports (REST, MCP, CLI) — verify all return `{"enabled": false, "mapped_count": 0, "unclassified_count": 0, "keys": []}` byte-for-byte.
- [ ] **Sparse-key visibility (AC-5)**: In an enabled response, find a key with `sample_count: 2` and verify it still carries `eligible_for_adjustment: false` (and is never presented as an addressable routing key).
- [ ] **Protected-class coverage-only (AC-6)**: Verify at least one `_unclassified` row appears in the response with `eligible_for_adjustment: false` hardcoded (and appears even if `CCDASH_ROUTING_FEEDBACK_INCLUDE_PROTECTED_ROWS=false`, since _unclassified is always emitted for visibility).
- [ ] **Reversibility (AC-7)**: Set flag to `true`, confirm non-empty response. Flip to `false`, restart, confirm disabled envelope. Flip back to `true`, confirm non-empty again (no backfill needed).
- [ ] **Version-mismatch resilience (AC-8)**: Every response (enabled or disabled) carries `contract_version: "1.0.0"`, `taxonomy_version: "1.0.0"`, `mapping_version: "1.0.0"` fields present and readable.

---

## 9. Running Log

_Optional. Append-only. Short notes during execution — surprises, pivots, validated assumptions._

- **[2026-07-29]** Brief created from PRD (locked 2026-07-29), implementation plan (locked 2026-07-29), and decisions block (locked 2026-07-29 except D9 pending). Cross-repo contract (routing-feedback v1.0.0) pinned and precondition cleared 2026-07-26. No gotchas anticipated; team familiar with AAR-review precedent. Ready for execution.

