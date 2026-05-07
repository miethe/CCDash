---
title: Artifact Intelligence Calibration Report v1
description: Seeded recommendation calibration review for CCDash artifact intelligence
audience: developers, operators
tags: [artifact-intelligence, skillmeat, calibration, recommendations]
created: 2026-05-07
updated: 2026-05-07
category: validation
status: active
related:
  - "../project_plans/implementation_plans/integrations/skillmeat-artifact-usage-intelligence-exchange-v1/phase-6-validation-docs.md"
  - "../project_plans/PRDs/integrations/skillmeat-artifact-usage-intelligence-exchange-v1.md"
  - "artifact-intelligence-operator-guide.md"
  - "artifact-intelligence-privacy-audit.md"
---

# Artifact Intelligence Calibration Report v1

## Scope

This report reviews the current seeded recommendation fixtures in:

- `backend/tests/test_artifact_recommendation_service.py`
- `backend/tests/test_artifact_ranking_calibration.py`

The review is fixture-based, not a production precision study. It checks whether seeded attribution and ranking scenarios produce the expected advisory recommendation type, confidence behavior, and stale-snapshot suppression.

## Calibration Sample

| # | Seed scenario | Expected type | Observed type | Confidence | Evidence check |
| --- | --- | --- | --- | --- | --- |
| 1 | Always-loaded `unused`, zero artifact sessions, fresh snapshot | `disable_candidate` | `disable_candidate` | `0.65` | Uses project session count 12, load mode `always`, status `active`. |
| 2 | Always-loaded `narrow`, one workflow, context pressure `0.82` | `load_on_demand` | `load_on_demand` | `0.72` | Applies narrow-workflow/context-pressure discount from base confidence `0.8`. |
| 3 | `expensive`, 8 sessions, efficiency `0.3`, cost `$2.50` | `optimization_target` | `optimization_target` | `0.8` | High utilization plus poor efficiency/cost evidence present. |
| 4 | `unresolved`, observed usage with missing identity confidence | `identity_reconciliation` | `identity_reconciliation` | `0.8` | Keeps artifact id in evidence for mapping review. |
| 5 | `cold`, project session count below minimum | `insufficient_data` | `insufficient_data` | none | Suppressed by `sample_below_threshold`. |
| 6 | `versioned` v2 success `0.65` vs v1 success `0.92` | `version_regression` | `version_regression` | `0.8` | Captures prior/current versions and score gap. |
| 7 | `swap-current` underperforms `swap-alt` in `workflow-a` | `workflow_specific_swap` | `workflow_specific_swap` | `0.68` | Includes current and alternative artifact ids. |
| 8 | Low-confidence `expensive`, confidence `0.4` | `insufficient_data` | `insufficient_data` | `0.4` | Suppressed by `confidence_below_threshold`; min confidence is `0.6`. |
| 9 | Stale always-loaded `unused`, snapshot 8 days old | `insufficient_data` | `insufficient_data` | none | Suppresses `disable_candidate`; evidence records `suppressedType: disable_candidate`. |
| 10 | Calibration high-usage `expensive`, efficiency `0.25`, cost `$2.00` | `optimization_target` | `optimization_target` | `0.85` | Independent calibration fixture matches expected high-use optimization type. |

Result: 10 of 10 reviewed seeded recommendations matched the expected recommendation type. This supports the current rule mapping, but it should not be read as an 80%+ production precision claim because the sample is synthetic and intentionally separated by clear thresholds.

## False Positive Risk Notes For V2

No false positives were observed in the seeded sample. Remaining V2 risks are mostly boundary and context risks:

- `disable_candidate` can be harmful if the SkillMeat snapshot is incomplete, the project/collection mapping is wrong, or usage attribution has delayed ingestion. Current V1 mitigation is advisory-only next actions plus stale-snapshot suppression.
- `load_on_demand` and `workflow_specific_swap` can overfit narrow seeded windows. V2 should add seasonality, workflow criticality, protected/default artifact policy, and operator review outcomes before raising confidence.
- `optimization_target` is safe as prioritization advice, but cost or risk spikes can be transient. V2 should distinguish sustained poor efficiency from one-off expensive sessions.
- `identity_reconciliation` is low action risk, but false matches during identity repair would affect later rankings. Keep unresolved quarantine and avoid aggressive fuzzy matching without review.

## Confidence Calibration Assessment

Confidence behavior is directionally calibrated for the seeded rules:

- Actionable recommendations require minimum project/artifact sample size before confidence is considered, except the zero-usage always-loaded path, which still requires project-level sample support.
- Low-confidence attribution (`0.4`) is downgraded to `insufficient_data` instead of producing an optimization recommendation.
- Rule-derived discounts are visible: `load_on_demand` emits `0.72` from base `0.8`, and `workflow_specific_swap` emits `0.68` from base `0.8`.
- `disable_candidate` uses a fixed moderate confidence (`0.65`) because confidence is not meaningful for zero attributed artifact sessions; this is acceptable for V1 because the next action is human review, not mutation.

Calibration gap: the current fixtures test threshold behavior, not probability calibration against labeled production outcomes. V2 should persist accepted/rejected/no-action-safe review outcomes before using these confidence values for automated prioritization or cross-project benchmarking.

## Staleness Gating

The seeded destructive scenario is verified: stale `disable_candidate` recommendations are suppressed to `insufficient_data` with `rationale_code: stale_snapshot` and evidence carrying `suppressedType: disable_candidate`.

Current service logic also routes actionable recommendation types through recommendation-specific freshness thresholds before emitting advice. Operator-facing defaults are:

| Recommendation type | Default stale threshold |
| --- | --- |
| `disable_candidate` | 7 days |
| `workflow_specific_swap` | 7 days |
| `load_on_demand` | 14 days |
| `version_regression` | 14 days |
| `optimization_target` | 30 days |
| `identity_reconciliation` | 30 days |
| `insufficient_data` | 30 days |

Assessment: V1 staleness gating is correct for the reviewed destructive stale-snapshot case. Before expanding recommendations beyond advisory UX, add boundary tests for stale `load_on_demand`, `workflow_specific_swap`, `version_regression`, and `optimization_target` so every actionable stale gate has direct fixture coverage.

## Validation Commands

Run the focused calibration suite:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_artifact_recommendation_service.py backend/tests/test_artifact_ranking_calibration.py -q
```

Check report formatting whitespace:

```bash
git diff --check -- docs/guides/artifact-intelligence-calibration-report-v1.md
```
