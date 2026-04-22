# Shared Content Viewer Guide

User behavior and developer implementation details for shared content rendering across documents, tasks, and sessions.

> Consolidated from the former top-level user and developer docs. `docs/project_plans/` content was intentionally left untouched.

## User Guide

Last updated: 2026-03-19

This guide explains where the shared content viewer appears in CCDash, what it renders, and what behavior to expect across documents, task sources, and session detail flows.

### What changed

CCDash now uses a common viewer shell for long-form document and file content across the main product surfaces.

The shared viewer now supports:

- formatted markdown rendering for documents, plans, prompts, and other markdown-like content
- collapsed frontmatter display when YAML frontmatter is present
- consistent code/text rendering with horizontal scrolling for long lines
- a lightweight raw file viewer modal for file-backed session rows that are not typed documents
- transcript/detail-pane escalation into the viewer when content is clearly long-form or markdown-like

### Where you will see it

### Documents (`/plans`)

The shared viewer is used in:

- the folder preview pane in `Plan Catalog`
- the `Content` tab inside `Document Modal`

What to expect:

- markdown docs render as formatted content instead of raw source text
- frontmatter is shown separately from the body
- implementation plans, PRDs, reports, and progress docs share the same visual shell

### Feature Board (`/board`)

The shared viewer is used in the task source dialog for feature tasks.

What to expect:

- markdown task source files render with headings, lists, code fences, and links
- JSON, TOML, YAML, and source files render in a code-style pane with horizontal scroll for long lines

### Session Inspector (`/sessions`)

The shared viewer appears in three places:

- `Activity` tab: file-backed rows can open in the shared viewer
- `Files` tab: file rows can open in the shared viewer
- transcript/detail pane: long-form or markdown-like payloads can switch from plain cards to the shared viewer

Session behavior is intentionally narrow:

- typed linked documents still open in `Document Modal`
- short conversational transcript messages remain normal transcript cards
- only file-backed, long-form, or markdown-like detail content escalates into the viewer

### Raw file viewer modal

When a session file row maps to a project file but not to a typed plan document, CCDash opens a lightweight read-only viewer modal.

This modal:

- fetches the current file content through the app backend
- keeps the file read-only
- includes a shortcut to open the same file locally in VS Code

### Transcript and prompt rendering

Long prompts and other long-form detail payloads can now render in the shared viewer instead of a raw `<pre>` block.

Examples include:

- expanded task prompts in Session Inspector tool details
- markdown-like session detail content
- read-tool outputs that contain structured file content

Read-tool line prefixes are normalized before rendering so the viewer shows the file body instead of transport-specific line-number formatting.

### Editing behavior

Editing remains limited to the document flows that already supported it:

- project plan documents can still be edited from `Document Modal`
- progress docs remain read-only
- raw file viewer modal in Session Inspector is read-only

### What the viewer does with different content

- Markdown or markdown-like content: renders as formatted markdown
- Frontmatter-bearing content: shows frontmatter separately and keeps it out of the body preview
- Code/text content: renders in a monospace pane with horizontal scrolling for long lines
- Large files: show a truncation banner when CCDash is only showing a partial preview

### Troubleshooting

1. If markdown still looks raw, confirm you are looking at a viewer surface and not a short plain transcript card.
2. If a session file row opens locally but not in the viewer, the file may no longer exist or may not be readable from the active project context.
3. If the viewer looks stale after edits or sync changes, run a cache rescan and reopen the surface.

### Related docs

- `docs/guides/document-entity-and-linking.md`
- `docs/guides/execution-workbench.md`
- `docs/developer/codebase-explorer.md`
- `docs/guides/shared-content-viewer.md`

## Developer Reference

Last updated: 2026-03-19

This reference covers the CCDash-specific shared content viewer wrapper, where it is used, and the configuration assumptions behind the current rendering behavior.

### Goals

- standardize document and file rendering across primary surfaces
- preserve edit behavior where CCDash already supported writes
- keep transcript/detail usage selective instead of replacing normal conversational cards
- align read-only rendering more closely with the SkillMeat parent experience

### Primary files

### Shared wrapper and helpers

- `components/content/UnifiedContentViewer.tsx`
- `lib/contentViewer.ts`
- `lib/sessionContentViewer.ts`
- `src/index.css`

### Consumers

