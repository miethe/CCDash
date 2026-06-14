---
schema_version: 2
doc_type: design_spec
title: "D-001: Correlation-Tab 'Observed Workload' Multi-Feature Session Over-Count (F-W6-001)"
description: >
  Deferred design spec for the Correlation-tab 'Observed Workload' over-count finding
  (F-W6-001). Documents what the artifact is, why it is deferred, the investigation
  scope if promoted, and the precise promotion trigger.
maturity: idea
status: deferred
created: '2026-06-14'
updated: '2026-06-14'
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-runtime-deploy-remediation-v1.md
findings_ref: .claude/findings/ccdash-core-remediation-findings.md
related_documents:
  - components/Analytics/AnalyticsDashboard.tsx
  - backend/routers/analytics.py
tags:
  - analytics
  - correlation
  - deferred
  - display
  - counting
audience: developers
category: design-spec
---

# D-001: Correlation-Tab "Observed Workload" Multi-Feature Session Over-Count

## 1. Finding Summary

**Finding ID**: F-W6-001
**Surfaced**: T12-006 audit (AC R12.6), 2026-06-12
**Severity at surface**: Low/Medium — display over-count; no data-integrity fault
**Current status**: Deferred (T4-006, 2026-06-14)

During the T12-006 audit of the per-lifecycle-event token aggregation path
(`backend/routers/analytics.py` ≈ line 553/570, `session_metrics().total_tokens`),
the auditor confirmed that the audited key is never surfaced as a workload/total metric
in any panel: aggregation loops read `token_input`/`token_output` separately into
deduplicated per-dimension buckets. **AC R12.6 passed.**

A tangential discovery, on a distinct code path, was recorded as F-W6-001:

The **Correlation tab "Observed Workload" MetricCard** in
`components/Analytics/AnalyticsDashboard.tsx` (≈ line 1142) sources its value from
`correlationSummary.totalTokens`, which is populated by the `/analytics/correlation`
endpoint's `_session_usage_metrics` aggregation. That aggregation walks session rows
and sums token counts per session. When a session is linked to multiple features, it
appears to be included in the sum once per feature association — producing a
multi-feature over-count in the displayed total.

## 2. Why It Is Deferred

### 2.1 Not a Data-Integrity Fault

The over-count is a **display artifact** confined to one MetricCard on the Correlation
tab. The underlying session, token, and feature data stored in the database is correct.
No write path, no export, no downstream consumer, and no stored aggregate is affected.
The correlation aggregation path (`_session_usage_metrics`) is a read-time rollup; no
persisted value is corrupted.

### 2.2 Distinct From the Token-Undercount Remediation

The token-undercount remediation was shipped 2026-03-09 and is explicitly out of scope
for this epic. F-W6-001 is a separate, opposite-direction artifact (over-count vs.
under-count) on a different code path (correlation summary vs. per-session lifecycle
aggregation). Bundling them would expand scope without shared code surface.

### 2.3 No Confirmed Billing or Quota Risk

No current CCDash surface uses `correlationSummary.totalTokens` for billing computation,
quota enforcement, or any authoritative capacity signal. The value is informational —
intended to give operators a rough sense of workload correlation across features. An
over-count in that context does not cause incorrect behavior elsewhere.

### 2.4 Phase Scope

Phase 5 (W4) is a finding-triage and close-out phase, not an analytics-remediation
phase. Implementing a correct deduplication strategy in the correlation aggregation path
is a non-trivial change requiring targeted investigation, backend query restructuring,
and frontend contract validation. That work belongs in a dedicated analytics improvement
epic, not a cleanup phase.

## 3. Investigation Scope If Promoted

If this item is promoted (see Section 4 for trigger), the following investigation is
required before any implementation begins:

### 3.1 Confirm the Over-Count Mechanism

- Trace `_session_usage_metrics` in `backend/routers/analytics.py` to determine the
  precise join path between sessions and features in the correlation query.
