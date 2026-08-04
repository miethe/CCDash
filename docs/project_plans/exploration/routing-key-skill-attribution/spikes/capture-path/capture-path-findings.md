---
schema_version: 2
doc_type: report
report_category: finding
title: "Capture-Path Trace for routing_rollup.skill_name (DI-4f leg: capture-path)"
status: completed
created: 2026-08-03
feature_slug: routing-key-skill-attribution
leg_id: capture-path
confidence: 0.8
exploration_charter_ref: docs/project_plans/exploration/routing-key-skill-attribution/routing-key-skill-attribution-charter.md
---

# Capture-Path Trace — `skill_name`

## 0. Method note (read this before the numbers)

All queries ran against the operative node Postgres (`10.42.10.76:5440`) via the shared
`/tmp/rfss/q.py` helper, using the same 30-day-window / `min_sample=5` denominator recipe as
`SHARED-CONTEXT.md`. **One correction to that recipe surfaced during this leg and matters for
every future query against `sessions`: `sessions.id` is NOT globally unique** — it is scoped per
project (19,258 total rows, only 17,842 distinct `id` values; e.g.
`S-agent-ap3-karen-57e1e1aec52d1aab` appears twice, once per project). Any self-join on `sessions`
(e.g. joining a subagent row to its parent via `subagent_parent_id`) that does not also constrain
`project_id` will fan out across projects and silently inflate counts. My first pass at the
parent-inheritance simulation below did exactly this (inflated "attributable" from 1,185 to 1,852
sessions); all numbers in this document use the corrected `p.id = s.subagent_parent_id AND
p.project_id = s.project_id` join. Flagging this for the sibling legs and for `SHARED-CONTEXT.md`.

My in-window totals (187 keys, 113 NULL keys) differ from the charter's stated 188/114 by one key
each — consistent with a few minutes of window drift between the charter's measurement and mine,
not a methodology disagreement. Not material to any conclusion below.

## 1. Trace: where does `skill_name` get set, and where can it be dropped?

**Headline: there is no "capture-time" `skill_name` at all.** The SessionStart hook never touches
skill. `skill_name` is entirely a **post-hoc parser derivation from transcript content**, computed
at sync/parse time from whatever the raw JSONL already contains — never something known upstream
and discarded downstream. This reframes the charter's state (a) ("known at capture and dropped"):
for this field, there is no capture-time value to drop. The fork point is entirely "does the
transcript contain the signal the parser looks for."

