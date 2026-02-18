# Document Linking Refactor Plan (2026-02-18)

## Objective
Make documents the authoritative source for feature/session linkage by:
- indexing frontmatter + filepath metadata across doc/progress files,
- resolving related/prd references as strong linkage evidence,
- reducing false-positive feature-session mappings from generic filenames.

## Current Gaps (Validated)
- Generic progress basenames (`phase-x-progress`) were used as feature aliases during session matching.
- Key-command sessions at moderate confidence were promoted to "Core Focus Sessions".
- Not all frontmatter relationships were consumed for document -> feature links.
- Feature linked docs were not consistently enriched with progress/report/supporting documents and metadata.

## Implemented In This Refactor
1. Shared linking utility module
- Added `/Users/miethe/dev/homelab/development/CCDash/backend/document_linking.py`.
- Centralized:
  - path normalization,
  - canonical slug/version handling,
  - generic phase filename filtering,
  - doc type/category classification,
  - frontmatter reference extraction (`related`, `prd`, linked session/feature refs).

2. Rich document metadata ingestion
- Extended document models in `/Users/miethe/dev/homelab/development/CCDash/backend/models.py`.
- `DocumentFrontmatter` now stores normalized refs, field keys, and raw frontmatter.
- `PlanDocument` now stores `docType`, `category`, `pathSegments`, `featureCandidates`.
- Updated parser `/Users/miethe/dev/homelab/development/CCDash/backend/parsers/documents.py` to populate these fields.

3. Feature document linking enhancement
- Refactored `/Users/miethe/dev/homelab/development/CCDash/backend/parsers/features.py` to:
  - use project-relative doc paths,
  - attach metadata on linked docs (slug/category/frontmatter keys/prd/related refs),
  - include progress docs in linked docs,
  - augment features with auxiliary docs (reports/specs/related docs) using slug + `related` + `prd` evidence.

4. Session-feature mapping hardening
- Refactored `/Users/miethe/dev/homelab/development/CCDash/backend/db/sync_engine.py` to:
  - stop using generic phase basenames as aliases,
  - derive aliases from feature-relevant path tokens (including parent feature directory),
  - consume linked doc `relatedRefs`/`prdRef` metadata,
  - improve command-path matching with parent-dir alias checks,
  - store a project-level `document_catalog` index in `app_metadata` for frontmatter field/type visibility.

5. Primary/Core session classification tightened
- Updated:
  - `/Users/miethe/dev/homelab/development/CCDash/backend/routers/features.py`
  - `/Users/miethe/dev/homelab/development/CCDash/backend/routers/api.py`
- Removed low-confidence key-command auto-promotion.

## Comprehensive Frontmatter Indexing Strategy
The `document_catalog` metadata snapshot (stored in `app_metadata` under key `document_catalog`) now captures:
- indexed markdown file count,
- file type distribution,
- frontmatter field frequency map,
- per-file metadata sample (path, type, keys, related/prd refs, derived feature refs).

This provides a baseline for identifying missing/underused fields and iterating parser coverage.

## Follow-Up Phases
1. Phase A: Surface catalog in API/UI
- Add `/api/documents/catalog` endpoint.
- Add a Documents metadata panel (field frequency, uncovered docs, unresolved refs).

2. Phase B: Conclusive reference priority
- Explicitly prioritize `related`/`prd` refs over fuzzy slug/path inference in confidence scoring.
- Add "conclusive" signal annotation in entity link metadata.

3. Phase C: Feature graph normalization
- Persist normalized feature aliases and doc relationships in first-class tables.
- Remove implicit inference duplication between parser and sync engine.

4. Phase D: Backfill and remediation tooling
- Add offline repair script to regenerate links and emit a before/after mismatch report.
- Add guardrails/tests for high-fanout anomalies (single session linked to many unrelated features).

## Testing Requirements
- Unit tests for document linking utilities.
- Regression tests for primary link threshold behavior.
- Sync-linking tests for progress parent-directory matching vs. generic filename suppression.
- Integration test: one session referencing feature A should not map to unrelated feature B through `phase-x-progress` filenames.

## Success Criteria
- Erroneous cross-feature "Core Focus Session" links are eliminated.
- `related`/`prd` frontmatter references reliably connect docs/features/sessions.
- Feature linked docs include plans, PRDs, progress, and supporting docs with accurate metadata.
- Document catalog reflects active field usage and supports further refactor phases.
