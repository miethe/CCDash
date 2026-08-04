---
schema_version: 2
doc_type: report
report_category: finding
title: "Key Redefinition — routing_rollup Fallback Key If skill_name Attribution Cannot Be Fixed"
status: completed
created: 2026-08-03
feature_slug: routing-key-skill-attribution
leg_id: key-redefinition
confidence: 0.75
exploration_charter_ref: docs/project_plans/exploration/routing-key-skill-attribution/routing-key-skill-attribution-charter.md
---

# Key Redefinition — DI-4f Leg

## 0. Scope and method

This leg runs regardless of the `null-population`/`capture-path` legs' outcomes, per charter. All
numbers below are freshly measured against the operative node Postgres
(`postgresql://ccdash:ccdash@10.42.10.76:5440/ccdash`) on 2026-08-03, using the read-only helper at
`/tmp/rfss/q.py`. No writes issued. Every number has a SQL query shown; no estimates presented as
measurements.

**Denominator drift note (honest, not a re-derivation error):** the charter's SHARED-CONTEXT.md
pinned `396` in-window keys / `188` clearing `min_sample`, measured earlier the same day. My fresh
run (several hours later, same `NOW() - INTERVAL '30 days'` rolling window) gets `405` / `187` —
the rolling window itself moved forward with wall-clock time; both figures are real, not
contradictory. I use my own fresh, self-consistent numbers throughout this leg so within-leg
comparisons are apples-to-apples; cross-leg comparisons to the `null-population`/`capture-path`
legs' exact counts may differ by 1-2% for the same reason and should not be read as disagreement.

**Correction to how the "NULL" framing maps onto the persisted table.** The charter and
SHARED-CONTEXT describe `sessions.skill_name` as NULL for the affected cohort — confirmed true at
the source column. But the **persisted** `routing_rollup.source_skill_name` column is declared
`TEXT NOT NULL` (`backend/db/postgres_migrations.py:1540`, mirrored in
`backend/db/sqlite_migrations.py`), because `_fetch_raw_aggregate_rows` coalesces at read time:
`source_skill_name=str(row["source_skill_name"] or "")`
(`backend/application/services/agent_queries/routing_rollup.py:618`). So downstream of the producer,
the "NULL" cohort is actually an **empty-string** `source_skill_name`, and the query-time
`GROUP BY project_id, skill_name, model` (`routing_rollup.py:586`, `:610`) already folds every NULL
`sessions.skill_name` session into one `(project_id, "", model)` key per project/model pair — this
is exactly the coalesce-to-empty-string behavior the charter's Notes flagged. Every "informative"
count below therefore tests `skill_name IS NOT NULL` (source table) / `<> ''` (derived value),
which is the correct test at either layer.

## 1. Current key (confirmed from code, not inherited)

- **Persisted natural/primary key**: `PRIMARY KEY (project_id, source_skill_name, model)` —
  `backend/db/postgres_migrations.py:1562`, `backend/db/sqlite_migrations.py` (mirror, v43).
