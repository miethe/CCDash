---
doc_type: implementation_plan
status: in-progress
category: enhancements

title: "Implementation Plan: Shared Content Viewer Standardization V1"
description: "Adopt @miethe/ui content viewer components in CCDash to unify document, feature, task-source, and file-backed transcript viewing."
author: codex
audience: [ai-agents, developers, engineering-leads]
created: 2026-03-15
updated: 2026-03-19

tags: [implementation, frontend, ui, documents, content-viewer, markdown]
feature_slug: shared-content-viewer-standardization-v1
feature_family: shared-content-viewer-standardization
lineage_family: shared-content-viewer-standardization
lineage_parent: ""
lineage_children: []
lineage_type: iteration
linked_features: [shared-content-viewer-standardization-v1]
prd: null
prd_ref: null
related:
  - package.json
  - tailwind.config.js
  - src/index.css
  - components/DocumentModal.tsx
  - components/PlanCatalog.tsx
  - components/ProjectBoard.tsx
  - components/SessionInspector.tsx
  - components/FeatureExecutionWorkbench.tsx
  - examples/skillmeat/ui/README.md
  - examples/skillmeat/ui/API.md
  - examples/skillmeat/ui/src/content-viewer/ContentPane.tsx
  - examples/skillmeat/ui/src/content-viewer/FileTree.tsx
  - examples/skillmeat/ui/src/content-viewer/adapters.ts
plan_ref: shared-content-viewer-standardization-v1
linked_sessions: []

owner: frontend-platform
owners: [frontend-platform]
contributors: [ai-agents]

complexity: Medium
track: Standard
timeline_estimate: "3-5 implementation days across 4 phases"
---

# Implementation Plan: Shared Content Viewer Standardization V1

## Executive Summary

CCDash already has `@miethe/ui` installed, but file and markdown viewing are still implemented in several local, inconsistent ways:

- `components/DocumentModal.tsx` renders markdown manually with `react-markdown` and uses a raw `textarea` for editing.
- `components/PlanCatalog.tsx` has its own folder explorer and markdown preview implementation.
- `components/ProjectBoard.tsx` shows task source files as raw `<pre>` text in `TaskSourceDialog`.
- `components/SessionInspector.tsx` resolves file-backed activity/files rows to documents, but transcript/detail rendering is still mostly plain text and only indirectly reaches `DocumentModal`.

The best rollout is not a full package-wide adapter migration on day one. The minimum-value path is:

1. Standardize on `@miethe/ui/content-viewer`'s `ContentPane` for all file/document rendering first.
2. Introduce a small CCDash wrapper component to normalize theme, edit behavior, truncation metadata, and source descriptors.
3. Upgrade the highest-value surfaces first: Documents, Feature task source viewing, linked document flows, and file-backed transcript/detail surfaces.
4. Defer `ContentViewerProvider` + `FileTree` adoption until after the base viewer abstraction is stable, because CCDash does not yet have one generic backend contract for "any file in any surface".

This gives the UI/UX standardization you want immediately, without forcing backend work before the first visible wins ship.

## Validated Findings

### Package capabilities already available

From `examples/skillmeat/ui`, the package already provides the core primitives CCDash needs:

- `ContentPane` for markdown, text, and code-like file content with frontmatter handling and edit support.
- `FileTree` for keyboard-accessible tree browsing.
- `ContentViewerProvider` and adapter interfaces for backend-agnostic file tree/content fetching.
- Lazy-loaded markdown editing/preview through `SplitPreview` and `MarkdownEditor`.

Important implementation detail: the minimum rollout does **not** require an adapter. `ContentPane` can be used directly with `path`, `content`, loading, and edit callbacks.

### Current CCDash surfaces to target

#### Tier 1: Immediate adoption targets

1. `components/DocumentModal.tsx`
   - Main document content tab.
   - Linked docs opened from Documents, Features, Sessions, and Execution already converge here.
   - Replacing this one surface upgrades multiple user flows at once.

2. `components/PlanCatalog.tsx`
   - Folder view preview pane currently uses custom markdown rendering.
   - This is the Documents page surface the user explicitly called out.

3. `components/ProjectBoard.tsx`
   - `TaskSourceDialog` currently shows raw source text in a `<pre>`.
   - This is the clearest "view any file" flow outside the Documents page.

