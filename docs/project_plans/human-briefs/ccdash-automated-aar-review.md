---
schema_name: ccdash_document
schema_version: 2

doc_type: human_brief
doc_subtype: feature_brief
root_kind: project_plans

id: BRIEF-ccdash-aar-review
title: "CCDash Automated AAR Review Loop — Human Brief"
status: draft
category: human-briefs

feature_slug: ccdash-automated-aar-review
feature_family: ccdash-automated-aar-review
feature_version: v1

prd_ref: docs/project_plans/PRDs/features/ccdash-automated-aar-review-v1.md
plan_ref: docs/project_plans/implementation_plans/features/ccdash-automated-aar-review-v1.md
intent_ref: null
epic_ref: null

related_documents:
  - docs/project_plans/feature_contracts/features/ccdash-aar-review-mvp.md
  - docs/project_plans/exploration/ccdash-automated-aar-review/ccdash-automated-aar-review-proposed-adr.md
  - docs/project_plans/exploration/ccdash-automated-aar-review/ccdash-automated-aar-review-feasibility-brief.md

owner: nick
contributors: []

audience: [humans]

priority: high
confidence: 0.78

created: 2026-07-22
updated: 2026-07-22
target_release: ""

tags: [human-brief, aar-review, automation, op-integration]
---

# CCDash Automated AAR Review Loop — Human Brief

> Living document for human orchestrators. Remaining efforts (P2–P4) after the shipped Tier 1 MVP (P1).
> Status: draft | Updated: 2026-07-22

---

## 1. Context Pointers

- **PRD**: `docs/project_plans/PRDs/features/ccdash-automated-aar-review-v1.md` — full vision (all 4 phases, 34–45 pts)
- **Implementation Plan**: `docs/project_plans/implementation_plans/features/ccdash-automated-aar-review-v1.md` (in progress, expands the decisions block)
- **Completed P1 Feature Contract**: `docs/project_plans/feature_contracts/features/ccdash-aar-review-mvp.md` — shipped Tier 1 slice (correlation + 4 flags + read-only surfaces, ~12 pts)
- **ADR + Feasibility**: `docs/project_plans/exploration/ccdash-automated-aar-review/ccdash-automated-aar-review-proposed-adr.md` (accepted, seam contract); feasibility brief (go, 0.8 confidence)
- **Decisions Block**: `.claude/worknotes/ccdash-automated-aar-review/decisions-block.md` (phases, agent routing, risks, OQs — the orchestration scaffold)

---

## 2. Estimation Sanity Check