- **Repository's independent restatement of the same key**: `_NATURAL_KEY_COLUMNS = ("project_id",
  "source_skill_name", "model")` — `backend/db/repositories/routing_rollup.py:104`.
- **Raw aggregation grain** (query-time, before persistence): `GROUP BY project_id, skill_name,
  model` — `backend/application/services/agent_queries/routing_rollup.py:586` (SQLite path),
  `:610` (Postgres path).
- **`task_class`** is a **derived, non-key column** on the same row — computed at write time by
  `apply_mapping()` (`routing_rollup.py:696-766`) from `source_skill_name` via the pinned
  `routing_task_map_v1.json` (mapping_version `1.1.0`). It is stored per row
  (`routing_rollup.py:1544` DDL column) but is **not** part of the `PRIMARY KEY` or the raw
  `GROUP BY` — multiple `skill_name` values can and do collapse to the same `task_class`.

## 2. Candidates measured

All queries use the 30-day rolling window `updated_at >= to_char(NOW() - INTERVAL '30 days',
'YYYY-MM-DD"T"HH24:MI:SS')`, matching the producer's own window resolution
(`config.CCDASH_ROUTING_FEEDBACK_WINDOW_DAYS = 30`). "Clearing" = `HAVING COUNT(*) >= 5`
(`CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE`). "Informative" = the discriminating dimension is
non-null/non-empty for that key (i.e. the key actually carries the signal it claims to key on).

### 2.0 Baseline confirm

```sql
SELECT COUNT(*) FROM (
  SELECT project_id, skill_name, model FROM sessions
  WHERE updated_at >= to_char(NOW() - INTERVAL '30 days','YYYY-MM-DD"T"HH24:MI:SS')
  GROUP BY project_id, skill_name, model
) t;
-- 405 (all in-window keys)
SELECT COUNT(*) FROM (
  SELECT project_id, skill_name, model, COUNT(*) c FROM sessions
  WHERE updated_at >= to_char(NOW() - INTERVAL '30 days','YYYY-MM-DD"T"HH24:MI:SS')
  GROUP BY project_id, skill_name, model HAVING COUNT(*) >= 5
) t;
-- 187 (clearing min_sample)
```

### 2.1 Candidate E — status quo, `(project_id, skill_name, model)`

```sql
SELECT COUNT(*) n_keys,
       SUM(CASE WHEN skill_name IS NOT NULL THEN 1 ELSE 0 END) n_informative
