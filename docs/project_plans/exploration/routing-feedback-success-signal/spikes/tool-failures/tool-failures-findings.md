---
doc_type: spike_findings
leg_id: tool-failures
confidence: 0.85
status: complete
created: 2026-08-03
---

# tool-failures — Tool Use/Result Error Rate as a Failure Signal

## Question

Do `tool_use`/`tool_result` pairs expose a per-session tool error rate usable as a failure
signal for the routing-feedback producer's `success_rate`/`regression_rate` fields?

## Method

All queries run read-only against `postgresql://ccdash:ccdash@10.42.10.76:5440/ccdash` via
`/tmp/rfss/q.py`. Denominator (188 keys clearing `min_sample`=5 in the 30-day window) taken from
`SHARED-CONTEXT.md` and re-derived independently below (matches: 188).

### 1. Where is the truth — is the failure bit persisted at all?

Schema inspection:

```sql
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='session_tool_usage' ORDER BY ordinal_position;
```
→ `project_id text, session_id text, tool_name text, call_count integer, success_count integer, total_ms integer`
— an aggregated `(session_id, tool_name)` counter table. No raw per-call error text.

```sql
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='session_logs' ORDER BY ordinal_position;
```
→ 18 columns including `tool_status`, `tool_output`, `tool_args`, `metadata_json` — this is the
per-call-granularity table the parser is *capable* of writing.

Row counts:

```sql
SELECT count(*) FROM session_tool_usage;                 -- 47759
SELECT count(DISTINCT session_id) FROM session_tool_usage; -- 15490
SELECT count(*) FROM session_logs;                        -- 0
SELECT count(*) FROM session_logs WHERE type='tool';      -- 0
```

**`session_logs` is empty — 0 rows, system-wide.** The per-call detail table that would carry
`tool_output`/raw error text/`tool_status` per individual call is not populated in the operative
DB. Only the aggregated `session_tool_usage` counters (`call_count`, `success_count` per
`(session_id, tool_name)`) survive. This bounds every downstream question: any analysis here is
at session-level aggregate granularity, never at individual-call granularity, and the raw error
message/exception text is unavailable without re-parsing source JSONL (out of scope per
SHARED-CONTEXT §5.1/§5.4).

**Code path — is the error bit genuinely derived from `tool_result.is_error`, or dropped?**

`backend/parsers/platforms/claude_code/parser.py`:
- Line 3279: `is_error = bool(block.get("is_error", False))` — reads the raw Anthropic
  `tool_result` content block's `is_error` field directly from JSONL.
- Line 3367–3372: propagates to `related_log.toolCall.status = "error" if is_error else "success"`
  and `related_log.metadata["toolStatus"]`.
- Lines 3863–3871 (root) / 3795–3804 (fork branches): per-tool counters —
  `tool_total[name] += 1`; `tool_success[name] += 1` only `if status != "error"`.
- Lines 3890–3900: `ToolUsage(successRate=success/total, ...)` emitted per tool per session.

`backend/parsers/platforms/codex/parser.py`:
- Line 1035: `is_error = status in {"error", "failed", "failure"}` — derived from the Codex
  `tool_result` payload's own `status` field (different shape than Anthropic's `is_error` bool).
- Lines 1046–1047: `if is_error: tool_success[name] -= 1` — decrements after the fact.

`backend/db/repositories/{sessions,postgres/sessions}.py::upsert_tool_usage` — writes
`success_count = int(count * successRate)` into `session_tool_usage`. This is a **correctly
wired pipeline in principle** — the parser genuinely extracts an error bit from the raw
`tool_result`/payload and it lands in the DB as an aggregate. The bit is not silently discarded
by design.

### 2. Coverage

Per-session error rate, joined to the (project_id, skill_name, model) key grain, over the 188
keys clearing `min_sample`=5 in the 30-day window:

