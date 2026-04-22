---
schema_version: 2
doc_type: implementation_plan
status: in-progress
created: 2026-04-20
updated: '2026-04-21'
feature_slug: ccdash-planning-reskin-v2
feature_version: v2
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-planning-reskin-v2.md
plan_ref: null
scope: Pixel-faithful reskin of /planning routes with design token system, UI primitive
  extraction, new surfaces (metrics, triage, live agent roster, graph enhancements),
  feature detail drawer interactions (SPIKEs, OQ resolution, exec buttons), and OQ
  write-back backend endpoint.
effort_estimate: 65-75 story points
architecture_summary: Phase 0 extracts OKLCH tokens and implements primitives; Phases
  1-4 reskin shell/home/graph/triage/agent-roster; Phases 5-6 implement feature detail
  drawer enhancements and dependency DAG; Phase 7 adds OQ write-back backend; Phases
  8-9 address a11y/perf/testing; Phase 10 handles documentation finalization. Total
  10 phases, ~8-10 weeks.
related_documents:
- docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2-interaction-performance-addendum-v1.md
- docs/project_plans/designs/ccdash-planning/README.md
- docs/project_plans/designs/ccdash-planning/project/Planning Deck.html
- docs/project_plans/implementation_plans/enhancements/ccdash-planning-control-plane-v1.md
- docs/project_plans/PRDs/enhancements/ccdash-planning-control-plane-v1.md
references:
  user_docs: []
  context: []
  specs:
  - docs/project_plans/designs/ccdash-planning/project/app/data.jsx
  - docs/project_plans/designs/ccdash-planning/project/app/app.jsx
  - docs/project_plans/designs/ccdash-planning/project/app/graph.jsx
  - docs/project_plans/designs/ccdash-planning/project/app/feature_detail.jsx
  - docs/project_plans/designs/ccdash-planning/project/app/triage.jsx
  - docs/project_plans/designs/ccdash-planning/project/app/primitives.jsx
spike_ref: null
adr_refs: []
deferred_items_spec_refs:
  - docs/project_plans/design-specs/live-agent-sse-streaming-v1.md
  - docs/project_plans/design-specs/spike-execution-wiring-v1.md
  - docs/project_plans/design-specs/oq-frontmatter-writeback-v1.md
  - docs/project_plans/design-specs/bundled-fonts-offline-v1.md
  - docs/project_plans/design-specs/spec-creation-workflow-v1.md
  - docs/project_plans/design-specs/planning-primitives-extraction-v1.md
  - docs/project_plans/design-specs/planning-collab-threads-v1.md
  - docs/project_plans/design-specs/planning-lightmode-tokens-v1.md
  - docs/project_plans/design-specs/planning-graph-virtualization-v1.md
findings_doc_ref: null
changelog_ref: null
changelog_required: true
test_plan_ref: null
plan_structure: unified
progress_init: auto
owner: platform-engineering
contributors: []
priority: high
risk_level: high
category: enhancements
tags:
- implementation
- planning
- ui
- reskin
- design-handoff
- enhancements
- phases
milestone: null
commit_refs: []
pr_refs: []
files_affected: []
---

# Implementation Plan: CCDash Planning Reskin v2

**Plan ID**: `IMPL-2026-04-20-ccdash-planning-reskin-v2`  
**Date**: 2026-04-20  
**Author**: Implementation Planner (Sonnet 4.5)  
**Related Documents**:
- **PRD**: `docs/project_plans/PRDs/enhancements/ccdash-planning-reskin-v2.md`
- **Prior Wave**: `docs/project_plans/implementation_plans/enhancements/ccdash-planning-control-plane-v1.md` (completed; do NOT re-plan)
- **Design Handoff**: `docs/project_plans/designs/ccdash-planning/project/Planning Deck.html`

**Complexity**: Large (L)  
**Total Estimated Effort**: 65-75 story points  
**Target Timeline**: 8-10 weeks across 10 phases

---

## Executive Summary

CCDash Planning Control Plane v1 (completed) delivered a functional planning surface with graph, feature drill-down, phase operations, and launch preparation. The Claude Design handoff ("Planning Deck") provides a pixel-precise reference for a significantly richer visual and interaction system that v1 did not attempt. This plan authorizes a **reskin + enhancements wave** that includes:

1. **Design tokenization** — extract OKLCH tokens to `planning-tokens.css` and Tailwind config; implement all base primitives (StatusPill, ArtifactChip, Dot, etc.).
2. **Shell + home reskin** — apply new typography (Geist/Mono/Fraunces), hero header with corpus stats, 6-tile metrics strip, 8-artifact composition chip row, layout frame.
3. **Enhanced surfaces** — triage inbox (filterable tabs), live agent roster (two-up layout), planning graph totals lane (effort + tokens + model-identity bar).
4. **Feature detail drawer enhancements** — lineage strip, SPIKEs section with exec buttons, OQ inline resolution, model legend, dependency DAG SVG, per-batch/task exec buttons, exec toast.
5. **Backend extension** — NEW `PATCH /api/planning/features/:id/open-questions/:oq_id` endpoint for OQ write-back; verify `spikes[]` and `openQuestions[]` in planning payload (resolve OQ-01); add per-feature `tokenUsageByModel` aggregation on planning/feature forensics payload sourced from existing session↔feature correlation (resolve OQ-02; replaces former DEFER-05).
6. **A11y + perf + testing** — keyboard navigation, ARIA roles, color-only fallback text, performance budgets, Vitest coverage.
7. **Documentation finalization** — CHANGELOG `[Unreleased]` entry, README updates, design specs for deferred items (DEFER-01 through DEFER-10).

**Key outcomes:**
- `/planning` route reaches visual parity with design handoff (≥90% per surface).
- All 11 planning surfaces (shell, home, graph, triage, roster, feature detail, DAG, legend, exec toast) implemented.
- Operators gain triage, OQ resolution, SPIKE management, and token/effort telemetry without leaving planning.
- No planning-only UI duplications remain; reuse `/board` and `/plans` components where possible.

---

## Implementation Strategy

### Architecture Sequence

Following the design handoff structure and CCDash layered architecture:

1. **Phase 0** — Design tokens + primitives (frontend foundation, non-blocking backend work)
2. **Phases 1–4** — Frontend reskin (shell, home, graph, triage/roster)
3. **Phases 5–6** — Feature detail drawer (interactions, DAG, exec buttons)
4. **Phase 7** — Backend OQ write-back extension
5. **Phases 8–9** — A11y, performance, testing
6. **Phase 10** — Documentation finalization

### Parallel Work Opportunities

- **Phase 0 and Phase 7 can run in parallel** — token extraction does not depend on backend changes
- **Phases 1–4 (frontend surfaces) can proceed in parallel** once Phase 0 is complete, using mocked API contracts
- **Phase 8–9 testing** can overlap with Phases 5–6 implementation if smoke tests are kept isolated
- **Phase 10 documentation** can begin once all phases are feature-complete (documentation does not block feature gate)

### Critical Path

1. Phase 0 → Phase 1–4 (sequential: tokens required before home/graph/triage rendering)
2. Phases 1–4 → Phase 5–6 (sequential: detail drawer relies on graph row selection)
3. Phase 7 (backend) can occur in parallel with Phases 5–6 (decoupled from UI)
4. Phases 8–9 (testing/a11y) → Phase 10 (docs) → shipping gate

**Critical-path total**: ~6–7 weeks for Phases 0–9; Phase 10 is async and can overlap with final QA.

### Phase Summary

Canonical orchestration table. Keep synced with detailed phase breakdowns below.