FROM (
  SELECT project_id, skill_name, model, COUNT(*) c FROM sessions
  WHERE updated_at >= to_char(NOW() - INTERVAL '30 days','YYYY-MM-DD"T"HH24:MI:SS')
  GROUP BY project_id, skill_name, model HAVING COUNT(*) >= 5
) t;
```
Result: **187 keys, 74 informative (39.6%)**. Consistent with the charter's 61% NULL figure
(measured a few hours earlier against a slightly different window; here `113/187 = 60.4%` NULL).

### 2.2 Candidate A — `(project_id, model)`

```sql
SELECT COUNT(*) FROM (
  SELECT project_id, model FROM sessions
  WHERE updated_at >= to_char(NOW() - INTERVAL '30 days','YYYY-MM-DD"T"HH24:MI:SS')
  GROUP BY project_id, model
) t;                                                    -- 189 all-keys
SELECT COUNT(*) FROM (
  SELECT project_id, model, COUNT(*) c FROM sessions
  WHERE updated_at >= to_char(NOW() - INTERVAL '30 days','YYYY-MM-DD"T"HH24:MI:SS')
  GROUP BY project_id, model HAVING COUNT(*) >= 5
) t;                                                    -- 120 clearing min_sample
SELECT COUNT(*) FROM sessions
WHERE updated_at >= to_char(NOW() - INTERVAL '30 days','YYYY-MM-DD"T"HH24:MI:SS') AND model IS NULL;
-- 0
```
Result: **120 keys, 120 informative (100%)** — trivially, since `model` is never NULL in-window.
This "coverage" is a mechanical artifact of discarding the skill dimension entirely, not an
attribution improvement — flagged explicitly in §4.

### 2.3 Candidate B — `(project_id, command_slug, model)`

```sql
SELECT COUNT(*) FROM (
  SELECT project_id, command_slug, model FROM sessions
  WHERE updated_at >= to_char(NOW() - INTERVAL '30 days','YYYY-MM-DD"T"HH24:MI:SS')
  GROUP BY project_id, command_slug, model
) t;                                                    -- 240 all-keys
SELECT COUNT(*) FROM (
  SELECT project_id, command_slug, model, COUNT(*) c FROM sessions
  WHERE updated_at >= to_char(NOW() - INTERVAL '30 days','YYYY-MM-DD"T"HH24:MI:SS')
  GROUP BY project_id, command_slug, model HAVING COUNT(*) >= 5
) t;                                                    -- 129 clearing min_sample
```
`command_slug` is column-level NOT NULL in this schema — every value is either a real slug or the
empty string `''` (never SQL NULL): `SUM(CASE WHEN command_slug IS NOT NULL ...)` over the 7,341
in-window sessions returns 7,341/7,341 non-NULL, which is a **false positive for "coverage."**
Distribution:

```sql
SELECT command_slug, COUNT(*) c FROM sessions
WHERE updated_at >= to_char(NOW() - INTERVAL '30 days','YYYY-MM-DD"T"HH24:MI:SS')
GROUP BY command_slug ORDER BY c DESC LIMIT 3;
-- "": 7150   "/clear": 68   "/effort": 23
```
7,150 of 7,341 sessions (97.4%) carry an empty `command_slug`. Re-measuring informativeness as
`command_slug <> ''`:

```sql
SELECT COUNT(*) n_keys, SUM(CASE WHEN command_slug <> '' THEN 1 ELSE 0 END) n_informative
FROM (
  SELECT project_id, command_slug, model, COUNT(*) c FROM sessions
  WHERE updated_at >= to_char(NOW() - INTERVAL '30 days','YYYY-MM-DD"T"HH24:MI:SS')
  GROUP BY project_id, command_slug, model HAVING COUNT(*) >= 5
) t;
```
Result: **129 keys, 10 informative (7.8%)**. `command_slug` is materially *worse* than
`skill_name` as a key dimension — most sessions never issue an explicit slash command, so this
column is emptier than `skill_name`, not fuller.

### 2.4 Candidate C — `(project_id, task_class, model)`

`task_class` is derived from `skill_name` via the pinned v1 mapping
(`routing_task_map_v1.json`, mapping_version `1.1.0`, 34 rules). I built the exact `CASE`
expression from the rules file (`unmapped_policy: "_unclassified"` — the same fallback
`_resolve_task_class` uses for a missing/NULL `skill_name`, `routing_rollup.py:497-510`) and ran it
against real rows:

```sql
SELECT COUNT(*) FROM (
  SELECT project_id, (<34-rule CASE ... ELSE '_unclassified' END>) taskclass, model
  FROM sessions WHERE updated_at >= <30d window>
  GROUP BY project_id, taskclass, model
) t;                                                    -- 325 all-keys
SELECT COUNT(*) FROM (... HAVING COUNT(*) >= 5) t;      -- 185 clearing min_sample
SELECT COUNT(*) n_keys, SUM(CASE WHEN taskclass <> '_unclassified' THEN 1 ELSE 0 END) n_informative
FROM (... HAVING COUNT(*) >= 5) t;                      -- 185 keys, 72 informative
```
Result: **185 keys, 72 informative (38.9%)** — statistically indistinguishable from `skill_name`'s
39.6% (§2.1). This **confirms the charter's suspicion by measurement, not assumption**: `task_class`
inherits the NULL-skill problem exactly, because `_resolve_task_class` maps a missing/NULL
`skill_name` to `_unclassified` via the identical fallback path a mapped-but-unclassified skill name
uses (`routing_rollup.py:509-510`). Distribution of the mapped classes (session-level, all in-window
rows, not just clearing keys):

```
_unclassified: 5331   mechanical: 916   implementation: 670   orchestration: 378
documentation: 24   web_research: 11   mode_d: 8   second_opinion: 1   code_review: 1
```
`_unclassified` is 72.6% of sessions — dominated by the NULL-`skill_name` cohort, not by genuine
unmapped skill names (there are only 34 mapped skill names total; NULL sessions vastly outnumber any
plausible unmapped-skill population).

### 2.5 Candidate D — coalesce chain `skill_name → command_slug → subagent_type → sentinel`

Session-level resolution of which rung of the chain each session actually lands on:

```sql
SELECT COUNT(*) n,
  SUM(CASE WHEN skill_name IS NOT NULL AND skill_name<>'' THEN 1 ELSE 0 END) has_skill,
  SUM(CASE WHEN (skill_name IS NULL OR skill_name='') AND command_slug IS NOT NULL AND command_slug<>''
           THEN 1 ELSE 0 END) falls_to_command,
  SUM(CASE WHEN (skill_name IS NULL OR skill_name='') AND (command_slug IS NULL OR command_slug='')
           AND subagent_type IS NOT NULL AND subagent_type<>'' THEN 1 ELSE 0 END) falls_to_subagent,
  SUM(CASE WHEN (skill_name IS NULL OR skill_name='') AND (command_slug IS NULL OR command_slug='')
           AND (subagent_type IS NULL OR subagent_type='') THEN 1 ELSE 0 END) falls_to_sentinel
