---
title: CCDash Planning Reskin & Enhancement Wave v2
schema_version: 2
doc_type: prd
status: completed
created: 2026-04-20
updated: '2026-04-26'
feature_slug: ccdash-planning-reskin-v2
feature_version: v2
prd_ref: null
plan_ref: null
priority: high
risk_level: high
category: product-planning
changelog_required: true
owner: platform-engineering
contributors: []
tags:
- prd
- planning
- ui
- reskin
- design-handoff
- enhancements
milestone: null
commit_refs: []
pr_refs: []
files_affected: []
related_documents:
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
  related_prds:
  - docs/project_plans/PRDs/enhancements/ccdash-planning-control-plane-v1.md
spike_ref: null
adr_refs: []
charter_ref: null
changelog_ref: null
test_plan_ref: null
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
---

# Feature Brief & Metadata

**Feature Name:** CCDash Planning Reskin & Enhancement Wave v2

**Filepath Name:** `ccdash-planning-reskin-v2`

**Date:** 2026-04-20

**Author:** Claude Sonnet 4.6 (AI)

**Related Documents:**
- Design handoff bundle: `docs/project_plans/designs/ccdash-planning/README.md`
- Primary design: `docs/project_plans/designs/ccdash-planning/project/Planning Deck.html`
- Baseline implementation: `docs/project_plans/implementation_plans/enhancements/ccdash-planning-control-plane-v1.md`

---

## 1. Executive Summary

Control-plane v1 delivered a functional planning surface covering the planning graph, feature drill-downs, phase operations, and launch preparation. The Claude Design handoff (`Planning Deck.html`) provides a pixel-precise reference for a significantly richer visual and interaction system that v1 did not attempt to match. This PRD authorizes two intertwined deliverables: (1) a pixel-faithful reskin of the `/planning` route using the new design token system, component inventory, and layout language, and (2) a set of interaction enhancements that the deck surfaces and that v1 either stubbed, omitted, or only partially implemented.

**Priority:** HIGH

**Key Outcomes:**
- Outcome 1: The `/planning` route reaches visual parity with the design handoff, measurable per surface.
- Outcome 2: All eight planning artifact types are navigable, filterable, and cross-linked in-app.
- Outcome 3: Operators gain actionable triage, open-question resolution, SPIKE management, and token/effort telemetry (backed by actual session-forensics token counts) without leaving the planning surface.

---

## 2. Context & Background

### Current state

Control-plane v1 (phases 1–8, status: completed) introduced:
- `components/Planning/PlanningHomePage.tsx` — summary cards and active/planned feature columns.
- `components/Planning/PlanningGraphPanel.tsx` — lane-per-artifact-type matrix grid.
- `components/Planning/PlanningNodeDetail.tsx` — per-feature detail delegating to ProjectBoard feature modal.
- `components/Planning/TrackerIntakePanel.tsx` — tracker and deferred item visibility.
- `components/Planning/PlanningLaunchSheet.tsx` — plan-driven batch launch preparation.
- `components/Planning/primitives/PhaseOperationsPanel.tsx` — per-phase task batch view.
- `components/Planning/ArtifactDrillDownPage.tsx` — artifact-type drill-down reusing `/plans` list components.
- Routes: `/planning`, `/planning/feature/:featureId`, `/planning/artifacts/:type`.

What v1 delivered was architecturally correct but used the existing slate/Tailwind visual language without implementing the opinionated design system established by the Claude Design handoff. The handoff defines a new token vocabulary (OKLCH color model, artifact-identity colors, model-identity colors, semantic colors), a three-column shell, a set of new surface sections (metrics strip, artifact composition chips, triage inbox, agent roster, planning graph with effort/token totals column), and rich feature detail interactions (SPIKEs panel, open-question inline resolution, dependency DAG, model legend, exec buttons per batch/task) that are absent or only partially visible in v1.

### Architectural context

Stack: React 19 + TypeScript + Vite, HashRouter, Tailwind CSS (slate dark-mode theme), `@/` path alias to repo root. Backend: Python FastAPI, transport-neutral agent query services at `backend/application/services/agent_queries/`, existing planning endpoints under `backend/routers/features.py`, live invalidation in `backend/routers/live.py`.

---

## 3. Problem Statement

> "As a platform operator, when I open the CCDash planning surface, I get a functional but visually sparse overview that does not expose the full richness of planning data — artifact cross-links, SPIKE status, open questions, token/effort telemetry, triage actions, and the dependency DAG — forcing me to navigate raw files or separate tools to get a complete operational picture."

