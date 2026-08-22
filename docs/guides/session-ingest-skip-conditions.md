---
title: Session ingest skip conditions
description: Every condition under which a transcript that exists on disk does not appear in GET /api/sessions, and how to attribute a specific absence.
audience: operators, agents
status: current
last_verified: 2026-08-22
---

# Session ingest skip conditions

A Claude Code transcript existing on disk is **not** sufficient for it to appear in
`GET /api/sessions`. This guide enumerates every skip condition on the path from file to API, so
that a future absence is **attributable rather than mysterious**.

Written from a live diagnosis on 2026-08-22 (IntentTree `node_01M0HG275DWRGNBRFRQ6AX4REG`) of a
reproduced gap: ended sessions on disk, well outside the ingest grace anchor, absent from the API
for their own window.

## 0. First: know which pipeline you are on

CCDash has **two independent ingest pipelines**, and they fail differently. Diagnosing the wrong one
wastes the whole investigation.

| | Direct worker relay | CLI daemon relay |
|---|---|---|
| Entry point | `backend.worker` (`worker-watch` profile) | `ccdash-cli daemon start` |
| Transport | writes **directly to Postgres** | `POST /api/v1/ingest/sessions` (NDJSON, bearer) |
| Backfill | yes, on startup/reconcile full sync | tail-only (see #14) |
| Dead-letter queue | **none** | `~/.local/state/ccdash/deadletter/` |
| Cursor/WAL | `sync_state` table | WAL + `ingest_cursors` |

On the Mac laptop the installed LaunchAgent `com.ccdash.stream-worker` runs
`deploy/local-streaming/bin/ccdash-stream-worker.sh`, which `exec`s **`python -m backend.worker`** —
the *direct* relay. It is **not** the CLI daemon. Therefore:

> An empty `~/.local/state/ccdash/deadletter/` on that host is a **non-finding**, not evidence that
> nothing was dropped. That directory belongs to the other pipeline.

Likewise `/api/health/detail` → `ingest_sources[]` is structurally blind to the direct relay: it
reports remote-ingest sources only. The direct relay's only observability is its local log at
`~/.ccdash/logs/stream-worker.err.log`.

## 1. Skip conditions

Each entry: the predicate, where it lives, whether it is silent, and whether a later pass recovers it.

### Path coverage (the highest-yield bucket in practice)

**S1 — The transcript's directory is not any registered project's `sessions_dir`.**
`ResolvedProjectPaths` computes exactly **one literal** `sessions_dir` per registered project
(`backend/services/project_paths/models.py`). Both the live watcher
(`backend/db/file_watcher.py:581`, `_resolve_watch_paths` → `[sessions_dir, docs_dir, progress_dir]`)
and the periodic full sync (`backend/db/sync_engine.py:4945`, `self._rglob(sessions_dir, "*.jsonl")`)
scan only that one tree. There is **no fan-out to sibling directories**.
*Silent.* **Never self-heals** — no later pass widens the scan.

This is not a corner case, because **Claude Code slugifies the session's `cwd`, not the repo root.**
A session launched from any directory below the repo root gets its **own top-level slug directory**,
a *sibling* of the repo's — not a child of it:

```
~/.claude/projects/-Users-miethe-dev-homelab-development-agentic-meta-dev                          <- registered
~/.claude/projects/-Users-miethe-dev-homelab-development-agentic-meta-dev--claude-worktrees-foo    <- sibling, unwatched
~/.claude/projects/-Users-miethe-dev-homelab-development-agentic-meta-dev--claude-skills-…         <- sibling, unwatched
```

Because a `sessions_dir` is a sibling of these, no amount of recursion reaches them.

> `backend/parsers/worktree_attribution.py` correctly parses the `--claude-worktrees-` marker, but it
> runs **after** a file is already discovered, to label `worktreeName` on an already-ingested row
> (`backend/db/sync_engine.py:5131`). It never expands what gets scanned. Its existence is easy to
> mistake for worktree coverage; it is not.

**S2 — The cwd can never map to a registered project at all.** Delegate/sandbox executions run in
ephemeral randomized directories (`/private/tmp/claude-501/<repo>-<uuid>/…`,
`/private/tmp/claude-launch-XXXXXX`, `/private/var/folders/.../T/claude-launch-XXXXXX`). The path
carries a fresh UUID per invocation, so no static registration can cover it. Distinct from S1: this
is not a resolution gap inside a registered project, it is the absence of any project to attribute
to. *Silent. Never self-heals.*

**S3 — A registered path does not exist on this host.** Watch paths are existence-filtered
(`file_watcher.py:_resolve_watch_paths`), so a registry entry pointing at an absent directory
contributes zero. A project registering `/home/miethe/.claude/projects` on a Mac (where `/home` is
not populated) silently watches nothing. *Logged `WARNING` only when **every** bound path is empty.*

**S4 — Watcher configured with no existing session path.** `file_watcher.py:341` logs
`WARNING "File watcher configured with no existing paths."` and that watcher instance does not
re-watch later; re-registration/restart is required.

**S5 — Not an eligible `.jsonl` under the configured root.** The watch classifier
(`file_watcher.py:629`) accepts only `.jsonl`/`.md`; sync dispatch (`sync_engine.py:4393`)
additionally requires `sessions_dir in path.parents`. *Silent. Permanent for that route.*

### Liveness and scheduling

**S6 — Worker never starts.** `deploy/local-streaming/bin/ccdash-stream-worker.sh` exits `78`
(missing `~/.ccdash/stream.env`, unset/invalid `CCDASH_REPO`) or `69` (no `backend/.venv/bin/python`).
launchd `KeepAlive` retries the launch but cannot fix the config.

**S7 — Downtime gap with no reconcile.** The live watcher only reacts to `awatch` events
(`file_watcher.py:421`). If a file is written while the worker is down, recovery depends on
`CCDASH_STARTUP_SYNC_ENABLED` (`backend/adapters/jobs/runtime.py:339`) or a periodic reconcile
(disabled when `CCDASH_RECONCILE_INTERVAL_SECONDS <= 0`, `runtime.py:1708`). *No log for the missed
event itself.*

**S8 — Startup backfill exists, but only for projects actually synced.** `worker-watch` sets
`sync=True` (`backend/runtime/profiles.py:69`, in the `worker-watch` block at `:65`); startup calls `sync_project`
(`runtime.py:2268`); `_sync_sessions` recursively enumerates all `*.jsonl` and processes recent +
backfill partitions (`sync_engine.py:4944`, `:4996`). There is **no size, age, or max-file cutoff**
on the Claude session path. So the direct relay is *not* live-cursor-only — provided the project is
bound and startup/reconcile sync runs.

**S9 — Watcher dispatch timeout drops the tick's classified files.** `sync_changed_files(...)` is
bounded by a configurable 120 s timeout (`file_watcher.py:464`); on expiry the handler logs
`ERROR "File watcher change sync TIMED OUT after 120s … continuing to next tick"` (`:483`) and the
files classified for that tick are abandoned. The in-flight sync is cancelled mid-transaction,
surfacing as `asyncio.exceptions.CancelledError` under
`ERROR "Skipping session file that failed to sync"`. Because an **ended** session's file never
changes again, no watcher event retries it; only a later reconcile/full sync recovers it. *Logged at
ERROR, but into a log that reached 191 MB in four days — effectively unread.*

Measured on the laptop relay over 2026-08-18 → 2026-08-22: **4,005 timeout ticks abandoning 8,058
classified file-syncs**, still occurring daily. The trigger is that a *single-session* "incremental"
link rebuild fans out to a full feature-evidence pass —
`links:feature-prep - Building feature evidence for 342 feature(s)` for
`incremental link rebuild — 1 session(s)` — which exceeds 120 s. See the follow-up node in
§ Related work; this is a **separate defect** from S1/S2, and is self-healing via reconcile.

**S10 — Parse/persistence exception for a changed file.** Caught per file
(`sync_engine.py:4397`, `:4969`), logged `ERROR "Skipping session file that failed to sync"`.
Observed causes on the laptop: `FileNotFoundError` (transient worktree/scratch dirs removed between
classify and read), `CancelledError` (S9), `asyncpg InterfaceError` /
`ConnectionDoesNotExistError`, `TimeoutError`. Normally self-healing, because sync state is not
advanced past a failure.

### Content and watermark

**S11 — Metadata watermark says unchanged.** `sync_engine.py:5078` returns `False` when cached (`:5074` computes the effective mtime)
`file_mtime == _session_input_mtime(path)`; effective mtime is the max of the JSONL and its capture
sidecar (`:251`). *Silent.* A content replacement preserving mtime is skipped until a forced sync.

**S12 — Light-mode manifest says nothing changed.** With `CCDASH_STARTUP_SYNC_LIGHT_MODE=true`,
`sync_engine.py:5220` skips when the inode snapshot shows no added/removed/changed paths; the
snapshot compares only `(st_mtime, st_size)` (`:5198`). *Logged `INFO light_mode_scan_skip`.*

**S13 — Unreadable, empty, or wholly invalid JSONL.** The Claude parser
(`backend/parsers/platforms/claude_code/parser.py:1919`) returns `None` on read failure, empty file,
or zero valid JSON lines; individual malformed lines are silently ignored. Sync deletes prior rows
and persists nothing (`sync_engine.py:5109`, `:5112`), recording outcome `empty` — *not an error*
(`:5186`). A previously visible row can be **removed** by this path while the bad file remains.

**S14 — A deletion event removes the row.** `sync_engine.py:4363` calls `delete_sync_state` +
`session_repo.delete_by_source` on `Change.deleted`. If the file is later restored without a new
added/modified event, it stays absent until a full sync.

### CLI daemon pipeline only

**S15 — Daemon config/import failure.** Missing `server_url`, token, project id, or session dir
(`packages/ccdash_cli/src/ccdash_cli/daemon/config.py:132`, `commands/daemon.py:51`), or
`backend.parsers.sessions` failing to import (`daemon/runner.py:217`).

**S16 — No universal startup backfill (tail-only).** The tail begins at
`iter_changed_files(...)` (`daemon/runner.py:230`); `watchfiles.awatch()` yields events only from
the moment observation starts (`daemon/tail.py:52`). Only the **mtime-poll fallback** emits
pre-existing files on first sight (`daemon/tail.py:89`) — and that fallback is **non-recursive**.
So a transcript that appeared or grew while the daemon was down is missed unless it is modified
again. *Silent.*

**S17 — Parse/queue durability failure.** Parse exceptions log `WARNING`, `None` is silently skipped
(`daemon/runner.py:232`); a WAL append failure is logged `ERROR` but the event remains only in
memory (`:243`–`:249`) and is lost on crash.

**S18 — HTTP rejection.** Server authenticates before parsing and derives project/workspace from the
bearer token (`backend/routers/ingest.py:63`, `:90`); invalid event shape is rejected (`:117`).
401/403/415, or a malformed/missing `event_id`/`batch_id`/`occurred_at`/object `payload`, yields a
non-retryable 4xx: client logs `ERROR` and dead-letters (`daemon/runner.py:479`). Recovery requires
manual `ccdash daemon replay` (`commands/daemon.py:156`).

**S19 — Transport failure / dead-letter.** Connection, 429 and 5xx retry paths at
`daemon/runner.py:375`, `:452`, `:487`; a **singleton 413** is terminally dead-lettered and
WAL-acked (`:423`). Connection/429/5xx self-heal via WAL replay; 413 and non-retryable 4xx need
manual intervention.

### Stored, but invisible to the query

**S20 — The row exists but this `GET /api/sessions` call cannot see it.** The list route resolves
**one** requested/context/active project and otherwise returns empty
(`backend/routers/api.py:653`, `backend/application/services/common.py:100`); it hard-codes
`workspace_id="default-local"` (`api.py:697`, `:699` — both marked `TODO(workspace-routing)`); and the repository **excludes subagents by default**
(`backend/db/repositories/postgres/sessions.py:696`), then applies pagination and every supplied
filter. *Silent.*

> An unscoped `GET /api/sessions` is **not** an all-project session inventory. A row can be absent
> because it lives under another project, another workspace, is a subagent with
> `include_subagents=false`, or falls beyond `limit`/`offset`. This is a visibility failure, not
> ingest loss — check it before concluding anything was dropped.

## 2. Attributing a specific absence

Work down this order; each step is cheap and eliminates a whole bucket.

1. **Is it a visibility problem?** (S20) Query the session id with its **own** `project_id`, with
   `include_subagents=true`, over a wide date range, before concluding it was never ingested.
2. **Is its directory covered?** (S1/S2/S3) Compare the transcript's slug directory against every
   registered project's `pathConfig.sessions.filesystemPath`:

   ```bash
   set -a; . ~/.config/aos/secrets.env; set +a
   curl -s -H "Authorization: Bearer $CCDASH_TOKEN" "$CCDASH_API/api/projects" \
     | python3 -c 'import json,sys
   for p in json.load(sys.stdin):
       print(((p.get("pathConfig") or {}).get("sessions") or {}).get("filesystemPath",""))'
   ```

   If the transcript sits in a `--claude-worktrees-` sibling, a subdirectory-cwd sibling, or under
   `/private/tmp` or `/private/var/folders`, stop — it is S1 or S2 and will never arrive.
3. **Was the relay alive?** (S6/S7) `launchctl print gui/$(id -u)/com.ccdash.stream-worker`, and
   correlate the transcript's mtime against `~/.ccdash/logs/stream-worker.err.log`.
   Beware: that log is **local time** (EDT), while windows are usually quoted in **UTC** —
   comparing the two directly manufactures a phantom multi-hour outage.
4. **Was its tick dropped?** (S9/S10)

   ```bash
   grep 'TIMED OUT' ~/.ccdash/logs/stream-worker.err.log | wc -l
   grep -A25 'Skipping session file that failed to sync' ~/.ccdash/logs/stream-worker.err.log \
     | grep -E '^[A-Za-z_.]+(Error|Exception)' | sort | uniq -c | sort -rn
   ```
5. **Watermark or content?** (S11/S12/S13) Check `sync_state` for the path, and confirm the file has
   at least one parseable JSON line.

## 3. Measured coverage on the laptop relay (2026-08-22)

Comparing every slug directory under `~/.claude/projects` against the 35 registered projects'
resolved session paths:

| Bucket | Slug dirs | Transcripts |
|---|---:|---:|
| Covered by a registered `sessions_dir` | 21 | 1,699 |
| **Uncovered — worktree-cwd siblings (S1)** | **218** | **925** |
| **Uncovered — ephemeral `/private/tmp` cwds (S2)** | **30** | **56** |
| Uncovered — other unregistered dirs (S1/S3) | 29 | 35 |
| **Total** | **298** | **2,715** |

**1,016 of 2,715 transcripts (37%) are structurally invisible to ingest** — not delayed, not
retryable: never scanned. The single largest cause is worktree-cwd sessions, which is precisely the
execution mode the `/itt:run` and `/dev:*` lanes use by default, so the loss is biased toward
orchestrated delivery work.

One project (`ccp-9704ef0f4498`) registers a single worktree slug directory as its own project.
That is the existing workaround, applied to 1 of 218 — it does not scale and nothing maintains it.

## 4. Related work

- `node_01M08PBYK20VE03M83AQZ7RKXK` — laptop sessions absent from ingest (related filing).
- The S9 timeout storm and its `links:feature-prep` trigger are tracked separately; they are a real
  and ongoing loss path, but **self-healing via reconcile**, and were *not* the cause of the
  diagnosed gap.

## Do not conclude

- Do not conclude a transcript was dropped because it is missing from an **unscoped**
  `GET /api/sessions` — that route is single-project, `default-local`-workspace, and
  subagent-excluding by default (S20).
- Do not conclude the direct relay lost a file because its dead-letter directory is empty — it has
  no dead-letter queue (§0).
- Do not conclude the relay was down from a log gap without normalizing local time to UTC (§2.3).
- Do not conclude worktree sessions are covered because `worktree_attribution.py` exists — that
  module labels rows after discovery and never widens the scan (S1).
