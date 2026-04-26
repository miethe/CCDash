---
type: worknotes
doc_type: worknotes
prd: feature-surface-data-loading-redesign-v1
phase: 0
task: P0-002
created: 2026-04-23
---

# Filter / Sort / Search Query Matrix

## 1. Summary

This document enumerates every query control exposed by the current feature UI
surfaces (primarily `ProjectBoard.tsx` and `PlanningHomePage.tsx`) and proposes
a backend query parameter contract for `GET /api/features` that will replace
today's wholesale in-memory filtering. The analysis is based on:

- `components/ProjectBoard.tsx` — `filteredFeatures` useMemo (lines 4512–4574),
  filter state declarations (lines 4476–4499)
- `backend/routers/features.py` — `list_features` route (line 799)
- `backend/routers/_client_v1_features.py` — `list_features_v1` handler
- `backend/routers/client_v1.py` — `/api/v1/features` route definition
- `backend/db/repositories/features.py` and `postgres/features.py` —
  `list_paginated` / `count` method signatures
- `services/apiClient.ts` — `getFeatures()` call (line 189: hardcoded
  `offset=0&limit=5000` — no filter params passed today)

---

## 2. Table A — UI Control Inventory

| # | Control | Where used (surface) | Current source (frontend filter / backend param / memoized?) | Data type | Multi-select? | Notes |
|---|---------|----------------------|--------------------------------------------------------------|-----------|---------------|-------|
| 1 | Text search (name, id, tags) | ProjectBoard — board + list view | Frontend in-memory: `filteredFeatures` useMemo over `f.name`, `f.id`, `f.tags[]`; backend `q=` param exists on `v1/features` but is NOT called by `apiClient.getFeatures()` | string | N | Backend param `q` only covers name+id; tags not indexed server-side |
| 2 | Status filter dropdown | ProjectBoard | Frontend in-memory: `getFeatureBoardStage(f) === statusFilter`; backend `status[]=` param on v1 route is post-pagination in-memory filter inside `list_features_v1` (lines 149–154 of `_client_v1_features.py`) | enum string | N (single select, 'all' sentinel) | "deferred" maps to `hasDeferredCaveat()` not `feature.status === 'deferred'` — see deferred filter below |
| 3 | Deferred caveat filter | ProjectBoard | Frontend in-memory: `hasDeferredCaveat(f)` — derived from `feature.status !== 'done'` AND `feature.deferredTasks > 0` (or summed phases) | boolean / derived | N | Not a raw `status` value; requires `deferredTasks` field on the DTO |
| 4 | Category filter dropdown | ProjectBoard | Frontend in-memory: `f.category === categoryFilter`; backend `category=` param on v1 route is post-pagination in-memory filter (lines 156–158 of `_client_v1_features.py`) | string | N | Category values derived client-side from full feature list |
| 5 | plannedAt from/to date range | ProjectBoard | Frontend in-memory: `inDateRange(getFeatureDateValue(f, 'plannedAt').value, from, to)` | ISO date string (YYYY-MM-DD) | N (pair) | `getFeatureDateValue` reads `feature.plannedAt` scalar; `feature.dates.plannedAt` object as fallback |
| 6 | startedAt from/to date range | ProjectBoard | Frontend in-memory: `inDateRange(getFeatureDateValue(f, 'startedAt').value, from, to)` | ISO date string | N (pair) | |
| 7 | completedAt from/to date range | ProjectBoard | Frontend in-memory: `inDateRange(getFeatureDateValue(f, 'completedAt').value, from, to)` | ISO date string | N (pair) | Only active when at least one bound is set |
| 8 | updatedAt from/to date range | ProjectBoard | Frontend in-memory: `inDateRange(getFeatureDateValue(f, 'updatedAt').value, from, to)` | ISO date string | N (pair) | Maps to `feature.updatedAt` scalar, no `dates.updatedAt` fallback in current helper |
| 9 | Sort: by date (default) | ProjectBoard | Frontend in-memory: descending `updatedAt` epoch via `getFeatureDateValue(f, 'updatedAt')` | enum ('date') | N | Default sort; applied AFTER client-side filtering |
| 10 | Sort: by progress | ProjectBoard | Frontend in-memory: `getFeatureCompletedCount(f) / f.totalTasks` descending | enum ('progress') | N | `getFeatureCompletedCount` adds deferred to completed; not a raw field |
| 11 | Sort: by task count | ProjectBoard | Frontend in-memory: `f.totalTasks` descending | enum ('tasks') | N | Maps directly to `total_tasks` column |
| 12 | Planning signal / bucket filter | PlanningHomePage | Frontend in-memory: `featureMatchesBucket(item, activeBucket)` and `featureMatchesSignal(item, activeSignal)` over `FeatureSummaryItem[]` | enum string (PlanningStatusBucket / PlanningSignal) | N (single active) | Applied on `FeatureSummaryItem`, not `Feature`; runs over planning query response, not feature list |
| 13 | Phase status filter (modal-local) | ProjectBoardFeatureModal — Phases tab | Local component state; not a feature-list filter | enum string | N | Detail-level; scoped to single feature modal |
| 14 | Task status filter (modal-local) | ProjectBoardFeatureModal — Phases tab | Local component state; not a feature-list filter | enum string | N | Detail-level; scoped to single feature modal |

