---
schema_name: ccdash_document
schema_version: 3
doc_type: implementation_plan
doc_subtype: implementation_plan
primary_doc_role: supporting_document
status: in_progress
category: refactors
title: "Implementation Plan: Document + Feature Schema Alignment V1"
description: "Adopt the canonical document frontmatter schemas, normalize the missing fields, expand document and feature surfaces, and add typed linked-feature relationships."
summary: "Refactor document parsing, storage, API shapes, and UI surfaces so CCDash exposes the full useful metadata already present in plan documents and progress trackers."
author: codex
audience: [ai-agents, developers, engineering-leads]
created: 2026-03-05
updated: 2026-03-05
tags: [documents, features, schemas, mapping, ui, refactor]
priority: high
risk_level: medium
complexity: high
track: standard
timeline_estimate: "2-3 weeks across 7 phases"
linked_features: []
related_documents:
  - docs/schemas/document_frontmatter/README.md
  - docs/schemas/document_frontmatter/document-and-feature-mapping.md
---

# Implementation Plan: Document + Feature Schema Alignment V1

## Objective

Bring CCDash into alignment with the canonical schemas in `docs/schemas/document_frontmatter/` so that:

1. document frontmatter is normalized consistently
2. document modals/cards show all useful typed data
3. features bubble up the right subset of doc metadata
4. linked-feature relationships become typed, derived, and user-overridable

## Scope

In scope:

1. parser normalization for the new shared fields
2. storage/API updates for document and feature payloads
3. document modal, document catalog, feature modal, and feature card updates
4. feature bubble-up and derived-field logic
5. migration/backfill support for legacy frontmatter aliases

Out of scope:

1. changing every existing markdown file immediately
2. in-app editors for manual metadata override
3. cross-project reuse work outside CCDash itself

## Phase 1: Canonical model expansion

Tasks:

1. Expand `DocumentFrontmatter`, `DocumentMetadata`, `LinkedDocument`, and `Feature` models with the canonical fields from the new schemas.
2. Make `doc_type` canonicalization support `design_doc` directly and treat `design_spec` as a subtype.
3. Add typed `linked_features[]` support to both document and feature models.

Acceptance criteria:

1. Backend and frontend types match the schema catalog.
2. No currently parsed fields regress.

## Phase 2: Parser and repository normalization

Tasks:

1. Extend `backend/parsers/documents.py` to normalize `description`, `summary`, `priority`, `risk_level`, `complexity`, `track`, `timeline_estimate`, `target_release`, `milestone`, `decision_status`, `execution_readiness`, `test_impact`, `linked_features[]`, and doc-type-specific blocks.
2. Extend `extract_frontmatter_references` and related helpers to extract typed linked-feature objects and legacy aliases.
3. Persist high-value stable fields into typed columns or structured JSON where appropriate.

Acceptance criteria:

1. Document API payloads expose the normalized fields.
2. Legacy frontmatter aliases still ingest cleanly.

## Phase 3: Feature bubble-up and correlation logic

Tasks:

1. Expand `backend/parsers/features.py` to bubble up the approved fields from the mapping spec.
2. Add `primary_documents`, `document_coverage`, `execution_readiness`, `quality_signals`, and typed `linked_features[]`.
3. Merge explicit, lineage-derived, and inferred feature relationships with source/confidence metadata.

Acceptance criteria:

1. Features expose richer typed metadata without changing document ownership semantics.
2. Related-feature links include a type whenever correlation can determine one.

## Phase 4: Document UI surfaces

Tasks:

1. Refactor `DocumentModal` to use the canonical tabs: `Summary`, `Delivery`, `Relationships`, `Content`, `Timeline`, `Raw`.
2. Expand `PlanCatalog` card/list/folder metadata panes to show typed metadata and doc-type-specific summaries.
3. Ensure every document type renders all relevant available fields, not just progress docs.

Acceptance criteria:

1. PRD, plan, phase plan, progress, report, design, and spec docs all show complete typed metadata when present.
2. Linked refs open the correct entity when resolvable.

## Phase 5: Feature UI surfaces

Tasks:

1. Expand `ProjectBoard` feature modal Overview/Docs and add a `Relations` tab.
2. Update feature cards/list cards to show priority, coverage, readiness, and linked-feature summary.
3. Expand the execution workbench feature context to reuse the same feature metadata blocks.

Acceptance criteria:

1. Feature surfaces expose bubbled metadata consistently.
2. Document-derived feature relationships are visible from the feature modal and cards.

## Phase 6: Migration and backfill

Tasks:

1. Add compatibility mapping for old root-level docs and legacy frontmatter keys.
2. Add a backfill or resync path so existing documents populate the new fields.
3. Update any developer references that currently point to the superseded specs.

Acceptance criteria:

1. Full resync populates the new fields for current repo documents.
2. No broken references remain to the archived spec docs.

## Phase 7: Tests and rollout

Tasks:

1. Add parser tests covering each schema file’s key fields.
2. Add feature aggregation tests for bubble-up precedence and typed linked-feature derivation.
3. Add UI tests or snapshot coverage for the major document and feature surfaces.

Acceptance criteria:

1. Document parsing tests cover every canonical doc type.
2. Feature aggregation tests cover lineage-derived and manual feature relationships.

## Phase 6-7 execution log

Completed implementation checkpoints:

1. `fc2e7e1` — Added phase-6 migration compatibility:
   - legacy root-level spec doc typing/classification
   - legacy frontmatter alias normalization for parser backfill
   - regression tests for compatibility mappings
2. `886fbba` — Added phase-7 rollout coverage:
   - parser coverage across canonical doc types
   - feature aggregation precedence and relationship-source tests
   - document/feature surface snapshot normalization tests
   - schema reference hygiene test for superseded spec paths

## Risks

1. The parser currently preserves raw frontmatter but normalizes only a narrow slice; adding too many unstable columns too early would increase churn.
2. Document types and subtypes are inconsistent today, especially around design docs.
3. Some documents use legacy aliases or unstructured prose where typed fields will need best-effort extraction first and authoring cleanup second.

## Recommended rollout order

1. Models and parser
2. Feature aggregation
3. Document surfaces
4. Feature surfaces
5. Resync/backfill
6. Cleanup and reference updates
