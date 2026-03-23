---
schema_name: ccdash_document
schema_version: 3
doc_type: implementation_plan
doc_subtype: implementation_plan
primary_doc_role: supporting_document
status: completed
category: enhancements
title: 'Implementation Plan: CCDash Standard Theme Modes V1'
description: 'Deliver standard app theme modes for CCDash after the theme-system foundation
  refactor: dark, light, and system.'
summary: Introduce runtime theme resolution, persistence, first-paint correctness,
  light-mode token sets, and validation across shell, charts, content, and accessibility-sensitive
  surfaces.
author: codex
audience:
- ai-agents
- developers
- fullstack-engineering
- frontend-platform
created: 2026-03-19
updated: '2026-03-22'
tags:
- implementation
- enhancement
- theming
- dark-mode
- light-mode
- system-theme
priority: high
risk_level: medium
complexity: medium
track: UI Platform
timeline_estimate: 2-3 weeks across 5 phases
feature_slug: ccdash-standard-theme-modes-v1
feature_family: ccdash-theme-system-modernization
feature_version: v1
lineage_family: ccdash-theme-system-modernization
lineage_parent:
  ref: docs/project_plans/implementation_plans/refactors/ccdash-theme-system-foundation-v1.md
  kind: prerequisite
lineage_children:
- docs/project_plans/implementation_plans/enhancements/ccdash-custom-theming-v1.md
lineage_type: enhancement
linked_features: []
related_documents:
- docs/project_plans/PRDs/refactors/ccdash-theme-system-modernization-v1.md
- docs/project_plans/implementation_plans/refactors/ccdash-theme-system-foundation-v1.md
- docs/project_plans/reports/ccdash-theme-foundation-phase-6-guardrails-and-handoff-2026-03-21.md
- docs/project_plans/implementation_plans/enhancements/ccdash-custom-theming-v1.md
context_files:
- index.tsx
- App.tsx
- src/index.css
- components/Settings.tsx
- components/Layout.tsx
- components/Dashboard.tsx
- components/Analytics/TrendChart.tsx
- components/content/UnifiedContentViewer.tsx
- contexts/ModelColorsContext.tsx
---

# Implementation Plan: CCDash Standard Theme Modes V1

## Objective

Ship the first user-facing theme modes for CCDash:

1. `dark`
2. `light`
3. `system`

This plan assumes the foundation refactor is complete and the app now renders through semantic tokens rather than palette-literal shared surfaces.

## Foundation Handoff Snapshot

