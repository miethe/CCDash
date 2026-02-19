# Document Entity User Guide

Last updated: 2026-02-19

This guide explains what changed in the Documents experience (`/plans`), what data is available, and how to use the new filters and views.

## What Changed

The Documents system now:

- Indexes both plan docs and progress docs as first-class `Document` records.
- Normalizes key metadata into typed fields (status, subtype, phase, progress, task counts, feature hints, PRD refs).
- Uses canonical project-relative paths for stable identity.
- Supports richer cross-entity linking (`document <-> feature/task/session/document`).
- Provides faceted filtering and broader search coverage in `/plans`.

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

The modal now shows:

- Core typed metadata (`docType`, `docSubtype`, `rootKind`, normalized status)
- Canonical path
- Progress-aware metrics (phase, overall progress, task counters)
- Ownership and contributors
- Request IDs and commit refs
- Link counts and linked entities

Linked entities are sourced from normalized entity links, not from ad-hoc assumptions on frontmatter fields.

## Linked Data Behavior

Links include:

- `Document -> Feature`
- `Document -> Task`
- `Document -> Session`
- `Document -> Document`

Feature links prioritize explicit refs; path inference and referenced-document inheritance are fallback strategies.

## Known Operational Notes

- Very large projects can include hundreds of documents. The UI now pages `/api/documents` behind the scenes and aggregates results.
- If `/plans` appears stale, run a full resync/backfill to refresh typed metadata and links.

## Quick Troubleshooting

1. If `/plans` is empty, check backend logs for `/api/documents` validation errors.
2. If links look missing, run a full forced sync and link rebuild.
3. If a document exists in Feature modal but not `/plans`, verify canonical path normalization and active project roots.

## Related Docs

- `docs/document-entity-spec.md`
- `docs/document-entity-developer-reference.md`
- `docs/entity-linking-user-guide.md`