**Technical root causes:**
- v1 implements the right component structure but does not apply the design handoff's token system (OKLCH surfaces, artifact-identity and model-identity color semantics, typography hierarchy using Geist/JetBrains Mono/Fraunces).
- v1 planning home is missing: the hero header with corpus statistics and spark chart; the 6-tile metrics strip (total / active / blocked / stale / mismatches / completed); the artifact composition chip row; the triage inbox with filterable tabs (blocked / mismatch / stale / ready-to-promote); the live agent roster panel.
- v1 planning graph is missing: the effort+tokens totals lane; model-identity stacked bar per feature row; phase dot stack in the progress lane.
- v1 feature detail does not expose: SPIKEs panel with per-SPIKE exec buttons; open-question inline resolution (write-back to frontmatter answer field); model legend strip with token breakdown by model; dependency DAG view (batch-column SVG graph with animated flow edges); per-batch and per-task exec buttons with toast feedback.
- v1 has no triage inbox, no open-question resolution, no SPIKE execution surface, and no token/effort telemetry visualization.

---

## 4. Goals & Success Metrics

### Primary goals

**Goal 1: Visual parity with the design handoff**
- Each major surface (planning home, planning graph, feature detail drawer, triage inbox) matches the handoff's layout, color tokens, typography, and component inventory.
- Measurable: per-surface visual parity checklist (see Acceptance Criteria).

**Goal 2: Full planning artifact navigability**
- All 8 artifact types (SPEC, SPIKE, PRD, PLAN, PHASE/progress, CTX, TRK, REP) are visible, filterable, and cross-linked from a single `/planning` entry point.

**Goal 3: Actionable operator telemetry**
- Token/effort rollup, model-identity breakdown, triage item counts, and open-question status are surfaced without requiring raw file inspection.

### Success metrics

| Metric | Baseline (v1) | Target | Measurement method |
|--------|--------------|--------|--------------------|
| Visual parity score (manual checklist) | ~25% | ≥90% per surface | Checklist pass/fail per surface section |
| Artifact types navigable in-app | 4 (spec, prd, plan, prog) | 8 | Feature flag enabled, QA walkthrough |
| Triage items surfaced automatically | 0 | blocked + mismatch + stale + ready | triage tab counts match backend derivation |
| Open questions resolvable in-app | 0 | Yes (inline write-back) | OQ resolved state persists across reload |
| Token/effort visible per feature | 0 | Points + actual session tokens + per-model bar visible | Planning graph totals column (backed by FeatureForensicsQueryService) |

---

## 5. User personas & journeys

**Primary persona: Platform operator / lead PM**
- Needs: Single surface to see planning health, triage blockers, track artifact coverage, and initiate execution.
- Current frustration: Must open raw markdown files to find SPIKE status, open questions, and token consumption.

**Secondary persona: AI agent orchestrator**
- Needs: Token-disciplined context about which phases are ready, which batches are parallelizable, and which exec actions are safe.
- Current frustration: Launch preparation UI does not expose batch-level context or model-identity information.

### High-level flow

```mermaid
graph LR
    A[/planning route] --> B[Planning Deck home]
    B --> C[Metrics strip + artifact chips]
    B --> D[Triage inbox]
    B --> E[Agent roster]
    B --> F[Planning graph]
    F --> G[Feature row click]
    G --> H[Feature detail drawer]
    H --> I[Lineage strip]
    H --> J[SPIKEs + OQ section]
    H --> K[Execution tasks — batches view]
    H --> L[Dependency DAG view]
    K --> M[Phase → Batch → Task exec]
    D --> N[Triage action: Remediate / Promote / Archive]
```

---

## 6. Requirements

### 6.1 Functional requirements

#### Surface 1: Design token system and base primitives

| ID | Requirement | Priority | Notes |
|----|-------------|----------|-------|
| FR-101 | Map design CSS variables to Tailwind arbitrary values / CSS custom properties in `tailwind.config.js` and a new `planning-tokens.css`; cover surface tokens (bg-0 through bg-4, line-1/2, ink-0 through ink-4), artifact-identity colors (spec/spk/prd/plan/prog/ctx/trk/rep), semantic colors (ok/warn/err/info/mag), model-identity colors (m-opus/m-sonnet/m-haiku), and brand accent | Must | Use OKLCH values from the handoff; do not invent equivalents |
| FR-102 | Implement base UI primitives: `Panel`, `Tile`, `Chip`, `Btn`, `BtnGhost`, `BtnPrimary`, `Dot`, `StatusPill`, `ArtifactChip`, `MetricTile`, `SectionHeader`, `Spark`, `ExecBtn` as React components in `components/Planning/primitives/` | Must | Map 1:1 from `primitives.jsx` + inline usage in the deck |
| FR-103 | Implement `STATUS_TOKENS` mapping covering: idea, shaping, ready, draft, approved, in-progress, blocked, completed, superseded, future, deprecated | Must | Used in pills, graph, detail, DAG |
| FR-104 | Typography: apply Geist (sans), JetBrains Mono (mono), and Fraunces (serif/italic for h1/h2 headers) via `@font-face` or Google Fonts import in the planning route; fall back to system fonts | Should | Load only on `/planning` route to avoid bundle bloat |
| FR-105 | Density modes: `comfortable` (row-h 44px, gap 16px) and `compact` (row-h 34px, gap 10px) togglable per user session preference | Could | Stored in localStorage |

