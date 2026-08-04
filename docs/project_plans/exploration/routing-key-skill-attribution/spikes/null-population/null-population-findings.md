---
schema_version: 2
doc_type: report
report_category: finding
title: "Null-Population Leg — What Are the 114 NULL skill_name Routing Keys? (DI-4f)"
status: completed
created: 2026-08-03
feature_slug: routing-key-skill-attribution
leg_id: null-population
confidence: 0.75
exploration_charter_ref: docs/project_plans/exploration/routing-key-skill-attribution/routing-key-skill-attribution-charter.md
related_documents:
  - docs/project_plans/exploration/routing-feedback-success-signal/spikes/SHARED-CONTEXT.md
---

# Null-Population Leg — What Are the 114 NULL skill_name Routing Keys?

## 0. Measurement re-run and a drift note

Re-running the charter's exact denominator query against `10.42.10.76:5440` right now (rolling
30-day window, so the boundary moves) gives **187 total keys, 113 NULL-`skill_name` keys** — one
off the charter's `188` / `114` in each direction. This is normal rolling-window drift (a session
crossed the 30-day boundary between the charter's measurement and now), not a discrepancy in
method. All figures below use the just-measured 113-key cohort.

```sql
WITH windowed AS (
  SELECT * FROM sessions
  WHERE updated_at >= to_char(NOW() - INTERVAL '30 days','YYYY-MM-DD"T"HH24:MI:SS')
),
keyed AS (
  SELECT project_id, skill_name, model, COUNT(*) AS session_count
  FROM windowed GROUP BY project_id, skill_name, model HAVING COUNT(*) >= 5
)
SELECT count(*) AS total_keys, count(*) FILTER (WHERE skill_name IS NULL) AS null_keys FROM keyed;
-- => total_keys=187, null_keys=113
```

**Sessions behind those 113 NULL keys**, joined back with the mandatory `IS NOT DISTINCT FROM` on
`model` (project_id is never NULL in this data, verified separately):

```sql
WITH windowed AS (...), keyed AS (...),
null_keys AS (SELECT project_id, model FROM keyed WHERE skill_name IS NULL)
SELECT count(*) AS sessions_behind_null_keys
FROM windowed w JOIN null_keys nk
  ON w.project_id = nk.project_id AND w.model IS NOT DISTINCT FROM nk.model
WHERE w.skill_name IS NULL;
-- => 5119
```

**5,119 sessions** sit behind the 113 NULL-`skill_name` keys. This is the population this leg
characterizes.

**A third gotcha, found here, not in SHARED-CONTEXT**: `sessions.id` is **not unique** —
`SELECT count(*), count(DISTINCT id) FROM sessions` returns `19260` vs `17844`. A naive
`LEFT JOIN sessions p ON p.id = child.parent_session_id` fans out (one duplicate `id` across two
different `project_id`s multiplies the match) and silently inflates every downstream count — it
did, in an earlier draft of this leg's own queries, by 400–900 rows per bucket. The fix is to scope
the self-join by `(id, project_id)` via `DISTINCT ON`. Anyone doing a parent/root self-join on this
table needs this, not just this leg.

## 1. Distribution by session_type, launcher, platform_type, command_slug, subagent_type, thread_kind, agent_id, project_id

All six requested columns exist on `sessions` (verified via `information_schema.columns`); none
are absent.

**By `session_type`** (3 values only):
```
session    3400
subagent   1647
fork         72
```

**By `launcher`** — almost entirely unpopulated for this cohort:
```
NULL             5086   (99.4%)
ica-claude.sh      33
```

**By `platform_type`**:
```
Claude Code   3686
Codex         1433
```

**By `command_slug`** (98.8% empty):
```
""                         5057
/clear                       38
/effort                      13
/redeploy                     4
/execute-plan                 3
/execute-contract             1
/fix:debug                    1
/plan:plan-feature            1
/dev:execute-contract         1
```

**By `subagent_type`** (99.5% empty — see §3, this column is nearly unpopulated even for rows
whose `session_type` IS `subagent`):
```
""                          5092
codebase-explorer               7
python-backend-engineer         7
Explore                         5
general-purpose                 3
codex-executor                  2
data-layer-expert               1
feature-sprint-executor         1
implementation-planner          1
```

**By `thread_kind`** (4 values):
```
root        1967
subagent    1647
""          1433   (all Codex — thread_kind is not populated for that platform)
fork          72
```

**By `agent_id`**: 2,815 NULL; the remaining 2,304 are spread across ~1,150 distinct low-cardinality
values (top 30 all show `n=2`) — no dominant agent_id, consistent with per-subagent-instance IDs
rather than a shared pool.

**By `project_id`**: spread across 22 of the 24 registered projects plus 8 rows with an empty
`project_id`. The largest single project (`ccp-3c5f7843344b`) accounts for 1,204/5,119 = 23.5% —
material but not dominant. **Not a single-project artifact.**