```sql
WITH per_session AS (
  SELECT session_id, SUM(call_count) AS calls, SUM(success_count) AS successes
  FROM session_tool_usage GROUP BY session_id),
win AS (
  SELECT s.id, s.project_id, s.skill_name, s.model FROM sessions s
  WHERE s.updated_at >= to_char(NOW() - INTERVAL '30 days','YYYY-MM-DD"T"HH24:MI:SS')),
keyed AS (
  SELECT w.project_id, w.skill_name, w.model, w.id, ps.calls, ps.successes,
         CASE WHEN ps.calls > 0 THEN 1.0 - (ps.successes::float / ps.calls) ELSE NULL END AS err_rate
  FROM win w LEFT JOIN per_session ps ON ps.session_id = w.id),
per_key AS (
  SELECT project_id, skill_name, model, count(*) AS session_count,
         count(err_rate) AS n_with_rate, AVG(err_rate) AS mean_err_rate,
         STDDEV(err_rate) AS stddev_err_rate
  FROM keyed GROUP BY project_id, skill_name, model HAVING count(*) >= 5)
SELECT count(*) AS total_keys,
       count(*) FILTER (WHERE n_with_rate >= 1) AS derivable_keys_any_data,
       count(*) FILTER (WHERE n_with_rate::float/session_count >= 0.5) AS derivable_ge50pct,
       count(*) FILTER (WHERE stddev_err_rate > 0.0) AS informative_keys,
       count(*) FILTER (WHERE mean_err_rate = 0.0) AS all_zero_mean_keys,
       count(*) FILTER (WHERE mean_err_rate IS NULL) AS no_data_keys
FROM per_key;
```

Result:

| total_keys | derivable (any data) | derivable (>=50% sessions) | informative (stddev>0) | all-zero-mean | no-data |
|---|---|---|---|---|---|
| 188 | 178 | 168 | 139 | 38 | 10 |

Raw coverage looks strong: **178/188 = 94.7%** derivable, **139/188 = 73.9%** informative. This is
the number a naive read would report. **It is misleading** — see §3.

### 3. Confound assessment — the finding that changes the verdict

**Split by model family, same query, same 188 keys:**

```sql
SELECT CASE WHEN model LIKE 'gpt%' THEN 'gpt/codex-family'
            WHEN model LIKE 'claude%' THEN 'claude-family'
            WHEN model = '<synthetic>' THEN 'synthetic'
            WHEN model = '' THEN 'empty' ELSE 'other' END AS family,
       count(*) AS n_keys,
       count(*) FILTER (WHERE stddev_err_rate > 0) AS informative_keys,
       count(*) FILTER (WHERE mean_err_rate = 0.0) AS zero_mean_keys,
       count(*) FILTER (WHERE mean_err_rate IS NULL) AS no_data_keys
FROM per_key GROUP BY family;
```

| family | n_keys | informative | zero-mean | no-data |
|---|---|---|---|---|
| claude-family | 138 | **137 (99.3%)** | 1 | 0 |
| gpt/codex-family | 37 | **0 (0%)** | 36 | 1 |
| empty model | 8 | 0 | 0 | 8 |
| synthetic | 5 | 2 | 1 | 1 |

**Every single gpt/codex-family key is either constant-zero or has no data at all. Zero of 37 are
informative.** Confirmed at the raw-aggregate level, system-wide (not just windowed):

```sql
SELECT s.model, count(*) n_sessions, sum(stu.call_count) total_calls,
       sum(stu.success_count) total_success
FROM sessions s JOIN session_tool_usage stu ON stu.session_id = s.id
WHERE s.model LIKE 'gpt-%' GROUP BY s.model ORDER BY total_calls DESC;
```
→ **all 16 gpt-family models show `total_calls == total_success`, exactly, with zero exceptions**
(e.g. `gpt-5.5`: 79,195 calls / 79,195 successes across 3,319 sessions; `gpt-5.6-sol`: 33,859/33,859;
same pattern for every one of the 16 rows). The same query for `claude-%` models shows a
consistent nonzero gap for every model (e.g. `claude-sonnet-5`: 125,151 calls / 121,785 successes,
`claude-opus-4-8`: 118,931/114,490).

**This is not evidence that Codex/GPT models never fail a tool call. It is a parser-coverage gap.**
Per-tool-name breakdown confirms the mechanism:

```sql
SELECT tool_name, sum(call_count) calls, sum(success_count) successes,
       round((1.0 - sum(success_count)::numeric/sum(call_count))::numeric,4) err_rate
FROM session_tool_usage GROUP BY tool_name HAVING sum(call_count) > 500 ORDER BY calls DESC;
```

