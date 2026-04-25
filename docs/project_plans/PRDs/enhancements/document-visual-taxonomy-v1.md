---
title: "PRD: Document Visual Taxonomy"
schema_version: 2
doc_type: prd
status: draft
created: 2026-04-24
updated: 2026-04-24
feature_slug: "document-visual-taxonomy"
feature_version: "v1"
prd_ref: null
plan_ref: docs/project_plans/implementation_plans/enhancements/document-visual-taxonomy-v1.md
related_documents:
  - docs/guides/feature-surface-architecture.md
references:
  user_docs: []
  context:
    - CLAUDE.md
    - components/ProjectBoard.tsx
    - components/DocumentModal.tsx
    - components/PlanCatalog.tsx
    - components/Planning/ArtifactDrillDownPage.tsx
    - components/Planning/PlanningQuickViewPanel.tsx
    - components/Planning/TrackerIntakePanel.tsx
    - backend/document_linking.py
    - types.ts
  specs: []
  related_prds: []
spike_ref: null
adr_refs: []
charter_ref: null
changelog_ref: null
test_plan_ref: null
owner: null
contributors: []
priority: medium
risk_level: medium
category: "product-planning"
tags: [prd, planning, enhancements, documents, ux, visual-design, taxonomy]
milestone: null
commit_refs: []
pr_refs: []
files_affected:
  - lib/documentVisualTaxonomy.ts
  - components/ProjectBoard.tsx
  - components/DocumentModal.tsx
  - components/PlanCatalog.tsx
  - components/Planning/
  - components/FeatureExecutionWorkbench.tsx
  - components/CodebaseExplorer.tsx
  - components/BlockingFeatureList.tsx
  - types.ts
---

# Feature Brief & Metadata

**Feature Name:**

> Document Visual Taxonomy

**Filepath Name:**

> `document-visual-taxonomy-v1`

**Date:**

> 2026-04-24

**Author:**

> Codex

**Related Documents:**

> - `docs/guides/feature-surface-architecture.md` - feature modal and cached section architecture

---

## 1. Executive Summary

CCDash already distinguishes a few linked document types with colored icons, especially PRD, implementation plan, phase plan, progress, report, and generic spec cards inside the feature modal. This enhancement expands that idea into a shared visual taxonomy for every supported document type and planning artifact type. The taxonomy will provide a canonical icon, label, group, accent color, surface background, border, and modal header treatment for each document type and group.

The goal is visual consistency anywhere documents are linked or displayed: feature modal overview rows, feature modal Documents tab groups and cards, document modal headers and linked-doc rows, plan catalog cards/list rows/tree details, Planning pages, execution workbench document references, codebase explorer document references, and any compact linked-document badges. Users should be able to identify document purpose by color and icon before reading the label, without the interface becoming noisy or inaccessible.

**Priority:** MEDIUM

**Key Outcomes:**
- Every supported document type has a distinct icon and type tone.
- Every document group has a distinct background tone used on group containers, cards, and compact line items.
- The document modal reflects the active document type/group in its header or title region.
- Document displays across the app consume one shared taxonomy instead of separate inline switch statements.
- Unknown or future document types fall back gracefully without breaking layout or contrast.

---

## 2. Context & Background

### Current State

Document classification is already present in backend and frontend contracts:
- `LinkedDocument.docType` supports `prd`, `implementation_plan`, `report`, `phase_plan`, `progress`, `design_doc`, `spec`, and arbitrary strings.
- Planning node types include `design_spec`, `prd`, `implementation_plan`, `progress`, `context`, `tracker`, and `report`.
- Backend classification and normalization live in `backend/document_linking.py` and document parser output in `backend/parsers/documents.py`.
- Feature modal grouping in `components/ProjectBoard.tsx` currently buckets docs into `initialPlanning`, `prd`, `plans`, `progress`, and `context`.

The UI styling is inconsistent:
- `ProjectBoard.tsx` owns local `DOC_TYPE_LABELS`, `DocTypeIcon`, `getDocTypeTone`, and `getDocGroupIcon`.
- `PlanCatalog.tsx` mostly uses a generic `FileText` icon with limited type distinction.
- `DocumentModal.tsx` uses a generic header and simple type chip.
- Planning pages have their own icon selections for node/artifact types.
- Compact linked document rows and secondary references often do not inherit document type or group color.