| Phase | Title | Estimate | Target Subagent(s) | Model(s) | Notes |
|-------|-------|----------|--------------------|----------|-------|
| 0 | Design tokenization & primitive inventory | 8 pts | ui-designer, ui-engineer-enhanced | sonnet | OKLCH → CSS/Tailwind, primitives, audit |
| 1 | Shell reskin & top bar | 6 pts | ui-engineer-enhanced, frontend-developer | sonnet | App rail, breadcrumb, live-status pill, fonts |
| 2 | Planning home: metrics & artifact chips | 5 pts | ui-engineer-enhanced, frontend-developer | sonnet | Hero header, 6 tiles, 8 chips, corpus stats |
| 3 | Triage inbox & live agent roster | 7 pts | ui-engineer-enhanced, frontend-developer | sonnet | Filterable tabs, roster rows, two-up layout, polling |
| 4 | Planning graph reskin & enhancements | 8 pts | ui-engineer-enhanced, react-performance-optimizer | sonnet | Lane headers, DocChips, PhaseStack, TotalsCell, edges, filter legend |
| 5 | Feature detail drawer — header + lineage | 5 pts | ui-engineer-enhanced, frontend-developer | sonnet | Mismatch pill, raw↔effective, lineage strip, collapsible sections |
| 6 | Feature detail drawer — SPIKEs, OQ, DAG, exec | 10 pts | ui-engineer-enhanced, frontend-developer | sonnet | SPIKE tiles, OQ inline editor, DAG SVG, batch/task exec buttons, toast |
| 7 | Backend OQ write-back endpoint + token-usage-by-model aggregation | 6 pts | python-backend-engineer, backend-architect | sonnet | PATCH endpoint, service method, schema validation, OTEL; per-feature tokenUsageByModel sourced from FeatureForensicsQueryService linked sessions |
| 8 | A11y hardening & performance tuning | 6 pts | web-accessibility-checker, react-performance-optimizer | sonnet | Keyboard nav, ARIA roles, font perf, graph render budgets, perf tests |
| 9 | Testing: unit, integration, component | 8 pts | frontend-developer, testing specialist | sonnet | Vitest coverage, component tests, OQ write-back integration tests |
| 10 | Documentation finalization | 4 pts | changelog-generator, documentation-writer, ai-artifacts-engineer | haiku (sonnet for skill updates) | CHANGELOG, README, context files, design specs for deferred items |
| **Total** | — | **73 pts** | — | — | — |

**Follow-Up Addendum**: Phases 11–17 (34–40 story points) cover interaction refinements, modal navigation, metric wiring, side-panel enhancements, and roster detail interactions. See `docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2-interaction-performance-addendum-v1.md`.

---

## Deferred Items & In-Flight Findings Policy

### Deferred Items Triage Table

| Item ID | Category | Reason Deferred | Trigger for Promotion | Target Spec Path |
|---------|----------|-----------------|-----------------------|-----------------|
| DEFER-01 | infra | SSE streaming for live agent roster updates | Streaming infrastructure stable | docs/project_plans/design-specs/live-agent-sse-streaming-v1.md |
| DEFER-02 | feature | Actual SPIKE/phase/batch/task execution dispatch | Execution connector roadmap settled | docs/project_plans/design-specs/spike-execution-wiring-v1.md |
| DEFER-03 | backend | OQ frontmatter write-through to filesystem | File-system mutation design doc | docs/project_plans/design-specs/oq-frontmatter-writeback-v1.md |
| DEFER-04 | ops | Bundled font assets for offline deployment | Offline requirement confirmed | docs/project_plans/design-specs/bundled-fonts-offline-v1.md |
| DEFER-06 | feature | "New spec" creation flow UI | Creation workflow PRD | docs/project_plans/design-specs/spec-creation-workflow-v1.md |
| DEFER-07 | engineering | @miethe/ui extraction of v2 Planning primitives | Post-2-week stability window | docs/project_plans/design-specs/planning-primitives-extraction-v1.md |
| DEFER-08 | feature | Collab/comment threads on planning artifacts | Auth/tenancy work | docs/project_plans/design-specs/planning-collab-threads-v1.md |
| DEFER-09 | design | Light-mode variant of planning token system | Design + testing investment | docs/project_plans/design-specs/planning-lightmode-tokens-v1.md |
| DEFER-10 | perf | Planning graph virtualization for >200 features | Project scale exceeds threshold | docs/project_plans/design-specs/planning-graph-virtualization-v1.md |

**Scope change — 2026-04-20:** DEFER-05 (session-linked actual token counts) was promoted into v2 scope. The feature↔session correlation already exists in `FeatureForensicsQueryService` (`backend/application/services/agent_queries/feature_forensics.py:266,324`); exposing per-feature + per-model actuals is a thin aggregation over existing data. Phase 7 now carries that work (see T7-004). OQ-02 resolved accordingly.

**N/A — no additional deferred items identified during planning.**

### In-Flight Findings

Lazy-creation rule: Findings doc created on **first real finding only**. Path: `.claude/findings/ccdash-planning-reskin-v2-findings.md`.

---

## Phase Breakdown

### Phase 0: Design Tokenization & Primitive Inventory

**Duration**: 3–4 days  
**Dependencies**: None (parallel to Phase 7)  
**Entry Criteria**: PRD approved, design handoff available  
**Exit Criteria**: All tokens mapped, all primitives implemented and tested, backend payload audited  
**Assigned Subagent(s)**: ui-designer, ui-engineer-enhanced

#### Objectives

1. Extract OKLCH tokens from handoff to `planning-tokens.css` and Tailwind config.
2. Implement all base primitive components in `components/Planning/primitives/`.
3. Audit backend `PlanningQueryService` for `spikes[]`, `openQuestions[]`, and artifact array completeness (resolve OQ-01).
4. Audit backend session-forensics token aggregation for per-feature totals AND per-model breakdown (opus/sonnet/haiku/other) (resolve OQ-02). Per-feature `total_tokens` already exists on `FeatureForensicsDTO` (`feature_forensics.py:336`) and per-session `{model, total_tokens}` is on each `SessionRef` (`feature_forensics.py:68-75`); confirm a per-model aggregation is exposed or scope it for Phase 7 (T7-004).
5. Set up typography (Geist/Mono/Fraunces) via Google Fonts CDN.

#### Tasks

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|-------|--------------|
| T0-001 | Token extraction and Tailwind config | Extract OKLCH values from Planning Deck handoff (surface tokens bg-0–bg-4, line-1/2, ink-0–4, artifact colors spec/spk/prd/plan/prog/ctx/trk/rep, semantic colors ok/warn/err/info/mag, model colors opus/sonnet/haiku) into `planning-tokens.css` and `tailwind.config.js`. Add CSS fallbacks for unsupported browsers. | `planning-tokens.css` created with all token definitions; Tailwind config extended with arbitrary color values; fallback conversion verified in target Chromium version | 2 pts | ui-designer | sonnet | None |
| T0-002 | Base primitive components | Implement React components in `components/Planning/primitives/`: Panel, Tile, Chip, Btn, BtnGhost, BtnPrimary, Dot, StatusPill (11 status values), ArtifactChip (8 types), MetricTile, SectionHeader, Spark, ExecBtn. Reference `primitives.jsx` from handoff. | All primitives render correctly in all states; StatusPill covers idea/shaping/ready/draft/approved/in-progress/blocked/completed/superseded/future/deprecated; each primitive has storybook story or documented usage | 3 pts | ui-engineer-enhanced | sonnet | T0-001 |
| T0-003 | Typography setup | Load Geist (sans), JetBrains Mono (mono), and Fraunces (serif) via Google Fonts CDN in planning route; apply via CSS custom properties (`--sans`, `--mono`, `--serif`); fall back to system fonts; measure font load impact and confirm non-blocking swap strategy | Fonts load with `display: swap`; h1/h2 render in Fraunces italic; body text uses Geist; preconnect links added; paint timing <50ms impact | 1 pt | ui-engineer-enhanced | sonnet | T0-001 |
| T0-004 | Backend payload audit (OQ-01) | Inspect `backend/application/services/agent_queries/planning_query_service.py` (or equivalent) to confirm feature payloads include `spikes[]`, `openQuestions[]`, artifact arrays per type, and mismatch/stale/readyToPromote flags. If missing, add them. | Feature payload structure documented; `spikes[]` and `openQuestions[]` present in sample payload; test coverage added if new fields added | 1.5 pts | python-backend-engineer, ui-engineer-enhanced | sonnet | None |
| T0-005 | Density modes (localStorage) | Implement session-local toggle for comfortable (row-h 44px, gap 16px) and compact (row-h 34px, gap 10px) density modes; store in localStorage `planning_density_preference` | User can toggle density; preference persists across page reloads; all planning surfaces respect density setting | 0.5 pts | frontend-developer | sonnet | T0-002 |
| T0-006 | Session-forensics token aggregation audit (OQ-02) | Inspect `backend/application/services/agent_queries/feature_forensics.py` and `planning.py` to confirm (a) per-feature `total_tokens` is exposed on planning payload (already present on `FeatureForensicsDTO.total_tokens`), and (b) per-model breakdown keyed by `modelFamily` (opus/sonnet/haiku/other) is present OR scoped to T7-004 as the extension task. Document feature↔session correlation path (`feature_forensics.py:266` + links repo) and model-identity derivation path (`backend/model_identity.py:29`). | Audit notes recorded in Phase 0 worknote; per-feature total_tokens confirmed on payload; per-model breakdown either confirmed OR T7-004 added with concrete DTO field name (`tokenUsageByModel`) | 0.5 pts | python-backend-engineer | sonnet | None |