## 2. The central deliverable — plausibly-should-have-a-skill vs genuinely-skill-less

**Classification rule.** A session is **plausibly-should-have-a-skill** if there is a positive,
measurable signal that a skill was known or knowable for it and not written to `skill_name`:
(a) its `parent_session_id` (same `project_id`, deduped per the id-collision gotcha above) points
to a session that **does** have a non-NULL `skill_name` — an inheritance opportunity that was not
taken; or (b) its `command_slug` matches one of the skill-bound slash commands in this repo's
Command–Skill Bindings table (`/redeploy`, `/execute-plan`, `/execute-contract`, `/fix:debug`,
`/plan:plan-feature`, `/dev:execute-contract` — NOT `/clear` or `/effort`, which are utility
commands with no skill binding). Everything else is **genuinely-skill-less by current evidence** —
either there was no invoked skill to record, or (Codex) the platform captures no skill-adjacent
signal at all today.

**Query** (parent join corrected for the id-collision gotcha):
```sql
WITH parent_dedup AS (
  SELECT DISTINCT ON (id, project_id) id, project_id, skill_name FROM sessions
)
SELECT nks.session_type,
       (nks.parent_session_id IS NOT NULL) AS has_parent,
       (p.skill_name IS NOT NULL) AS parent_has_skill,
       count(*) AS n
FROM null_key_sessions nks
LEFT JOIN parent_dedup p ON p.id = nks.parent_session_id AND p.project_id = nks.project_id
GROUP BY 1,2,3 ORDER BY n DESC;
```

**Result** (sums to 5,117 of the 5,119 — 2 sessions drop out of the dedup tie-break, disclosed not
resolved; immaterial to the split below):
```
session,  no-parent,              n=2747
subagent, parent-has-skill=true,  n=1174
subagent, parent-has-skill=false, n=473
session,  parent-has-skill=true,  n=330
session,  parent-has-skill=false, n=321
fork,     no-parent,              n=72
```

Cross-checking the 62 non-empty `command_slug` sessions against this same join, the 11 skill-bound
ones (`/redeploy`×4, `/execute-plan`×3, `/execute-contract`×1, `/fix:debug`×1,
`/plan:plan-feature`×1, `/dev:execute-contract`×1) all fall inside the `no-parent` buckets — pulled
out below.