### Supported Types and Groups

The shared taxonomy should cover these canonical document types:
- `prd`
- `implementation_plan`
- `phase_plan`
- `progress`
- `report`
- `spec`
- `design_doc`
- `design_spec` as an alias/subtype of design documentation
- `context`
- `tracker`
- `spike`
- `adr`
- `document` / `unknown`

The shared taxonomy should cover these canonical groups:
- `initialPlanning`: reports, SPIKEs, ADRs, analysis, discovery, research, and design/spec artifacts that precede PRD/planning
- `prd`: product requirements and feature definition
- `plans`: implementation plans and phase plans
- `progress`: execution progress and phase tracking files
- `context`: worknotes, context files, and supporting references
- `unknown`: uncategorized or future document types

---

## 3. Problem Statement

Users rely on linked documents to understand a feature's planning state and execution evidence. Today, document displays do not carry a consistent visual language across the app. Some areas distinguish PRDs, plans, progress, and reports; other areas show every document as a generic file. Group containers also look similar, so the feature modal's Documents tab requires extra reading and scanning to understand whether a row is a planning input, requirements doc, execution plan, or progress tracker.

This creates three UX problems:
- Users must read labels and paths repeatedly to classify documents.
- The same document type can look different depending on where it appears.
- The app has multiple local type-to-icon mappings, making future document types easy to miss.

---

## 4. Goals & Success Metrics

### Goals

- Create a single frontend source of truth for document visual metadata.
- Give every supported document type a custom icon and accessible color treatment.
- Give every document group a custom background treatment for rows, cards, group panels, progress phase buckets, and document modal headers.
- Apply the taxonomy consistently across all document display surfaces.
- Preserve scannability in dense operational views.

### Success Metrics

- All known document types render with non-generic icon/color metadata in the feature modal and document modal.
- No duplicated document type icon switch remains in major UI surfaces.
- Visual regression screenshots show distinct group backgrounds in the feature modal Documents tab.
- Component tests cover canonical type/group mapping and unknown fallback behavior.
- Colors meet expected dark-theme contrast for label text and icons.

---

## 5. Requirements

### Functional Requirements

| ID | Requirement | Priority |
| --- | --- | --- |
| FR-1 | Add a shared document visual taxonomy helper that maps document type/subtype/root kind/path/title metadata to canonical type and group metadata. | Must |
| FR-2 | Provide a custom icon, label, accent text class, border class, chip class, row/card background class, and group background class for every supported type and group. | Must |
| FR-3 | Replace local document icon/tone/group logic in `ProjectBoard.tsx` with the shared taxonomy while preserving current sorting/grouping behavior. | Must |
| FR-4 | Apply group-colored backgrounds to feature modal Overview linked-document line items. | Must |
| FR-5 | Apply group-colored backgrounds to feature modal Documents tab group sections, cards, and progress phase buckets. | Must |
| FR-6 | Apply the active document type/group color to `DocumentModal` header/title area and linked-document relationship rows. | Must |
| FR-7 | Update `/plans` catalog card view, list view, tree detail, and active document panel to use the shared taxonomy. | Must |
| FR-8 | Update Planning artifact pages, quick view, and tracker intake chips/buttons to use shared document icons where document/node types are displayed. | Should |
| FR-9 | Update secondary document references in execution workbench, blocking feature list, and codebase explorer where docs are linked or displayed. | Should |
| FR-10 | Provide graceful fallback styling for unknown or future doc types. | Must |
| FR-11 | Keep background tones subtle enough that status colors, execution gates, and selected/hover states remain legible. | Must |
| FR-12 | Avoid layout shifts and text overflow in compact rows, chips, and modal headers. | Must |

### Non-Functional Requirements

- No backend schema change is required for v1.
- The shared taxonomy must accept both `LinkedDocument` and `PlanDocument` shaped inputs.
- The taxonomy must be compatible with existing Tailwind build behavior; dynamic class names should be enumerated in source or returned as stable literal strings.
- The implementation should avoid introducing new runtime dependencies.
- Existing document sorting, grouping, click behavior, and modal routing must be preserved.