#### Surface 2: Three-column shell and top bar

| ID | Requirement | Priority | Notes |
|----|-------------|----------|-------|
| FR-201 | App rail (64px sticky sidebar) with icon buttons for Dashboard / Planning (active) / Sessions / Analytics / Codebase / Trackers; active item highlighted with brand color ring; nav is visual only — routing stays in existing `App.tsx` | Must | Do not break existing nav |
| FR-202 | Top bar: breadcrumb (`CCDash / CCDash · Planning / Planning Deck`), live-agent status pill (running count, thinking count, live/idle toggle indicator), global search button (⌘K, opens existing search), "New spec" primary CTA | Must | Live counts read from existing live-agent context |
| FR-203 | Main canvas: max-width 1680px, padding 22px top/bottom 28px left/right, scroll-independent from rail | Must | |

#### Surface 3: Planning Deck hero header and metrics strip

| ID | Requirement | Priority | Notes |
|----|-------------|----------|-------|
| FR-301 | Hero header: eyebrow (`ccdash · planning — ai-native sdlc`), serif italic h1 ("The Planning Deck."), subtitle text, and right-side corpus stats (date, ctx/phase, spark chart, tokens-saved percentage) | Must | Corpus stats from `GET /api/planning/summary` or derived client-side from existing metrics |
| FR-302 | Metrics strip: 6 tiles in a grid — Features (total), Active (plan color), Blocked (error color), Stale (warn color), Mismatches (mag color), Completed (ok color) | Must | Counts from existing `PlanningQueryService` / `GET /api/planning/summary` |
| FR-303 | Artifact composition chip row: one chip per artifact type (SPEC/SPIKE/PRD/PLAN/PHASE/CTX/TRK/REP), each showing type glyph + short label + count; chips are colored with artifact-identity colors; row ends with corpus corpus summary text | Must | Counts from existing planning summary; clicking a chip navigates to `/planning/artifacts/:type` |

#### Surface 4: Triage inbox

| ID | Requirement | Priority | Notes |
|----|-------------|----------|-------|
| FR-401 | Triage inbox panel with tabbed filter strip: All / Blocked / Mismatches / Stale / Ready-to-promote; each tab shows count badge | Must | Derived from existing `TriageService` or backend triage endpoint |
| FR-402 | Each triage row: severity bar (3px wide, color by severity), kind badge (BLOCKED/MISMATCH/STALE/READY), feature slug, title/description, primary action button + chevron; clicking title opens feature detail | Must | Actions: Remediate, Dismiss, Promote to PRD, Assign PM, Archive, Resume shaping |
| FR-403 | Empty state: green check + "Nothing to triage." message when filtered list is empty | Must | |
| FR-404 | Triage rows for high-severity open questions: surface OQ-ID, question text, owner, severity; primary action "Resolve" opens feature detail scrolled to OQ section | Should | Requires OQ data in planning summary payload |

#### Surface 5: Live agent roster

| ID | Requirement | Priority | Notes |
|----|-------------|----------|-------|
| FR-501 | Agent roster panel alongside triage (two-up layout, 1.3fr triage / 1fr roster); columns: state dot, agent name + model/tier, current task, since; rows colored by state (running=ok, thinking=info, queued=warn, idle=dim) | Must | State dot glows (box-shadow) for running/thinking; opaque when roster paused |
| FR-502 | Live/paused toggle chip in section header; when paused, roster rows are 50% opacity | Should | Reads from existing live-update infrastructure |

#### Surface 6: Planning graph (reskin + enhancements)

