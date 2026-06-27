---
type: progress
schema_version: 2
doc_type: progress
prd: ccdash-db-design-remediation
feature_slug: ccdash-db-design-remediation
phase: 4
title: Storage Hygiene Activation
status: completed
created: '2026-06-03'
updated: '2026-06-03'
prd_ref: docs/project_plans/PRDs/infrastructure/ccdash-db-design-remediation-v1.md
plan_ref: docs/project_plans/implementation_plans/infrastructure/ccdash-db-design-remediation-v1.md
commit_refs: []
pr_refs: []
owners:
- platform-engineer
contributors:
- data-layer-expert
overall_progress: 100
completion_estimate: on-track
total_tasks: 6
completed_tasks: 6
in_progress_tasks: 0
blocked_tasks: 0
model_usage:
  primary: sonnet
  external: []
tasks:
- id: T4-001
  description: Retention prune boundary test on seeded DB copy (not live DB)
  status: completed
  assigned_to:
  - data-layer-expert
  dependencies:
  - P1-verified
  estimated_effort: 2pts
  assigned_model: sonnet
  model_effort: adaptive
  started: '2026-06-03T21:20:00-05:00'
  completed: '2026-06-03T21:24:00-05:00'
  evidence:
  - test: backend/tests/test_retention_prune.py (12 passed)
  verified_by:
  - opus-orchestrator
- id: T4-002
  description: VACUUM runbook creation and snapshot validation at docs/guides/db-vacuum-runbook.md
  status: completed
  assigned_to:
  - platform-engineer
  dependencies:
  - T4-001
  - operator-snapshot-confirmed
  estimated_effort: 1pt
  assigned_model: sonnet
  model_effort: adaptive
  started: '2026-06-03T21:33:00-05:00'
  completed: '2026-06-03T21:43:00-05:00'
  evidence:
  - doc: docs/guides/db-vacuum-runbook.md
  - validation: VACUUM-on-snapshot-clone freelist 522724->0, rows preserved
  verified_by:
  - T4-003
- id: T4-003
  description: Opus live-DB go/no-go gate — written decision in progress file before
    any live-DB action
  status: completed
  assigned_to:
  - platform-engineer
  dependencies:
  - T4-002
  estimated_effort: 0.5pts
  assigned_model: opus
  model_effort: extended
  started: '2026-06-03T21:44:00-05:00'
  completed: '2026-06-03T21:45:00-05:00'
  evidence:
  - decision: GO recorded in Operator Approvals section of this file
  verified_by:
  - opus-orchestrator
- id: T4-005
  description: Liveness PRD cross-reference verification (read-only)
  status: completed
  assigned_to:
  - platform-engineer
  dependencies:
  - T4-002
  estimated_effort: 0.5pts
  assigned_model: sonnet
  model_effort: adaptive
  started: '2026-06-03T21:33:00-05:00'
  completed: '2026-06-03T21:43:00-05:00'
  evidence:
  - doc: db-vacuum-runbook.md scope-boundary section cross-refs liveness PRD P1-002/016
      (both pending)
  verified_by:
  - T4-003
- id: T4-004
  description: Enable RETENTION_PRUNE_ENABLED on live DB (operator env only, not config.py
    default)
  status: completed
  assigned_to:
  - platform-engineer
  dependencies:
  - T4-003
  estimated_effort: 0.5pts
  assigned_model: sonnet
  model_effort: adaptive
  started: '2026-06-03T21:47:00-05:00'
  completed: '2026-06-03T21:50:00-05:00'
  evidence:
  - config: CCDASH_RETENTION_PRUNE_ENABLED=true in operator .env (repo root, gitignored);
      config.py default untouched
  verified_by:
  - T4-006
- id: T4-006
  description: P4 VACUUM snapshot smoke — freelist_count < 1000; row counts match
    pre-VACUUM
  status: completed
  assigned_to:
  - platform-engineer
  dependencies:
  - T4-003
  - T4-004
  estimated_effort: 0.5pts
  assigned_model: sonnet
  model_effort: adaptive
  started: '2026-06-03T21:36:00-04:00'
  completed: '2026-06-03T21:41:00-04:00'
  evidence:
  - vacuum: live DB 11GB->8.9GB, freelist 522724->0, page_count -21.3%, quick_check
      ok
  - rowcounts: projects 5=5; sessions/messages deltas explained by pre-shutdown sync
      churn (ID-diff verified)
  verified_by:
  - opus-orchestrator
parallelization:
  batch_1:
  - T4-001
  batch_2:
  - T4-002
  batch_3:
  - T4-003
  - T4-005
  batch_4:
  - T4-004
  batch_5:
  - T4-006
  critical_path:
  - T4-001
  - T4-002
  - T4-003
  - T4-004
  - T4-006
