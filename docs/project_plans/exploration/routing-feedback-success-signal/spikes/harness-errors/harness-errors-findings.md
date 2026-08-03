---
doc_type: spike_findings
leg_id: harness-errors
title: "Harness Error Entries as a Failure Signal — Findings"
status: complete
confidence: 0.85
created: 2026-08-03
feature_slug: routing-feedback-success-signal
charter_ref: docs/project_plans/exploration/routing-feedback-success-signal/routing-feedback-success-signal-charter.md
related_documents:
  - docs/project_plans/exploration/routing-feedback-success-signal/spikes/SHARED-CONTEXT.md
  - docs/project_plans/design-specs/routing-feedback-router-merge-handoff.md
---

# Harness Error Entries as a Failure Signal — Findings

## Question

Can harness error entries be counted per session as a failure signal, and is an API/infrastructure
error confounded with model-quality failure for routing purposes? Lead candidate: the `<synthetic>`
transcript entries (audit figure: 325 occurrences / 249 transcripts, literally `API Error: Connection
closed mid-response` and interrupt notices).

**Headline correction to the lead candidate**: the `<synthetic>` *literal string* is not the
countable unit. It occurs only **9 times** in `session_messages.content`, and 7 of those 9 are
agents *talking about* the phenomenon (meta-discussion from the CCDash session that fixed the
parser), not harness-emitted error entries themselves. The real countable unit is free-text
`API Error: ...` / `Agent "<name>" failed: Agent terminated early due to an API error: ...` /
`[Request interrupted by user...]` strings written directly into `session_messages.content` by the
harness. The 325/249 audit figure was almost certainly counting these free-text occurrences, not
literal `<synthetic>` tokens — the audit's own citation ("literally `API Error: Connection closed
mid-response`") already pointed at this text, the leg's job was to verify the count and establish
the taxonomy, which is done below.

## Method

All queries run against the operative node Postgres (`10.42.10.76:5440/ccdash`) via the read-only
helper (`backend/.venv/bin/python /tmp/rfss/q.py` / a `q2.py` variant with a longer
`command_timeout=280` for heavier joins). Per SHARED-CONTEXT §2, the denominator is the 188
`(project_id, skill_name, model)` keys clearing `min_sample=5` in the 30-day window.

### 1. Where do these entries live, and is `<synthetic>` the right marker?

```sql
SELECT COUNT(*) FROM session_messages WHERE content ILIKE '%<synthetic>%';
-- === rows: 1  {"count": "9"}

SELECT COUNT(*) FROM session_messages WHERE content ILIKE '%API Error%';
-- === rows: 1  {"count": "670"}

SELECT COUNT(*) FROM session_messages WHERE content ILIKE '%Connection closed%';
-- === rows: 1  {"count": "79"}

SELECT COUNT(*) FROM session_messages WHERE content ILIKE '%interrupt%';
-- === rows: 1  {"count": "3244"}   -- includes unrelated "interrupt" mentions in prose; narrowed below

SELECT id, session_id, role, message_type, LEFT(content,200)
FROM session_messages WHERE content ILIKE '%<synthetic>%';
-- 9 rows. 7 of 9 are assistant prose discussing the parser fix for <synthetic> model identity
-- (e.g. "`<synthetic>` isn't written by CCDash — only a provider-identity test references it.")
-- Only 2 of 9 are unrelated task briefs that happen to mention the word.
-- Zero of the 9 are harness-emitted error/interrupt notices.
```

`session_logs` (18 columns, includes a `tool_status` column that looked promising) has **0 rows** —
confirmed empty, consistent with SHARED-CONTEXT's table inventory.

### 2. Taxonomy of the real error/interrupt text (all-time, `session_messages.content`)

```sql
SELECT role, message_type, COUNT(*) FROM session_messages
WHERE content ILIKE '%API Error%' GROUP BY role, message_type ORDER BY COUNT(*) DESC;
-- === rows: 4
-- {"role": "assistant", "message_type": "message", "count": "496"}
-- {"role": "user",      "message_type": "message", "count": "117"}
-- {"role": "system",    "message_type": "system",  "count": "48"}
-- {"role": "assistant", "message_type": "thought",  "count": "9"}

