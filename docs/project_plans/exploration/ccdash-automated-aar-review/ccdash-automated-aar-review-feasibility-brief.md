---
schema_version: 2
doc_type: report
report_category: feasibility
title: "CCDash Automated AAR Review Loop — Feasibility Brief"
status: finalized
created: 2026-07-21
updated: '2026-07-21'
feature_slug: ccdash-automated-aar-review
verdict: go
verdict_confidence: 0.8
exploration_charter_ref: 
  docs/project_plans/exploration/ccdash-automated-aar-review/ccdash-automated-aar-review-charter.md
proposed_adr_ref: 
  docs/project_plans/exploration/ccdash-automated-aar-review/ccdash-automated-aar-review-proposed-adr.md
recommended_next_action: "/plan:plan-feature --tier=1"
related_documents:
- docs/project_plans/exploration/ccdash-automated-aar-review/spikes/tech-findings.md
- docs/project_plans/exploration/ccdash-automated-aar-review/spikes/reuse-findings.md
- docs/project_plans/exploration/ccdash-automated-aar-review/spikes/risk-findings.md
- docs/project_plans/exploration/ccdash-automated-aar-review/spikes/scope-findings.md
---

# CCDash Automated AAR Review Loop — Feasibility Brief

**Verdict: `go` (confidence 0.8).** MVP is Tier 1 (~10–13 pts); full vision is Tier 3 (~34–45 pts),
sequenced after.

---

## 1. Synopsis

The AOS produces AARs everywhere but has no path from a *post-hoc AAR* to an *acted-upon system
improvement*. `op story` already sources AARs from CCDash (`ccdash report aar --feature`) yet
terminates in a blog draft PR — the improvement loop (triage → surface-review-or-ARC-deep-dive →
enhancement recommendation) exists nowhere. This idea has CCDash pair each agent-written AAR back to
the session log(s) it describes, compute deterministic surface flags over already-ingested data, and
emit a model-free triage verdict that `op`/ARC consume. The load-bearing assumption — that CCDash
already holds the correlation substrate — is confirmed. CCDash serves the operator/ARC by answering,
over existing data, "which recent sessions warrant a deep review, and on what evidence?"

---

## 2. Investigation Summary

| Leg | Agent | Confidence | Findings | Conclusion |
|-----|-------|-----------|----------|------------|
| tech | spike-writer | 0.82 | [tech-findings.md](spikes/tech-findings.md) | Deal-killer **refuted** — `document→session` correlation already materialized in `entity_links` (3-strategy: explicit ref 1.0, task-session 0.96, two-hop doc→feature→session 0.64–1.0; `sync_engine.py:6574-6656`). 2/5 flags computable now, 3 are deterministic derivation. No new ingest for MVP. |
| reuse | general-purpose | 0.82 | [reuse-findings.md](spikes/reuse-findings.md) | Non-duplicative seam **confirmed** — `op story` owns AAR→blog; the AAR→system-improvement loop is unowned. CCDash must reuse `op story`'s existing CCDash calls, not rebuild sourcing. Deterministic surface-flag triage is the one seam CCDash is uniquely positioned to close. |
| risk | backend-architect | 0.65 | [risk-findings.md](spikes/risk-findings.md) | Mitigable with in-repo precedent — 3 guards (provenance self-exclusion, `(aar_doc_id,session_id)` dedup ledger, escalation quota) + producer-only boundary. Cost/recursion/writeback risks all belong to gates upstream. |
| scope | general-purpose | 0.8 | [scope-findings.md](spikes/scope-findings.md) | MVP = Tier 1, ~10–13 pts (S1–S4: correlation + 4 flags + verdict DTO + REST/MCP/CLI). Full vision = Tier 3, ~34–45 pts. Correlation reuses `session_correlation.py`, so all 4 flags fit one sprint. |

---

## 3. Cost Estimate

**Rough estimate**: MVP ~10–13 story points (**Tier 1**, single Feature Contract sprint). Full vision
~34–45 pts (**Tier 3**), sequenced after MVP validation.

**Comparable past feature (H5 anchor)**: RF run telemetry (commit `9594fcc`, Tier 3, ~26 pts) — ingest
+ derived entity + run↔session correlation + analytics tab. Its **P2 correlation wave** (~8 pts:
entity minting + run↔session correlation via `entity_graph.py`, additive-only, zero changes to
`aos_correlation.py`) is the MVP-core calibration anchor. The MVP's correlation helper is comparable
in shape and *slightly smaller* — it reuses `session_correlation.py` rather than adding a new entity
kind, which is why the MVP lands at the low end of Tier 1 rather than Tier 2.

