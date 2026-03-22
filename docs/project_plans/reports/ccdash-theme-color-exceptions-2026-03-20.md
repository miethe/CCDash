---
schema_name: ccdash_document
schema_version: 3
doc_type: report
doc_subtype: theme_policy
primary_doc_role: supporting_document
status: active
category: reports
title: 'CCDash Theme Color Exceptions'
description: Defines the limited data-driven color paths that may remain outside the base app theme token contract.
summary: Separates semantic app theming from model colors, data-visualization series colors, and other domain accents.
author: codex
audience:
- ai-agents
- developers
created: 2026-03-20
updated: '2026-03-21'
tags:
- theme
- policy
- ui
- colors
---

# CCDash Theme Color Exceptions

## Rule

Base application surfaces, text, borders, overlays, alerts, badges, and shell chrome must use semantic theme tokens.

## Allowed Exceptions

1. Model identity colors from [`lib/modelColors.ts`](/Users/miethe/dev/homelab/development/CCDash/lib/modelColors.ts) may remain data-driven because they encode domain meaning, not app theme meaning.
2. Chart series colors may use the centralized adapter in [`lib/chartTheme.ts`](/Users/miethe/dev/homelab/development/CCDash/lib/chartTheme.ts), including semantic status tones and the shared chart token series.
3. User-selected accent overrides may style only the domain artifacts they describe. They must not restyle shell, panel, navigation, or form surfaces.

## Disallowed Paths

1. New page-level `slate`, `indigo`, `emerald`, `amber`, or `rose` literals for shared surfaces.
2. File-local chart tooltip, grid, axis, or container colors when the shared chart adapter can supply them.
3. Reusing model color overrides to tint global navigation, cards, forms, or markdown surfaces.

## Enforcement

1. [`lib/__tests__/themeFoundationGuardrails.test.ts`](/Users/miethe/dev/homelab/development/CCDash/lib/__tests__/themeFoundationGuardrails.test.ts) fails if the guarded foundation files reintroduce raw palette utilities for shared surfaces.
2. The guarded scope is intentionally narrow: it covers foundation-owned shared primitives and the migrated shell/dashboard/viewer/chart paths, not every remaining feature-local hotspot.
3. Expand the guardrail only after a candidate file is fully migrated onto semantic tokens; otherwise the policy loses signal in CI.