| ID | Requirement | Priority | Notes |
|----|-------------|----------|-------|
| FR-601 | Lane header row: Feature column (240px sticky) + lanes for Design Spec / SPIKE / PRD / Impl Plan / Progress / Context+Report / Effort·Tokens; lane header has colored square glyph with CSS glow; lane headers sticky | Must | |
| FR-602 | Feature cell: category badge (color-coded) + complexity chip + mismatch/stale indicators (⚑ mag / ◷ warn); title (2-line clamp); status pill + slug | Must | |
| FR-603 | Lane cells support multiple stacked DocChips per artifact (e.g., 2 specs, 2 PRDs, 2 plans); DocChip shows type label + title truncated + status dot; completed/superseded artifacts muted | Must | Requires backend to return arrays of artifacts per type per feature |
| FR-604 | Progress lane: PhaseStackInline — row of PhaseDots (14×14, filled=completed, pulsing ring=in-progress, ! =blocked) with completed/total count | Must | |
| FR-605 | Effort+Tokens totals lane (TotalsCell): story-points large number, total tokens right-aligned, stacked model-identity bar (opus/sonnet/haiku proportional widths), per-model token counts with colored dots | Must | Token rollup sourced from `FeatureForensicsQueryService` (`feature_forensics.py:324`, `FeatureForensicsDTO.total_tokens` + `linked_sessions[*].{model, total_tokens}`) — actual session-forensics values, grouped by model identity via `backend/model_identity.py` |
| FR-606 | SVG edge layer: animated dashed flow edges for active features (brand color), static edges for inactive; per-feature row edges connect existing lane cells | Must | |
| FR-607 | Selected row highlight: brand-tinted background + 3px left border; clicking a row opens feature detail drawer | Must | |
| FR-608 | Graph filter controls: "All categories" filter button (dropdown: features / enhancements / refactors / spikes); "New feature" button (stub, shows toast for now) | Should | |
| FR-609 | Artifact legend below graph showing color swatch + label for each artifact type; animated flow edge example with label "active edge" | Must | |

#### Surface 7: Feature detail drawer

| ID | Requirement | Priority | Notes |
|----|-------------|----------|-------|
| FR-701 | Drawer: fixed right panel, `min(920px, 64vw)` wide, bg-1 background, border-left line-2, box-shadow; header has category/slug breadcrumb, mismatch pill, serif h1 title, raw→effective status pills, complexity chip, tags, Execute CTA, Close button | Must | |
| FR-702 | Lineage strip: one clickable tile per artifact type (SPEC/SPIKE/PRD/PLAN/PHASE/CTX/REPORT); tile shows type label, count ×N, status pill (representative), PhaseDot stack for PHASE type; clicking scrolls to relevant section and opens it | Must | |
| FR-703 | Collapsible sections: each section has a color-coded left border (artifact color), eyebrow, bold title with count, chevron toggle, optional right slot for view mode controls | Must | |
| FR-704 | SPIKEs + Open Questions section (spec color): two-column grid — SPIKEs list (tile with SPIKE ID, title, status pill, hover-reveal ExecBtn) and Open Questions list (OQ tile with severity bar, OQ ID, question text, "+ answer…" inline editor with textarea, Cmd+Enter to resolve, escape to cancel, answer persists in component state and emits write-back request) | Must | OQ write-back: `PATCH /api/planning/features/:id/open-questions/:oq_id` — NEW endpoint needed |
| FR-705 | PRD section (prd color, only shown when ≥2 PRDs): list of PRD tiles with ID, title, updated date, status pill | Should | |
| FR-706 | Execution tasks section (plan color): segment control "Batches" / "Dependency DAG"; in Batches view: ModelLegend strip + per-PhaseCard list | Must | |
| FR-707 | PhaseCard: phase header (PHASE N, name, status, "run phase" ExecBtn, progress bar + % and pts/tokens); per-batch BatchCol (parallel label, task count, ExecBtn); per-task TaskRow (task ID, title, agent chip with model color, token display, status pill, hover-reveal ExecBtn) | Must | |
| FR-708 | ModelLegend: shows opus/sonnet/haiku color dots + label + token count + %, total pts + tokens right-aligned | Must | Per-model token counts sourced from feature-forensics session aggregation (see FR-605); displayed as actuals, not estimates |
| FR-709 | Dependency DAG view: absolute-positioned SVG canvas; nodes arranged by phase (horizontal bands) and batch (columns); SVG cubic bezier edges with arrowheads; active edges animated (flow dashes); blocked edges red; legend for edge states | Must | Per-feature phases + task deps from existing phase payload |
| FR-710 | Agent activity section (bottom of drawer): live agent rows filtered to feature context, showing state dot, agent name, state, task, since | Should | Existing live-agent data filtered by feature slug |
| FR-711 | Exec toast: bottom-center fixed toast showing dispatched action label (e.g., "▶ running Phase 02 — Service layer") with brand dot; auto-dismisses after 2.4s | Must | Client-side only for now; actual execution wired to existing batch launch API |

#### Surface 8: Cross-surface search and filter

| ID | Requirement | Priority | Notes |
|----|-------------|----------|-------|
| FR-801 | Global search (⌘K) on planning surface opens existing search overlay, pre-filtered to planning artifacts | Should | Reuse existing search infrastructure |
| FR-802 | showCompleted toggle: filter planning graph to hide/show completed features; stored per session | Should | |

### 6.2 Non-functional requirements

**Performance:**
- Initial load of `/planning` route: TTI ≤ 2s on local dev stack (consistent with v1 budget).
- Planning graph with ≤50 features: first render ≤ 500ms; with ≤200 features: ≤1.5s (virtualize if needed).
- Feature detail drawer open: ≤ 150ms to visible content.
- Font loading (Geist/Mono/Fraunces): non-blocking; swap strategy with system fallbacks.