**Major cost drivers**:
- 3 needs-derivation flags (artifact diff, generic-agent ruleset, stack map) — the variable cost;
  each is deterministic feature-engineering, not a model call.
- Transport wiring (REST + CLI + MCP) + DTOs + tests — H6 plumbing, with direct precedent in
  `reporting.py` wiring.
- MVP has **no** new ingest, no new table, no FE — materially cheaper than the RF telemetry anchor.

---

## 4. Value Statement

**Primary beneficiaries**: the operator (`op`) and ARC — today the triage decision of *which* sessions
merit an expensive deep review is entirely manual; and CCDash itself, whose rich session evidence
currently dead-ends at feature-scoped AAR generation.

**The core insight — the inverse of `generate_aar`.** CCDash's `generate_aar` *synthesizes* an AAR
**from** telemetry, keyed by feature. This idea runs it backwards: take an agent-*written* AAR
document, pair it back to the session log(s) it describes, and deterministically triage those sessions
into `surface_only` vs `deep_review_recommended`. No subsystem computes this today — `op story` knows
only three coarse thresholds (tokens/sessions/duration); ARC knows nothing until pointed. The four
flags (missing artifacts, context ballooning, generic-agent-where-a-specialist-fit, stack
ineffectiveness) are computable **only** from data CCDash already holds (session JSONL + token/context
columns + `subagent_parent_id`/`skill_name`/`model_slug` detection columns + artifact snapshots).

**Evidence of demand**:
- The user's "ARC-driven AAR review" framing — a stated desire to close the AAR→improvement loop.
- `op story` already reaches into CCDash for AAR material (`story.py:1414-1458`), proving CCDash is
  the natural evidence home; it just lacks the review-worthiness triage tier.

**Counterfactual**: If not built, the AAR→system-improvement loop stays entirely manual; AARs continue
flowing only into the blog pipeline; and the "which sessions deserve ARC" decision remains a
human judgment call with no evidence-backed triage — the exact toil this closes.

---

## 5. Risks & Blast Radius

The three day-1 guards (all with in-repo precedent) plus the producer-only boundary keep this safe.

