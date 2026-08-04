---
schema_version: 2
doc_type: exploration_charter
title: "Routing Key Skill Attribution — Exploration Charter"
status: concluded
created: 2026-08-03
feature_slug: routing-key-skill-attribution
timebox_days: 2
hypothesis: "The 61% NULL `skill_name` rate on min_sample-clearing routing keys is
  a capture or derivation gap that can be closed for a material fraction of keys,
  rather than an irreducible property of how sessions are invoked."
deal_killer: "If the NULL population turns out to be dominated by session kinds that
  genuinely have no skill (bare interactive sessions, subagent threads with no skill
  in scope), and no derivation can attribute them without fabricating a skill, then
  the honest outcome is to redefine the routing key rather than fix attribution --
  and to say so. Do not backfill a guessed skill onto a session that never had one."
investigation_legs:
- id: null-population
  question: What ARE the 114 NULL-skill_name keys? Break the NULL population 
    down by session_type, launcher, platform_type, command_slug, subagent/thread
    kind, and project -- is it one coherent cohort or several unrelated ones?
  assigned_to: spike-writer
- id: capture-path
  question: Where does `skill_name` get set, and where does it fail? Is the 
    skill known at capture time and dropped, derivable post-hoc from what IS 
    captured (skills_used_json, command_slug, transcript Skill tool calls), or 
    genuinely absent?
  assigned_to: spike-writer
- id: key-redefinition
  question: If attribution cannot be materially improved, what is the right 
    routing key? Evaluate the alternatives against DI-1's actual need -- 
    (project x model), (command_slug x model), (task_class x model), or a 
    coalesce/fallback chain -- including what each does to the 188-key 
    denominator and to min_sample eligibility.
  assigned_to: spike-writer
verdict_criteria:
  go:
  - A bounded fix (capture-time or derivation-time) raises non-NULL `skill_name`
    coverage on min_sample-clearing keys by a material margin -- recommend to 
    >=60% of keys non-NULL, and the SPIKE must state and justify its own 
    threshold
  - The fix does not fabricate a skill for sessions that genuinely had none (a 
    session correctly attributed as 'no skill' is a right answer, not a gap)
  - Deal-killer condition not triggered
  no_go:
  - 'Deal-killer triggered: the NULL population is dominated by genuinely skill-less
    sessions and no honest derivation exists'
  - A fix exists but is open-ended (requires new capture instrumentation across 
    multiple platforms) with no bounded first increment
  conditional:
  - Attribution is improvable but only for one platform/launcher cohort, leaving
    a skewed key space -- the same categorical-bias failure mode that gated 
    DI-4b, requiring a named follow-up before the key is trustworthy
verdict: no-go
verdict_rationale: "Go bar (>=60% of min_sample-clearing keys non-NULL) is unreachable:
  current 74/187 (39.6%), and the only honest zero-lead-time fix (Claude Code subagent->parent
  skill inheritance) converts just 10 of 113 NULL keys -- ceiling 84/187 = 44.9%.
  The fix repairs ~31% of NULL sessions at row level but fragments one large NULL
  bucket into many small per-skill buckets that individually miss min_sample=5, so
  a row-level win does not survive the key-level threshold. Hard floor beneath it:
  37/113 NULL keys are pure-Codex and 100% of all 3,482 Codex sessions ever recorded
  carry zero skill-adjacent signal (codex/parser.py:953 has never fired) -- permanent
  capture absence, unattributable post-hoc. No alternative key wins: task_class measured
  38.9% (inherits the same NULL fallback via _resolve_task_class routing_rollup.py:497-510),
  command_slug 7.8% (regression), coalesce chain 41.1% for a breaking dual-DDL migration;
  all candidates churn at Jaccard 0.29-0.35. Not conditional: the Claude-Code-only
  fix is platform-skewed but immaterial at key level (8.8% of NULLs), so the conditional
  premise fails at the level DI-1 consumes -- collapsing into the deal_killer's named
  redirect. Redirect (not a dead end): keep (project_id, skill_name, model), emit
  null for the no-skill cohort, document coverage as a contract state per the existing
  null-over-fabrication precedent. Human sign-off 2026-08-03."
output_artifacts:
- path: docs/project_plans/exploration/routing-key-skill-attribution/spikes/null-population/null-population-findings.md
  leg_id: null-population
  confidence: 0.75
- path: docs/project_plans/exploration/routing-key-skill-attribution/spikes/capture-path/capture-path-findings.md
  leg_id: capture-path
  confidence: 0.8
