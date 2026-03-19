# Shared Content Viewer User Guide

Last updated: 2026-03-19

This guide explains where the shared content viewer appears in CCDash, what it renders, and what behavior to expect across documents, task sources, and session detail flows.

## What changed

CCDash now uses a common viewer shell for long-form document and file content across the main product surfaces.

The shared viewer now supports:

- formatted markdown rendering for documents, plans, prompts, and other markdown-like content
- collapsed frontmatter display when YAML frontmatter is present
- consistent code/text rendering with horizontal scrolling for long lines
- a lightweight raw file viewer modal for file-backed session rows that are not typed documents
- transcript/detail-pane escalation into the viewer when content is clearly long-form or markdown-like

## Where you will see it

## Documents (`/plans`)

The shared viewer is used in:

- the folder preview pane in `Plan Catalog`
- the `Content` tab inside `Document Modal`

What to expect:

- markdown docs render as formatted content instead of raw source text
- frontmatter is shown separately from the body
- implementation plans, PRDs, reports, and progress docs share the same visual shell

## Feature Board (`/board`)

The shared viewer is used in the task source dialog for feature tasks.

What to expect:

- markdown task source files render with headings, lists, code fences, and links
- JSON, TOML, YAML, and source files render in a code-style pane with horizontal scroll for long lines

## Session Inspector (`/sessions`)

The shared viewer appears in three places:

- `Activity` tab: file-backed rows can open in the shared viewer
- `Files` tab: file rows can open in the shared viewer
- transcript/detail pane: long-form or markdown-like payloads can switch from plain cards to the shared viewer

Session behavior is intentionally narrow:

- typed linked documents still open in `Document Modal`
- short conversational transcript messages remain normal transcript cards
- only file-backed, long-form, or markdown-like detail content escalates into the viewer

## Raw file viewer modal

When a session file row maps to a project file but not to a typed plan document, CCDash opens a lightweight read-only viewer modal.

This modal:

- fetches the current file content through the app backend
- keeps the file read-only
- includes a shortcut to open the same file locally in VS Code

## Transcript and prompt rendering

Long prompts and other long-form detail payloads can now render in the shared viewer instead of a raw `<pre>` block.

Examples include:

- expanded task prompts in Session Inspector tool details
- markdown-like session detail content
- read-tool outputs that contain structured file content

Read-tool line prefixes are normalized before rendering so the viewer shows the file body instead of transport-specific line-number formatting.

## Editing behavior

Editing remains limited to the document flows that already supported it:

- project plan documents can still be edited from `Document Modal`
- progress docs remain read-only
- raw file viewer modal in Session Inspector is read-only

## What the viewer does with different content

- Markdown or markdown-like content: renders as formatted markdown
- Frontmatter-bearing content: shows frontmatter separately and keeps it out of the body preview
- Code/text content: renders in a monospace pane with horizontal scrolling for long lines
- Large files: show a truncation banner when CCDash is only showing a partial preview

## Troubleshooting

1. If markdown still looks raw, confirm you are looking at a viewer surface and not a short plain transcript card.
2. If a session file row opens locally but not in the viewer, the file may no longer exist or may not be readable from the active project context.
3. If the viewer looks stale after edits or sync changes, run a cache rescan and reopen the surface.

## Related docs

- `docs/document-entity-user-guide.md`
- `docs/execution-workbench-user-guide.md`
- `docs/codebase-explorer-developer-reference.md`
- `docs/shared-content-viewer-developer-reference.md`