| Risk | Category | Severity | Mitigation |
|------|----------|---------|------------|
| Self-referential loop: AAR-review sessions re-triaged as input to the next pass | technical | H | **Provenance-tag self-exclusion** via `skill_name`/`workflow_id` capture columns at capture time — never content-sniff (that needs an LLM on the recall path). Precedent: telemetry exporter's skip-without-failing path. |
| Duplicate/racing triage + duplicate escalations across restarts | technical | M | **`(aar_doc_id, session_id)` idempotent dedup ledger**, mirroring `emit_artifact_outcomes`'s `dedup_key`; reuse the `(project_id, trigger)` coalescing guard, don't add a second scheduler. |
| Unbounded cost from auto-escalation to full ARC swarm | operational | H | **Env-configured escalation quota** checked *before* any handoff; CCDash never calls the swarm — it hands off via `op`/ARC's own gated classify→plan→dispatch. |
| Autonomous writeback into SkillMeat/agents bypassing HITL | organizational | H | Producer-only boundary (proposed ADR); recommendations land as `op story`-shaped drafts; mirror `council_review_queries.py`'s read-only line. |
| Silently-swallowed write failure in a new ledger (ADR-007 regression) | technical | M | **ADR-007 write-path compliance**: `retry_on_locked` + direct-count assertion test + dual SQLite+PG DDL. (Note: the MVP has no new table; this applies to Inc-2's `aar_reviews` rollup.) |
| False-positive flags drive bad recommendations at volume | operational | M | Low-confidence correlations route to human triage, never straight to synthesis; correlation confidence is part of the gate. |
| Redaction bypass if triage reads raw JSONL | technical | M | Triage consumes `session_detail.py`'s redaction-passed output, never raw transcript files — critical since the eventual audience is an external boundary. |

**Blast radius is bounded by design**: the MVP has no writeback, no swarm dispatch, no scheduling. All
irreversible actions stay behind existing upstream gates.

---

## 6. Architectural Implications

**Proposed ADR**: [ccdash-automated-aar-review-proposed-adr.md](ccdash-automated-aar-review-proposed-adr.md)
— CCDash is the producer of AAR-review evidence; `op`/ARC/SkillMeat own synthesis, swarm dispatch, and
writeback. Deterministic (model-free) triage on the CCDash side; no LLM on the recall path; all gates
upstream.

The MVP fits cleanly into the existing transport-neutral `agent_queries` pattern with **no structural
change** — it is a new read/derivation surface over existing data, following the exact shape of
`reporting.py` / `session_correlation.py`:

- **Query service** — additive `backend/application/services/agent_queries/aar_review.py`: given an AAR
  doc id/path, resolve sessions via `entity_links` (reuse `session_correlation.correlate_session`),
  pull session rows + `session_artifacts`, compute **4 deterministic surface flags**, and return a
  **triage verdict DTO** (`surface_only` vs `deep_review_recommended`, with flags[], evidence_refs,
  confidence, reasons). Reuse `@memoized_query`.
- **Ports** — reuse existing `storage.entity_links()/sessions()/documents()/features()`; no new port
  for MVP.
- **Transports** — REST `GET /agent/aar-review/{document_id}` (mirrors `/reports/aar`), CLI `report
  aar-review` subcommand, MCP tool — the standing transport-neutral fan-out.
- **Producer event** — a model-free `aar_review_candidate` record (feature/session refs + flag set +
  severity + verdict), mirroring the RF→CCDash `ccdash_event.yaml` shape *in reverse*. `op` consumes it
  and routes to ARC at ITS existing gate. **No swarm dispatch, no writeback, no scheduling in MVP.**

**Do-Not-Build list** (reuse-findings §4–§5; hard boundaries):
- **Do not rebuild AAR sourcing** — reuse `op story`'s existing `ccdash report aar` calls (`story.py`).
- **Do not rebuild a blog-scoring rubric** — `_classify_candidate` scores blog-worthiness, wrong sink.
- **Do not build a second correlation key** — reuse IntentTree `ccdash_session_id` + `document_linking`.
- **Do not synthesize new artifacts** — no "create a new skill/agent" path exists by design; that
  stays a human/Claude authoring act. CCDash emits candidate *events*; all synthesis, ARC dispatch,
  and writeback gates stay upstream in op/ARC/SkillMeat.

---

## 7. Verdict

**Verdict**: `go`
**Confidence**: 0.8

**Rationale**: All three charter `go` criteria are met. (1) The deal-killer is **refuted** — the
`document→session` correlation key already exists as the materialized `entity_links` table with a
3-strategy linkage; the agent-written-AAR→session case rides the two-hop AAR→feature→sessions fallback,
which needs no new ingest (tech leg, 0.82). (2) A **non-duplicative seam is confirmed** — `op story`
sources AARs from CCDash but terminates in a blog draft PR; the AAR→system-improvement loop exists
nowhere, and deterministic surface-flag triage is uniquely CCDash's to own (reuse leg, 0.82). (3)
**Risks are mitigable** with three guards that each have direct in-repo precedent, plus a producer-only
boundary that keeps cost, recursion, and writeback with their upstream owners (risk leg, 0.65). The MVP
is a self-contained Tier 1 slice (~10–13 pts) delivering standalone value with no swarm, no writeback,
no scheduling.

**Recommended next action**: `/plan:plan-feature --tier=1 --charter=docs/project_plans/exploration/ccdash-automated-aar-review/ccdash-automated-aar-review-charter.md`
for the MVP (S1–S4). Full vision (S5–S9) is Tier 3 (~34–45 pts) to be sequenced after MVP flags are
validated as useful/low-false-positive against real AARs.

---

## 8. Citations

- Exploration charter: [ccdash-automated-aar-review-charter.md](ccdash-automated-aar-review-charter.md)
- Proposed ADR: [ccdash-automated-aar-review-proposed-adr.md](ccdash-automated-aar-review-proposed-adr.md)
- Tech leg: [spikes/tech-findings.md](spikes/tech-findings.md) — `entity_links` correlation, flag computability, `agent_queries` integration
- Reuse leg: [spikes/reuse-findings.md](spikes/reuse-findings.md) — AOS seam map, ownership line, do-not-build list
- Risk leg: [spikes/risk-findings.md](spikes/risk-findings.md) — cost/recursion/writeback guards, ADR-006/007 compliance
- Scope leg: [spikes/scope-findings.md](spikes/scope-findings.md) — MVP carve, S1–S9 slices, tier sizing
- H5 anchor: RF run telemetry commit `9594fcc` (Tier 3, ~26 pts; P2 correlation wave ~8 pts)