**Total UI controls inventoried: 14**
(Controls 13–14 are modal-local and not candidates for the list query contract.)

---

## 3. Table B — Proposed Query Parameter Contract for `GET /api/features`

This contract targets the app-shell feature list endpoint (`/api/features` served
by `backend/routers/features.py`) and the CLI endpoint (`/api/v1/features`).
Both must be brought to parity. Parameters marked **Phase 1** are backed by
indexed columns already in the schema. Parameters marked **Phase 2** require
JSON extraction or new indexes.

| Query param | Type | Operator(s) | Default | Maps to DB field / logic | Notes / precision |
|-------------|------|-------------|---------|--------------------------|-------------------|
| `q` | string | `ILIKE %q%` (substring) | `""` (no filter) | `features.name`, `features.id` | Already in `list_paginated`; extend to tags in Phase 2. Minimum length: 2 chars. Case-insensitive. |
| `status` | string[] (repeatable) | `IN` | `[]` (no filter) | `features.status` | Allowed values: `backlog`, `in-progress`, `review`, `done`, `deferred`, `draft`, `completed`. `deferred` maps to the DB `status` value, NOT `hasDeferredCaveat`. See deferred note. Phase 1. |
| `has_deferred` | boolean | `eq` | `false` (no filter) | `features.data_json->>'deferredTasks' > 0` or phase sum | Replaces `hasDeferredCaveat()` frontend logic. Requires JSON extraction or a new `deferred_tasks` indexed column. Phase 2. |
| `category` | string | `eq` (case-insensitive) | `""` (no filter) | `features.category` | Already in `list_paginated` as in-memory; move to SQL WHERE. Phase 1. |
| `tags` | string[] (repeatable) | `contains any` (OR semantics) | `[]` (no filter) | `features.data_json` JSON array field | No column today; requires JSON extraction or a `feature_tags` junction table. Phase 2. |
| `planned_from` | ISO 8601 date | `gte` | `""` (no filter) | `features.data_json->>'plannedAt'` or a new `planned_at` column | Phase 2 unless a `planned_at` column is added in Phase 1 migration. |
| `planned_to` | ISO 8601 date | `lte` | `""` (no filter) | same | Phase 2 |
| `started_from` | ISO 8601 date | `gte` | `""` (no filter) | `features.data_json->>'startedAt'` | Phase 2 |
| `started_to` | ISO 8601 date | `lte` | `""` (no filter) | same | Phase 2 |
| `completed_from` | ISO 8601 date | `gte` | `""` (no filter) | `features.completed_at` (already indexed column) | Phase 1 — column exists. |
| `completed_to` | ISO 8601 date | `lte` | `""` (no filter) | `features.completed_at` | Phase 1. |
| `updated_from` | ISO 8601 date | `gte` | `""` (no filter) | `features.updated_at` (already indexed column) | Phase 1 — column exists. |
| `updated_to` | ISO 8601 date | `lte` | `""` (no filter) | `features.updated_at` | Phase 1. |
| `sort_by` | enum: `updated_at` \| `completed_at` \| `created_at` \| `name` \| `total_tasks` \| `progress` | `eq` | `updated_at` | column or derived expression | `progress` = `completed_tasks / total_tasks` — requires CASE expression. Phase 1 for column sorts; Phase 2 for progress sort (adds CASE). |
| `sort_order` | enum: `asc` \| `desc` | `eq` | `desc` | ORDER BY direction | |
| `offset` | integer ≥ 0 | `eq` | `0` | pagination OFFSET | |
| `limit` | integer 1–200 | `eq` | `50` (board); `200` (CLI) | pagination LIMIT | Current CLI default 200; current app-shell call uses limit=5000 (must be removed). Hard cap: 200. |
| `project_id` | string | `eq` | active project | `features.project_id` | Already in all queries. Only relevant for multi-project overrides. |

**Total proposed query params: 17**

---

## 4. Sort / Total / Search / Pagination / Grouping Semantics

### 4.1 Default Sort Order

