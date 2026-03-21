---
schema_name: ccdash_document
schema_version: 3
doc_type: implementation_plan
doc_subtype: implementation_plan
primary_doc_role: supporting_document
status: completed
category: refactors
title: 'Implementation Plan: CCDash Theme System Foundation V1'
description: Refactor CCDash UI styling from dark-only palette composition to a semantic
  token-driven architecture that can safely support standard theme modes and later
  user-defined themes.
summary: Establish the semantic styling contract, shared primitives, chart theming
  layer, and migration guardrails required before dark/light/system or custom theming
  work begins.
author: codex
audience:
- ai-agents
- developers
- fullstack-engineering
- frontend-platform
created: 2026-03-19
updated: '2026-03-21'
tags:
- implementation
- refactor
- theming
- tailwind
- ui
- design-system
priority: high
risk_level: high
complexity: high
track: UI Platform
timeline_estimate: 4-6 weeks across 6 phases
feature_slug: ccdash-theme-system-foundation-v1
feature_family: ccdash-theme-system-modernization
feature_version: v1
lineage_family: ccdash-theme-system-modernization
lineage_parent:
  ref: docs/project_plans/PRDs/refactors/ccdash-theme-system-modernization-v1.md
  kind: implementation_of
lineage_children:
- docs/project_plans/implementation_plans/enhancements/ccdash-standard-theme-modes-v1.md
lineage_type: refactor
linked_features: []
related_documents:
- docs/project_plans/reports/ccdash-theme-system-feasibility-and-migration-report-2026-03-19.md
- docs/project_plans/reports/ccdash-theme-foundation-phase-1-token-inventory-and-contract-2026-03-20.md
- docs/project_plans/reports/ccdash-theme-foundation-phase-2-primitives-2026-03-20.md
- docs/project_plans/reports/ccdash-theme-color-exceptions-2026-03-20.md
- docs/project_plans/reports/ccdash-theme-foundation-phase-6-guardrails-and-handoff-2026-03-21.md
- docs/project_plans/PRDs/refactors/ccdash-theme-system-modernization-v1.md
- docs/project_plans/implementation_plans/enhancements/ccdash-standard-theme-modes-v1.md
context_files:
- index.tsx
- src/index.css
- tailwind.config.js
- components/Layout.tsx
- components/Dashboard.tsx
- components/Analytics/AnalyticsDashboard.tsx
- components/Analytics/TrendChart.tsx
- components/content/UnifiedContentViewer.tsx
- components/Settings.tsx
- components/featureStatus.ts
---

# Implementation Plan: CCDash Theme System Foundation V1

## Objective

Convert CCDash from a palette-literal dark UI into a semantic token-driven frontend architecture while preserving the current dark appearance as the default visual baseline. This plan does not ship user-facing light mode yet. Its job is to make the app structurally ready for that next step.

## Scope And Fixed Decisions

In scope:

1. Expand the app-wide semantic theme contract beyond the current shadcn defaults.
2. Replace repeated shell, surface, badge, alert, and state formulas with shared primitives or variants.
3. Remove dark-only global CSS escape hatches by moving them onto token-backed styling.
4. Add a centralized chart theme layer.
5. Migrate the highest-leverage product surfaces from palette literals to semantic tokens.
6. Add tests, rules, or review guardrails to discourage regression on shared surfaces.

Out of scope:

1. Shipping user-facing `light` or `system` mode.
2. Building a custom theme editor.
3. Reworking all domain-specific inline color use cases.

Non-negotiables:

1. The default appearance should remain visually close to current dark mode during this plan.
2. Shared surfaces must migrate before page-specific edge cases.
3. Chart theming must be centralized, not fixed ad hoc.

## Proposed Theme Contract Targets

Introduce or formalize semantic roles for:

1. `app-background`, `app-foreground`
2. `panel`, `panel-foreground`, `panel-border`
3. `sidebar`, `sidebar-foreground`, `sidebar-accent`
4. `surface-muted`, `surface-elevated`, `surface-overlay`
5. `success`, `warning`, `danger`, `info`, plus foreground/border companions
6. `chart-grid`, `chart-axis`, `chart-tooltip`, `chart-tooltip-foreground`
7. `selection`, `focus`, `hover`, and `disabled`

The exact variable names can vary, but the contract must be broad enough that future theme changes do not require page-level palette surgery.

## Phase Overview

