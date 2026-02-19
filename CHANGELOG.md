# Changelog

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
- Added deferred lifecycle support for tasks/phases/features:
  - New `deferred` status option across status controls.
  - Deferred counts contribute to completion and progress calculations.
  - Features move to/remain in `Done` stage when all tasks are terminal (`done` or `deferred`) and now show a deferred caveat indicator.
  - Feature/phase/task filters now include deferred visibility.

### Fixed

- `/plans` load failures from oversized `limit` requests and slow N+1 link lookups in list endpoint.
- Migration ordering issue for typed `documents` index creation on legacy DBs.