**Phase 0 Quality Gates:**
- [ ] All OKLCH tokens defined in `planning-tokens.css` with browser-compatible fallbacks
- [ ] All primitives implemented and render correctly in all states
- [ ] Storybook stories or documented usage for each primitive
- [ ] Typography loads non-blocking with correct fallbacks
- [ ] Backend payload includes `spikes[]`, `openQuestions[]`, and artifact arrays (OQ-01 resolved)
- [ ] Session-forensics token aggregation audited (OQ-02 resolved): per-feature total_tokens confirmed; per-model breakdown confirmed on payload OR scoped to T7-004
- [ ] Density toggle works and persists

---

### Phase 1: Shell Reskin & Top Bar

**Duration**: 2–3 days  
**Dependencies**: Phase 0 complete  
**Entry Criteria**: Tokens and primitives available  
**Exit Criteria**: App rail, top bar, shell layout all reskinned per handoff  
**Assigned Subagent(s)**: ui-engineer-enhanced, frontend-developer

#### Objectives

1. Reskin the app rail (active Planning state, brand color ring).
2. Implement top bar with breadcrumb, live-agent status pill, search button, "New spec" CTA.
3. Update main canvas layout (max-width, padding, scroll).

#### Tasks

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|-------|--------------|
| T1-001 | App rail reskin | Reskin existing app rail with Planning icon/label active state using brand color ring highlight (matches handoff design). Confirm nav routing unchanged. | App rail renders with active Planning state; icon and label both highlighted; nav routing preserved; responsive behavior at <1280px | 2 pts | ui-engineer-enhanced | sonnet | T0-002 |
| T1-002 | Top bar implementation | Build top bar with: breadcrumb (`CCDash / CCDash · Planning / Planning Deck`), live-agent status pill (running + thinking count, live/idle toggle indicator), global search button (⌘K), "New spec" primary CTA (stub — shows toast for v2). Use existing live-agent context. | Top bar renders with all elements; breadcrumb trails correctly; live counts update from context; search button functional; "New spec" shows toast; layout responsive | 2.5 pts | ui-engineer-enhanced, frontend-developer | sonnet | T0-002 |
| T1-003 | Main canvas layout | Update planning route canvas to max-width 1680px, padding 22px (top/bottom) 28px (left/right); ensure scroll-independent from rail; confirm Tailwind classes applied correctly | Canvas renders with correct max-width and padding; content scrolls independently from rail; responsive behavior verified | 1.5 pts | frontend-developer | sonnet | T1-001, T1-002 |

**Phase 1 Quality Gates:**
- [ ] App rail active state matches handoff design
- [ ] Top bar complete with all elements (breadcrumb, live counts, search, CTA)
- [ ] Main canvas layout correct (max-width, padding, scroll)
- [ ] Responsive behavior verified (≥1280px breakpoint)

---

### Phase 2: Planning Home — Metrics & Artifact Chips

**Duration**: 2 days  
**Dependencies**: Phase 1 complete  
**Entry Criteria**: Top bar and shell layout complete  
**Exit Criteria**: Hero header, metrics strip, artifact chips all rendering with correct data  
**Assigned Subagent(s)**: ui-engineer-enhanced, frontend-developer

#### Objectives

1. Implement hero header with corpus stats and spark chart.
2. Build 6-tile metrics strip (total, active, blocked, stale, mismatches, completed).
3. Build 8-artifact composition chip row (clickable, navigates to `/planning/artifacts/:type`).

#### Tasks

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|-------|--------------|
| T2-001 | Hero header with corpus stats | Render serif italic h1 "The Planning Deck.", subtitle text, and right-side corpus stats (date, ctx/phase count, spark chart, tokens-saved %). Pull data from `GET /api/planning/summary` or compute client-side from planning payload. | h1 renders in Fraunces italic; corpus stats visible (date, counts, spark); spark chart animated on load; tokens-saved % computed correctly; all text readable at 1x zoom | 2 pts | ui-engineer-enhanced, frontend-developer | sonnet | T1-003 |
| T2-002 | Metrics strip (6 tiles) | Render 6 tiles in responsive grid: Features (total count), Active (plan color), Blocked (error color), Stale (warn color), Mismatches (mag color), Completed (ok color). Pull counts from planning summary API or existing feature list context. | 6 tiles render with correct labels and colors; counts accurate per surface checklist in PRD; grid responsive; accent colors match design tokens | 2 pts | ui-engineer-enhanced, frontend-developer | sonnet | T2-001 |
| T2-003 | Artifact chip row (8 types) | Render chip per artifact type (SPEC/SPIKE/PRD/PLAN/PHASE/CTX/TRK/REP) with glyph, label, count; color with artifact-identity colors; clicking chip navigates to `/planning/artifacts/:type` (reusing existing artifact drill-down page if available). | 8 chips render with correct glyphs, labels, and colors; counts accurate; clicks navigate correctly; row ends with corpus summary text; empty counts show "0" | 2 pts | frontend-developer, ui-engineer-enhanced | sonnet | T2-001 |

**Phase 2 Quality Gates:**
- [ ] Hero header visible with corpus stats and spark chart
- [ ] 6 metrics tiles render with correct counts and colors
- [ ] 8 artifact chips render and navigate correctly
- [ ] All counts verified against backend payload
- [ ] Desktop and narrow-desktop responsive verified

---

### Phase 3: Triage Inbox & Live Agent Roster

**Duration**: 3 days  
**Dependencies**: Phase 2 complete  
**Entry Criteria**: Home layout established  
**Exit Criteria**: Triage and roster panels side-by-side, fully functional with filters and polling  
**Assigned Subagent(s)**: ui-engineer-enhanced, frontend-developer

#### Objectives

1. Implement triage inbox with filterable tabs (All / Blocked / Mismatches / Stale / Ready-to-promote).
2. Build live agent roster with state dots, names, tasks, and live/paused toggle.
3. Arrange two-up layout (1.3fr triage / 1fr roster).