- path: docs/project_plans/exploration/routing-key-skill-attribution/spikes/key-redefinition/key-redefinition-findings.md
  leg_id: key-redefinition
  confidence: 0.75
- path: docs/project_plans/exploration/routing-key-skill-attribution/routing-key-skill-attribution-feasibility-brief.md
  role: feasibility_brief
  confidence: 0.78
related_documents:
- docs/project_plans/exploration/routing-feedback-success-signal/routing-feedback-success-signal-synthesis.md
- docs/project_plans/design-specs/routing-feedback-router-merge-handoff.md
updated: '2026-08-03'
---

# Routing Key Skill Attribution — Exploration Charter

## Hypothesis Context

The DI-4b exploration (closed 2026-08-03, verdict conditional) surfaced a blocking discovery outside
its own charter's scope:

> **114 of the 188 `min_sample`-clearing routing keys (61%) have a NULL `skill_name`**, which the
> producer coalesces to `""` (`str(row["source_skill_name"] or "")` in
> `backend/application/services/agent_queries/routing_rollup.py`).

This conditions the value of *all* remaining routing-feedback work. The rollup key is
`(project_id, skill_name, model)`. If `skill_name` is empty on 61% of the keys the router acts on,
then those keys are really `(project_id, model)` wearing a three-part key's clothes — and the
"skill-aware routing feedback" DI-1 was designed to deliver degrades into per-project model
preference for the majority of its own key space.

This matters independently of whether DI-4b's `success_rate` precondition (DI-4d, the Codex
tool-error fix) ever clears. A perfect outcome signal attached to a key with no skill dimension is
still not the thing the feedback loop was specified to produce. **Decide this before investing
further in `success_rate`.**

Note the asymmetry that makes this worth a real exploration rather than a bug ticket: some fraction
of those NULLs are almost certainly *correct*. A bare interactive session with no skill invoked has
no skill to attribute. The question is not "how do we make the column non-NULL" — it is "how much of
this NULL population is a gap, and what is the right key given the irreducible remainder."

## Measured Starting Point

Established 2026-08-03 against the operative node Postgres (`10.42.10.76:5440`, schema as of
`main`). Do not re-derive; verify and extend.

| Quantity | Value |
|---|---|
| Sessions, all time | 19,178 |
| Sessions in 30-day window | 7,354 |
| All keys in window | 396 |
| Keys clearing `min_sample`=5 | 188 |
| **Of those, keys with NULL `skill_name`** | **114 (61%)** |

Reusable measurement recipe (denominator, PG typing gotchas, query helper) is in
`docs/project_plans/exploration/routing-feedback-success-signal/spikes/SHARED-CONTEXT.md`.
**`sessions.updated_at` is `text`, not `timestamptz`** — comparing to `NOW()` errors. And note the
NULL-join trap that bit the DI-4b orchestrator: `skill_name = skill_name` never matches when both
are NULL, so any key-level join in this exploration **must** use `IS NOT DISTINCT FROM` or the
results will silently undercount exactly the cohort under investigation.

---

## Investigation Legs

### Leg: null-population — What are the NULL keys?

**Question**: Is the 114-key NULL population one coherent cohort or several unrelated ones?
**Assigned to**: `spike-writer`
**Expected output**: `.../spikes/null-population/null-population-findings.md`

- Break the NULL-`skill_name` sessions down by `session_type`, `launcher`, `platform_type`,
  `command_slug`, `subagent_type`, `thread_kind`, `agent_id`, and `project_id`. Report the
  distribution, not just a total.
- Separate the population into **plausibly-should-have-a-skill** vs **genuinely-skill-less**. This
  split is the leg's central deliverable — the go criterion depends on not counting the latter as a
  gap.
- Check whether NULLs concentrate in subagent/sidechain threads. If a parent session has a skill and
  its subagents do not, that is an inheritance gap with a very different fix from a capture gap.
- Cross-check against `skills_used_json` and `agents_used_json`: is there evidence the skill WAS
  known for these sessions and simply not written to `skill_name`?

### Leg: capture-path — Where does attribution break?

**Question**: Is the skill known at capture time and dropped, derivable post-hoc, or genuinely absent?
**Assigned to**: `spike-writer`
**Expected output**: `.../spikes/capture-path/capture-path-findings.md`

- Trace `skill_name` from capture to column: the SessionStart capture sidecar, the platform parsers
  (`backend/parsers/platforms/`), the sync engine, and the sessions repository. Cite `file:line`.