**Bottom-up total (remaining P2–P4)**: 26–34 points across 7 capability areas  
**Top-down anchor**: RF run telemetry (commit `9594fcc`, Tier 3, ~26 pts full) — this feature's correlation-persistence wave is a direct comparable; however, AAR-review adds cross-repo consumer contract (Ph5, +30–70%) and HITL-writeback with 3 self-recursion guards (Ph6, no RF analogue) ⟹ **+8–15 pts above RF baseline**.  
**Reconciliation**: The remaining work exceeds RF telemetry by the asynchronous cross-repo seam phase (Ph5: contract + ADR transport decision + smoke, not implementation) and the guarded-writeback orchestration layer (Ph6: guards + worker + gate, heavier than RF's simple telemetry export). This is realistic; no H1–H6 adjustment needed.

**Per-phase point ranges** (from decisions block §4):

| Phase | Points | Scope |
|-------|--------|-------|
| 1 (Verdict Reconcile + Persist) | 5–7 | Schema reconciliation + `aar_reviews` table (dual DDL) + provenance/dedup columns |
| 2 (Full-Metadata Enrichment) | 5–7 | Deterministic doc→feature→plan→task traversal + flag sharpening + evidence attachment |
| 3 (SkillMeat + 5th Flag) | 3–5 | Artifact-ranking linkage + 5th flag (read-only) |
| 4 (FE Panel + v1 Endpoint) | 4–6 | Read-only review panel (3 verdict states, resilient) + v1 REST endpoint + capability ad |
| 5 (Cross-Repo Contract) | 5–8 | op-side consumer contract + transport decision (D5) + smoke (heavy D5 design cost, light in-repo delivery) |
| 6 (Gated Writeback + Worker) | 6–9 | 3 guard enforcement + autonomous worker + escalation-quota ledger + gate integration tests |
| 7 (Documentation + Deferred Specs) | 2–3 | Guides + CHANGELOG + CLAUDE.md pointer + DOC-006 design specs for OQ-3/OQ-4/OQ-6 |

**H1–H6 application**:
- **H1 (noun-counting)**: 2 new DTOs (P1) + 1 table (P2) + 1 event schema (cross-cutting) + 3 guard data structures (P4) ⟹ 4–6 pts new-noun floor, in range.
- **H2 (dual-implementation)**: Single SQLite+PostgreSQL backend (not local+enterprise) ⟹ no ×1.8 multiplier; H2 not applicable.
- **H3 (algorithmic)**: 3 needs-derivation flags at ≥3 pts each (Ph2) + SkillMeat correlation (Ph3) ⟹ ~6–9 pts algorithmic, matching ~8–12 pts for P2–P3 combined.
- **H4 (bundle-vs-sum)**: 7 capability areas (correlation, persistence, enrichment, SkillMeat, transports, cross-repo seam, writeback) ⟹ floor applies; 26–34 is the bundle consensus.
- **H5 (anchor)**: RF run telemetry ~26 pts (Tier 3); this feature's flag-derivation slice (Ph2–Ph3) alone is 8–12 pts (heavier than RF's 8-pt correlation wave); adding cross-repo + writeback justifies the 30–70% uplift ⟹ 26–34 is sound.
- **H6 (hidden plumbing)**: DTOs, dual DDL, OpenAPI, CHANGELOG ⟹ ~15–20% folded into ranges above.

---

## 3. Wave & Orchestration Notes

**Critical path (7 phases, strictly serial at phase boundaries)**:

```
Ph1 (Verdict Reconcile)
 ↓ [schema/verdict must freeze before persistence/consumers read it]
Ph2 (Enrichment)
 ↓ [enrichment surface is prereq for SkillMeat linkage in Ph3]
Ph3 (SkillMeat + 5th Flag)
 ↓ [full verdict must exist before it's exposed/rendered in Ph4]
Ph4 (Read Surfaces: FE + v1 endpoint)
 ↓ [v1 surface must exist before external consumer can reference it in Ph5]
Ph5 (Cross-Repo Consumer Contract)
 ↓ [op-side contract + routing proven before autonomous writeback in Ph6]
Ph6 (Gated Writeback + Worker)
 ↓ [all enforcement in place before docs finalization in Ph7]
Ph7 (Documentation + Deferred Specs)
```

**Parallelization opportunities**:
- **Ph2 ∥ Ph3 scaffold** (after Ph2 enrichment-evidence contract is locked): Ph2 defines the enrichment service + API surface; Ph3 can scaffold SkillMeat-ranking plumbing in parallel once Ph2's DTO shape is clear, then join at Ph4 when both surfaces exist.
- **Ph4 FE ∥ v1 endpoint** (file ownership split): `FeatureAARReviewPanel.tsx` (FE) and `client_v1.py` (BE) are independent until a seam task (DTO field → both surfaces) validates payload shape end-to-end.

**Merge order**:
- Ph1 completed before Ph2 branch opens (schema stability gate).
- Ph2+Ph3 can be in-flight concurrently (separate PRs) but must be reviewed sequentially (Ph2 → Ph3 dependency clear).
- Ph4 FE + v1 branches merge after their seam task validates both surfaces.
- Ph5–Ph7 strictly sequential (downstream dependencies accumulate).

