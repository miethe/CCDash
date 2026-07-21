---
schema_version: 2
doc_type: exploration_charter
title: "Research Foundry Run Telemetry in CCDash — Exploration Charter"
status: concluded
created: 2026-07-20
feature_slug: research-foundry-run-telemetry
timebox_days: 3
hypothesis: "We believe CCDash should ingest, correlate, and visualize Research Foundry
  search-run telemetry as a first-class 'run' entity — linked to existing sessions/AOS-correlation
  via shared UUIDs — because RF now emits execution_event telemetry (RF spec §16)
  whose provider cost/quality/drift evidence loop is currently unreceived and unanalyzable."
deal_killer: "If Research Foundry does not actually persist or emit retrievable search-run
  telemetry that CCDash can consume without RF-side rework, abandon — there is nothing
  to retrieve, analyze, or visualize."
investigation_legs:
- id: tech
  question: What did RF actually ship as its CCDash-telemetry emission mechanism
    (endpoint POST / JSONL sidecar / OTEL / shared DB), and can CCDash consume 
    it through an existing ingest/parse/export seam or does it require a new 
    transport?
  assigned_to: research-technical-spike
- id: priorart
  question: What CCDash surfaces already overlap (AOS correlation indexing 
    676bcca, planning session board, session detail, system_metrics, 
    artifact_intelligence)? Does the existing session/correlation model already 
    represent a 'run', or is a genuinely new entity + tab warranted?
  assigned_to: codebase-explorer
- id: risk
  question: What are the correlation-integrity, dual-DDL (SQLite+PG), volume, 
    and cross-system-coupling risks of a new run entity + UUID linkage — given 
    the deferred D-001 correlation over-count and the RF event's 
    intent_id/task_node_id vs CCDash's aos_*_uuid mismatch?
  assigned_to: backend-architect
- id: value
  question: What is the minimum-lovable visualization slice? Do the RF spec 
    §16.2 panels justify a dedicated new tab, or should telemetry extend an 
    existing analytics surface? Which panels are load-bearing for the evidence 
    loop vs nice-to-have?
  assigned_to: ux-researcher
verdict_criteria:
  go:
  - tech leg confirms RF telemetry is persisted and retrievable by CCDash 
    (confidence >= 0.7)
  - priorart leg confirms a new run entity/tab adds value beyond existing 
    surfaces (not pure duplication)
  - risk leg confirms UUID linkage + dual-DDL is tractable within layered 
    architecture (confidence >= 0.7)
  - Deal-killer condition not triggered
  no_go:
  - Deal-killer condition triggered (no retrievable RF telemetry)
  - priorart leg shows existing AOS-correlation/session model already fully 
    captures search-run telemetry (confidence >= 0.8) — extend, do not build new
  conditional:
  - 'RF telemetry transport is defined-but-not-yet-wired: proceed with a contract-first
    CCDash ingest surface, deferring UI until real events flow'
  - Run entity is warranted but the correlation key (intent_id/task_node_id vs 
    aos_*_uuid) requires an RF-side or IntentTree-side alignment first
verdict: conditional
verdict_rationale: "All three go-criteria met (tech 0.92, priorart 0.92, risk 0.75);
  deal-killer not triggered — RF telemetry is real and persisted (commit c3a2545).
  Sole gap: RF emission is a local-file writeback with zero egress to CCDash (defined_stubbed).
  Precondition — RF→CCDash transport — is now a handed-off companion spec (rf-transport-handoff-addendum.md),
  not a blocker: CCDash Phase A ingest surface is buildable contract-first. Effectively
  go for the ~24pt CCDash-side build via /plan:plan-feature --tier=2."
output_artifacts:
- research-foundry-run-telemetry-feasibility-brief.md
- research-foundry-run-telemetry-proposed-adr.md
- rf-transport-handoff-addendum.md
- spikes/tech-spike.md
- spikes/priorart-spike.md
- spikes/risk-spike.md
- spikes/value-spike.md
related_documents:
- ../../../../../research-foundry/docs/project_plans/design-specs/research_foundry_search_router_spec.md
updated: '2026-07-20'
---

# Research Foundry Run Telemetry in CCDash — Exploration Charter

## Hypothesis Context

The Research Foundry Search Router ADR (§16) defines an `execution_event` telemetry contract and 11 target dashboard panels (provider spend, cost per useful source, useful-source rate by domain, search-mode frequency, latency, extraction-failure rate, duplicate rate, citation coverage, unsupported/conflicted/stale claims, promoted reuse patterns). The operator reports RF "just added CCDash telemetry from runs" — i.e., the emission side is landing. CCDash today has rich session/feature/workflow intelligence and a just-shipped AOS correlation index (676bcca), but no representation of an RF **search run** (§11.2 `search_run`) as a distinct entity, and no surface for provider-quality/cost analytics. Without the receive/analyze/visualize side, the ADR's central "evidence-driven provider selection" loop (§5.2) cannot close.

