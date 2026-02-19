# Document Entity Developer Reference

Last updated: 2026-02-19

This is the implementation-level reference for the document-entity enhancement pass.

## Goals

- Treat progress markdown as first-class documents.
- Persist typed metadata in DB for stable filtering/search.
- Use canonical project-relative path identity everywhere possible.
- Improve document mapping to features/tasks/sessions/documents.
- Expose a paginated/filterable document API and facet catalog.

## Core Components

## Shared linking/normalization

- `backend/document_linking.py`
  - Canonical path/root helpers
  - Subtype/root classification
  - Expanded frontmatter ref extraction (`plan_ref`, `prd_link`, `related_documents`, `request_log_id`, etc.)

## Parsing

- `backend/parsers/documents.py`
  - Parses frontmatter/body
  - Produces typed `PlanDocument`
  - Computes:
    - `docType`, `docSubtype`, `rootKind`
    - `statusNormalized`
    - `featureSlugHint`, `featureSlugCanonical`
    - `phaseToken`, `phaseNumber`
    - `overallProgress`, task counters
    - owners/contributors/request/commit refs
    - normalized `dates` + `timeline` with confidence/source metadata

- `backend/parsers/features.py`
  - Reuses document-level date extraction for linked docs when deriving feature timelines/dates.

## Sync and linking

- `backend/db/sync_engine.py`
  - Synces docs from both plan and progress roots
  - Synces changed progress markdown into both `documents` and `tasks`
  - Rebuilds document links to features/tasks/sessions/documents
  - Uses canonical project root inference
  - Builds git date metadata in batches (no per-file git calls)

## Storage

- `backend/db/sqlite_migrations.py`
- `backend/db/postgres_migrations.py`
- `backend/db/repositories/documents.py`
- `backend/db/repositories/postgres/documents.py`

Enhancements include typed columns in `documents` and normalized `document_refs` table.

## API

- `backend/routers/api.py`
  - `GET /api/documents` (paginated + filterable)
  - `GET /api/documents/catalog` (facet counts)
  - `GET /api/documents/{doc_id}`
  - `GET /api/documents/{doc_id}/links`

## Frontend

- `types.ts`: expanded `PlanDocument` shape
- `contexts/DataContext.tsx`: paged document fetching
- `components/PlanCatalog.tsx`: scope tabs, facets, metadata-aware search
- `components/DocumentModal.tsx`: typed metadata + normalized links panels
- `components/ProjectBoard.tsx`: canonical path doc resolution fallback

## Canonical Identity Rules

- Canonical path is project-relative and slash-normalized.
- Document IDs are path-derived (`DOC-...`) and stable against absolute path drift.
- Linking logic should prefer canonical path comparisons before legacy/fallback matching.

## Link Strategy Summary

## Document -> Feature

Priority:

1. Explicit frontmatter refs (`linkedFeatures`, parsed feature refs, PRD refs)
2. Canonical/path-derived feature hint
3. Referenced-document inheritance

Metadata includes strategy and confidence.

## Document -> Document

- Path refs from normalized ref extraction are resolved to document IDs via canonical path.

## Document -> Task

- Progress document source path links to tasks parsed from that same canonical source file.

## Document -> Session

- Explicit session refs in document frontmatter
- Task session refs inherited through linked tasks

## DB Notes

`documents` now includes typed fields for:

- Identity and classification (`canonical_path`, `root_kind`, `doc_subtype`, etc.)
- Search/filter keys (`status_normalized`, `feature_slug_canonical`, `phase_token`, etc.)
- Progress metrics (`overall_progress`, task counters)
- `metadata_json` (typed extension payload)

`document_refs` stores normalized reference rows:

- `(document_id, ref_kind, ref_value_norm, source_field)` uniqueness
- `(project_id, ref_kind, ref_value_norm)` query index

## API Filter Parameters

`GET /api/documents` supports:

- `q`
- `doc_subtype`
- `root_kind`
- `doc_type`
- `category`
- `status`
- `feature`
- `prd`
- `phase`
- `include_progress`
- `offset`
- `limit`

## Verification and Backfill

For existing projects, run a full forced sync after migration updates.

Expected outcomes:

- `documents` populated for plans + progress markdown
- typed columns and `document_refs` filled
- link graph rebuilt with document-centric mappings
- date fields recomputed from normalized precedence (frontmatter + git + filesystem)

## Date Resolution Strategy

`createdAt` precedence:

1. frontmatter `created*` (`high`)
2. git first commit touching file (`high`)
3. filesystem birthtime (`medium`)
4. filesystem mtime fallback (`low`)

`updatedAt` precedence:

1. git latest commit touching file (`high`)
2. frontmatter `updated*` (`medium`)
3. filesystem mtime when file is dirty/untracked (`high`)
4. filesystem mtime fallback (`low`)
5. frontmatter created fallback (`low`)

`completedAt` precedence:

1. frontmatter `completed*` (`high`)
2. frontmatter `updated*` for completion-equivalent statuses (`medium`)
3. filesystem mtime fallback for completion-equivalent statuses (`low`)

Implementation references:

- `backend/db/sync_engine.py` (`_build_git_doc_dates`, `_sync_documents`, `sync_changed_files`, `_sync_features`)
- `backend/parsers/documents.py` (`_build_document_date_fields_with_git`)
- `backend/parsers/features.py` (`_extract_doc_metadata`, `scan_features`)

## One-Time Date Backfill (Existing Data)

Use a full forced sync to recalculate and persist dates for all docs/features:

```bash
curl -X POST http://127.0.0.1:8000/api/cache/sync \
  -H 'Content-Type: application/json' \
  -d '{"force": true, "background": true, "trigger": "api"}'
```

Then poll operation status until `completed`:

```bash
curl http://127.0.0.1:8000/api/cache/operations/<operation_id>
```

This backfills existing rows; no manual per-file migration is required.

## Tests Added/Updated

- `backend/tests/test_document_linking.py`
- `backend/tests/test_documents_parser.py`

Coverage includes:

- canonical path/root handling
- subtype classification
- expanded frontmatter key extraction
- typed progress metadata parsing