- **Default**: `sort_by=updated_at`, `sort_order=desc`.
- **Allowed sort keys**: `updated_at`, `completed_at`, `created_at`, `name`,
  `total_tasks`, `progress`.
- Current backend default in `list_paginated` is `ORDER BY name` — this is wrong
  for the UI which defaults to most-recently-updated first. The sort must be
  moved server-side and the `ORDER BY name` default overridden.

### 4.2 Total Semantics

**Current behavior**: `total` returned by `list_features` / `list_features_v1`
reflects the pre-filter row count with only keyword (`q`) applied at the DB
layer. Status and category filters are applied in-memory after the paginated DB
fetch, so the returned `total` does NOT account for those filters. This is a
correctness bug: `has_more` can be incorrect when status or category filters
reduce the result set.

**Target behavior**: `total` MUST reflect the post-filter, pre-pagination count
(i.e., count of rows matching all WHERE predicates). This allows clients to
compute `has_more` and page counts correctly. `total` is NOT affected by
pagination (OFFSET/LIMIT). It is NOT affected by search highlighting or
in-memory transformations.

### 4.3 Search Semantics

- **Fields covered**: `name`, `id`. Tags (`data_json` array) are not yet
  indexed; adding tags search is a Phase 2 concern. The v1 CLI `q` param
  currently covers only `name` and `id` (ILIKE).
- **Case sensitivity**: case-insensitive (SQLite: LOWER() LIKE; PostgreSQL:
  ILIKE).
- **Match mode**: substring (`%q%`). No prefix-only or token-split mode at this
  stage.
- **Minimum length**: 2 characters (to avoid full-table scans with single-char
  queries). The CLI already enforces `min_length=2` on `q` for session search;
  apply the same guard to features.
- **Scope**: single search string covers all indexed fields simultaneously (OR
  semantics across fields).

### 4.4 Pagination Contract

- **Style**: offset-based (not cursor). Both SQLite and PostgreSQL implementations
  already use OFFSET/LIMIT.
- **Default page size**: 50 for the app-shell board load; 200 for CLI. Hard cap: 200.
- **Current bug**: `apiClient.getFeatures()` calls `offset=0&limit=5000` with no
  filter params — this must be replaced by paginated board loading as part of
  Phase 2 (the board loading redesign).
- **`has_more`**: `(offset + len(items)) < total`. Already computed in
  `list_features_v1`.
- **`truncated`**: `len(items) >= limit AND has_more`. Already computed in
  `list_features_v1`.
- Cursor-based pagination is NOT required for Phase 1; offset is sufficient for
  the expected feature-list cardinality (hundreds, not millions).

### 4.5 Grouping Semantics

**Kanban column grouping** (`backlog` / `in-progress` / `review` / `done`) is
performed **client-side** by `getFeatureBoardStage(f)`, which maps `feature.status`
values to board lanes. This is NOT a server-side `group_by` parameter and should
remain client-side. The board renders four filtered slices of `filteredFeatures`
(lines 4970, 4987, 5004, 5021 of `ProjectBoard.tsx`).

**Completed / done grouping**: Features with `status === 'done'` or
`status === 'completed'` are placed in the "done" column. This is also
client-side lane assignment and does NOT need a server `group_by`.

**Planning status bucket / signal grouping** (PlanningHomePage): The
`featureMatchesBucket` and `featureMatchesSignal` functions operate over
`FeatureSummaryItem[]` returned by the planning summary endpoint — NOT the
feature list endpoint. These filters remain frontend-side for now because they
operate on the planning-specific lightweight DTO, not `Feature`. They are out of
scope for `GET /api/features` query contract.

---

## 5. Frontend-Only Filters That Must Move Server-Side

The following filters are currently computed entirely in-memory after loading the
full feature list (≤5000 features). They must move to the repository layer to
support true server-side pagination.

### 5.1 Status Filter (highest priority)

**Current**: `list_features_v1` receives `status[]` as a query param but applies
it in-memory via list comprehension AFTER `list_paginated` returns its page
(lines 149–154 of `_client_v1_features.py`). As a result, the paginated response
can be undersized and `total` is incorrect.

**Target**: SQL `WHERE status IN (...)` applied before OFFSET/LIMIT. The `status`
column is already indexed (`features.status`). This is a Phase 1 change.

**Deferred caveat sub-case**: The "deferred" board filter is NOT `status = 'deferred'`
— it is `hasDeferredCaveat(f)`, which requires `feature.deferredTasks > 0 AND
feature.status !== 'done'`. This derived predicate cannot map to the existing
`status` column and requires either a new `deferred_tasks` indexed column or a
JSON extraction predicate. Expose it as `has_deferred=true` and implement in
Phase 2 if the column is not added in Phase 1.

