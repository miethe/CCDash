---
title: "Implementation Plan: Document Visual Taxonomy"
schema_version: 2
doc_type: implementation_plan
status: draft
created: 2026-04-24
updated: 2026-04-24
feature_slug: "document-visual-taxonomy"
feature_version: "v1"
prd_ref: docs/project_plans/PRDs/enhancements/document-visual-taxonomy-v1.md
plan_ref: null
scope: "Create and apply a shared visual taxonomy for all CCDash document types and groups across feature modal, document modal, plans catalog, planning views, and secondary linked-document surfaces."
effort_estimate: "18-26 story points"
architecture_summary: "Frontend-only shared taxonomy module with staged UI integration; no backend schema changes required."
related_documents:
  - docs/project_plans/PRDs/enhancements/document-visual-taxonomy-v1.md
  - docs/guides/feature-surface-architecture.md
references:
  user_docs: []
  context:
    - components/ProjectBoard.tsx
    - components/DocumentModal.tsx
    - components/PlanCatalog.tsx
    - components/Planning/ArtifactDrillDownPage.tsx
    - components/Planning/PlanningQuickViewPanel.tsx
    - components/Planning/TrackerIntakePanel.tsx
    - components/FeatureExecutionWorkbench.tsx
    - components/CodebaseExplorer.tsx
    - components/BlockingFeatureList.tsx
    - backend/document_linking.py
    - types.ts
  specs: []
  related_prds: []
spike_ref: null
adr_refs: []
deferred_items_spec_refs: []
findings_doc_ref: null
charter_ref: null
changelog_ref: null
test_plan_ref: null
plan_structure: unified
progress_init: manual
owner: null
contributors: []
priority: medium
risk_level: medium
category: "product-planning"
tags: [implementation, planning, documents, ux, visual-design, taxonomy]
milestone: null
commit_refs: []
pr_refs: []
files_affected:
  - lib/documentVisualTaxonomy.ts
  - lib/__tests__/documentVisualTaxonomy.test.ts
  - components/ProjectBoard.tsx
  - components/DocumentModal.tsx
  - components/PlanCatalog.tsx
  - components/Planning/ArtifactDrillDownPage.tsx
  - components/Planning/PlanningQuickViewPanel.tsx
  - components/Planning/TrackerIntakePanel.tsx
  - components/FeatureExecutionWorkbench.tsx
  - components/CodebaseExplorer.tsx
  - components/BlockingFeatureList.tsx
---

# Implementation Plan: Document Visual Taxonomy

## Executive Summary

This plan implements a shared frontend visual taxonomy for CCDash document types and document groups. The work consolidates duplicated icon/tone logic currently spread across `ProjectBoard.tsx`, `PlanCatalog.tsx`, `DocumentModal.tsx`, and Planning views, then applies group-specific background treatments anywhere linked documents are displayed.

The implementation is intentionally frontend-first. Backend document classification already provides enough signal through `docType`, `docSubtype`, `rootKind`, path, title, and category fields. The frontend taxonomy will normalize aliases and infer display groups without changing APIs.

## Implementation Strategy

- Build one static config module with literal Tailwind class strings so styling survives Tailwind scanning.
- Expose helpers that accept partial `PlanDocument` or `LinkedDocument` shapes.
- Preserve existing feature modal document group ordering and sorting while moving group metadata to the shared taxonomy.
- Roll out from highest-traffic surfaces to lower-traffic references.
- Validate with focused unit tests and representative component tests rather than broad snapshot churn.

## Canonical Visual Model

### Types

| Type | Aliases / Signals | Group | Expected Visual Role |
| --- | --- | --- | --- |
| `prd` | PRD paths/frontmatter | `prd` | Requirements definition |
| `implementation_plan` | `plan`, implementation plan paths | `plans` | Execution plan |
| `phase_plan` | phase plan paths, phase files | `plans` | Plan subsection |
| `progress` | progress root/path/type | `progress` | Execution tracking |
| `report` | reports, findings, reviews | `initialPlanning` | Evidence or analysis |
| `spec` | generic spec | `initialPlanning` | Technical/design input |
| `design_doc` | `design_spec`, design docs | `initialPlanning` | Design specification |
| `context` | worknotes, context files | `context` | Supporting context |
| `tracker` | tracker/intake artifacts | `progress` | Work tracking |
| `spike` | spike paths/title/category | `initialPlanning` | Research |
| `adr` | ADR paths/title/category | `initialPlanning` | Decision record |
| `document` | unknown/fallback | `unknown` | Neutral fallback |

### Groups

| Group | Surfaces |
| --- | --- |
| `initialPlanning` | Feature modal initial planning group, report/spec/design/SPIKE/ADR cards, initial planning compact rows |
| `prd` | PRD group, PRD cards/rows, PRD modal header |
| `plans` | Implementation and phase plan group, cards, compact rows |
| `progress` | Progress group, phase buckets, tracker/progress cards |
| `context` | Context/worknotes group, supporting doc rows |
| `unknown` | Fallback cards/rows |

## Phase Breakdown

