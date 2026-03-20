---
schema_name: ccdash_document
schema_version: 3
doc_type: report
doc_subtype: implementation_report
primary_doc_role: supporting_document
status: active
category: refactors
title: "CCDash Theme Foundation Phase 1 Token Inventory And Contract"
description: "Inventory of palette-literal styling hotspots and the semantic token contract introduced for the theme-system foundation refactor."
summary: "Documents the highest-leverage raw color hotspots, the new semantic token vocabulary, and the Tailwind mapping strategy used to prepare CCDash for later dark/light/system theme delivery."
author: codex
audience: [ai-agents, developers, frontend-platform]
created: 2026-03-20
updated: 2026-03-20
tags: [theming, tokens, tailwind, ui, design-system, report]
feature_slug: ccdash-theme-system-foundation-v1
feature_family: ccdash-theme-system-modernization
feature_version: v1
---

# CCDash Theme Foundation Phase 1 Token Inventory And Contract

## Audit Summary

The current CCDash frontend mixes the default shadcn token set with a large volume of page-local dark palette literals. The most repeated patterns are shell and panel formulas such as `bg-slate-900 border border-slate-800`, control formulas such as `bg-slate-800 hover:bg-slate-700 border-slate-700`, and content-viewer-specific raw RGB values in [`src/index.css`](/Users/miethe/dev/homelab/development/CCDash/src/index.css).

## Highest-Leverage Hotspots

1. Global CSS bypasses in [`src/index.css`](/Users/miethe/dev/homelab/development/CCDash/src/index.css): scrollbars, markdown typography, code blocks, table chrome, and quote styling used raw slate and indigo values.
2. Shared shell formulas in [`components/Layout.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/Layout.tsx) and [`components/content/UnifiedContentViewer.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/content/UnifiedContentViewer.tsx): app background, sidebar surfaces, viewer shells, and header treatments were palette-bound.
3. Repeated panel formulas across feature pages such as [`components/Analytics/AnalyticsDashboard.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/Analytics/AnalyticsDashboard.tsx), [`components/PlanCatalog.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/PlanCatalog.tsx), and [`components/DocumentModal.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/DocumentModal.tsx).
4. Repeated control formulas across buttons, filters, native selects, and chips in settings, sessions, plans, project board, and explorer surfaces.

## Semantic Contract

The foundation contract expands the app beyond the stock shadcn roles and reserves stable names for shell, panel, surface, state, and chart semantics.

| Domain | Semantic Roles | Intended Usage |
|------|------|------|
| App shell | `app-background`, `app-foreground` | Global page background and default foreground |
| Panels | `panel`, `panel-foreground`, `panel-border` | Cards, frames, section shells, drawers, modals |
| Sidebar | `sidebar`, `sidebar-foreground`, `sidebar-accent`, `sidebar-border` | Left-nav shell, active states, flyouts |
| Surface stack | `surface-muted`, `surface-elevated`, `surface-overlay` | Nested containers, elevated sections, overlay surfaces |
| Status | `success`, `success-foreground`, `success-border` | Positive status chips, alerts, summaries |
| Status | `warning`, `warning-foreground`, `warning-border` | Caution states and warnings |
| Status | `danger`, `danger-foreground`, `danger-border` | Destructive and error surfaces |
| Status | `info`, `info-foreground`, `info-border` | Informational alerts and helper UI |
| Chart | `chart-grid`, `chart-axis`, `chart-tooltip`, `chart-tooltip-foreground` | Shared chart chrome and tooltip surfaces |
| Interaction | `selection`, `focus`, `hover`, `disabled`, `disabled-foreground` | Selected states, ring color, hover fills, disabled UI |

## Tailwind Mapping Strategy

The contract is mapped into [`tailwind.config.js`](/Users/miethe/dev/homelab/development/CCDash/tailwind.config.js) as semantic color utilities so future migrations can use stable class names instead of page-local palette formulas.

Preferred utility families:

1. `bg-app-background`, `text-app-foreground`
2. `bg-panel`, `text-panel-foreground`, `border-panel-border`
3. `bg-sidebar`, `text-sidebar-foreground`, `bg-sidebar-accent`, `border-sidebar-border`
4. `bg-surface-muted`, `bg-surface-elevated`, `bg-surface-overlay`
5. `bg-success`, `text-success-foreground`, `border-success-border`
6. `bg-warning`, `text-warning-foreground`, `border-warning-border`
7. `bg-danger`, `text-danger-foreground`, `border-danger-border`
8. `bg-info`, `text-info-foreground`, `border-info-border`
9. `border-chart-grid`, `text-chart-axis`, `bg-chart-tooltip`, `text-chart-tooltip-foreground`

## Migration Guardrails

1. Shared surfaces should prefer semantic tokens even if feature pages still contain palette literals.
2. Raw palette literals remain temporarily acceptable only for domain-driven color data and one-off data visualization accents.
3. New shared CSS should consume variables first, not hard-coded RGB, hex, or slate utilities.
4. Future theme-mode work should layer mode switching by changing variables, not by rewriting component classes.