#### Tasks

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|-------|--------------|
| T3-001 | Triage inbox with filterable tabs | Render tabbed filter (All / Blocked / Mismatches / Stale / Ready-to-promote) with count badges. For each tab, list triage rows: severity bar (3px, color by severity), kind badge, feature slug, title, action button + chevron. Clicking title opens feature detail drawer. Pull triage data from existing TriageService or new `GET /api/planning/triage` endpoint. | All 5 tabs present with badge counts; rows render for each filtered category; severity colors match design; action buttons functional; title clicks open feature detail; empty state shows green check + "Nothing to triage" | 3 pts | ui-engineer-enhanced, frontend-developer | sonnet | T2-003 |
| T3-002 | Triage action buttons | For each triage row, implement primary action button (Remediate / Dismiss / Promote / Assign PM / Archive / Resume shaping per kind). Clicking action shows toast and triggers planning graph refresh. (Actual remediation logic may be stubbed for v2 if complex.) | Action buttons render with correct labels per triage kind; clicking button shows toast feedback; graph refreshes; action state persists briefly; no errors thrown | 2 pts | frontend-developer | sonnet | T3-001 |
| T3-003 | Live agent roster panel | Render roster alongside triage in two-up layout (triage 1.3fr, roster 1fr). Columns: state dot (glows for running/thinking), agent name + model/tier, current task, since. Rows colored by state (running=ok, thinking=info, queued=warn, idle=dim). | Roster renders side-by-side with triage; state dots glow for active states; rows color-coded; layout proportions correct; responsive at <1280px (switch to stacked); polling updates live agents (if SSE not available, poll existing live-agent context) | 2 pts | ui-engineer-enhanced, frontend-developer | sonnet | T3-001 |

**Phase 3 Quality Gates:**
- [ ] Triage inbox renders with all 5 filter tabs
- [ ] Triage action buttons functional and show toast feedback
- [ ] Live agent roster side-by-side with triage
- [ ] State dots and row colors match design tokens
- [ ] Two-up layout responsive; stacks below 1280px
- [ ] Triage and roster data accurate against backend

---

### Phase 4: Planning Graph Reskin & Enhancements

**Duration**: 4–5 days  
**Dependencies**: Phase 2 complete (Phase 3 not on critical path)  
**Entry Criteria**: Metrics and chips complete  
**Exit Criteria**: Full graph reskin with all new lanes, DocChips, TotalsCell, edges, filters, and legend  
**Assigned Subagent(s)**: ui-engineer-enhanced, react-performance-optimizer

#### Objectives

1. Reskin lane headers and feature cells with new token system and visual hierarchy.
2. Implement DocChips (multiple stacked per lane for multi-artifact features).
3. Add PhaseStackInline (PhaseDots with completed/in-progress/blocked states).
4. Implement TotalsCell (effort points, token count, model-identity stacked bar).
5. Add animated SVG edge layer for active features.
6. Add graph filter controls and artifact legend.

#### Tasks

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|-------|--------------|
| T4-001 | Lane headers and feature cell reskin | Reskin lane header row with colored square glyphs (each artifact type, glyph color = artifact color), sticky positioning, lane labels. Reskin feature cell with category badge, complexity chip, mismatch/stale indicators (⚑ mag / ◷ warn), title (2-line clamp), status pill + slug. | Lane headers sticky and match handoff design; feature cells render all fields; mismatch/stale indicators visible; colors match artifact-identity tokens; grid layout correct | 2 pts | ui-engineer-enhanced | sonnet | T2-001 |
| T4-002 | DocChips and multi-artifact lanes | Implement DocChip component (type label + title truncated + status dot); support multiple stacked chips per lane cell for features with 2+ PRDs/Plans/Progress/etc. Gray out completed/superseded artifacts. | DocChips render in lanes; multiple chips per lane stack correctly; status dots visible; completed artifacts muted; spacing correct | 2 pts | ui-engineer-enhanced | sonnet | T4-001 |
| T4-003 | PhaseStackInline and PhaseDots | Implement PhaseDot (14×14, filled=completed, pulsing ring=in-progress, ! =blocked). Implement PhaseStackInline in progress lane showing row of dots with completed/total count. | PhaseDots render all 3 states (completed, in-progress, blocked); animation smooth for in-progress; PhaseStackInline shows correct count | 1.5 pts | ui-engineer-enhanced, react-performance-optimizer | sonnet | T4-001 |
| T4-004 | TotalsCell with model-identity bar | Implement TotalsCell in rightmost lane showing: large story-points number, total tokens right-aligned, stacked model-identity bar (opus/sonnet/haiku proportional widths), per-model token counts with colored dots. **Data source: server-provided `feature.tokenUsage` from `PlanningQueryService` / `FeatureForensicsQueryService` — specifically `total_tokens` plus the per-feature `tokenUsageByModel` breakdown delivered by T7-004. No client-side estimator.** | TotalsCell renders server-provided actual tokens; model bar proportions match server breakdown; per-model tokens and colors visible; layout right-aligned; component falls back gracefully when backend returns 0 (e.g., feature with no linked sessions) | 2 pts | ui-engineer-enhanced, react-performance-optimizer | sonnet | T4-002, T4-003, T7-004 |
| T4-005 | SVG edge layer with animation | Add SVG layer beneath/above grid rendering animated dashed flow edges for active features (brand color), static edges for inactive. Edges connect per-row lane cells in sequence. | Edges visible for active features; brand color correct; animation smooth; no performance regression on graph render; edges hidden for inactive features | 2 pts | ui-engineer-enhanced, react-performance-optimizer | sonnet | T4-004 |
| T4-006 | Graph filter controls and legend | Add "All categories" dropdown filter (features/enhancements/refactors/spikes); implement legend below graph showing color swatch + label per artifact type and animated edge example labeled "active edge". | Filter dropdown present and filters graph; legend renders with all 8 artifact types and edge example; "New feature" button renders (stub, shows toast for v2) | 1.5 pts | frontend-developer, ui-engineer-enhanced | sonnet | T4-005 |

**Phase 4 Quality Gates:**
- [ ] Lane headers sticky and match design
- [ ] DocChips render for multi-artifact lanes
- [ ] PhaseStackInline with PhaseDots correct states
- [ ] TotalsCell shows points and server-provided actual tokens (total + per-model bar) from session forensics; no client-side estimation present
- [ ] SVG edges animated and performant
- [ ] Filter controls and legend functional
- [ ] Graph render time ≤1.5s for 50 features

---

### Phase 5: Feature Detail Drawer — Header & Lineage

**Duration**: 2–3 days  
**Dependencies**: Phase 4 complete  
**Entry Criteria**: Graph row selection functional  
**Exit Criteria**: Feature detail drawer shell complete with header and lineage strip  
**Assigned Subagent(s)**: ui-engineer-enhanced, frontend-developer

#### Objectives

1. Implement drawer shell (fixed right panel, min 920px / 64vw wide, bg-1, border-left line-2, box-shadow).
2. Build header with category/slug breadcrumb, mismatch pill, serif h1 title, raw→effective status arrows, complexity chip, tags, Execute CTA, Close button.
3. Build lineage strip with 7 artifact-type tiles (clickable, scrolls to section).

#### Tasks

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|-------|--------------|
| T5-001 | Feature detail drawer shell | Render fixed right panel (min-width 920px, max 64vw) with bg-1 background, border-left line-2, box-shadow. Ensure scroll independent from graph. Header includes close button (top-right). | Drawer opens on graph row click; width and background correct; close button functional; drawer scrolls independently; responsive width at <1280px (narrow to 640px) | 1.5 pts | ui-engineer-enhanced, frontend-developer | sonnet | T4-006 |
| T5-002 | Drawer header with metadata | Render header: category/slug breadcrumb, mismatch pill (if mismatched), serif italic h1 title, raw status pill → effective status pill (arrow if different), complexity chip, tags (up to 3), Execute CTA button, Close button. | Header elements all visible; mismatch pill colors correct; raw→effective arrow shows when different; title in Fraunces italic; Execute CTA prominent | 2 pts | ui-engineer-enhanced, frontend-developer | sonnet | T5-001 |
| T5-003 | Lineage strip with artifact tiles | Render horizontal tile row: one clickable tile per artifact type (SPEC/SPIKE/PRD/PLAN/PHASE/CTX/REPORT). Tile shows type label, count ×N, representative status pill, PhaseDot stack for PHASE type. Clicking tile scrolls to relevant section in drawer and opens/toggles it. Mute tiles for empty types. | 7 tiles render with correct labels and counts; muted tiles for empty types; status pills representative; PhaseDot stack visible for PHASE; clicks scroll and toggle sections | 1.5 pts | frontend-developer, ui-engineer-enhanced | sonnet | T5-001 |

