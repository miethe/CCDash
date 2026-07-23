# Phase 1 Completion Note — Verdict Reconciliation + Persistence Foundation

**Status:** COMPLETED · branch `feat/ccdash-automated-aar-review` · 2026-07-22
**Validator:** task-completion-validator — code APPROVED (68/68 tests green); tracking gaps found and remediated before commit.

## What was built

1. **DTO reconciliation (T1-003, T1-004 · D1):** `AARReviewDTO` reconciled to PRD §7.2 — nested
   `correlation{strategy, confidence, session_ids, feature_id}` + 3-value
   `triage_verdict (surface_only | deep_review_recommended | human_triage_required)`;
   `schema_version` bumped to 2. Old flat fields (`session_refs`, `correlation_confidence`,
   `correlation_strategy`, `verdict`) retained as deprecated aliases, auto-synced via a pydantic
   `model_validator`, for a one-release deprecation window. Contract test pins the exact shape +
   alias consistency (`backend/tests/test_aar_review_dto_contract.py`).

2. **OQ-2 resolution (T1-002 · `compute_verdict`):** Correlation *strategy* never forces
   `human_triage_required`; only confidence value/ambiguity gates it — null confidence →
   human_triage; `< 0.64` → human_triage; ambiguous multi-session two-hop tie → human_triage;
   else deterministic flag mapping. Rationale grounded in OQ-1 data (below).

3. **OQ-1 prevalence (T1-001):** Sampled 9 real AAR docs — 0/9 direct session ref, 6/9 two-hop via
   `feature_slug`, 3/9 uncorrelatable. Two-hop dominates; entity_links freshness is the binding
   constraint. Evidence: `.claude/worknotes/ccdash-automated-aar-review/oq1-aar-prevalence.md`.

4. **Persistence (T1-005..T1-008):** New `aar_reviews` rollup table with dual, parity-clean DDL
   (SQLite TEXT / Postgres JSONB; composite PK `(aar_document_id, session_id)` = upsert key +
   P6 dedup key; guard-input columns `provenance_skill_name`, `provenance_workflow_id`).
   `backend/db/repositories/aar_reviews.py` — every write via `retry_on_locked`, upsert-by-composite-key,
   `PRAGMA busy_timeout=30000`. Direct-count + upsert-idempotency tests (ADR-007). Idempotent backfill
   (`backend/scripts/aar_reviews_backfill.py`) reuses `AARReviewQueryService.get_review` verbatim.

5. **ADR addendum (T1-009):** D1 + OQ-2 recorded in
   `docs/project_plans/exploration/ccdash-automated-aar-review/ccdash-automated-aar-review-proposed-adr.md`.

## Verification

- 68/68 named tests green (contract 20 + repo 27 + MVP-reconciled 21). Bare `pytest` collection avoided (hangs).
- Hard Invariant #1 confirmed by import audit: zero LLM/model calls on the compute/persistence path.
- Dual-DDL parity: `column_parity_diff("aar_reviews") == {}`; PG DDL syntax reviewed vs `research_runs` precedent.
- **Deferred (consolidated):** live `docker:hosted:smoke:seeded-pg` PG apply of the full v42 migration set
  runs ONCE before the final squash-to-main (no local PG available per-phase). SQLite green + parity test
  + PG-syntax review carry P1 confidence until then.

## Recommendations for Phase 2

- Live persist-on-compute wiring (calling `aar_reviews` repo from the `aar_review.py` compute path) was
  intentionally NOT done in P1 (not in AC-P1.1/P1.2 scope) to keep W2 off W1's files. P2 (evidence
  enrichment) already edits `aar_review.py` — fold the persist hook there.
- Enrichment must remain deterministic (Invariant #1); it adds evidence/reasons, not new verdicts.
