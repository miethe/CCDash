# Codex `session_tool_usage` backfill — APPLY record, 2026-08-10

Tracking node: `node_01KZP9FBMYNB6BE8EFPAZFYVJ0` (D-b4 precondition for DI-4e's ship gate).
Script: `backfill_codex_tool_usage.py`. Tests: `backend/tests/test_backfill_codex_tool_usage.py` (13 passed).

## Status: APPLIED and verified

> **This file previously said "NOT APPLIED".** It was written while the `--apply` write was declined
> by the permission layer, and it was **not updated when the write subsequently happened** — so the
> repo's only durable artifact contradicted the commit that lifted the gate. A reviewer gate caught
> exactly that (`defect_class: self-reported-side-effect`) and was right to: the AC2 claim rested on a
> commit message while the branch's own record said the opposite, and the file was named
> `backfill-dry-run-…`, which is part of how it misled. This section is the correction; the
> idempotency proof in §2 is the part that requires trusting no narrative at all.

## Why the session counts differ between runs — read this before comparing numbers

The window is a **rolling 30 days**, so the in-window Codex session count moves between every run.
Three different totals appear in this file and they are not inconsistent:

| Run | In-window Codex sessions | Matched a local JSONL |
|---|---|---|
| dry-run (pre-apply) | 1,197 | 1,194 (99.7%) |
| `--apply` | 1,242 | 1,239 (99.8%) |
| dry-run (post-apply idempotency check) | 1,240 | 1,239 (99.9%) |

Comparing "1194/1197" against "1239/1242" and inferring fabricated figures is a reasonable read of a
real inconsistency in the *old* version of this file, which reported only the first run and asserted
no apply had occurred.

## 1. The apply

```
coverage: 1239/1242 in-window Codex sessions matched a local JSONL file (99.8%)
skips by reason (never zeroed, left untouched):
  no_local_file: 3
per-tool before -> after (call_count / success_count):
  exec:         40056/40021 -> 40056/39783
  exec_command:  1234/1234  ->  1234/1155
  wait:          5589/5582  ->  5589/5508
  spawn_agent:    618/614   ->   618/596
  write_stdin:     16/16    ->    16/11
  apply_patch:     41/41    ->    41/38
  followup_task:  301/297   ->   301/292
  run:             27/27    ->    27/25
  send_message:  1767/1765  ->  1767/1765
  (unchanged: close_agent, create_goal, get_goal, interrupt_agent, js, list_agents,
   load_workspace_dependencies, update_goal, update_plan, view_image, wait_agent)

APPLIED: wrote session_tool_usage for 1239 session(s).
```

`call_count` unchanged on every tool while `success_count` falls — the signature of the fixed
detector: the same calls are seen, and errors among them are now classified as errors instead of
counted as successes. Headline: `exec` 35 errors → 273.

## 2. The idempotency proof — the part you can re-run

This is the evidence that does not depend on trusting §1. Re-running the script in **dry-run** mode
after the apply reads the *stored* rows as its `before` and the *freshly re-parsed* JSONL as its
`after`. Had the write not landed, `before` would still show the stale counts and the deltas would
reappear. Instead every tool reads `before == after`, with `before` already carrying the corrected
values:

```
coverage: 1239/1240 in-window Codex sessions matched a local JSONL file (99.9%)
no_local_file: 1
per-tool before -> after (call_count / success_count):
  apply_patch:      41/38     ->     41/38
  exec:          40076/39803  ->  40076/39803
  exec_command:   1234/1155   ->   1234/1155
  followup_task:   301/292    ->    301/292
  run:              27/25     ->     27/25
  send_message:   1767/1765   ->   1767/1765
  spawn_agent:     618/596    ->    618/596
  wait:           5589/5508   ->   5589/5508
  wait_agent:     3033/3029   ->   3033/3029
  write_stdin:      16/11     ->     16/11
  (all others unchanged and equal)

DRY RUN: zero writes performed.
```

Compare `exec`: `40076/39803` on the *before* side here, against `40056/40021` on the *before* side of
the apply run. The stored success count moved from ~40021 to ~39803 — the write landed. Reproduce in
one read-only command:

```bash
backend/.venv/bin/python .claude/worknotes/di-4e-routing-success-rate/run_backfill.py   # dry-run is the default
```

Expect `before == after` on every tool. Divergence means either new un-backfilled sessions have
entered the rolling window (normal as time passes) or the rows were re-staled.

## 3. The D-b4 gate (AC2), before and after

```bash
backend/.venv/bin/python .claude/worknotes/di-4e-routing-success-rate/run_db4_verify.py
```

| Reading | gpt/codex informative | err_rate | claude informative | err_rate |
|---|---|---|---|---|
| pre-apply (7,342-session window) | 8/28 (**28.6%**) | 0.11% | 146/162 (90.1%) | 4.01% |
| post-apply (7,344-session window) | 25/28 (**89.3%**) | 0.87% | 146/162 (90.1%) | 4.01% |
| post-apply re-read (7,347-session window) | 25/28 (**89.3%**) | 0.87% | 146/162 (90.1%) | 4.01% |

Earlier fix-cycle readings on narrower windows recorded 21.4%. The informative-key gap between
families is now **0.8pp**, down from 99.3pp pre-DI-4d and 10.1pp post-DI-4d, landing on the 89.2%
`di-4d-remeasurement.md` projected was achievable. AC2 is met.

**Residual, not resolved:** the two families' informative fractions now agree (89.3% vs 90.1%) but
their error *rates* still differ ~4.6x (0.87% vs 4.01%). That is a difference in measured tool-failure
rate, not in coverage, and is plausibly a genuine property of the different tool mixes (Codex's
`exec`/`wait` vs Claude's set) — but it has **not** been independently attributed. Do not read the
cross-family `success_rate` spread as purely behavioural until it has been.

## 4. Reviewer notes on the script

- Reuses `PostgresSessionRepository.upsert_tool_usage` (`DELETE` + `INSERT ... ON CONFLICT` in one
  `postgres_transaction`) rather than hand-rolled SQL — atomic and idempotent by construction, and
  the same path `SessionIngestService.persist_envelope` uses.
- Session-id mapping imports `_make_id` from the Codex parser directly, so it cannot drift from the
  parser's own `'S-' + path.stem` rule.
- Codex identification is `platform_type = 'Codex'` exact match — the value the parser stamps, not a
  model-name heuristic.
- Sessions with no local JSONL are **skipped, never zeroed** (`skip_reason="no_local_file"`, counted
  and reported). Same for a file that parses to `None` (`parse_returned_none`).
- **Bug found and fixed during the live dry-run, which the SQLite-only unit tests could not catch:**
  `sessions.updated_at` is `TEXT` in this schema, so the original
  `updated_at >= NOW() - INTERVAL '30 days'` raised
  `operator does not exist: text >= timestamp with time zone`. The window predicate now mirrors
  `di-4d-remeasurement.md` §1's `to_char(...)` form verbatim, so the backfill and the gate that judges
  it select the same window. A mock-backed green suite proved nothing about this query.
- Candidate universe is *all* in-window Codex sessions, not a "detected-stale" subset — same choice
  the DI-4d re-measurement made, and safe because the operation is overwrite-idempotent.
- Files appended-to or rotated since ingest re-parse to today's content, so figures drift slightly
  from the frozen DI-4d numbers by design.

## 5. How to run the apply (for the record)

```bash
# Sources the DSN from .env so no credential is materialized into a shell var or file.
backend/.venv/bin/python .claude/worknotes/di-4e-routing-success-rate/run_backfill.py --apply
```

The 2026-08-10 apply was executed by the operator directly, because the write is a mass
`DELETE`+`INSERT` across ~1.2k rows in shared node Postgres and the agent's permission layer declines
it by design. `session_tool_usage` is a **derived cache** (files are canonical), so the operation is
re-derivable and non-destructive of source data — but it is still production data, hence the gate.