| Phase | Title | Effort | Duration | Critical Path | Objective |
|------|-------|--------|----------|---------------|-----------|
| 1 | Semantic Theme Contract | 8 pts | 3-4 days | Yes | Expand and document the token vocabulary |
| 2 | Global CSS And Shared Primitive Refactor | 10 pts | 4-5 days | Yes | Tokenize globals and add reusable UI building blocks |
| 3 | Status, Alert, And Chart Infrastructure | 10 pts | 4-5 days | Yes | Centralize color semantics and chart defaults |
| 4 | Shell And Shared Surface Migration | 10 pts | 4-5 days | Yes | Migrate layout, settings shell, content viewer, and shared surfaces |
| 5 | Feature Surface Migration Waves | 14 pts | 1.5 weeks | Yes | Migrate high-traffic feature pages away from palette literals |
| 6 | Guardrails, Validation, And Handoff | 8 pts | 3-4 days | Final gate | Lock in the contract and prepare the theme-modes plan |

**Total**: ~60 story points over 4-6 weeks

## Implementation Strategy

### Critical Path

1. Define the semantic contract before creating new components.
2. Tokenize globals and shared components before migrating feature pages.
3. Centralize chart and status semantics before touching chart-heavy screens.
4. Migrate shell and reusable surfaces before monolithic feature files.
5. End with validation and guardrails so the next plan inherits a stable base.

### Parallel Work Opportunities

1. Phase 3 chart infrastructure can begin once Phase 1 finalizes naming and token semantics.
2. Phase 4 shared surface migration and Phase 5 feature-page migration can overlap once primitives are stable.
3. Documentation and lint/test guardrails can be added incrementally after each migration wave.

### Migration Order

1. Tokens and globals
2. Shared primitives
3. Layout and content viewer
4. Status/alert/chart infrastructure
5. High-leverage screens: Dashboard, Analytics, Settings, Test Visualizer shells
6. Monolithic screens: FeatureExecutionWorkbench, ProjectBoard, SessionInspector

## Phase 1: Semantic Theme Contract

**Assigned Subagent(s)**: frontend-platform, ui-engineer-enhanced

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| THEME-001 | Token Inventory | Audit current token usage, palette-literal hotspots, and global CSS bypasses. | Token inventory and migration map exist for shell, surfaces, status states, charts, and viewer surfaces. | 2 pts | frontend-platform | None |
| THEME-002 | Semantic Role Design | Define the semantic token vocabulary needed beyond current shadcn defaults. | Contract covers shell, panels, state colors, charts, overlays, and content surfaces. | 3 pts | ui-engineer-enhanced, frontend-platform | THEME-001 |
| THEME-003 | Tailwind Mapping Plan | Define how new semantic roles map into CSS variables and Tailwind utilities. | Tailwind extension approach is agreed and documented. | 3 pts | frontend-platform | THEME-002 |

**Phase 1 Quality Gates**

1. Semantic token contract is broad enough to express all current repeated surface patterns.
2. Status and chart semantics are explicitly included, not deferred.
3. Future theme-mode work can consume this contract without reopening naming.

## Phase 2: Global CSS And Shared Primitive Refactor

**Assigned Subagent(s)**: frontend-developer, ui-engineer-enhanced

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| THEME-101 | Base CSS Tokenization | Move dark-only scrollbar, markdown, overlay, and content-viewer-adjacent global styles onto CSS variables. | `src/index.css` no longer contains dark-only raw values for shared global surfaces without token backing. | 4 pts | frontend-developer | THEME-003 |
| THEME-102 | Shared Surface Primitives | Create reusable surface primitives or class variants for panels, section shells, alerts, and control rows. | Repeated `bg-slate-900 border border-slate-800` patterns are replaceable through shared semantics. | 3 pts | ui-engineer-enhanced, frontend-developer | THEME-003 |
| THEME-103 | Shared Control Standardization | Standardize common button/input/select/chip patterns around semantic variants. | Shared control patterns exist for future migration waves. | 3 pts | ui-engineer-enhanced | THEME-102 |

**Phase 2 Quality Gates**

1. Shared surfaces and common controls have semantic building blocks.
2. Global CSS no longer encodes dark-only assumptions for shared content surfaces.
3. New primitives are documented well enough for broad adoption.

## Phase 3: Status, Alert, And Chart Infrastructure

**Assigned Subagent(s)**: frontend-platform, data-viz-ui, frontend-developer

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| THEME-201 | Status Semantic Layer | Replace raw success/warning/error/info formulas with semantic status variants. | `featureStatus.ts` and shared badge-like systems no longer hard-code product semantics directly to palette literals. | 3 pts | frontend-platform | THEME-102 |
| THEME-202 | Chart Theme Adapter | Build a centralized Recharts theme adapter for grid, axis, tooltip, series defaults, and gradients. | Shared chart config exists and can remove duplicated dark hex values from chart files. | 4 pts | data-viz-ui, frontend-developer | THEME-003 |
| THEME-203 | Dynamic Color Escape-Hatch Rules | Document and codify which inline/data-driven colors remain allowed and how they coexist with base theming. | Model colors and domain-specific accents are clearly separated from app theme tokens. | 3 pts | frontend-platform | THEME-201 |

