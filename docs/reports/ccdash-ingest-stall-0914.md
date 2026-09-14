---
title: CCDash fleet-wide session-ingest stall — probe, mechanism, fix
node: node_01M2GV5XJ63HYV282W02N7DF2R
date: 2026-09-14
---

## Probe

- Reproduced live via LAN (ssh to `agentic-nuc` was not grantable in this session — approval
  never resolved; all evidence below is from `10.42.10.76:8090` directly and from this repo's
  git history):
  `curl -s http://10.42.10.76:8090/api/health/detail` → `ingest_sources[0]` =
  `{"source_id": "remote_ingest", "project_id": "ccp-e9ae9bcf8f6b", "last_ingest_at":
  "2026-09-10T19:53:31.252321+00:00", "lag_seconds": 351197.9, "state": "disconnected"}`.
  This is the ADR-014/015 remote-ingest cursor — the ONE pipe every registered project's
  sessions flow through (per-file `cwd` re-attributes server-side; see
  `infra/agentic-node/CCDASH-NODE-INGEST.md` §(d)). It stopped advancing 2026-09-10T19:53Z,
  ~4 days before this probe — consistent with the finding's Sep-9-onward zero window.
- `api` runtime profile confirms no in-process watcher/jobs (`capabilities.watch/sync/jobs` all
  `false`) — this runtime cannot self-heal or re-scan; ingestion depends entirely on the external
  daemon(s) POSTing to `/api/v1/ingest/sessions`.
- `git log --all --since=2026-09-05 --until=2026-09-12`: commit `1deccf0` (#83, merged
  2026-09-08 14:22 UTC) added the journal-egress predicate at the parser choke point
  (`backend/parsers/platforms/claude_code/parser.py:1965`, `filter_transcript_records`). Its own
  doc (`docs/guides/journal-transcript-egress.md` "Deployment") states both ingest daemons run
  from **separate checkouts** (laptop `com.ccdash.stream-worker`, node
  `ccdash-ingest-daemon.service`) that must be manually `git pull`ed + restarted — "merged is not
  deployed" — and that a restart failure is invisible (`infra/agentic-node/CCDASH-NODE-INGEST.md`
  §(b): a broken `backend.parsers.sessions` import kills only the daemon's tail coroutine; the
  flush coroutine keeps running and reports clean, so `systemctl status`/`daemon status` both
  look healthy forever).

## Mechanism (candidate, not proven without node log access)

`packages/ccdash_cli/src/ccdash_cli/daemon/runner.py:344-352` (`_tail_coroutine`, pre-fix):
caught `ImportError` on the lazy `backend.parsers.sessions` import, logged **one** ERROR line,
and `return`ed. `asyncio.gather(tail_task, flush_task)` in `run_daemon()` never completes when
`tail_task` merely returns early (`flush_task` loops forever regardless) — so the daemon process
never exits, never crash-loops, and `Restart=on-failure` never fires. It just stops ingesting
everything, forever, while looking perfectly healthy. This is the exact "silent-failure trap"
`CCDASH-NODE-INGEST.md` §(b) already documents from a prior incident — the Sep-8 restart required
by #83 is the most likely trigger for it recurring, given the timing (merge 09-08 14:22 UTC →
last cursor advance 09-10 19:53 UTC, ~2 days later, matching an operator getting to the restart).
I could not confirm the exact trigger (ImportError vs. something else) without node
`journalctl`/`ccdash-cli daemon status` access, which this session's ssh approval never granted.

Ruled out empirically: the journal-egress predicate itself (`backend/services/transcript_filter.py`)
does not false-positive on ordinary (non-journal) transcript content — tested directly against a
synthetic normal session including a `thinking` block; all three records kept, none excluded.

## Fix

