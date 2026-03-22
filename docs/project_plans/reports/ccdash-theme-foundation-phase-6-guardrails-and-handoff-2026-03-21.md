---
schema_name: ccdash_document
schema_version: 3
doc_type: report
doc_subtype: implementation_report
primary_doc_role: supporting_document
status: active
category: refactors
title: 'CCDash Theme Foundation Phase 6 Guardrails and Handoff'
description: Records the automated guardrails, dark-parity validation scope, and theme-mode readiness handoff completed in phase 6 of the theme foundation refactor.
summary: Locks the semantic theme foundation with CI-visible shared-surface checks, documents dark-parity validation scope, and identifies the remaining palette-literal hotspots outside the guarded set.
author: codex
audience:
- ai-agents
- developers
- frontend-platform
- qa-engineering
created: 2026-03-21
updated: '2026-03-21'
tags:
- theming
- ui
- validation
- guardrails
- handoff
feature_slug: ccdash-theme-system-foundation-v1
feature_family: ccdash-theme-system-modernization
feature_version: v1
---

# CCDash Theme Foundation Phase 6 Guardrails and Handoff

## Delivered In Phase 6

1. [`lib/__tests__/themeFoundationGuardrails.test.ts`](/Users/miethe/dev/homelab/development/CCDash/lib/__tests__/themeFoundationGuardrails.test.ts) adds CI-visible protection for the shared semantic theme foundation.
2. [`docs/project_plans/reports/ccdash-theme-color-exceptions-2026-03-20.md`](/Users/miethe/dev/homelab/development/CCDash/docs/project_plans/reports/ccdash-theme-color-exceptions-2026-03-20.md) is now an active policy document and explicitly describes how the automated guardrail should be interpreted.
3. [`.claude/progress/ccdash-theme-system-foundation-v1/phase-6-progress.md`](/Users/miethe/dev/homelab/development/CCDash/.claude/progress/ccdash-theme-system-foundation-v1/phase-6-progress.md) records completion status, guarded scope, and handoff readiness.

## Guarded Foundation Scope

The automated guardrail currently protects the files that should already be foundation-complete and semantically tokenized:

1. [`components/ui/surface.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/ui/surface.tsx)
2. [`components/ui/button.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/ui/button.tsx)
3. [`components/ui/input.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/ui/input.tsx)
4. [`components/ui/select.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/ui/select.tsx)
5. [`components/ui/badge.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/ui/badge.tsx)
6. [`components/Layout.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/Layout.tsx)
7. [`components/Dashboard.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/Dashboard.tsx)
8. [`components/Analytics/AnalyticsDashboard.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/Analytics/AnalyticsDashboard.tsx)
9. [`components/Analytics/TrendChart.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/Analytics/TrendChart.tsx)
10. [`components/content/UnifiedContentViewer.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/content/UnifiedContentViewer.tsx)
11. [`components/featureStatus.ts`](/Users/miethe/dev/homelab/development/CCDash/components/featureStatus.ts)
12. [`lib/chartTheme.ts`](/Users/miethe/dev/homelab/development/CCDash/lib/chartTheme.ts)

If any of these files reintroduce raw `slate`, `indigo`, `emerald`, `amber`, `rose`, or `sky` utility formulas for shared surfaces, the guardrail test fails.

## Dark-Parity Validation Scope

Phase 6 dark-parity validation was completed as a source audit plus targeted regression verification for the foundation-owned surface set:

1. [`src/index.css`](/Users/miethe/dev/homelab/development/CCDash/src/index.css) still defines the dark-token baseline for shell, surface, state, chart, viewer, and markdown roles.
2. [`components/Layout.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/Layout.tsx), [`components/Dashboard.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/Dashboard.tsx), and [`components/content/UnifiedContentViewer.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/content/UnifiedContentViewer.tsx) remain free of raw palette utilities after the migration waves.
3. [`components/Analytics/AnalyticsDashboard.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/Analytics/AnalyticsDashboard.tsx) and [`components/Analytics/TrendChart.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/Analytics/TrendChart.tsx) continue to consume the centralized chart adapter for axis, grid, tooltip, series, and gradients.
4. Existing semantic regression coverage remains in place for [`lib/__tests__/chartTheme.test.ts`](/Users/miethe/dev/homelab/development/CCDash/lib/__tests__/chartTheme.test.ts) and [`components/__tests__/featureStatus.test.ts`](/Users/miethe/dev/homelab/development/CCDash/components/__tests__/featureStatus.test.ts).

No intentional dark-mode deviations were introduced in the guarded set during phase 6.

## Remaining Hotspots Outside The Guarded Set

The app is foundation-ready, but the raw-palette audit still shows notable feature-local debt outside the guarded scope. The largest remaining hotspots are:

1. [`components/Settings.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/Settings.tsx)
2. [`components/SessionInspector.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/SessionInspector.tsx)
3. [`components/OpsPanel.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/OpsPanel.tsx)
4. [`components/SessionMappings.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/SessionMappings.tsx)
5. [`components/DocumentModal.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/DocumentModal.tsx)
6. [`components/execution/RecommendedStackCard.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/execution/RecommendedStackCard.tsx)
7. [`components/execution/WorkflowEffectivenessSurface.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/execution/WorkflowEffectivenessSurface.tsx)

These files no longer block the standard theme modes plan because the semantic contract, shared primitives, chart adapter, and core shell/content surfaces are stable. They should still be prioritized in later cleanup so the guardrail scope can expand over time.

## Handoff To Standard Theme Modes

The follow-on plan can proceed with these assumptions:

1. Theme runtime work should preserve the current dark-token values as the baseline visual contract and layer `light` and `system` behavior on top.
2. Shared surfaces must keep using semantic primitives and `chartTheme` rather than adding mode-specific palette literals.
3. The exceptions policy in [`docs/project_plans/reports/ccdash-theme-color-exceptions-2026-03-20.md`](/Users/miethe/dev/homelab/development/CCDash/docs/project_plans/reports/ccdash-theme-color-exceptions-2026-03-20.md) remains the boundary for model colors, chart series, and other domain-driven accents.
4. Future migration work should expand the guardrail test only after each newly targeted surface is actually semantic-token clean.