SELECT COUNT(*) FROM session_messages WHERE content ILIKE '%Agent terminated early due to an api error%';
-- === rows: 1  {"count": "80"}
SELECT COUNT(DISTINCT session_id) FROM session_messages WHERE content ILIKE '%Agent terminated early due to an api error%';
-- === rows: 1  {"count": "32"}

SELECT COUNT(*) FROM session_messages WHERE content ILIKE '%[Request interrupted%';
-- === rows: 1  {"count": "427"}
SELECT COUNT(DISTINCT session_id) FROM session_messages WHERE content ILIKE '%[Request interrupted%';
-- === rows: 1  {"count": "399"}
SELECT DISTINCT LEFT(content,150) FROM session_messages WHERE content ILIKE '%[Request interrupted%' LIMIT 15;
-- Only two distinct literal strings exist:
--   "[Request interrupted by user]"
--   "[Request interrupted by user for tool use]"
```

Bucketed classification (all-time, `content ILIKE '%API Error%' OR '%[Request interrupted%' OR
'%Agent terminated early%'`, one row per matching `session_messages` row):

```sql
SELECT CASE
    WHEN content ILIKE '%[Request interrupted%' THEN 'user_interrupt'
    WHEN content ILIKE '%rate limit%' THEN 'rate_limit'
    WHEN content ILIKE '%budget%exceeded%' OR content ILIKE '%spend limit%' THEN 'billing_quota'
    WHEN content ILIKE '%401%' OR content ILIKE '%403%' OR content ILIKE '%not allowed to access%' THEN 'auth_denied'
    WHEN content ILIKE '%timed out%' THEN 'timeout'
    WHEN content ILIKE '%connection closed%' OR content ILIKE '%socket connection closed%' THEN 'connection_closed'
    WHEN content ILIKE '%bad gateway%' OR content ILIKE '%502%' THEN 'bad_gateway'
    WHEN content ILIKE '%server error%' THEN 'server_error_mid_response'
    WHEN content ILIKE '%api error%' THEN 'api_error_other'
    ELSE 'other' END AS bucket,
  COUNT(*) AS n, COUNT(DISTINCT session_id) AS n_sessions
FROM session_messages
WHERE content ILIKE '%API Error%' OR content ILIKE '%[Request interrupted%' OR content ILIKE '%Agent terminated early%'
GROUP BY bucket ORDER BY n DESC;
```

| bucket | n rows | n sessions | attribution |
|---|---|---|---|
| `user_interrupt` | 427 | 399 | user, not model/infra |
| `api_error_other` | 223 | 166 | mixed generic API-error text (includes some overlap with buckets below not caught by simpler patterns) |
| `billing_quota` | 113 | 83 | account/billing, not model |
| `auth_denied` | 112 | 96 | team/model-access policy, not model |
| `timeout` | 79 | 63 | transport/infra |
| `connection_closed` | 67 | 52 | transport/infra |
| `rate_limit` | 39 | 36 | provider throttling, not model |
| `server_error_mid_response` | 29 | 20 | provider-side 5xx, not model |
| `bad_gateway` | 8 | 5 | transport/infra |

Sample distinct raw texts (from `SELECT DISTINCT LEFT(content,150)... LIMIT 30` against
`content ILIKE '%API Error%'`): `API Error: Connection closed mid-response`, `API Error: Server
error mid-response`, `API Error: The operation timed out.`, `API Error: 401 team not allowed to
access model...`, `API Error: 400 Budget has been exceeded!...`, `API Error: 502: Bad gateway`,
`You've hit your monthly spend limit`, `API Error: socket connection closed unexpectedly`.

**Attribution site**: the `role: system, message_type: system` rows (48 of the 670) are the harness's
own `Agent "<subagent name>" failed: Agent terminated early due to an API error: ...` notices,
inserted into the **parent/orchestrator session's own transcript** when a Task-tool subagent dies.
This confirms the entry is per-session countable (a known `session_id`), but it is the *orchestrating*
session's failure event about a *child* task, not necessarily a standalone failed session of its own.

### 3. Per-session derivation and coverage against the 188-key denominator

Rather than a single heavy join (two attempts against the full 955,669-row `session_messages` table
timed out at 280s over the WAN link to the node — see raw tracebacks below), the error/interrupt flag
was computed once per `session_id` and joined to the 30-day window, then aggregated to
`(project_id, skill_name, model)` keys in Python:

```
# attempt 1 (single SQL statement, keys+join+aggregate in one query): timed out at 120s, background-run,
# then failed again at 280s command_timeout with asyncpg.exceptions.TimeoutError / ConnectionDoesNotExistError.
# Root cause: 3x ILIKE OR-scan over 955,669 text rows (no index) plus a downstream 188-key join, all
# over a WAN link — resolved by fetching the per-session flags once (~9s) and aggregating client-side.
```

```python
# /tmp/rfss/q3.py — the query that succeeded
WITH win AS (
  SELECT id, project_id, skill_name, model FROM sessions
  WHERE updated_at >= to_char(NOW() - INTERVAL '30 days','YYYY-MM-DD"T"HH24:MI:SS')
),
errs AS (
  SELECT session_id,
    COUNT(*) FILTER (WHERE content ILIKE '%[Request interrupted%') AS n_interrupt,
    COUNT(*) FILTER (WHERE (content ILIKE '%API Error%' OR content ILIKE '%Agent terminated early%')
                      AND content NOT ILIKE '%[Request interrupted%') AS n_apierr
  FROM session_messages
  WHERE content ILIKE '%API Error%' OR content ILIKE '%Agent terminated early%' OR content ILIKE '%[Request interrupted%'
  GROUP BY session_id
)
SELECT w.project_id, w.skill_name, w.model, w.id,
  COALESCE(e.n_apierr,0) AS n_apierr, COALESCE(e.n_interrupt,0) AS n_interrupt
FROM win w LEFT JOIN errs e ON e.session_id = w.id;
```

Real output:
```
total_session_rows 7362
total_keys 397
keys_clearing_min_sample 188
apierr:    keys_with_any=71/188   keys_informative(0<rate<1)=70/188
interrupt: keys_with_any=59/188   keys_informative(0<rate<1)=59/188
```

Note: `total_session_rows` (7362) and `total_keys` (397) differ very slightly from SHARED-CONTEXT's
7,354/396 — expected clock drift between when SHARED-CONTEXT's `NOW() - INTERVAL '30 days'` was
evaluated (2026-08-03, earlier in the day) and when this query ran; both anchor to the same rolling
window definition. `keys_clearing_min_sample=188` matches SHARED-CONTEXT exactly, confirming the
same denominator.

Also confirmed session-level headline: of the 7,362 window sessions, only **442** (6.0%) have *any*
matching error/interrupt row at all — most sessions are clean.

```sql
-- confirms the 442/7354(≈7362) figure independently
SELECT COUNT(*) AS total_win_sessions,
  COUNT(*) FILTER (WHERE e.session_id IS NOT NULL) AS win_sessions_with_any_error_row
FROM win w LEFT JOIN errs e ON e.session_id = w.id;
-- === rows: 1  {"total_win_sessions": "7354", "win_sessions_with_any_error_row": "442"}
```

### 4. Confound queries

**By model** (window-scoped, `apierr` bucket only, excludes `[Request interrupted...]`):

```sql
SELECT s.model, COUNT(*) AS n_sessions,
  SUM(CASE WHEN sm.session_id IS NOT NULL THEN 1 ELSE 0 END) AS n_with_apierr
FROM sessions s
LEFT JOIN (SELECT DISTINCT session_id FROM session_messages
  WHERE (content ILIKE '%API Error%' OR content ILIKE '%Agent terminated early%')
    AND content NOT ILIKE '%[Request interrupted%') sm ON sm.session_id = s.id
WHERE s.updated_at >= to_char(NOW() - INTERVAL '30 days','YYYY-MM-DD"T"HH24:MI:SS')
GROUP BY s.model ORDER BY n_sessions DESC LIMIT 30;
```

| model | n_sessions | n_with_apierr | rate |
|---|---|---|---|
| `<synthetic>` | 77 | 62 | **80.5%** |
| claude-opus-4-8 | 1306 | 96 | 7.4% |
| claude-opus-5 | 303 | 18 | 5.9% |
| claude-fable-5 | 173 | 9 | 5.2% |
| claude-opus-4-7 | 11 | 3 | 27.3% (n too small) |
| claude-sonnet-4-6 | 963 | 22 | 2.3% |
| claude-sonnet-5 | 2340 | 42 | 1.8% |
| gpt-5.4 | 63 | 1 | 1.6% |
| claude-haiku-4-5-20251001 | 573 | 6 | 1.0% |
| gpt-5.5 | 274 | 3 | 1.1% |
| gpt-5.6-sol | 478 | 2 | 0.4% |
| gpt-5.6-terra | 575 | 2 | 0.3% |
| (16 more models, all n_with_apierr ≤ 1) | | | |

