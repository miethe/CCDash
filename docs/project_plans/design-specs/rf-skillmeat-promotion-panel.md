---
schema_version: 2
doc_type: design_spec
title: "DF-006: Reusable-Patterns-Promoted-to-SkillMeat Panel for Research Foundry Run Telemetry"
description: >
  Deferred design spec for the Research Foundry (RF) run telemetry feature's
  "reusable patterns promoted to SkillMeat" panel gap (PRD §12, DF-006). RF tracks
  its own writebacks to SkillMeat on a distinct entity (`search_run.writebacks`)
  that this feature does not ingest at all — the gap is not a missing field on an
  ingested event, it is an entire un-ingested cross-system entity whose promotion
  requires joining two independent systems' identity spaces. Documents the exact
  unblock condition, the join shape, and the investigation scope for the
  follow-up feature.
status: draft
maturity: idea
created: '2026-07-21'
updated: '2026-07-21'
feature_slug: research-foundry-run-telemetry
prd_ref: docs/project_plans/PRDs/features/research-foundry-run-telemetry-v1.md
problem_statement: >
  The operator cannot see which reusable patterns (SkillMeat tool profiles,
  SkillBOMs) a Research Foundry search run promoted into SkillMeat, because this
  feature ingests only RF's `execution_event` telemetry (§16) — it never ingests
  RF's `search_run.writebacks.skillmeat_candidate_ids` field, which lives on a
  distinct RF entity (`search_run`, §11.2) that CCDash does not yet receive in any
  form, raw or derived.
open_questions:
  - "Does RF plan to emit search_run.writebacks (or just its skillmeat_candidate_ids subset) as part of the same ccdash_event payload this feature already ingests, or as a genuinely separate transport/entity requiring a new ingest route?"
  - "Is search_run.writebacks.ccdash_event_id (RF spec §11.2) guaranteed to match this feature's rf_events.event_id 1:1, or can one search_run write back against zero, one, or multiple execution_events?"
  - "What SkillMeat identity do skillmeat_candidate_ids strings resolve to — a SkillMeat artifact_uuid/artifact_id (joinable against backend/services/artifact_ranking_service.py's identity space) or an RF-local path string (e.g. /tool-profiles/brave_search_v1.yaml, per RF's own worked example) requiring a resolution step before any SkillMeat-side join is possible?"
  - "Does SkillMeat's project registration model even cover research-foundry as a tracked project, i.e. would this feature's artifact-intelligence surfaces (ArtifactIntelligenceQueryService) return any rows at all for RF-sourced artifacts without a prior SkillMeat-side onboarding step?"
explored_alternatives: []
related_documents:
  - docs/project_plans/PRDs/features/research-foundry-run-telemetry-v1.md
  - docs/project_plans/implementation_plans/features/research-foundry-run-telemetry-v1/phase-4-hardening-docs.md
  - research-foundry/docs/project_plans/design-specs/research_foundry_search_router_spec.md
  - .claude/worknotes/skillmeat-artifact-usage-intelligence-exchange-v1/feature-guide.md
tags:
  - research-foundry
  - skillmeat
  - telemetry
  - analytics
  - deferred
  - cross-system
audience: developers
category: design-spec
---

# DF-006: Reusable-Patterns-Promoted-to-SkillMeat Panel for Research Foundry Run Telemetry

## 1. Deferred Item Summary

