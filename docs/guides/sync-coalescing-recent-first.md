---
title: "Sync Coalescing & Recent-First Guide"
description: "How CCDash deduplicates concurrent syncs and prioritises recent sessions at startup"
category: guides
tags: [sync, performance, startup, operator, coalescing]
updated: 2026-06-12
---

# Sync Coalescing & Recent-First Guide

Three Phase 7/8 features govern how CCDash schedules and orders filesystem sync
work: the **coalescing guard** (deduplicates concurrent syncs), the
**recent-first window** (makes new sessions queryable within seconds), and
**startup hygiene** flags.  All three are on by default and independently
controllable.

> **Source**: `backend/db/sync_engine.py` (coalescing + recent-first),
> `backend/config.py` (all env vars), `backend/adapters/jobs/` (durable-queue
> idempotent path).

---

## Coalescing guard

**Env var**: `CCDASH_SYNC_COALESCING_ENABLED` (default: `true`)

When enabled, concurrent or duplicate sync dispatches for the same
`(project_id, trigger)` key are collapsed to a single in-flight run.

### How it works

`SyncEngine.sync_project` maintains an in-process set `_sync_in_flight`.  The
check and add are both synchronous (no `await` between them), so the
check-then-add is **atomic** in asyncio's single-threaded event loop:

1. Incoming dispatch computes `key = (project_id, trigger or "api")`.
2. If `key` in set → **coalesced**: returns immediately with `stats["coalesced"] = True`
   and a structured `INFO` log (never silent).
3. Otherwise → adds key to set, runs full sync.
4. `finally` block removes key via `discard()` (idempotent).

The coalescing guard also gates the **durable-queue idempotent-enqueue** check
(`enqueue_durable_idempotent`) when `CCDASH_JOB_QUEUE_BACKEND != memory`.

### Disable

```dotenv
CCDASH_SYNC_COALESCING_ENABLED=false
```

With the guard off, all dispatches for the same project run independently
(pre-Phase-7 behaviour).

---

## Recent-first window

**Env vars**:
| Variable | Default | Notes |
|---|---|---|
| `CCDASH_SYNC_RECENT_FIRST_ENABLED` | `true` | Gates the recent-first split |
| `CCDASH_SYNC_RECENT_FIRST_N` | `200` | Size of the priority window |

When enabled, `_sync_sessions` sorts all JSONL files by `mtime` descending and
splits them into two passes:

1. **Recent window** (first N files by mtime) — processed immediately so the
   newest sessions are queryable within seconds.
2. **Backfill pass** (remaining files) — processed in the same sync call
   immediately after the window.

A structured `INFO` log fires when the recent window completes and backfill
work remains:

```
sync_sessions recent_first_window_ready: project_id=<id>
  recent_synced=N recent_skipped=K backfill_deferred=M
```

**No silent caps**: `backfill_count` is asserted equal to `baseline_count` after
both passes; discrepancies are surfaced as `WARNING` logs.

### Why count-bounded (not time-bounded)

- Works identically on projects of any age or size.
- No empty windows on new projects; no runaway windows on large archives.
- Single-integer operator knob; no calendar dependency.
- mtime tiebreak is deterministic even when multiple files share a second.

### Tuning

```dotenv
# Process 500 most-recent sessions first instead of 200:
CCDASH_SYNC_RECENT_FIRST_N=500

# Disable recent-first (full scan, no split):
CCDASH_SYNC_RECENT_FIRST_ENABLED=false
```

When disabled or when file count ≤ N, all files are processed in a single pass
(identical to pre-Phase-7 behaviour — no regression).

---

## Startup hygiene

| Variable | Default | Effect |
|---|---|---|
| `CCDASH_STARTUP_SYNC_ENABLED` | `true` | Runs a sync pass on boot |
| `CCDASH_STARTUP_SYNC_DELAY_SECONDS` | `2` | Seconds to wait before boot sync starts (lets API server come up first) |
| `CCDASH_STARTUP_SYNC_LIGHT_MODE` | `false` | Skip unchanged paths based on a manifest (faster cold start on large archives) |
| `CCDASH_STARTUP_DEFERRED_REBUILD_LINKS` | `false` | Defer document-link rebuild until after API startup |

`CCDASH_STARTUP_SYNC_LIGHT_MODE=true` enables manifest-based scan skip: paths
whose manifest fingerprint has not changed since the last sync are skipped
entirely, reducing cold-start I/O on large session archives.  Disable if you
need guaranteed freshness on every boot.

---

## Phase 8 cross-project reconcile

| Variable | Default | Effect |
|---|---|---|
| `CCDASH_RECONCILE_INTERVAL_SECONDS` | `300` | Seconds between background reconcile ticks (≤ 0 disables) |
| `CCDASH_WATCHER_HEAL_ENABLED` | `true` | Auto-restart crashed/dead watchers within one reconcile interval |

The reconcile job enumerates every registered project each tick and dispatches
`sync_project(trigger="reconcile")` **through** the coalescing guard.  This
catches filesystem events missed by the watcher and picks up projects added
after boot without a restart.

With `CCDASH_WATCHER_HEAL_ENABLED=true`, a registered-but-dead watcher is
detected and re-bound within one interval; re-bind failures are logged and
retried on the next tick (no permanently silent dead watcher).

Set `CCDASH_RECONCILE_INTERVAL_SECONDS=0` to disable reconcile entirely; freshness
then depends solely on live watchers and the boot sweep.
