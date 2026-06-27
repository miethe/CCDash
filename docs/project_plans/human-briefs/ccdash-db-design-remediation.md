---
schema_name: ccdash_document
schema_version: 2

doc_type: human_brief
doc_subtype: feature_brief
root_kind: project_plans

id: BRIEF-ccdash-db-design-remediation
title: "CCDash DB Design Remediation — Human Brief"
status: draft
category: human-briefs

feature_slug: ccdash-db-design-remediation
feature_family: ccdash-db-design-remediation
feature_version: v1

prd_ref: docs/project_plans/PRDs/infrastructure/ccdash-db-design-remediation-v1.md
plan_ref: docs/project_plans/implementation_plans/infrastructure/ccdash-db-design-remediation-v1.md
intent_ref: null
epic_ref: null

related_documents:
  - docs/dev/architecture/spikes/findings/ccdash-db-design-remediation-findings.md
  - docs/dev/architecture/spikes/charters/ccdash-db-design-remediation-charter.md
  - .claude/worknotes/ccdash-db-design-remediation/decisions-block.md
  - docs/project_plans/adrs/adr-006-db-authoritative-project-registry.md
  - docs/project_plans/adrs/adr-007-db-write-failure-surfacing-standard.md
  - docs/project_plans/PRDs/infrastructure/ccdash-enterprise-liveness-storage-v1.md

owner: Nick Miethe
contributors: []

audience: [humans]

priority: high
confidence: 0.85

created: 2026-06-03
updated: 2026-06-03
target_release: ""

tags: [human-brief, database, infrastructure, remediation]
---

# CCDash DB Design Remediation — Human Brief

> Living document for human orchestrators. Agents: do not load unless explicitly instructed.
> Status: draft | Updated: 2026-06-03

---

## 1. Context Pointers

- **PRD**: `docs/project_plans/PRDs/infrastructure/ccdash-db-design-remediation-v1.md`
- **Plan**: `docs/project_plans/implementation_plans/infrastructure/ccdash-db-design-remediation-v1.md`
- **Phase Files**: `docs/project_plans/implementation_plans/infrastructure/ccdash-db-design-remediation-v1/phase-{1..5}-*.md`
- **SPIKE Findings**: `docs/dev/architecture/spikes/findings/ccdash-db-design-remediation-findings.md`
- **SPIKE Charter**: `docs/dev/architecture/spikes/charters/ccdash-db-design-remediation-charter.md`
- **Decisions Block**: `.claude/worknotes/ccdash-db-design-remediation/decisions-block.md`
- **ADR-006**: `docs/project_plans/adrs/adr-006-db-authoritative-project-registry.md` (ratified 2026-06-03)
- **ADR-007**: `docs/project_plans/adrs/adr-007-db-write-failure-surfacing-standard.md` (accepted 2026-06-03)
- **Liveness PRD** (owns destructive storage reclaim): `docs/project_plans/PRDs/infrastructure/ccdash-enterprise-liveness-storage-v1.md`
- **Related Briefs**: None

---

## 2. Estimation Sanity Check

**Bottom-up total**: ~40 pts / ~4–6 engineer-weeks
**Top-down anchor**: `system-wide-metrics` health surfacing + observability additions (~8 pts, 1 week). This plan is 5× that scope with a much larger risk surface and live-DB destructive step.
**Reconciliation**: The 40 pt estimate is bottoms-up from SPIKE backlog items. The largest phase (P3, 13 pts) carries genuine unknowns in column-parity discovery. The estimate is well-grounded in file:line evidence from the SPIKE — no re-investigation was needed.

H1–H6 heuristic application:

- **H1 (noun-counting)**: 0 new domain nouns introduced. All work is repair and observability on existing tables. H1 does not apply as a floor multiplier — but the new `migrations_applied` ledger table (P3-4) is ~2 pts, which H1 predicts. Verified.

- **H2 (dual-implementation multiplier)**: Partially applies. `SqliteProjectRepository` and `PostgresProjectRepository` both need `ensure_table` elimination (T3-003). Migration governance extends to both backends. The retry helper in `base.py` is shared (single implementation, no multiplier). The migration guard is SQLite-only (Postgres already has `pg_advisory_lock`). Effective dual-impl overhead is ~2 pts absorbed in P3 tasks. No H2 multiplier needed beyond what is already in the task estimates.