**Cross-feature coupling**:
- **Upstream**: Depends on RF telemetry (commit `9594fcc`; stable, shipped). No other active features block this.
- **Downstream**: op-side consumer code (P3) lives in `agentic_meta_dev`/`op` repo — this feature's Ph5 contract is a forward-facing API promise; no other CCDash feature depends on it yet.

---

## 4. Open Questions Ledger

| ID | Source | Question | Owner | Status | Resolved By Phase | Notes |
|----|--------|----------|-------|--------|-------------------|-------|
| OQ-1 | PRD §15 | Do real `op story` AARs carry session/feature frontmatter today, or is two-hop the norm? | — | open | Ph1 | Tech leg assumed two-hop fallback; OQ-1 controls whether any cross-repo session-ref contract is needed (OQ-3). Resolve by sampling ≥5 real AARs early in Ph1. |
| OQ-2 | PRD §15 | Is the 0.64–1.0 two-hop confidence band sufficient for autonomous triage, or should every two-hop pairing route to `human_triage_required` regardless of score? | — | open | Ph1 | Affects verdict decision table (§7.2). P1 validation must confirm before Ph2 persists history. |
| OQ-3 | PRD §15 | Exact frontmatter contract `op story` should adopt if session-ref increment is pursued; who owns that cross-repo change? | — | open | Ph7 (DOC-006) | Contingent on OQ-1. Deferred to Ph7 as a design-spec task only if OQ-1 shows low frontmatter prevalence. |
| OQ-4 | PRD §15 | Escalation-quota default (count/time-window) for P4 — per-project or global? Must be env-configured. | — | open | Ph6 | Affects the hard guard 3 (§8.1). Resolved during Ph6's guard-logic design; recorded in a DOC-006 spec. |
| OQ-5 | Reconciliation | Does the reconciled P1 DTO keep flat 2-value fields as deprecated aliases, or hard-cut to nested 3-value? | — | locked | Ph1 | D1: default to one-release deprecation window. |
| OQ-6 | D5 Transport | Does op consumption stay PULL (REST/MCP/CLI) as v1, or promote log-only event to durable/queued PUSH? | — | pending | Ph5 | Resolved from cross-repo smoke evidence in Ph5; if unresolved, deferred to Ph7 as DOC-006 spec. |
| OQ-7 | Enrichment Scope | Confirm every enrichment comparison is deterministic (set/threshold/ruleset), never semantic. | — | open | Ph2 | implementation-planner must annotate each enrichment task with its deterministic rule. |

---

## 5. Deferred Items Rationale

- **5th Flag (`new_skill_or_agent_need`)**: Deferred from P1 to P2 because it is the softest signal (derived from volume patterns of two other flags) and the nearest to the model/opinion boundary. It is deliberately omitted from P1's validation gate so the core 4 flags can ship independently proven; Ph2 adds it only once Ph1 flags are validated as useful/low-false-positive. Promote when: P1 shipped, validated, and approved for persistence (Phase 2 entry gate, scope-findings.md Inc-2).

- **`aar_reviews` rollup table**: Deferred from P1 to P2. P1 ships as a read-only query service (no persistence) so triage is lightweight and cheap; if volume/latency/caching proves insufficient after P1 production validation, Ph2 adds the rollup table and FE surface. Promote when: P1's per-request latency is acceptable or production volume justifies persistence (Ph2 entry gate).

- **FE review panel**: Deferred from P1 to P2. P1 surfaces triage via REST/MCP/CLI only; Ph2 adds the FE panel for operator convenience once the verdict shape is frozen and persisted. Promote when: Ph1 verdict schema locked, `aar_reviews` table backfilled (Ph2 early scope).

- **op-side consumer implementation**: Lives outside this repo (cross-repo, P3). This PRD specifies the contract (§7.3 event schema + routing logic); op/agentic_meta_dev owns the consumer code. Promote when: Ph5 contract is finalized and cross-repo smoke proves viability.

