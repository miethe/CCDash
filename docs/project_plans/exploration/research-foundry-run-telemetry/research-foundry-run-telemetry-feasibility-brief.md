---
schema_version: 2
doc_type: report
report_category: feasibility
title: "Research Foundry Run Telemetry in CCDash — Feasibility Brief"
status: finalized
created: 2026-07-20
updated: '2026-07-20'
feature_slug: research-foundry-run-telemetry
verdict: conditional
verdict_confidence: 0.82
exploration_charter_ref: 
  docs/project_plans/exploration/research-foundry-run-telemetry/research-foundry-run-telemetry-charter.md
proposed_adr_ref: 
  docs/project_plans/exploration/research-foundry-run-telemetry/research-foundry-run-telemetry-proposed-adr.md
recommended_next_action: "/plan:plan-feature --tier=2"
related_documents:
- docs/project_plans/exploration/research-foundry-run-telemetry/research-foundry-run-telemetry-charter.md
- docs/project_plans/exploration/research-foundry-run-telemetry/rf-transport-handoff-addendum.md
- ../../../../research-foundry/docs/project_plans/design-specs/research_foundry_search_router_spec.md
---

# Research Foundry Run Telemetry in CCDash — Feasibility Brief

<!-- verdict and verdict_confidence are populated; brief is a draft pending human sign-off. -->

---

## 1. Synopsis

Research Foundry (RF) now emits a schema-validated per-run `ccdash_event` (an `execution_event`
carrying provider spend, useful-source rate, duplicate/extraction-failure rates, and latency) so
that the operator can close RF's "evidence-driven provider selection" loop (RF spec §5.2). This
exploration asked whether CCDash should ingest, correlate, and visualize that telemetry as a
first-class **research run** entity. The four investigation legs concluded that the emission is
real and shipped, that no CCDash "run" concept exists to extend, that a new entity + ingest surface
is mechanically tractable within the existing layered architecture, and that a compact 4-panel
analytics slice makes the cost/quality loop legible. The single gating condition is that RF's event
today writes **only to a directory inside RF's own workspace** with zero egress to CCDash — the
transport is defined-but-unwired. Because the operator has authorized cross-project specs, that one
precondition becomes a small **companion RF deliverable** rather than a blocker, converting the
charter's `conditional` into an effective **go** for a contract-first CCDash build.

---

## 2. Investigation Summary

| Leg | Agent | Confidence | Findings | Conclusion |
|-----|-------|-----------|----------|------------|
| tech | research-technical-spike | 0.92 | [tech-spike.md](spikes/tech-spike.md) | RF's `emit_ccdash_event` is real, tested, and shipped (`c3a2545`) but writes YAML only inside RF's own workspace (`ccdash/events/*.yaml`) — zero egress to CCDash. State = `defined_stubbed`. New `POST /api/v1/ingest/rf-events` + `rf_events` table preferred over FS-watch. |
| priorart | codebase-explorer | 0.92 | [priorart-spike.md](spikes/priorart-spike.md) | No CCDash "run" concept exists; sessions/AOS-correlation/planning-board are all session-scoped. Build a new entity/table. Cheapest points: `run_intelligence.py` service, `/api/agent/research-runs` route, new FE surface. |
| risk | backend-architect | 0.75 | [risk-spike.md](spikes/risk-spike.md) | `tractable_with_conditions` (~20 pts). Corrects priorart: AOS added **no** `aos_*_uuid` columns (read-time derivation; RF ids are non-UUID slugs). Link run↔session via `links.py` entity rows keyed by a real UUID `run_id`; apply D-001 dedup from day one; reuse NDJSON/`ingest_cursors` transport, not the FS-watcher coalescing path. |
| value | ux-researcher | 0.78 | [value-spike.md](spikes/value-spike.md) | The §16 event carries run-level aggregates with a provider **list** — no per-provider cost/quality splits — so §16.2 "by provider/domain/extractor" panels are not computable from the event alone. Buildable grain = per-mode + per-run. MVP = 4 panels inside existing `AnalyticsDashboard.tsx`, not a new top-level route. |

