---
type: context
schema_version: 2
doc_type: context
prd: "feature-surface-remediation-v1"
feature_slug: "feature-surface-remediation-v1"
title: "Feature Surface Remediation v1 - Development Context"
status: active
created: 2026-04-24
updated: 2026-04-24

critical_notes_count: 0
implementation_decisions_count: 0
active_gotchas_count: 0
agent_contributors: []
agents: []
---

# Feature Surface Remediation v1 — Development Context

**Status**: Active Development
**Created**: 2026-04-24
**Last Updated**: 2026-04-24

> **Purpose**: Shared worknotes for all agents working on the four post-review gaps from `feature-surface-data-loading-redesign`. Add observations, decisions, and gotchas here as work progresses.

---

## Quick Reference

- **Review Report**: `docs/project_plans/reports/feature-surface-data-loading-redesign-review-2026-04-24.md`
- **Implementation Plan**: `docs/project_plans/implementation_plans/harden-polish/feature-surface-remediation-v1.md`
- **Parent PRD**: `docs/project_plans/PRDs/refactors/feature-surface-data-loading-redesign-v1.md`
- **Parent Plan**: `docs/project_plans/implementation_plans/refactors/feature-surface-data-loading-redesign-v1.md`
- **Progress (Phase 1)**: `.claude/progress/feature-surface-remediation-v1/phase-1-progress.md`
- **Progress (Phase 2)**: `.claude/progress/feature-surface-remediation-v1/phase-2-progress.md`
- **Progress (Phase 3)**: `.claude/progress/feature-surface-remediation-v1/phase-3-progress.md`

---

## Gap Summary

Four gaps identified in the post-implementation review of `feature-surface-data-loading-redesign-v1`:

- **G1 (high, perf)** — `AppEntityDataContext.refreshFeatures()` still triggers the legacy `/api/features?limit=5000` global load even though ProjectBoard renders from bounded v2 surfaces; the app-shell refresh and the ProjectBoard surface provider are decoupled in consumption but not in refresh triggers.

- **G2 (high, bug)** — `services/apiClient.ts` write paths (`updateFeatureStatus`, `updatePhaseStatus`, `updateTaskStatus`) use raw string interpolation for IDs; IDs containing `#`, `?`, `&`, or spaces produce silently broken requests.

- **G3 (medium, tech-debt)** — `FeatureExecutionWorkbench` sessions tab loads via `getFeatureExecutionContext()` rather than the paginated v2 surface; the parent plan was ambiguous on whether this is exempt (user-initiated) or a required migration target.

- **G4 (medium, test)** — Phases 4–5 of the parent plan skipped runtime smoke validation; browser network waterfall, modal lazy-load behavior, and cache invalidation on feature update have not been verified in a live browser session.

---

## Decisions & Blockers

_No decisions or blockers recorded yet._
