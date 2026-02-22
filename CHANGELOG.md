# Changelog

## 2026-02-22

### Added

- Track A analytics API surface:
  - `GET /api/analytics/overview`
  - `GET /api/analytics/series`
  - `GET /api/analytics/breakdown`
  - `GET /api/analytics/correlation`
  - `POST /api/analytics/alerts`
  - `PATCH /api/analytics/alerts/{id}`
  - `DELETE /api/analytics/alerts/{id}`
- Token timeline series support sourced from persisted session log usage metadata.
- New documentation:
  - `docs/telemetry-analytics-track-a-implementation-reference-2026-02-22.md`
- New tests:
  - `backend/tests/test_tasks_repository.py`
  - `backend/tests/test_analytics_router.py`

### Changed

- Task analytics correctness:
  - completion metrics now count `done`, `deferred`, and `completed` for compatibility.
- Session telemetry persistence:
  - session `dates`, `timeline`, and `impactHistory` are now persisted and rehydrated.
- Tool usage telemetry:
  - `session_tool_usage.total_ms` now populated from tool use/result timing.
- Analytics capture:
  - writes `analytics_entries.metadata_json` context and `analytics_entity_links` associations.
- Dashboard analytics:
  - KPI/model/series cards now sourced from backend analytics endpoints (removed hardcoded display values for core KPIs).
- Session Inspector analytics:
  - token timeline now uses backend series endpoint instead of simulated data.
- Settings alerts:
  - alerts tab now uses persisted backend CRUD operations.

### Migrations

- SQLite schema version bumped to `8`.
- Postgres schema version bumped to `6`.
- Added `sessions` columns:
  - `dates_json`
  - `timeline_json`
  - `impact_history_json`
- Added/ensured `session_tool_usage.total_ms`.

## 2026-02-19

### Added

- Unified document metadata system for plan and progress markdown.
- Typed `Document` fields (subtype/root kind/status normalization/phase/progress/task metrics/feature hints).
- Normalized `document_refs` storage for searchable/linkable extracted references.
- New APIs:
  - `GET /api/documents` (paginated/filterable)
  - `GET /api/documents/catalog` (facet counts)
  - `GET /api/documents/{doc_id}/links` (linked features/tasks/sessions/docs)
- Documents UI upgrades:
  - scope tabs (`Plans`, `PRDs`, `Reports`, `Progress`, `All`)
  - faceted filters and typed-metadata search
  - subtype-aware document modal with normalized links panel

### Changed

- Progress markdown is now synced as first-class `documents` (not only task source).
- Canonical path identity standardized to project-relative slash-normalized paths.
- Document-to-entity mapping strategy now prioritizes explicit refs, then path hints, then inherited doc refs.
- Feature doc resolution in board/modal now supports canonical path matching.
- Frontend document loading now pages API calls to avoid validation failures on large projects.
- `npm run dev` now validates backend health before starting frontend, and exits fast if backend startup fails.
- Added explicit startup scripts for backend-only dev/prod-style runs (`dev:backend`, `start:backend`) and frontend preview (`start:frontend`).
- Added deferred lifecycle support for tasks/phases/features:
  - New `deferred` status option across status controls.
  - Deferred counts contribute to completion and progress calculations.
  - Features move to/remain in `Done` stage when all tasks are terminal (`done` or `deferred`) and now show a deferred caveat indicator.
  - Feature/phase/task filters now include deferred visibility.
- Added completion-equivalence reconciliation across linked feature docs:
  - Feature status now resolves to done when any equivalent completion collection is complete (`PRD`, `Plan`/phase plans, or all progress docs).
  - Inferred completion writes through `status: inferred_complete` to linked PRD/Plan docs that are not already completion-equivalent.
- Document filter facets now normalize status/subtype variants into canonical values.
- Document and feature date derivation now uses normalized source precedence with git-backed file history:
  - batched `git log` extraction for `createdAt`/`updatedAt`
  - dirty/untracked worktree detection for in-progress local edits
  - parser fallback to frontmatter/filesystem when git data is unavailable
- Link rebuild execution now uses cached-state gating:
  - startup full sync skips relink when synced entities are unchanged and logic version matches
  - full relink still runs on force sync, explicit rebuild endpoint, changed-file link-impact, or logic-version bump (`CCDASH_LINKING_LOGIC_VERSION`)

### Fixed

- `/plans` load failures from oversized `limit` requests and slow N+1 link lookups in list endpoint.
- Migration ordering issue for typed `documents` index creation on legacy DBs.
- Reduced frontend false-start state where UI loaded while backend was unavailable (`ECONNREFUSED` proxy errors).

### Docs

- Added `/docs/setup-user-guide.md` with setup, startup, deployment-style runbook, and troubleshooting for `/api` connectivity errors.
- Updated document entity/frontmatter specs with completion-equivalence and canonical filter-value behavior.
- Updated sync/document developer docs with git date extraction strategy and one-time backfill workflow.
- Documented linking rebuild gate and `CCDASH_LINKING_LOGIC_VERSION` usage for deployment-safe relink triggers.
