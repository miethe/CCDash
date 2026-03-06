# CCDash Document Schema Catalog

Last updated: 2026-03-06
Status: Canonical

This directory is the active source of truth for CCDash document frontmatter and document-to-feature mapping.

It replaces these superseded root-level specs, now archived under `docs/archive/superseded/document-specs/2026-03-05/`:

- `docs/document-frontmatter-improvement-spec-2026-02-19.md`
- `docs/document-frontmatter-current-implementation-spec-2026-02-19.md`
- `docs/document-frontmatter-lineage-v2-spec-2026-02-19.md`
- `docs/document-entity-spec.md`

## Files

- `base-envelope.schema.yaml`
  Shared frontmatter envelope and reusable field definitions.
- `prd.schema.yaml`
  Product requirements documents.
- `implementation-plan.schema.yaml`
  Top-level implementation plans.
- `phase-plan.schema.yaml`
  Per-phase implementation plan files.
- `progress.schema.yaml`
  Progress trackers under `.claude/progress/...`.
- `report.schema.yaml`
  Analysis, audit, and findings documents.
- `design-doc.schema.yaml`
  UX, design-system, wireframe, and interaction docs.
- `spec.schema.yaml`
  Technical, API, entity, and contract specs.
- `document-and-feature-mapping.md`
  UI display mapping, document card/modal mapping, feature bubble-up rules, and derived-field rules.

## Canonical document types

These are the target `doc_type` values going forward:

- `prd`
- `implementation_plan`
- `phase_plan`
- `progress`
- `report`
- `design_doc`
- `spec`
- `document`

Notes:

- `design_spec` is folded into `design_doc` as a subtype, not a separate doc type.
- Legacy values and aliases remain ingestible during migration, but new and updated documents should use the canonical values above.
- `doc_subtype` is where narrower classes belong: `roadmap`, `progress_phase`, `design_system`, `wireframe`, `api_spec`, `entity_spec`, `postmortem`, and similar.

## Shared conventions

- `schema_name` is always `ccdash_document`.
- `schema_version` is always `3`.
- `status` should use the canonical lifecycle set:
  - `pending`
  - `in_progress`
  - `review`
  - `completed`
  - `deferred`
  - `blocked`
  - `archived`
- `feature_slug` is the owning feature slug for PRDs, plans, and progress docs.
- `feature_family` is the versionless family slug.
- `linked_features` is now a structured relationship field. Legacy string arrays remain accepted during migration.
- `related_documents`, `linked_sessions`, `linked_tasks`, `request_log_ids`, `commit_refs`, and `pr_refs` should prefer stable ids or canonical project-relative paths.

## Newly standardized fields

These were either missing from the older specs or only partially implemented in code:

- `description`
- `summary`
- `priority`
- `risk_level`
- `complexity`
- `track`
- `timeline_estimate`
- `target_release`
- `milestone`
- `linked_features[]` as typed relationships with `type`, `source`, and `confidence`
- `decision_status`
- `execution_readiness`
- `test_impact`
- `integrity_signal_refs`
- `primary_doc_role`

## Migration intent

The implementation plan for adopting these schemas is:

- [document-feature-schema-alignment-v1.md](/Users/miethe/dev/homelab/development/CCDash/docs/project_plans/implementation_plans/refactors/document-feature-schema-alignment-v1.md)

Current rollout status:

- Parser/repository normalization, feature bubble-up, and document/feature UI surfaces are implemented.
- Legacy frontmatter aliases and superseded root-level spec doc classification are supported for migration/backfill.
- Parser/aggregation/snapshot coverage was expanded in backend tests for rollout safety.