#### Tier 2: Follow-up adoption targets

4. `components/SessionInspector.tsx`
   - File-backed rows in `ActivityView` and `FilesView` already resolve to `PlanDocument` where possible.
   - Transcript/detail panes should use the shared viewer only when the selected item is file-backed or clearly markdown, not for all transcript messages.

5. `components/FeatureExecutionWorkbench.tsx`
   - Already relies on `DocumentModal` for linked document viewing.
   - Most benefits arrive automatically once `DocumentModal` is upgraded.

### Integration constraints discovered in CCDash

#### Constraint 1: Tailwind package scanning is not configured

`tailwind.config.js` currently scans local app files only. The `@miethe/ui` package README expects the package dist files to be included in Tailwind content scanning. Without that, some package classes can be purged.

#### Constraint 2: Dark theme activation is inconsistent with package expectations

`src/index.css` defines both light and `.dark` token sets, but CCDash does not currently apply a `dark` class at the document root. Existing CCDash screens mostly avoid the semantic token problem by using hard-coded slate classes. `@miethe/ui` uses semantic classes such as `bg-card`, `text-foreground`, and `text-muted-foreground`, so package surfaces need a consistent dark token strategy before rollout.

#### Constraint 3: CCDash does not yet expose one generic "file tree + file content" API

Current data access is split:

- documents by ID via `/api/documents/{doc_id}`
- task source by path via `/api/features/task-source`
- file references in session/activity views via inferred document linkage and local/GitHub links

That is enough for a shared viewer wrapper, but not yet ideal for a clean app-wide `ContentViewerProvider` adapter spanning all surfaces.

## Recommended Architecture

## 1) Create a CCDash viewer wrapper first

Add a wrapper component, for example:

- `components/content/UnifiedContentViewer.tsx`

Responsibilities:

1. Wrap `ContentPane` from `@miethe/ui/content-viewer`.
2. Accept a CCDash-friendly prop shape:
   - `path`
   - `content`
   - `isLoading`
   - `error`
   - `readOnly`
   - `isEditing`
   - `editedContent`
   - `onEditStart`
   - `onEditChange`
   - `onSave`
   - `onCancel`
   - optional truncation/source metadata
3. Apply any CCDash-specific container styling so package components sit naturally inside the existing dark shell.
4. Centralize heuristics such as:
   - when to mark content read-only
   - when to pass truncation metadata
   - how to label the viewer for accessibility

This keeps package adoption isolated to one seam instead of scattering raw `ContentPane` usage everywhere.

## 2) Treat `DocumentModal` as the primary convergence point

`DocumentModal` should become the canonical document/file viewer shell for CCDash.

After refactor:

1. Replace the current markdown-only content rendering with `UnifiedContentViewer`.
2. Replace the raw markdown `textarea` edit path with package-backed editing for markdown files.
3. Preserve existing document metadata, relationship tabs, save flow, and document link fetching.
4. Keep `DocumentModal` responsible for document-level concerns:
   - document loading
   - save mutation
   - metadata tabs
   - navigation between surfaces

`ContentPane` handles rendering and editing. `DocumentModal` remains the CCDash-specific orchestration layer.

## 3) Use direct props before introducing adapters

For V1, use `ContentPane` directly in local wrappers and dialogs. Do **not** lead with `ContentViewerProvider`.

Reasoning:

1. The user's minimum goal is rendering/viewing consistency, not backend abstraction purity.
2. CCDash already has enough local data for most high-value surfaces.
3. A direct-props rollout reduces risk and gets to user-visible value faster.

## 4) Introduce provider + `FileTree` only for the explorer phase

Use `ContentViewerProvider` and `FileTree` in a later phase when CCDash is ready to normalize one or both of:

1. a document-tree adapter built from the existing document catalog
2. a generic backend file API for path-based browsing outside documents

This should be an optimization phase, not the first phase.

## Phase Breakdown

### Phase 1: Viewer foundation and package compatibility

**Duration**: 0.5-1 day
**Assigned**: frontend-developer

**Objective**: Make `@miethe/ui` render correctly inside CCDash and create the shared wrapper used by all subsequent surfaces.

#### Tasks

