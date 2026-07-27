---
schema_version: 2
doc_type: exploration_charter
title: "Plan-Execution ↔ Session Correlation & Frontmatter Enrichment — Exploration
  Charter"
status: concluded
created: 2026-07-26
feature_slug: plan-execution-session-correlation
timebox_days: 3
hypothesis: "We believe CCDash should ingest richer plan/workflow frontmatter and
  carve agent sessions against every level of an execution plan (wave→gate→phase→task→AC),
  surfacing per-level performance (validation/fix loops, reviews used, tokens/cost),
  because ~$1,191 of measured spend for a single feature is invisible to retros today
  (feature→session join = 29/14,399) and no sub-feature plan-hierarchy correlation
  exists at all."
deal_killer: "If session forensics cannot be reliably attributed BELOW the feature
  level — i.e. plan-hierarchy→session correlation has no usable signal even after
  the base feature→session join is fixed (gap-analysis Step 0) — then per-level performance
  is unbuildable and the effort collapses to static plan-structure display; abandon
  the correlation scope."
investigation_legs:
- id: schema-currency
  question: What planning-artifact frontmatter schemas exist in this repo's 
    artifact-tracking skill vs their upstream skillmeat-cli source (field-level 
    delta / staleness), and what planning metadata does CCDash's 
    document/feature parser ingest today vs leave on the floor?
  assigned_to: search-specialist
- id: hierarchy-ingestion
  question: Can CCDash's parser + sync + DB model represent the full execution 
    hierarchy (wave→gate→phase→task→AC) extracted from plan files and progress 
    YAMLs? Integration points, data-model shape, reuse of existing 
    features/tasks/sync_import, rough cost.
  assigned_to: spike-writer
- id: correlation-crux
  question: Given the gap-analysis (feature→session join dead), is it feasible 
    to correlate sessions to EACH plan-hierarchy level and derive per-level 
    performance signals (fix loops, reviews used, review counts) from session 
    forensics? Is the signal present in session data, and what must the Step-0 
    base-join fix deliver first?
  assigned_to: research-technical-spike
- id: risk-blast-radius
  question: What is the blast radius of plan-structure ingestion + hierarchical 
    correlation on the sync engine hot path, link derivation, and DB (new 
    tables, migrations, SQLite/Postgres dual-DDL parity)? Confirm or refute the 
    deal-killer; sequence against gap-analysis remediation.
  assigned_to: data-layer-expert
verdict_criteria:
  go:
  - correlation-crux + hierarchy-ingestion legs report confidence >= 0.7 that 
    level-granular correlation and hierarchy ingestion are feasible
  - Deal-killer not triggered (usable session signal exists below feature level)
  - risk-blast-radius leg finds no critical unmitigated risk to the sync hot 
    path or DB parity
  no_go:
  - 'Deal-killer triggered: no usable per-level session signal even after base-join
    fix'
  - correlation-crux leg reports infeasibility with confidence >= 0.8
  conditional:
  - Hierarchy ingestion + schema enrichment feasible, but per-level correlation 
    depends on a named precondition (e.g. gap-analysis Step 0 / Themes 1–2 
    landing first)
verdict: conditional
verdict_rationale: 'All four legs report confidence >=0.70; no hard infeasibility;
  deal-killer refuted/deferred (raw per-level signal ingredients exist at tool-call/log
  granularity, and no data-layer structural blocker). Scope splits: SLICE 1 (hierarchy
  ingestion + frontmatter/schema enrichment) is GO-able now, independent of the dead
  session->feature join (~20-30 pts, reuses feature_phases pattern). SLICE 2 (per-level
  session correlation + performance signals) is DEFERRED, gated on gap-analysis Themes
  1-2 (base-join fix) plus net-new per-level attribution work. Precondition: gap-analysis
  Step 0 -> Theme 1 -> Theme 2.'
output_artifacts: []
related_documents:
- docs/project_plans/reports/feature-retro-linkage-gap-analysis.md
updated: '2026-07-26'
---

# Plan-Execution ↔ Session Correlation & Frontmatter Enrichment — Exploration Charter

## Hypothesis Context

