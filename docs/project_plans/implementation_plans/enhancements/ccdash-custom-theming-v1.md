---
schema_name: ccdash_document
schema_version: 3
doc_type: implementation_plan
doc_subtype: implementation_plan
primary_doc_role: supporting_document
status: pending
category: enhancements
title: "Implementation Plan: CCDash Custom Theming V1"
description: "Enable user-defined themes in CCDash through validated token presets layered on top of the standard theme system."
summary: "Add theme preset storage, validation, editing, preview, and application for app-wide semantic tokens while keeping data-driven domain colors explicitly separated."
author: codex
audience: [ai-agents, developers, fullstack-engineering, frontend-platform]
created: 2026-03-19
updated: 2026-03-19
tags: [implementation, enhancement, theming, presets, customization, ui]
priority: medium
risk_level: medium
complexity: medium
track: UI Platform
timeline_estimate: "2-4 weeks across 5 phases"
feature_slug: ccdash-custom-theming-v1
feature_family: ccdash-theme-system-modernization
feature_version: v1
lineage_family: ccdash-theme-system-modernization
lineage_parent:
  ref: docs/project_plans/implementation_plans/enhancements/ccdash-standard-theme-modes-v1.md
  kind: prerequisite
lineage_children: []
lineage_type: enhancement
linked_features: []
related_documents:
  - docs/project_plans/PRDs/refactors/ccdash-theme-system-modernization-v1.md
  - docs/project_plans/implementation_plans/refactors/ccdash-theme-system-foundation-v1.md
  - docs/project_plans/implementation_plans/enhancements/ccdash-standard-theme-modes-v1.md
  - docs/project_plans/reports/ccdash-theme-system-feasibility-and-migration-report-2026-03-19.md
context_files:
  - components/Settings.tsx
  - src/index.css
  - tailwind.config.js
  - contexts/ModelColorsContext.tsx
  - lib/modelColors.ts
  - components/ui/badge.tsx
---

# Implementation Plan: CCDash Custom Theming V1

## Objective

Enable users to apply their own app-wide UI themes to CCDash using validated semantic token presets layered on top of the standard theme system. This plan begins only after the foundation refactor and standard theme modes are complete.

## Scope And Fixed Decisions

In scope:

1. Add a persistent user theme preset model.
2. Allow users to customize semantic app tokens through approved controls.
3. Support preview, apply, save, edit, duplicate, reset, and delete flows for presets.
4. Keep compatibility with standard theme modes.
5. Clearly separate app theme tokens from data-driven accent systems such as model colors.

Out of scope:

1. Arbitrary CSS text input.
2. Unvalidated token names or raw stylesheet injection.
3. Replacing model color overrides or other domain-specific color systems.

Fixed decisions:

1. Custom theming is token-map based.
2. Only semantic theme tokens are user-customizable.
3. Standard theme modes remain the outer runtime modes; custom themes specialize those semantics.

## Preset Model Direction

Each custom theme preset should define a validated set of semantic values for roles such as:

1. app background and foreground
2. panel surfaces and borders
3. primary, secondary, accent, muted roles
4. success, warning, danger, info roles
5. chart roles and tooltip/grid roles
6. radii or density-related style tokens only if the foundation and standard modes plans deem them stable enough

The implementation may support separate dark and light token maps per preset or a single preset with mode-specific variants. The model must remain bounded and explicit.

## Phase Overview

| Phase | Title | Effort | Duration | Critical Path | Objective |
|------|-------|--------|----------|---------------|-----------|
| 1 | Preset Model And Validation | 7 pts | 3 days | Yes | Define storage schema, validation, and token boundaries |
| 2 | Theme Preset Runtime Integration | 8 pts | 3-4 days | Yes | Apply presets on top of standard theme modes safely |
| 3 | Settings UI And Editing Workflow | 10 pts | 4-5 days | Yes | Build user-facing preset management and editing |
| 4 | Preview, Safety, And Recovery | 7 pts | 3 days | Yes | Add non-destructive preview, reset, and invalid-theme recovery |
| 5 | QA, Accessibility, And Preset Governance | 7 pts | 3 days | Final gate | Validate custom themes and establish extension guardrails |

**Total**: ~39 story points over 2-4 weeks

## Implementation Strategy

1. Start with preset schema and validation boundaries before building UI.
2. Keep runtime application deterministic: base mode resolves first, custom preset overlays second.
3. Build preview and recovery features before broadening editing flexibility.
4. Treat accessibility and invalid-theme handling as core requirements, not polish.

## Phase 1: Preset Model And Validation

**Assigned Subagent(s)**: frontend-platform, ui-engineer-enhanced

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| CUSTOM-001 | Preset Schema | Define the preset data model, stable token set, and per-mode behavior. | Preset schema is explicit, versionable, and scoped to supported semantic roles only. | 3 pts | frontend-platform | Standard theme modes plan complete |
| CUSTOM-002 | Validation Rules | Add validation for color formats, missing required roles, and unsafe or unsupported values. | Invalid preset data cannot be applied silently. | 2 pts | frontend-platform | CUSTOM-001 |
| CUSTOM-003 | Persistence Strategy | Define storage location and migration/versioning strategy for saved presets. | Presets persist safely and can evolve without breaking old entries. | 2 pts | frontend-platform | CUSTOM-001 |

