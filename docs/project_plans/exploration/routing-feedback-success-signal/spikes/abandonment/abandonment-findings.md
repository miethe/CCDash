---
doc_type: spike_findings
leg_id: abandonment
title: "Abandonment Leg — Active-Never-Completed Sessions as a Failure Signal"
status: complete
confidence: 0.85
created: 2026-08-03
feature_slug: routing-feedback-success-signal
related_documents:
  - docs/project_plans/exploration/routing-feedback-success-signal/routing-feedback-success-signal-charter.md
  - docs/project_plans/exploration/routing-feedback-success-signal/spikes/SHARED-CONTEXT.md
  - docs/project_plans/design-specs/routing-feedback-router-merge-handoff.md
---

# Abandonment Leg — Findings

## Question

Are `active` sessions that never reach `completed` a usable negative signal for routing feedback,
or just watcher lag? (Charter leg `abandonment`; DI-4b.)

## Method

All queries run read-only against the node Postgres (`postgresql://ccdash:ccdash@10.42.10.76:5440/ccdash`)
via `/tmp/rfss/q.py`, 2026-08-03. Denominator (188 keys clearing `min_sample=5` in the 30-day
window) taken from `SHARED-CONTEXT.md` §2, not re-derived.

### 1. Age distribution of `active` sessions (all-time, `status='active'`)

Hand-verification of the text→timestamp cast first (two rows, newest and oldest):

```sql
SELECT status, updated_at, ended_at, started_at, created_at
FROM sessions WHERE status='active' ORDER BY updated_at DESC LIMIT 5;
--END
SELECT status, updated_at, ended_at, started_at, created_at
FROM sessions WHERE status='active' ORDER BY updated_at ASC LIMIT 5;
```
Newest row: `updated_at="2026-08-03T16:45:11Z"` (today — sane). Oldest row:
`updated_at="2026-06-27T19:54:21Z"` (~37 days before "today", 2026-08-03 — sane, and notably
`ended_at` is populated even on this `active` row, confirming `ended_at` is a last-write timestamp,
not a "session ended cleanly" marker).

Bucketed age (all 594 all-time `active` rows, `NOW() - updated_at`):

```sql
SELECT
  CASE
    WHEN (EXTRACT(EPOCH FROM NOW()) - EXTRACT(EPOCH FROM to_timestamp(updated_at,'YYYY-MM-DD"T"HH24:MI:SS'))) < 3600 THEN '<1h'
    WHEN ... < 21600 THEN '1-6h'
    WHEN ... < 86400 THEN '6-24h'
    WHEN ... < 604800 THEN '1-7d'
    WHEN ... < 2592000 THEN '7-30d'
    ELSE '>30d'
  END AS bucket, COUNT(*) AS n
FROM sessions WHERE status='active' GROUP BY bucket ORDER BY n DESC;
```

| Bucket | n | % of 594 |
|---|---|---|
| 7-30d | 314 | 52.9% |
| >30d | 139 | 23.4% |
| 1-7d | 89 | 15.0% |
| <1h | 25 | 4.2% |
| 6-24h | 17 | 2.9% |
| 1-6h | 10 | 1.7% |

`MIN(updated_at)=2026-06-27T19:54:21Z`, `MAX(updated_at)=2026-08-03T16:45:11Z`, n=594, 0 null/empty
`updated_at`. Cross-check against `SHARED-CONTEXT`'s in-window figure: summing `<1h..7-30d`
(<30 days old) = 455, vs. the shared-context's independently-measured in-window `active` count of
454 — within 1 row (boundary rounding between `NOW()` and the `to_char` cutoff used there). This
confirms the cast is trustworthy.

**Verdict on this sub-question: not watcher lag in the narrow sense.** Only 8.8% (52/594) are
under 24h old. The overwhelming majority (76.3%) are 7+ days stale, and nearly a quarter are over
30 days stale. If this were transient sync/watcher catch-up lag, the distribution would concentrate
near 0. It does not — there is a real, large stale tail. But "not lag" does not by itself mean
"a genuine outcome signal" — see §2.

### 2. Is `active` even a terminal-state signal? (code path)