- **H3 (algorithmic flag)**: Not triggered. The column-parity diff (T3-002) involves parsing and comparing DDL, which is mechanical text processing. The concurrency guard (T3-001) is a well-understood file-locking pattern with a clear reference implementation (Postgres advisory lock). No SPIKE needed; test scenarios are enumerable.

- **H4 (bundle decomposition)**: Five capability areas bundled. Per-area independent estimates:
  | Area | Independent Estimate |
  |------|---------------------|
  | Registry correctness (P1) | 11 pts |
  | DB-write reliability + observability (P2) | 8 pts |
  | Migration integrity + parity (P3) | 13 pts |
  | Storage hygiene activation (P4) | 5 pts |
  | Docs/ADRs (P5) | 3 pts |
  | **Σ** | **40 pts** |
  Σ = plan total. No compression. H4 satisfied.

- **H5 (anchor reference)**: Closest anchor is the enterprise-liveness-storage P3/P4 observability work (~10 pts, 2 weeks). This plan is 4× that scope because it covers five independent areas including a live 11 GB DB operation. The delta is justified: 5 capability areas, each with dedicated tests. Delta vs anchor: +300%; justified by scope breadth and P3 complexity.

- **H6 (hidden plumbing budget)**: Absorbed into per-task estimates. No new DTOs, DI wiring, or OpenAPI changes. The `migrations_applied` table and `ccdash_db_write_failures_total` counter each have ~0.5 pts of registration/wiring overhead already included in T3-004 and T2-004 respectively. Explicit plumbing line item: ~2 pts (~5% of subtotal). This is below the typical H6 15–20% because there is no new product surface (no new router, no new UI, no new DI factory).

**Locked estimate**: 40 pts. Bottom-up Σ = 40 pts. Top-down anchor check: 4–5× liveness-observability work is consistent with 5 independent capability areas. Estimate is locked at bottom-up.

---

## 3. Wave & Orchestration Notes

**Critical path**: ADR-006 ratified → P1 (registry correctness) → P2 (reliability generalization). P1 is the only phase with live-bug urgency. If P1 slips, P2–P5 all slip. P1 should be treated as an emergency fix and shipped independently if needed.

**Parallel opportunities**: P3 (migration integrity) and P4 (storage hygiene) can run in parallel after P1 verifies. P4 is additionally blocked on operator snapshot confirmation — if that takes time, P3 can proceed independently.

**Merge order**: P1 must merge before P2 (P2 generalizes the P1 local retry into the shared helper). P3 and P4 can be separate PRs merged in any order after P1. P5 must be last.

**Cross-feature coupling**: P4 cross-references the enterprise-liveness-storage PRD. Do not let any P4 task re-implement the `session_logs` drop or `telemetry_events` bounding — those must remain in the liveness PRD. Confirm the liveness PRD owner has not already shipped those items before P4 executes (check `docs/project_plans/PRDs/infrastructure/ccdash-enterprise-liveness-storage-v1.md` status).

---

## 4. Open Questions Ledger

| ID | Source | Question | Status | Resolved By |
|----|--------|----------|--------|-------------|
| OQ-01 | PRD §13 | Should the `migrations_applied` ledger use a shared schema across backends or backend-specific tables? Recommendation: shared. | open | Decide at P3 T3-004 authoring |
| OQ-02 | PRD §13 | WAL-checkpoint strategy: enforce via `PRAGMA wal_autocheckpoint=N` config, or via the retention job? Choosing the retention job means CHECKPOINT only after prune. | open | Decide at P4 T4-002 (VACUUM runbook); document in runbook |

---

## 5. Deferred Items Rationale

- **OQ-01 (migrations_applied schema)**: Deferred because the decision requires understanding both SQLite and Postgres migration structures in context. Promote when P3 T3-004 implementation begins; if the shared-schema recommendation is rejected, a parity design spec will be needed.
- **OQ-02 (WAL-checkpoint strategy)**: Deferred to P4 execution. The VACUUM runbook is the natural home for this decision. If checkpoint is chosen as a separate job, a platform-engineer design spec may be needed.
- **P2-3 (telemetry_events bounded growth)**: Not owned here. Liveness PRD owns this. P4 only verifies the liveness PRD's retention job is configured. If liveness PRD has not shipped, this remains deferred to that plan.