---

## Investigation Legs

### Leg: tech — Telemetry transport & ingest feasibility

**Question**: What did RF actually ship as its CCDash-telemetry emission mechanism, and can CCDash consume it through an existing seam or does it need new transport?
**Assigned to**: `research-technical-spike`
**Expected output**: `docs/project_plans/exploration/research-foundry-run-telemetry/spikes/tech-spike.md`

- Inspect the RF repo (`../research-foundry/`) for the shipped writeback: `writebacks/ccdash.py`, any HTTP client, JSONL emission, or OTEL export. Determine the actual on-the-wire shape and where it lands.
- Map against CCDash consumption seams: `POST /api/v1/ingest/sessions`, `backend/parsers/`, `backend/services/integrations/telemetry_exporter.py`, `backend/db/sync_engine.py`, AOS correlation indexing (676bcca).
- Answer: is telemetry *retrievable by CCDash today*, or only aspirationally "added"? What is the minimal transport contract?

### Leg: priorart — Existing-surface overlap

**Question**: What already overlaps, and does the existing model already represent a "run"?
**Assigned to**: `codebase-explorer`
**Expected output**: `docs/project_plans/exploration/research-foundry-run-telemetry/spikes/priorart-spike.md`

- Catalog: AOS correlation indexing (aos_run_uuid/session/trace/work), `planning_sessions`/session board, `session_detail`, `system_metrics.py`, `artifact_intelligence.py`, analytics repositories.
- Determine whether an RF search-run maps onto an existing session/correlation row or is a distinct kind requiring its own entity.
- Identify the cheapest extension point vs. net-new build.

### Leg: risk — Correlation integrity, DDL parity, coupling

**Question**: What are the correlation-integrity, dual-DDL, volume, and coupling risks?
**Assigned to**: `backend-architect`
**Expected output**: `docs/project_plans/exploration/research-foundry-run-telemetry/spikes/risk-spike.md`

- The RF event keys on `intent_id`/`task_node_id`/`event_id`; CCDash correlation keys on `aos_*_uuid`. Assess the linkage strategy and whether D-001 (correlation over-count, deferred) is aggravated.
- Any new table needs SQLite + Postgres DDL parity + `retry_on_locked` + direct-count test (ADR-007) + column-parity allowlist. Estimate the plumbing budget.
- Cross-system coupling: RF is a separate service/repo (node `:7432`). Resilience-by-default for optional/absent fields.

### Leg: value — Minimum-lovable visualization slice

**Question**: New tab vs. extend existing analytics? Which §16.2 panels are load-bearing?
**Assigned to**: `ux-researcher`
**Expected output**: `docs/project_plans/exploration/research-foundry-run-telemetry/spikes/value-spike.md`

- Rank the 11 §16.2 panels by evidence-loop value (provider selection improvement) vs. cost to render.
- Decide: dedicated "Research" / "Runs" tab, or a section within an existing analytics/dashboard surface.
- Define the smallest slice that makes provider cost/quality legible to the operator.

---

## Verdict Criteria Narrative

**Go** if: RF telemetry is persisted and CCDash-retrievable (tech ≥0.7), a new run entity/tab adds non-duplicative value (priorart), and UUID linkage + dual-DDL is tractable (risk ≥0.7).
**No-go** if: no retrievable RF telemetry (deal-killer), or the existing AOS-correlation/session model already fully captures search-run telemetry (priorart ≥0.8) — in which case extend, don't build.
**Conditional** if: the transport is defined-but-unwired (→ contract-first ingest, defer UI), or the correlation key needs upstream RF/IntentTree alignment first.

---

## Out of Scope

- Building any RF-side emission (that is RF's deliverable, per RF spec §19 Phase 3).
- Provider-scoring algorithm design (RF owns §5.2 metric computation; CCDash visualizes).
- MeatyWiki / SkillMeat writeback surfaces (RF spec §17–18) — CCDash concern is telemetry only.

---

## Citations / Prior Art

- RF Search Router ADR/spec: `../research-foundry/docs/project_plans/design-specs/research_foundry_search_router_spec.md` (§11.2 search_run, §16 CCDash telemetry, §16.2 panels)
- CCDash AOS correlation indexing: commit `676bcca`
- CCDash transcript orchestration intelligence: commit `beaf964`
- Deferred D-001 correlation over-count (CCDash runtime-deploy remediation)

---

## Notes

- 2026-07-20: Charter scaffolded via `/plan:explore`. Triage: exploration warranted (medium risk, no directly comparable past feature for an RF run entity + tab).
