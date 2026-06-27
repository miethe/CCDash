---
schema_version: 1
doc_type: decisions_block
title: "Decisions Block: CCDash DB Design Remediation"
description: "High-level planning scaffold for the Tier 3 DB design remediation: phase boundaries, risk mapping, agent routing, and model routing. Expanded by implementation-planner into a PRD + Implementation Plan."
created: 2026-06-03
updated: 2026-06-03
feature_slug: "ccdash-db-design-remediation"
estimated_points: "~40 (Tier 3)"
tier: "3"
related_feature_prd: "docs/project_plans/PRDs/infrastructure/ccdash-db-design-remediation-v1.md (to be authored)"
spike_findings_ref: "docs/dev/architecture/spikes/findings/ccdash-db-design-remediation-findings.md"
spike_charter_ref: "docs/dev/architecture/spikes/charters/ccdash-db-design-remediation-charter.md"
ratified_decisions:
  - "ADR-006 = Option B: DB-authoritative project registry; projects.json is import-seed + export/backup only (ratified by operator 2026-06-03)."
  - "ADR-007 = DB-write failure-surfacing standard (accepted as design constraint)."
references_not_owned:
  - "docs/project_plans/PRDs/infrastructure/ccdash-enterprise-liveness-storage-v1.md — owns the destructive multi-GB storage reclaim (session_logs drop, telemetry bounding). This plan REFERENCES, does not duplicate."
---

# Decisions Block: CCDash DB Design Remediation

**Feature Goal**: Bring every CCDash DB design up to spec and provably functioning as intended — fix the silent project-registry persistence failure (DB-authoritative per ADR-006), standardize DB-write reliability + observability (ADR-007), close migration concurrency/parity/ledger gaps, and activate the dormant storage-retention subsystem — without coupling the small reversible registry fix to the slow destructive storage reclaim.

**This Decisions Block** captures phase boundaries, agent routing, risk hotspots, estimation anchors, and model routing, grounded in the SPIKE findings (11 findings S0–S3, conditional-GO). `implementation-planner` (sonnet) expands it into the full PRD + Implementation Plan. Source-of-truth for findings/evidence is the spike findings doc; do not re-investigate.

---

## 1. Phase Boundaries