- **Writeback + autonomous worker**: Deferred from P1–P3 to P4 because every earlier phase is read-only and poses zero writeback risk. Ph4 adds the highest-blast-radius capability (autonomous ARC dispatch + SkillMeat mutations) only after all earlier read-side and cross-repo gates are proven. Promote when: Ph3 op-side routing stable in production, escalation-quota design reviewed (Ph4 entry gate).

- **Self-recursion guards (3)**: **Designed** in Ph1 (provenance columns + dedup key surfaced as first-class fields in the DTO + `aar_reviews` table) but **enforced** only in Ph4 when the autonomous worker path exists and poses the risk. Ph1–Ph3 have no escalation path, so guards have nothing to guard; but their data requirements must be met early to avoid a breaking schema change in Ph4. Promote enforcement when: Ph4 autonomous worker implementation begins.

- **DOC-006 design specs** (OQ-3, OQ-4, OQ-6): Deferred to Ph7. If any OQ remains unresolved at Ph6 completion, Ph7 includes a design-spec task capturing the design rationale for that open item, enabling a future implementer to pick it up without re-litigating the decision. Promote when: Ph7 docs phase (every open item gets a spec).

---

## 6. Risk Narrative

Six risk hotspots from the decisions block, orchestrator-facing:

1. **Hard-Invariant #1 violation (LLM on the read path)**: The enrichment mandate (compare plan-task intent vs session behavior) is a natural place for semantic heuristics to creep in. Any model call on the triage path is a review failure in any phase. Watch for: any implementation introducing a ruleset that requires judgment ("was this agent choice wrong") instead of fact-matching ("which agent was used"). Mitigation: Ph2 ships a test asserting no model-client import; every enrichment task is annotated with its deterministic rule; code review gates explicitly check for Invariant 1. Escalate to: task-completion-validator if any flag evaluator reaches for an ML model.

2. **Contract divergence (flat 2-value vs nested 3-value)**: P1 shipped a flatter DTO; PRD specifies nested + 3-value. If Ph1 reconciliation is skipped or botched, consumers (op/ARC) will break silently or require a breaking change mid-flight. Watch for: Ph1 reconciliation task marked complete but the DTO still carries the old shape, or a review comment "let's just use what P1 has." Mitigation: Ph1 explicitly reconciles per D1; bumps `schema_version`; a contract test pins the field shape. Escalate to: backend-architect if Ph1 DTO audit shows divergence.

3. **Writeback blast radius + self-recursion** (P4 only, highest risk): An autonomous worker triaging AARs can (a) triage its own review outputs (structural recursion) or (b) auto-escalate unbounded ARC/swarm handoffs. Watch for: any Ph4 implementation that skips guard 1 (provenance self-exclusion) or guard 3 (escalation quota), or treats `op approve` as optional. Mitigation: All 3 guards designed from Ph1; Ph4 integration test asserts a rejected/pending run NEVER writes; worker flag-gated default-off; code review explicitly rejects any "convenience bypass" of the `op approve` gate. Escalate to: backend-architect + `op` leadership if any Ph4 writeback runs without explicit `op approve`.

4. **Correlation reliability — two-hop is the norm** (OQ-1/OQ-2, Ph1 input): The one real AAR exercised in P1 validation had zero direct session frontmatter. If two-hop is indeed the norm, the 0.64–1.0 confidence band is the entire triage signal. Watch for: Ph1 validation sampling only 1–2 AARs (insufficient signal) or dismissing low-confidence pairings without understanding why. Mitigation: Ph1 early task samples ≥5 real AARs; OQ-2 decision recorded in Ph1 exit criteria before Ph2 persists any history. Escalate to: implementation-planner if sample shows confidence < 0.64 is common (may require threshold rethink).

5. **Autonomous worker load on the sync/watcher hot path** (Ph6 scheduling): A naive worker re-triaging all AARs each cycle adds unbounded load to the ingest path. Watch for: Ph6 worker implementation that re-scans all AARs per cycle instead of incremental (changed/new AARs only), or a second scheduler running in parallel with the existing sync/watcher. Mitigation: Ph6 worker reuses `(project_id, trigger)` coalescing guard (no second scheduler); scopes to changed/new AAR docs only (mirroring `CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED` pattern). Escalate to: backend-architect if Ph6 task proposes a new scheduling subsystem.