`packages/ccdash_cli/src/ccdash_cli/daemon/runner.py`: `_tail_coroutine`'s `ImportError` handler
now `raise`s instead of `return`s, so the failure propagates out of `asyncio.gather()` and crashes
`run_daemon()` — visible in `journalctl`, retried by `Restart=on-failure`, instead of an
undetectable zombie. Regression test:
`packages/ccdash_cli/tests/test_daemon_tail_import_failure_is_fatal.py` (2 tests: the coroutine
re-raises directly, and `run_daemon()` end-to-end raises within a bounded timeout instead of
hanging — the hang IS the pre-fix zombie state). Full `packages/ccdash_cli` suite: 255 passed, 0
failed, run in the foreground.

PR: (opened after this commit — see the follow-up commit on this branch for the real link).
Landing-queue row added to `~/.local/share/aos/landing-queue/CCDash.jsonl`.

## Recovery — gated for Nick, NOT executed

Backfilling Sep 9 onward and any daemon/service restart on `agentic-nuc` are shared-infra deploy
actions. None were run. Read-only probes only, all via LAN HTTP (ssh approval did not resolve in
this session — the commands below use ssh anyway, per the brief, and are unexercised by me):

```
ssh agentic-nuc 'systemctl --user status ccdash-ingest-daemon.service'
```
Proves: whether the node daemon is currently running, and its last exit/restart per systemd, which
this session could not observe over LAN HTTP.

```
ssh agentic-nuc 'journalctl --user -u ccdash-ingest-daemon --since "2026-09-08" --no-pager'
```
Proves: the actual tail-coroutine failure line (or absence of one), confirming or refuting the
ImportError mechanism above.

```
ssh agentic-nuc 'python -c "import ccdash_cli, backend.parsers.sessions, watchfiles; print(1)"' # run with the daemon's own interpreter, e.g. /home/miethe/dev/CCDash/backend/.venv/bin/python
```
Proves: whether the node daemon's interpreter can currently import all three required modules —
directly reproduces or rules out the §(b) trap.

```
ssh agentic-nuc 'cat ~/.local/state/ccdash/daemon.status'
```
Proves: the daemon's self-reported counters (accepted/rejected/last_error) — a clean zero-count
record here, next to a non-empty dead-letter dir, is the documented zombie signature.

```
ssh agentic-nuc '/home/miethe/dev/CCDash/backend/.venv/bin/python -m ccdash_cli.main daemon replay --dir ~/.local/state/ccdash/deadletter --dry-run'
```
Proves: whether any batches were dead-lettered (vs. never sent at all) during the outage window.

```
ssh agentic-nuc 'git -C /home/miethe/dev/CCDash log -3 --oneline'
```
Proves: whether the node checkout ever advanced past commit `1deccf0` (i.e., whether the #83
deploy this incident is theorized around actually happened on this checkout).

Once the daemon is confirmed healthy on the fixed code, no separate backfill script is needed —
the daemon's cold-start backfill scan (`_backfill_existing_sessions`) and `iter_changed_files`
will pick up every untouched file already on disk on next start, and future files as they change.

## Assumptions

```json
[
  {"claim": "the fleet-wide 5-day zero-session outage is caused by the tail-coroutine silent-death class of bug, triggered by the #83 (1deccf0) restart", "confidence": 0.45, "blast_radius": "med", "evidence_if_wrong": "journalctl shows no ImportError/traceback near 2026-09-10T19:53Z, or shows the daemon process was never restarted after 09-08 at all"},
  {"claim": "the journal-egress predicate (backend/services/transcript_filter.py) does not itself drop ordinary sessions to empty", "confidence": 0.8, "blast_radius": "low", "evidence_if_wrong": "a real, non-journal session file run through parse_session_file returns None post-fix-deploy on the node"},
  {"claim": "restarting the node's ccdash-ingest-daemon.service on the now-fixed code is sufficient recovery with no separate backfill", "confidence": 0.5, "blast_radius": "low", "evidence_if_wrong": "the cold-start backfill scan misses files, or the WAL/dead-letter directories are empty because the daemon never even attempted the writes it should retry"}
]
```