**Accessibility:**
- All interactive elements (drawer, triage rows, graph rows, PhaseCards, BatchCols, TaskRows, ExecBtns) must be keyboard-navigable (Tab order, Enter/Space activation).
- Focus ring: 2px solid brand color at 60% alpha, 2px offset (from handoff CSS `.focus-visible` rule).
- StatusPills, ArtifactChips, and model-identity elements must not rely on color alone — include text labels.
- Drawer close button must have accessible name. Triage action buttons must have accessible names.
- Screen reader: planning graph table must use `<table>` semantics or ARIA grid roles with row/column headers.
- WCAG 2.1 AA target for all new surfaces.

**Dark-theme-only:**
- All token values are dark-mode-only (OKLCH low-lightness surfaces). No light-mode variant required. No `prefers-color-scheme` logic needed.

**Responsive behavior:**
- Primary breakpoint: ≥1280px (standard desktop). Below 1280px: feature detail drawer narrows to `min(640px, 95vw)`; planning graph enables horizontal scroll. No mobile layout required.

**Observability:**
- OpenTelemetry spans for new backend endpoints (`/api/planning/features/:id/open-questions/:oq_id`).
- Frontend: track triage action clicks, exec button dispatches, and OQ resolve events via existing analytics service.

---

## 7. Scope

### In scope

- Visual reskin of all `/planning` route surfaces to match the handoff token system and component inventory.
- New/enhanced UI surfaces: metrics strip, artifact chip row, triage inbox, live agent roster, graph totals lane (with actual session-forensics tokens), graph filter controls, artifact legend.
- Enhanced feature detail drawer: SPIKEs section, OQ inline resolution, model legend, dependency DAG, per-task/batch/phase exec buttons, exec toast.
- New backend endpoint for OQ write-back (`PATCH /api/planning/features/:id/open-questions/:oq_id`).
- Token/effort rollup surfacing backed by actual session-forensics totals: feature payload extended with per-model token breakdown derived from `FeatureForensicsQueryService` linked sessions grouped via `backend/model_identity.py` (no client-side estimation).
- Design token CSS extraction and Tailwind mapping.
- Primitive component extraction to `components/Planning/primitives/` (StatusPill, ArtifactChip, MetricTile, etc.).
- A11y hardening of new surfaces to WCAG 2.1 AA.
- Test coverage for all new/changed surfaces.

### Out of scope

- New backend data sources beyond OQ write-back and token rollup aggregation.
- Auth, tenancy, or multi-user support.
- Mobile / responsive layout below 1280px (beyond horizontal scroll on graph).
- Collaborative cursors or real-time co-presence.
- Server-sent event streaming for live agent roster updates (deferred — see DEFER-01).
- Actual SPIKE execution wiring to a runner (ExecBtn dispatches toast only — deferred — see DEFER-02).
- Actual OQ frontmatter file write-back persistence (write-back endpoint returns 200; file-system persistence is a separate effort — see DEFER-03).
- Collab / comment threads on planning artifacts.
- Light-mode theming.

---

## 8. Dependencies & assumptions

### Internal dependencies

- **control-plane-v1** (status: completed): All eight phases shipped. Routes `/planning`, `/planning/feature/:featureId`, `/planning/artifacts/:type` exist. Components `PlanningHomePage`, `PlanningGraphPanel`, `PlanningNodeDetail`, `TrackerIntakePanel`, `PlanningLaunchSheet`, `PhaseOperationsPanel`, `ArtifactDrillDownPage` exist and will be reskinned and enhanced, not replaced.
- **`backend/application/services/agent_queries/`** (agent_queries surface): Assumed stable. Planning query service returns feature list with artifact arrays (specs[], prds[], plans[], ctxs[], reports[]), spikes[], openQuestions[], phases[], and mismatch/stale/readyToPromote flags. If current response shape does not include all of these, extension is in scope (FR-603).
- **`backend/routers/features.py`** and **`backend/routers/live.py`**: Existing live invalidation infrastructure used for live agent roster and planning invalidation topics.
- **`@miethe/ui`**: No new extractions required in this wave (v1 Phase 7 completed extraction). If new primitives are added in this wave that qualify for extraction, that is explicitly deferred.
- **Font assets**: Google Fonts CDN (Geist, JetBrains Mono, Fraunces); acceptable in dev and production for local-first app. If offline use is required, fonts must be bundled — deferred (DEFER-04).

### Assumptions