| Bucket | Count | % of 5,117 | Rule |
|---|---|---|---|
| **Plausibly-should-have-a-skill** — inheritance gap (parent has a skill, child doesn't) | 1,504 (1,174 subagent + 330 session) | 29.4% | (a) |
| **Plausibly-should-have-a-skill** — skill-bound command_slug, skill_name still NULL | 11 | 0.2% | (b) |
| **Genuinely skill-less** — Claude Code root/fork, no parent, no skill-bound command | 2,738 + 70 = 2,808 | 54.9% | true negative |
| **Genuinely skill-less** — cascading NULL (parent also lacks a skill, nothing to inherit) | 473 + 321 = 794 | 15.5% | true negative (transitively) |
| **Platform-structural — Codex** (subset of the "no-parent" row above; called out separately, see below) | 1,433 | 28.0% (of 5,117) | *ambiguous — see note* |

**Bottom line: 1,515 of 5,117 (29.6%) are a plausible attribution gap; 3,602 of 5,117 (70.4%) are
genuinely skill-less by current evidence** — with one important carve-out on that 70.4%, below.

**The Codex carve-out.** Codex accounts for 1,433 of the 5,117 (28.0%) and sits entirely inside
the "genuinely skill-less" bucket by the rule above, because there is *no* positive signal to
apply the rule to: verified against **every Codex session ever recorded** (3,482 rows, all time,
not just this cohort), `skill_name`, `command_slug`, and `skills_used_json` are **100% NULL/empty
— zero exceptions**:
```sql
SELECT (skill_name IS NOT NULL) has_skill, count(*) FROM sessions WHERE platform_type='Codex' GROUP BY 1;
-- => has_skill=false, n=3482  (no true row)
SELECT (command_slug IS NOT NULL AND command_slug!='') has_slug, count(*) FROM sessions WHERE platform_type='Codex' GROUP BY 1;
-- => has_slug=false, n=3482
```
This is a **platform-structural absence**, not a per-session true-negative — I cannot distinguish
"Codex sessions genuinely never use anything skill-like" from "CCDash's Codex parser never
extracts the equivalent concept" from this leg's data alone. That determination belongs to the
`capture-path` leg. I report it separately rather than folding it into either bucket with false
confidence, and flag it as the single largest lever on this leg's conclusion: if capture-path finds
Codex has a capturable skill-equivalent, the genuinely-skill-less share drops from 70.4% to 42.4%
and the go-criterion arithmetic changes materially.

## 3. Subagent/sidechain inheritance — quantified, and shown to be a general gap, not cohort-specific

**Within the null-key cohort**: 1,504 sessions (1,174 `subagent` + 330 `session`-typed children)
have a parent in the same `project_id` with a known `skill_name`, yet the child's `skill_name` is
NULL. That is the inheritance gap's size inside this cohort (§2).

**Is this cohort-specific or systemic?** Re-running the same corrected join against the **entire**
`sessions` table (not scoped to the null-key cohort), for all rows with `session_type='subagent'`:
```sql
WITH parent_dedup AS (SELECT DISTINCT ON (id, project_id) id, project_id, skill_name FROM sessions)
SELECT (s.skill_name IS NOT NULL) child_has_skill, (p.skill_name IS NOT NULL) parent_has_skill, count(*) n
FROM sessions s LEFT JOIN parent_dedup p ON p.id=s.parent_session_id AND p.project_id=s.project_id
WHERE s.session_type='subagent' GROUP BY 1,2 ORDER BY n DESC;
```
```
child_has_skill=true,  parent_has_skill=true,  n=1930
child_has_skill=false, parent_has_skill=true,  n=1834
child_has_skill=false, parent_has_skill=false, n=925
child_has_skill=true,  parent_has_skill=false, n=467
```
Among all subagent sessions whose parent HAS a known skill, inheritance succeeds only
**1,930 / (1,930+1,834) = 51.3%** of the time, system-wide. This is a real, general mechanism gap
— not a peculiarity of the 5,119-session null-key cohort — meaning a fix belongs in the
capture/derivation path (propagate parent `skill_name` to `subagent`/child rows at write time),
not in a per-key workaround. Also note the `child_has_skill=true, parent_has_skill=false, n=467`
row: a non-trivial fraction of subagents somehow DO have a skill their parent lacks, which argues
against a naive parent-copy fix being sufficient on its own — some subagents currently derive skill
independently of the parent chain.

## 4. Cross-check against skills_used_json and agents_used_json

**`skills_used_json`**, within the null-key cohort:
```sql
SELECT (skills_used_json IS NULL) is_null, (skills_used_json='') is_empty_str,
       (skills_used_json='[]') is_empty_array, count(*) n
FROM null_key_sessions GROUP BY 1,2,3;
-- is_null=false, is_empty_str=false, is_empty_array=true,  n=5115
-- is_null=false, is_empty_str=false, is_empty_array=false, n=4
```
Only **4 of 5,119 (0.08%)** NULL-`skill_name` sessions have a non-empty `skills_used_json`. Sample:
`["dev:autopilot"]`, `["redeploy"]`, `["symbols"]`, `["update-config"]`. This essentially **rules
out** "the skill was known and simply not written to `skill_name`" as a material explanation —
if it were, `skills_used_json` non-emptiness would track the inheritance-gap bucket (1,515
sessions), not 4.

**`agents_used_json`**: 220 of 5,119 (4.3%) non-empty. Sampling the contents shows this field
tracks **invoked agent/subagent identifiers** (e.g. `["python-backend-engineer"]`,
`["aleg8-context-remainder-89032b6cd2fb9f0e"]`), not skill names — it is a different dimension
(which agents ran) and is **not a skill-name backfill source**, despite the superficial name
similarity. Do not conflate the two in any derivation leg.

## Conclusion

The 5,119 sessions behind the 113 (~114, rolling-window drift) NULL-`skill_name` min_sample-clearing
keys are **not one coherent cohort** — they split cleanly into three unrelated mechanisms: (1) a
**general, system-wide subagent-inheritance gap** that fails to propagate a known parent skill
roughly half the time (1,504 sessions in this cohort, 51.3% baseline failure rate system-wide) —
the strongest and most bounded fix candidate; (2) a **large genuinely-skill-less majority**
(2,808 bare interactive/root sessions plus 794 cascading-NULL descendants, ~70% of the non-Codex
population) that correctly has no skill to attribute — consistent with the charter's own
expectation that some NULLs are the right answer; and (3) a **platform-structural blind spot in
Codex** (1,433 sessions, 28% of the cohort) where zero skill-adjacent signal exists anywhere in the
data, which this leg cannot resolve and must hand to the capture-path leg — its resolution swings
the genuinely-skill-less share from 70% down to 42% and is the single fact most likely to move this
exploration from a clean "go" to a "conditional" (the same per-platform-skew shape that gated
DI-4b). `skills_used_json` and `agents_used_json` do not offer a hidden backfill source — the
former is almost never populated on this cohort (4/5,119) and the latter tracks agents, not skills.

## Confidence: 0.75

High confidence in the measured breakdowns (every number above is a real query against the live
node Postgres, and the id-collision join bug was caught and corrected before it reached this
document). Confidence is capped below 0.8 because the Codex classification is a genuine open
question this leg cannot close on its own — it is reported as ambiguous rather than resolved, and
the exploration's overall verdict is sensitive to how the capture-path leg resolves it.
