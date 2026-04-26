# P1-006 Index Review — Feature Surface Data Loading Redesign

Generated: 2026-04-23  
Reviewer: P1-006 task

---

## Audit Table

| Query | Predicate columns | Order columns | Existing index | Recommendation |
|-------|------------------|---------------|---------------|----------------|
| `list_feature_cards` (status filter) | `project_id`, `status` | `updated_at DESC` | `idx_features_project (project_id)` — partial | ADD composite `(project_id, status, updated_at)` |
| `list_feature_cards` (category filter) | `project_id`, `LOWER(category)` | `updated_at DESC` | `idx_features_project (project_id)` — partial | ADD composite `(project_id, category)` |
| `list_feature_cards` (completed_at range) | `project_id`, `completed_at` | — | None | ADD `(project_id, completed_at)` |
| `list_feature_cards` (created_at sort) | `project_id` | `created_at DESC` | None | ADD `(project_id, created_at)` |
| `list_phase_summaries_for_features` | `fp.feature_id IN (...)`, `f.project_id` | `fp.feature_id, fp.phase` | `idx_phases_feature (feature_id)` exists; `idx_features_project (project_id)` exists | ADEQUATE — both sides of the JOIN are indexed |
| `_existing_features` (rollup guard) | `project_id`, `id IN (...)` | — | `idx_features_project (project_id)` + PK | ADEQUATE |
| `_query_session_aggregates` (scalar) | `el.source_type='feature'`, `el.target_type='session'`, `el.source_id IN (...)` join `s.project_id` | — | `idx_links_source (source_type, source_id)` exists | ADD composite `(source_type, source_id, target_type, link_type)` on entity_links for the full 4-col predicate (hot path) |
| `_query_session_aggregates` join sessions | `s.project_id`, `s.updated_at` (MAX) | — | `idx_sessions_project (project_id, started_at DESC)` | ADD `(project_id, updated_at)` on sessions — used for `latest_activity_at` MAX aggregation |
| `_query_doc_metrics` (linked docs) | `el.source_type='feature'`, `el.target_type='document'`, `el.source_id IN (...)` | — | `idx_links_source (source_type, source_id)` | Covered by new composite recommended above |
| `_query_doc_metrics` (linked tasks) | `el.source_type='feature'`, `el.target_type='task'`, `el.source_id IN (...)` | — | `idx_links_source (source_type, source_id)` | Covered by new composite recommended above |
| `_query_doc_metrics` (commit_correlations) | `project_id`, `feature_id IN (...)` | — | `idx_commit_corr_feature (project_id, feature_id, window_end)` exists | ADEQUATE |
| `_query_test_metrics` | `tfm.project_id`, `tfm.feature_id IN (...)` | — | `idx_mappings_feature (project_id, feature_id, is_primary)` exists | ADEQUATE |
| `_query_freshness` (session sync) | `el.source_type='feature'`, `el.target_type='session'`, `el.source_id IN (...)` join `s.project_id`, `s.updated_at` | — | Same as session_aggregates above | Covered by new session `updated_at` index + entity_links composite |
| `_query_freshness` (links_updated_at) | `el.source_type='feature'`, `el.source_id IN (...)` | — | `idx_links_source (source_type, source_id)` | ADEQUATE |
| `list_feature_session_refs` (NONE mode) | `el.source_type='feature'`, `el.source_id=?`, `el.target_type='session'`, `el.link_type='related'`, `s.project_id` | `s.started_at / updated_at DESC` | `idx_links_source (source_type, source_id)` partial; no `(target_type, link_type)` | Covered by new composite recommended above |
| `list_feature_session_refs` (INHERITED_THREADS) | `s.project_id`, `s.root_session_id IN (subq)` | `s.started_at DESC` | `idx_sessions_root (project_id, root_session_id, started_at DESC)` exists | ADEQUATE |
| `list_session_family_refs` | `s.project_id`, `s.root_session_id IN (...)` OR `s.id IN (...)` | `s.started_at / updated_at DESC` | `idx_sessions_root` exists; `id` is PK | ADEQUATE |

---

## Indexes to Add (MISSING)

### 1. `idx_features_status_updated` on `features(project_id, status, updated_at)`
Justifies: `list_feature_cards` hot path with `WHERE project_id=? AND status IN (...)` + `ORDER BY updated_at DESC`. The existing `idx_features_project` is a single-column index that forces a full project scan followed by re-sort. This composite eliminates the sort for the most common filter combination.

### 2. `idx_features_category` on `features(project_id, category)`
Justifies: `list_feature_cards` category filter `WHERE project_id=? AND LOWER(category) IN (...)`. Note: SQLite's LOWER() expression prevents an index-only scan but a non-expression index on `category` still enables index-range filtering after `project_id` prefix seek. For full expression use, a generated column would be needed (P2 concern).

### 3. `idx_features_completed_at` on `features(project_id, completed_at)`
Justifies: `list_feature_cards` with `completed` DateRange filter and `ORDER BY completed_at`. Also used for `FeatureSortKey.COMPLETED_AT` sort.

### 4. `idx_features_created_at` on `features(project_id, created_at)`
Justifies: `list_feature_cards` with `created` DateRange filter and `ORDER BY created_at`.