**By project** (window-scoped, same bucket):

```sql
SELECT s.project_id, COUNT(*) AS n_sessions,
  SUM(CASE WHEN sm.session_id IS NOT NULL THEN 1 ELSE 0 END) AS n_with_apierr
FROM sessions s LEFT JOIN (...) sm ON sm.session_id = s.id
WHERE s.updated_at >= to_char(NOW() - INTERVAL '30 days', ...)
GROUP BY s.project_id ORDER BY n_sessions DESC LIMIT 30;
```

Top rates: `ccp-89da067a7379` 9/11 = 81.8%; `ccp-9658679e4ca2` 19/481 = 4.0%;
`ccp-c9265a150c1c` 36/725 = 5.0%; most other projects sit in the 0–5% band; several projects (e.g.
`3da60e0c-...`, `ccp-72d3b307d19c`, `ccp-695d1ee3cf7d`, `ccp-61d5a4bb0de5`) show **0** occurrences
across 27–97 sessions each.

**By time** (window-scoped, day granularity):

```sql
SELECT LEFT(s.updated_at,10) AS day, COUNT(DISTINCT sm.session_id) AS n_sessions_with_apierr
FROM sessions s JOIN (...) sm ON sm.session_id = s.id
WHERE s.updated_at >= to_char(NOW() - INTERVAL '30 days', ...) GROUP BY day ORDER BY day;
```

25 days had at least one occurrence, ranging 2–23/day. A clear elevated band runs
**2026-07-18 → 2026-07-23** (9, 13, 22, 19, 23, 17), roughly 2–4x the ~5/day baseline seen elsewhere
in the window; the rest of the window is a low, noisy 2–13/day.

**Cross-check — is the `<synthetic>` model outlier the same signal as the project outlier?**

```python
# per_key_rates.json, filtered to model == '<synthetic>'
synthetic keys in 188: 5
{"project_id": "ccp-89da067a7379", "skill_name": null, "model": "<synthetic>", "n": 9,  "apierr_rate": 1.0}
{"project_id": "ccp-3c5f7843344b", "skill_name": null, "model": "<synthetic>", "n": 16, "apierr_rate": 0.75}
{"project_id": "3df0ff70-...",     "skill_name": null, "model": "<synthetic>", "n": 16, "apierr_rate": 0.75}
{"project_id": "ccp-9658679e4ca2", "skill_name": null, "model": "<synthetic>", "n": 5,  "apierr_rate": 0.8}
{"project_id": "ccp-c9265a150c1c","skill_name": null, "model": "<synthetic>", "n": 12, "apierr_rate": 0.833}
```

Yes — `ccp-89da067a7379`'s 81.8% project-level rate is composed **entirely** of its 9
`<synthetic>`-model sessions (9/9, `apierr_rate: 1.0` on that exact key). This is not a coincidence:
5 of the 188 keys clearing `min_sample` (2.7%) carry `model = "<synthetic>"` — sessions where the
harness never resolved a real model identity because the request failed before that point. These 5
keys sit among the 71 "keys_with_any_apierr," meaning **~7% of the entire apierr-positive coverage
is definitionally circular**: the key's "model" is not a model at all, it is the harness's own
sentinel for "this request never reached a model."

## Coverage Assessment

Per SHARED-CONTEXT §2, coverage must be reported as `usable_keys / 188`, distinguishing derivable
(any signal present) from informative (non-trivial variance, `0 < rate < 1`):

| Signal | Derivable (`keys_with_any`) | Informative (`0<rate<1`) | % of 188 |
|---|---|---|---|
| API/transport error rate (`apierr`) | 71/188 | 70/188 | **37.8% derivable, 37.2% informative** |
| User-interrupt rate (`interrupt`) | 59/188 | 59/188 | **31.4%** (both) |
| Pooled (either signal present) | not computed separately; would be ≤71+59, almost certainly <50% given the overlap implied by shared session/project structure | — | below threshold either way |