### 5.2 Category Filter (high priority)

**Current**: Same in-memory pattern as status — `category=` is received by
`list_features_v1` but applied after pagination (lines 156–158). `total` is wrong.

**Target**: SQL `WHERE LOWER(category) = LOWER(?)` before OFFSET/LIMIT. The
`category` column is already present in the schema. Phase 1.

### 5.3 Date Range Filters — updatedAt / completedAt (high priority)

**Current**: Entirely frontend in-memory. `apiClient.getFeatures()` never sends
date params. The board loads `offset=0&limit=5000`, then `filteredFeatures`
useMemo applies `inDateRange()` client-side.

**Target**: `updated_from` / `updated_to` map to `features.updated_at` (column
exists). `completed_from` / `completed_to` map to `features.completed_at`
(column exists). Both can be added to the SQL WHERE clause in Phase 1 without
schema changes.

`planned_from/to` and `started_from/to` require extracting `plannedAt` /
`startedAt` from `data_json` or adding new columns — Phase 2.

### 5.4 Sort Order (medium priority)

**Current**: All sorting is frontend in-memory after loading the full feature
list. The DB always returns `ORDER BY name`. The default board sort is
`updatedAt` descending.

**Target**: `sort_by` / `sort_order` params control `ORDER BY` in SQL.
`updated_at` and `name` and `total_tasks` map directly to columns and are
Phase 1. `progress` (`completed_tasks / total_tasks`) requires a CASE/CAST
expression — Phase 2.

### 5.5 Text Search — Tags Extension (low priority)

**Current**: `q` covers `name` and `id` at the DB layer but the frontend also
searches `f.tags[]` (a JSON array in `data_json`). The backend `q` param silently
misses tag matches.

**Target**: Extend `q` to search tags via JSON extraction or a `feature_tags`
junction table. Phase 2.

---

## 6. Open Questions

1. **`has_deferred` vs `status=deferred` ambiguity**: The board "deferred" filter
   option uses `hasDeferredCaveat()`, which is NOT equivalent to
   `feature.status === 'deferred'`. Should the API expose a distinct
   `has_deferred=true` boolean param, or should the frontend be changed to use
   `status=deferred` (which would alter visible results)? This needs a product
   decision before Phase 1 implementation.

2. **`total` reflects which scope?** The current `total` in `list_features`
   (`features.py` line 902) is fetched via `repo.count(project_id)` BEFORE
   in-memory status/category filtering, so it represents the unfiltered count.
   After filters move server-side, `total` will represent post-filter
   pre-pagination count. Any client that currently uses `total` for progress
   indicators must be updated.

3. **`limit=5000` removal timing**: `apiClient.getFeatures()` hardcodes
   `limit=5000`. This call is the data source for the board's `apiFeatures`.
   Replacing it with paginated loads requires the board to support infinite
   scroll or explicit page navigation — that is Phase 2 scope. For Phase 1,
   the query contract can be defined without breaking the existing call.

4. **`effectiveStatus` / `planningStatus.rawStatus` filtering**: The planning
   home page uses `effectiveStatus` and `rawStatus` from `FeatureSummaryItem`
   (the planning summary DTO), which differ from the base `Feature.status`.
   Should `GET /api/features` also accept `effective_status` as a filter, or
   is this exclusively a planning-query concern?

5. **Tags indexing strategy**: Adding tags full-text search requires either a
   JSON path index (PostgreSQL `GIN`) or a `feature_tags` junction table. The
   choice affects migration scope for Phase 2.

6. **Sort by `progress` precision**: `progress = completed_tasks / total_tasks`.
   Features with `totalTasks = 0` should sort as `0`. The current `getFeatureCompletedCount`
   helper also counts deferred tasks as completed — should the server-side
   `progress` sort use raw `completed_tasks` or the deferred-inclusive count?
   If the latter, a new `effective_completed_tasks` column is needed.

7. **`planning signal / bucket` filter scope**: `featureMatchesBucket` and
   `featureMatchesSignal` operate on `FeatureSummaryItem` from the planning
   endpoint, not on the feature list endpoint. Should these signals be
   backported as filters on `GET /api/features` for consistency, or remain
   planning-endpoint-only?

8. **Multi-select status**: The v1 route already accepts `status` as a repeatable
   query param (`list[str]`). The main `GET /api/features` route currently only
   accepts a scalar. The contract should unify both to accept `status[]` (repeated
   param, OR semantics).

9. **`project_id` override**: Both the app-shell and CLI endpoints resolve
   `project_id` from the active project context. An explicit `project_id`
   override query param is available in the v1 route but not in the main route.
   Should the main route also support it?
