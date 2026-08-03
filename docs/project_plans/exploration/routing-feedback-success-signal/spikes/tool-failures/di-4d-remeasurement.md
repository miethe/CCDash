---
doc_type: spike_remeasurement
leg_id: tool-failures
parent_finding: tool-failures-findings.md
di_item: DI-4d
confidence: 0.88
status: complete
created: 2026-08-03
method: reparse
same_denominator: true
---

# DI-4d Re-measurement — Codex tool-error detection, before vs. after

Satisfies DI-4d acceptance criterion #3: *"The DI-4b tool-failures coverage measurement is re-run
against the SAME 188-key denominator so before/after is directly comparable."*

The fix under measurement is commit `089ab60` — `backend/parsers/platforms/codex/tool_outcome.py`
plus the call-site change at `backend/parsers/platforms/codex/parser.py:1036`.

## 0. What "after" means here — read this before the table

**A parser fix does not retroactively change stored counts.** Every row in
`session_tool_usage` on the node Postgres was written by the *old* parser. Re-running the DI-4b
query verbatim after the fix returns the identical `0 errors` for GPT/Codex, because that query
reads history, not behaviour.

So the "after" column below is **not** a re-query of unchanged historical rows. It is produced by
**re-parsing the raw JSONL with the fixed parser** and substituting the resulting per-session
counts into the same 188-key key grain:

| | source of counts |
|---|---|
| **before** | `session_tool_usage` rows on node PG, as written by the old parser |
| **after — gpt/codex-family keys** | **re-parse** of `~/.codex/sessions/**/*.jsonl` through `parse_session_file` at commit `089ab60` |
| **after — claude / synthetic / empty keys** | unchanged historical rows (the fix touches only `platforms/codex/`, so these are correctly identical by construction, not by omission) |

Re-parse coverage of the denominator: **1,318 of 1,319** distinct in-window GPT/Codex session ids
had their source JSONL present locally (**99.9%**); 1,414 of 1,415 key-member session rows were
substituted. One session (`S-rollout-2026-07-12T21-21-56-019f5911-...`) has no local file and
retains its historical (zero-error) counts. Session-id ↔ file mapping is
`'S-' + path.stem`, per `codex/parser.py:120` (`_make_id`).

The re-parse total for the substituted sessions is **58,453 calls** against the historical
**60,238** for the same keys (−3.0%, attributable to the one missing file and to sessions whose
JSONL has been appended-to or rotated since ingest). Because the call denominators agree to within
3%, the substitution is a like-for-like comparison rather than a different corpus.

## 1. Denominator — independently re-derived, matches SHARED-CONTEXT

```sql
WITH per_session AS (
  SELECT session_id, SUM(call_count) AS calls, SUM(success_count) AS successes
  FROM session_tool_usage GROUP BY session_id),
win AS (
  SELECT s.id, s.project_id, s.skill_name, s.model FROM sessions s
  WHERE s.updated_at >= to_char(NOW() - INTERVAL '30 days','YYYY-MM-DD"T"HH24:MI:SS'))
SELECT w.project_id, w.skill_name, w.model, w.id, ps.calls, ps.successes
FROM win w LEFT JOIN per_session ps ON ps.session_id = w.id;
```
Aggregated to `(project_id, skill_name, model)` in Python with `HAVING count(*) >= 5`:

| Quantity | SHARED-CONTEXT (measured earlier 2026-08-03) | This run |
|---|---|---|
| sessions in 30-day window | 7,354 | 7,384 |
| all keys in window | 396 | 405 |
| **keys clearing `min_sample`=5** | **188** | **188** |
| sessions inside those keys | 6,952 | 6,964 |

**The denominator is 188 in both runs — same number.** The window is a rolling 30 days and has
advanced a few hours, so the raw session count moved (+30) and the sub-`min_sample` tail moved
(+9 keys), but the set clearing the threshold is the same size. Family split is also identical
(138 claude / 37 gpt-codex / 8 empty / 5 synthetic), so the before/after comparison is on the
same key population.

## 2. The before/after family-split table