Read directly (not inferred): `backend/parsers/platforms/claude_code/parser.py:1648-1672`
(`_derive_session_status`), `_ACTIVE_SESSION_WINDOW_SECONDS = 10 * 60` (line 101), and
`backend/db/sync_engine.py` (`_sync_single_session`, ~line 4967-4972).

```python
def _derive_session_status(entries, path) -> str:
    if not entries:
        return "completed"
    last = entries[-1]
    if last.type == "system":
        if "durationMs" in last: return "completed"
        if last.subtype in _TERMINAL_SYSTEM_SUBTYPES: return "completed"
    age_seconds = time.time() - path.stat().st_mtime
    if age_seconds <= _ACTIVE_SESSION_WINDOW_SECONDS:  # 600s
        return "active"
    return "completed"
```

This is a **one-shot decision made at parse time**, keyed on the file's mtime *at that moment*.
`sync_engine.py`'s `_sync_single_session` skips re-parsing a session file whose mtime has not
changed since the last cached parse (`if cached and cached["file_mtime"] == mtime: return False`),
and no production sync path passes `force=True` (all call sites in
`backend/adapters/jobs/runtime.py` use the `force=False` default). There is no periodic
reconciliation job that walks existing `active` rows and re-evaluates them against elapsed
wall-clock time — verified by tracing every call site of `_sync_single_session`/`sync_project`.

**Consequence**: `active` is not a state a session is "in" — it is a stamp frozen at the moment of
the last file write that didn't end in a terminal system entry. If the underlying process crashes
or is interrupted (Ctrl-C, network death, laptop closed) before a terminal system entry is written,
and the file is never touched again, the row is stamped `active` **permanently** — it will never
transition to `completed` on its own, no matter how much wall-clock time passes, because nothing
re-parses an unchanged file. Conversely, plenty of genuinely-finished sessions likely also lack a
recognized terminal marker and simply age past the 10-minute window at next parse, landing in
`completed` by default — i.e., `completed` isn't purely "graceful exit" either. **This settles the
question from code, as instructed**: `active` is a parse-time sync artifact (a proxy for
"was the file recently touched," never revisited), not a designed outcome/success signal. This
narrows — but does not simply restate — the handoff §0 finding that `sessions.status` carries only
two non-outcome values; §0 established the value space is not outcome-shaped, this leg establishes
*why* mechanically (freeze-on-last-parse, no re-evaluation).

### 3. Coverage under a stale-active threshold

**Threshold choice**: 7 days, justified from §1's bucket boundaries — the <24h buckets (8.8% of
all active rows) are the closest analog to "still genuinely in flight or freshly orphaned,"
1-7d (15.0%) is an ambiguous middle zone the age-distribution alone can't disambiguate, and 7-30d
(52.9%) plus >30d (23.4%) together comprise the unambiguous stale tail. Using the existing 7-day
buckets already computed avoids inventing a new cutpoint. A 1-day threshold is reported alongside
for sensitivity.

```sql
WITH scoped AS (
  SELECT project_id, skill_name, model, status, updated_at FROM sessions
  WHERE updated_at >= to_char(NOW() - INTERVAL '30 days','YYYY-MM-DD"T"HH24:MI:SS')
),
per_key AS (
  SELECT project_id, skill_name, model, COUNT(*) AS session_count,
         COUNT(*) FILTER (WHERE status='active' AND updated_at < to_char(NOW() - INTERVAL '7 days','YYYY-MM-DD"T"HH24:MI:SS')) AS n_stale_active
  FROM scoped GROUP BY project_id, skill_name, model
)
SELECT COUNT(*) FILTER (WHERE session_count>=5) AS keys_clearing_min_sample,
       COUNT(*) FILTER (WHERE session_count>=5 AND n_stale_active>0) AS derivable_nonzero,
       COUNT(*) FILTER (WHERE session_count>=5 AND n_stale_active=session_count) AS derivable_all_stale,
       COUNT(*) FILTER (WHERE session_count>=5 AND n_stale_active>0 AND n_stale_active<session_count) AS informative_strict
FROM per_key;
```

Result: `keys_clearing_min_sample=188` (matches shared-context exactly), `derivable_nonzero=60`,
`derivable_all_stale=0`, `informative_strict=60`.

Sensitivity (1-day threshold, and the degenerate "any active at all" measure), same query shape:

| Measure | derivable (n>0) | informative (non-constant) | Coverage |
|---|---|---|---|
| stale-active, 7d threshold | 60 | 60 | **60/188 = 31.9%** |
| stale-active, 1d threshold | 78 | 78 | 78/188 = 41.5% |
| "any active" (no staleness filter) | 91 | 91 | 91/188 = 48.4% |

No key has `n_stale_active == session_count` (`derivable_all_stale=0`) — no key is 100% stale-active,
so every derivable key is automatically informative under this definition. That is a mild positive
(no all-1.0 constant-column trap), but the primary failure mode named in the task brief did not
materialize in the opposite direction either: coverage is genuinely capped by *derivability*, not
inflated by a mostly-zero column masquerading as informative.

Magnitude, among the 60 nonzero keys (7d threshold):
```sql
SELECT COUNT(*) FILTER (WHERE n_stale_active>0) AS nonzero_keys,
       ROUND(AVG(n_stale_active::numeric/session_count) FILTER (WHERE n_stale_active>0),4) AS mean_rate,
       ROUND(MIN(...),4) AS min_rate, ROUND(MAX(...),4) AS max_rate,
       SUM(n_stale_active) AS total_stale, SUM(session_count) AS total_in_188
FROM per_key;
```
`mean_rate_nonzero=0.1406`, `min=0.0145`, `max=0.6667`, `total_stale_active_sessions=301` out of
`total_sessions_in_188=6957`.

**Note on the "any active" row**: 48.4% coverage looks closer to the charter's recommended
threshold, but that measure is *not* staleness-based — it is just re-deriving the `completed`/
`active` split already established in handoff §0 as carrying no outcome semantics (2 values only).
It is listed for completeness, not as a candidate; the staleness-gated version (31.9% at 7d,
41.5% at 1d) is the actual abandonment-leg candidate, and both fall short of the charter's
recommended >=50% usable-coverage bar.

### 4. Confound assessment

**Model clustering** — stale-active rate by model, in-window, 7d threshold:

```sql
SELECT model, COUNT(*) AS n_sessions,
       COUNT(*) FILTER (WHERE status='active' AND updated_at < to_char(NOW() - INTERVAL '7 days','YYYY-MM-DD"T"HH24:MI:SS')) AS n_stale,
       ROUND(... ::numeric / COUNT(*), 4) AS stale_rate
FROM sessions WHERE updated_at >= to_char(NOW() - INTERVAL '30 days', ...) GROUP BY model ORDER BY n_sessions DESC;
```

| Model | n_sessions | n_stale | stale_rate |
|---|---|---|---|
| claude-sonnet-5 | 2339 | 52 | 0.0222 |
| claude-opus-4-8 | 1306 | 117 | **0.0896** |
| claude-sonnet-4-6 | 963 | 77 | **0.0800** |
| gpt-5.6-terra | 575 | 1 | 0.0017 |
| claude-haiku-4-5-20251001 | 574 | 46 | **0.0801** |
| gpt-5.6-sol | 478 | 9 | 0.0188 |
| claude-opus-5 | 304 | 0 | 0.0000 |
| gpt-5.5 | 274 | 2 | 0.0073 |

The three highest stale rates (opus-4-8, sonnet-4-6, haiku-4-5-20251001, all ~8-9%) are exactly
the **superseded/legacy** model identifiers in this fleet (per project memory: sonnet-5/opus-5
are the current generation as of 2026-07/08). The current-generation models (sonnet-5, opus-5,
gpt-5.6-terra) show near-zero rates (0.0-2.2%).

**Time clustering** — the raw stale-active rows are not spread evenly across the 30-day window:

```sql
SELECT LEFT(updated_at,10) AS day, model, COUNT(*) AS n
FROM sessions WHERE status='active'
  AND updated_at >= to_char(NOW() - INTERVAL '30 days', ...)
  AND updated_at < to_char(NOW() - INTERVAL '7 days', ...)
GROUP BY day, model ORDER BY day;
```
Result (59 day×model rows): the bulk of the 301 stale-active sessions concentrate in
**2026-07-06 through 2026-07-11** (a ~5-day burst, roughly 190+ of 301 rows), tapering to sparse
single-digit counts per day afterward through 2026-07-24, with nothing after that date.