- The design handoff is authoritative for visual decisions. Where implementation constraints require deviation (e.g., OKLCH not fully supported in all browsers — use CSS custom properties with fallbacks), the deviation must be documented.
- Backend feature payload already includes or can cheaply include: per-feature artifact arrays by type, spike list, openQuestions list, phase list with tasks, and mismatch/stale/readyToPromote derived fields. This was introduced in v1; v2 assumes it is stable.
- Token/effort rollup is sourced from existing session forensics: `FeatureForensicsQueryService` already correlates sessions to features (`backend/application/services/agent_queries/feature_forensics.py:266` via links repository) and returns `total_tokens` plus per-session `{model, total_tokens}`. A small backend extension (Phase 7) aggregates this into a per-feature `tokenUsageByModel` field keyed by model family (opus/sonnet/haiku/other) using `backend/model_identity.py`. No client-side estimation.
- `CCDASH_LIVE_AGENTS` data is already available from the existing live-update context for the agent roster display.
- OQ write-back endpoint (`PATCH`) returns 200/accepted and triggers a filesystem deferred write; actual frontmatter write-through is out of scope for this wave.

### Feature flags

- `CCDASH_PLANNING_V2_ENABLED`: gates the reskinned planning surface; when false, v1 layout renders.
- `CCDASH_PLANNING_OQ_WRITEBACK_ENABLED`: gates the inline OQ resolution write-back endpoint.

---

## 9. Risks & mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Design/code token drift — OKLCH CSS variables require modern browser support; older Chromium in Electron may not support `oklch()` or `color-mix()` | High | Medium | Add PostCSS plugin to convert OKLCH to sRGB fallbacks; test in target Chromium version; document minimum version |
| Scope creep into net-new backend data sources — exec buttons on tasks imply actual execution wiring | High | High | Exec buttons are wired to toast only in v2; actual dispatch integration is a separate feature (DEFER-02). All exec surfaces must clearly indicate "dispatch queued" not "execution started" |
| Parity-vs-pragmatism tension — perfect pixel parity is expensive; some handoff elements are prototype artifacts | Medium | Medium | Establish per-surface parity thresholds (see AC). Accept ~5% deviation for elements not visible at 1x zoom. Track deviations in a "known delta" list |
| OQ write-back data integrity — resolving an OQ in-app without guaranteed frontmatter sync can create UI/file divergence | Medium | Medium | Mark OQ state as "pending-sync" in UI until round-trip confirms; do not remove raw status from payload; fallback to re-fetch on sync event |
| Performance regression from font loading and OKLCH painting — three Google Fonts families + CSS custom properties paint cost | Medium | Low | Load fonts with `display: swap`; measure paint timings before/after; cap font weights to those actually used |
| @miethe/ui API drift — primitives in this wave may conflict with already-extracted components | Low | Low | Keep new primitives in `components/Planning/primitives/` (local scope); extraction evaluation deferred to post-ship |

---

## 10. Target state

After v2 ships:

**User experience:**
- Opening `/planning` presents "The Planning Deck" — a rich operational overview with hero header, 6 live metrics tiles, 8 artifact-type composition chips, a triage inbox (filterable by blocked/mismatch/stale/ready), and a live agent roster, all above the planning graph.
- The planning graph shows each feature as a row with per-artifact-type lane cells (multiple stacked chips per lane, color-coded), animated flow edges for active features, a phase dot stack in the progress lane, and a totals lane with effort points, token count, and model-identity bar.
- Clicking a feature row opens a slide-in detail drawer with: lineage strip (clickable artifact tiles), collapsible SPIKEs + Open Questions section (with inline OQ answer editor), collapsible execution tasks section (batches view with per-phase/batch/task exec buttons, model legend, and token counts; switchable to dependency DAG view), and agent activity footer.
- Triage inbox actions (Remediate, Promote, Archive) provide immediate feedback (toast) and trigger background planning graph refresh.
- OQ "answer" button opens an inline textarea; resolving writes the answer to the server and marks the question resolved in-app.

**Technical architecture:**
- `components/Planning/primitives/` contains all design-system primitives (Panel, Tile, StatusPill, ArtifactChip, MetricTile, Spark, ExecBtn, DocChip, PhaseDot, PhaseStackInline, TotalsCell, ModelLegend).
- `planning-tokens.css` (or Tailwind config extension) owns the OKLCH custom property definitions.
- Feature detail drawer state is managed locally in `PlanningNodeDetail.tsx`; OQ resolution fires a PATCH via `services/planning.ts`.
- The dependency DAG SVG is rendered client-side from phase/task/deps data in the feature payload — no separate API call.

---

## 11. Acceptance criteria

### AC by surface