"Informative" = within-key variance in the per-session error rate (`stddev > 0`), the same
definition used in `tool-failures-findings.md` §2 and mandated by SHARED-CONTEXT §2 ("a column
that is present but constant is coverage without information").

### BEFORE — historical rows, old parser

| family | keys | informative | zero-mean | no-data | calls | errors | err_rate |
|---|---|---|---|---|---|---|---|
| claude-family | 138 | **137 (99.3%)** | 1 | 0 | 184,403 | 5,881 | 3.19% |
| gpt/codex-family | 37 | **0 (0.0%)** | 36 | 1 | 60,238 | **0** | **0.00%** |
| synthetic | 5 | 2 | 1 | 1 | 387 | 9 | 2.33% |
| empty model | 8 | 0 | 0 | 8 | 0 | 0 | n/a |
| **TOTAL** | **188** | **139 (73.9%)** | 38 | 10 | 245,028 | 5,890 | 2.40% |

### AFTER — gpt/codex re-parsed with the fixed parser

| family | keys | informative | zero-mean | no-data | calls | errors | err_rate |
|---|---|---|---|---|---|---|---|
| claude-family | 138 | 137 (99.3%) | 1 | 0 | 184,403 | 5,881 | 3.19% |
| gpt/codex-family | 37 | **33 (89.2%)** | 3 | 1 | 60,227 | **889** | **1.48%** |
| synthetic | 5 | 2 | 1 | 1 | 387 | 9 | 2.33% |
| empty model | 8 | 0 | 0 | 8 | 0 | 0 | n/a |
| **TOTAL** | **188** | **172 (91.5%)** | 5 | 10 | 245,017 | 6,779 | 2.77% |

### Delta

| metric | before | after |
|---|---|---|
| informative keys, all families | 139/188 = **73.9%** | 172/188 = **91.5%** |
| informative fraction, claude-family | 137/138 = **99.3%** | 137/138 = **99.3%** (unchanged, by design) |
| informative fraction, gpt/codex-family | 0/37 = **0.0%** | 33/37 = **89.2%** |
| gpt/codex recorded error rate | 0.00% (190,450 all-time calls, 0 errors) | 1.48% in-window |
| cross-family informativeness gap | 99.3pp | 10.1pp |

The four GPT/Codex keys that remain non-informative are 3 genuinely constant-zero (small
low-tool-count keys) plus the 1 no-data key. No key regressed.

**This is not a Claude-only fix.** The Claude numbers are byte-identical before and after because
the change is confined to `backend/parsers/platforms/codex/`; the gain is entirely on the
previously-dead family, which is the direction that removes the bias rather than deepening it.

## 3. Detection coverage — is the new signal actually resolving, or guessing?

Instrumented over the same 1,318 re-parsed sessions, reading the `toolStatusSource` the fix
records on every tool log:

```
tool_results_with_source = 58,427   unresolved ("unknown") = 156 = 0.27%
```

| tool | n | unresolved | classification sources |
|---|---|---|---|
| `exec` | 34,698 | 0 (0.00%) | script_lifecycle 34,672 · failure_marker 26 |
| `exec_command` | 10,849 | 0 (0.00%) | exit_code_line 10,730 · in_flight 119 |
| `wait` | 5,623 | 0 (0.00%) | script_lifecycle 5,620 · failure_marker 3 |
| `wait_agent` | 3,177 | 48 (1.51%) | structured_ok 3,125 · unknown 48 · failure_marker 4 |
| `send_message` | 1,558 | 0 (0.00%) | empty_output 1,558 |
| `spawn_agent` | 728 | 62 (**8.52%**) | structured_ok 647 · unknown 62 · failure_marker 19 |
| `list_agents` | 482 | 0 | structured_ok 482 |
| `apply_patch` | 391 | 0 | exit_code_line 376 · failure_marker 15 |
| `followup_task` | 323 | 0 | empty_output 312 · failure_marker 11 |
| `write_stdin` | 170 | 0 | exit_code_line 108 · in_flight 60 · failure_marker 2 |

**99.73% of Codex tool results now resolve to a named classification source.** The residual
`unknown` bucket is 0.27% overall and concentrates in the agent-orchestration tools
(`spawn_agent` 8.5%, `wait_agent` 1.5%). Unknown is scored as non-error (same as the old
behaviour), so this residual biases *toward* success — the conservative direction — and, because
the source is recorded per log, it is measurable rather than silent.

## 4. Residual gap — quantified

The families are no longer categorically split, but they are not equal either: **1.48% (Codex) vs
3.19% (Claude)**, a 2.2x remaining asymmetry. Three separable causes, measured:

**(a) Tool mix, not detection — the dominant cause.** `exec` alone is 34,718 of 58,453 in-window
Codex calls (59%) at 0.65%. Excluding `exec` and the poll/messaging tools that have no Claude
analogue (`wait`, `wait_agent`, `send_message`, `list_agents`, `close_agent`,
`interrupt_agent`, `update_plan`):

```
Codex in-window ALL tools        : 58,453 calls    881 err   1.51%
Codex in-window WORK tools only  : 12,532 calls    578 err   4.61%
```

**4.61% vs Claude's 3.19% — Codex is now measurably *worse*, not flawless.** Like-for-like pairs
confirm the symmetry is real:

| Codex tool (re-parsed) | rate | Claude analogue (historical) | rate |
|---|---|---|---|
| `exec_command` | 4.63% | `Bash` | 3.70% |
| `apply_patch` | 3.84% | `Edit` | 4.37% |
| `run` | 7.41% | `Bash` | 3.70% |

**(b) In-flight `exec` polls diluting the rate — a real, bounded residual.** `exec` header shapes
over all 34,699 in-window results:

```
29,421  "Script completed | Wall time N seconds"
 5,048  "Script running with cell ID N | Wall time N seconds"   <-- in-flight, no outcome yet
   204  "Script failed | Wall time N seconds"
    21  "failed to spawn code-mode host ...: No such file or directory"
     5  "aborted by user after Ns"
```
The classifier routes `"Script running with cell ID N"` through `script_lifecycle` → non-error,
whereas the analogous `exec_command` shape (`"Process running with session ID N"`) has its own
`in_flight` source. Those 5,048 (14.5% of `exec` calls) are launches with no outcome yet, counted
in the success denominator. Excluding them: **227/29,670 = 0.77%** rather than 0.65%. Effect on
the family total is ~0.07pp — bounded and small, but it is a genuine loose end for DI-4e's
denominator choice, which should decide explicitly whether in-flight polls belong in a
success-rate denominator at all.

**(c) `exec`'s signal is harness-level, not per-command — coarser than Claude's by construction.**
`exec` is the code-mode host: its outcome line reports whether the *script* completed, and
per-command exit codes appear inside the body as `--- command N (exit K) ---`. The classifier
deliberately does not scan the body (a command whose stdout mentions `error:` must not be misread
as a failure). Measured cost of that deliberate choice: of 34,469 `exec` results classified OK,
only **2** carry a nonzero per-command exit in the body (7 such markers exist corpus-wide). Upper
bound on the correction is **0.66% → 0.67%** — negligible. The body-scan restriction is therefore
*not* a meaningful source of missed errors; `exec`'s low rate is a property of the tool (one
`exec` call wraps a whole script that usually succeeds), not of the detector.