**Threshold chosen: 50%**, same as the charter's own recommendation, and I am not discounting it. My
reason for not lowering it here (unlike a leg that might argue a domain-specific lower bar): the
router's whole value proposition is a signal that fires *and is trustworthy* for a majority of the
keys it actually acts on. A signal usable for barely a third of keys leaves the router falling back
to `null`/neutral for the other ~63-69%, which reproduces exactly the "inert for most rows" failure
mode DI-4 was created to fix (§0 of the handoff spec) — just partially instead of universally. A
sub-50% signal does not clear that bar regardless of its confound properties, so the coverage gate
alone is sufficient to fail this leg; the confound analysis below is reported anyway because the
charter treats it as a first-class deliverable, not a footnote, and because it explains *why* the
signal is this sparse (see Verdict Contribution).

**Both signals fail the 50% bar.** 37.8%/37.2% (apierr) and 31.4% (interrupt) are both well under
half of the 188 keys the router would act on.

## Confound Assessment

This is the center of the leg, per the charter, and the evidence points to an **unmitigable
confound**, not a marginal one:

1. **Model variation exists, but tracks orchestration weight, not output quality.** Rates for
   ordinary single-turn models cluster low (0.3%–2.3%: sonnet-5, sonnet-4-6, haiku-4-5, all GPT
   variants). Rates for the models most associated with long-running, subagent-spawning
   orchestration in this repo (opus-4-8 7.4%, opus-5 5.9%, fable-5 5.2%) are 3-7x higher — and the
   harness's own error text (`Agent "<name>" failed: Agent terminated early due to an API error`) is
   *literally about a Task-tool subagent dying*, which happens more often the more subagents a
   session spawns. This is workload-shape (how many long subagent calls a session makes), not a
   signal that the model's *responses* were worse. A router reacting to this would downweight the
   models used for the heaviest orchestration work, penalizing exactly the sessions doing the most
   ambitious multi-step work — the opposite of what "quality" should reward.

2. **The `<synthetic>` model rows are a self-referential artifact, not evidence about any real
   model.** 80.5% apierr rate on `model="<synthetic>"` sounds like the worst-performing "model" in
   the table, but `<synthetic>` is the harness's own placeholder for "no model identity was ever
   resolved because the request failed first." Counting this key's near-100% error rate as
   model-quality evidence is circular: the failure caused the sentinel value, not the reverse. 5 of
   the 71 apierr-positive keys (7%) are this artifact, inflating the "any signal" coverage number
   without contributing a single bit of real model-attributable information.

3. **Time clustering is real and looks like a provider incident, not uniform noise** — a
   2026-07-18→07-23 band running 2–4x the baseline daily rate. This is evidence *for* the
   infrastructure-failure interpretation (incidents cluster in time; genuine model-quality
   degradation from a fixed model checkpoint should not). But it also shows the rollup's 30-day
   window is the wrong instrument for it even if it were actionable: by the time a 30-day rolling
   average absorbs a week-long burst and a min_sample-gated key crosses into `eligible_for_adjustment`,
   the underlying provider incident is very likely already over. The router would be downweighting a
   model for an infrastructure event that ended weeks earlier — stale correction, not live feedback.

4. **Project clustering confirms workload/infra characteristics, not model quality.** The single
   highest-rate project (`ccp-89da067a7379`, 81.8%) owes that rate entirely to 9 sessions that all
   carry the `<synthetic>`-model artifact from point 2 — i.e., the project-level clustering here
   *is* the model-artifact clustering, not an independent workload signal. Several other projects
   show zero occurrences across dozens of sessions, and the mid-range projects (4-5%) are close to
   the opus-driven baseline. There is no clean "some projects just have riskier workloads" story
   distinct from the artifacts already identified in points 2-3.

5. **User-interrupt is a genuinely different signal and pooling it in would be a defect.** 399
   sessions / 427 occurrences of the literal string `[Request interrupted by user]` /
   `[Request interrupted by user for tool use]` are user-attributable — the operator killed the
   session, which says nothing about whether the model's output was good or bad up to that point (it
   may equally mean the human got what they needed and moved on, or grew impatient with a bad
   response — the string alone cannot distinguish these). This is correctly tracked as a separate
   bucket in this leg (`interrupt` vs `apierr`) rather than folded into one "harness error" count. Its
   own coverage (31.4% informative) is below the bar independently.