| Phase | Title | Effort | Primary Files | Assigned Subagent(s) |
| --- | --- | --- | --- | --- |
| 1 | Taxonomy foundation | 4-5 pts | `lib/documentVisualTaxonomy.ts`, tests | `ui-engineer-enhanced`, `frontend-developer` |
| 2 | Feature modal integration | 5-7 pts | `components/ProjectBoard.tsx` | `ui-engineer-enhanced` |
| 3 | Document modal and plan catalog | 4-6 pts | `components/DocumentModal.tsx`, `components/PlanCatalog.tsx` | `frontend-developer`, `ui-engineer-enhanced` |
| 4 | Planning and secondary surfaces | 3-5 pts | `components/Planning/`, `FeatureExecutionWorkbench`, `CodebaseExplorer`, `BlockingFeatureList` | `frontend-developer` |
| 5 | Validation and polish | 2-3 pts | tests, screenshots, contrast tuning | `web-accessibility-checker`, `testing agents` |

## Phase 1: Taxonomy Foundation

**Goal:** Provide a single source of truth for document visual metadata.

| ID | Task | Description | Acceptance Criteria | Estimate | Assigned Subagent(s) |
| --- | --- | --- | --- | --- | --- |
| DVT-101 | Add taxonomy module | Create `lib/documentVisualTaxonomy.ts` with canonical type/group configs, aliases, labels, icons, and class names. | Module exports static config and helper functions with no React rendering side effects beyond icon component references. | 1.5 pts | `ui-engineer-enhanced` |
| DVT-102 | Add normalization helpers | Implement helpers to normalize type, infer group, and resolve metadata from `docType`, `docSubtype`, `rootKind`, path, title, and category. | Helpers work for `PlanDocument`, `LinkedDocument`, planning node-like inputs, and partial objects. | 1 pt | `frontend-developer` |
| DVT-103 | Add tests | Cover canonical types, aliases, path/title inference for SPIKE/ADR/context, progress root fallback, and unknown fallback. | `lib/__tests__/documentVisualTaxonomy.test.ts` passes. | 1.5 pts | `testing agents` |
| DVT-104 | Define usage API | Export high-level helpers such as `getDocumentVisuals(doc)`, `getDocumentGroupVisuals(group)`, and `getDocumentTypeLabel(type)`. | Components can replace local switches without duplicating config. | 0.5 pts | `ui-engineer-enhanced` |

**Quality Gate:**
- All class names are literal strings in the module.
- Unknown input never returns undefined icon, label, or classes.

## Phase 2: Feature Modal Integration

**Goal:** Apply type icons and group backgrounds in the highest-value linked-document surface.

| ID | Task | Description | Acceptance Criteria | Estimate | Assigned Subagent(s) |
| --- | --- | --- | --- | --- | --- |
| DVT-201 | Replace local type helpers | Replace `DOC_TYPE_LABELS`, `DocTypeIcon`, `DocTypeBadge`, `getDocTypeTone`, and `getDocGroupIcon` logic in `ProjectBoard.tsx` with shared taxonomy helpers. | Existing labels/icons remain equivalent or richer; no local duplicate switch remains for doc type visuals. | 1.5 pts | `ui-engineer-enhanced` |
| DVT-202 | Preserve grouping behavior | Keep existing `getDocGroupId` sorting semantics but route group identity through taxonomy where possible. | Initial planning, PRD, plans, progress, and context grouping still match current behavior. | 1 pt | `frontend-developer` |
| DVT-203 | Update Overview linked-doc rows | Apply group background, group border, type icon, type chip, and hover treatment to Linked Documents rows in the Overview tab. | Rows visually distinguish doc groups while retaining title truncation and external-link affordance. | 1 pt | `ui-engineer-enhanced` |
| DVT-204 | Update Documents tab sections | Apply group backgrounds to `FeatureModalSection` wrappers or a section variant for document groups. | Initial Planning, PRD, Plans, Progress, and Context groups have distinct section tone. | 1.5 pts | `ui-engineer-enhanced` |
| DVT-205 | Update doc cards and progress buckets | Apply group backgrounds to `FeatureDocCard` and progress phase bucket containers. | Cards and phase buckets inherit group tone; type icon/chip remains visible. | 1 pt | `ui-engineer-enhanced` |
| DVT-206 | Component test coverage | Extend feature modal tests to assert representative type icons/labels and group class application. | Tests cover one overview row and one Documents tab group/card. | 1 pt | `testing agents` |

**Quality Gate:**
- Feature modal Overview and Documents tab remain keyboard-clickable and text does not overflow compact rows.

## Phase 3: Document Modal and Plan Catalog

**Goal:** Make standalone document browsing consistent with feature-linked documents.