- `components/DocumentModal.tsx`
- `components/PlanCatalog.tsx`
- `components/ProjectBoard.tsx`
- `components/SessionInspector.tsx`
- `components/content/ProjectFileViewerModal.tsx`

### Backend support for raw session file views

- `backend/routers/codebase.py`
- `backend/services/codebase_explorer.py`

Session Inspector raw file modals rely on `GET /api/codebase/file-content?path=...`.

Current behavior:

- project-scoped reads are supported
- current worktree also accepts absolute filesystem paths through the backend helper
- responses are read-only
- large files can be truncated before display

### Rendering model

`UnifiedContentViewer` has two main paths:

1. Editing path
   - delegates to `@miethe/ui/content-viewer` `ContentPane`
   - preserves existing document edit/start/save/cancel flows

2. Non-editing path
   - uses a CCDash-side read-only renderer
   - applies markdown detection, frontmatter separation, and code/text overflow handling
   - uses shared CSS under `.ccdash-content-viewer`

This split is intentional. It keeps package-based editing behavior while giving CCDash tighter control over read-only rendering quality.

### Mode detection

`lib/contentViewer.ts` resolves the viewer mode with two signals:

- file extension
- markdown-like content heuristics for read-only views

Markdown-like detection currently looks for signals such as:

- headings
- blockquotes
- bullet or ordered lists
- fenced code blocks
- tables
- YAML frontmatter

That allows markdown rendering even when the source does not have a `.md` extension.

### Transcript/detail heuristics

`lib/sessionContentViewer.ts` is responsible for Session Inspector-specific viewer escalation.

Current rules:

- read-tool outputs can render in the viewer when a file path and usable output body exist
- consistent line-number prefixes are stripped from read-tool output before rendering
- generic transcript/detail payloads only escalate into the viewer when they are long-form or markdown-like
- short conversational content remains in the existing transcript cards

Current thresholds:

- character threshold: `600`
- line threshold: `14`

If these need tuning, update them in `lib/sessionContentViewer.ts` instead of adding per-surface exceptions.

### Styling and configuration

### Tailwind/package scanning

`tailwind.config.js` must continue to scan:

- local app files
- `./node_modules/@miethe/ui/dist/**/*.js`

Without the package dist glob, package classes can be purged.

### Dark mode

The app expects the root dark class to be active:

- `index.tsx` adds `dark` to `document.documentElement`
- `src/index.css` defines the semantic token values used by the package and the CCDash wrapper

### CCDash-specific read-only styles

`src/index.css` provides the wrapper styling for:

- markdown headings, paragraphs, lists, tables, blockquotes, and inline code
- pre/code blocks with horizontal scrolling
- mode-specific whitespace behavior for code/text panes

These styles intentionally live in CCDash rather than the package so the app can keep its own visual language.

### Usage guidance

Use `UnifiedContentViewer` when:

- the surface should display document or file content in the standard CCDash shell
- the content may be markdown or markdown-like
- frontmatter separation should remain consistent with documents and plans

Prefer `DocumentModal` when:

- the item is a typed `PlanDocument`
- you need document relationships, delivery metadata, or edit/save behavior

Prefer `ProjectFileViewerModal` when:

- the item is a file-backed session row
- the file is not a typed document
- the flow should stay read-only

### Example

```tsx
<UnifiedContentViewer
  path={doc.filePath}
  content={doc.content}
  readOnly={!canEdit}
  isEditing={isEditing}
  editedContent={draftContent}
  onEditStart={handleStartEdit}
  onEditChange={setDraftContent}
  onSave={handleSave}
  onCancel={handleCancelEdit}
/>
```

### Validation

Focused coverage currently lives in:

- `components/content/__tests__/UnifiedContentViewer.test.tsx`
- `lib/__tests__/contentViewer.test.ts`
- `lib/__tests__/sessionContentViewer.test.ts`
- `backend/tests/test_codebase_router.py`

Recommended checks after changes:

```bash
pnpm exec vitest run \
  lib/__tests__/contentViewer.test.ts \
  lib/__tests__/sessionContentViewer.test.ts \
  components/content/__tests__/UnifiedContentViewer.test.tsx

backend/.venv/bin/python -m unittest backend.tests.test_codebase_router
```

### Known caveats

- Repo-wide `pnpm typecheck` currently includes unrelated example-suite noise; filter by touched files when validating this area.
- Transcript escalation is heuristic-based by design. If a payload should stay a plain card, prefer tightening the shared thresholds before adding special-case UI logic.