1. Update `tailwind.config.js` content globs to include the installed package dist:
   - `./node_modules/@miethe/ui/dist/**/*.js`

2. Normalize dark theme behavior for package surfaces.
   - Preferred option: apply `dark` at the app root or document root.
   - Fallback option: move CCDash semantic tokens so default root values reflect the dark shell.

3. Add `components/content/UnifiedContentViewer.tsx`.

4. Add a small viewer utility module, for example:
   - `lib/contentViewer.ts`

Utility responsibilities:

- normalize file paths
- infer whether content is editable
- build truncation metadata
- optionally detect whether transcript/detail payloads should use file viewer mode

#### Acceptance Criteria

- `@miethe/ui` classes are present in production build output.
- Package surfaces render with dark styling consistent with CCDash.
- One wrapper component exists and is the required entry point for future viewer adoption.

### Phase 2: Minimum rollout to required surfaces

**Duration**: 1.5-2 days
**Assigned**: frontend-developer

**Objective**: Ship the minimum set of surfaces explicitly requested by the user.

#### 2.1 `DocumentModal`

Replace the content tab viewer/editor path with `UnifiedContentViewer`.

Keep:

- save API via `services/documents.ts`
- existing content tab routing
- summary/delivery/relationships/timeline/raw tabs

Expected outcome:

- markdown files render with package preview/frontmatter handling
- non-markdown files render through the same viewer shell
- edit mode is standardized instead of raw textarea-only

#### 2.2 `PlanCatalog` Documents folder view

Replace the middle preview pane renderer with `UnifiedContentViewer`.

Keep for V1:

- current custom document tree built from `filteredDocs`
- current metadata right pane

Do not replace the tree with package `FileTree` yet.

Reason:

- the current document list already produces the explorer structure
- the value here is content rendering standardization, not a tree rewrite

#### 2.3 `ProjectBoard` task source dialog

Replace raw `<pre>` rendering in `TaskSourceDialog` with `UnifiedContentViewer`.

Input data already exists from `/api/features/task-source?file=...`, so no backend work is needed for this change.

Expected outcome:

- task source markdown renders as markdown
- TOML/YAML/JSON/text source files render in a consistent file viewer shell
- future task-source editing can be added without another UI rewrite

#### Acceptance Criteria

- Documents page folder preview uses the shared viewer.
- Document modal content tab uses the shared viewer.
- Feature task source dialog uses the shared viewer.
- Linked docs opened from Features, Sessions, and Execution inherit the new viewer through `DocumentModal`.

### Phase 3: Session transcript and file-backed detail adoption

**Duration**: 1-1.5 days
**Assigned**: frontend-developer

**Objective**: Extend the shared viewer to Session Inspector surfaces without over-applying it to normal conversational transcript entries.

#### Recommended scope

1. `ActivityView`
   - When a row resolves to a linked `PlanDocument`, continue opening `DocumentModal`.
   - For file-backed rows that do not resolve to a document but do have fetchable content, open a lightweight viewer modal using the same wrapper.

2. `FilesView`
   - Same behavior as `ActivityView`.
   - If the file maps to a document, use `DocumentModal`.
   - If it is only a raw file path, use a path-based viewer modal.

3. Transcript detail pane
   - Only switch to shared viewer mode for entries that are clearly file content or markdown artifacts.
   - Keep ordinary transcript messages as conversational text cards.

#### Implementation note

This phase may require one small backend endpoint if CCDash needs to fetch arbitrary project-relative file content beyond plan/progress docs.

Recommended endpoint if needed:

- `GET /api/files/content?path=...`

Rules:

- project-scoped only
- path normalization + traversal protection
- read-only in V1

#### Acceptance Criteria

- Session inspector can open a shared viewer for file-backed details, even when the file is not a typed plan document.
- Transcript conversation cards are not regressed into "everything is a file" behavior.

### Phase 4: Optional explorer unification with `FileTree` and adapters

**Duration**: 1 day
**Assigned**: frontend-developer, backend-architect

**Objective**: Replace local explorer/tree implementations with package-native `FileTree` where it materially reduces duplication.

#### Candidate targets

1. `PlanCatalog` folder explorer
2. a future generic session file browser
3. any feature/file browsing pane added later