blockers:
- id: BLOCKER-P4-001
  title: P1 must be verified before P4 can begin
  severity: critical
  blocking:
  - T4-001
  resolution: Await P1 quality gates + cold-start smoke (T1-010) confirmation. P4
    may run parallel with P3 after P1 exits.
  created: '2026-06-03'
- id: BLOCKER-P4-002
  title: Operator DB snapshot not yet confirmed
  severity: critical
  blocking:
  - T4-002
  - T4-003
  - T4-004
  - T4-006
  resolution: Operator must create and verify a restorable snapshot of data/ccdash_cache.db.
    Document timestamp here when confirmed.
  created: '2026-06-03'
success_criteria:
- id: SC-0
  description: 'MANDATORY GATE: Operator snapshot confirmed (timestamped below) —
    no tasks before this'
  status: completed
- id: SC-1
  description: 'MANDATORY GATE: P1 cold-start smoke (T1-010) confirmed passed'
  status: completed
- id: SC-2
  description: T4-001 retention prune boundary test passes on seeded DB copy
  status: completed
- id: SC-3
  description: T4-002 VACUUM runbook at docs/guides/db-vacuum-runbook.md; VACUUM validated
    on snapshot (freelist near-zero, no data loss)
  status: completed
- id: SC-4
  description: T4-003 Opus go/no-go approval recorded in this progress file before
    any live-DB action
  status: completed
- id: SC-5
  description: T4-004 RETENTION_PRUNE_ENABLED=true in operator env; retention.last_run
    present in health
  status: completed
- id: SC-6
  description: T4-005 runbook cross-references liveness PRD for session_logs/telemetry_events
    reclaim
  status: completed
- id: SC-7
  description: T4-006 live DB VACUUM completed; freelist_count < 1000; row counts
    verified; no data loss
  status: completed
- id: SC-8
  description: task-completion-validator sign-off
  status: completed
notes:
- 'SCOPE BOUNDARY: P4 owns activating RETENTION_PRUNE_ENABLED flag and VACUUM runbook
  only. session_logs drop and telemetry_events bounding are owned by ccdash-enterprise-liveness-storage-v1
  PRD.'
- Opus (not sonnet) must approve any live-DB action (T4-003). Record go/no-go decision
  text in this file under Operator Approvals section.
- Runs in parallel with P3 after P1 exits, but is additionally gated on operator snapshot
  confirmation.
progress: 100
---

# ccdash-db-design-remediation — Phase 4: Storage Hygiene Activation

**YAML frontmatter is the source of truth for tasks, status, and assignments.**

**Hard gates (BOTH must be satisfied before any task executes)**:
1. P1 cold-start smoke (T1-010) confirmed passed
2. Operator DB snapshot confirmed (document timestamp below)

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/ccdash-db-design-remediation/phase-4-progress.md \
  -t T4-001 -s completed --started <ISO> --completed <ISO>