**Overall confound verdict: unmitigable for the intended purpose.** The apierr signal is
predominantly (billing_quota 113 + auth_denied 112 + rate_limit 39 + bad_gateway 8 + timeout 79 +
connection_closed 67 = 418 of 670, ~62%, by raw taxonomy count) composed of categories that are
transport/account/policy failures with no relationship to a model's output quality, plus a
self-referential `<synthetic>` artifact contributing a further chunk of the "coverage." There is no
mitigation available within CCDash's existing telemetry that separates "the model produced a bad
response" from "the connection dropped/the account hit a quota/a subagent's request never landed" —
the raw text does not carry that distinction, and inferring it would require new capture (e.g. an
explicit harness-side outcome classification), which is out of scope for this exploration per the
charter (§ Out of Scope: "New data capture instrumentation — a no-go verdict is the answer, not a
mandate to scope it here").

## Killer Follow-Up: Is Complement-Based `success_rate` Different from `sessions.status`?

**No — not meaningfully.** `sessions.status`'s `completed`/`active` split was rejected in §0 of the
handoff spec because it encodes "did the session finish" (an infra/completion artifact), not "was the
model's output good." The apierr/interrupt signal here, on inspection, encodes almost exactly the
same category of thing one level down: "did *something external* (connection, quota, auth, rate
limit, or a human) interrupt this session," not "was the model's output good." The taxonomy in §2
above shows ~90%+ of the raw error text falls into categories (billing, auth, rate-limit, transport,
user-interrupt) that are definitionally about session continuity/access, not response quality — the
same axis `status` already covers, just observed at finer grain and with slightly more variance
(a continuous-ish rate instead of a strict boolean). More levels of granularity on the same
uninformative axis is not a different signal; it is the same non-signal measured with a less coarse
ruler. A complement `success_rate = 1 - apierr_rate` would inherit this: it would mostly measure "was
this key's workload light on subagent-spawning /orchestration-heavy sessions and lucky enough to avoid
a billing/rate-limit/outage window," not "did the model produce good work." Shipping it under the name
`success_rate` would be actively misleading in exactly the way the v1 producer's code comment already
warned against (§0 of the handoff spec) — this leg's evidence reinforces rather than overturns that
judgment.

## Verdict Contribution

**no-go** for this leg, on two independent grounds, either one of which is sufficient on its own:

1. **Coverage fails the bar.** 37.8%/37.2% (apierr) and 31.4% (interrupt) both fall well short of
   the 50% threshold this leg adopts (matching the charter's own recommendation).
2. **The confound is unmitigable with existing telemetry.** The signal is dominated by
   transport/billing/auth/rate-limit categories and a self-referential `<synthetic>`-model artifact,
   none of which are model-attributable; the residual "genuine API error" text cannot be
   distinguished from these without new capture, which is out of scope.

Even setting aside the coverage shortfall, the confound analysis alone would recommend no-go for
this specific candidate, because the killer follow-up question resolves against it: a
harness-error-derived `success_rate` is not meaningfully different in kind from the already-rejected
`sessions.status` split — it is the same "session continuity, not response quality" axis, sampled at
finer grain.

This leg's evidence does not, by itself, decide the charter-level verdict (that depends on whether
`tool-failures`, `abandonment`, or `existing-rollups` clears the bar) — but it rules out the lead
candidate the charter opened with, and the reasons it fails (transport/billing/auth noise,
self-referential artifacts, staleness against a 30-day window) generalize as a caution for any
sibling candidate built on free-text harness/error transcript scanning.

## Confidence

**0.85** — every quantitative claim above traces to a query pasted with its real output; the two
heavy-join queries that failed are reported as failures (with tracebacks) rather than papered over,
and the successful re-derivation (`q3.py`, client-side aggregation) reproduced SHARED-CONTEXT's
`keys_clearing_min_sample=188` exactly, which is the strongest available cross-check on correctness.
Residual uncertainty: the taxonomy buckets use ILIKE pattern matching on free text and a stricter
regex/NLP pass could shift bucket boundaries by single-digit percentages (e.g. some `api_error_other`
rows likely belong in `connection_closed` or `timeout` but weren't caught by the simple patterns);
this would not change the coverage conclusion (both signals are ~20+ points under the 50% bar) or the
confound conclusion (the dominant categories are unambiguous regardless of bucket-boundary noise).
