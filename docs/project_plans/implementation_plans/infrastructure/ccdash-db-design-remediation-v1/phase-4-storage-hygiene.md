---
schema_version: 2
doc_type: phase_plan
title: "P4 — Storage Hygiene Activation"
status: draft
created: 2026-06-03
updated: 2026-06-03
phase: 4
phase_title: "Storage Hygiene Activation"
feature_slug: ccdash-db-design-remediation
prd_ref: docs/project_plans/PRDs/infrastructure/ccdash-db-design-remediation-v1.md
plan_ref: docs/project_plans/implementation_plans/infrastructure/ccdash-db-design-remediation-v1.md
---

# Phase 4 — Storage Hygiene Activation (~5 pts)

**Parent Plan**: `docs/project_plans/implementation_plans/infrastructure/ccdash-db-design-remediation-v1.md`

**Dependencies**: P1 verified (registry correctness confirmed; live DB no longer in startup-contention failure mode). Operator DB snapshot confirmed before any live-DB step.
**Assigned Subagent(s)**: platform-engineer (primary — VACUUM/retention runbook, ops); data-layer-expert (secondary — retention prune boundaries)
**Model**: sonnet (implementation); Opus go/no-go on live-DB destructive step (VACUUM / retention enable)
**Reviewer Gates**: task-completion-validator at exit; Opus sign-off before any live-DB action

## Entry Criteria (Mandatory — Phase 4 Gate)

Both preconditions must be confirmed in writing before any code execution:

1. **Operator DB snapshot confirmed**: Operator has created a restorable snapshot of `data/ccdash_cache.db` (and verified it is restorable). This must be documented with a timestamp in the progress file.
2. **P1 cold-start smoke passed**: T1-010 must have passed, confirming the registry is no longer in contention-failure mode (reduces risk of lock conflicts during VACUUM).

If either precondition is unconfirmed, Phase 4 must wait. Phase 3 may proceed in parallel without P4.

## Background (file:line anchors)

| File | Lines | Subject |
|------|-------|---------|
| `backend/config.py` | 1079 | `RETENTION_PRUNE_ENABLED = False` (F-03) |
| `backend/config.py` | 1074–1102 | Full retention config block |
| `backend/adapters/jobs/runtime.py` | 1394–1418 | Retention prune job; early-returns `None` when disabled |
| Live DB | — | `freelist_count=543,926` (2.23 GB), `auto_vacuum=0`, `journal_mode=wal` |
| Liveness PRD | — | `docs/project_plans/PRDs/infrastructure/ccdash-enterprise-liveness-storage-v1.md` — owns `session_logs` drop and `telemetry_events` bounding |

## Scope Boundary (Critical)

P4 owns:
- (a) Activating `RETENTION_PRUNE_ENABLED` behind its existing flag (snapshot-first)
- (b) One-time VACUUM runbook validated on a snapshot copy

P4 does NOT own (liveness PRD owns):
- `session_logs` dedupe/drop — liveness PRD `P1-002/016`
- `telemetry_events` bounded growth implementation — liveness PRD P1

P4 tasks (c) P2-2 and P2-3 from the SPIKE backlog are "reference only": P4 verifies the liveness PRD jobs are enabled but does not re-implement them.

