---
schema_version: 2
doc_type: design_spec
title: "Research Foundry Run Telemetry: Extraction Failure Rate by Extractor"
status: draft
maturity: idea
created: 2026-07-21
updated: 2026-07-21
feature_slug: "research-foundry-run-telemetry"
prd_ref: docs/project_plans/PRDs/features/research-foundry-run-telemetry-v1.md
category: analytics
tags:
  - design-spec
  - research-foundry
  - analytics
  - deferred-item
  - source-cards
  - extractor-reliability
problem_statement: "Operators cannot see which content extractor (e.g. readability, boilerplate-strip, PDF, JS-render) is failing most often, because extractor identity lives on RF's source_card entity, not on the §16 execution_event this feature ingests."
open_questions: []
explored_alternatives: []
related_documents:
  - docs/project_plans/implementation_plans/features/research-foundry-run-telemetry-v1.md
  - docs/project_plans/implementation_plans/features/research-foundry-run-telemetry-v1/phase-4-hardening-docs.md
  - docs/project_plans/PRDs/features/research-foundry-run-telemetry-v1.md
---

# Research Foundry Run Telemetry: Extraction Failure Rate by Extractor

## Context

This is deferred item **DF-003** from the Research Foundry (RF) Run Telemetry PRD (§12, "Extraction failure rate by extractor" — PRD §16.2 panel #7). It was named out of scope for v1 in the PRD's Contract Reality / Out of Scope section (§ "Out of Scope") and carried into the Phase 4 hardening plan as task **T4-003** under the mandatory DOC-006 deferred-item process.

The v1 feature (`research-foundry-run-telemetry` v1) ingests RF's §16 `execution_event` — a run-level aggregate payload that carries a `selected_providers` **list** and rollup metrics, but no per-source detail. Extractor identity (which parsing/extraction strategy handled a given source URL, and whether it succeeded or failed) lives on RF's `source_card` entity (RF spec §11.3), which this feature does not ingest. Without `source_card` data, CCDash has no way to attribute extraction failures to a specific extractor.

This mirrors DF-001 and DF-002, which are blocked by the same missing `source_cards` join — all three deferred items share one unblock path.

## Problem Statement

Operators viewing the Provider Economics analytics tab currently see no failure-rate breakdown by extraction method. When RF search runs report degraded source quality or a high volume of unusable/empty extractions, operators cannot tell whether the cause is concentrated in one extractor (e.g. a PDF extractor failing on paywalled content, a JS-render extractor timing out on heavy SPAs) versus spread evenly across the run. This makes root-causing systemic RF extraction quality regressions from CCDash alone impossible in v1.

## Idea

Panel concept: **"Extraction Failure Rate by Extractor"** — a bar or stacked-bar panel on the Provider Economics tab showing, per extractor identity, the ratio of failed/empty extractions to total extraction attempts across a selected time window or run set.

Possible direction, once unblocked:

1. Ingest RF's `source_card` records (RF spec §11.3) as a new entity, keyed to the parent `research_runs` row via `run_id` (same correlation pattern already established for `rf_events` → `research_runs`).
2. Persist `source_card.extractor` (extractor identity string) and an extraction-outcome field (success/failure/empty) per source card.
3. Add a query in `backend/application/services/agent_queries/run_intelligence.py` (or a new `source_card_intelligence.py` sibling, per the transport-neutral pattern) that groups source cards by `extractor` and computes failure rate = `failed_count / total_count`.
4. Surface as a new panel in `AnalyticsDashboard.tsx`'s Provider Economics tab, following the existing 4-panel v1 layout conventions.
5. Consider whether failure rate should be windowed (last N runs, last N days) or all-time, and whether low-sample extractors need a minimum-count threshold before being charted (to avoid noisy percentages from a single run).

## Open Questions

1. Does RF's `source_card.extractor` field enumerate a small fixed set of extractor identities, or is it a free-form string that could fragment across RF versions (requiring a normalization/mapping layer on ingest)?
2. Should `source_card` ingestion be a shared entity feeding all three of DF-001, DF-002, and DF-003, or should each be scoped independently? (Recommendation: shared — see Unblock Condition below.)
3. What counts as an "extraction failure" from RF's perspective — an explicit error status, an empty/zero-length content result, or both? This needs to be confirmed against the RF `source_card` schema (§11.3) rather than assumed.
4. Does this warrant a new dual-DDL table (`source_cards`), or can extractor + outcome be folded into a lighter-weight derived rollup without persisting every source card row?

## Unblock Condition

**Same `source_cards` join as DF-001 and DF-002** (per the PRD §12 table and the parent plan's Deferred Items table). Specifically: CCDash must ingest RF's §11.3 `source_card` entity — at minimum the fields `run_id` (or equivalent correlation key), `extractor`, and an extraction-outcome indicator — before this panel is computable.

Given that DF-001 (per-provider cost/quality splits), DF-002 (useful-source rate by domain), and DF-003 (this item) all depend on the identical `source_cards` join, the recommended promotion path is a **single follow-up feature** that ingests `source_card` as a new entity once and unlocks all three panels together, rather than three independent ingestion efforts.

## Promotion Criteria

Promote this idea to a shaped design (or directly to an implementation plan) when either:

- RF emits per-provider/per-source metric splits in a future `execution_event` schema version that removes the need for a separate `source_cards` join, **or**
- A decision is made to ingest RF's `source_card` entity (RF spec §11.3) as a new CCDash entity correlated to `research_runs`, at which point this spec should be expanded alongside DF-001 and DF-002 into a single follow-up PRD/plan covering all three source-card-derived panels.
