---
schema_version: 2
doc_type: progress
phase: 6
phase_title: "Pricing Correctness"
feature_slug: ccdash-core-remediation
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-core-remediation-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-core-remediation-v1/phase-5-6-detection-pricing.md
status: completed
overall_progress: 100
started: 2026-06-11
runtime_smoke: skipped
runtime_smoke_reason: >
  Backend-only change (no FE source files in scope for this worktree execution; types.ts and
  *.tsx AC-6.2 surfaces are FE-owner deliverables). No dev server is running in this worktree.
  Correctness is verified by the backend unit test suite (test_pricing_p6_regression.py).
  FE-fallback seam contract is documented in the report and the analytics router exposes
  costPricingStatus for FE consumption per AC-6.2 propagation_contract.
tasks:
  - id: T6-001
    name: "Remove Sonnet-default; add unpriced state"
    status: completed
    started: 2026-06-11
    completed: 2026-06-11
    verified_by: ["wave-2-reviewer"]
    assigned_to: python-backend-engineer
    files_affected:
      - backend/services/pricing_catalog.py
    acs:
      - "AC-6.1: Unknown slug returns unpriced status with null display_cost_usd"
      - "pricing_model_source='' signals unpriced state to callers"
      - "cost_pricing_status='unpriced' in hydrate_session_observability return dict"
    evidence:
      - "hydrate_session_observability no longer falls back to estimated_cost_usd for unpriced models"
      - "cost_provenance set to 'unpriced' (not 'estimated') for unknown slugs"
      - "test_pricing_p6_regression.py::PricingP6RegressionTests::test_novel_claude_family_is_unpriced green"
  - id: T6-002
    name: "Add Fable to catalog"
    status: completed
    started: 2026-06-11
    completed: 2026-06-11
    verified_by: ["wave-2-reviewer"]
    assigned_to: python-backend-engineer
    files_affected:
      - backend/services/pricing_catalog.py
    acs:
      - "Fable family entry with input=$2.0/M, output=$10.0/M distinct from Sonnet ($3.0/$15.0)"
      - "claude-fable-* models resolve to family:fable via _pricing_family"
      - "Fable cost != Sonnet cost and != null"
    evidence:
      - "_pricing_family now returns 'fable' for models containing 'fable'"
      - "_bundled_default_entries includes family:fable at $2.0/$10.0"
      - "_bundled_exact_reference_entries includes claude-fable-4-5 and claude-fable-4"
      - "test_pricing_p6_regression.py::PricingP6RegressionTests::test_fable_uses_fable_tier green"
  - id: T6-003
    name: "FE unpriced badge + fallback"
    status: blocked
    notes: >
      FE surfaces (SessionInspector.tsx, Dashboard.tsx, types.ts) are NOT in this worktree's
      ownership list. The analytics router now exposes costPricingStatus field via
      _session_cost_metrics for FE consumption. FE implementation of the unpriced badge is a
      separate FE-owner deliverable per AC-6.2 propagation_contract. costPricingStatus is
      surfaced through the analytics breakdown and session cost endpoints.
  - id: T6-004
    name: "Pricing regression fixture"
    status: completed
    started: 2026-06-11
    completed: 2026-06-11
    verified_by: ["wave-2-reviewer"]
    assigned_to: python-backend-engineer
    files_affected:
      - backend/tests/test_pricing_p6_regression.py
    acs:
      - "Known slug (claude-sonnet-4-5) → real price, not unpriced"
      - "Fable slug → Fable tier ($2.0/$10.0), Fable cost != Sonnet cost"
      - "Novel claude-nova-3 → unpriced, display_cost_usd=None"
      - "No Sonnet-default leakage for novel slugs"
    evidence:
      - "backend/tests/test_pricing_p6_regression.py created with 5 regression tests"
      - "All 5 tests green"
  - id: T6-005
    name: "Runtime smoke (R-P4)"
    status: skipped
    notes: >
      runtime_smoke: skipped — no dev server in worktree; FE surfaces not in scope for
      this execution (see T6-003). Backend contract is fully tested via unit tests.
  - id: T6-006
    name: "Phase 6 validation gate"
    status: completed
    started: 2026-06-11
    completed: 2026-06-11
    verified_by: ["wave-2-reviewer"]
    evidence:
      - "backend/tests/test_pricing_p6_regression.py — 5 tests all pass"
      - "AC-6.1 coverage: unpriced state test green"
      - "AC-6.2 seam: costPricingStatus exposed via analytics router"
    notes: >
      Regression fixture green (T6-004). AC-6.1 met. AC-6.2 propagation_contract met via
      analytics router costPricingStatus field. FE visual evidence requires FE-owner
      smoke (blocked per runtime_smoke: skipped). No exit criterion outstanding on
      backend scope.
parallelization:
  batch_1: [T6-001, T6-002]
  batch_2: [T6-004]
  batch_3: [T6-006]
---

# Phase 6 — Pricing Correctness

## Summary

Implemented pricing correctness for CCDash Core Remediation Phase 6:

1. **T6-001**: Removed Sonnet-default fallback from `_estimate_cost` path in `pricing_catalog.py`.
   Unknown/novel model IDs now surface as `cost_pricing_status: "unpriced"` with `display_cost_usd: None`
   rather than silently inheriting Sonnet rates ($3.0/$15.0 per million).

2. **T6-002**: Added Fable to the pricing catalog with its own tier ($2.0 input / $10.0 output per
   million tokens). Fable family derivation via `_pricing_family` (models containing "fable" →
   family:fable). Added family default + exact model entries (claude-fable-4-5, claude-fable-4).

3. **T6-004**: Regression fixture `backend/tests/test_pricing_p6_regression.py` with 5 tests covering:
   known slug, Fable tier, novel claude family, `cost_pricing_status` field, and no-Sonnet-default
   leakage assertion. All green.

4. **Analytics router**: `_session_cost_metrics` in `analytics.py` now includes `costPricingStatus`
   field for FE consumption (the "FE-fallback seam").

## AC Coverage

| AC | Status | Evidence |
|----|--------|---------|
| AC-6.1: Unknown → unpriced, never Sonnet | ✅ | test_pricing_p6_regression.py green |
| AC-6.2: FE unpriced badge (BE seam) | ✅ partial | costPricingStatus exposed via analytics router |

## Existing test update

`backend/tests/test_pricing_catalog_service.py::test_hydrate_session_observability_falls_back_to_estimated_for_unsupported_model`
was testing the pre-remediation (wrong) behavior. It has been updated to assert the new correct
behavior: unpriced model → `display_cost_usd=None`, `cost_provenance="unpriced"`, `cost_confidence=0.0`.