- Identify whether over-counting occurs at the SQL level (session rows duplicated by a
  JOIN with features) or at the Python aggregation level (same session id summed
  multiple times in a loop).
- Produce a reproducer: two features sharing at least one session; compare displayed
  `totalTokens` to the sum of unique-session token values.

### 3.2 Scope the Impact Surface

- Audit every consumer of `correlationSummary` (frontend components, MCP tools,
  CLI report commands) to determine whether any non-display consumer exists.
- Check whether `totalTokens` or any correlated field is referenced in export paths,
  billing hooks, or operator-visible reports beyond the MetricCard.

### 3.3 Design a Fix

Two candidate approaches:

**Option A — Deduplicate at the SQL level**: Restructure the correlation query to
`SELECT DISTINCT session_id` (or use `GROUP BY session_id`) before summing token
counts, ensuring each session contributes exactly once regardless of how many features
it is linked to.

**Option B — Deduplicate in the Python aggregation layer**: Track a `seen_session_ids`
set in `_session_usage_metrics`; skip a session's token contribution if already
counted.

Option A is preferred for correctness (deduplication at the source) but requires
careful query analysis to avoid breaking other correlation dimensions (per-feature
breakdown, per-phase breakdown) that legitimately need the multi-feature join.

### 3.4 Validate Resilience

- Confirm FE MetricCard handles a corrected (lower) value without layout breakage.
- Confirm the MCP and CLI correlation report outputs are consistent post-fix.
- Add a regression test using a session linked to two features; assert
  `totalTokens == sum of unique-session tokens`, not sum of (session × feature) rows.

### 3.5 Relevant File Anchors

| Surface | Location |
|---------|----------|
| MetricCard display | `components/Analytics/AnalyticsDashboard.tsx` ≈ line 1142 |
| Correlation endpoint | `backend/routers/analytics.py` — `/analytics/correlation` handler |
| Session usage aggregation | `backend/routers/analytics.py` — `_session_usage_metrics` |
| Feature–session link table | `backend/db/repositories/links.py` |

## 4. Promotion Trigger

**Promote this item (change `status: deferred` → `status: active`) when any of the
following conditions is met:**

1. **Billing or quota enforcement**: `correlationSummary.totalTokens` (or any field
   derived from `_session_usage_metrics`) is used, directly or indirectly, as an input
   to a billing computation, quota threshold, or capacity-enforcement gate.

2. **Operator-reported inflation**: One or more operators file a report that the
   Correlation tab "Observed Workload" total is visibly and materially inflated relative
   to their expected session volume, causing confusion or incorrect capacity planning
   decisions.

3. **Export surface expansion**: The correlation summary is added to an export format
   (CSV, JSON snapshot, external integration) that is consumed by an authoritative
   downstream system where an over-count would propagate.

**Owner on promotion**: analytics surface owner (currently unassigned).

## 5. Acceptance Criteria (Placeholder — for use when promoted)

When this item is promoted to active, the following ACs apply:

```yaml
AC-D001-1:
  description: >
    A session linked to N features contributes its token counts exactly once to
    correlationSummary.totalTokens, regardless of N.
  verified_by:
    - backend/tests/test_analytics_correlation.py  # new: multi-feature session dedup test
    - curl /analytics/correlation (manual spot-check with known fixture)

AC-D001-2:
  description: >
    All existing correlation breakdown dimensions (per-feature, per-phase)
    continue to report correctly after the deduplication fix.
  verified_by:
    - backend/tests/test_analytics_correlation.py  # regression coverage

AC-D001-3:
  description: >
    FE MetricCard renders the corrected value without layout breakage or
    visible error state.
  verified_by:
    - Runtime smoke: Correlation tab loads; MetricCard displays a non-NaN value
```

---

*Deferred under ccdash-runtime-deploy-remediation-v1, Phase 5, Task T5-006. See
`.claude/findings/ccdash-core-remediation-findings.md` — F-W6-001 for original
finding record.*
