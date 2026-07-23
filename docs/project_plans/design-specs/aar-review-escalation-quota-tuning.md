---
title: "Design Spec: AAR Review Escalation Quota & Pre-Production Hardening (OQ-4)"
doc_type: design-spec
maturity: shaping
feature_slug: ccdash-automated-aar-review
prd_ref: docs/project_plans/PRDs/features/ccdash-automated-aar-review-v1.md
status: draft
created: 2026-07-23
updated: 2026-07-23
audience: developers
category: operational-tuning
tags:
  - ccdash
  - aar-review
  - escalation-quota
  - rate-limiting
  - operational-tuning
  - p4-hardening
related_documents:
  - docs/project_plans/PRDs/features/ccdash-automated-aar-review-v1.md
  - docs/project_plans/implementation_plans/features/ccdash-automated-aar-review-p4-phase.md
description: |
  Specification of the escalation quota (count/time-window) guard for P4 autonomous
  worker. Captures the SHIPPED default per-project quota, its operational rationale,
  tuning knobs, and signals for revision. Also documents the pre-production hardening
  checklist derived from P6 integration work. Addresses open question OQ-4 from the PRD.
schema_version: 2
---

# Design Spec: AAR Review Escalation Quota & Pre-Production Hardening (OQ-4)

## Problem Statement

**Current State (PRD §8.1, Guard 3)**:
- CCDash's autonomous AAR-review triage can emit unbounded `aar_review_candidate` events to `op`
- `op story`'s own escalation path (classify→plan→dispatch) is the only cost brake
- Without an explicit quota in CCDash, a misconfigured triage policy or unexpected volume spike could overwhelm `op`'s dispatch gate with hundreds of low-signal candidates

**Problem**: Unbounded handoff from CCDash to `op` violates the "producer-only" boundary (ADR Decision 3, Risk §12 of PRD). A hard, configurable quota checked *before* any handoff prevents runaway spend and protects `op`'s own gates from becoming a bottleneck.

**P6 Integration Experience**: Phase 6 resolved escalation quota operationally (after pre-production testing showed the boundary was necessary). This spec captures the SHIPPED default and the pre-production hardening checklist for P4 and beyond.

---

## Proposed Design

### 2.1 Escalation Quota Default (Shipped in P6, to be promoted to P4)

**Configuration**:

```yaml
# backend/config.py environment variables
CCDASH_AAR_ESCALATION_QUOTA:
  description: "Max number of AARs that can be handed off to op per time window"
  type: integer
  default: 5
  
CCDASH_AAR_ESCALATION_WINDOW_HOURS:
  description: "Time window (hours) for the escalation quota"
  type: integer
  default: 24
  
# Derived: a quota violation means CCDash will NOT hand off the 6th+ AAR until
# the time window rolls over or quota is manually reset.
```

**Semantic**: Within a rolling 24-hour window, **per project**, at most **5 AARs** can be escalated (handed off to `op`). The 6th AAR in that window is:
- Logged as "quota exceeded" with trace_id/escalation_history
- Queued in a durable "pending quota" state (stored in a new `escalation_ledger` table, P4)
- Retried in the next time window (no loss; rate-limiting, not dropping)

### 2.2 Scope of the Quota

**Per-Project Scoping** (NOT global):
- The quota is maintained separately for each project (via `AuthContext.project_id` per ADR-010)
- Rationale: One project's aggressive triage policy must not starve another project's legitimate escalations
- Implementation: `(project_id, escalation_window_start)` is the key for quota tracking in the ledger

**Checked Before Handoff** (NOT after dispatch):
- The quota check happens inside CCDash's autonomous worker, immediately before the `op` CLI call or REST handoff
- If quota is exhausted, the escalation is queued; no call to `op` is made
- This ensures `op`'s own plan gate sees a steady, controllable stream

### 2.3 Tuning Knobs

All knobs are environment-variable-configurable; no restart required if deployed with hot reload of config (future):