---

## 3. Cost Estimate

**Rough estimate**: 20–24 story points, CCDash-side (Tier 2 equivalent). RF-side companion spec adds ~2–3 pts owned by the RF repo.

**H5 anchor**: The risk leg anchors the CCDash-side backend budget at **20 pts**
([risk-spike.md:118-125](spikes/risk-spike.md)), decomposed against the directly comparable
**remote session ingest** work (ADR-008/009/014/015 + `ingest_cursors` v36): two new dual-DDL tables
(~5 pts each, sized to the `ingest_cursors` precedent), an idempotent NDJSON ingest write path
reusing the existing transport (~3 pts), a run↔session entity-link adapter with the D-001 dedup
regression test (~5 pts, the highest-uncertainty slice with no direct precedent), and a
transport-neutral query service + REST route + capability flag (~2 pts).

**CCDash-side vs RF-side split**:
- **CCDash (this repo)**: 20 pts backend (above) + ~2–4 pts for the 4-panel analytics tab inside
  `AnalyticsDashboard.tsx` (value leg: no new primitives, no new route — reuses `MetricCard`,
  `TrendChart`, dense-table patterns, [value-spike.md:37-44](spikes/value-spike.md)). Frontend is
  additive and cheap because the visual language is a 1:1 fit.
- **RF (research-foundry repo, companion deliverable)**: ~2–3 pts to add a best-effort HTTP POST at
  the end of `emit_ccdash_event()` ([tech-spike.md:200-207](spikes/tech-spike.md)), modeled on RF's
  existing `push_status()` "never raise, return bool" pattern; local YAML mirror retained for
  durability/replay.

**Major cost drivers**: dual-DDL table parity (SQLite + Postgres, ADR-006/007 governance);
the run↔session link adapter + D-001 dedup discipline (novel, no precedent); cross-repo transport
coordination (RF companion spec + CCDash contract-first endpoint must agree on the field mapping).

---

## 4. Value Statement

**Primary beneficiaries**: The solo operator running RF search runs on the LAN node, who currently
cannot see where provider spend goes or which search mode yields the best useful-sources-per-dollar.

**Evidence of demand**:
- RF spec §5.2 defines an explicit "evidence-driven provider selection" loop that **cannot close**
  without a receive/analyze/visualize side — RF emits the evidence but nothing consumes it
  ([charter §Hypothesis Context](research-foundry-run-telemetry-charter.md)).
- RF shipped the emission side on `c3a2545` (2026-07-20, the same day this exploration opened),
  confirming this is active, funded, in-flight work — not speculation ([tech-spike.md:30-53](spikes/tech-spike.md)).
- The value leg identifies a single economic north-star (**cost per useful source**) plus a quality
  triad already latent in the event, so the payoff is immediate the moment events flow
  ([value-spike.md:12-13,46-55](spikes/value-spike.md)).

**Counterfactual**: If not built, RF's telemetry accumulates as inert YAML inside RF's own
workspace, the provider-selection loop stays open, and the operator continues choosing search
providers/modes without cost or quality evidence.

---

## 5. Risks & Blast Radius