#### Recommended adapter strategy

Option A: Document-only adapter first

- Build a document artifact adapter that treats the document catalog as one virtual artifact.
- `useFileTree` returns a tree derived from `PlanDocument.filePath`.
- `useFileContent` fetches document content by `doc.id` after path lookup.

Option B: Generic file adapter after backend endpoint exists

- Back the adapter with a unified file tree/content API.
- Use that same adapter for documents, task source, and session file browsing.

Recommendation:

- Start with Option A only if replacing the current document tree actually removes enough duplicate code to justify it.
- Otherwise keep the custom tree and stop after Phase 3.

#### Acceptance Criteria

- Any explorer migrated to `FileTree` has no net loss in keyboard support, path selection, or metadata affordances.
- Adapter logic is centralized and not duplicated per page.

## Surface-by-Surface Recommendation Matrix

| Surface | Current state | V1 recommendation | Requires backend work? |
|---|---|---|---|
| `DocumentModal` | Manual markdown + textarea editor | Replace content tab with `UnifiedContentViewer` | No |
| `PlanCatalog` folder preview | Manual markdown preview | Replace preview pane with `UnifiedContentViewer` | No |
| `ProjectBoard` task source dialog | Raw `<pre>` | Replace dialog body with `UnifiedContentViewer` | No |
| `FeatureExecutionWorkbench` linked docs | Uses `DocumentModal` | Inherits improvement automatically | No |
| `SessionInspector` linked docs | Uses `DocumentModal` in activity/files flows | Inherits improvement automatically | No |
| `SessionInspector` raw file-backed details | No shared viewer | Add lightweight viewer modal in Phase 3 | Possibly |
| `PlanCatalog` tree UI | Custom tree | Defer package `FileTree` to optional phase | No |

## Testing Plan

### Unit / component coverage

1. Add tests for `UnifiedContentViewer`:
   - markdown render path
   - non-markdown render path
   - edit flow callbacks
   - frontmatter display behavior

2. Add regression tests for `DocumentModal`:
   - content tab render
   - markdown edit/save flow
   - non-markdown display

3. Add regression tests for `TaskSourceDialog`:
   - loading
   - error
   - markdown rendering

### Integration checks

1. Validate Tailwind build picks up `@miethe/ui` classes.
2. Validate dark theme tokens on package surfaces.
3. Smoke test:
   - Documents page explorer preview
   - Feature linked doc modal
   - Session linked doc modal
   - Feature task source dialog

### Manual QA scenarios

1. Open a PRD from Documents and confirm frontmatter is collapsed and content is readable.
2. Open an implementation plan from a feature modal and confirm the viewer matches the Documents surface.
3. Open a progress/task source markdown file and confirm headings, lists, code fences, and links render correctly.
4. Open a non-markdown source file and confirm raw content rendering is stable and legible.

## Risks and Mitigations

### Risk 1: Package styling renders light or partially unstyled

**Cause**:
- Tailwind purge misses package classes
- `.dark` is not consistently applied

**Mitigation**:
- Fix Tailwind content globs first
- make dark token activation a Phase 1 exit criterion

### Risk 2: Transcript surfaces become too aggressive about "file mode"

**Cause**:
- trying to use the content viewer for normal transcript prose

**Mitigation**:
- restrict viewer usage to file-backed or clearly markdown payloads
- keep conversational transcript cards unchanged

### Risk 3: Premature adapter abstraction slows the rollout

**Cause**:
- trying to solve generic file APIs before shipping visible improvements

**Mitigation**:
- use direct-prop `ContentPane` integration first
- defer provider/adapters to the optional explorer phase

## Recommended Implementation Order

1. Phase 1 foundation
2. `DocumentModal`
3. `PlanCatalog` preview pane
4. `ProjectBoard` task source dialog
5. Session file-backed detail modal
6. Optional `FileTree`/adapter migration only if the first rollout proves stable and valuable

## Definition of Done

This effort is complete when:

1. CCDash uses one shared viewer implementation for document and file rendering across the primary surfaces.
2. Documents, Features, Sessions, and task-source flows all present markdown/files through the same visual and interaction model.
3. Package styling is stable in production builds.
4. Session transcript/detail integration improves file-backed viewing without regressing normal transcript readability.