| Surface | Acceptance criterion |
|---------|----------------------|
| Token system | All OKLCH custom properties defined; StatusPill renders correct color for all 11 status values; model-identity dots show opus/sonnet/haiku colors |
| Shell | App rail renders with correct active state on Planning item; top bar shows live count, breadcrumb, search button, "New spec" CTA |
| Hero header | Serif italic h1 visible; corpus stats render (total, ctx/phase); spark chart visible and animated |
| Metrics strip | 6 tiles visible; each tile shows correct count from backend; correct accent colors |
| Artifact chips | 8 chips visible with correct counts; clicking chip navigates to `/planning/artifacts/:type` |
| Triage inbox | All 4 filter tabs present; Blocked tab shows blocked task items; Mismatch tab shows status-mismatch features; Stale tab shows features stale > 30d; Ready tab shows readyToPromote features; empty state shows check |
| Agent roster | Rows render with state dots; running/thinking dots glow; live/paused toggle dims rows |
| Planning graph | Feature column 240px; 7 lane columns; DocChips render for multi-artifact features; PhaseStackInline shows PhaseDots; TotalsCell shows pts and **server-provided actual tokens from session forensics** (total + per-model breakdown via stacked bar); animated edges for in-progress features |
| Feature detail — header | Mismatch pill visible when present; raw→effective arrow shown when they differ; complexity + tag chips |
| Feature detail — lineage | 7 artifact tile buttons; muted tiles for empty types; clicking tile scrolls and opens section |
| Feature detail — SPIKEs | SPIKE tiles with ID, title, status, hover exec button; exec button fires toast |
| Feature detail — OQs | OQ tiles with severity bar; "+ answer…" button opens textarea; Cmd+Enter saves; saved answer renders with ok background |
| Feature detail — batches | ModelLegend strip populated from **server-provided actuals (session-forensics tokens grouped by model family)** — not client-side estimates; PhaseCards with BatchCols; TaskRow per task showing agent chip with model color, token count, status pill; exec buttons fire toast |
| Feature detail — DAG | Switching to DAG renders SVG canvas with nodes (phase bands, batch columns) and cubic edges; blocked edges red; active edges animated |
| Exec toast | Toast appears bottom-center within 50ms of exec action; auto-dismisses in 2.4s |
| A11y | All interactive elements have visible focus ring; planning graph rows have ARIA roles; all color-only status elements have text labels; screen reader can read feature title in graph row |
| Performance | Planning home TTI ≤ 2s; graph with 20 features renders ≤ 500ms; detail drawer opens ≤ 150ms |
| OQ write-back | Resolving an OQ fires PATCH request; response 200 → question shows resolved state; response error → error toast |

---

## 12. Assumptions & open questions

### Open questions

- [ ] **OQ-01**: Does the backend already return `spikes[]` and `openQuestions[]` arrays in the feature planning payload from `PlanningQueryService`, or do those fields need to be added? If not present, this is a backend extension task.
  - **A:** TBD — implementation planner to audit `backend/application/services/agent_queries/` before Phase 1.

- [x] **OQ-02**: Token rollup — is client-side token estimation (base cost × points × agent-model) acceptable for the v2 telemetry tiles, or does the backend need to return actual session-linked token counts?
  - **A:** **Resolved — use actual token counts from existing session forensics.** `FeatureForensicsQueryService` already correlates sessions to features (`backend/application/services/agent_queries/feature_forensics.py:324`) and returns `FeatureForensicsDTO.total_tokens` plus per-session `{model, total_tokens}` on `linked_sessions[*]`. Phase 7 adds a thin per-feature `tokenUsageByModel` aggregation (grouping linked sessions via `backend/model_identity.py:29`) so the Planning graph TotalsCell and Feature detail ModelLegend render server-authoritative actuals. No client-side estimation.

- [ ] **OQ-03**: Geist font license — is using Google Fonts CDN acceptable for local-first deployment, or should fonts be bundled? This affects whether font loading is non-blocking or requires a one-time download step.
  - **A:** TBD — default to CDN; add bundling as a follow-up if offline use is required.

- [ ] **OQ-04**: The design shows a "New spec" primary CTA in the top bar. Should clicking it open a creation flow (new design_spec file template), or is it a stub that shows a "coming soon" toast for v2?
  - **A:** Stub with toast for v2. Full creation flow is DEFER-06.

---

## 13. Deferred items

