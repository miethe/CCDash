# Shared Ground Truth — routing-feedback-success-signal SPIKE legs

Measured by the orchestrator on 2026-08-03 against the **operative** database. Every leg MUST
use these numbers as its denominator rather than re-deriving them, so the four legs' coverage
figures are directly comparable.

## 1. The operative database is the node Postgres — NOT local SQLite

The local `data/ccdash_cache.db` is an empty stub. All measurement runs against:

```
postgresql://ccdash:ccdash@10.42.10.76:5440/ccdash
```

Read-only query helper (already written, use it):

```bash
cd /Users/miethe/dev/homelab/development/CCDash
backend/.venv/bin/python /tmp/rfss/q.py <<'SQL'
SELECT ...;
--END
SELECT ...;
SQL
```
(`--END` on its own line separates multiple statements. Output is JSON lines, capped at 200 rows
per statement.)

**Postgres typing gotcha**: `sessions.updated_at`, `started_at`, `ended_at`, `created_at` are all
`text`, not `timestamptz`. Comparing to `NOW()` raises
`operator does not exist: text >= timestamp with time zone`. Use the text form:

```sql
WHERE updated_at >= to_char(NOW() - INTERVAL '30 days','YYYY-MM-DD"T"HH24:MI:SS')
```

**`sessions.id` is NOT globally unique** — 19,260 rows carry 17,844 distinct ids (measured
2026-08-03). It is unique only per project. Any self-join for parent/root lookups
(`s.subagent_parent_id = p.id`) therefore **fans out and silently inflates counts by hundreds**.
Scope every such join to the composite key:

```sql
-- WRONG: fans out
JOIN sessions p ON s.subagent_parent_id = p.id
-- RIGHT: scope to (id, project_id), or DISTINCT ON when you need one row per parent
JOIN sessions p ON s.subagent_parent_id = p.id AND s.project_id = p.project_id
```

Discovered independently by two DI-4f legs; the first-draft inheritance numbers were wrong by
400–900 rows per bucket before it was caught. The failure is silent — counts come back plausible.

**NULL-join trap**: `skill_name = skill_name` never matches when both sides are NULL. Any key-level
join must use `IS NOT DISTINCT FROM`, or it silently drops exactly the NULL cohort — which is the
cohort under investigation in most of this work. This trap bit the DI-4b orchestrator.

## 2. The key grain and the denominator

The rollup producer's key is **`(project_id, skill_name, model)`** — confirmed in
`backend/db/repositories/routing_rollup.py` (`_NATURAL_KEY_COLUMNS`) and produced by the single
`GROUP BY project_id, skill_name, model` in
`backend/application/services/agent_queries/routing_rollup.py:_fetch_raw_aggregate_rows`.
Note the charter calls this `(source_skill_name × model)`; `source_skill_name` is just
`sessions.skill_name` aliased. **`project_id` is part of the real key** — include it.

Config (`backend/config.py`):
- `CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE` = **5**
- `CCDASH_ROUTING_FEEDBACK_WINDOW_DAYS` = **30**

The canonical denominator query:

```sql
SELECT project_id, skill_name, model, COUNT(*) AS session_count
FROM sessions
WHERE updated_at >= to_char(NOW() - INTERVAL '30 days','YYYY-MM-DD"T"HH24:MI:SS')
GROUP BY project_id, skill_name, model
HAVING COUNT(*) >= 5
```

Measured 2026-08-03:

| Quantity | Value |
|---|---|
| `sessions` rows, all time | 19,178 |
| `sessions` rows in the 30-day window | 7,354 |
| Distinct projects | 24 |
| **All keys in window** | **396** |
| **Keys clearing `min_sample`=5 → THE DENOMINATOR** | **188** |
| Sessions inside those 188 keys | 6,952 |
| Window span, all-time | 2025-08-28 → 2026-08-03 |

**Coverage must be reported as `usable_keys / 188`** — percent of keys clearing min_sample, never
percent of sessions. The charter is explicit that a session-percentage overstates usability for
exactly the keys the router acts on.

"Usable" for a key means: the candidate signal is derivable for that key **and has enough
within-key variance to produce a rate that is not trivially 0.0 or 1.0 for every key**. A column
that is present but constant is coverage without information — report both numbers separately
(derivable-keys vs. informative-keys) and treat the informative count as the coverage that
matters.

## 3. In-window status split (kills any status-based signal, and bounds the abandonment leg)

```
completed  6,900
active       454
```
Only two values, as the handoff spec §0 said. The abandonment leg's 533 figure was all-time; the
in-window figure is 454.

## 4. Tables available (67 total). The ones that plausibly matter

| Table | Relevance |
|---|---|
| `sessions` | the key grain; 83 columns |
| `session_messages` | per-message transcript rows — the harness-errors leg's likely home |
| `session_logs` | log/entry rows |
| `session_tool_usage` | the tool-failures leg's likely home |
| `effectiveness_rollups` | the existing-rollups leg's target (has real success/risk/quality scores) |
| `session_stack_observations` | the skill-attribution join the existing-rollups leg must fix |
| `session_stack_components` | component resolution |
| `session_sentiment_facts` | **unlisted in the charter — a possible 5th candidate; note it if it looks usable** |
| `session_scope_drift_facts` | same |
| `test_results` / `test_runs` | §0 said zero rows — verify, don't assume |
| `commit_correlations` | possible outcome proxy |

Inspect column types before querying (`information_schema.columns`); several `*_at` columns are
`text` on this backend.

## 5. Non-negotiables for every leg

1. **Feasibility only.** Do not implement a derivation, do not write migrations, do not touch
   `backend/` production code. Output is a findings document.
2. **No fabricated numbers.** Every quantitative claim in your findings must be traceable to a SQL
   query you actually ran; paste the query and its real output. If a query fails or a table is
   empty, that is a finding — report it, do not estimate around it.
3. **Confound assessment is a deliverable, not a footnote.** For the error-rate legs especially:
   is the signal attributable to model quality (which the router should react to) or to
   infrastructure/environment (which it should not)? Bring evidence — e.g. does the signal cluster
   by model/time/project in a way that distinguishes the two?
4. **Read-only.** No `INSERT`/`UPDATE`/`DELETE`/`ALTER` against the node database, ever.
5. **State your confidence** (0.0–1.0) at the end of your findings file, with a one-line
   justification.

## 6. Prior art to read (do not re-derive)

- `docs/project_plans/design-specs/routing-feedback-router-merge-handoff.md` §0 (signal-source
  audit — the negative results are already established) and §5.4 (DI-4 scoping).
- `docs/project_plans/exploration/routing-feedback-success-signal/routing-feedback-success-signal-charter.md`
  — the charter, incl. verdict criteria and the deal-killer.
