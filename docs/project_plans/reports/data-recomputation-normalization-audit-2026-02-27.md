# Data Recalculation and Normalization Audit

Date: 2026-02-27  
Project: CCDash  
Scope: Backend persistence, API read paths, analytics aggregation, and cross-entity linking

## Confidence Check

- Duplicate check: Pass. The codebase does not already contain a consolidated "derived/session summary" persistence layer; the same derivations are implemented repeatedly in API handlers.
- Architecture compliance: Pass. Findings align with current Router -> Repository -> SyncEngine design.
- Root-cause clarity: Pass. Recalculation is caused primarily by JSON-as-text storage and endpoint-level hydration logic.
- Official docs / OSS references: Not required for this audit-only deliverable (no new external library/API adoption proposed here).

## Executive Summary

The codebase has a strong ingestion pipeline and a meaningful link graph (`entity_links`, `document_refs`, `telemetry_events`), but many high-traffic read paths still recompute structured data from raw logs/JSON blobs on every request. The biggest performance and maintainability costs come from:

1. Endpoint-level re-hydration from `session_logs` and JSON text fields.
2. N+1 repository access patterns for cross-entity views.
3. Analytics endpoints that re-aggregate raw sessions/logs despite a telemetry fact table already existing.

The dominant remediation theme is: persist derived fields once during sync, then serve set-based DB queries.

## Findings

### 1) Session list/detail APIs recompute badges and metadata from raw logs on every request

Evidence:
- `backend/routers/api.py:283-375` (`/api/sessions`) fetches logs per session, parses metadata JSON, classifies commands, derives model identity, and builds badges.
- `backend/routers/api.py:446-649` (`/api/sessions/{id}`) repeats similar reconstruction for a single session.
- `backend/session_badges.py:101-189` derives `modelsUsed`, `agentsUsed`, `skillsUsed`, `toolSummary` by scanning logs.
- `backend/session_mappings.py:454-477` computes session key metadata from command events each request.

Impact:
- N+1 query behavior and repeated `json.loads` across large log arrays.
- Same derivation logic repeated across multiple endpoints.
- Derived values are not queryable/indexable in DB.

Recommendation:
- Add a persisted `session_derived` payload (or normalized columns/tables) populated during sync:
  - `title`, `session_metadata_json`, `models_used_json`, `agents_used_json`, `skills_used_json`, `tool_summary_json`.
- Read endpoints should prefer persisted derived data and only fall back to runtime derivation when missing.

### 2) Feature -> linked sessions endpoint performs heavy per-session reconstruction

Evidence:
- `backend/routers/features.py:887-1342` builds feature-linked session payloads.
- `backend/routers/features.py:947` calls `get_logs` per session.
- `backend/routers/features.py:1041-1156` repeatedly parses log metadata and rematches tasks/phases.
- `backend/routers/features.py:1294-1338` expands root threads and builds inherited items, increasing total session/log scans.

Impact:
- Large runtime cost for features with many linked sessions/subthreads.
- Task/phase inference is repeated despite similar signals being generated during sync.

Recommendation:
- Persist session-task-phase associations and normalized command metadata during sync (separate relation table).
- Persist a compact precomputed "feature session card" JSON in link metadata or a dedicated summary table.
- Use repository batch loaders for session rows/log-derived summaries by `IN (...)`.

### 3) Analytics endpoints re-aggregate from raw sessions/logs and trigger N+1 queries

Evidence:
- `backend/routers/analytics.py:1479-1534` (`/breakdown`) loads up to 2000 sessions and then:
  - `get_tool_usage` per session (`:1495`)
  - `get_logs` per session (`:1501`)
  - `get_links_for` per session (`:1520`)
- `backend/routers/analytics.py:1551-1592` (`/correlation`) loads sessions, links per session, and feature row per link (`:1575`).
- `backend/routers/analytics.py:1389-1411` (`/series` for session tokens) scans/parses session logs on demand.

Impact:
- Latency grows linearly with session count and link density.
- Duplicates capabilities already represented in `telemetry_events`.

Recommendation:
- Rewrite breakdown/correlation endpoints to use set-based SQL over `telemetry_events` + `entity_links` with grouped aggregations.
- Add rollup tables/materialized views for common dimensions (model family, tool, feature, session type).
- Reserve raw-log scans for drill-down endpoints only.

### 4) Document link endpoint does table-wide task scan and per-entity lookups