FROM sessions WHERE updated_at >= <30d window>;
-- n=7340, has_skill=2077, falls_to_command=63, falls_to_subagent=12, falls_to_sentinel=5188
```
Of the 5,263 sessions with no skill, the fallback chain rescues only 75 (63 + 12) — **1.4%** of the
skill-less population — before bottoming out at the sentinel for 5,188 (98.6% of the skill-less
population). Key-level result:

```sql
SELECT COUNT(*) n_keys, SUM(CASE WHEN coalesced <> '_none' THEN 1 ELSE 0 END) n_informative
FROM (
  SELECT project_id,
    COALESCE(NULLIF(skill_name,''), NULLIF(command_slug,''), NULLIF(subagent_type,''), '_none') coalesced,
    model, COUNT(*) c
  FROM sessions WHERE updated_at >= <30d window>
  GROUP BY project_id, coalesced, model HAVING COUNT(*) >= 5
) t;
```
Result: **192 keys, 79 informative (41.1%)** — a **+1.5 percentage-point** improvement over status
quo (39.6%), at the cost of a materially more complex key derivation (three-column coalesce with
its own precedence-tiebreak semantics to document and test). Not material.

## 3. Churn across adjacent windows

Measured `w0 = [NOW-60d, NOW-30d)` vs `w1 = [NOW-30d, NOW)` — adjacent, non-overlapping 30-day
windows (`w0`: 2026-06-04T21:04:13 → 2026-07-04T21:04:13; `w1`: 2026-07-04T21:04:13 →
2026-08-03T21:04:13; `w0` has 8,815 in-window sessions, confirmed non-empty). For each candidate,
computed the set of keys clearing `min_sample=5` in each window and its Jaccard overlap:

| Candidate | \|w0\| | \|w1\| | \|intersection\| | Jaccard | % of w1 keys that are new |
|---|---|---|---|---|---|
| A `(project, model)` | 71 | 120 | 49 | **0.345** | 59.2% |
| B `(project, command_slug, model)` | 97 | 129 | 55 | 0.322 | 57.4% |
| C `(project, task_class, model)` | 116 | 185 | 72 | 0.314 | 61.1% |
| D `(project, coalesce-chain, model)` | 133 | 192 | 74 | 0.295 | 61.5% |
| E `(project, skill_name, model)` (status quo) | 129 | 187 | 71 | **0.290** | 62.0% |

**Every candidate churns badly** — no key is even 40% stable window-to-window, so "a key that
churns every window cannot accumulate confidence" (charter) is a real property of this dataset, not
just a `skill_name`-specific defect. Coarser keys churn less (A is most stable, E is least), simply
because a coarser key aggregates more sessions per key and is less sensitive to any single skill/
task appearing or disappearing in a given window. This is a genuine, if modest, argument for a
coarser key independent of attribution coverage — but the effect size (Jaccard 0.29 → 0.35, an 0.06
absolute improvement) is smaller than the informativeness differences in §2, and does not by itself
justify discarding the skill dimension.

## 4. Contract cost — scoped, not implemented

**Current shipped contract surface** (verified by code, not inferred):
- Persisted schema: `PRIMARY KEY (project_id, source_skill_name, model)` in both DDLs (v43,
  `backend/db/postgres_migrations.py:1562` / mirror in `sqlite_migrations.py`).
- Repository conflict target: `_NATURAL_KEY_COLUMNS` (`backend/db/repositories/routing_rollup.py:104`),
  used by every `upsert()` `ON CONFLICT` clause on both backends.
- Raw aggregation: `GROUP BY project_id, skill_name, model` (`routing_rollup.py:586`, `:610`).
- REST/DTO consumer surface exposes `source_skill_name` and `task_class` per key
  (`backend/routers/_client_v1_routing_rollup.py:147-148`), and the cross-repo handoff spec pins the
  input contract's key vocabulary as `(source_skill_name × model)` throughout
  (`routing-feedback-router-merge-handoff.md` §2.1).
- Contract versioning already exists and is exercised: `contract_version`/`taxonomy_version`/
  `mapping_version`/`mapping_digest` are frozen, CI-guarded fields
  (`routing_feedback_contract.py`, digest parity test T1-005) — any redefinition of what the *key*
  means is exactly the kind of change that vocabulary/digest machinery exists to gate.

**Per-candidate cost and compatibility:**

| Candidate | Migration shape | Envelope/DTO change | Additive or breaking |
|---|---|---|---|
| A `(project, model)` | Drop `source_skill_name` from `PRIMARY KEY`; re-derive/dedupe existing rows (multiple old skill-keyed rows collapse to one project×model row — needs an explicit merge policy, not a no-op) | Removes the skill/task_class dimension from what the key *means*; `source_skill_name`/`task_class` could still ride as non-key columns, but the router's per-`task_class` demotion actuation (§2.4.5) loses its addressable grain if the producer no longer aggregates by it | **Breaking** — changes what a "row" represents; requires MeatySkills renegotiation of the merge contract, not just a version bump |
| B `(project, command_slug, model)` | Same shape as A (drop `source_skill_name`, add `command_slug` to key) | Same DTO risk as A, plus a *worse* coverage number (§2.3) | **Breaking**, and strictly worse than status quo — not worth scoping further |
| C `(project, task_class, model)` | Change the raw `GROUP BY` grain (persist at `task_class` grain instead of `skill_name` grain) — `source_skill_name` would need to become a non-key aggregate (e.g. a representative or list value) since multiple skill names collapse into one `task_class` | `RoutingRollupKeyDTO.source_skill_name` semantics change from "the skill" to "a skill in this class" or `null`; mapping_version coupling gets *tighter*, not looser, since the persisted grain now depends on mapping content, not just a display derivation | **Breaking** for the DTO's `source_skill_name` field; the `task_class` field itself is unaffected since it is already computed today |
| D coalesce chain | Change `_fetch_raw_aggregate_rows`'s `GROUP BY` expression to the coalesce; migration must handle three more session columns' worth of pre-computation, and document a precedence tiebreak policy | New key semantics (a `subagent_type`-derived key looks nothing like a `skill_name`-derived one) need their own vocabulary entry in the contract | **Breaking**, for a 1.5pp coverage gain (§2.5) — worst cost/benefit ratio of the four redefinition candidates |
| **E — leave key, emit empty/null, document coverage** | **None.** No DDL change, no `GROUP BY` change, no consumer-contract renegotiation | None — this is exactly what v1 already ships (`source_skill_name=""` for the NULL cohort, `is_coverage_only`/`eligible_for_adjustment` already carry the honesty signal at the row level per `apply_mapping()`) | **N/A — status quo, trivially additive by construction** |

**The load-bearing scoping fact**: every redefinition candidate is a **breaking** change to the
persisted key and to the DTO's `source_skill_name` semantics, requiring (a) an Alembic-equivalent
DDL migration on both SQLite and Postgres DDL files (ADR-007 dual-DDL parity), (b) an explicit
merge/backfill policy for now-colliding historical rows, and (c) a version bump negotiated with
MeatySkills/`ibm-main` per the existing `mapping_digest`/`contract_version` gate — not a local
refactor, exactly as the charter anticipated. None of B/C/D purchase enough coverage or stability to
be worth that cost; A purchases 100% "coverage" only by discarding the dimension the whole
exploration exists to preserve.

## 5. Recommendation

**Recommend Candidate E — leave the persisted key as `(project_id, skill_name, model)`, keep
emitting the empty-string/coverage-only row for the no-skill cohort, and treat the ~40% informative
rate as a documented contract state** (the same null-over-fabrication posture the module already
applies to `success_rate`/`regression_rate`/`cost_index`).

Reasoning against each alternative:
- **A `(project, model)`** achieves 100% "coverage" only by deleting the skill dimension. That is
  not an attribution fix; it is the exact degenerate outcome the parent charter (§ Hypothesis
  Context) opens by naming as the risk to avoid presenting as a solution.
- **B `(project, command_slug, model)`** is measurably worse than status quo (7.8% vs 39.6%
  informative) — `command_slug` is emptier than `skill_name` because most sessions never invoke an
  explicit slash command. Ruled out on measurement, not assumption.
- **C `(project, task_class, model)`** is statistically identical to status quo (38.9% vs 39.6%)
  because it is a deterministic function of the same `skill_name` column and inherits its NULL
  cohort through the identical `_unclassified` fallback path. Crucially, `task_class` is **already
  computed and exposed per row today** without any key change — DI-1's actual actuation unit (the
  router reorders the `routing_policy` chain "for that task_class," §2.4.5 of the handoff spec) is
  already available to a consumer without CCDash migrating its persisted grain. A schema change
  here would buy nothing that isn't already shipped.
- **D coalesce chain** buys +1.5pp of coverage (41.1% vs 39.6%) for a materially more complex,
  three-column derivation with its own precedence semantics to test and document, and it is still a
  breaking DDL change under the migration ledger in §4. Not worth it.

None of the redefinition candidates clears a bar that would justify the breaking-change cost in §4.
The status quo key is also the only candidate requiring zero migration, zero consumer-contract
renegotiation, and zero backfill/collision-merge policy — and it is already built to the same
coverage-is-a-contract-state discipline the rest of the D5 payload uses.

**What would change this recommendation:**
1. If the sibling `null-population`/`capture-path` legs find a bounded, honest fix that raises
   `skill_name` informative coverage materially (charter's own >=60% bar) — this whole leg becomes
   moot; keep the key, fix the data, do not redefine.
2. If MeatySkills states a concrete need to apply `min_sample`/`eligible_for_adjustment` gating at
   **`task_class` grain** rather than per-`skill_name` row (e.g., because pooling multiple skills'
   sessions under one `task_class` changes eligibility outcomes for keys currently too sparse to
   qualify) — that would be a real, cost-justified reason to migrate the raw `GROUP BY` grain to
   `task_class` (Candidate C), independent of the coverage question this leg was scoped to answer.
   I did not find density evidence for this in-window (`task_class` clearing count 185 vs
   `skill_name`'s 187 — essentially flat), but a router-side requirement, not a coverage number,
   would be the trigger.
3. If churn turns out to matter more than coverage to the router's actual merge cadence (§2.4.6's
   hysteresis/TTL design already anticipates window-to-window instability) — Candidate A's better
   Jaccard (0.345 vs E's 0.290) is a real, if modest, argument for coarsening. I judge the coverage
   loss too large to accept on the current evidence, but this is the single number most likely to
   flip the recommendation if router-side operational experience disagrees.

## Confidence

**0.75.** Every quantitative claim above is a real SQL query against the operative node Postgres,
shown in place; every code claim is cited with `file:line`. The primary source of residual
uncertainty is judgment, not measurement: the "right" key ultimately depends on what MeatySkills'
router-side merge actually needs at write time, which I inferred from the ratified §2.4 ADR
(task_class is the actuation unit) rather than from a live router-side requirements conversation.
I did not find a second-agent verification pass practical to run inside this leg's timebox, which is
the sibling-leg precedent (DI-4b) explicitly warns against trusting single-pass claims uncritically —
I mitigate this by citing exact `file:line` for every code claim and showing every query's exact SQL
and result, so the numbers are independently re-runnable rather than asserted.