| Stage | File:line | What happens |
|---|---|---|
| SessionStart capture sidecar | `scripts/hooks/ccdash_capture_session_start.py` (321 lines, grepped case-insensitive for "skill": **zero hits**) | Writes `launcher`/`profile`/`effortLevel`/`model` to the `.capture.json` sidecar. No skill awareness exists at this layer, for either platform. |
| Claude Code parser — signal source | `backend/parsers/platforms/claude_code/parser.py:1652` `_extract_skill_payload`, gated by `_SKILL_FORMAT_PATTERN` (line 38: `<skill-format>\s*true\s*</skill-format>`) and a `"base directory for this skill:"` substring check | Only fires when a transcript **message** contains the literal marker Claude Code emits after a `Skill()` tool call successfully loads content (this exact marker is present in the command message that invoked *this* CCDash spike, for what it's worth). |
| Claude Code parser — accumulation | `parser.py:2288-2333` `process_skill_payload_from_message` | Appends `{skill, timestamp, sourceToolUseId, sourceLogId}` to `session_context["skillLoads"]` **only** when the marker above is found in a message. A separate `Skill` tool-call detector (`parser.py:3342-3360`) records an artifact + `skill_invocations_by_tool_use_id[tool_id]` but does **not** itself append to `skillLoads` — only the marker-bearing message does. |
| Claude Code parser — reduction to session field | `parser.py:1400-1412` `_primary_skill_name` → called at `parser.py:4604` and `4670` | Takes the **first** entry in `skillLoads` and returns its `skill` string, or `None` if `skillLoads` is empty. This becomes `session_data["skillName"]`. |
| Codex parser — signal source | `backend/parsers/platforms/codex/parser.py:953-965` | Detects a `tool_name == "skill"` tool call and creates a `kind="skill"` artifact (same shape as Claude Code's tool-level detector) — but this is **the only place "skill" appears in the entire file** (confirmed via grep for `skill_name`/`skillName`/`SkillName`: zero further hits). |
| Codex parser — reduction to session field | **does not exist** | There is no `_primary_skill_name` equivalent, no `skillLoads` accumulator, and no code path that ever sets a top-level `skillName` key in the dict the Codex parser returns. `session_data.get("skillName")` therefore always returns `None` for every Codex session, unconditionally. |
| Sync engine | `backend/db/sync_engine.py:678` (comment only: "workflow_id / subagent_parent_id are log-derived in the parser and survive a...") | No skill-specific logic; passes parser output straight to the repository. |
| Repository write | `backend/db/repositories/sessions.py:244`, `backend/db/repositories/postgres/sessions.py:179` | `session_data.get("skillName")` written directly, no coalesce, no default. Adjacent comment (line 246-248) states the project convention explicitly: *"null == 'not captured' (contract state, no default, no backfill)"*. Confirms nothing is dropped here — a `None` from the parser stays `None` in the column. |
| Rollup producer | `backend/application/services/agent_queries/routing_rollup.py` (cited in charter/SHARED-CONTEXT) | Coalesces `NULL` → `""` at read time for the `(project_id, skill_name, model)` `GROUP BY`. This is the only place a NULL is "hidden," and it happens far downstream of capture. |

**Conclusion of the trace**: for Claude Code, `skill_name` is derivable but conditional on a
specific transcript marker appearing in a message; for Codex, it is architecturally absent — no
code path anywhere in `codex/parser.py` ever populates it, regardless of transcript content.

## 2. Real-row verification: is Codex's gap total, and is it wiring-only or signal-absent?

```sql
SELECT platform_type, COUNT(*) AS n,
       COUNT(*) FILTER (WHERE skill_name IS NOT NULL AND skill_name <> '') AS n_skill_nonnull
FROM sessions GROUP BY platform_type;
```
```
Claude Code: n=15778, n_skill_nonnull=5630  (35.7% non-null)
Codex:       n=3482,  n_skill_nonnull=0     (0.0% non-null, all-time, no exceptions)
```

This alone would be consistent with either "wiring gap" (signal exists elsewhere, just not
promoted to `skill_name`) or "genuinely never captured." I checked both retained proxies the
charter names — `session_artifacts` (kind='skill') and `session_tool_usage` (tool_name='skill'):

```sql
SELECT s.platform_type, COUNT(DISTINCT sa.session_id)
FROM session_artifacts sa JOIN sessions s ON s.id = sa.session_id
WHERE sa.type = 'skill' GROUP BY s.platform_type;
-- Claude Code: 3806   (Codex: no row at all)

SELECT s.platform_type, COUNT(DISTINCT stu.session_id)
FROM session_tool_usage stu JOIN sessions s ON s.id = stu.session_id
WHERE lower(stu.tool_name) = 'skill' GROUP BY s.platform_type;
-- Claude Code: 826    (Codex: no row at all)

SELECT COUNT(*) FROM sessions WHERE platform_type='Codex' AND command_slug IS NOT NULL AND command_slug <> '';
-- 0 (of 3482)
```

**Zero Codex sessions have a `skill`-typed artifact, a `Skill`-named tool-usage row, or a non-empty
`command_slug`**, despite `codex/parser.py:953` containing code that *would* create a skill
artifact if it ever saw `tool_name == "skill"`. That code path has simply never fired in this
database. This is stronger than a wiring gap: it means either (a) the Codex CLI/harness never
emits a Skill-equivalent construct in the raw transcript for any of these 3,482 sessions, or (b)
it does, under a shape this parser's detector doesn't match. I could not distinguish those two
from CCDash's DB alone — that requires inspecting raw Codex JSONL for a session, which is outside
this leg's read-only-DB scope. Either way: **there is currently no reconstructable proxy for skill
in Codex data as parsed today.** This is a genuine per-platform capture gap, not a coalesce/lookup
bug.

## 3. Cohort classification (state a / b / c)

| Cohort | Platform | n (in-window NULL) | State | Fix boundedness |
|---|---|---|---|---|
| Codex, any session type | Codex | 1,473 / 1,473 (100%) | **(c)** never captured, no retained proxy found (§2) | Not bounded from CCDash's side alone — requires confirming whether raw Codex transcripts carry *any* skill-equivalent signal (open question, needs a Codex-harness-level check outside this leg). Feeds `key-redefinition`. |
| Claude Code, subagent, parent has a skill | Claude Code | 1,185 / 3,789 in-window CC nulls (31.3%); 1,834 / 10,146 all-time CC nulls (18.1%) | **(b)** not captured on the subagent's own row, but derivable by joining `subagent_parent_id` → parent's `skill_name` | **Bounded.** Pure backfill (existing columns only, no new instrumentation) + a small forward fix (repository/service inherits parent skill when a subagent row's own `skillName` is null). See §4 for why the *key-level* yield is smaller than the *row-level* yield. |
| Claude Code, subagent, parent also NULL | Claude Code | ~925 all-time (2,759 null-subagent CC minus 1,834 attributable) | **(c)** unreconstructable by this derivation (nothing to inherit); may still hold real skill context the `null-population` leg should classify (e.g., orchestrator-spawned subagent under a `/dev:execute-plan` wave with no `Skill()` call in the parent transcript either) | Not bounded here — feeds `key-redefinition` / `null-population`. |
| Claude Code, top-level (`session`/`fork`), no `skillLoads` marker | Claude Code | ~2,604 all-time (10,146 − 2,759 − ~2,783 counted elsewhere; see the session_type breakdown below) | **(c)**, and plausibly genuinely skill-less — `skills_used_json` is non-empty for only 3 of 2,682 top-level `session` rows and 0 of 146 `fork` rows in-window | Not a derivation gap by the evidence I could find; `command_slug` recovers a further 54+9=63 of these (see §5), an imprecise and small yield. |

Session-type breakdown backing the table (in-window, Claude Code only):

```sql
SELECT session_type, (subagent_parent_id IS NOT NULL) AS is_subagent, COUNT(*) AS n,
       COUNT(*) FILTER (WHERE skill_name IS NULL) AS n_null,
       COUNT(*) FILTER (WHERE skill_name IS NULL AND skills_used_json::text NOT IN ('[]','null','{}')) AS n_null_skills_json,
       COUNT(*) FILTER (WHERE skill_name IS NULL AND command_slug <> '') AS n_null_cmd_slug
FROM sessions WHERE platform_type='Claude Code' AND updated_at >= <30d> GROUP BY session_type, is_subagent;
```
```
subagent  True   n=3040  n_null=1660  skills_json=1   cmd_slug=0
session   False  n=2682  n_null=2057  skills_json=3   cmd_slug=54
fork      False  n=146   n_null=74    skills_json=0    cmd_slug=9
```

`skills_used_json` is essentially never populated when `skill_name` is NULL (1, 3, 0 hits across
3,791 NULL rows) — it is **not** a usable backfill source; whatever writes it appears to mirror
`skill_name` rather than capturing independently. `command_slug` has some non-empty values (63
total) but on inspection these are session-management commands, not skill invocations:

```sql
SELECT command_slug, COUNT(*) FROM ... WHERE skill_name IS NULL AND command_slug<>'' GROUP BY 1;
```
```
/clear 38, /effort 13, /redeploy 5, /execute-plan 3, /execute-contract 1,
/fix:debug 1, /plan:plan-feature 1, /dev:execute-contract 1
```
`/clear` and `/effort` are not skill invocations at all. A few (`/execute-plan`, `/plan:plan-feature`)
plausibly map to a skill but this is a 4–5-row yield, not material.

## 4. Derivation test: parent→subagent inheritance, and why the key-level yield is small

Tested `COALESCE(skill_name, parent.skill_name)` as the inherited value, properly project-scoped:

```sql
WITH windowed AS (
  SELECT s.id, s.project_id, s.model, s.skill_name,
         COALESCE(s.skill_name, p.skill_name) AS inherited_skill_name
  FROM sessions s
  LEFT JOIN sessions p ON p.id = s.subagent_parent_id AND p.project_id = s.project_id
  WHERE s.updated_at >= to_char(NOW() - INTERVAL '30 days','YYYY-MM-DD"T"HH24:MI:SS')
)
-- orig vs. new key counts, GROUP BY project_id, {skill_name|inherited_skill_name}, model HAVING >=5
```
```
orig_total_keys=187  orig_null_keys=113
new_total_keys=212   new_null_keys=103
```

Row-level yield is real (1,185 of 3,789 in-window CC-null sessions, 31.3%, gain a non-null
attribution). **Key-level yield is much smaller: only 10 of 113 NULL keys flip to non-null.**
Per-key breakdown of the 113 NULL keys (SQL in the appendix below) shows why: of the 73
Claude-Code-only NULL keys, only **1** is fully resolved (100% of its sessions attributable), 29
have **zero** attributable sessions (these are dominated by top-level, non-subagent sessions — the
genuinely-skill-less cohort in §3), and the remaining 43 are partially attributable but the
reattributed sessions scatter across many small per-inherited-skill buckets that individually often
don't clear `min_sample=5` — the aggregation that made the original NULL bucket large (many
different subagent types with no skill, lumped under one key) is precisely what the fix breaks
apart. **A derivation that measurably helps at the session/row level does not translate 1:1 into
cleared keys** — this is the single most important quantitative finding of this leg, and it bounds
how much the `key-redefinition` leg should expect from this fix alone.

## 5. Per-platform asymmetry (explicit, per charter instruction)

Of the 113 NULL keys: **37 are pure-Codex (33%, 0% attributable, always)**, **73 are pure-Claude-Code
(65%, partially attributable)**, and **3 are mixed** (a project+model pair where `model` itself is
empty-string, mixing both platforms' unset-model sessions). This is a clean platform split, not
overlap — models are named distinctly per platform (`claude-*` vs `gpt-*`), so almost no key spans
both. **This is a conditional signal, not a go**: a fix bounded to Claude Code's subagent-inheritance
path cannot touch the 37 Codex-only NULL keys at all, and Codex sessions in-window (1,473) are
23% of the same-window session volume — not a rounding error.

## 6. Backfill feasibility

- **Claude Code parent-inheritance fix: not forward-only.** `subagent_parent_id` and the parent's
  `skill_name` are both existing, already-populated columns (`subagent_parent_id` populated for
  5,156 of 15,778 Claude Code sessions all-time, spanning 2026-04-22 → 2026-08-03 — the full
  history the DB holds). The derivation can be applied retroactively to every historical row via a
  read-time join or a one-time backfill; **zero lead time**. The only cost is the key-level dilution
  shown in §4, not a waiting period.
- **Codex gap: no known bounded fix from this leg.** Since no retained proxy exists (§2), any fix
  requires first confirming Codex transcripts carry a skill-equivalent signal at all — an
  open question outside this leg's read-only-DB scope, not a coding task I can size. If confirmed,
  a parser fix would be **forward-only** (historical Codex JSONL would need re-parsing under the
  new detector, feasible only if raw logs are retained and re-syncable — not verified here). If no
  such signal exists in Codex transcripts, the 37 Codex-only NULL keys are unreconstructable and
  belong entirely to the `key-redefinition` leg, not to any capture fix.
- If a Codex fix is deployed prospectively, keys need up to the full 30-day
  `CCDASH_ROUTING_FEEDBACK_WINDOW_DAYS` window to fill with exclusively-post-fix sessions before
  `min_sample=5` keys reflect the corrected signal cleanly — real cost, not a footnote, and it
  compounds with the "confirm the signal exists" precondition above.

## Appendix: per-key attribution query (73 CC-only NULL keys)

```sql
WITH windowed AS (
  SELECT s.id, s.project_id, s.model, s.platform_type, s.skill_name, s.subagent_parent_id,
         p.skill_name AS parent_skill
  FROM sessions s
  LEFT JOIN sessions p ON p.id = s.subagent_parent_id AND p.project_id = s.project_id
  WHERE s.updated_at >= to_char(NOW() - INTERVAL '30 days','YYYY-MM-DD"T"HH24:MI:SS')
),
null_keys AS (
  SELECT project_id, model, COUNT(*) AS n FROM windowed WHERE skill_name IS NULL
  GROUP BY project_id, model HAVING COUNT(*) >= 5
)
SELECT nk.project_id, nk.model, nk.n,
       COUNT(*) FILTER (WHERE w.platform_type='Codex') AS n_codex,
       COUNT(*) FILTER (WHERE w.platform_type='Claude Code') AS n_cc,
       COUNT(*) FILTER (WHERE w.parent_skill IS NOT NULL) AS n_attributable
FROM null_keys nk
JOIN windowed w ON w.project_id=nk.project_id AND w.model=nk.model AND w.skill_name IS NULL
GROUP BY nk.project_id, nk.model, nk.n ORDER BY nk.n DESC;
```
Full 113-row output reviewed; summary counts: `pure_codex_keys=37, pure_cc_keys=73, mixed_keys=3,
fully_resolvable_cc_keys=1, zero_attribution_cc_keys=29` (remaining 43 partial).

---

## Conclusion

`skill_name` has no capture-time value to preserve — it is a pure post-hoc parser derivation, and
the two platforms diverge completely in what they derive it from: Claude Code computes it from a
literal `<skill-format>true</skill-format>` marker that only appears in a transcript message after
a successful `Skill()` tool load, while Codex's parser has a dormant skill-artifact detector that
has never once fired across 3,482 real sessions and no other retained proxy (artifacts, tool usage,
`command_slug`) carries the signal either — making Codex's 100% NULL rate a genuine, total capture
absence rather than a wiring bug. Within Claude Code, the one clearly derivable cohort is
subagent-inherits-parent's-skill (state b, a zero-lead-time backfill), but it only converts 10 of
113 NULL routing keys because the fix fragments the aggregate NULL bucket into many small
per-skill buckets that individually often miss `min_sample=5` — a real row-level win that mostly
doesn't survive the key-level threshold. The remaining Claude Code NULL sessions split between a
plausibly-genuine skill-less cohort (top-level interactive sessions with no `Skill()` invocation
anywhere in scope) and orphaned subagents whose parent is also NULL, neither of which this leg
found a derivation for.

## State classification table

| Cohort | State | Fix boundedness |
|---|---|---|
| Codex (all session types, 100% of Codex NULLs, 37 of 113 NULL keys) | (c) never captured, no retained proxy | Not bounded from this leg; needs a raw-transcript check outside DB scope, feeds `key-redefinition` |
| Claude Code subagent, parent has a skill (1,185 in-window / 1,834 all-time null sessions) | (b) derivable via `subagent_parent_id` join | Bounded backfill (zero lead time) + forward fix, but converts only 10/113 NULL keys (see §4) |
| Claude Code subagent, parent also NULL (~925 all-time) | (c) unreconstructable by this derivation | Not bounded here; feeds `null-population`/`key-redefinition` |
| Claude Code top-level `session`/`fork`, no skill marker, no `skills_used_json`, no skill-shaped `command_slug` (majority of remaining CC NULLs) | (c), plausibly genuinely skill-less | Not a gap by evidence found; `command_slug` yields a marginal, imprecise 63 rows |

## Confidence

**0.8** — every quantitative claim above is backed by a SQL query run against the live node
Postgres and a `file:line` code citation; the one open question I could not close from CCDash's DB
alone is whether raw Codex transcripts carry *any* unparsed skill-equivalent signal (I can only show
CCDash's current parser and retained tables never surface one). That gap keeps this just under 0.9.