CCDash already ingests session forensics (tokens, cost, tool use, subagent trees) and parses planning-doc frontmatter, but its intelligence stops at the **feature** grain and — per the [feature-retro-linkage-gap-analysis](../../reports/feature-retro-linkage-gap-analysis.md) — the feature→session join is effectively dead (29 links / 14,399 sessions; a probe feature showed $1,191 / 24 sessions / 388M tokens reported as **$0 / 0 / 0**). This exploration asks whether we can go the other direction and *deeper*: pull richer plan/workflow frontmatter, extract the full execution hierarchy (wave→gate→phase→task→AC), and correlate sessions to **every** level — then derive per-level performance (validation/fix loops, reviews used, tokens/cost). The gap-analysis is prior art for the join mechanics and risk; this charter must not re-derive it.

---

## Investigation Legs

### Leg: schema-currency — Frontmatter Schema Audit & Current-Ingestion Map
**Question**: (see frontmatter) **Assigned to**: `search-specialist`
**Expected output**: `docs/project_plans/exploration/plan-execution-session-correlation/spikes/schema-currency-findings.md`
- Inventory frontmatter schemas in `.claude/skills/artifact-tracking/schemas/` + their upstream skillmeat-cli source; flag staleness/field deltas.
- Map what CCDash's document/feature parsers ingest today (frontmatter → DB) vs available-but-unused fields.
- Propose candidate new fields that would strengthen correlation.

### Leg: hierarchy-ingestion — Wave→Gate→Phase→Task→AC Ingestion Feasibility
**Question**: (see frontmatter) **Assigned to**: `spike-writer`
**Expected output**: `docs/project_plans/exploration/plan-execution-session-correlation/spikes/hierarchy-ingestion-findings.md`
- Determine data-model shape; assess reuse of existing `features`/`tasks` tables, `document_linking`, and IntentTree `sync_import`.
- Identify parser/sync integration points; rough story-point estimate with H5 anchor.

### Leg: correlation-crux — Level-Granular Session Correlation & Performance Signals
**Question**: (see frontmatter) **Assigned to**: `research-technical-spike`
**Expected output**: `docs/project_plans/exploration/plan-execution-session-correlation/spikes/correlation-crux-findings.md`
- Assess signal presence: can fix loops / reviews used / validation cycles be derived from session logs, artifacts, file-updates, subagent tree?
- State the dependency on the gap-analysis Step-0 base-join fix. This leg owns the deal-killer.

### Leg: risk-blast-radius — Blast Radius & Deal-Killer Assessment
**Question**: (see frontmatter) **Assigned to**: `data-layer-expert`
**Expected output**: `docs/project_plans/exploration/plan-execution-session-correlation/spikes/risk-blast-radius-findings.md`
- Sync hot-path impact, link-derivation load, new-table migrations, SQLite/Postgres dual-DDL parity (CLAUDE.md invariant), ADR-006/007 constraints.
- Confirm/refute deal-killer; sequence vs gap-analysis Themes 1–2.

---

## Verdict Criteria Narrative

**Go** if hierarchy ingestion and level-granular correlation are both feasible with a usable session signal and no critical unmitigated DB/sync risk. **No-go** if there is no usable per-level session signal even after the base join is fixed. **Conditional** if ingestion + schema enrichment are feasible but per-level correlation must wait on a named precondition (gap-analysis Step 0 / Themes 1–2).

---

## Out of Scope

- Re-deriving the feature→session join mechanics or the G-1…G-11 gap register (owned by the gap-analysis report).
- Cross-repo feature federation (gap-analysis G-5) — noted as a hard constraint, not solved here.
- Building the ingestion/correlation itself. This is pre-commitment exploration only.

---

## Citations / Prior Art
- `docs/project_plans/reports/feature-retro-linkage-gap-analysis.md` (2026-07-26) — the join gap register + remediation themes.
- Memory: `ccdash-feature-session-linkage-dead`, `ccdash-session-telemetry-capture-reality`, `ccdash-aar-review-loop-shipped`.

---

## Notes
- 2026-07-26: Charter scaffolded via `/plan:explore`. Value leg intentionally skipped — desirability established by the gap-analysis ($1,191 invisible spend) + explicit operator intent.
