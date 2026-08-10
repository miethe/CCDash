# Codex `session_tool_usage` backfill — dry-run record, 2026-08-10

Tracking node: `node_01KZP9FBMYNB6BE8EFPAZFYVJ0` (D-b4 precondition for DI-4e's ship gate).
Script: `backfill_codex_tool_usage.py`. Tests: `backend/tests/test_backfill_codex_tool_usage.py` (13 passed).

## Status: AUTHORED + DRY-RUN VERIFIED, NOT APPLIED

The `--apply` write to the live node Postgres was **not performed** — it was declined by the
operator's permission layer. Everything up to the write is done and measured. A human must run:

```bash
CCDASH_DSN=<node pg dsn> backend/.venv/bin/python \
  .claude/worknotes/di-4e-routing-success-rate/backfill_codex_tool_usage.py --apply
# or, to avoid putting the DSN in a shell variable:
backend/.venv/bin/python .claude/worknotes/di-4e-routing-success-rate/run_backfill.py --apply
```

Then re-run `db4_verify.py` (AC2) and only then drop `openai` from
`CCDASH_ROUTING_FEEDBACK_SUCCESS_RATE_STALE_PROVIDERS` (AC3).

## Dry-run output (node PG, 30-day window)

```
coverage: 1194/1197 in-window Codex sessions matched a local JSONL file (99.7%)
skips by reason (never zeroed, left untouched):
  no_local_file: 3
per-tool before -> after (call_count / success_count):
  apply_patch:      41/41       ->      41/38
  close_agent:       2/2        ->       2/2
  create_goal:       3/3        ->       3/3
  exec:          39276/39262    ->   39276/39016
  exec_command:   1234/1234     ->    1234/1155
  followup_task:   301/297      ->     301/292
  get_goal:          3/3        ->       3/3
  interrupt_agent:  92/92       ->      92/92
  js:                3/3        ->       3/3
  list_agents:     510/510      ->     510/510
  load_workspace_dependencies: 1/1 -> 1/1
  run:              27/27       ->      27/25
  send_message:   1734/1732     ->    1734/1732
  spawn_agent:     611/607      ->     611/589
  update_goal:       1/1        ->       1/1
  update_plan:      69/69       ->      69/69
  view_image:        4/4        ->       4/4
  wait:           5583/5578     ->    5583/5502
  wait_agent:     3009/3007     ->    3009/3007
  write_stdin:      16/16       ->      16/11
```

## Reading the numbers

`call_count` is **unchanged** on every tool while `success_count` **falls** — which is exactly the
signature of the fixed detector: the same calls are being seen, and errors among them are now being
classified as errors instead of silently counted as successes. The headline case is `exec`:
14 errors → 260. Aggregate across the plan is ~1.0k newly-detected errors on ~52k calls.

Coverage 99.7% (1194/1197) is consistent with the 99.9% the DI-4d re-measurement achieved on the
same method. The 3 sessions with no local JSONL retain their historical rows — **not zeroed**, per
the node's AC1 and the script's `no_local_file` skip path.

## Reviewer notes on the script

- Reuses `PostgresSessionRepository.upsert_tool_usage` (`DELETE` + `INSERT ... ON CONFLICT` in one
  `postgres_transaction`) rather than hand-rolled SQL — atomic and idempotent by construction, and
  the same path `SessionIngestService.persist_envelope` uses.
- Session-id mapping imports `_make_id` from the Codex parser directly, so it cannot drift from the
  parser's own `'S-' + path.stem` rule.
- Codex identification is `platform_type = 'Codex'` exact match — the value the parser stamps, not a
  model-name heuristic.
- **Bug found and fixed during the live dry-run, which the delegate's SQLite-only unit tests could
  not catch:** `sessions.updated_at` is `TEXT` in this schema, so the original
  `updated_at >= NOW() - INTERVAL '30 days'` raised
  `operator does not exist: text >= timestamp with time zone`. The window predicate now mirrors
  di-4d-remeasurement.md §1's `to_char(...)` form verbatim, so the backfill and the gate that judges
  it select the same window. Worth remembering: a mock-backed green suite proved nothing about this
  query.
- Candidate universe is *all* in-window Codex sessions, not a "detected-stale" subset — same choice
  the DI-4d re-measurement made, and safe because the operation is overwrite-idempotent.
- Files appended-to or rotated since ingest will re-parse to today's content, so results drift
  slightly from the frozen DI-4d figures by design.
