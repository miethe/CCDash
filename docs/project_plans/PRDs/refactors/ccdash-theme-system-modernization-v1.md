---
schema_name: ccdash_document
schema_version: 3
doc_type: prd
doc_subtype: research_prd
status: pending
category: refactors
title: "PRD: CCDash Theme System Modernization V1"
description: "Refactor CCDash from a dark-only, palette-literal UI into a semantic token-driven application that supports standard theme modes and later custom user theming."
summary: "Define the staged program required to establish a theme-system foundation, then deliver dark/light/system modes, then deliver user-defined themes."
created: 2026-03-19
updated: 2026-03-19
priority: high
risk_level: high
complexity: High
track: UI Platform
timeline_estimate: "8-12 weeks across 3 sequential implementation plans"
feature_slug: ccdash-theme-system-modernization-v1
feature_family: ccdash-theme-system-modernization
feature_version: v1
lineage_family: ccdash-theme-system-modernization
lineage_parent: ""
lineage_children: []
lineage_type: refactor
problem_statement: "CCDash has the beginnings of a semantic theme system, but most of the actual product UI is still authored as a hard-coded dark theme, which blocks safe delivery of light mode and makes user-defined app-wide theming impractical."
owner: fullstack-engineering
owners: [fullstack-engineering, frontend-platform]
contributors: [ai-agents]
audience: [ai-agents, developers, fullstack-engineering, frontend-platform]
tags: [prd, ui, theming, tailwind, refactor, dark-mode, light-mode, design-system]
related_documents:
  - docs/project_plans/reports/ccdash-theme-system-feasibility-and-migration-report-2026-03-19.md
  - docs/project_plans/implementation_plans/refactors/ccdash-theme-system-foundation-v1.md
  - docs/project_plans/implementation_plans/enhancements/ccdash-standard-theme-modes-v1.md
  - docs/project_plans/implementation_plans/enhancements/ccdash-custom-theming-v1.md
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
  - contexts/ModelColorsContext.tsx
implementation_plan_ref: docs/project_plans/implementation_plans/refactors/ccdash-theme-system-foundation-v1.md
---

# PRD: CCDash Theme System Modernization V1

## Executive Summary

CCDash needs to evolve from a dark-themed application with partial token support into a true themeable web app. The current frontend already has a semantic token seed in Tailwind and CSS variables, but most of the real UI ignores that layer in favor of copied palette literals, dark-only global CSS, and hard-coded chart colors.

This PRD defines a three-step modernization program:

1. refactor the app so the UI styling contract is semantic and token-driven
2. implement standard theme modes (`dark`, `light`, `system`)
3. implement custom user theming on top of that stable contract

The work must happen in this order. Theme modes and custom themes are product features, but they depend on the foundational refactor that converts the app away from palette-bound styling.

## Context And Background

CCDash already contains encouraging infrastructure:

1. Tailwind semantic color mappings in `tailwind.config.js`
2. light and dark token sets in `src/index.css`
3. shadcn-style component metadata in `components.json`
4. a small set of semantic UI primitives in `components/ui/`

At the same time, the real product surface remains mostly dark-only:

1. `index.tsx` forces `.dark` at startup
2. `src/index.css` pins `color-scheme: dark`
3. shell and feature pages are dominated by direct `slate`, `indigo`, `emerald`, `amber`, and `rose` classes
4. charts and markdown surfaces use raw hex/RGB values
5. large feature files duplicate surface, chip, and alert patterns instead of consuming shared variants

## Problem Statement

As CCDash continues to grow, I need the web app to support a stable, app-wide theme system instead of a dark-only styling convention. Today, the design token infrastructure exists, but the UI itself is not actually built on it. That gap makes light mode expensive, custom theming unreliable, and mass style updates overly risky.

## Goals

1. Establish a semantic theme contract for the entire app UI.
2. Remove hard dependencies on dark-only palette literals from core product surfaces.
3. Make standard theme modes (`dark`, `light`, `system`) a first-class app capability.
4. Enable future user-defined themes through validated token maps and presets.
5. Improve maintainability of mass style updates through shared primitives, variants, and chart theming infrastructure.

## Success Metrics

| Metric | Baseline | Target |
|--------|----------|--------|
| Hard-coded palette utility usage on app surfaces | Dominant | Majority of shared surfaces migrated to semantic tokens |
| Dark-only bootstrap behavior | Forced `.dark` and dark `color-scheme` | Theme resolved from provider, persistence, and system preference |
| Shared primitive adoption | Low | Core shell, alerts, surfaces, badges, and common controls standardized |
| Chart theming consistency | File-by-file literals | Central chart theme adapter backed by tokens |
| App-wide theme mode support | Dark only | Dark, Light, System |
| User-defined theme capability | None | Supported through validated token presets after theme-mode rollout |

