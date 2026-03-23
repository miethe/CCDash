# Document Entity User Guide

Last updated: 2026-03-12

This guide explains what changed in the Documents experience (`/plans`), what data is available, and how to use the new filters and views.

## What Changed

The Documents system now:

- Indexes both plan docs and progress docs as first-class `Document` records.
- Normalizes canonical schema fields into typed metadata (description/summary, priority/risk/complexity/track, timeline/release/milestone, readiness/test impact, typed linked-feature refs, and doc-type-specific blocks).
- Uses canonical project-relative paths for stable identity.
- Supports richer cross-entity linking (`document <-> feature/task/session/document`).
- Provides faceted filtering and broader search coverage in `/plans`.
- Preserves migration compatibility for legacy frontmatter aliases and superseded root-level schema docs.

## Document Sources

Documents are ingested from:

- Project plans root: `docs/project_plans/...`
- Progress root: `.claude/progress/...`

Progress files remain first-class documents, but the default `/plans` scope starts on non-progress-focused content.

## Using `/plans`

## Scope tabs

Top-level tabs let you quickly narrow the document set:

- `Plans`
- `PRDs`
- `Reports`
- `Progress`
- `All`

## Filters

The sidebar supports faceted filtering by:

- `Subtype`
- `Type`
- `Status`
- `Category`
- `Feature`
- `PRD`
- `Phase`
- `Frontmatter presence`

Filter values are normalized into a fixed canonical set before faceting so historical value drift does not fragment options.

- `Status` canonical values: `pending`, `in_progress`, `review`, `completed`, `deferred`, `blocked`, `archived`, `inferred_complete`
- `Subtype` canonical values:
  - `implementation_plan`, `phase_plan`, `prd`, `report`, `spec`
  - `design_spec`, `design_doc`, `spike`, `idea`, `bug_doc`
  - `progress_phase`, `progress_all_phases`, `progress_quick_feature`, `progress_other`
  - `document` (fallback)

## Search

Search now matches across:

- Title and paths
- Type/subtype/category/status
- Feature and PRD hints
- Phase token
- Request IDs
- Commit refs
- Linked refs (`relatedRefs`, `pathRefs`, `slugRefs`, linked features/sessions)
- Typed metadata blocks (owners/contributors/request IDs/commit refs)

## Document Modal

The modal now uses canonical tabs:

1. `Summary`
2. `Delivery`
3. `Relationships`
4. `Content`
5. `Timeline`
6. `Raw`

Across these tabs it shows:

- Core typed metadata (`docType`, `docSubtype`, `rootKind`, normalized status)
- Canonical path and ownership/audience metadata
- Delivery/execution metadata (`execution_readiness`, `timeline_estimate`, `test_impact`, file/context/source refs)
- Progress-aware metrics (phase, overall progress, task counters)
- Typed feature relationships (`linked_features[]` with type/source/confidence)
- Request IDs, commit refs, PR refs, and linked entities

Linked entities are sourced from normalized entity links, not from ad-hoc assumptions on frontmatter fields.

The dependency-aware execution rollout also surfaces a few document-specific behaviors in the modal:

- `Relationships` now includes linked feature pills that navigate back to the feature board.
- `Blocked By` metadata is rendered as hard dependency chips so blocked plans and progress files are obvious at a glance.
- Family lineage and sequence metadata remain visible in the `Summary` tab, matching the family-aware summaries in the board and workbench.

## Editing and save behavior

- Plan documents (`rootKind = project_plans`) can be edited directly from the modal `Content` view.
- Progress documents remain view-only in this flow.
- Local plan docs write back to the underlying file immediately when saved.
- GitHub-backed plan docs require an enabled GitHub integration plus project/repo write access before save is allowed.
- When GitHub write-back is available, CCDash writes through the managed repo workspace, creates a commit, pushes it to the configured branch, and refreshes document state in the UI.
- Operators can provide an optional commit message during save; otherwise CCDash uses the default managed write-back message.

## Linked Data Behavior

Links include:

- `Document -> Feature`
- `Document -> Task`
- `Document -> Session`
- `Document -> Document`

Feature links prioritize explicit refs; path inference and referenced-document inheritance are fallback strategies.

## Completion Equivalence and Write-Through

Feature completion now treats the following document collections as equivalent completion sources:

- PRD completion
- Plan completion (top-level implementation plan, or all phase-plan docs when those are the plan shape)
- All linked progress phase documents completed

If any of those completion groups is complete, the Feature is treated as `done` even when other linked docs were not manually updated.

When completion is inferred this way, CCDash writes through to linked PRD/Plan docs and sets their frontmatter status to `inferred_complete` when they were not already completion-equivalent.

## Known Operational Notes

- Very large projects can include hundreds of documents. The UI now pages `/api/documents` behind the scenes and aggregates results.
- If `/plans` appears stale, run a full resync/backfill (`POST /api/cache/sync` with `force=true`) to refresh typed metadata and links.

## Quick Troubleshooting

1. If `/plans` is empty, check backend logs for `/api/documents` validation errors.
2. If links look missing, run a full forced sync and link rebuild.
3. If a document exists in Feature modal but not `/plans`, verify canonical path normalization and active project roots.

## Related Docs

- `docs/schemas/document_frontmatter/README.md`
- `docs/schemas/document_frontmatter/document-and-feature-mapping.md`
- `docs/document-entity-developer-reference.md`
- `docs/entity-linking-user-guide.md`