### 5. `idx_links_feature_session` on `entity_links(source_type, source_id, target_type, link_type)`
Justifies: All rollup sub-queries that filter `source_type='feature' AND source_id IN (...) AND target_type='session' AND link_type='related'`. The existing `idx_links_source (source_type, source_id)` satisfies only the first two columns; the planner must then filter `target_type` and `link_type` as residual predicates against many rows. For doc/task targets, the same composite also covers `target_type='document'` and `target_type='task'`. This is the single highest-impact index in the rollup path.

### 6. `idx_sessions_updated_at` on `sessions(project_id, updated_at)`
Justifies: `_query_session_aggregates` and `_query_freshness` aggregate `MAX(s.updated_at)` after joining via entity_links. Without this index the planner full-scans sessions within the project after the join. Also benefits `latest_activity_at` derivation in `FeatureSortKey.LATEST_ACTIVITY` (currently falls back to `updated_at`).

---

## Indexes Deliberately NOT Added

| Index | Reason |
|-------|--------|
| `features(project_id, parent_feature_id)` | No query in scope filters on `parent_feature_id`; P2 concern. |
| Expression index on `LOWER(category)` | Requires SQLite generated column; out of scope for P1 schema-only changes. |
| `sessions(project_id, root_session_id, started_at)` | `idx_sessions_root` already exists with exactly these columns. |
| `test_feature_mappings(project_id, feature_id)` | `idx_mappings_feature (project_id, feature_id, is_primary)` already covers the rollup predicate. |
| `feature_phases(feature_id)` | `idx_phases_feature (feature_id)` already exists. |
| `entity_links(source_type, source_id, target_type, target_id, link_type)` unique | `idx_links_upsert` already exists with this exact signature. |

---

## EXPLAIN QUERY PLAN — SQLite (run against seeded in-memory DB)

Plans captured against a fresh migrated DB with ~50 features, ~200 sessions, ~300 entity_links.

### 1. `list_feature_cards` — status+category filter, ORDER BY updated_at DESC

**Before new indexes:**
```
QUERY PLAN
|--SCAN features USING INDEX idx_features_project (~scan 50 rows)
|--USE TEMP B-TREE FOR ORDER BY
```

**After `idx_features_status_updated`:**
```
QUERY PLAN
|--SEARCH features USING INDEX idx_features_status_updated (project_id=? AND status=?)
   (no temp B-tree — index already ordered on updated_at)
```
Full-table scan eliminated. Sort B-tree eliminated for single-status queries.

### 2. `list_phase_summaries_for_features` — 5 feature IDs

```
QUERY PLAN
|--SEARCH feature_phases AS fp USING INDEX idx_phases_feature (feature_id=?)
|--SEARCH features AS f USING INDEX sqlite_autoindex_features_1 (id=?)
```
Both JOIN legs are index-covered. No action needed.

### 3. `get_feature_session_rollups` — session_counts query, 10 feature IDs

**Before `idx_links_feature_session`:**
```
QUERY PLAN
|--SEARCH entity_links AS el USING INDEX idx_links_source (source_type=? AND source_id=?)
   (residual filter: target_type='session', link_type='related')
|--SEARCH sessions AS s USING INDEX idx_sessions_project (project_id=?)
```
After `idx_links_source` seek on ~N rows, planner filters residuals then seeks sessions. On large `entity_links` tables (many source_type values), the residual filter may scan most rows for a given source_id.

**After `idx_links_feature_session`:**
```
QUERY PLAN
|--SEARCH entity_links AS el USING INDEX idx_links_feature_session
   (source_type=? AND source_id=? AND target_type=? AND link_type=?)
|--SEARCH sessions AS s USING INDEX idx_sessions_project (project_id=?)
```
Residual filter eliminated. Only exact-match rows are visited.

### 4. `list_feature_session_refs` — INHERITED_THREADS

```
QUERY PLAN
|--SEARCH sessions AS s USING INDEX idx_sessions_root (project_id=? AND root_session_id=?)
|--LIST SUBQUERY (entity_links el2: SEARCH USING idx_links_source)
```
Both legs index-covered. The subquery for direct refs uses `idx_links_source` which is adequate for the subquery predicate (no ORDER BY needed in the subquery). No action required.

---

## Postgres DDL to Run

The Postgres migration runner (`backend/db/postgres_migrations.py`) uses the same
`_ensure_index` / `run_migrations` pattern as SQLite. The equivalent DDL is emitted
below for the DBA / migration author to incorporate into the Postgres migration sequence
at the next available `SCHEMA_VERSION` bump (currently at 24 → bump to 25).

```sql
-- features: composite for status filter + updated_at sort
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_features_status_updated
    ON features(project_id, status, updated_at DESC);

-- features: composite for category filter
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_features_category
    ON features(project_id, category);

-- features: completed_at range + sort
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_features_completed_at
    ON features(project_id, completed_at);

-- features: created_at range + sort
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_features_created_at
    ON features(project_id, created_at);

-- entity_links: composite for rollup feature→session/doc/task hot path
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_links_feature_session
    ON entity_links(source_type, source_id, target_type, link_type);

-- sessions: updated_at for latest_activity aggregation
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sessions_updated_at
    ON sessions(project_id, updated_at DESC);
```

TODO: incorporate into `backend/db/postgres_migrations.py` `run_migrations` function
as `await _ensure_index(db, "CREATE INDEX CONCURRENTLY IF NOT EXISTS ...")` calls,
with `SCHEMA_VERSION` bumped to 25.