1. The shared theme foundation is now CI-guarded for [`components/ui/surface.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/ui/surface.tsx), [`components/ui/button.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/ui/button.tsx), [`components/ui/input.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/ui/input.tsx), [`components/ui/select.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/ui/select.tsx), [`components/ui/badge.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/ui/badge.tsx), [`components/Layout.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/Layout.tsx), [`components/Dashboard.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/Dashboard.tsx), [`components/Analytics/AnalyticsDashboard.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/Analytics/AnalyticsDashboard.tsx), [`components/Analytics/TrendChart.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/Analytics/TrendChart.tsx), [`components/content/UnifiedContentViewer.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/content/UnifiedContentViewer.tsx), [`components/featureStatus.ts`](/Users/miethe/dev/homelab/development/CCDash/components/featureStatus.ts), and [`lib/chartTheme.ts`](/Users/miethe/dev/homelab/development/CCDash/lib/chartTheme.ts).
2. The dark baseline for those foundation-owned surfaces was revalidated in phase 6; see [`docs/project_plans/reports/ccdash-theme-foundation-phase-6-guardrails-and-handoff-2026-03-21.md`](/Users/miethe/dev/homelab/development/CCDash/docs/project_plans/reports/ccdash-theme-foundation-phase-6-guardrails-and-handoff-2026-03-21.md).
3. Remaining palette-literal hotspots still exist in feature-local files such as [`components/Settings.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/Settings.tsx), [`components/SessionInspector.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/SessionInspector.tsx), and [`components/OpsPanel.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/OpsPanel.tsx), but they no longer block runtime theme-mode delivery.

## Scope And Fixed Decisions

In scope:

1. Add root theme state management and first-paint resolution.
2. Support persisted theme preference and system preference fallback.
3. Implement light-mode tokens and validate dark-mode parity.
4. Wire the existing Settings Theme selector into real behavior.
5. Validate charts, markdown, tables, content viewer, badges, and selected states under both modes.

Out of scope:

1. User-defined theme editing.
2. Preset import/export.
3. Arbitrary token override UI.

Fixed decisions:

1. Theme state resolves at app root before visible paint when possible.
2. `system` follows `prefers-color-scheme`.
3. Standard mode delivery does not change data-driven color override systems.

## Phase Overview

| Phase | Title | Effort | Duration | Critical Path | Objective |
|------|-------|--------|----------|---------------|-----------|
| 1 | Theme Runtime And Persistence | 7 pts | 3 days | Yes | Add provider, storage, and boot-time resolution |
| 2 | Standard Mode Token Sets | 8 pts | 3-4 days | Yes | Finalize dark/light token definitions and `color-scheme` handling |
| 3 | Settings And App Wiring | 6 pts | 2-3 days | Yes | Connect UI controls and route the resolved theme through the app |
| 4 | Surface And Chart Verification | 8 pts | 3-4 days | Yes | Validate shell, viewer, and chart behavior under all modes |
| 5 | Accessibility, QA, And Rollout | 6 pts | 2-3 days | Final gate | Confirm contrast, regression coverage, and readiness for custom theming |

**Total**: ~35 story points over 2-3 weeks

## Implementation Strategy

1. Add the provider and persistence first so the rest of the app has a stable runtime contract.
2. Finalize token sets before wiring Settings or testing charts.
3. Validate first-paint correctness early to avoid flash-of-wrong-theme regressions.
4. Treat charts and content-heavy surfaces as dedicated verification tracks, not incidental QA.

## Phase 1: Theme Runtime And Persistence

**Assigned Subagent(s)**: frontend-platform, frontend-developer

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| MODE-001 | Theme State Model | Define the theme preference model for `dark`, `light`, and `system` plus resolved runtime theme. | Theme contract is explicit and usable from app root and Settings UI. | 2 pts | frontend-platform | Foundation plan complete |
| MODE-002 | Theme Provider | Add a root provider that resolves, stores, and exposes current preference and effective theme. | App can read/write theme preference centrally. | 3 pts | frontend-developer | MODE-001 |
| MODE-003 | Boot-Time Resolution | Replace hard-forced `.dark` bootstrap with resolved theme application and no incorrect default mode flash. | `index.tsx` no longer forces dark; boot path respects saved or system mode. | 2 pts | frontend-platform | MODE-002 |

**Phase 1 Quality Gates**

1. Theme state is centralized.
2. Theme preference persists reliably.
3. First paint resolves the correct mode.

## Phase 2: Standard Mode Token Sets

**Assigned Subagent(s)**: ui-engineer-enhanced, frontend-platform

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| MODE-101 | Dark Token Finalization | Validate and adjust dark token values after the foundation refactor to preserve intended visual baseline. | Dark mode remains coherent under resolved theme runtime. | 3 pts | ui-engineer-enhanced | MODE-003 |
| MODE-102 | Light Token Definition | Define light token values for shell, surfaces, states, charts, and content surfaces. | Light mode token set is complete for all semantic roles established in the foundation plan. | 3 pts | ui-engineer-enhanced, frontend-platform | MODE-003 |
| MODE-103 | Color-Scheme And Browser Surface Handling | Make `color-scheme`, scrollbars, and other browser-controlled surfaces follow resolved theme correctly. | Browser-native chrome aligns with light/dark mode. | 2 pts | frontend-platform | MODE-102 |

**Phase 2 Quality Gates**

1. Semantic tokens produce valid dark and light results.
2. Browser-level surfaces follow theme correctly.
3. No shared surface depends on hidden dark-only assumptions.

## Phase 3: Settings And App Wiring

**Assigned Subagent(s)**: frontend-developer

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| MODE-201 | Settings Theme Selector Wiring | Connect the existing Theme selector in `Settings.tsx` to real provider state and persistence. | Selecting a theme updates the app and persists preference. | 3 pts | frontend-developer | MODE-103 |
| MODE-202 | App-Level Consumption Cleanup | Ensure shell and relevant pages consume resolved theme state only through provider and tokens, not local theme logic. | Theme behavior is centralized and consistent. | 2 pts | frontend-developer | MODE-201 |
| MODE-203 | Developer Debug Hooks | Add lightweight debug visibility for active preference/resolved mode during validation if needed. | Theme QA can verify mode state deterministically. | 1 pt | frontend-developer | MODE-202 |

**Phase 3 Quality Gates**

1. Settings UI reflects real app state.
2. Theme switching is stable and immediate.
3. No duplicate theme state exists in page components.

## Phase 4: Surface And Chart Verification

**Assigned Subagent(s)**: qa-engineer, data-viz-ui, frontend-developer

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| MODE-301 | Core Surface Verification | Validate shell, navigation, settings, content viewer, tables, and overlays in dark/light/system. | All major shared surfaces render legibly and consistently in each mode. | 3 pts | qa-engineer | MODE-202 |
| MODE-302 | Chart Verification | Validate chart axes, grid, gradients, tooltips, series defaults, and legends in both modes. | Charts remain readable and visually coherent in dark and light themes. | 3 pts | data-viz-ui, qa-engineer | MODE-202 |
| MODE-303 | Edge-State Verification | Validate status chips, alerts, selection states, hover states, and focus states in both modes. | State semantics remain understandable without palette regressions. | 2 pts | frontend-developer, qa-engineer | MODE-301 |

**Phase 4 Quality Gates**

1. Charts are production-ready in both modes.
2. Content-heavy surfaces such as markdown and tables remain readable.
3. State colors and focus affordances survive the mode expansion.

## Phase 5: Accessibility, QA, And Rollout

**Assigned Subagent(s)**: accessibility-engineer, qa-engineer, documentation-writer

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| MODE-401 | Contrast And Accessibility Pass | Validate text, border, and focus contrast in both modes for critical UI states. | Accessibility-sensitive surfaces meet agreed contrast expectations. | 2 pts | accessibility-engineer | MODE-303 |
| MODE-402 | Regression Coverage | Add or update tests/checklists for theme persistence, resolved mode selection, and core surface parity. | Theme-mode regressions are detectable. | 2 pts | qa-engineer | MODE-401 |
| MODE-403 | Custom Theming Handoff | Document remaining assumptions, stable token APIs, and extension points for user-defined theming. | Next plan can layer customization on top of standard modes without revisiting runtime fundamentals. | 2 pts | documentation-writer | MODE-402 |

**Phase 5 Quality Gates**

1. Standard modes are feature-complete.
2. Accessibility-sensitive surfaces are validated.
3. Custom theming is unblocked.

## Exit Criteria

This plan is complete when:

1. CCDash supports `dark`, `light`, and `system`.
2. Theme preference persists and resolves correctly at boot.
3. Shared surfaces, charts, markdown, and app shell are validated in both modes.
4. The platform is ready for user-defined theming on top of the standard theme contract.

## Completion Notes

Completed on 2026-03-22.

1. `Settings > General > Theme` now writes through the centralized theme provider and persists the selected preference.
2. The settings route includes a scoped light-mode compatibility bridge so the remaining legacy controls stay usable under the delivered standard modes while deeper semantic cleanup remains future work.
3. Theme guardrails now also verify the Settings selector wiring and the scoped compatibility bridge alongside the existing bootstrap and shared-surface checks.
4. Standard-mode rollout and extension guidance now live in:
   - `docs/theme-modes-user-guide.md`
   - `docs/theme-modes-developer-reference.md`