---

## 6. Scope

### In Scope

- Shared frontend document visual taxonomy module.
- Feature modal Overview and Documents tab document rows/cards/groups.
- Document modal header and relationships tab document rows.
- Plan catalog card/list/tree/detail surfaces.
- Planning views that display artifact/document type chips.
- Secondary document links in execution and investigation surfaces where feasible.
- Unit/component tests for taxonomy and representative UI usage.

### Out of Scope

- Changing backend document classification rules, except for follow-up bug fixes discovered during implementation.
- Adding new document parser types.
- Redesigning the full feature modal layout beyond document visual treatments.
- User-customizable colors or themes for document types.
- Light-theme-specific redesign beyond preserving current token compatibility.

---

## 7. UX Guidelines

- Colors should communicate document family, not dominate the page.
- Group backgrounds should be visible on dark surfaces but remain lower emphasis than active status, danger, and success states.
- Icons should come from `lucide-react` and should use familiar symbols where available:
  - PRD: clipboard/list or file check
  - implementation plan: layers/map
  - phase plan: route/list tree
  - progress: terminal/activity/check circle
  - report: chart/bar chart
  - spec/design: file search/palette/ruler
  - context: notebook/tag
  - tracker: list todo/checklist
  - SPIKE/research: search/compass
  - ADR/decision: scale/gavel-like available icon
- Avoid one-hue palettes. Use distinct but restrained families across planning, requirements, execution, evidence, design, and context.
- Compact rows must keep icon, title, type chip, and external-link affordance visible without wrapping into awkward heights.

---

## 8. Acceptance Criteria

- [ ] A single shared module exports document type metadata, group metadata, and helper functions for `PlanDocument`/`LinkedDocument` inputs.
- [ ] Feature modal Overview linked-document rows use group backgrounds and type icons for all supported types.
- [ ] Feature modal Documents tab group sections have group-specific backgrounds, and child cards/rows use the matching group background with type accents.
- [ ] Progress phase buckets use the progress group background rather than generic muted styling.
- [ ] `DocumentModal` header/title bar reflects the active document type or group, and relationship document rows use taxonomy styling.
- [ ] `/plans` card, list, tree detail, and active panel surfaces use taxonomy icons and type/group colors.
- [ ] Planning artifact drill-down rows and quick-view document actions use taxonomy icons for the displayed artifact type.
- [ ] Unknown document types render with a stable fallback label, icon, and neutral background.
- [ ] Tests cover all canonical document types, aliases, group resolution, and unknown fallback.
- [ ] Existing tests for feature modal, plan catalog, and document modal behavior pass.

---

## 9. Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Color noise makes dense operational screens harder to scan. | Medium | Use subtle backgrounds and reserve saturated colors for icons/chips. Validate with screenshots. |
| Dynamic Tailwind classes are purged or not generated. | High | Return literal class strings from a static config module. Avoid computed class fragments. |
| Multiple document contracts lead to incomplete mapping. | Medium | Build helpers around optional fields and test both `PlanDocument` and `LinkedDocument` examples. |
| Existing status colors conflict with document colors. | Medium | Keep document group color on containers and type color on icon/chip only; leave status chips unchanged. |
| Aliases like `design_spec` and `design_doc` diverge between surfaces. | Medium | Normalize aliases in the shared taxonomy module and document supported aliases in tests. |

---

## 10. Implementation Phases

1. **Taxonomy Foundation:** Create shared module, canonical type/group config, helpers, and tests.
2. **Feature Modal Integration:** Replace local icon/tone/group rendering in `ProjectBoard.tsx` and apply group backgrounds in Overview and Documents tab.
3. **Document Modal and Catalog Integration:** Update `DocumentModal.tsx` and `PlanCatalog.tsx` surfaces.
4. **Planning and Secondary Surfaces:** Update Planning pages, execution workbench, blocking feature list, and codebase explorer where document references appear.
5. **Validation and Polish:** Run tests, inspect UI screenshots, adjust contrast/spacing, and remove obsolete local mappings.