- Determine, for each cohort the `null-population` leg identifies, which of three states applies:
  **(a)** known at capture and dropped → bounded fix; **(b)** not captured but derivable from
  retained data (`skills_used_json`, `command_slug`, `Skill` tool invocations in
  `session_messages`) → bounded backfill + forward fix; **(c)** never captured and unreconstructable
  → feeds the `key-redefinition` leg.
- **Heed the DI-4b precedent, twice over.** That exploration's designated lead was mis-specified in
  a committed spec, and a related claim about `effectiveness_rollups` attribution (component
  extraction emitting hashes) was refuted by measurement. Verify the mechanism against current code
  and real rows; do not inherit a stated cause.
- Note per-platform asymmetry explicitly. Claude Code and Codex capture differently, and DI-4b was
  gated precisely by a per-platform categorical gap. If attribution is fixable for one platform and
  not the other, that is a conditional verdict, not a go.
- Backfill feasibility: can historical rows be attributed, or forward-only? If forward-only, state
  the lead time before the 30-day rolling window carries usable keys — that is a real cost.

### Leg: key-redefinition — Is `skill_name` even the right key dimension?

**Question**: If attribution cannot be materially improved, what key should the rollup use?
**Assigned to**: `spike-writer`
**Expected output**: `.../spikes/key-redefinition/key-redefinition-findings.md`

- This leg must run **regardless** of the other two legs' outcomes — it is the fallback that makes a
  no-go actionable rather than terminal.
- Evaluate candidate keys against DI-1's actual consumption need (handoff spec §1/§2): `(project_id,
  model)`, `(command_slug, model)`, `(task_class, model)` — noting `task_class` is already derived
  from `skill_name` via the pinned v1 mapping, so it likely inherits the same NULL problem; verify
  rather than assume — and a coalesce/fallback chain (`skill_name` → `command_slug` →
  `subagent_type` → sentinel).
- For each candidate: how many keys result, how many clear `min_sample`=5, and what happens to
  key stability across windows (a key that churns every window cannot accumulate confidence).
- Assess the contract cost: the rollup's `PRIMARY KEY (project_id, source_skill_name, model)` is
  declared in both DDLs (v43). A key change is a migration plus a consumer-contract change with
  MeatySkills/`ibm-main`, not a local refactor. Scope it; do not implement it.
- Explicitly consider "leave the key, emit null, and document the coverage" as a candidate — the
  same coverage-is-a-contract-state principle that governs `success_rate`.

---

## Verdict Criteria Narrative

**Go** if a bounded fix materially raises non-NULL coverage on min_sample-clearing keys (recommend
>=60% non-NULL, justify your own threshold) **without fabricating a skill** for sessions that never
had one.

**No-go** if the NULL population is dominated by genuinely skill-less sessions with no honest
derivation. In that case the `key-redefinition` leg's recommendation becomes the actual next step —
a no-go here is a redirect, not a dead end.

**Conditional** if attribution is improvable for only one platform/launcher cohort. This is the same
categorical-bias shape that gated DI-4b: a partially-populated key space is not a partial win, it is
a systematic skew, and it needs a named follow-up before the key can be trusted.

---

## Out of Scope

- Implementing any fix, migration, or backfill — feasibility and scoping only.
- The Codex tool-error detection fix (DI-4d) — separate, tracked in handoff spec §5.4.
- `regression_rate` — closed by DI-4b; not reopened here.
- Router-side merge changes (DI-1) — deferred, owned by MeatySkills/`ibm-main`.

---

## Citations / Prior Art

- `docs/project_plans/exploration/routing-feedback-success-signal/routing-feedback-success-signal-synthesis.md`
  §7 (where this finding originated) and §2 (the 188-key denominator).
- `docs/project_plans/exploration/routing-feedback-success-signal/spikes/SHARED-CONTEXT.md` —
  measurement recipe, denominator, PG typing and NULL-join gotchas.
- `docs/project_plans/design-specs/routing-feedback-router-merge-handoff.md` §0 (DI-4b outcome box),
  §1–§2 (consumer contract and merge math), §5.4 (DI-4d/DI-4f).
- `backend/application/services/agent_queries/routing_rollup.py` — the `GROUP BY` that defines the
  key and the `or ""` coalesce that hides the NULL.

---

## Notes

2026-08-03: Charter authored from the DI-4b exploration's out-of-scope finding (synthesis §7). No
legs run yet.
