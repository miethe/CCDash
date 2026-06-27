---
title: SQLite VACUUM Runbook
doc_type: runbook
scope: ccdash-db-design-remediation
phase: P4
tasks: [T4-002, T4-005]
created: 2026-06-03
author: platform-engineer
status: validated
---

# SQLite VACUUM Runbook

This runbook covers the full VACUUM lifecycle for the CCDash SQLite database
(`data/ccdash_cache.db`): pre-VACUUM snapshot, execution, post-VACUUM
verification, WAL-checkpoint strategy (OQ-02 decision), rollback procedure, and
scope boundaries for related reclaim work owned by other PRDs.

All path references are relative to the CCDash repo root unless otherwise noted.
`$DATA` refers to `data/` throughout.

---

## 1. Pre-VACUUM Snapshot Procedure

A transactionally consistent snapshot is mandatory before running VACUUM. Two
variants are provided depending on whether the server is stopped or running.

### Variant A — Server Stopped (safest, preferred for scheduled maintenance)

```bash
# 1. Stop the API server and worker (CTRL-C or systemd/launchctl stop).
# 2. Force a final WAL checkpoint so the WAL file is fully merged.
sqlite3 $DATA/ccdash_cache.db "PRAGMA wal_checkpoint(TRUNCATE);"

# 3. Copy the DB file and its WAL/SHM siblings atomically while stopped.
cp $DATA/ccdash_cache.db $DATA/ccdash_cache_$(date +%Y%m%d).db.bak
cp $DATA/ccdash_cache.db-wal $DATA/ccdash_cache_$(date +%Y%m%d).db.bak-wal  2>/dev/null || true
cp $DATA/ccdash_cache.db-shm $DATA/ccdash_cache_$(date +%Y%m%d).db.bak-shm  2>/dev/null || true

# 4. Size sanity check.
ls -lh $DATA/ccdash_cache_$(date +%Y%m%d).db.bak
```

> Rationale: A raw `cp` of a live WAL-mode SQLite DB is not transactionally safe
> — the WAL may contain frames not yet merged into the main file. Stopping the
> server eliminates concurrent writers and lets `wal_checkpoint(TRUNCATE)` drain
> the WAL before the copy.

### Variant B — Server Running (online backup API; used for the P4 snapshot)

Use the SQLite online backup API via the `.backup` dot-command. This is safe
with a live server because the backup API takes a read lock and copies pages
consistently even while writers are active.

```bash
# Online backup — produces a transactionally consistent single-file copy.
sqlite3 $DATA/ccdash_cache.db ".backup $DATA/ccdash_cache_$(date +%Y%m%d).db.bak"

# The .backup command does NOT copy WAL/SHM — the backup is already a
# fully-checkpointed, WAL-quiesced file.

# Size sanity check.
ls -lh $DATA/ccdash_cache_$(date +%Y%m%d).db.bak
```

This variant was used for the P4 pre-VACUUM snapshot
(`data/ccdash_cache.db.pre-P4.20260603.bak`).

### Verify Restorability

Run these checks against the backup file before proceeding:

```bash
SNAP=$DATA/ccdash_cache.db.pre-P4.20260603.bak   # substitute actual name

sqlite3 "$SNAP" "PRAGMA quick_check;"
# Expected: ok

sqlite3 "$SNAP" "SELECT COUNT(*) FROM sessions;"
sqlite3 "$SNAP" "SELECT COUNT(*) FROM projects;"
sqlite3 "$SNAP" "SELECT COUNT(*) FROM session_messages;"
```

Record the row counts as your restore baseline.

**P4 baseline (verified 2026-06-03):**

| Metric | Value |
|---|---|
| `quick_check` | ok |
| sessions | 9510 |
| projects | 5 |
| session_messages | 400897 |
| `freelist_count` | 522724 |
| `page_count` | 2748612 |
| `page_size` | 4096 |
| Approximate file size | 11 GB |

---

## 2. VACUUM Execution

VACUUM rewrites the entire database file into a new, compacted file, reclaiming
all pages on the freelist. It cannot run against an open connection — the API
server and worker must be stopped first.

### Prerequisites

- DB snapshot taken and verified (Section 1).
- Sufficient free disk space: VACUUM writes a full copy of the DB to a temp file
  before replacing the original. Peak disk usage during VACUUM is approximately
  `current_file_size + post_vacuum_file_size`. For an 11 GB DB compacting to
  ~8.8 GB, budget at least 20 GB free on the volume holding `data/`.
- Server and worker are stopped. Running VACUUM against an active CCDash server
  will return `SQLITE_BUSY` and abort without making any changes.

### Stop the Server

```bash
# Dev (npm run dev / uvicorn):
# CTRL-C in the terminal running dev, or kill the uvicorn process.

# If managed by launchctl or systemd, use the appropriate stop command.
pkill -f "uvicorn backend.main" || true
pkill -f "backend.worker" || true
```

### Run VACUUM

```bash
sqlite3 $DATA/ccdash_cache.db "VACUUM;"
```