| ID | Description | Implied by | Why deferred |
|----|-------------|------------|--------------|
| DEFER-01 | SSE streaming for live agent roster updates | Agent roster, live-state | Complex infra; roster can poll until live updates are stable |
| DEFER-02 | Actual SPIKE / phase / batch / task execution wiring | ExecBtn dispatch | Depends on execution connector roadmap (phase 5 v1 incomplete providers) |
| DEFER-03 | OQ frontmatter write-through to filesystem | OQ inline resolution | File-system mutation from API is a separate concern; v2 ships endpoint stub |
| DEFER-04 | Bundled font assets for offline use | Typography | Not needed for local dev target; add if offline deployment is required |
| ~~DEFER-05~~ | ~~Session-linked actual token counts (vs estimated)~~ | **Promoted to v2 scope (2026-04-20):** feature↔session correlation already exists in `FeatureForensicsQueryService`; Phase 7 exposes per-feature + per-model actuals. No remaining deferred work. | — |
| DEFER-06 | "New spec" creation flow | Top bar CTA | Out of scope for reskin wave; add in a future creation-workflow PRD |
| DEFER-07 | @miethe/ui extraction of v2 Planning primitives | New component inventory | Follow v1 Phase 7 extraction process; evaluate after 2-week stability window |
| DEFER-08 | Collab / comment threads on planning artifacts | Implied by OQ thread UI | Multi-user collaboration requires auth/tenancy work out of scope |
| DEFER-09 | Light-mode variant of planning token system | Design handoff is dark-only | No light-mode design exists; out of scope |
| DEFER-10 | Planning graph virtualization for >200 features | OQ-10 from design data | Sufficient for current project scale; revisit when feature count exceeds 100 |

---

## Implementation phases (lightweight)

The implementation planner should expand these into a full phased plan. Suggested structure:

**P0 — Design tokenization and primitive inventory** (3–4 days)
- Extract OKLCH tokens to `planning-tokens.css` and `tailwind.config.js`.
- Implement all base primitive components in `components/Planning/primitives/`.
- Audit backend planning payload for `spikes[]`, `openQuestions[]`, and artifact array completeness (resolve OQ-01).

**P1 — Shell, top bar, and hero header reskin** (2–3 days)
- Reskin app rail active state, top bar, breadcrumb, and live-status pill.
- Implement hero header with corpus stats and spark chart.
- Apply new typography (Geist/Mono/Fraunces).

**P2a — Metrics strip, artifact chips, and planning home layout** (2 days)
- Replace v1 summary cards with metrics strip and artifact composition chip row.
- Wire chip clicks to `/planning/artifacts/:type`.

**P2b — Triage inbox and live agent roster** (3 days)
- Build triage inbox with filterable tabs, triage rows, and action buttons.
- Build agent roster panel.
- Two-up layout with triage 1.3fr / roster 1fr.

**P2c — Planning graph reskin and enhancements** (4–5 days)
- Reskin lane headers, FeatureCell, DocChips, PhaseStackInline, PhaseDots.
- Add TotalsCell with model-identity bar.
- Add animated SVG edge layer.
- Add graph filter controls and legend.

**P3 — Feature detail drawer enhancements** (5–6 days)
- Reskin header (mismatch pill, raw→effective, serif title).
- Implement lineage strip with scroll-to-section behavior.
- SPIKEs section with exec buttons.
- OQ inline resolution editor and write-back endpoint.
- Model legend strip.
- Dependency DAG SVG view.
- Per-batch/task exec buttons and exec toast.

**P4 — Backend extension for OQ write-back** (1–2 days)
- Add `PATCH /api/planning/features/:id/open-questions/:oq_id` endpoint.
- Transport-neutral service method in `agent_queries/`.

**P5 — A11y hardening and performance** (2–3 days)
- Keyboard navigation audit for all new surfaces.
- ARIA roles for planning graph.
- Color-only fallback text labels.
- Font performance (display: swap, preconnect).
- Planning graph render timing benchmarks.

**P6 — Testing, CHANGELOG, and documentation** (2–3 days)
- Unit tests for all new primitives.
- Integration tests for OQ write-back.
- Visual parity checklist validation per surface.
- CHANGELOG `[Unreleased]` entry.
- Update `docs/guides/` if any operator guidance changes.

---

## Appendices & references

- **Design bundle:** `docs/project_plans/designs/ccdash-planning/project/Planning Deck.html` (primary visual truth)
- **App shell:** `docs/project_plans/designs/ccdash-planning/project/app/app.jsx`
- **Data model:** `docs/project_plans/designs/ccdash-planning/project/app/data.jsx`
- **Primitives:** `docs/project_plans/designs/ccdash-planning/project/app/primitives.jsx`
- **Graph:** `docs/project_plans/designs/ccdash-planning/project/app/graph.jsx`
- **Feature detail:** `docs/project_plans/designs/ccdash-planning/project/app/feature_detail.jsx`
- **Triage:** `docs/project_plans/designs/ccdash-planning/project/app/triage.jsx`
- **Tweaks:** `docs/project_plans/designs/ccdash-planning/project/app/tweaks.jsx`
- **v1 implementation plan:** `docs/project_plans/implementation_plans/enhancements/ccdash-planning-control-plane-v1.md`
- **v1 PRD:** `docs/project_plans/PRDs/enhancements/ccdash-planning-control-plane-v1.md`

---

**Progress tracking:** `.claude/progress/ccdash-planning-reskin-v2/` (to be created by implementation planner)