| Risk | Category | Severity | Mitigation |
|------|----------|---------|------------|
| Run↔session cost rollup reproduces D-001's multi-parent over-count (one session linked to N runs summed without dedup) | technical | H | Apply D-001 Option A (`DISTINCT`/`GROUP BY` before sum) as a hard rule for **any** run-aware rollup, and ship the D-001-shape regression test (two runs sharing one session; assert session tokens counted once) alongside the feature, not deferred ([risk-spike.md:72-85,184](spikes/risk-spike.md)). |
| Correlation-key mismatch: RF `intent_id`/`task_node_id`/`event_id` are non-UUID semantic slugs that cannot join the AOS sidecar-URN graph | technical | M | Link via `backend/db/repositories/links.py` entity rows (`kind=research_run`) keyed by a genuine UUID `run_id`; carry RF's semantic ids as display-only string attributes, never as SQL join keys. Do **not** retrofit RF ids into `aos_correlation.py`'s UUID parser ([risk-spike.md:40-70,182](spikes/risk-spike.md)). |
| Cross-system coupling: RF runs as a separate service (node `:7432`) with an independent deploy lifecycle; may be down/absent | operational | M | Fail-open at both ends: RF POST is best-effort and never blocks a run ([tech-spike.md:200-207](spikes/tech-spike.md)); CCDash registers an `ingest_sources[]` health entry with freshness thresholds and renders explicit absent-state (never `0`/`NaN`) per resilience-by-default ([risk-spike.md:149-176](spikes/risk-spike.md)). Advertise a `research-runs:*` capability string so pre-feature consumers don't hard-fail. |
| Per-provider-split data gap: §16.2 "by provider/domain/extractor" panels are not computable from the event alone | organizational | M | MVP builds only the honest per-mode + per-run grain from the event; per-provider economics is the highest-value deferral, unblocked when RF emits per-provider metric splits or CCDash joins §11.2 `source_cards` ([value-spike.md:16-17,57-64](spikes/value-spike.md)). Do not promise provider-attributed panels in MVP scope. |
| Dual-DDL drift (SQLite vs Postgres) on the two new tables | technical | L | Follow the `ingest_cursors` v36 precedent exactly; governance suite (`test_migration_governance.py`) auto-fails CI on table-set drift ([risk-spike.md:87-114,185](spikes/risk-spike.md)). |

**Blast radius**: Additive-only if the entity-link strategy is followed — two new tables
(`rf_events`/`research_runs`, `run_events`), one repository module, one query service, one REST
namespace, one entity-link kind, one health entry, one capability string. **Zero modification** to
existing `sessions`, `aos_correlation.py`, `analytics.py`, or `planning_sessions.py`
([risk-spike.md:192-201](spikes/risk-spike.md)).

---

## 6. Architectural Implications

**Proposed ADR**: [research-foundry-run-telemetry-proposed-adr.md](research-foundry-run-telemetry-proposed-adr.md)
— (1) transport is a new `POST /api/v1/ingest/rf-events` endpoint backed by a new `rf_events` table
(FS-watch adapter is the no-RF-rework fallback); (2) run↔session correlation uses entity-link rows
keyed by a UUID `run_id`, with RF's semantic ids as display-only attributes.

This fits cleanly into the existing layered architecture. Backend follows the well-worn
router → transport-neutral `agent_queries` service → repository → dual-DDL table path. Ingest reuses
the NDJSON + `ingest_cursors` + dead-letter transport (ADR-008/009/014/015) rather than the
filesystem-watcher sync-coalescing path (which is filesystem-source-scoped and does **not** protect
external HTTP writes — [risk-spike.md:128-147](spikes/risk-spike.md)). The frontend extends
`components/Analytics/AnalyticsDashboard.tsx` with a new `TAB_LABELS` entry rather than adding a
top-level route, matching the emerging embedded-analytics pattern
([value-spike.md:36-44](spikes/value-spike.md)). No structural changes to existing surfaces are
required.

---

## 7. Phased Shape

Contract-first: CCDash builds the receiving contract before real events flow; the RF transport spec
is handed off in parallel so it lands independently on the RF side.

- **Phase A — Contract-first ingest surface + `rf_events` table**: New `POST /api/v1/ingest/rf-events`
  endpoint accepting RF's `ccdash_event` shape near-verbatim (schema is `additionalProperties: true`,
  tolerant of CCDash-side additions); new `rf_events` table (dual DDL, `retry_on_locked`, ADR-007
  direct-count test, column-parity allowlist); reuse workspace-token auth (ADR-008) and the
  idempotent NDJSON/`ingest_cursors`/dead-letter transport; register an `ingest_sources[]` health
  entry and a `research-runs:*` capability string. Store RF ids as opaque string columns; no
  correlation yet.
