---
title: "CCDash Core Remediation — Execution-Time Findings"
doc_type: worknote
created: 2026-06-11
feature_slug: ccdash-core-remediation
findings_for: docs/project_plans/implementation_plans/enhancements/ccdash-core-remediation-v1.md
---

# CCDash Core Remediation — Execution-Time Findings

Lazy-created per the plan's In-Flight Findings policy. New findings surfaced during
wave execution are recorded here; load-bearing ones get a design-spec row in Phase 12.

## F-001 — Pre-existing FK-fixture failures in session-repository test suites (Phase 0)

**Discovered**: Phase 0 (Wave 1), 2026-06-11.
**Severity**: Low (pre-existing; not a Phase 0 regression).
**Status**: Open — not in Phase 0 scope; do not attribute to cross-project work.

Four tests fail with `sqlite3.IntegrityError: FOREIGN KEY constraint failed`, reproducing
**identically on the clean baseline `25b53e1`** (verified via `git stash -u` + re-run) and
with Phase 0 changes — i.e. **zero regression introduced by Phase 0**:

- `backend/tests/test_sessions_repository_filters.py::SessionRepositoryFilterTests::test_session_detail_logs_are_limited_and_offsettable`
- `backend/tests/test_session_intelligence_repository.py::SessionIntelligenceRepositoryTests::test_replace_session_code_churn_facts_round_trips`
- `backend/tests/test_session_intelligence_repository.py::...::test_replace_session_scope_drift_facts_round_trips`
- `backend/tests/test_session_intelligence_repository.py::...::test_replace_session_sentiment_facts_replaces_existing_rows`

**Root cause (hypothesis)**: fixtures insert child rows (logs / intelligence facts) with
`project_id=""` while the parent `sessions` row is seeded under a different `project_id`;
the composite FK `(project_id, session_id)` then fails. Likely a fixture-seeding bug, not a
product bug — but Phases 1/5 extend session-intelligence storage and should fix these fixtures
(or confirm the FK behavior is intended) before adding rows on top.

**Trigger for promotion**: if Phase 1 (`session_detail` service) or Phase 5 (detection columns)
touch these suites, fix the fixtures in-flight and add a design-spec note at Phase 12.

## F-002 — `test_runtime_bootstrap.py` segfaults at pytest collection in this env

**Discovered**: Phase 0 (Wave 1).
**Severity**: Low (env/tooling, not product).
**Status**: Open — consistent with user-memory hazard ("test_runtime_bootstrap hangs/segfaults
with dev server up"). Confirmed pre-existing at baseline `25b53e1`. Excluded from the Phase 0
regression set; not caused by Phase 0.

## F-003 — `ac-coverage-report.py` does not parse nested-list `verified_by` in phase-spec ACs

**Discovered**: Phase 0 (Wave 1).
**Severity**: Low (tooling/format mismatch; no real coverage gap).
**Status**: Open.

The phase-0 spec authors AC `verified_by` as nested YAML lists, e.g.:

```yaml
- verified_by:
    - T0-005
    - T0-006
```

`ac-coverage-report.py` reports all four ACs as "uncovered" against this structure, even though
each AC is substantively covered by a passing verification task (see phase-0-completion.md
AC→task→test map). Either the phase-spec AC blocks should use inline `verified_by: [T0-005, T0-006]`,
or the script should learn the nested-list form. Tracking for a later doc-tooling cleanup.

---

## F-W3-001: AC 8.2 prose overclaims cross-trigger sync coalescing (non-blocking)

**Status**: Open (recommend doc-only fix at Phase 12).
**Surfaced**: Wave 3 validator gate (P8), 2026-06-11. **Severity**: Low (correctness-safe; prose/impl divergence).

Phase 8 AC 8.2 resilience prose says a coinciding *watcher* event and *reconcile* tick for the same
project "coalesce via the Phase 7 guard (no double-scan)." In implementation, the Phase 7 guard
`_sync_in_flight` keys on `(project_id, trigger)`. Watcher dispatches `trigger="watcher"`, reconcile
dispatches `trigger="reconcile"` — so the two do NOT coalesce against each other; only same-trigger
dispatches deduplicate.

Safe because upserts are idempotent (`ON CONFLICT(project_id, id)`), run through `retry_on_locked`,
and `context_window` uses `COALESCE(excluded, existing)`. A rare same-project watcher+reconcile overlap
performs at most one redundant idempotent pass — never a correctness fault. The binding requirement
("reconcile dispatches go through the guard; no double-scan reintroduced") is fully met.

Promotion options: (1) tighten AC 8.2 prose to scope coalescing to same-trigger dispatches [recommended, Phase 12];
(2) widen guard key to `(project_id)` only if redundant cross-trigger passes become measurable load [deferred, YAGNI].

## F-W3-002: test_sync_all_projects.py emits 3 unawaited-coroutine RuntimeWarnings (test hygiene)

**Status**: Open (trivial). Tests pass (21/21 P8 suite); setup doesn't cleanly await `adapter.start()`.
Tidy-up in a future pass; not load-bearing.

## F-W6-001: Correlation-tab "Observed Workload" multi-feature session over-count (out of scope)

**Status**: Open (deferred — NOT a Phase 12 deliverable). **Surfaced**: T12-006 audit, 2026-06-12. **Severity**: Low/Med (display over-count, not a data-integrity fault).

The T12-006 audit (AC R12.6) confirmed the audited per-lifecycle-event in+out sum at `backend/routers/analytics.py` (≈ line 553/570, `session_metrics().total_tokens`) is **NOT** surfaced as a workload/total metric in any panel — that key is never accessed; aggregation loops read `token_input`/`token_output` separately into deduplicated per-dimension buckets. **AC R12.6 = PASS.**

Tangential discovery (distinct code path, NOT caused by the audited line): the **Correlation tab "Observed Workload" MetricCard** (`components/Analytics/AnalyticsDashboard.tsx` ≈ line 1142) sources `correlationSummary.totalTokens` from `/analytics/correlation` (`_session_usage_metrics` over session rows). A session linked to multiple features appears to be counted once per feature, producing a multi-feature over-count in that summary total.

**Why deferred**: Phase 12 is docs/close-out; the token-undercount remediation was explicitly out of scope (shipped 2026-03-09). This is a separate over-count in the correlation path. Promotion trigger: when correlation-tab token totals are used for billing/quota or operators report inflated numbers. Owner: analytics. No fix applied in Wave 6.