**Phase 5 Quality Gates:**
- [ ] Drawer shell renders with correct dimensions
- [ ] Header complete with all fields and colors
- [ ] Lineage strip renders 7 tiles with correct data
- [ ] Lineage tile clicks scroll and toggle sections
- [ ] Close button functional
- [ ] Responsive width verified

---

### Phase 6: Feature Detail Drawer — SPIKEs, OQ, DAG, Exec Buttons

**Duration**: 5–6 days  
**Dependencies**: Phase 5 complete  
**Entry Criteria**: Drawer shell and lineage complete  
**Exit Criteria**: All drawer sections complete (SPIKEs, OQ, batches, DAG), exec buttons wired to toast, user can resolve OQs inline  
**Assigned Subagent(s)**: ui-engineer-enhanced, frontend-developer

#### Objectives

1. Implement SPIKEs + Open Questions section with two-column grid (SPIKEs list, OQ list).
2. OQ inline resolution editor (textarea, Cmd+Enter to save, escape to cancel).
3. ModelLegend strip (opus/sonnet/haiku dots, labels, token counts, percentages).
4. Execution tasks section with "Batches" / "Dependency DAG" segment control.
5. Per-phase PhaseCard with per-batch BatchCol and per-task TaskRow.
6. Dependency DAG SVG view (cubic bezier edges, phase bands, batch columns, active edge animation).
7. Per-batch, per-task, and per-phase exec buttons (dispatch to toast only for v2).
8. Exec toast (bottom-center, auto-dismiss 2.4s).

#### Tasks

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|-------|--------------|
| T6-001 | SPIKEs + OQ section | Render collapsible section (spec color left border, eyebrow, bold title, chevron, count). Two-column grid: SPIKEs list on left (tile with SPIKE ID, title, status pill, hover-reveal ExecBtn), Open Questions list on right (OQ tile with severity bar, OQ ID, question text, "+ answer…" button). | Section renders with color-coded border; SPIKE tiles visible with exec button on hover; OQ tiles visible with answer button; grid responsive; counts accurate | 2 pts | ui-engineer-enhanced, frontend-developer | sonnet | T5-003 |
| T6-002 | OQ inline resolution editor | Clicking "+ answer…" on OQ tile opens inline textarea (Cmd+Enter to resolve, Escape to cancel, click outside to cancel). On Cmd+Enter, show pending state and fire `PATCH /api/planning/features/:id/open-questions/:oq_id` request with answer text. On success, mark OQ resolved (ok background, answer text visible). On error, show error toast. Component state stores pending answers. | Textarea opens on button click; Cmd+Enter fires PATCH request; pending state shows briefly; on success, OQ marked resolved with ok background; error toast on failure; escape cancels edit | 2 pts | frontend-developer, ui-engineer-enhanced | sonnet | T6-001 |
| T6-003 | ModelLegend strip | Render horizontal strip showing: opus color dot + label + token count, sonnet color dot + label + token count, haiku color dot + label + token count, totals (pts + tokens) right-aligned. **Data source: `feature.tokenUsageByModel` from the server (per T7-004) — actuals from session forensics, not estimates.** | Legend renders with all 3 models and correct colors; token counts per model reflect server-provided session-forensics actuals; totals right-aligned; layout horizontal and compact | 1.5 pts | frontend-developer, ui-engineer-enhanced | sonnet | T6-002, T7-004 |
| T6-004 | Execution tasks section — batches view | Render collapsible section with segment control "Batches" / "Dependency DAG" at top. In Batches view: ModelLegend strip, then per-PhaseCard list. PhaseCard: phase header (PHASE N, name, status, "run phase" ExecBtn, progress bar + % and pts/tokens); per-batch BatchCol (parallel label, task count, ExecBtn); per-task TaskRow (task ID, title, agent chip with model color, token display, status pill, hover-reveal ExecBtn). | Batches view renders with ModelLegend; PhaseCards render with batch structure; per-task rows visible; exec buttons visible on hover; progress bar shows correctly | 3 pts | ui-engineer-enhanced, frontend-developer | sonnet | T6-003 |
| T6-005 | Dependency DAG SVG view | Switching to DAG view renders SVG canvas (absolute-positioned). Nodes arranged by phase (horizontal bands) and batch (columns); cubic bezier edges with arrowheads; active edges animated (flow dashes); blocked edges red; legend for edge states. Render from phase/task/deps data in feature payload (no separate API call). | DAG view renders SVG with correct phase bands and batch columns; edges visible and bezier curves smooth; arrowheads correct; animation smooth for active edges; blocked edges red; legend present | 3 pts | ui-engineer-enhanced | sonnet | T6-004 |
| T6-006 | Exec buttons and toast | Wire all exec buttons (per-phase, per-batch, per-task, per-SPIKE) to dispatch action and show exec toast. Toast: bottom-center fixed, shows label (e.g., "▶ running Phase 02 — Service layer"), brand color dot, auto-dismisses 2.4s. For v2, toast is client-side only; actual execution is stubbed (future DEFER-02). | Exec buttons visible and clickable on all surfaces; clicking button shows toast within 50ms; toast auto-dismisses 2.4s; no errors thrown; actual execution stubbed (no API call for now) | 1.5 pts | frontend-developer, ui-engineer-enhanced | sonnet | T6-005 |

**Phase 6 Quality Gates:**
- [ ] SPIKEs and OQ sections render correctly
- [ ] OQ inline editor functional (Cmd+Enter saves, Escape cancels)
- [ ] OQ resolution fires PATCH and updates UI
- [ ] ModelLegend accurate — values are server-provided session-forensics actuals (from `feature.tokenUsageByModel`), not client-side estimates
- [ ] Batches view complete with all card/col/row layers
- [ ] DAG view renders SVG correctly
- [ ] Exec buttons show toast
- [ ] Toast auto-dismisses 2.4s

---

### Phase 7: Backend OQ Write-Back Endpoint + Per-Feature Token-Usage-By-Model

**Duration**: 2–3 days  
**Dependencies**: Phase 0 backend audit (OQ-01, OQ-02) complete  
**Entry Criteria**: `spikes[]`, `openQuestions[]` confirmed on feature payload; session-forensics token aggregation audited (T0-006)  
**Exit Criteria**: `PATCH /api/planning/features/:id/open-questions/:oq_id` endpoint live with schema validation and OTEL spans; per-feature `tokenUsageByModel` field exposed on planning/feature-forensics payload  
**Assigned Subagent(s)**: python-backend-engineer, backend-architect

#### Objectives

1. Add `PATCH /api/planning/features/:id/open-questions/:oq_id` endpoint.
2. Implement transport-neutral service method in `backend/application/services/agent_queries/`.
3. Request validation (Pydantic schema for answer text).
4. Response: 200 OK with updated OQ state, or 202 Accepted with pending status (deferred file-write per DEFER-03).
5. Add OpenTelemetry spans for observability.
6. Extend `FeatureForensicsQueryService` / `PlanningQueryService` with a per-feature `tokenUsageByModel` aggregation (opus / sonnet / haiku / other) derived from existing `linked_sessions[*].{model, total_tokens}` using `backend/model_identity.py:derive_model_identity`. Expose on the planning feature payload consumed by TotalsCell (T4-004) and ModelLegend (T6-003). Resolves OQ-02 and absorbs the former DEFER-05.

