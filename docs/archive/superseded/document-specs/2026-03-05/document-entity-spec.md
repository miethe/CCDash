# Document Entity Specification

Last updated: 2026-02-19
Version: 1.1

This specification defines the normalized `Document` data model, DB schema, API contracts, and UI-facing object shape.

## 1. Domain Model

A `Document` is any indexed markdown artifact from configured plan/progress roots.

## 1.1 Runtime model (`PlanDocument`)

Source of truth: `backend/models.py` and `types.ts`.

### Core fields

- `id: string`
- `title: string`
- `filePath: string`
- `canonicalPath: string`
- `status: string`
- `statusNormalized: string`
- `author: string`
- `lastModified: string`
- `docType: string`
- `docSubtype: string`
- `rootKind: "project_plans" | "progress" | "document"`
- `category: string`
- `content?: string`

### Classification and identity

- `hasFrontmatter: boolean`
- `frontmatterType: string`
- `featureSlugHint: string`
- `featureSlugCanonical: string`
- `prdRef: string`
- `phaseToken: string`
- `phaseNumber?: number`

### Progress/task metrics

- `overallProgress?: number`
- `totalTasks: number`
- `completedTasks: number`
- `inProgressTasks: number`
- `blockedTasks: number`

### Derived arrays

- `pathSegments: string[]`
- `featureCandidates: string[]`

### Frontmatter payload

`frontmatter` (normalized + raw fidelity):

- `tags: string[]`
- `linkedFeatures?: string[]`
- `linkedSessions?: string[]`
- `version?: string`
- `commits?: string[]`
- `prs?: string[]`
- `relatedRefs?: string[]`
- `pathRefs?: string[]`
- `slugRefs?: string[]`
- `prd?: string`
- `prdRefs?: string[]`
- `fieldKeys?: string[]`
- `raw?: Record<string, any>`

### Typed metadata block

`metadata`:

- `phase?: string`
- `phaseNumber?: number`
- `overallProgress?: number`
- `taskCounts`:
  - `total: number`
  - `completed: number`
  - `inProgress: number`
  - `blocked: number`
- `owners?: string[]`
- `contributors?: string[]`
- `requestLogIds?: string[]`
- `commitRefs?: string[]`
- `featureSlugHint?: string`
- `canonicalPath?: string`

### Link summary

`linkCounts`:

- `features: number`
- `tasks: number`
- `sessions: number`
- `documents: number`

### Date metadata

`dates` stores normalized date values with confidence metadata:

- `createdAt?: { value, confidence, source, reason }`
- `updatedAt?: { value, confidence, source, reason }`
- `completedAt?: { value, confidence, source, reason }`
- `lastActivityAt?: { value, confidence, source, reason }`

`timeline[]` stores human-readable lifecycle events derived from these date values.

Date sources are merged and ranked per field:

- `createdAt`:
  - frontmatter `created*` (`high`)
  - git first commit touching file (`high`)
  - filesystem birthtime (`medium`)
  - filesystem mtime fallback (`low`)
- `updatedAt`:
  - git latest commit touching file (`high`)
  - frontmatter `updated*` (`medium`)
  - filesystem mtime when file is dirty/untracked in working tree (`high`)
  - filesystem mtime fallback (`low`)
  - frontmatter created fallback (`low`)
- `completedAt`:
  - frontmatter `completed*` (`high`)
  - frontmatter `updated*` for completion-equivalent doc statuses (`medium`)
  - filesystem mtime fallback for completion-equivalent statuses (`low`)

Notes:

- When git metadata is unavailable (non-git project or command failure), parser behavior falls back to frontmatter/filesystem sources.
- `lastActivityAt` is computed as the latest of `updatedAt` and `completedAt`.

## 2. Classification

## 2.1 `rootKind`

- `project_plans`
- `progress`
- `document` (fallback/legacy)

## 2.2 `docSubtype`

Examples:

- `implementation_plan`
- `phase_plan`
- `prd`
- `report`
- `spec`
- `progress_phase`
- `progress_all_phases`
- `progress_quick_feature`
- `progress_other`

## 3. Database Schema

## 3.1 `documents` (key columns)

Identity/classification:

- `id`
- `project_id`
- `file_path`
- `canonical_path`
- `root_kind`
- `doc_subtype`
- `doc_type`
- `category`

Search/filter keys:

- `status`
- `status_normalized`
- `feature_slug_hint`
- `feature_slug_canonical`
- `prd_ref`
- `phase_token`
- `phase_number`

Progress metrics:

- `overall_progress`
- `total_tasks`
- `completed_tasks`
- `in_progress_tasks`
- `blocked_tasks`

Fidelity payloads:

- `frontmatter_json`
- `metadata_json`
- `content`

File convenience columns:

- `file_name`
- `file_stem`
- `file_dir`
- `has_frontmatter`
- `frontmatter_type`

## 3.2 `document_refs`

Purpose: normalized refs extracted from frontmatter/metadata for linking and search.

Columns:

- `document_id`
- `project_id`
- `ref_kind`
- `ref_value`
- `ref_value_norm`
- `source_field`

Constraints/indexes:

- Unique: `(document_id, ref_kind, ref_value_norm, source_field)`
- Query index: `(project_id, ref_kind, ref_value_norm)`

## 4. API Contracts

## 4.1 `GET /api/documents`

Paginated response:

```ts
PaginatedResponse<PlanDocument>
```

Query params:

- `q?: string`
- `doc_subtype?: string`
- `root_kind?: string`
- `doc_type?: string`
- `category?: string`
- `status?: string`
- `feature?: string`
- `prd?: string`
- `phase?: string`
- `include_progress?: boolean`
- `offset?: number`
- `limit?: number`

## 4.2 `GET /api/documents/catalog`

Facet payload (DB-derived):

- `total`
- `root_kind`
- `doc_subtype`
- `doc_type`
- `category`
- `status`
- `feature`
- `phase`
- `has_frontmatter`

## 4.3 `GET /api/documents/{doc_id}`

Returns full `PlanDocument` with `content`.

Legacy compatibility:

- Supports canonical path lookup fallback.
- Supports legacy ID fallback heuristics for old deep links.

## 4.4 `GET /api/documents/{doc_id}/links`

Returns resolved linked entities:

- `features[]`
- `tasks[]`
- `sessions[]`
- `documents[]`

## 5. Sync Behavior

On full sync:

1. sessions sync
2. documents sync from plans + progress roots
3. task sync from progress frontmatter
4. feature derivation
5. link rebuild
6. analytics snapshot

Date extraction during full sync:

- Git commit history is loaded in one batched pass for docs/progress roots.
- Dirty/untracked file status is loaded separately so in-flight edits can surface as high-confidence `updatedAt`.
- Parsed date values are persisted to `documents` and used by downstream feature derivation.

On changed progress markdown:

- document sync runs for changed file
- task sync runs for changed file
- feature/link rebuild runs for affected project context

Date extraction during changed-file sync:

- Git commit history is loaded once for docs/progress scope per batch.
- Changed markdown paths are treated as dirty overrides to avoid missing fresh local edits.

## 6. Link Strategy Rules

## 6.1 Document -> Feature

Precedence:

1. explicit refs (`linkedFeatures`, feature refs, PRD refs)
2. path-derived feature hint
3. referenced-document inheritance

## 6.2 Document -> Document

- path-based refs are resolved against canonical document paths.

## 6.3 Document -> Task

- progress doc source path matches task source file.

## 6.4 Document -> Session

- explicit session refs
- plus task session refs when available

## 7. UI Behavior

`/plans`:

- Scope tabs: `Plans`, `PRDs`, `Reports`, `Progress`, `All`
- Facet filters: subtype/type/status/category/feature/prd/phase/frontmatter
- Search includes typed metadata and normalized refs

Document modal:

- subtype-aware metadata blocks
- progress metrics for progress-classified docs
- linked entities from `/api/documents/{id}/links`

## 8. Backward Compatibility

- Existing `frontmatter_json` remains authoritative raw source.
- Normalized typed fields are derived and indexed.
- Feature-linked docs continue to resolve via canonical document records.

## 9. Non-goals (this pass)

- No standalone RequestLog entity/table.
- Request IDs are indexed only as document refs and metadata values.