Codex-native tool names (`exec_command`, `exec`, `apply_patch`, `shell_command`, `wait`,
`wait_agent`, `write_stdin`, `spawn_agent`, `shell`, `send_message`, `update_plan`,
`close_agent`) show **exactly 0.0000 error rate, every one, no exceptions** (calls up to 110,369
for `exec_command`). Claude-native tool names (`Bash` 3.70%, `Read` 2.57%, `Edit` 4.37%, `Write`
6.17%, `WebSearch` 7.49%, `Skill` 3.22%, `SendMessage` 1.97%) show consistent nonzero rates. The
`is_error`/`status` extraction path is wired for Anthropic-style `tool_result.is_error` blocks
(claude_code/parser.py:3279) but the Codex `status in {"error","failed","failure"}` heuristic
(codex/parser.py:1035) evidently never matches real Codex tool-result payload shapes — the
downstream `success_count` decrement (line 1047) never fires for any Codex session in this
dataset. Note this is also true for some Claude-orchestration tool names (`wait_agent`,
`spawn_agent`, `close_agent`, `send_message` non-capitalized variants) — the gap is not purely a
Codex/Claude split, it is a per-tool-name detection-coverage gap that happens to align almost
perfectly with the provider boundary in this dataset.

**Confound verdict: unmitigable for the router's primary use case.** The router's core job is
comparing models against each other for the same `(skill, task_class)` — including
cross-provider comparisons (Claude vs GPT-family). A signal that is genuinely variable for one
provider family and a hard-coded zero for another is not a quality signal at all for that
comparison — it would make every GPT/Codex model look strictly better than every Claude model on
this axis, for a reason that has nothing to do with either model's actual tool-call behavior.
This is a stronger, more mechanical version of the "infrastructure vs. model-quality" confound
the charter anticipated: it is not noisy confounding, it is a categorical parser gap that maps
directly onto the exact axis (model/provider) the signal is meant to differentiate.

**Attributability (model's fault vs. environment's fault), within the informative claude-family
subset:** cannot be determined from the DB. `session_logs` (0 rows, §1) is where the raw
`tool_output`/error text and per-call context would need to live to distinguish "hallucinated
path" from "file genuinely absent" from "permission denied." Only the aggregate counts survive.
**This separation requires re-parsing raw JSONL — explicitly out of scope for this leg
(SHARED-CONTEXT §5.1).** Reported as a scoped gap, not estimated around.

**Perverse-incentive check — does raw error rate reward the wrong behaviour?**

```sql
SELECT s.status, count(*) FROM sessions s
JOIN (SELECT session_id, SUM(call_count) c, SUM(success_count) sc
      FROM session_tool_usage GROUP BY session_id) t ON t.session_id = s.id
WHERE t.c > t.sc GROUP BY s.status;
```
→ `active: 225`, `completed: 4462`. **4,462 of 4,687 sessions with at least one recorded tool
failure (95.2%) still reached `completed`.** The aggregate `call_count`/`success_count` counters
carry no retry-linkage — a session that fails once and immediately recovers is indistinguishable,
in this schema, from a session that fails once and never recovers. Both register identically as
"1 failure out of N calls." A raw tool-error rate therefore does reward the wrong behaviour in
exactly the shape the charter worried about: a session that ran more tools and hit (and recovered
from) more transient failures scores strictly worse than a session that ran fewer tools and
happened to avoid any, even when the former is the better outcome. Normalizing by call volume
(which the rate already does) does not fix this — it is a retry-attribution problem, not a scale
problem; only per-call sequencing (unavailable, §1) could distinguish "recovered" from "fatal."

**Within-Claude-family model vs. workload:**

```sql
SELECT skill_name, model, sum(calls) total_calls, sum(successes) total_success,
       round((1.0 - sum(successes)::numeric/sum(calls))::numeric,4) err_rate
FROM ... WHERE skill_name IN ('dev-execution','skillmeat-cli','symbols')
GROUP BY skill_name, model HAVING sum(calls) >= 200 ORDER BY skill_name, err_rate DESC;
```

For `dev-execution` across 5 Claude models: err_rate ranges 2.40%–3.78% (1.6x spread). For
`skillmeat-cli` across 4 models: 1.09%–3.19% (2.9x spread). Per-tool-name rates vary far more
(`ToolSearch` 0.12% vs `WebSearch` 7.49%, a 62x spread) than per-model rates do within the same
skill. This is consistent with the charter's "workload signal wearing a quality mask" concern:
within the one family where the signal is even informative, tool-mix (which tools a
skill/task calls) is a larger driver of variance than which model ran it.

## Findings

1. **The failure bit is genuinely persisted** — this is not a case of the parser discarding an
   error signal. `claude_code/parser.py` correctly extracts `tool_result.is_error` and it lands
   in `session_tool_usage.success_count` as designed.
2. **Coverage is high in the naive read (178/188 derivable, 139/188 "informative") but the
   informative count is a near-total illusion of the provider split**: 137 of those 139
   informative keys are Claude-family; 0 of 37 GPT/Codex-family keys are informative — they are
   uniformly a parser-coverage artifact (constant 0.0), not evidence of flawless tool execution.