**Phase 1 Quality Gates**

1. Preset schema is bounded and documented.
2. Unsupported customization paths are rejected clearly.
3. Storage and versioning are stable enough for user-facing management.

## Phase 2: Theme Preset Runtime Integration

**Assigned Subagent(s)**: frontend-developer, frontend-platform

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| CUSTOM-101 | Runtime Overlay Model | Apply custom preset tokens on top of resolved dark/light/system mode without bypassing the provider. | Effective theme result is deterministic and mode-aware. | 3 pts | frontend-platform, frontend-developer | CUSTOM-003 |
| CUSTOM-102 | Token Application Pipeline | Add a safe runtime path for applying preset values to CSS variables. | Presets affect the full app surface through the semantic token layer. | 3 pts | frontend-developer | CUSTOM-101 |
| CUSTOM-103 | Exception-System Compatibility | Ensure model colors and other data-driven accents remain isolated from app theme preset changes. | Domain-specific color systems continue to work without being overridden unexpectedly. | 2 pts | frontend-platform | CUSTOM-102 |

**Phase 2 Quality Gates**

1. Presets apply app-wide through semantic tokens.
2. Runtime application is mode-aware and reversible.
3. Data-driven accents remain intentionally separate.

## Phase 3: Settings UI And Editing Workflow

**Assigned Subagent(s)**: ui-engineer-enhanced, frontend-developer

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| CUSTOM-201 | Preset Management UI | Add Settings UI for listing, selecting, creating, duplicating, renaming, and deleting presets. | Users can manage presets without touching raw config. | 4 pts | ui-engineer-enhanced | CUSTOM-102 |
| CUSTOM-202 | Token Editing UI | Add bounded editing controls for supported semantic token values. | Users can modify supported theme roles with validation feedback. | 4 pts | ui-engineer-enhanced, frontend-developer | CUSTOM-201 |
| CUSTOM-203 | Default And Reset Flows | Support reset-to-standard-mode or reset-to-default-preset behavior. | Users can recover from unwanted visual changes quickly. | 2 pts | frontend-developer | CUSTOM-201 |

**Phase 3 Quality Gates**

1. Preset management is user-friendly and bounded.
2. Editing stays inside validated token controls.
3. Reset behavior is always available.

## Phase 4: Preview, Safety, And Recovery

**Assigned Subagent(s)**: frontend-developer, qa-engineer

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| CUSTOM-301 | Non-Destructive Preview | Let users preview theme changes before committing them. | Users can inspect a preset without permanently applying it immediately. | 3 pts | frontend-developer | CUSTOM-202 |
| CUSTOM-302 | Invalid Theme Recovery | Add fallback behavior for malformed, missing, or partially invalid preset data. | The app never becomes unreadable or stuck because of a bad preset. | 2 pts | frontend-developer | CUSTOM-301 |
| CUSTOM-303 | Cross-Surface Preview Validation | Confirm preview behavior works across shell, charts, markdown, and table surfaces. | Preview is representative across major UI surfaces. | 2 pts | qa-engineer | CUSTOM-301 |

**Phase 4 Quality Gates**

1. Theme preview is safe and reversible.
2. Fallback behavior is reliable.
3. Preview reflects real app-wide coverage.

## Phase 5: QA, Accessibility, And Preset Governance

**Assigned Subagent(s)**: accessibility-engineer, qa-engineer, documentation-writer

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|--------------|
| CUSTOM-401 | Custom Theme Accessibility Guardrails | Add validation or warnings for low-contrast or unsafe token combinations where feasible. | Users receive meaningful guardrails before saving clearly problematic presets. | 3 pts | accessibility-engineer | CUSTOM-303 |
| CUSTOM-402 | Preset Regression Coverage | Add tests/checklists for preset apply/remove/preview behavior and persisted selection. | Custom-theme regressions are detectable. | 2 pts | qa-engineer | CUSTOM-401 |
| CUSTOM-403 | Governance And Extensibility Docs | Document supported customizable roles, future expansion rules, and boundaries around data-driven colors. | Future preset expansion follows a stable contract. | 2 pts | documentation-writer | CUSTOM-402 |

**Phase 5 Quality Gates**

1. Presets are safe enough for general usage.
2. Accessibility risks are surfaced or mitigated.
3. Custom theming has clear long-term guardrails.

## Exit Criteria

This plan is complete when:

1. Users can apply saved theme presets to the entire app through semantic tokens.
2. Presets coexist correctly with dark/light/system base modes.
3. Preview, reset, and invalid-theme recovery are reliable.
4. Domain-specific accent systems remain separated from the base theme model.