| Knob | Default | Range | When to Adjust |
|------|---------|-------|----------------|
| `CCDASH_AAR_ESCALATION_QUOTA` | 5 | 1–100 | Start conservative (5). Increase if real escalation volume exceeds this regularly; decrease if quota is never exceeded (signal of over-engineering). |
| `CCDASH_AAR_ESCALATION_WINDOW_HOURS` | 24 | 1–720 | 24-hour rolling window is standard. Reduce to 6–12 hours for faster iteration in dev; increase to 7 days for production batch-review cycles. |
| `CCDASH_AAR_ESCALATION_PENDING_TTL_SECONDS` | 604800 (7 days) | 3600–2592000 | Pending escalations expire after 7 days to avoid stale queues. Reduce if triage freshness is critical; increase if slower review cycles are acceptable. |

**No per-flag overrides**: Each flag's severity (low/medium/high) does NOT bypass the quota. Only `human_triage_required` verdicts (confidence < 0.64) skip the quota check entirely — they are logged and surfaced immediately to a human operator, never queued for async dispatch.

---

## Pre-Production Hardening Checklist (P6 → P4)

**Promotion criteria**: Before enabling the autonomous worker in production (P4 exit criteria), the following checks must PASS. All items are implemented in P4, exercised in seeded-PG smoke, and verified in a pre-production deployment window.

### 3.1 Guard 1: Workspace Context & Session Fetch

**Issue (P6 discovery)**: The worker's session-fetch paths used a hardcoded `workspace_id='default-local'`, which broke when multiple workspaces were active. This violates ADR-010 (multi-project scoping).

**Hardening Task**:
- [ ] **Resolve worker's workspace_id hardcode**: The autonomous worker must inherit `AuthContext.workspace_id` from the project registry (ADR-006 DB-authoritative). Every session fetch in the escalation path must pass the correct workspace scope.
- [ ] **Verification**: Unit test asserting that a session from workspace-A is correctly scoped when fetching correlation context; sessions from workspace-B do not appear in workspace-A's triage results.

### 3.2 Guard 2: Writeback Seam (Conditional Readiness)

**Issue (P6 discovery)**: The writeback seam between CCDash and `op`'s gated approval flow is dormant (not yet wired in P4). Once activated in a future phase, this checklist ensures it doesn't silently drop approvals.

**Hardening Task** (Conditional — only when writeback seam is wired):
- [ ] **ApprovedRunReference validation**: When the worker receives an `op approve` signal, it must construct an `ApprovedRunReference` ONLY from a real, validated run record (not a synthetic/local record). Never hand off without a real run_id.
- [ ] **Escalation history enforcement**: Every escalation handed off must carry a non-empty `escalation_history` list (at minimum: escalation_timestamp, triage_verdict, project_id). Empty history is rejected with a clear error.
- [ ] **Test case**: A synthetic integration test asserts that an escalation with `escalation_history=[]` is rejected before any mutation occurs.

### 3.3 Guard 3: Memoized Query Invalidation

**Issue (P6 discovery)**: When a triage pass completes and new escalations are queued, the client-side query cache for `aar_review_list` was stale, showing old verdicts. This is a cache-coherence bug, not a triage bug, but critical for operator UX.

**Hardening Task**:
- [ ] **Cache invalidation after escalation**: After the autonomous worker completes a triage sweep, it MUST invalidate the `aar_review_list` memoized query cache entry (e.g., via `clear_project_cache(project_id, "aar_review_list")`).
- [ ] **Test case**: A runtime test confirms that `clear_project_cache` evicts the memoized entry, forcing a fresh fetch on the next query.
- **Timing**: This invalidation must happen synchronously BEFORE returning from the worker's sweep, not as a background task.

### 3.4 Seeded-PG Smoke with Quota Flag ON

**Issue (P6 discovery)**: SQLite in-process testing missed a PG lock convoy when multiple projects escalate simultaneously. Seeded-PG smoke with `CCDASH_AAR_ESCALATION_QUOTA_ENABLED=true` caught it.

**Hardening Task**:
- [ ] **Seeded-PG smoke test**: Run the full `npm run docker:hosted:smoke:seeded-pg` suite with `CCDASH_AAR_ESCALATION_QUOTA_ENABLED=true` (flag added in P4).
- [ ] **Multi-project scenario**: The smoke must include ≥2 projects triggering escalations simultaneously. Verify no lock conveyor and all escalations are correctly scoped.
- [ ] **Pass/fail**: The smoke PASSES if all 5-quota limits are enforced per-project without lock convoys, and FAILS if any escalation is silently dropped or over-counted.