Runtime: several minutes for an 11 GB database. The command produces no output
on success; it will print an error if the database is busy or if there is
insufficient disk space.

After VACUUM completes, the WAL file will be empty or absent. Do not start the
server until verification (Section 3) passes.

---

## 3. Post-VACUUM Verification

Run these checks against the vacuumed database before restarting the server.

```bash
DB=$DATA/ccdash_cache.db

echo "=== freelist_count (expect < 1000, ideally 0) ==="
sqlite3 "$DB" "PRAGMA freelist_count;"

echo "=== page_count (expect large drop from pre-VACUUM value) ==="
sqlite3 "$DB" "PRAGMA page_count;"

echo "=== page_size ==="
sqlite3 "$DB" "PRAGMA page_size;"

echo "=== row counts (must match pre-VACUUM baseline) ==="
sqlite3 "$DB" "SELECT COUNT(*) FROM sessions;"
sqlite3 "$DB" "SELECT COUNT(*) FROM projects;"
sqlite3 "$DB" "SELECT COUNT(*) FROM session_messages;"

echo "=== structural integrity ==="
sqlite3 "$DB" "PRAGMA quick_check;"
```

Pass criteria:

| Check | Pass condition |
|---|---|
| `freelist_count` | < 1000 (near 0 after a full VACUUM) |
| `page_count` | Materially lower than pre-VACUUM value |
| sessions | Matches pre-VACUUM snapshot count |
| projects | Matches pre-VACUUM snapshot count |
| session_messages | Matches pre-VACUUM snapshot count |
| `quick_check` | ok |

### Validated on Snapshot — 2026-06-03

VACUUM was validated against an APFS clone of the P4 snapshot
(`ccdash_cache.db.pre-P4.20260603.bak`) on 2026-06-03. The validation copy was
deleted after measurement.

| Metric | Pre-VACUUM | Post-VACUUM | Delta |
|---|---|---|---|
| `freelist_count` | 522724 | 0 | -522724 (100%) |
| `page_count` | 2748612 | 2159750 | -588862 (-21.4%) |
| `page_size` | 4096 | 4096 | unchanged |
| Approximate file size | 11 GB | 8.8 GB | -2.2 GB |
| sessions | 9510 | 9510 | no change |
| projects | 5 | 5 | no change |
| session_messages | 400897 | 400897 | no change |
| `quick_check` | ok | ok | pass |

The freelist reclaim alone freed ~2.0 GB (522724 pages x 4096 bytes). All row
counts matched. Structural integrity check passed.

> Note: ~78.5% of pages remain post-VACUUM. The remaining bulk is live data
> (primarily `session_messages` at 400K rows). Full storage reclaim beyond this
> point requires the liveness-PRD row-deletion jobs described in Section 5.

---

## 4. WAL-Checkpoint Strategy (OQ-02 Decision)

### Current Behavior in the Codebase

`backend/db/connection.py` sets the following PRAGMAs on every new SQLite
connection (lines 50–58):

```python
await conn.execute("PRAGMA journal_mode=WAL")
await conn.execute("PRAGMA wal_autocheckpoint=1000")  # line 58
```

`backend/config.py` has no WAL-specific env-var overrides; there is no
`CCDASH_WAL_AUTOCHECKPOINT` setting. The `wal_autocheckpoint=1000` value is
hard-coded in `connection.py` and matches the SQLite compile-time default.

**What this means operationally:**

- SQLite triggers a passive checkpoint automatically after every write
  transaction that grows the WAL past 1000 pages (4 MB at 4096 bytes/page).
- A passive checkpoint does not block readers or writers; it merges WAL frames
  back into the main file opportunistically.
- Passive checkpoints can be "stalled" by long-running readers. Under heavy
  concurrent read load (the CCDash analytics path issues 12–15K queries per
  snapshot cycle) the WAL can grow beyond the 1000-page trigger before a
  checkpoint completes, allowing freelist fragmentation to accumulate over time.

### OQ-02 Resolution

**OQ-02 resolution:** The current strategy — SQLite WAL with
`wal_autocheckpoint=1000` (passive mode, hard-coded in `connection.py`) — is
retained as-is for the P4 release. No env-var override is introduced at this
time.

Rationale: The 522K-page freelist that existed before P4 accumulated over an
extended period of active ingest without a prior VACUUM, not because passive
checkpointing at 1000 pages is misconfigured. A post-VACUUM database with an
active maintenance schedule will not re-accumulate that fragmentation on the
same timescale.

**Recommendation if growth recurs:** If `freelist_count` climbs above 100K pages
again within a 90-day window (monitored via `PRAGMA freelist_count` in the
health endpoint), consider:

1. Switching to `PRAGMA wal_autocheckpoint=0` and scheduling an explicit
   `PRAGMA wal_checkpoint(RESTART)` or `(TRUNCATE)` after each nightly
   retention-prune job (when `RETENTION_PRUNE_ENABLED=true`). This is more
   aggressive than passive mode but avoids unscheduled stalls.