3. `session_logs` — the table that would carry per-call detail needed to assess attributability
   (model's fault vs. environment's fault) — has **zero rows system-wide**. That question cannot
   be answered from the operative DB at all.
4. A raw tool-error rate rewards recovery-heavy sessions worse than error-free-but-less-active
   ones (95.2% of failure-containing sessions still complete), the exact perverse-incentive shape
   the charter flagged.

## Coverage Assessment

- **Naive**: 139/188 = **73.9%** informative — clears the charter's ≥50% threshold.
- **Corrected for the provider-split artifact**: 137/188 = **72.9%** informative, but
  concentrated entirely in 137 of 138 Claude-family keys (99.3% within-family) and **0 of 37**
  GPT/Codex-family keys (0% within-family). Reporting only the aggregate number without this
  split would misrepresent the signal as broadly usable when it is provider-siloed.
- **Threshold used**: the charter's own ≥50% is the right bar for *raw* coverage, but this leg
  additionally requires informativeness to hold **within each model family the router would
  compare**, because the router's job is cross-model (often cross-provider) comparison. Judged
  against that bar, the signal fails for exactly the comparisons (Claude model X vs. GPT model Y)
  that most matter to a routing decision.

## Confound Assessment

- **Attributability (model vs. environment)**: cannot be resolved from the DB (`session_logs`
  empty); would require raw JSONL re-parse — out of scope, named rather than estimated around.
- **Cross-provider confound**: unmitigable without a parser fix. The Codex `status` heuristic
  (codex/parser.py:1035, `status in {"error","failed","failure"}`) does not match real Codex
  tool-result payloads in this dataset — verified at 0/37 keys, 0/16 models, system-wide 0 failures
  recorded across 100k+ Codex tool calls. Fixing this is a scoped, bounded parser change (not
  attempted here — read-only feasibility leg), but until fixed, the signal cannot support any
  routing decision that compares a Claude-family model against a GPT/Codex-family model.
- **Perverse incentive**: confirmed present. Raw error rate does not distinguish recovered
  failures from fatal ones; normalizing by call volume does not resolve this since it is a
  retry-attribution gap, not a scale artifact.
- **Workload vs. model-quality**: within the one family where the signal is informative
  (Claude), tool-mix variance (per-tool-name spread up to 62x) dominates over per-model variance
  within the same skill (1.6x–2.9x spread) — consistent with this being partly a workload signal
  wearing a quality mask, not purely a model-quality signal.

## Verdict Contribution

**conditional** — a derivable signal exists and clears the charter's raw coverage bar (73.9%
informative vs. ≥50%), but with an unmitigable cross-provider confound (0% informative for
GPT/Codex-family, entirely a parser gap not a quality finding) and a confirmed perverse-incentive
shape. This leg alone should not carry a `go` verdict for `success_rate`/`regression_rate`:
shipping it as-is would silently bias every routing decision in favor of GPT/Codex models
regardless of their actual tool-call reliability. If this candidate is pursued at all, the named
precondition is fixing the Codex tool-result error-detection heuristic (codex/parser.py:1035) and
re-measuring family-split informativeness — not a fresh signal search. Absent that fix, this
candidate should not be combined into a cross-provider success signal; it could conceivably serve
a Claude-family-only variant, but that is a narrower deliverable than DI-4b asks for.

**Comparative note vs. harness-errors** (provisional — that leg's own findings were not yet
written at the time of this leg): SHARED-CONTEXT records the harness-errors lead candidate at 325
occurrences across 249 transcripts system-wide — a much smaller raw event volume than this leg's
47,759 `session_tool_usage` rows across 15,490 sessions. On raw volume this leg has far more data
to work with. But volume is not the deciding axis: this leg's defect is categorical (an entire
provider family is a parser artifact, not partial confounding), which is a harder defect to
mitigate than a noisy-but-present signal would be. Whether harness-errors' infrastructure-vs-model
confound is more or less severe than this leg's provider-coverage gap should be judged by the
synthesis once that leg's findings land; this leg's contribution is that its own confound is not
merely "risky," it is a **measured zero** for one entire provider family.

## Confidence

0.85 — every quantitative claim above is from a query pasted here, run against the operative node
Postgres, and the provider-split mechanism was independently verified at both the per-model and
per-tool-name level. Confidence is not 1.0 because (a) the comparative note against harness-errors
is provisional pending that leg's own write-up, and (b) the within-Claude-family
workload-vs-model split (§ "Within-Claude-family model vs. workload") is suggestive from three
skill examples, not an exhaustive causal analysis.