The work product changes shape four times: registry correctness → reliability/observability foundation → migration integrity → storage hygiene → docs. P0 (Phase 1) is deliberately isolated so it ships first, independently, and reversibly (SPIKE precondition #2).

| Phase | Name | Scope | Success Criteria | Exit Gate |
|-------|------|-------|------------------|-----------|
| P1 | Registry Correctness & Authority (ADR-006) | F-01 fail-loud bootstrap + local locked-retry + `busy_timeout`; sequence bootstrap outside the heavy startup-sync window; collapse to single DB-authoritative manager, demote legacy `ProjectManager` to `import_from_json()`, add `export_to_json()`; F-10 dead `config.DB_PATH` cleanup. Backlog: P0-1..P0-5, F-10. | Registry rows persist across a real restart, asserted by direct `SqliteProjectRepository.count()`; lock-injection test reproduces old F-01 and proves fail-loud/retry (never silent True); UI shows all projects after cold boot. | Lock-injection + direct-count tests green; **runtime smoke**: cold-start dev server, `/api/projects` returns full set, table non-empty; no startup regression. |
| P2 | DB-Write Reliability & Observability Standard (ADR-007) | Generalize one locked-retry helper in `repositories/base.py` (from `execution.py:_commit_with_retry`); apply to registry + sync `sessions.py` helpers; ensure every independent sync connection issues `PRAGMA busy_timeout`. `/api/health/detail` gains `registry.project_count`, `registry.last_flush_status`, `db.size_bytes`, `db.freelist_bytes`, `retention.last_run`; emit `ccdash_db_write_failures_total{repo,reason}`. Backlog: P1-4, P3-1, P3-2. | Helper covers all sync writers; health fields present + asserted; counter increments under injected failure. | New health-field tests + counter test green; **runtime smoke**: `/api/health/detail` shows registry+db gauges. |
| P3 | Migration Integrity & Parity | SQLite first-boot concurrency guard (flock/inter-process mutex mirroring PG advisory lock); column/constraint-level parity diff in `migration_governance` + test; make `ensure_table` safety-nets call canonical migration DDL (single source) or delete after P1 ordering guarantees migrations-first; migration idempotency-on-rerun + concurrency tests; per-version migration ledger. Backlog: P1-1, P1-2, P1-3, P3-3, P3-4. | Two concurrent `run_migrations` on one SQLite file is safe; column-parity test passes for all shared tables; `run_migrations` twice on a populated DB is a no-op. | Concurrency + idempotency + column-parity tests green on both backends. |
| P4 | Storage Hygiene Activation | Enable `RETENTION_PRUNE_ENABLED` (snapshot-first, flag-gated); one-time `VACUUM` runbook to reclaim 2.23 GB freelist; document WAL-checkpoint strategy. REFERENCE liveness PRD for `session_logs` dedupe/drop + `telemetry_events` bounding (do not own). Backlog: P2-1 (+ P2-2/P2-3 referenced). | Retention prune runs behind flag and prunes past TTL; VACUUM runbook validated on a DB snapshot; freelist reclaim verified; no data loss vs snapshot. | Prune-then-COUNT boundary test; VACUUM reclaim verified on snapshot copy (NOT live first); operator runbook reviewed. |
| P5 | Docs, Conventions & Deferred Items | Ratify ADR-006/007 as accepted ADR files; CLAUDE.md DB-write/registry conventions; design specs for any deferred items surfaced during execution; AAR. Backlog: DOC. | ADRs accepted; conventions documented; deferred items captured. | Docs merged; `karen` end-of-feature review clean. |

**Boundary Rationale**:
- **P1↔P2**: P1 ships the minimal reversible live-bug fix (local retry) fast and independently per SPIKE precondition #2; P2 *generalizes* that into the shared helper + observability standard. Splitting keeps P1 small and shippable before any cross-cutting refactor.
- **P2↔P3**: P2 is the runtime write-path reliability layer; P3 is the *build-time/migration* integrity layer — different surfaces, different reviewers, parallelizable after P1.
- **P3↔P4**: P3 is non-destructive code/test work; P4 touches the live 11 GB DB destructively and demands snapshot protection + ops care (different risk profile, SPIKE precondition #1). P4 must not start before P1 is verified.
- **P4↔P5**: P5 is documentation/ratification + deferred-item capture, naturally last.

---

## 2. Agent Routing

| Phase | Primary Agent(s) | Secondary Agent | Notes |
|-------|------------------|-----------------|-------|
| P1 | data-layer-expert (sqlite registry, retry, ordering) | python-backend-engineer (manager collapse, export/import, config) | ADR-006 implementation; reviewer pass mandatory. |
| P2 | python-backend-engineer (helper, health fields, counter) | data-layer-expert (apply helper to sync repos) | Touches `repositories/base.py` + `runtime/bootstrap.py` + observability. |
| P3 | data-layer-expert (migrations, parity governance, ensure_table) | — | Single-owner migration surface; column-parity diff is the meaty part. |
| P4 | platform-engineer (VACUUM/retention runbook, ops) | data-layer-expert (retention prune boundaries) | Snapshot-first; coordinate with liveness PRD owners. |
| P5 | documentation-writer (haiku) | — | ADR files, CLAUDE.md, AAR. |

**Parallel Opportunities**:
- P3 and P4 can run in parallel after P1 verifies (independent surfaces), but P4 needs an operator-confirmed DB snapshot first.
- P1 → P2 must sequence (P2 generalizes P1's retry).
- Reviewer gate per phase: `senior-code-reviewer` + `task-completion-validator`; `karen` at feature end (Tier 3 also surfaces milestone `karen` checkpoints after P1 and P3).

---

## 3. Risk Hotspots

### Risk 1: Destructive ops on the live 11 GB DB (P4)
- **Severity**: high
- **Rationale**: VACUUM/retention-prune on a 11 GB live file under WAL can lock for minutes and is hard to reverse if mis-scoped; the 10 GB `.bak` shows prior caution.
- **Mitigation**: SPIKE precondition #1 — snapshot-before-touch, flag-gated, validate VACUUM on a snapshot copy first, never the live DB un-snapshotted. Destructive `session_logs`/`telemetry` items stay owned by the liveness PRD; P4 only activates the already-built retention subsystem.

### Risk 2: Registry startup-ordering change regresses boot (P1)
- **Severity**: medium
- **Rationale**: Moving the registry bootstrap out of the sync window (P0-3) alters startup sequencing in `container.py`; a wrong order could break project-binding for the worker or delay readiness.
- **Mitigation**: Mandatory runtime smoke gate (cold-start api + worker; assert `/api/projects` and worker binding); keep the change behind clear sequencing with a fallback to lazy-on-first-request.

### Risk 3: SQLite migration concurrency guard deadlocks dual-process boot (P3)
- **Severity**: medium
- **Rationale**: api + worker both may run `run_migrations` on boot; a naive flock could serialize or deadlock startup.
- **Mitigation**: Mirror the PG advisory-lock *intent* (acquire → migrate → release, with timeout + skip-if-already-current); test concurrent boot of both profiles.

### Risk 4: Column-parity governance surfaces real existing drift (P3)
- **Severity**: medium
- **Rationale**: The new column/constraint diff (F-05) may reveal genuine sqlite↔postgres divergences, expanding scope mid-phase.
- **Mitigation**: On first real drift, record to the lazy findings doc and triage: fix in-phase if small, else split a follow-up. Do not let parity discovery balloon P3.

### Risk 5: Collapsing dual managers breaks explicit-JSON-manager callers (P1)
- **Severity**: low
- **Rationale**: `build_workspace_registry` accepts an explicit `manager=` (JSON) override; tests or call-sites may rely on it.
- **Mitigation**: Grep all callers before retiring; preserve `import_from_json()`/`export_to_json()` and keep the override path test-only or remove its prod uses deliberately.

---

## 4. Estimation Anchors

### Total: ~40 points (Tier 3)

| Phase | Points | Reasoning Anchor |
|-------|--------|------------------|
| P1 | 11 | Bounded sync-path fix + manager collapse + tests. Anchor: original P3-001 registry build was comparable; here the code is small, the design (ADR-006) is settled. |
| P2 | 8 | Shared helper extraction + health fields + counter. Anchor: prior observability/health additions (system-wide-metrics health surfacing). |
| P3 | 13 | Migration concurrency guard + column-parity diff + 3 test classes + ledger. Anchor: `migration_governance` table-set work; column diff is the new heavy lift. |
| P4 | 5 | Mostly activating an existing subsystem + a runbook; destructive items are liveness-owned. |
| P5 | 3 | ADR files + CLAUDE.md + AAR (haiku). |

**Estimation Notes**:
- P1 is the only phase with live-bug urgency; treat as shippable on its own even if P2–P5 slip.
- P3 carries the largest unknown (Risk 4 drift discovery) — its 13 pts assume modest existing drift.
- P4 marginal new work is small precisely because the liveness PRD owns the destructive reclaim.

---

## 5. Dependency Map

```
ADR-006 (ratified) ──gates──> P1 (Registry Correctness)  [ships first, independent, reversible]
                                   │
                                   ├──> P2 (Reliability + Observability)   [generalizes P1 retry]
                                   │
                                   ├──> P3 (Migration Integrity)           [parallel w/ P4 after P1]
                                   │
                                   └──> P4 (Storage Hygiene)               [needs DB snapshot; parallel w/ P3]
                                                 │
P2 + P3 + P4 ──────────────────────────────────> P5 (Docs / ADRs / AAR)
```

- **Hard gate**: ADR-006 ratified → P1 may proceed (satisfied).
- **Sequence**: P1 → P2.
- **Parallel after P1**: P3 ∥ P4 (P4 blocked on operator snapshot confirmation).
- **Converge**: P5 after P2/P3/P4.
- **External reference (not a blocker, coordinate)**: enterprise-liveness PRD owns P4's destructive `session_logs`/`telemetry` reclaim.

---

## 6. Model Routing per Phase

| Phase | Model | Why |
|-------|-------|-----|
| P1 | Sonnet (impl) + Opus (ADR-006 conformance review) | Authority-model change warrants an Opus sanity review of the manager-collapse seam. |
| P2 | Sonnet | Mechanical-but-careful refactor + observability wiring. |
| P3 | Sonnet | Migration/parity logic; data-layer-expert domain. |
| P4 | Sonnet (impl) + Opus (go/no-go on live-DB destructive step) | Opus confirms snapshot + scope before any live VACUUM/prune. |
| P5 | Haiku | Documentation. |

**Cross-cutting**: `task-completion-validator` (Sonnet) per phase; `karen` (Opus) after P1, after P3, and at feature end. Findings doc is lazy — `findings_doc_ref: null` until first execution finding.