- **Phase B — Run entity + correlation via `links.py`**: Promote/normalize ingested events into a
  `research_runs` entity (UUID `run_id`, CCDash-minted if RF doesn't supply a UUID4); add a
  `run_events` cursor-paginated child log; add `research_run` as a linkable entity kind and the
  run↔session link adapter. Ship the D-001-shape dedup regression test with any rollup. Add the
  transport-neutral `run_intelligence.py` query service + `/api/agent/research-runs` REST route
  (auto-wires MCP/CLI).
- **Phase C — 4-panel analytics tab**: Add a `research` ("Provider Economics") tab to
  `AnalyticsDashboard.tsx` `TAB_LABELS`: (A) KPI strip incl. cost-per-useful-source north-star;
  (B) cost & quality by mode (the evidence-loop workhorse table); (C) spend + run-volume trend;
  (D) run-level drill table with `EntityLinkButton` to correlated session/intent. All fields
  absent-tolerant. Runtime smoke check required before phase exit (UI-touching phase).
- **RF-side transport spec (parallel companion)**: Hand
  [rf-transport-handoff-addendum.md](rf-transport-handoff-addendum.md) to the research-foundry repo:
  add a best-effort HTTP POST at the end of `emit_ccdash_event()` to CCDash's ingest endpoint,
  fail-open, config-gated, local YAML mirror retained. No RF change needed if the FS-watch fallback
  is chosen instead.

---

## 8. Verdict

**Verdict**: conditional
**Confidence**: 0.82

**Rationale**: All three `go` criteria from the charter are met — the tech leg confirms RF telemetry
is persisted and schema-validated (0.92, exceeds ≥0.7), the priorart leg confirms a new run entity
adds non-duplicative value (0.92), and the risk leg confirms UUID linkage + dual-DDL is tractable
within the layered architecture (0.75, exceeds ≥0.7). The charter's `conditional` branch fires on
exactly one condition: RF's transport is **defined-but-not-yet-wired** — the event lands inside RF's
own workspace with zero egress ([tech-spike.md:60-100](spikes/tech-spike.md)). Because the operator
has authorized cross-project specs, that precondition is satisfiable as a small, additive RF
companion deliverable rather than an external blocker, so CCDash can proceed contract-first
immediately (Phase A does not depend on RF being wired first). This is effectively a **go** for the
CCDash-side build plus a handed-off RF transport spec. The 0.18 confidence gap reflects the
per-provider-split data-contract uncertainty (value leg) and the novel, precedent-free run↔session
link adapter (risk leg) — both bounded and mitigated, neither surface-altering.

**Recommended next action**: `/plan:plan-feature --tier=2 --charter=docs/project_plans/exploration/research-foundry-run-telemetry/research-foundry-run-telemetry-charter.md`
— and hand the RF transport addendum to the research-foundry repo in parallel.

---

## 9. Citations

- Exploration charter: [research-foundry-run-telemetry-charter.md](research-foundry-run-telemetry-charter.md)
- Tech leg SPIKE: [spikes/tech-spike.md](spikes/tech-spike.md) — RF emission real but no egress (`c3a2545`, `telemetry.py:132-258`, `paths.py:114-115`); transport options table; minimal contract.
- Prior-art leg SPIKE: [spikes/priorart-spike.md](spikes/priorart-spike.md) — no run concept exists; cheapest extension points; new-tab mechanics.
- Risk leg SPIKE: [spikes/risk-spike.md](spikes/risk-spike.md) — AOS-column correction (§0); correlation strategy (§1); 20-pt plumbing budget (§2); D-001 aggravation (§1.1); coupling/resilience (§4).
- Value leg SPIKE: [spikes/value-spike.md](spikes/value-spike.md) — per-provider data gap; 4-panel MVP; extend-don't-build surface decision.
- Proposed ADR: [research-foundry-run-telemetry-proposed-adr.md](research-foundry-run-telemetry-proposed-adr.md)
- RF handoff addendum: [rf-transport-handoff-addendum.md](rf-transport-handoff-addendum.md)
- RF Search Router spec: `../../../../research-foundry/docs/project_plans/design-specs/research_foundry_search_router_spec.md` (§11.2 `search_run`, §16 CCDash telemetry, §16.2 panels)