### 3.5 Coalescing Guard Posture Decision

**Issue (P6 decision point)**: The `(project_id, trigger)` coalescing guard (existing, used by sync/watcher) can be reused by the autonomous worker to avoid duplicate escalation runs. However, the question remains: is coalescing per-instance or shared?

**Hardening Task** (Design Decision Required):
- [ ] **Document the chosen posture**:
  - **Option A (Per-Instance)**: Each worker instance (dev, staging, production) maintains its own coalescing guard. Sync runs in one environment do not block escalation runs in another. Simpler, isolated.
  - **Option B (Shared via DB)**: Coalescing is tracked in the `escalation_ledger` table, shared across all instances. Prevents a dev/staging sweep from re-triaging the same AAR while prod is still processing. More robust for multi-instance deployments.
- [ ] **Recommend**: Option A for P4 (simpler, matches existing per-worker pattern). Promote to Option B if multi-instance production deployment is observed.

---

## Escalation Quota Behavior

### 4.1 Quota Consumption

**Consumption events**:
1. A triage verdict is `deep_review_recommended` (correlation.confidence ≥ 0.64 + at least one `severity: high` flag)
2. The escalation-quota check is performed: `current_escalations_in_window(project_id) < QUOTA`
3. If under quota: escalation is handed off to `op` immediately; quota counter increments
4. If at/over quota: escalation is logged and queued in `escalation_ledger` with `state: pending_quota`; no call to `op` is made

**Non-consuming events**:
- `triage_verdict: surface_only` — no escalation, quota untouched
- `triage_verdict: human_triage_required` (confidence < 0.64) — escalated immediately to human operator (not queued), quota untouched
- Self-exclusion (Guard 1, provenance self-exclusion) — AAR is not triaged; quota untouched

### 4.2 Quota Window Rolling

```python
# Pseudocode
def check_escalation_quota(project_id: str) -> bool:
    now = utcnow()
    window_start = now - timedelta(hours=CCDASH_AAR_ESCALATION_WINDOW_HOURS)
    
    # Count escalations in the current rolling window
    escalations_in_window = escalation_ledger.count(
        project_id=project_id,
        escalated_at__gte=window_start
    )
    
    # Check quota
    under_quota = escalations_in_window < CCDASH_AAR_ESCALATION_QUOTA
    return under_quota
```

**Example timeline** (quota = 5 per 24h):
- Hour 0: escalations [1, 2, 3, 4, 5] at times 0:00, 2:00, 4:00, 6:00, 8:00
- Hour 12: 6th escalation attempted → rejected, queued as pending
- Hour 24: window rolls; escalation [1] from hour 0 is now outside the window
- Hour 24 + ε: 6th escalation is retried, passes quota check (only [2, 3, 4, 5] remain in window)

### 4.3 Pending Escalations & Retry

**State machine**:
```
triage_verdict: deep_review_recommended
  ↓
  Check quota
  ├─ Under quota → hand off to op immediately (state: escalated)
  └─ At/over quota → queue in escalation_ledger (state: pending_quota)
         ↓
      (daily retry loop)
      Check quota again
      ├─ Under quota → hand off to op (state: escalated)
      └─ At/over quota → remain pending; retry next cycle
         ↓
      (if pending_ttl expires)
      → state: pending_expired; log warning; do not retry
```

**Retry policy**:
- Pending escalations are retried once per quota window (e.g., daily at a fixed hour)
- If pending TTL expires (default 7 days), the escalation is marked `pending_expired` and never retried
- Operator can manually promote a pending escalation via CLI: `ccdash-cli escalation-ledger approve --id <eid>`

---

## Signals for Quota Revision

**Monitor these metrics (P4 onwards)**:

| Signal | Current Observed | Action Trigger | Recommended Change |
|--------|---------|-----------------|-------------------|
| Quota exhaustion rate | 0% (unobserved in dev) | Consistently hitting 4–5 per day (quota spent every day) | Increase `QUOTA` by 50% or reduce `WINDOW_HOURS` to allow higher daily rate |
| Pending escalation backlog | 0 (unobserved) | >10 pending escalations remain in queue after one week | Increase `QUOTA` or investigate false-positive flags causing volume spike |
| Escalation churn (re-escalations of same AAR) | 0 (guard 2 prevents dups) | Operator reports seeing the same AAR multiple times in review queue | Increase `PENDING_TTL` to allow dedup ledger to settle before retry |
| Missed escalations (quota denial) | 0% | Operators report "I expected to see AAR X but it didn't escalate" + logs show it was quota-rejected | Review the triage verdict and flags; consider if the verdict should be `human_triage_required` instead of queued |

**Decision rules**:
- If quota exhaustion is chronic (daily, for ≥2 weeks), increase quota by 25% and re-monitor for ≥1 week
- If quota is never touched (0% exhaustion for ≥1 month), document as over-conservative and consider reducing to save operational toil
- If pending backlog grows unbounded (>100 pending after 14 days), escalate to CCDash maintainer — indicates a fundamental flag-tuning or `op`-side dispatch issue

---

## Implementation in P4

### 5.1 Code Changes

**New files/modules**:
- `backend/db/repositories/escalation_ledger.py` — CRUD for escalation quota tracking
- `backend/db/sqlite_migrations.py` / `backend/db/postgres_migrations.py` — new `escalation_ledger` table (per ADR-007: dual DDL, `retry_on_locked`, direct-count assertion test)

**Modified files**:
- `backend/config.py` — new config knobs (`CCDASH_AAR_ESCALATION_QUOTA`, `CCDASH_AAR_ESCALATION_WINDOW_HOURS`, `CCDASH_AAR_ESCALATION_PENDING_TTL_SECONDS`)
- `backend/adapters/jobs/aar_escalation_worker.py` (new) — autonomous worker entrypoint, includes quota check
- `backend/application/services/agent_queries/aar_review.py` — add `escalate_aar` method that checks quota before handing off
- `backend/cli/commands/escalation.py` (new) — operator CLI commands to inspect/manage escalation ledger

### 5.2 Testing

**Unit tests**:
- [ ] Quota-check logic (under, at, over quota states)
- [ ] Rolling window calculation (window moves correctly as time passes)
- [ ] Per-project isolation (escalations in project-A don't count toward project-B quota)

**Integration tests** (P4 exit criteria):
- [ ] Seeded-PG smoke with `ENABLED=true` and multi-project concurrent escalations
- [ ] Verify pending escalations are retried correctly after window rolls
- [ ] Verify pending-TTL expiration is honored

---

## Acceptance Criteria

- [ ] `CCDASH_AAR_ESCALATION_QUOTA` and `CCDASH_AAR_ESCALATION_WINDOW_HOURS` environment variables are read and logged at startup
- [ ] Before any escalation handoff, quota is checked; at-quota escalations are queued and logged (no silent drops)
- [ ] `escalation_ledger` table ships with dual SQLite+PostgreSQL DDL, includes `retry_on_locked` error handling, and has a direct-count assertion test
- [ ] Seeded-PG smoke passes with the flag enabled and multi-project load
- [ ] Pre-production hardening checklist (§3) passes or is explicitly deferred with a PRD amendment reason
- [ ] Quota knobs are documented in `docs/guides/aar-escalation-quota-tuning.md` with examples

---

## References

- **PRD §8.1**: Self-recursion Guard 3 (escalation quota)
- **PRD §12**: Risk table — "Unbounded cost from auto-escalation"
- **ADR-007**: DB write-path compliance (`retry_on_locked`, dual DDL, assertion tests)
- **ADR-010**: Multi-project scoping via `AuthContext`
- **P6 integration milestone**: where escalation quota was operationally resolved

---

## Status & Next Steps

**Status**: SHAPING (ready for P4 implementation plan review)

**Next Steps**:
1. Review and approve the default quota (5 per 24h, per-project)
2. Confirm pre-production hardening checklist items are assigned to P4 tasks
3. Draft `backend/db/repositories/escalation_ledger.py` and test suite
4. Update seeded-PG smoke to include `CCDASH_AAR_ESCALATION_QUOTA_ENABLED=true`