6. **LAN egress of session-derived evidence without redaction** (Ph4 only, security): The v1 endpoint + events stream session-derived evidence to op/ARC/Hermes over the LAN; unredacted fields must never leave. Watch for: any Ph4 implementation that reads raw JSONL directly or skips the redaction pipeline. Mitigation: Hard Invariant #4 — consume only redaction-passed `session_detail` output; v1 endpoint applies redaction before serialization; events remain count-only (IDs, flag_ids, verdict — no payload). Escalate to: data-layer-expert if any v1 response carries unredacted session-derived fields.

---

## 7. What to Watch For

_Gotchas, trap-doors, and real-time execution hooks. Updated during execution._

- [Specific gotcha or pattern to monitor]

_To be populated during execution._

---

## 8. Expected Success Behaviors

Human-verifiable post-ship outcomes (not AC checklists — observable in production):

- [ ] **Ph1 validation**: An operator samples ≥5 real AARs via the CLI (`ccdash report aar-review --feature ...` or similar) and observes 4 flags with non-empty evidence arrays + a verdict decision that matches expected triage logic (no surprise auto-escalations, no missing evidence). The schema reconciliation is proven by comparing the flat P1 DTO fields to the nested structure and confirming the old fields are deprecated aliases.

- [ ] **Ph2 persistence**: After Ph2 ships, the same operator queries the FE review panel and browses a list of triaged AARs with verdicts persisted over 1–2 triage cycles; paging/filtering works smoothly; no unexplained null fields crash the panel. The 5th flag is visible and populated for AARs matching the "new skill or agent" pattern.

- [ ] **Ph3 cross-repo smoke**: The `op` repo consumes a real `aar_review_candidate` event (via its own polling or our event transport) and routes a single high-confidence `deep_review_recommended` verdict to `op council` without any CCDash code change. A human verifies the recommendation draft is readable and evidence-backed.

- [ ] **Ph4 read surfaces**: The v1 REST endpoint (`GET /api/v1/aar-review/...` or similar) returns a triage verdict in <2s (p95). The FE panel renders 3 verdict states (surface_only, deep_review_recommended, human_triage_required) with all optional fields handled gracefully (no crashes on null evidence). Runtime smoke confirms all `target_surfaces` entries work on the browser.

- [ ] **Ph6 gated writeback**: The operator approves a recommendation draft in `op` CLI (`op approve <run_id>`), and CCDash observes the writeback trigger (via logs/metrics) flowing through the autonomous worker only after the approval. A simulated worker restart does not cause duplicate escalations (dedup ledger holds). A synthetic self-referential AAR (one describing an AAR-review session) is correctly excluded from the next triage pass (provenance guard holds).

- [ ] **No autonomous writeback ever occurs without `op approve`**: An integration test asserts that if a run record is in `rejected` or `pending` state, no writeback happens — the guard 3 (escalation quota) never fires and no SkillMeat mutation occurs.

- [ ] **Ph7 documentation complete**: CHANGELOG entry present for each phase that ships user/operator-facing capability; LAN-deployment guide updated with the v1 endpoint + capability string; CLAUDE.md updated with any new env vars or feature flags; all DOC-006 design specs (OQ-3/OQ-4/OQ-6) recorded if deferred.

---

## 9. Running Log

_Append-only. Short notes during execution — surprises, pivots, validated assumptions._

- [2026-07-22] Brief created from decisions-block scaffold + PRD § sections. Remaining work scoped at 26–34 pts (P2–P4); Ph1 shipped as independent Feature Contract. Confidence: 0.78 (strong anchor to RF telemetry; cross-repo seam + writeback phases add +30–70% over telemetry baseline, realistic for the guard complexity).