---

## 6. Risk Narrative

**Risk 1 — Live 11 GB DB VACUUM (P4)**: This is the highest-risk step. A VACUUM on an 11 GB WAL DB can lock for minutes and is essentially irreversible without a snapshot. The mitigation (snapshot-first, Opus go/no-go, validate on copy first) is strong, but requires operator discipline. Watch for: operator taking the "it'll be fine" shortcut and skipping the snapshot step. The progress file must show a timestamped snapshot confirmation before any P4 task executes.

**Risk 2 — Bootstrap re-sequencing (P1 T1-003)**: The `container.py` sequencing change is the subtlest P1 task. A wrong order could break the worker's project-binding or cause the health check to return stale data on the first request. The cold-start smoke (T1-010) is the regression guard — do not mark P1 complete without it.

**Risk 3 — Column-parity drift discovery (P3 T3-002)**: The column-parity diff may surface genuine existing SQLite/Postgres divergences. The scope-protection rule is: ≤2 pts of drift fixed in-phase; larger drift becomes a design spec and deferred follow-up. Watch for: the implementer deciding to "fix it while I'm in there" and ballooning P3 beyond 13 pts.

**Risk 4 — Dual-manager collapse breaks existing test infrastructure (P1 T1-004)**: Some tests may rely on passing the JSON-backed `ProjectManager` explicitly. The T1-007 caller-grep audit is the safety net. Watch for: test infrastructure failures after the manager collapse that are not caught until CI runs.

---

## 7. What to Watch For

- P1 T1-003 (bootstrap sequencing): if the worker fails to bind after the sequencing change, check `container.py` line 1203 area and confirm the registry bootstrap is not racing the sync engine startup burst.
- P3 T3-002 (column-parity diff): if the diff returns non-empty on the first run, record the drift before attempting to fix it. Do not attempt to fix drift inline without checking the liveness PRD for ownership overlap.
- P4 operator snapshot: confirm the snapshot is restorable (not just created) before marking the gate as satisfied. A `.bak` file that cannot be restored is not a valid snapshot.
- P5 karen review: this is a Tier 3 end-of-feature review and will be thorough. Ensure all ADR files have `status: accepted` and all CLAUDE.md conventions are in place before scheduling the review.

---

## 8. Expected Success Behaviors

These are human-verifiable post-ship outcomes drawn from the PRD acceptance criteria:

- [ ] Cold boot the dev server from scratch, add a project via the UI, restart the server. The project is still present after restart — no manual DB intervention required.
- [ ] Query `GET /api/health/detail`. The response contains `registry.project_count` (≥ 0), `db.size_bytes` (> 0), and `retention.last_run` (timestamp or null). The CLI `ccdash target check local` exits 0 without a parse error.
- [ ] Inject a lock (hold a write connection open) while the registry flushes. The process logs an ERROR-level message and the test asserts an exception is raised — not a silent `True` return.
- [ ] Run `backend/.venv/bin/python -m pytest backend/tests/test_db_project_registry.py -v`. Both `test_registry_flush_fail_loud` and `test_registry_persistence_direct_count` pass.
- [ ] Run `backend/.venv/bin/python -m pytest backend/tests/test_migration_governance.py -v`. `test_column_parity_all_shared_tables` passes with an empty diff.
- [ ] Check `docs/project_plans/adrs/adr-006-db-authoritative-project-registry.md` — `status: accepted`.
- [ ] Check `docs/project_plans/adrs/adr-007-db-write-failure-surfacing-standard.md` — `status: accepted`.
- [ ] Check CLAUDE.md "Key Conventions" — contains DB-write, registry, and `busy_timeout` convention lines referencing ADR-006/007.
- [ ] Post-VACUUM (P4): `PRAGMA freelist_count` on the live DB is < 1,000 pages (down from 543,926).

---

## 9. Running Log

- [2026-06-03] Brief created. ADR-006 and ADR-007 ratified same day. Plan authored from decisions block.