2. Enabling `RETENTION_PRUNE_ENABLED=true` to remove dead analytics and
   telemetry rows on a 24-hour cadence, which reduces the live page count and
   prevents freelist re-accumulation.
3. Scheduling quarterly VACUUM runs during maintenance windows.

An env-var `CCDASH_WAL_AUTOCHECKPOINT` can be introduced in `connection.py`
alongside the existing `CCDASH_SQLITE_BUSY_TIMEOUT_MS` and
`CCDASH_SQLITE_CACHE_SIZE_KB` pattern if operator control is needed.

---

## 5. Rollback Procedure

If post-VACUUM verification fails or the server does not start cleanly after
VACUUM, restore from the pre-VACUUM snapshot.

```bash
# 1. Ensure the server and worker are stopped.
pkill -f "uvicorn backend.main" || true
pkill -f "backend.worker" || true

# 2. Remove stale WAL and SHM files from the vacuumed database.
#    These must be removed before restoring; a mismatch between the main DB
#    and leftover WAL/SHM from a different database state causes corruption.
rm -f $DATA/ccdash_cache.db-wal $DATA/ccdash_cache.db-shm

# 3. Restore from snapshot.
cp $DATA/ccdash_cache.db.pre-P4.20260603.bak $DATA/ccdash_cache.db

# 4. Verify the restored file.
sqlite3 $DATA/ccdash_cache.db "PRAGMA quick_check;"
sqlite3 $DATA/ccdash_cache.db "SELECT COUNT(*) FROM sessions;"

# 5. Restart the server.
npm run dev   # or the appropriate start command
```

Do NOT copy the snapshot's `-wal`/`-shm` siblings back. The snapshot produced
by `.backup` is already fully checkpointed; it has no outstanding WAL frames.
Starting the server against the restored main file will create fresh
`-wal`/`-shm` files automatically.

---

## 6. Scope Boundary — Related Reclaim Work

This runbook covers structural compaction (VACUUM) only. Two additional
categories of storage reclaim are owned by the liveness/storage PRD and are
explicitly out of scope here.

### PRD Reference

`docs/project_plans/PRDs/infrastructure/ccdash-enterprise-liveness-storage-v1.md`
Implementation plan: `docs/project_plans/implementation_plans/infrastructure/ccdash-enterprise-liveness-storage-v1.md`

### P1-002 — session_logs Drop (T1-002)

**What it is:** Staged, flag-gated DROP of the legacy denormalized
`session_logs` table. `session_messages` is the canonical store; `session_logs`
is a ~1.75 GB duplicate.

**Status (read from `.claude/progress/ccdash-enterprise-edition-v1/phase-1-progress.md`):**
T1-002 is marked `status: completed` in the progress file. However, the
flag that gates the actual DROP TABLE migration remains `CCDASH_DROP_SESSION_LOGS_ENABLED=false`
by default in `backend/config.py` (line 1112). The progress `completed` status
reflects that the migration code and consumer migration were implemented and
merged; it does not mean the DROP has been executed against the live database.

**Current live-DB state:** `session_logs` table is still present in the live
database. The table will not be dropped until an operator explicitly sets
`CCDASH_DROP_SESSION_LOGS_ENABLED=true` and the migration runner executes the
staged DDL. A DB snapshot must be taken before enabling this flag.

**Storage impact of enabling:** Dropping `session_logs` is expected to free
~1.75 GB (per PRD problem statement). This is the largest single remaining
reclaim opportunity not captured by VACUUM.

### P1-016 — telemetry_events Bounded Growth / FTS5 (T1-016)

**What it is:** FTS5 full-text index on `session_messages.content`, dependency-
blocked on P1-002 staging being fully complete.

**Status:** T1-016 is marked `status: deferred` in the progress file. The PRD
notes it may slip to a later phase if the P1-002 staging window extends.

**Current live-DB state:** No FTS5 index exists. `telemetry_events` bounded-
growth retention is implemented behind `RETENTION_PRUNE_ENABLED` (default
false, see `config.py` lines 1079, 1085–1089). The retention pruner is not
running.

### What Must Run for Full Storage Reclaim

The following liveness-PRD jobs must execute (in order) to achieve full storage
reclaim beyond the VACUUM baseline:

1. **Enable `CCDASH_DROP_SESSION_LOGS_ENABLED=true`** and run the migration to
   DROP the `session_logs` table. Expected reclaim: ~1.75 GB. Prerequisite: DB
   snapshot, all 6 consumers confirmed on `session_messages`.
2. **Enable `CCDASH_RETENTION_PRUNE_ENABLED=true`** to activate the 24-hour
   TTL-delete cycle for `analytics_entries` (>90 days) and `telemetry_events`
   (>90 days). This bounds ongoing growth but does not reclaim existing rows
   immediately without a subsequent VACUUM.
3. **Run a second VACUUM** after the `session_logs` DROP and at least one
   retention-prune cycle to collapse the newly freed pages into file-size
   reduction.

None of these steps are implemented by this runbook. This runbook establishes
the VACUUM procedure and baseline; the liveness PRD owns the row-level reclaim.