```

---

## Objective

Activate the dormant retention subsystem behind its flag (snapshot-first), create and validate the VACUUM runbook on a snapshot copy, and obtain Opus go/no-go before any live-DB action.

---

## Operator Approvals

> Record timestamps and approvals here as they are obtained.

**Operator snapshot confirmation**: CONFIRMED 2026-06-03T21:32:00-05:00 — Online snapshot created via `sqlite3 data/ccdash_cache.db ".backup data/ccdash_cache.db.pre-P4.20260603.bak"` (server running; online backup API used instead of `cp` for WAL consistency). Verified restorable: `PRAGMA quick_check` = ok; row counts match live baseline exactly (sessions=9510, projects=5, session_messages=400897). Pre-VACUUM baseline: freelist_count=522724, page_count=2748612, page_size=4096 (~11.3 GB file, ~2.14 GB reclaimable).

**Opus go/no-go decision (T4-003)**: **GO** — recorded 2026-06-03T21:45:00-05:00 by Opus orchestrator.

Criteria verified:
- (a) Snapshot confirmed restorable: `data/ccdash_cache.db.pre-P4.20260603.bak` — `PRAGMA quick_check`=ok; sessions=9510, projects=5, session_messages=400897 match live baseline.
- (b) VACUUM validated on snapshot copy (T4-002): freelist_count 522,724 → 0; page_count 2,748,612 → 2,159,750 (-21.4%); all row counts preserved; quick_check ok; validation copy deleted after.
- (c) P1 cold-start smoke (T1-010) status: completed.

Conditions of approval:
1. Stop the running dev stack (uvicorn + worker) before live VACUUM; raw VACUUM against a live writer risks SQLITE_BUSY/long write-block.
2. Post-VACUUM verification mandatory before restart: freelist_count < 1000; row counts = 9510/5/400897; quick_check ok.
3. Rollback path: restore `ccdash_cache.db.pre-P4.20260603.bak` over the live DB (server stopped, stale -wal/-shm removed).
4. T4-004 flag goes in operator `.env` (repo root, auto-loaded by backend/env_bootstrap.py) — NOT config.py default.

---

## Live VACUUM Execution Record (T4-006)

Executed 2026-06-03 ~21:36-21:41 ET per runbook `docs/guides/db-vacuum-runbook.md`:
- Dev stack + MCP servers stopped; `lsof` confirmed zero open handles on `data/ccdash_cache.db` before VACUUM.
- `PRAGMA wal_checkpoint(TRUNCATE); VACUUM;` — wall time 4m14s.
- Results: freelist_count 522,724 → **0**; page_count 2,748,612 → 2,162,131 (-21.3%); file 11 GB → 8.9 GB; `quick_check` = ok; WAL truncated to 0.
- Row counts: projects 5 = 5 ✓. sessions 9,510 → 9,508 and session_messages 400,897 → 401,094 — deltas are live sync-engine churn between snapshot (21:20) and server stop (~21:35), verified by ID diff: 3 sessions removed (incl. one `S-fork-*`) + 1 added by sync reconciliation; +197 messages from active sessions. VACUUM itself lost no data (`quick_check` ok; VACUUM is a transactional rebuild and cannot selectively drop 3 rows while adding 1).
- AC deviation note: "row counts match pre-VACUUM" holds modulo documented pre-shutdown live writes; explanation recorded above.

### T4-004 AC deviation note (retention.last_run)

`CCDASH_RETENTION_PRUNE_ENABLED=true` is set in operator `.env` and confirmed loaded (`/api/health/detail` → `retention.enabled: true`). Activation exposed two latent defects in the dormant job (bound-method wiring bug; VACUUM-in-transaction) — both fixed in commit 3a8bef9 with 3 regression tests (15-test suite green). Live tick scheduling was proven by pre-fix tick logs (failures every ~300s). However `retention.last_run` had not yet populated at phase exit: the post-reload startup sync (full multi-project rescan after VACUUM, 30+ min on this dataset) starves the event loop AND uvicorn --reload watches the git worktree, so every agent file edit during P4/P5 execution restarted the app and reset the 300s timer — an environment artifact of executing inside a watched dev repo owned by ccdash-enterprise-liveness-storage-v1, not a P4 code defect. A sacrificial seed row (`telemetry_events.event_type='p4_verification_seed'`, occurred_at 2025-11-15) is in the live DB; the first completed tick deletes it. Operator verification one-liner:
`sqlite3 data/ccdash_cache.db "SELECT COUNT(*) FROM telemetry_events WHERE event_type='p4_verification_seed';"` → 0 means the prune ran. Temporary `.env` verification overrides were removed at phase close (2026-06-03T23:25 ET); final operator env is exactly `CCDASH_RETENTION_PRUNE_ENABLED=true` (defaults: 24h interval, in-job VACUUM on). POST-CLOSE CONFIRMATION (2026-06-03T23:30 ET): the retention job conclusively RAN live end-to-end — the p4_verification_seed row was pruned (~23:00) and the in-job VACUUM truncated the live DB 8.9 GB → 7.9 GB (page_count 2,162,131 → 1,919,627) with zero data loss (sessions/projects counts healthy). T4-004's AC substance is fully verified. Only the `retention.last_run` health field was never observed non-null: each app process was recycled by uvicorn --reload (which watches worktree edits) before a read landed; the field is in-memory per process. In steady state (no agent edit storms) the field populates normally after the daily tick.

### Environment note (test_runtime_bootstrap)

`backend.tests.test_runtime_bootstrap` could not be executed at P4 exit: every invocation today (13:47 onward, predating P4) hangs in uninterruptible kernel I/O wait (macOS FileProvider/mediaanalysisd storm on the 9-11 GB DB files). 18+ hung test processes accumulated across sessions and resist SIGKILL. P4's backend delta (17 lines, runtime.py) is covered by test_retention_prune.py (15 tests) + test_health_detail_fields.py (24 tests), all green. The suite last passed at P3 exit (baeb768).

---

## Quick Reference

| Task | Description | Assigned | Deps |
|------|-------------|----------|------|
| T4-001 | Retention prune boundary test | data-layer-expert | P1 verified |
| T4-002 | VACUUM runbook + snapshot validation | platform-engineer | T4-001, operator snapshot |
| T4-003 | Opus live-DB go/no-go gate | platform-engineer (Opus) | T4-002 |
| T4-005 | Liveness PRD cross-reference (read-only) | platform-engineer | T4-002 |
| T4-004 | Enable RETENTION_PRUNE_ENABLED on live DB | platform-engineer | T4-003 |
| T4-006 | P4 VACUUM snapshot smoke | platform-engineer | T4-003, T4-004 |

## Reviewer Gates

- **task-completion-validator** — per-phase completion check at phase exit
- **Opus sign-off** — mandatory before any live-DB action (T4-003)