#### Tasks

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|-------|--------------|
| T7-001 | Transport-neutral OQ resolution service | Add method to `backend/application/services/agent_queries/` (or existing planning service) that accepts feature_id, oq_id, answer_text and returns OQ state with resolved flag. No file writes; state stored in component cache only (per DEFER-03). Include request validation. | Service method callable; returns OQ state with resolved flag; answer_text stored in payload; validation rejects empty answers | 1.5 pts | backend-architect, python-backend-engineer | sonnet | T0-004 |
| T7-002 | REST endpoint wrapper | Add `PATCH /api/planning/features/:id/open-questions/:oq_id` endpoint in `backend/routers/features.py` (or new `planning.py` router). Request body: `{ answer: string }`. Response: 200 with updated OQ state, or 202 if file-sync pending. Integrate service method from T7-001. | Endpoint callable via curl/frontend; accepts answer text; returns 200 with OQ state or 202 with pending status; error handling (404 for missing feature/OQ, 400 for invalid answer) | 1.5 pts | python-backend-engineer, backend-architect | sonnet | T7-001 |
| T7-003 | OpenTelemetry instrumentation | Add OTEL spans for OQ resolution (span name: `planning.oq.resolve`, attributes: feature_id, oq_id, answer_length, success). Integrate with existing otel.py observability layer. | Spans exported to configured OTEL exporter; span attributes correct; logs captured if configured | 0.5 pts | python-backend-engineer | sonnet | T7-002 |
| T7-004 | Per-feature `tokenUsageByModel` aggregation | Extend `FeatureForensicsQueryService.build_feature_forensics` (and the planning feature payload consumed by the Planning Deck) with a `tokenUsageByModel` field shaped `{opus: int, sonnet: int, haiku: int, other: int, total: int}`. Derive by iterating `linked_sessions[*]`, normalizing `model` via `backend/model_identity.derive_model_identity(raw_model)["modelFamily"]`, and summing `total_tokens`. Treat unknown families as `other`. Keep legacy `total_tokens` untouched. Add unit tests covering multi-session features with mixed models and zero-session features. | New field present on feature forensics + planning feature payloads; unit tests pass (multi-model, empty, partial data); `modelFamily` resolution covers lowercase variants; `total` equals existing `total_tokens`; no frontend breakage | 2 pts | python-backend-engineer, backend-architect | sonnet | T0-006 |

**Phase 7 Quality Gates:**
- [ ] Service method implemented and tested
- [ ] `PATCH` endpoint callable and validates input
- [ ] OQ state updated correctly
- [ ] OpenTelemetry spans exported
- [ ] Error handling for missing/invalid inputs
- [ ] Integration tests pass
- [ ] `tokenUsageByModel` field present on planning feature payload (T7-004) with opus/sonnet/haiku/other breakdown sourced from `FeatureForensicsQueryService` linked sessions

---

### Phase 8: A11y Hardening & Performance Tuning

**Duration**: 2–3 days  
**Dependencies**: Phases 4–7 complete  
**Entry Criteria**: All feature surfaces complete  
**Exit Criteria**: WCAG 2.1 AA compliance, font perf optimized, graph render budgets met  
**Assigned Subagent(s)**: web-accessibility-checker, react-performance-optimizer

#### Objectives

1. Keyboard navigation audit (Tab order, Enter/Space activation for all interactive elements).
2. ARIA roles for planning graph (table semantics or grid roles with headers).
3. Focus ring styling (2px solid brand color, 60% alpha, 2px offset).
4. Color-only fallback text labels for StatusPills, ArtifactChips, model-identity elements.
5. Font performance (non-blocking load, no CLS, <50ms paint impact).
6. Planning graph render timing benchmarks (TTI, graph render ≤1.5s for 50 features, detail drawer ≤150ms).

#### Tasks

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|-------|--------------|
| T8-001 | Keyboard navigation audit | Test all interactive elements (drawer, triage rows, graph rows, PhaseCards, BatchCols, TaskRows, ExecBtns, OQ editor) for Tab navigation and Enter/Space activation. Fix tab order if needed; use tabindex strategically. | All interactive elements keyboard-accessible; Tab order logical; Enter/Space activates buttons; focus always visible; no keyboard traps | 1.5 pts | web-accessibility-checker | sonnet | T6-006 |
| T8-002 | ARIA roles and screen-reader support | Add `role="table"` or `role="grid"` to planning graph; add `role="rowheader"` to feature column; add `role="columnheader"` to lane headers; ensure all color-only elements have text labels. Test with screen reader (e.g., NVDA on Windows). | Graph and headers have correct ARIA roles; screen reader can read feature titles and lane names; color-only elements have text fallback | 1.5 pts | web-accessibility-checker | sonnet | T8-001 |
| T8-003 | Focus ring styling and visual hierarchy | Implement 2px solid brand-color focus ring at 60% alpha, 2px offset (from handoff CSS). Apply to all focusable elements. Verify contrast against bg-1 and bg-2 backgrounds. | Focus ring visible on all interactive elements; contrast ≥4.5:1 against backgrounds; 2px offset correct | 0.5 pts | web-accessibility-checker, ui-engineer-enhanced | sonnet | T8-002 |
| T8-004 | Color + text label fallback | Audit StatusPills (add label text next to dot), ArtifactChips (ensure type label text is always readable, not just color), and model-identity bars (add "Opus", "Sonnet", "Haiku" text next to dots or in legend). Verify compliance with WCAG 2.1 § 1.4.1 (Color not the only means). | All color-only elements have readable text labels; no reliance on color alone for meaning; labels tested for contrast and legibility | 1 pt | web-accessibility-checker, ui-engineer-enhanced | sonnet | T8-003 |
| T8-005 | Font performance (non-blocking, CLS, paint impact) | Confirm Google Fonts loaded with `display: swap`; preconnect links in `<head>`; measure CLS (Cumulative Layout Shift) before and after font load; confirm paint timing <50ms impact; use `font-display: swap` to avoid invisible text during load. | Fonts load with display: swap; CLS <0.1 on initial load; paint timing <50ms; no missing glyphs or fallback jumps | 0.5 pts | react-performance-optimizer, frontend-developer | sonnet | T1-003 |
| T8-006 | Planning graph render budgets | Benchmark planning home TTI (target ≤2s), graph render with ≤50 features (target ≤500ms), graph render with ≤200 features (target ≤1.5s, may need virtualization for >100; currently out of scope per DEFER-10), feature detail drawer open (target ≤150ms). Use React DevTools Profiler and Lighthouse. Document if budgets exceeded and mitigation plan. | Planning home TTI ≤2s on local dev; graph render 50 features ≤500ms; graph render 200 features ≤1.5s (or virtualization flagged); drawer ≤150ms; metrics documented | 1.5 pts | react-performance-optimizer, frontend-developer | sonnet | T4-005, T4-006 |

**Phase 8 Quality Gates:**
- [ ] All interactive elements keyboard-navigable
- [ ] ARIA roles and screen-reader support validated
- [ ] Focus ring visible and contrasting
- [ ] Color-only elements have text fallback labels
- [ ] Fonts load non-blocking with <50ms impact
- [ ] CLS <0.1
- [ ] Performance budgets met (TTI, render, drawer times)
- [ ] WCAG 2.1 AA compliance verified

---

### Phase 9: Testing — Unit, Integration, Component

**Duration**: 2–3 days  
**Dependencies**: Phase 8 complete  
**Entry Criteria**: All features complete and a11y hardened  
**Exit Criteria**: >80% code coverage, all critical flows tested, OQ write-back integration tested  
**Assigned Subagent(s)**: frontend-developer, testing specialist

#### Objectives

1. Unit tests for all new primitives (StatusPill, ArtifactChip, etc.).
2. Component tests for Planning surfaces (home, graph, drawer, triage, roster).
3. Integration tests for OQ write-back endpoint.
4. E2E tests for critical journeys (graph row click → drawer open, OQ resolve).
5. A11y tests (automated axe checks, screen-reader smoke tests).