**Interpretation**: the stale-active rate does not cluster by model *quality* — it clusters by
model *recency* (legacy models used earlier in the window naturally accumulate more elapsed
wall-clock time for an orphaned session to age into "stale," and per §2 these rows never
self-heal) and by a **specific calendar burst** (2026-07-06/11), consistent with a systemic event
(e.g., a harness/infra incident, a bulk migration, or the model-rotation itself producing a wave of
abandoned sessions as users switched clients) rather than per-session, per-model quality variance.
This is the same confound shape the charter flagged for harness-errors: **the router would be
downweighting model recency and a historical incident window, not model quality** — an unmitigable
confound for this candidate as currently derivable, since there is no available covariate to
separate "this key's sessions are old" from "this model performs worse."

**Interaction with the harness-errors leg**: checked whether stale-active sessions and harness-error
entries are the same underlying phenomenon (which would risk double-counting one signal as two
candidates):
```sql
WITH stale AS (SELECT id AS session_id FROM sessions WHERE status='active'
  AND updated_at >= to_char(NOW()-INTERVAL '30 days', ...) AND updated_at < to_char(NOW()-INTERVAL '7 days', ...))
SELECT COUNT(DISTINCT s.session_id) AS stale_total,
       COUNT(DISTINCT sm.session_id) AS stale_with_synthetic_error
FROM stale s LEFT JOIN session_messages sm ON sm.session_id=s.session_id
  AND (sm.agent_name='<synthetic>' OR sm.content ILIKE '%API Error%' OR sm.content ILIKE '%connection closed%');
```
Result: `stale_total=310`, `stale_with_synthetic_error=13` (4.2%). **Minimal overlap** — the
overwhelming majority of stale-active sessions carry no harness-error/synthetic marker at all.
These are largely distinct phenomena (silent abandonment vs. explicit error), not the same signal
seen through two tables — the synthesis should treat them as separate candidates, not collapse or
double-count them.

**Attribution to the model at all**: even setting the clustering confound aside, a session frozen
in `active` state proves only that the file stopped being written — it does not distinguish "the
operator judged the model's output bad and quit," "the operator got distracted/changed their mind/
went to lunch," "the laptop crashed or lost network," or "the session finished normally but the
harness didn't happen to emit a recognized terminal marker" (a parser-coverage gap, not user
behavior). None of these is verifiable from `sessions` alone, and the 4.2% harness-error overlap
above shows the frozen rows are not predominantly the "explicit error" subtype where infra-vs-model
attribution would at least be arguable.

## Verdict Contribution

**no-go** for this leg as a standalone `success_rate`/`regression_rate` candidate:

1. Coverage (31.9% at the age-distribution-justified 7-day threshold, 41.5% at 1-day) falls below
   the charter's recommended >=50% usable-coverage bar in both derivable-and-informative framings.
2. The one measure that approaches 50% ("any active," 48.4%) is not a staleness-based candidate at
   all — it is a relabeling of the `completed`/`active` split handoff §0 already ruled out.
3. Confound is unmitigable with data on hand: stale-active rate clusters by model *recency* and a
   specific ~5-day calendar burst, not by anything attributable to model quality, and there is no
   available covariate to separate the two.
4. Even where a stale-active rate is technically derivable, the underlying `active` value is a
   parse-time freeze artifact (§2, from code) rather than a designed or reliable outcome signal —
   consistent with, and mechanically explaining, the pre-existing handoff §0 finding.

This leg does not block a `go` for another leg, but on its own it cannot supply the failure-rate
term. Recommend: leave `success_rate`/`regression_rate` null pending the other three legs'
verdicts; do not use abandonment/staleness as a fallback if the other legs also come back no-go.

## Confidence

**0.85** — every quantitative claim above is backed by a query actually run against the node
Postgres with pasted output (denominator cross-checked against `SHARED-CONTEXT.md` independently
and matched within 1 row); the code-path claim is backed by direct file:line reads of
`_derive_session_status` and the sync-engine skip condition, not inference. The 0.15 discount is
for: (a) the "systemic burst" interpretation of the 2026-07-06/11 clustering is a plausible
reading of the calendar data, not confirmed against an external incident record; (b) the confound
section's model-recency framing assumes the project's model-rotation timeline from prior memory
rather than an in-DB verification of "when was each model current."