## Functional Requirements

| ID | Requirement | Priority | Notes |
|----|-------------|----------|-------|
| FR-1 | Introduce a semantic UI token contract that covers shell, surfaces, text, borders, states, overlays, and charts. | Must | Must extend beyond the current shadcn defaults. |
| FR-2 | Refactor shared and repeated UI patterns to consume semantic primitives and variants instead of copied palette formulas. | Must | Includes panels, alerts, badges, status chips, and common controls. |
| FR-3 | Remove hard-forced dark-mode bootstrap behavior and support resolved theme state at app root. | Must | Required before standard theme modes can ship. |
| FR-4 | Deliver standard theme modes: `dark`, `light`, and `system`. | Must | Requires persistence and first-paint correctness. |
| FR-5 | Theme markdown/content-viewer surfaces, global scrollbars, and overlays from semantic tokens. | Must | These are current dark-only bypasses. |
| FR-6 | Centralize chart styling through token-backed configuration and defaults. | Must | Applies to Recharts surfaces and related chart legends/tooltips. |
| FR-7 | Preserve data-driven accent systems such as model colors while separating them from base app theming. | Should | Prevents conflict between theme tokens and domain colors. |
| FR-8 | Add user-defined theme presets built on validated token maps, not arbitrary CSS injection. | Must | This is the custom theming stage. |
| FR-9 | Wire the existing Settings Theme control into real theme state and persistence. | Must | Existing control is currently placeholder UI only. |

## Non-Functional Requirements

1. Preserve current dark visual intent during the foundation refactor unless a plan explicitly changes product appearance.
2. Avoid a big-bang rewrite; migrate in waves with shared surfaces first.
3. Keep theme rendering stable on first paint and during app boot.
4. Maintain accessible contrast ratios for text, borders, focus states, and data visualizations in both dark and light themes.
5. Add guardrails or tests that reduce regressions back to palette-literal styling on shared surfaces.

## In Scope

1. Theme-system refactor of frontend styling architecture.
2. Standard app theme modes and persistence.
3. Custom user theming based on semantic token presets.
4. Shared primitives and chart theming infrastructure required to support those outcomes.

## Out Of Scope

1. Arbitrary CSS injection or unrestricted user-authored stylesheets.
2. A full visual redesign unrelated to theming architecture.
3. Replacing all data-driven color usage with theme tokens.

## Target State

At the end of this program:

1. The shell and shared UI surfaces render from semantic tokens rather than palette literals.
2. Theme state is resolved centrally and applied before first paint.
3. Dark and light mode are both valid, tested, and visually coherent.
4. Charts, markdown, overlays, and global surfaces follow the same theme contract.
5. Users can choose from standard modes and then optionally apply custom token presets that affect the entire app consistently.

## Sequencing And Dependencies

This program must be delivered as three sequential implementation plans:

1. `docs/project_plans/implementation_plans/refactors/ccdash-theme-system-foundation-v1.md`
   - prerequisite for all later work
   - converts the app to semantic styling contracts and shared theming infrastructure
2. `docs/project_plans/implementation_plans/enhancements/ccdash-standard-theme-modes-v1.md`
   - depends on the foundation plan
   - delivers `dark`, `light`, and `system`
3. `docs/project_plans/implementation_plans/enhancements/ccdash-custom-theming-v1.md`
   - depends on the standard theme modes plan
   - delivers validated user-defined theme presets and customization

## Risks And Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Styling migration churn in monolithic components slows delivery | High | High | Migrate by shared surface class first, then feature waves, and decompose large components where needed. |
| Theme refactor accidentally changes dark-mode visuals too early | Medium | Medium | Keep the foundation plan scoped to semantic parity before introducing new modes. |
| Light mode exposes many hidden contrast and readability issues | High | High | Treat chart, markdown, and status states as explicit validation tracks in the second plan. |
| Custom theming becomes an unbounded CSS feature | High | Medium | Restrict customization to validated semantic token maps and presets. |
| Data-driven accent colors conflict with app theme tokens | Medium | Medium | Keep domain-specific color systems explicitly separated from base app theme state. |

## Acceptance Criteria

1. The project has a documented three-stage roadmap for theme-system modernization.
2. The foundation refactor has a clear contract for semantic UI tokens, shared primitives, and chart theming.
3. Standard theme modes are planned as a dedicated delivery after semantic migration, not mixed into the foundation work.
4. Custom theming is planned as a follow-on capability built on token presets and validated boundaries.
5. The resulting planning artifacts are sufficient to execute the work in succession without reopening sequencing decisions.