## 5. Why this number (1.51%) differs from the commit message's 3.85%

Commit `089ab60` reports 3.85% over the **full local corpus** (3,389 files, 189,392 tool results).
This re-measurement reports 1.51% over the **30-day in-window subset** (1,318 files, 58,453 calls).
Both are correct; they weight a different tool mix:

| tool | full-corpus name mentions | in-window calls |
|---|---|---|
| `exec_command` | 110,369 | 10,849 |
| `exec` | 35,182 | 34,718 |
| `apply_patch` | 11,393 | 391 |
| `shell_command` | 5,827 | — |

**34,718 of 35,182 `exec` calls (98.7%) fall inside the last 30 days** — `exec` (the code-mode
host) is a recent addition. The full corpus is `exec_command`-weighted (4.63%, the higher-signal
shape); the routing window is `exec`-weighted (0.65%, the coarse harness shape). Per-tool rates
agree closely across the two measurements (`exec_command` 4.38% full-corpus vs 4.63% in-window;
`apply_patch` 4.37% vs 3.84%), which is what confirms the difference is mix and not a
measurement error. **DI-4e must use the in-window figure**, because the rollup's window is 30
days — and must expect this ratio to keep moving as `exec` adoption grows.

## 6. Scope boundary — verified unchanged

`routing_rollup` still emits `success_rate=None`
(`backend/application/services/agent_queries/routing_rollup.py:921`). Commit `089ab60` touches
exactly 5 files, none of them `routing_rollup.*`:

```
backend/parsers/platforms/codex/parser.py                     |  14 +-
backend/parsers/platforms/codex/tool_outcome.py               | 298 +++
backend/tests/fixtures/codex_tool_error_payloads.jsonl        |  15 +
backend/tests/fixtures/codex_tool_error_payloads.provenance.json | 60 +
backend/tests/test_codex_tool_error_detection.py              | 244 +++
```

`backend/tests/test_codex_tool_error_detection.py` — 19 passed, 17 subtests passed.

No write was issued against the node database at any point in this measurement (read-only
`asyncpg.fetch` only).

## 7. What this changes for DI-4b's verdict, and what it does not

**Closed.** The named precondition in `tool-failures-findings.md` § "Verdict Contribution" —
*"fixing the Codex tool-result error-detection heuristic (codex/parser.py:1035) and re-measuring
family-split informativeness"* — is now satisfied and measured. The categorical
confound is gone: GPT/Codex went 0/37 → 33/37 informative, and on directly comparable work tools
Codex reads 4.61% against Claude's 3.19%, i.e. the signal can now rank either family either way.
The specific failure mode DI-4d existed to prevent — `weight_failure` (0.5, the largest merge
term) steering toward GPT/Codex *by construction* — no longer applies.

**Still open, unaffected by this fix.** Two of the four findings in the parent leg are orthogonal
to error detection and remain exactly as measured:

1. **Perverse incentive.** 4,462 of 4,687 sessions with a recorded tool failure (95.2%) still
   reached `completed`. The aggregate counters carry no retry linkage, so recovered and fatal
   failures are indistinguishable. Fixing detection makes this *more* consequential, not less —
   there are now Codex failures to be mis-weighted too.
2. **Attributability (model's fault vs. environment's fault).** `session_logs` is still 0 rows
   system-wide, so per-call error text is unavailable in the DB. Note the fix now records
   `toolStatusSource` on the parsed log, which is a step toward this — but it is not persisted to
   any table, so it is not yet queryable.

Additionally: **historical rows are still wrong.** Every pre-fix `session_tool_usage` row for a
Codex session records 100% success. DI-4e cannot read a correct Codex success_rate out of the DB
until the affected sessions are re-parsed; a backfill (re-sync of Codex sessions) is a
prerequisite, not an optimisation. This re-measurement demonstrates the fix works by re-parsing
in-process — it did not and must not write those corrected counts to the node DB.

## Confidence

**0.88** — the denominator was independently re-derived and matches at 188; the "after" column
comes from a real re-parse at 99.9% JSONL coverage of the affected keys with call totals agreeing
to within 3%; detection coverage, the residual gap, and the 1.51%-vs-3.85% discrepancy were each
mechanically explained with a query or a payload-shape census rather than asserted. Not higher
because (a) the 1,318-file re-parse ran in-process rather than through the full sync engine, so
`upsert_tool_usage`'s `int(count * successRate)` truncation is modelled as `round()` and could
shift per-session counts by ±1 call; (b) the full-corpus cross-check of the 3.85% figure was
started but stopped for runtime, so that number is corroborated only indirectly via per-tool rate
agreement and the tool-mix census; and (c) whether in-flight `exec` polls belong in the
success-rate denominator is a judgement call left to DI-4e, not settled here.