#### Tasks

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|-------|--------------|
| T9-001 | Primitive component unit tests | Add Vitest unit tests for StatusPill (all 11 status values), ArtifactChip (8 types), MetricTile, Spark, ExecBtn, PhaseDot, PhaseStackInline, TotalsCell, DocChip, Dot, Chip, Panel, Tile. Each test verifies render, props, and basic interaction. Target >90% coverage. | All primitives have unit tests; all status values and artifact types covered; tests pass in CI; coverage >90% | 2 pts | frontend-developer, testing specialist | sonnet | T6-006 |
| T9-002 | Planning surface component tests | Add component tests for PlanningHomePage (metrics, chips render), PlanningGraphPanel (rows, lanes, edges render), PlanningNodeDetail (drawer open/close, lineage tiles), TriagePanel (tabs, rows, actions), AgentRoster (rows, state dots). Use React Testing Library. Mock API calls. | All main surfaces have component tests; mocked API calls work; user interactions (clicks, tabs) trigger expected state; coverage >80% | 2.5 pts | frontend-developer, testing specialist | sonnet | T9-001 |
| T9-003 | OQ resolution integration test | Add backend integration test for `PATCH /api/planning/features/:id/open-questions/:oq_id`: (1) seed test feature with OQ, (2) call endpoint with answer text, (3) verify response 200 with resolved OQ, (4) verify OTEL span exported. Also add frontend integration test: mock API, render OQ editor, resolve, verify UI updated. | Backend test passes (endpoint callable, response correct); frontend test passes (editor opens, Cmd+Enter fires PATCH, UI updates on success); >85% test coverage | 2 pts | python-backend-engineer, frontend-developer | sonnet | T7-003, T6-002 |
| T9-004 | E2E critical journeys | Add E2E tests (Playwright) for: (1) open planning home, (2) click graph row, (3) drawer opens with lineage, (4) resolve OQ inline, (5) switch to DAG view, (6) click exec button, (7) toast appears and dismisses. | All 7 journeys covered; tests pass in CI; screenshots captured for visual regression (if screenshot-testing enabled) | 2 pts | testing specialist | sonnet | T9-003 |
| T9-005 | A11y automated + manual tests | Run axe-core (Vitest plugin) on all planning surfaces (target: 0 violations). Manual smoke test with screen reader (NVDA on Windows or VoiceOver on Mac) for feature title and key interactive elements. Document any false positives. | Automated a11y tests pass (0 violations or documented exceptions); manual screen-reader smoke tests pass; no blocking a11y issues | 1.5 pts | web-accessibility-checker, testing specialist | sonnet | T8-004 |

**Phase 9 Quality Gates:**
- [ ] All primitives have unit tests with >90% coverage
- [ ] All planning surfaces have component tests with >80% coverage
- [ ] OQ resolution integration tests pass (backend + frontend)
- [ ] E2E critical journeys pass (7 scenarios)
- [ ] A11y tests pass (0 violations, screen-reader smoke test OK)
- [ ] All tests pass in CI/CD

---

### Phase 10: Documentation Finalization

**Duration**: 1 day  
**Dependencies**: All phases complete  
**Entry Criteria**: All features complete and tested  
**Exit Criteria**: CHANGELOG updated, README updated, design specs for deferred items, context files updated  
**Assigned Subagent(s)**: changelog-generator, documentation-writer, ai-artifacts-engineer

#### Overview

Evaluate and update all documentation affected by this feature. All doc tasks delegate to skill-equipped agents.