| ID | Task | Description | Acceptance Criteria | Estimate | Assigned Subagent(s) |
| --- | --- | --- | --- | --- | --- |
| DVT-301 | Update document modal header | Resolve visuals for the active document and apply type/group accent to header/title bar, type chip, and icon. | Opening a PRD, plan, progress, report, or spec shows a distinct header treatment. | 1.5 pts | `ui-engineer-enhanced` |
| DVT-302 | Update document relationships rows | Apply taxonomy icons and row backgrounds to linked docs in `DocumentModal` relationships tab. | Related docs no longer render as generic file rows. | 1 pt | `frontend-developer` |
| DVT-303 | Update plan catalog cards | Use taxonomy icon/type/group styles in card view. | Cards have distinct document type icons and subtle group backgrounds. | 1 pt | `ui-engineer-enhanced` |
| DVT-304 | Update plan catalog list/tree/detail | Use taxonomy in list rows, tree active document details, and active panel metadata. | Generic `FileText` treatment is replaced where document type is known. | 1.5 pts | `frontend-developer` |
| DVT-305 | Add or update tests | Extend plan catalog/document modal tests for representative visual metadata rendering. | Tests cover at least PRD, implementation plan, progress, and fallback doc. | 1 pt | `testing agents` |

**Quality Gate:**
- Document modal header treatment does not reduce close button visibility or content area readability.

## Phase 4: Planning and Secondary Surfaces

**Goal:** Remove remaining inconsistent document icon treatments from document-heavy surfaces.

| ID | Task | Description | Acceptance Criteria | Estimate | Assigned Subagent(s) |
| --- | --- | --- | --- | --- | --- |
| DVT-401 | Update Planning artifact drill-down | Replace artifact row and type icon logic in `ArtifactDrillDownPage.tsx` with taxonomy metadata. | Design specs, PRDs, implementation plans, contexts, and reports render with canonical visuals. | 1 pt | `frontend-developer` |
| DVT-402 | Update quick view and tracker intake | Use taxonomy icons for document actions and node chips where they represent document artifacts. | PRD/context/design/tracker chips are visually aligned with the shared taxonomy. | 1 pt | `frontend-developer` |
| DVT-403 | Update execution workbench doc refs | Apply taxonomy visuals to document tabs, doc update events, and linked document cards/rows where displayed. | Execution workbench document references no longer rely on generic file icons. | 1 pt | `frontend-developer` |
| DVT-404 | Update investigation/reference surfaces | Update `CodebaseExplorer.tsx` and `BlockingFeatureList.tsx` document references where type is present. | Secondary document links show canonical type icon/chip without overhauling layout. | 1 pt | `frontend-developer` |

**Quality Gate:**
- No new imports create circular dependencies; taxonomy remains in `lib/` with type-only dependencies where needed.

## Phase 5: Validation and Polish

**Goal:** Confirm the shared taxonomy is consistent, accessible, and non-disruptive.

| ID | Task | Description | Acceptance Criteria | Estimate | Assigned Subagent(s) |
| --- | --- | --- | --- | --- | --- |
| DVT-501 | Run focused tests | Run taxonomy tests and affected component tests. | Relevant tests pass or failures are documented with fixes. | 0.5 pts | `testing agents` |
| DVT-502 | Run typecheck/build | Run TypeScript validation and build command used by the repo. | No type or build regressions. | 0.5 pts | `frontend-developer` |
| DVT-503 | Visual QA | Inspect feature modal Overview/Documents tab, DocumentModal, and `/plans` in desktop and mobile-width screenshots. | Distinct type/group colors are visible and text does not overlap. | 1 pt | `ui-engineer-enhanced`, `web-accessibility-checker` |
| DVT-504 | Contrast and density pass | Tune tones if colors overpower status or reduce text contrast. | Colors remain subtle and readable in dense views. | 1 pt | `ui-designer`, `web-accessibility-checker` |

## Test Plan

- Unit tests:
  - `lib/__tests__/documentVisualTaxonomy.test.ts`
  - Canonical doc type resolution
  - Alias resolution for `design_spec`/`design_doc`
  - Group inference for progress root/path, SPIKE, ADR, report, context/worknotes
  - Unknown fallback
- Component tests:
  - Existing feature modal tests for Overview and Documents tab
  - Plan catalog tests with document type rendering
  - Document modal tests for active doc type chip/header
- Manual/visual checks:
  - Feature modal Overview linked document rows
  - Feature modal Documents tab sections and progress buckets
  - `/plans` card and list views
  - Document modal header and Relationships tab
  - Planning artifact drill-down page

## Migration Notes

- Keep existing document group IDs to avoid changing user-facing ordering and expanded-state logic.
- Prefer replacing local helper functions in place over broad component restructuring.
- Use taxonomy helpers for display only; do not change backend `docType` values or parser behavior.
- Any future document type should be added to the shared taxonomy first, then consumed by UI surfaces automatically.

## Open Questions

- Should `report` stay in `initialPlanning` for all contexts, or should completed execution reports eventually become their own evidence group?
- Should `design_doc` and `spec` remain in `initialPlanning`, or should design/spec artifacts get a separate group if volume grows?
- Should document group color be used in global navigation counts or only in document-specific surfaces?

## Definition of Done

- Shared taxonomy module and tests exist.
- Feature modal, document modal, plan catalog, Planning views, and secondary document references consume the shared taxonomy.
- All supported document types have a custom icon and type tone.
- All document groups have custom backgrounds applied to relevant cards, rows, groups, or headers.
- Unknown types have a stable fallback.
- Relevant tests, typecheck, and visual QA pass.

