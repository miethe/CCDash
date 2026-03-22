---
schema_name: ccdash_document
schema_version: 3
doc_type: report
doc_subtype: implementation_report
primary_doc_role: supporting_document
status: active
category: refactors
title: "CCDash Theme Foundation Phase 2 Shared Primitives"
description: "Reference for the reusable surface and control primitives introduced in phase 2 of the theme-system foundation refactor."
summary: "Documents the new semantic surface, alert, control-row, button, input, select, and badge primitives that replace repeated dark-palette formulas on shared UI."
author: codex
audience: [ai-agents, developers, frontend-platform]
created: 2026-03-20
updated: 2026-03-20
tags: [theming, ui, components, primitives, controls]
feature_slug: ccdash-theme-system-foundation-v1
feature_family: ccdash-theme-system-modernization
feature_version: v1
---

# CCDash Theme Foundation Phase 2 Shared Primitives

## New Shared Building Blocks

1. [`components/ui/surface.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/ui/surface.tsx)
   Exposes `Surface`, `AlertSurface`, and `ControlRow` for panel shells, callouts, and control group wrappers.
2. [`components/ui/button.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/ui/button.tsx)
   Adds semantic `panel` and `chip` variants and retargets existing variants to token-backed colors.
3. [`components/ui/input.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/ui/input.tsx)
   Adds semantic `tone` and `size` variants for shared text inputs.
4. [`components/ui/select.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/ui/select.tsx)
   Provides the native select baseline aligned with the shared input contract.
5. [`components/ui/badge.tsx`](/Users/miethe/dev/homelab/development/CCDash/components/ui/badge.tsx)
   Adds semantic tones for neutral, muted, info, success, warning, and danger chips.

## Usage Guidelines

1. Use `Surface` for reusable shells that would previously have used `bg-slate-900 border border-slate-800`.
2. Use `AlertSurface` for shared warning, success, info, or danger blocks instead of one-off amber/emerald/rose formulas.
3. Wrap dense filter rows, action rows, and settings rows in `ControlRow` before custom per-page styling.
4. Prefer `Button variant="panel"` or `Button variant="chip"` over ad hoc `bg-slate-800 hover:bg-slate-700 border-slate-700`.
5. Prefer `Input tone="default"` and `Select tone="default"` for filters and forms unless a screen explicitly needs a nested panel tone.
6. Reserve raw palette literals for data-driven accents or chart-series exceptions, not shared chrome.