**Phase 3 Quality Gates**

1. Shared status semantics are token-based.
2. Charts can inherit themed defaults without per-file literal rewrites.
3. Exception paths for data-driven colors are bounded and documented.

## Phase 4: Shell And Shared Surface Migration

**Assigned Subagent(s)**: frontend-developer, ui-engineer-enhanced

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| THEME-301 | App Shell Migration | Migrate `Layout.tsx` and other shell-level surfaces to semantic tokens and shared primitives. | Sidebar, main content surfaces, nav states, and notifications no longer rely on raw palette formulas. | 4 pts | frontend-developer | THEME-201 |
| THEME-302 | Settings And Theme-Adjacent Surface Migration | Migrate `Settings.tsx` shared shells, cards, alerts, and control rows to semantic surfaces. | Theme settings and model color configuration surfaces consume shared semantic primitives. | 3 pts | ui-engineer-enhanced | THEME-103 |
| THEME-303 | Content Viewer Migration | Migrate `UnifiedContentViewer` and markdown wrappers to semantic tokens and global roles. | Content preview surfaces can follow future theme changes without file-local dark rewrites. | 3 pts | frontend-developer | THEME-101 |

**Phase 4 Quality Gates**

1. The app shell is no longer dark-palette locked.
2. The Settings page and content viewer act as examples of the new contract.
3. Shared surfaces are ready for standard theme modes.

## Phase 5: Feature Surface Migration Waves

**Assigned Subagent(s)**: frontend-developer, ui-engineer-enhanced, codebase-janitor

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| THEME-401 | Analytics And Dashboard Wave | Migrate `Dashboard.tsx`, analytics shells, and shared metric cards to semantic surfaces and chart adapter usage. | Dashboard and analytics surfaces no longer depend on dynamic palette strings or chart literals. | 4 pts | frontend-developer | THEME-202 |
| THEME-402 | Testing And Workflow Wave | Migrate test-visualizer and workflow registry surfaces to semantic primitives and status variants. | Test and workflow pages consume shared semantic shells and status semantics. | 4 pts | ui-engineer-enhanced | THEME-201 |
| THEME-403 | Monolithic Page Wave | Migrate the most styling-dense monolithic pages in staged slices: FeatureExecutionWorkbench, ProjectBoard, SessionInspector. | High-risk pages are materially migrated away from repeated palette formulas without visual regressions. | 6 pts | codebase-janitor, frontend-developer | THEME-401 |

**Phase 5 Quality Gates**

1. Core product surfaces now render through semantic contracts.
2. Dynamic palette string construction is removed from shared UI paths.
3. High-traffic screens are no longer the main blocker for theme-mode rollout.

## Phase 6: Guardrails, Validation, And Handoff

**Assigned Subagent(s)**: frontend-platform, qa-engineer, documentation-writer

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| THEME-501 | Guardrails And Review Rules | Add lint guidance, code review rules, or lightweight tests to discourage new palette-literal usage on shared surfaces. | Shared surface regressions are detectable in review or CI. | 3 pts | frontend-platform | THEME-403 |
| THEME-502 | Dark-Parity Validation | Validate that semantic migration preserved intended dark-mode appearance for major surfaces and charts. | Visual parity checklist is completed and deviations are intentional/documented. | 3 pts | qa-engineer | THEME-403 |
| THEME-503 | Theme Modes Handoff | Document resolved token contract, open gaps, and readiness criteria for the standard theme modes plan. | Next plan can begin without re-auditing foundation decisions. | 2 pts | documentation-writer, frontend-platform | THEME-501 |

**Phase 6 Quality Gates**

1. The app is semantically theme-ready even if only dark mode is exposed.
2. Shared surfaces and charts have guardrails against regression.
3. Standard theme modes are unblocked.

## Validation And Test Strategy

1. Snapshot or visual-regression coverage for core shell and shared surfaces.
2. Focused test coverage for chart theme adapter behavior.
3. Manual parity review for markdown, content viewer, tables, alerts, and selected states.
4. Review checklist updates for semantic token usage versus palette-literal exceptions.

## Exit Criteria

This plan is complete when:

1. CCDash shared surfaces are primarily semantic-token driven.
2. Chart theming and status semantics are centralized.
3. Global CSS no longer hard-codes dark-only shared surfaces.
4. The app is structurally ready for `dark`, `light`, and `system` theme delivery.

## Completion Notes

Phase 6 completed on 2026-03-21 with:

1. automated guardrails for the foundation-owned shared semantic files and centralized chart adapter usage
2. a recorded dark-parity validation scope for shell, dashboard, analytics, viewer, and status/chart helpers
3. a follow-on handoff for the standard theme modes plan with remaining non-blocking palette hotspots called out explicitly