**Item ID**: DF-006 (PRD §12, row 6 — "Reusable patterns promoted to SkillMeat panel")
**Parent feature**: `research-foundry-run-telemetry-v1` (Tier 3, 26 pts)
**Corresponds to**: Research Foundry (RF) spec §16.2 dashboard panel #11 ("promoted reuse
patterns")
**Current status**: Deferred (PRD §7 "Out of Scope" — "explicitly out of the exploration
charter's scope"; locked at PRD authoring time, 2026-07-21)

Research Foundry's search-router spec (§11.2) defines a `search_run` entity, distinct from
the `execution_event` telemetry this feature ingests (§16). `search_run` carries a
`writebacks` block:

```yaml
search_run:
  run_id: string
  created_at: datetime
  completed_at: datetime|null
  request: search_request
  provider_chain: [...]
  metrics: {...}
  writebacks:
    ccdash_event_id: string|null
    meatywiki_page_ids: [string]
    skillmeat_candidate_ids: [string]
```

`skillmeat_candidate_ids` is RF's own record of which reusable artifacts (RF's worked
example in its spec shows tool-profile and SkillBOM paths, e.g.
`/tool-profiles/brave_search_v1.yaml`, `/skillboms/skill_source_discovery_v1.yaml`) a given
search run promoted or recommended for promotion into SkillMeat. This is the data the
"promoted reuse patterns" panel (§16.2 panel #11) would visualize.

This feature's `rf_events`/`research_runs` tables (Phases 1–2) are derived exclusively from
RF's `execution_event` payload — they do not carry `search_run.writebacks` in any column,
raw or derived, because `search_run` is a separate RF entity this feature never ingests.
There is no partial data to extend here; the gap is the absence of an entire entity, not a
missing field on data already flowing through the pipe (contrast DF-001–DF-003, which need
a join against an already-adjacent RF entity, `source_card`).

## 2. Why It Is Deferred

### 2.1 Explicitly Out of the Exploration Charter's Scope

Unlike DF-001–DF-004 (payload-shape gaps discovered during PRD authoring by direct
inspection of the ingested event), DF-006 was named out of scope in the PRD's "Out of
Scope" section under its own heading: **"MeatyWiki/SkillMeat writebacks"** — RF's own
writeback targets are "not ingested or surfaced by this feature," full stop. The
exploration charter that scoped this Tier-3 feature bounded it to RF's `execution_event`
telemetry and the resulting "Provider Economics" analytics tab; cross-system promotion
tracking into SkillMeat was never in scope to begin with, not discovered as a limitation
mid-design.

### 2.2 Genuinely Cross-System, Not a Same-System Join

DF-001–DF-004's unblock paths stay entirely inside RF's telemetry surface (a future
`ccdash_event` schema addition, or ingesting RF's `source_card` entity). DF-006's unblock
requires joining **two independent systems' identity spaces**: RF's
`skillmeat_candidate_ids` strings against SkillMeat's own artifact identity, as already
exposed on the CCDash side by
`backend/application/services/agent_queries/artifact_intelligence.py`
(`ArtifactIntelligenceQueryService`) and the underlying
`backend/services/artifact_ranking_service.py` / `artifact_recommendation_service.py`. That
join only produces meaningful output if RF's candidate-id strings resolve to the same
artifact identity CCDash's SkillMeat-integration surfaces already understand — an open
question (see frontmatter), not a confirmed fact.

### 2.3 Depends on an Un-Landed RF-Side Writeback

RF's own spec (§17 module layout) lists `/writebacks/skillmeat.py` as a planned module
alongside `/writebacks/ccdash.py` (the transport this feature's Phase 1 ingest endpoint
receives from) and `/writebacks/meatywiki.py`. As of this PRD's authoring, only the
`ccdash.py` writeback path is confirmed landing (this feature's entire reason to exist);
whether `skillmeat.py` is implemented, and whether `search_run.writebacks` is emitted to
CCDash at all (vs. staying RF-internal bookkeeping), is unconfirmed.

### 2.4 Phase Scope

Phase 4 of this feature is hardening + docs + deferred-item specs, not new ingest/entity
work. Per the PRD's Out of Scope section, SkillMeat writeback tracking is a follow-up
feature's responsibility, not this one's.

## 3. Unblock Condition

**Promote this item (author an implementation plan; change `status: draft` →
`status: active` or equivalent) when all of the following become true:**

1. **RF emits `search_run.writebacks` (or at minimum `skillmeat_candidate_ids`) to
   CCDash.** Either as an addition to the existing `ccdash_event` payload this feature's
   `/api/v1/ingest/rf-events` endpoint already receives (cheapest — reuses the existing
   transport, `rf_events` gains new nullable columns per the standard "unknown == null"
   convention), or as a genuinely new ingest route/entity if RF decides `search_run` needs
   its own transport. **The precise unblock signal is the appearance of a populated
   `writebacks.skillmeat_candidate_ids` field reaching CCDash by whichever transport RF
   chooses.**

2. **`search_run.writebacks.ccdash_event_id` is confirmed as the join key back to this
   feature's `rf_events.event_id`.** This is the field RF's own spec designates for tying a
   `search_run`'s writebacks back to the `execution_event` this feature already persists —
   it is the natural correlation key and should be used rather than any attempt to
   correlate via `run_id` (RF's `run_id` is a non-UUID semantic slug per this feature's own
   D2 decision; `research_runs.run_id` is a CCDash-minted UUID and would need the same
   `rf_run_id` display-column precedent this feature already established).

3. **SkillMeat candidate-id resolution is confirmed.** Whether `skillmeat_candidate_ids`
   strings are directly joinable against `ArtifactIntelligenceQueryService`'s existing
   artifact identity (`artifact_uuid`/`artifact_id`), or require an intermediate resolution
   step (e.g. resolving an RF-local path string like `/tool-profiles/brave_search_v1.yaml`
   to a SkillMeat artifact identity via the same `ArtifactIdentityMapper` pattern this
   feature's sibling exchange already uses for CCDash's own artifacts).

**Trigger signal**: RF's `schemas/ccdash_event.schema.yaml` (or a new schema file) gains a
populated `writebacks`/`skillmeat_candidate_ids` field that reaches CCDash, and a follow-up
exploration confirms the candidate-id resolution question above.

**Relative cost if chosen**: Medium-High. At minimum: new nullable columns (or a new
entity/table) for `search_run.writebacks`, a correlation join against `rf_events.event_id`,
a resolution step against SkillMeat artifact identity, a new query-service method (likely
`run_intelligence.py` or a new `skillmeat_promotion.py` sibling), a new panel on the
Provider Economics tab (or a distinct analytics surface, since this crosses into
`skillmeat-artifact-usage-intelligence-exchange-v1`'s domain), and an explicit resilience
contract for candidate ids that never resolve (SkillMeat has no matching artifact, or the
artifact was later deleted/renamed).

## 4. Investigation Scope If Promoted

Before implementation begins:

### 4.1 Confirm the RF-Side Emission Shape

- Obtain RF's updated schema (or transport spec) for however `search_run.writebacks`
  reaches CCDash, and confirm the exact field names, nullability, and cardinality of
  `skillmeat_candidate_ids` (a list of strings per RF spec §11.2 — confirm this stays a
  flat list of identifiers, not a richer object, in whatever CCDash actually receives).
- Confirm whether `writebacks.ccdash_event_id` is populated for every `search_run`, or only
  for runs where RF's writeback actually fired (i.e. whether `null` is a normal, frequent
  state that CCDash's join must handle gracefully — "unknown == null, never a fabricated
  default" per this repo's established convention).

### 4.2 Resolve the SkillMeat Identity Question

- Inspect `backend/services/integrations/skillmeat_client.py` and
  `ArtifactIdentityMapper` (per the `skillmeat-artifact-usage-intelligence-exchange-v1`
  feature guide) to determine whether an RF-sourced candidate-id string can be resolved
  through the same identity-mapping pattern already used for CCDash's own artifacts, or
  whether RF and SkillMeat need a new shared identifier convention first.
- If RF's candidate ids are path strings (per RF's own worked example) rather than
  SkillMeat UUIDs, determine whether SkillMeat's API can resolve a path string to an
  artifact identity, or whether this join is not reliably possible without an RF-side or
  SkillMeat-side schema change.

### 4.3 Design the Ingest/Correlation Path

- Decide whether `search_run.writebacks` piggybacks on the existing `ccdash_event`
  payload/route (cheapest, reuses `rf_events` idempotency-by-`event_id` contract) or needs
  a new dual-DDL table and ingest route (if RF treats `search_run` as a fully separate
  transport).
- If a new table is needed, follow the `rf_events` v1 precedent (Phase 1 of this feature)
  for dual SQLite+Postgres DDL, ordered-column-list parity discipline, and idempotent
  insert-by-primary-key semantics.
- Apply the same D-001 dedup discipline (PRD decision D5) if any promotion count or
  candidate list is rolled up across multiple runs or sessions.

### 4.4 Panel / Surface Design

- Decide whether the promoted-patterns view belongs on the Provider Economics tab
  (`components/Analytics/AnalyticsDashboard.tsx`, this feature's existing surface) or as a
  new panel inside the SkillMeat artifact-intelligence surfaces (Analytics rankings,
  Workflow Effectiveness artifact contribution, Execution Workbench recommendations — per
  `skillmeat-artifact-usage-intelligence-exchange-v1`'s existing UI footprint) since the
  data genuinely straddles both features' domains.
- Confirm resilience: a `search_run` with a non-empty `skillmeat_candidate_ids` list whose
  ids never resolve to a known SkillMeat artifact renders an explicit "unresolved
  candidate" state, never a silently dropped row or a fabricated artifact name.

### 4.5 Relevant File Anchors

| Surface | Location |
|---------|----------|
| RF `search_run` entity + `writebacks` shape | `research-foundry/docs/project_plans/design-specs/research_foundry_search_router_spec.md` §11.2 |
| RF planned SkillMeat writeback module | `research-foundry/docs/project_plans/design-specs/research_foundry_search_router_spec.md` §17 (`/writebacks/skillmeat.py`, not yet confirmed implemented) |
| CCDash ingest route (this feature) | `backend/routers/ingest.py` (`POST /api/v1/ingest/rf-events`) |
| CCDash raw event table (this feature) | `backend/db/repositories/rf_events.py` (`RF_EVENTS_COLUMNS`) |
| CCDash run rollup + query service (this feature) | `backend/application/services/agent_queries/run_intelligence.py` |
| SkillMeat artifact identity mapping | `backend/services/integrations/skillmeat_client.py` (`ArtifactIdentityMapper`) |
| SkillMeat artifact-intelligence query service | `backend/application/services/agent_queries/artifact_intelligence.py` (`ArtifactIntelligenceQueryService`) |
| SkillMeat ranking/recommendation services | `backend/services/artifact_ranking_service.py`, `backend/services/artifact_recommendation_service.py` |
| SkillMeat exchange feature guide (sibling feature) | `.claude/worknotes/skillmeat-artifact-usage-intelligence-exchange-v1/feature-guide.md` |
| D-001 dedup precedent | `docs/project_plans/design-specs/f-w6-001-correlation-overcounting.md` |

## 5. Acceptance Criteria (Placeholder — for use when promoted)

```yaml
AC-DF006-1:
  description: >
    A research_run's promoted-to-SkillMeat candidate list (search_run.writebacks.
    skillmeat_candidate_ids) is queryable against this feature's run entity, joined via
    writebacks.ccdash_event_id -> rf_events.event_id.
  verified_by:
    - backend/tests/test_run_intelligence.py  # new: skillmeat writeback join test
    - Runtime smoke: promoted-patterns panel renders with seeded fixtures

AC-DF006-2:
  description: >
    Every candidate id resolves against SkillMeat's existing artifact-intelligence
    identity space (ArtifactIntelligenceQueryService) or renders an explicit "unresolved"
    state -- never a silently dropped row or a fabricated artifact name.
  verified_by:
    - backend/tests/test_artifact_intelligence_phase6_contracts.py  # extended: RF-sourced candidate resolution
    - Runtime smoke: seeded fixture with an intentionally unresolvable candidate id

AC-DF006-3:
  description: >
    No run-or-session promotion count double-counts across a rollup that spans multiple
    search_run rows correlated to the same execution_event/session (D-001 Option A dedup
    discipline applied).
  verified_by:
    - backend/tests/test_run_intelligence.py  # D-001-shape regression test, promotion-count variant
```

---

*Deferred under `research-foundry-run-telemetry-v1`, Phase 4, Task T4-006. See PRD §12
"Deferred Items" table, row 6, and PRD §7 "Out of Scope" ("MeatyWiki/SkillMeat writebacks")
for the original deferral record.*