## Task Table

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|-------|--------|--------------|
| T4-001 | Retention prune boundary test | In a test environment using a seeded DB copy (not the live DB): set `RETENTION_PRUNE_ENABLED=true`, configure `ANALYTICS_RETENTION_DAYS=90` and `TELEMETRY_RETENTION_DAYS=90`, run the retention job from `adapters/jobs/runtime.py:1394–1418`. Assert that rows older than the TTL are pruned and rows within TTL are preserved. | Test `test_retention_prune_boundary` passes: rows past TTL removed, rows within TTL present; no data loss for active records | 2 pts | data-layer-expert | sonnet | adaptive | P1 verified |
| T4-002 | VACUUM runbook creation and snapshot validation | Create `docs/guides/db-vacuum-runbook.md` documenting: (a) pre-VACUUM snapshot procedure (operator must run `cp data/ccdash_cache.db data/ccdash_cache_$(date +%Y%m%d).db.bak` and verify size); (b) VACUUM execution command (`sqlite3 data/ccdash_cache.db "VACUUM;"`); (c) post-VACUUM verification (assert `PRAGMA freelist_count < 1000`); (d) WAL-checkpoint strategy (decision from OQ-02: either `PRAGMA wal_autocheckpoint=N` or retention-job checkpoint — document the chosen approach); (e) rollback procedure (restore from snapshot). Validate the runbook by executing all steps against a DB snapshot copy (NEVER the live DB without operator sign-off). | Runbook doc exists at `docs/guides/db-vacuum-runbook.md`; VACUUM validated on snapshot copy: `freelist_count` drops to near-zero (< 1,000 pages); row counts for `session_messages`, `sessions`, `projects` match pre-VACUUM snapshot; no data loss | 1 pt | platform-engineer | sonnet | adaptive | T4-001, operator snapshot confirmed |
| T4-003 | Opus live-DB go/no-go gate | Before running any command on the live `data/ccdash_cache.db`: present the runbook to Opus for a go/no-go decision. Opus must confirm: (a) snapshot is confirmed restorable, (b) VACUUM was validated on snapshot copy (T4-002), (c) P1 cold-start smoke passed. If Opus approves, proceed. If Opus declines, document the reason and escalate to operator. | Written go/no-go decision recorded in the phase progress file; no live-DB VACUUM or retention-enable executed without this approval | 0.5 pts | platform-engineer | opus | extended | T4-002 |
| T4-004 | Enable RETENTION_PRUNE_ENABLED on live DB | After T4-003 Opus approval: set `RETENTION_PRUNE_ENABLED=true` in the operator's environment config (`.env` or `CCDASH_*` env var). Document in the runbook. Do NOT flip the default in `config.py` (keep the default `False` to protect fresh installs). | Operator environment has `RETENTION_PRUNE_ENABLED=true`; retention job runs on next worker cycle and does not error; `retention.last_run` appears in `/api/health/detail` within one worker cycle | 0.5 pts | platform-engineer | sonnet | adaptive | T4-003 |
| T4-005 | Liveness PRD cross-reference verification | Verify (read-only) that the liveness PRD's `session_logs` drop job and `telemetry_events` retention jobs are configured or noted as pending. Add a comment in the runbook noting the cross-reference. Do not implement these jobs. | Runbook contains explicit cross-reference to liveness PRD `P1-002/016`; a note states which liveness PRD jobs need to run to achieve full storage reclaim | 0.5 pts | platform-engineer | sonnet | adaptive | T4-002 |
| T4-006 | P4 VACUUM snapshot smoke | After T4-003 approval and T4-004 execution: run the VACUUM on the live DB per the runbook. Verify `PRAGMA freelist_count` drops significantly (target: <1,000 pages). Confirm `SELECT COUNT(*) FROM sessions` and `SELECT COUNT(*) FROM projects` match pre-VACUUM values. | Post-VACUUM: `freelist_count < 1,000`; session and project row counts match pre-VACUUM snapshot; no data loss; runbook step executed and documented | 0.5 pts | platform-engineer | sonnet | adaptive | T4-003, T4-004 |

**Phase total: ~5 pts**

## Acceptance Criteria Traceability

| AC | Task(s) | Notes |
|----|---------|-------|
| AC-009a: Retention prune runs behind flag | T4-001, T4-004 | Boundary test + live enable |
| AC-009b: VACUUM runbook validated on snapshot | T4-002, T4-006 | Runbook + smoke |

## Phase 4 Quality Gates

- [ ] MANDATORY GATE: Operator snapshot confirmed (timestamped in progress file) — no tasks execute before this
- [ ] MANDATORY GATE: P1 cold-start smoke (T1-010) confirmed passed
- [ ] T4-001 retention prune boundary test passes on seeded DB copy
- [ ] T4-002 VACUUM runbook exists at `docs/guides/db-vacuum-runbook.md`; VACUUM validated on snapshot (freelist near-zero, no data loss)
- [ ] T4-003 Opus go/no-go approval recorded in progress file before any live-DB action
- [ ] T4-004 `RETENTION_PRUNE_ENABLED=true` in operator environment; `retention.last_run` present in health
- [ ] T4-005 runbook cross-references liveness PRD for `session_logs`/`telemetry_events` reclaim
- [ ] T4-006 live DB VACUUM completed; `freelist_count < 1,000`; row counts verified; no data loss
- [ ] task-completion-validator sign-off