#### Task Table

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|-------|--------------|
| DOC-001 | Update CHANGELOG | Add entry for user-facing changes under `[Unreleased]` following Keep A Changelog format. Include: "Added: CCDash Planning Reskin v2 with new design tokens, hero header, metrics strip, triage inbox, live agent roster, planning graph enhancements (effort/token totals lane, animated edges), feature detail drawer SPIKEs/OQ resolution, dependency DAG, exec buttons, and OQ write-back API endpoint. Changed: Planning routes now use new Geist/JetBrains Mono/Fraunces typography and OKLCH token system. Improved: A11y (WCAG 2.1 AA) and performance (graph render <1.5s for 50 features)." Categorization per `.claude/specs/changelog-spec.md`. | `[Unreleased]` contains planning v2 entry with all major features; categorization correct; readability good | 0.5 pts | changelog-generator | haiku | T9-005 |
| DOC-002 | Update README | Update planning section in root README (or create new Planning Guide under `docs/guides/`) describing new surfaces (home, graph, triage, drawer), new interactions (OQ resolution, exec buttons), and how to access them. Include screenshots of main surfaces if available. | README or planning guide updated with new surfaces and navigation; screenshots present; clear and concise | 0.5 pts | documentation-writer | haiku | T9-005 |
| DOC-003 | Update context files (CLAUDE.md, key-context) | Update `docs/project_plans/CLAUDE.md` with pointer to planning design token system (one-liner referencing `planning-tokens.css`). Update key-context file for planning UI patterns if needed (new primitives, token usage). | CLAUDE.md pointer added (≤3 lines); key-context file updated if applicable; progressive disclosure maintained | 0.5 pts | documentation-writer | haiku | T9-005 |
| DOC-004 | Author design specs for deferred items | For each remaining deferred item (DEFER-01, 02, 03, 04, 06, 07, 08, 09, 10 — DEFER-05 was promoted into v2 scope on 2026-04-20 and is not deferred), author a design_spec at `docs/project_plans/design-specs/[item-slug].md` with `maturity: shaping` (or `idea` if research-needed), set `prd_ref` to this plan's parent PRD, and populate with problem statement and open questions. | All 9 remaining deferred items have corresponding design specs; specs have correct frontmatter and maturity; `deferred_items_spec_refs` frontmatter populated with all paths | 1.8 pts | documentation-writer | sonnet | T9-005 |
| DOC-005 | Update plan frontmatter | Set status: completed, populate commit_refs (if PRs merged), files_affected list (key files: components/Planning/*, backend/routers/features.py, planning-tokens.css, tailwind.config.js), and updated date. | Frontmatter complete; status = completed; all key files listed; dates accurate | 0.5 pts | documentation-writer | haiku | DOC-001 through DOC-004 |

**Phase 10 Quality Gates:**
- [x] CHANGELOG entry complete and under `[Unreleased]`
- [x] README or planning guide updated with new surfaces
- [x] Context files updated (CLAUDE.md pointer, key-context)
- [x] Design specs authored for the 9 remaining deferred items (DEFER-05 removed from deferred list on 2026-04-20 — promoted into v2 scope)
- [ ] Plan frontmatter complete (status, commit_refs, files_affected)

---

## Risk Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| OKLCH token drift — browser support for `oklch()` and `color-mix()` varies | High | Medium | PostCSS fallback plugin for sRGB; test in target Chromium version; document minimum version requirement |
| Scope creep into exec button wiring | High | High | Clearly stub actual execution; dispatch to toast only; DEFER-02 marks full wiring as future work |
| OQ write-back data integrity | Medium | Medium | Mark OQ state as "pending-sync" in UI; do not remove raw status from payload; fallback to re-fetch on sync event |
| Performance regression from font loading | Medium | Low | Load fonts with `display: swap`; measure CLS and paint timing; budget <50ms impact |
| @miethe/ui extraction coordination | Low | Low | Keep primitives in `components/Planning/primitives/` (local scope); extraction deferred to post-ship (DEFER-07); 9-step process documented |
| Design/code drift — parity vs pragmatism | Medium | Medium | Accept ~5% visual deviation for non-critical elements; document "known deltas" if minor deviations necessary |

---

## Resource Requirements

**Team Composition:**
- **Frontend Engineer (UI/UX specialist)**: 1.5 FTE (Phases 0–9)
- **Frontend Developer**: 1 FTE (Phases 1–9)
- **Backend Engineer**: 0.5 FTE (Phase 7, Phase 0 audit)
- **QA / Testing Specialist**: 0.5 FTE (Phase 9)

**Skill Requirements:**
- React 19, TypeScript, Tailwind CSS, Vitest
- OKLCH color model, CSS custom properties
- SVG / canvas rendering (for DAG)
- A11y standards (WCAG 2.1 AA), performance profiling (Lighthouse, React DevTools)
- FastAPI, Pydantic (backend)

---

## Success Metrics

### Visual Parity
- Each major surface (shell, home, graph, drawer, triage, roster) matches handoff design ≥90% per checklist.

### Functional Completeness
- All 11 surfaces (app rail, top bar, hero, metrics, chips, triage, roster, graph, drawer, DAG, toast) implemented and tested.
- All interactive elements (graph row click, drawer open/close, OQ resolve, exec button dispatch, filter tabs) functional.

### Performance
- Planning home TTI ≤2s on local dev.
- Planning graph render with 50 features ≤500ms; 200 features ≤1.5s.
- Feature detail drawer open ≤150ms.
- Font load impact <50ms CLS.

### Accessibility
- WCAG 2.1 AA compliance (keyboard nav, ARIA roles, focus visibility, color + text labels).
- Automated a11y tests: 0 violations (or documented exceptions).
- Screen-reader smoke test passes.

### Test Coverage
- Primitives: >90% unit test coverage.
- Planning surfaces: >80% component test coverage.
- E2E: 7 critical journeys covered.
- OQ write-back: integration test pass.

### Deferred Items
- All 9 remaining deferred items (DEFER-01, 02, 03, 04, 06, 07, 08, 09, 10) have corresponding design specs at documented paths. DEFER-05 was promoted into v2 scope on 2026-04-20 and no longer requires a design spec.
- `deferred_items_spec_refs` frontmatter populated.

---

## Communication Plan

- **Daily standups** for progress/blockers (async or sync).
- **End-of-phase reviews** to validate quality gates before progressing.
- **Weekly status** on milestones and critical-path health.
- **Open-questions resolution** (OQ-01 through OQ-04 from PRD flagged for early clarification in Phase 0).

---

## Post-Implementation

- **Feature guide** (`.claude/worknotes/ccdash-planning-reskin-v2/feature-guide.md`) authored after final phase seals.
- **Pull request** opened with feature guide, CHANGELOG entry, and test coverage summary.
- **Post-launch monitoring** for performance regressions, a11y issues, and user feedback.
- **Deferred items** (DEFER-01 through DEFER-10) scheduled for future waves per triggers in design specs.

---

## Open Questions (from PRD)

### OQ-01: Backend payload structure
- **Question**: Does `PlanningQueryService` already return `spikes[]` and `openQuestions[]` arrays, or do those need to be added?
- **Recommendation**: Audit during Phase 0 (T0-004); if missing, add them (in-scope as part of Phase 0 backend audit).

### OQ-02: Token source
- **Question**: Is client-side token estimation acceptable for v2 telemetry tiles, or should the backend return actual session-linked token counts?
- **Resolution (2026-04-20)**: **Use actual session-forensics tokens.** The feature↔session correlation already exists: `FeatureForensicsQueryService` loads links via `_load_feature_session_rows` (`backend/application/services/agent_queries/feature_forensics.py:266`) and returns `FeatureForensicsDTO.total_tokens` plus `linked_sessions[*].{model, total_tokens}`. Phase 7 (T7-004) adds a per-feature `tokenUsageByModel` aggregation keyed by `modelFamily` (opus/sonnet/haiku/other) via `backend/model_identity.py:29`. Former DEFER-05 is promoted into scope; no client-side estimator.

### OQ-03: Font loading
- **Question**: Is Google Fonts CDN acceptable for local-first deployment, or should fonts be bundled?
- **Recommendation**: **Default to CDN for v2.** Bundled fonts deferred to DEFER-04; spec authored in Phase 10. CDN acceptable because local-first target has internet access in dev environment.

### OQ-04: "New spec" CTA
- **Question**: Should "New spec" button open a creation flow or show a stub toast for v2?
- **Recommendation**: **Stub with toast for v2.** Full creation flow deferred to DEFER-06; spec authored in Phase 10.

---

## Glossary & Key Terms

- **Reskin**: Visual redesign using new token system and component inventory; behavior unchanged.
- **Design parity**: Visual match to design handoff (target ≥90% per surface checklist in PRD).
- **Triage inbox**: New surface listing blocked/mismatch/stale/ready-to-promote features with filterable tabs.
- **Planning graph**: Lane-per-artifact-type matrix grid showing feature rows with multi-artifact stacked chips.
- **TotalsCell**: Rightmost lane showing effort points, token count, and model-identity stacked bar.
- **DocChip**: Small tile showing artifact type, title, and status dot; supports multiple stacked chips per lane cell.
- **OQ**: Open Question (from feature planning documents); inline resolution editor allows operators to answer and save.
- **DAG**: Directed Acyclic Graph of phase→batch→task dependencies; rendered as SVG with cubic bezier edges.
- **Exec button**: Interactive button to dispatch a phase/batch/task execution action; toast-only for v2 (actual wiring deferred).
- **Live agent roster**: Panel showing currently running agents with state dots (running=glowing, idle=dim) and task context.

---

## Appendices

### File Structure (Expected Changes)

```
components/Planning/
  ├── primitives/
  │   ├── StatusPill.tsx
  │   ├── ArtifactChip.tsx
  │   ├── MetricTile.tsx
  │   ├── Dot.tsx
  │   ├── PhaseDot.tsx
  │   ├── PhaseStackInline.tsx
  │   ├── DocChip.tsx
  │   ├── TotalsCell.tsx
  │   ├── ModelLegend.tsx
  │   ├── ExecBtn.tsx
  │   ├── ExecToast.tsx
  │   └── index.ts
  ├── PlanningHomePage.tsx (reskin)
  ├── PlanningGraphPanel.tsx (reskin + enhancements)
  ├── PlanningNodeDetail.tsx (reskin + feature detail drawer)
  ├── TriagePanel.tsx (new)
  ├── AgentRoster.tsx (new)
  ├── DependencyDAG.tsx (new)
  └── index.ts

planning-tokens.css (new)
tailwind.config.js (extended with token values)

backend/routers/
  ├── features.py (add PATCH endpoint for OQ)
  └── planning.py (optional: new planning-specific router)

backend/application/services/agent_queries/
  └── planning_query_service.py (extend with OQ resolution method)

tests/
  ├── components/Planning/__tests__/
  │   ├── primitives.spec.tsx
  │   ├── PlanningHomePage.spec.tsx
  │   ├── PlanningGraphPanel.spec.tsx
  │   └── PlanningNodeDetail.spec.tsx
  └── backend/tests/
      └── test_oq_resolution.py
```

### References

- **Design Handoff**: `docs/project_plans/designs/ccdash-planning/project/Planning Deck.html`
- **Prior Wave (v1)**: `docs/project_plans/implementation_plans/enhancements/ccdash-planning-control-plane-v1.md`
- **Planning Skill**: `.claude/skills/planning/`
- **Subagent Assignments**: `.claude/skills/planning/references/subagent-assignments.md`
- **Multi-Model Guidance**: `.claude/skills/planning/references/multi-model-guidance.md`
- **Deferred Items Reference**: `.claude/skills/planning/references/deferred-items-and-findings.md`
- **Documentation Finalization Guidance**: `.claude/skills/planning/references/doc-finalization-guidance.md`

---

**Progress Tracking**: `.claude/progress/ccdash-planning-reskin-v2/` (to be created)

**Implementation Plan Version**: 1.0  
**Last Updated**: 2026-04-20