Evidence:
- `backend/routers/api.py:1024-1036` (`/documents/{id}/links`) calls `task_repo.list_all(project.id)` then filters in Python.
- Same handler does per-id fetch loops for features/sessions/documents (`:1012-1063`).

Impact:
- Unnecessary full table reads.
- Repeated repository roundtrips for linked entity hydration.

Recommendation:
- Add repository methods:
  - `tasks.list_by_ids(project_id, ids)`
  - `features.list_by_ids(ids)`
  - `sessions.list_by_ids(ids)`
  - `documents.list_by_ids(ids)`
- Optionally replace handler with one SQL join pipeline keyed by `entity_links`.

### 5) JSON text blobs are used for frequently queried structures

Evidence:
- Schema stores many frequently-used arrays/objects as text:
  - `sessions.platform_versions_json`, `sessions.git_commit_hashes_json`, `sessions.dates_json`, `sessions.timeline_json` (`backend/db/sqlite_migrations.py:94-116`)
  - `features.data_json` (`:290`)
  - `tasks.data_json` (`:271`)
  - `documents.frontmatter_json`, `documents.metadata_json` (`:220,225`)
- Runtime parsing in repositories/routes:
  - Platform facets parse versions row-by-row (`backend/db/repositories/sessions.py:328-375`, Postgres equivalent `backend/db/repositories/postgres/sessions.py:350-403`)
  - Task/model/document mapping via `_safe_json` in routers (`backend/routers/api.py:744-875,1117-1135`, `backend/routers/features.py:456-573,788-883`)

Impact:
- High parse overhead.
- Limited indexability and slower filtering.
- More duplication of map/transform code.

Recommendation:
- Normalize hot-path structures:
  - `session_platform_versions(session_id, version)`
  - `session_model_identity(session_id, provider, family, version, canonical, display_name)` or direct columns on `sessions`
  - `task_tags`, `task_related_files`
  - `feature_tags`, `feature_related_features`
- Keep JSON only for cold/opaque payloads.

### 6) Model identity parsing is repeated across multiple endpoints

Evidence:
- Model derivation utility: `backend/model_identity.py:29-113`.
- Used in sessions list/detail/facets and analytics repeatedly (`backend/routers/api.py:312,401,517`; `backend/routers/features.py:1031`; `backend/routers/analytics.py` throughout artifact payload build).

Impact:
- Redundant CPU work and inconsistent filtering strategy (string token matching on raw model).

Recommendation:
- Persist canonical model dimensions at ingestion time.
- Add indexes for provider/family/version filters.
- Remove broad `LIKE` filters where structured columns are available.

### 7) Codebase explorer recomputes file-feature involvement from event/link data on cache miss

Evidence:
- Snapshot rebuild and event folding: `backend/services/codebase_explorer.py:633-734`.
- Feature involvement scoring on each snapshot build: `:917-988`.

Impact:
- Potentially expensive cache-miss path for large projects.

Recommendation:
- Optional: maintain a `file_feature_rollup` table updated during sync/rebuild operations.
- Keep current in-memory cache as a short-term mitigation.

## Prioritized Recommendations

### Priority A (highest ROI, low schema risk)

1. Replace N+1 patterns with batch repository methods (`list_by_ids`, set-based link hydration).  
2. Move analytics breakdown/correlation to SQL aggregations on telemetry/link tables.  
3. Persist session-derived card metadata (`title`, badges, mapped session metadata) at sync time.

### Priority B (schema improvements)

1. Add normalized model identity fields/columns and indexes.  
2. Split hottest JSON arrays into relation tables (`session_platform_versions`, task/feature tag tables).  
3. Add persisted session-command/session-phase relation table for feature/session endpoints.

### Priority C (advanced optimization)

1. Rollup/materialized views for frequently requested analytics dimensions.  
2. Optional `file_feature_rollup` for codebase explorer cache misses.

## Suggested Implementation Order

1. Batch loading + N+1 removal in routers (`api.py`, `features.py`, `analytics.py`).  
2. Session-derived snapshot persistence in sync engine and migration/backfill.  
3. Normalized model + platform version schema changes and backfill.  
4. Analytics SQL rollups and endpoint rewrites.  
5. Optional explorer rollup table.

## Expected Outcome

- Lower p95 latency on session/feature/analytics endpoints.
- Reduced CPU from repetitive JSON parsing and log rescans.
- More stable and testable data contracts (less endpoint-specific reconstruction).
- Better filter/query fidelity by using normalized, indexed entity attributes.

