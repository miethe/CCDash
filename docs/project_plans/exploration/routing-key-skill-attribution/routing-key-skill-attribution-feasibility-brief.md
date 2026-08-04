---
schema_version: 2
doc_type: report
report_category: feasibility
title: "Routing Key Skill Attribution — Feasibility Brief"
status: finalized
created: 2026-08-03
updated: '2026-08-03'
feature_slug: routing-key-skill-attribution
verdict: no-go
verdict_confidence: 0.78
exploration_charter_ref: 
  docs/project_plans/exploration/routing-key-skill-attribution/routing-key-skill-attribution-charter.md
proposed_adr_ref:
recommended_next_action: "archive charter as no-go; adopt key-redefinition leg's Candidate
  E (keep (project_id, skill_name, model), emit empty-string for the no-skill cohort,
  document ~40% coverage as a contract state per the existing null-over-fabrication
  discipline); separately scope a decoupled Tier 1 follow-up for Claude Code subagent
  skill-inheritance (row/session-correctness value only, not a DI-1 unblocker)"
related_documents:
- docs/project_plans/exploration/routing-key-skill-attribution/spikes/null-population/null-population-findings.md
- docs/project_plans/exploration/routing-key-skill-attribution/spikes/capture-path/capture-path-findings.md
- docs/project_plans/exploration/routing-key-skill-attribution/spikes/key-redefinition/key-redefinition-findings.md
- docs/project_plans/exploration/routing-feedback-success-signal/routing-feedback-success-signal-synthesis.md
- docs/project_plans/design-specs/routing-feedback-router-merge-handoff.md
---

# Routing Key Skill Attribution — Feasibility Brief

---

## 1. Synopsis

DI-4b (closed 2026-08-03) surfaced that 61% of `min_sample`-clearing `routing_rollup` keys carry a
NULL `skill_name`, meaning most of the routing key space DI-1 depends on is really `(project, model)`
wearing a three-part key's clothes. This exploration asked whether that NULL population is a
fixable capture/derivation gap or an irreducible property of how sessions are invoked, and — either
way — what key the rollup should use. **It is a redirect, not a dead end**: the deal-killer the
charter wrote for exactly this outcome names the next step. The arithmetic is decisive — the one
honest, zero-lead-time fix available (Claude Code subagent→parent skill inheritance) converts only
10 of 113 NULL keys, pushing coverage from 39.6% to a ceiling of ≈44.9%, well short of the charter's
60% go bar — because that fix repairs individual NULL *sessions* (31% of them) without repairing
NULL *keys*: it fragments one large NULL bucket into many small per-skill buckets that individually
still miss `min_sample=5`. Layered on top, 37 of the 113 NULL keys are pure-Codex, and Codex's
capture path has *never once* recorded a skill-adjacent signal across all 3,482 sessions ever
ingested — a permanent, platform-structural floor, not a bug to fix. No alternative key dimension
(`task_class`, `command_slug`, a coalesce chain) beats the status quo enough to justify a breaking
schema/consumer-contract change. The recommended path is the one the key-redefinition leg already
converged on independently: keep the key, keep emitting the empty-string/coverage-only row for the
no-skill cohort, and document ~40% coverage as a contract state — the same null-over-fabrication
posture the module already applies to `success_rate`/`regression_rate`/`cost_index`.

---

## 2. Investigation Summary

| Leg | Agent | Confidence | Findings | Conclusion |
|-----|-------|-----------|----------|------------|
| null-population | spike-writer | 0.75 | [null-population-findings.md](./spikes/null-population/null-population-findings.md) | 5,119 sessions behind the 113 NULL keys split into 3 unrelated mechanisms: a general, system-wide subagent-inheritance gap (51.3% baseline failure rate when a parent has a known skill), a genuinely-skill-less majority (~70% of non-Codex NULLs, correctly NULL), and a Codex platform-structural blind spot (28% of the cohort, ambiguous pending capture-path). |
| capture-path | spike-writer | 0.8 | [capture-path-findings.md](./spikes/capture-path/capture-path-findings.md) | `skill_name` has no capture-time value to drop — it's a pure post-hoc parser derivation. Claude Code derives it from a literal transcript marker; Codex's equivalent detector (`codex/parser.py:953`) has never fired across 3,482 real sessions and no retained proxy exists. Parent-inheritance backfill is bounded and zero-lead-time but converts only 10/113 NULL keys — a row-level win that mostly doesn't survive the key-level `min_sample` threshold. |
| key-redefinition | spike-writer | 0.75 | [key-redefinition-findings.md](./spikes/key-redefinition/key-redefinition-findings.md) | Measured (not assumed): `task_class` inherits the same NULL problem (38.9% vs 39.6% informative, statistically indistinguishable); `command_slug` is worse (7.8%); a 3-column coalesce chain buys +1.5pp for a breaking-change cost. Every alternative candidate requires a breaking DDL/consumer-contract change; the status quo key requires none. Recommends Candidate E — keep the key, document coverage. |

---

## 3. Cost Estimate

**The exploration itself**: complete, ~3 SPIKE legs, no further cost.

**Recommended follow-up (decoupled, not a DI-1 unblocker)**: the Claude Code subagent→parent
skill-inheritance backfill + forward fix.

**Rough estimate**: 3–5 story points (Tier 1 equivalent — single bounded fix, existing columns
only, no new instrumentation).

**Comparable past feature**: no single directly-comparable completed feature was cited by name in
the legs; the closest anchor is the *shape* of DI-4d (a bounded parser/derivation fix scoped to one
platform's capture path, closed within this same routing-feedback initiative). Treat the 3–5 pt
figure as a size-class estimate, not an H5-verified anchor — flag this honestly rather than
manufacturing false precision.

**Major cost drivers**:
- Repository/service-layer inheritance logic: propagate a known parent `skill_name` to a
  `subagent`/child row at write time (forward fix) — small, isolated change per capture-path
  leg's trace (`backend/db/repositories/sessions.py:244`, `postgres/sessions.py:179`).
- Historical backfill: zero lead time, but needs the corrected `(id, project_id)`-scoped join
  (capture-path leg §0/§4) to avoid the id-collision fan-out bug both legs independently hit.
- Test coverage for the "some subagents derive skill independently of the parent chain" edge case
  (`child_has_skill=true, parent_has_skill=false, n=467` system-wide, null-population leg §3) — the
  fix must not overwrite an independently-derived value.

---

## 4. Value Statement

**Primary beneficiaries**: any consumer reading `skill_name` off individual session/subagent rows
(session-detail UI, transcript views, per-skill analytics) — **not** the routing-feedback key space,
which this brief concludes cannot be materially rescued.

**Evidence of demand**:
- System-wide inheritance failure rate is 51.3% (1,834 of 3,764 subagent sessions with a
  skill-bearing parent still show a NULL `skill_name` on the child) — a real, general correctness
  gap independent of this exploration's routing-key motivation (null-population leg §3).
- The gap is not cohort-specific: measured against the *entire* `sessions` table, not just the
  113-key NULL cohort, confirming it as a durable data-quality issue worth fixing on its own terms.

**Counterfactual**: If not built, session-detail and per-skill analytics surfaces continue
mis-attributing roughly half of subagent sessions whose parent's skill is known, and the artifact
usage/attribution pipeline undercounts skill invocations by the same margin. The routing-key
coverage problem is unaffected either way — this is a correctness fix, not a mitigation.

---

## 5. Risks & Blast Radius

| Risk | Category | Severity | Mitigation |
|------|----------|---------|------------|
| The subagent-inheritance fix gets scoped as a "DI-1 unblocker" by a future reader skimming only the headline (31% row-level win) | organizational | M | This brief states explicitly, twice, that the fix is decoupled and does not move the routing-key coverage number past ~45%; cite this brief, not just the leg findings, when scoping. |
| Codex's zero-signal capture gap is later assumed fixable once "someone looks at the raw JSONL" | technical | M | Capture-path leg confirmed to DB-scope limits: no retained proxy (artifacts, tool usage, command_slug) carries any Codex skill signal across 3,482 sessions, all-time, zero exceptions. Any Codex fix requires a raw-transcript-level investigation outside this leg's scope before it can even be sized — treat as an open question, not a known gap. |
| A future contributor attempts a key-redefinition migration (task_class, coalesce chain) based on intuition rather than the measured numbers here | technical | L | Key-redefinition leg's §2/§4 give exact measured coverage and exact contract-cost citations (`PRIMARY KEY`, `_NATURAL_KEY_COLUMNS`, DTO fields) for every candidate; point any future proposal at that table first. |
| `sessions.id` non-uniqueness (19,260 rows / 17,844 distinct) silently inflates future parent/root self-joins on this table, as it did in both legs' first drafts | technical | M | Both legs independently caught and corrected it; recommend appending it to `docs/project_plans/exploration/routing-feedback-success-signal/spikes/SHARED-CONTEXT.md` as a standing gotcha (not done by this brief — a recommendation only). |

---

## 6. Architectural Implications

No ADR is warranted. The candidate decision — "keep `(project_id, skill_name, model)` as the
persisted key and document sub-100% coverage as a contract state" — is not an architectural
decision that exists independent of the verdict; it *is* the no-go verdict's specific redirect, not
a choice that would also apply under a "go." It is also not new architecture: it is the existing
null-over-fabrication precedent (already applied to `success_rate`, `regression_rate`, `cost_index`
per the DI-4a/DI-4b line of work) extended to `skill_name` coverage, verbatim. Drafting an ADR here
would document a convention already established elsewhere, not a new decision.

The one artifact worth updating is **not** an ADR: `SHARED-CONTEXT.md`'s measurement recipe should
gain the `sessions.id` non-uniqueness gotcha (both legs hit it independently; see Risks table). This
is a documentation update to a shared measurement helper, not an architectural decision.

---

## 7. Verdict

**Verdict**: no-go (on attribution-as-a-fix for the routing key)
**Confidence**: 0.78 (mean of the three legs' 0.75/0.8/0.75, no material disagreement between legs)

**Rationale**:

The charter's go bar is ">=60% of min_sample-clearing keys non-NULL." Measured status quo is
74/187 = 39.6% (key-redefinition leg §2.1). The only bounded, honest fix identified — Claude Code
subagent→parent skill inheritance — converts 10 of 113 NULL keys (capture-path leg §4), for a
ceiling of (74+10)/187 = 44.9%. That ceiling is well below 60% and cannot be closed further: the
Codex side of the NULL population (37 of 113 keys, 33%) is a total, all-time, zero-exception
capture absence with no retained proxy (capture-path leg §2) — not a wiring bug, an irreducible
floor. This triggers the charter's deal-killer as written: the NULL population is dominated by
sessions that are either genuinely skill-less (~70% of the non-Codex NULL population, per
null-population leg §2) or structurally unattributable (Codex), and no honest derivation exists to
close the remaining gap without fabricating a skill.

**Why this is a no-go, not a conditional**, despite the charter's conditional criterion reading
close to this shape ("attribution is improvable but only for one platform/launcher cohort, leaving
a skewed key space"). The distinction is subtle and worth stating precisely: the conditional
criterion presumes the platform-skewed fix is *material* — large enough that adopting it would
leave a real, exploitable-but-biased improvement someone might be tempted to ship as-is. Here the
Claude-Code-only fix is indeed platform-skewed, but at 10 of 113 NULL keys (8.8%) it is **immaterial
at the level DI-1 actually consumes** — the key space. It is a real, useful fix at the *row* level
(31.3% of in-window NULL sessions gain a correct attribution, capture-path leg §4) but it does not
create a meaningfully-improved-but-biased key space to be conditional about. The conditional
criterion's premise — "attribution is improvable" at a scale that matters to the key — fails at
exactly the level this exploration was scoped to answer. That collapses the outcome into the
deal-killer's no-go path, not the conditional path.

This is a **redirect, not a terminus**, exactly as the charter's deal-killer anticipated: the
key-redefinition leg ran regardless (per charter instruction) and independently arrived at the same
recommendation this verdict implies — Candidate E, keep the key, document coverage. That leg also
measured every plausible alternative rather than assuming status quo was safest: `task_class`
(Candidate C) is statistically identical to `skill_name` (38.9% vs 39.6%, because
`_resolve_task_class` folds a missing skill into `_unclassified` via the same fallback path,
`routing_rollup.py:497-510`) and buys nothing that isn't already exposed per-row today without a
migration; `command_slug` (Candidate B) is measurably worse (7.8% informative — most sessions never
issue a slash command); a 3-column coalesce chain (Candidate D) buys +1.5 percentage points for a
breaking-change cost. Window-to-window key churn is bad across *every* candidate (Jaccard 0.29–0.35,
key-redefinition leg §3) — an independent property of this session population, not a `skill_name`
defect, and not itself a reason to redefine the key.

**Recommended next action**: archive this charter with verdict no-go/redirect. Adopt the
key-redefinition leg's Candidate E — no schema change, no consumer-contract renegotiation: keep
`(project_id, skill_name, model)`, keep coalescing NULL to `""` at read time as already shipped, and
document the ~40% informative rate as a known contract state in whatever surface communicates
`routing_rollup` coverage to consumers (MeatySkills/`ibm-main` handoff docs). Separately — and
explicitly not as a DI-1 unblocker — scope a small, decoupled Tier 1 follow-up for the Claude Code
subagent-inheritance backfill+forward-fix (§3 Cost Estimate above), justified purely on
session/transcript-correctness and per-skill-analytics grounds.

---

## 8. Citations

- Exploration charter: [routing-key-skill-attribution-charter.md](./routing-key-skill-attribution-charter.md)
- null-population leg: [spikes/null-population/null-population-findings.md](./spikes/null-population/null-population-findings.md)
- capture-path leg: [spikes/capture-path/capture-path-findings.md](./spikes/capture-path/capture-path-findings.md)
- key-redefinition leg: [spikes/key-redefinition/key-redefinition-findings.md](./spikes/key-redefinition/key-redefinition-findings.md)
- DI-4b origin: `docs/project_plans/exploration/routing-feedback-success-signal/routing-feedback-success-signal-synthesis.md` §7 (finding origin), §2 (188-key denominator)
- Shared measurement recipe: `docs/project_plans/exploration/routing-feedback-success-signal/spikes/SHARED-CONTEXT.md` (recommend appending the `sessions.id` non-uniqueness gotcha per §5 Risks above — not applied by this brief)
- Consumer contract: `docs/project_plans/design-specs/routing-feedback-router-merge-handoff.md` §0–§2, §5.4
- Code: `backend/application/services/agent_queries/routing_rollup.py` (`GROUP BY`, `_resolve_task_class`, `apply_mapping`), `backend/db/postgres_migrations.py:1540,1562`, `backend/db/repositories/routing_rollup.py:104`, `backend/parsers/platforms/claude_code/parser.py:1652,2288,1400`, `backend/parsers/platforms/codex/parser.py:953`, `backend/db/repositories/sessions.py:244,246-248`

### Cohort-drift note

The three legs measured slightly different in-window totals (187/113, 187/113, 405/187 across
different query times on the same day) than the charter's original 188/114. This is rolling
30-day-window drift as wall-clock time moved during the exploration, not a methodology
disagreement — every leg disclosed and reconciled it independently. Not reopened here.

---

## Next Actions

| Action | Target | Achieves | Gates/Blockers | Recommended model | Priority |
|---|---|---|---|---|---|
| Archive charter, set `verdict: no-go`, `verdict_rationale` per §7 above | `routing-key-skill-attribution-charter.md` frontmatter | Closes the exploration with a citable, machine-readable verdict | Requires human sign-off (no-go verdicts require it per skill contract) | n/a (CLI/manual edit) | 1 |
| Document ~40% `skill_name` coverage as a contract state for `routing_rollup` consumers | MeatySkills/`ibm-main` handoff docs (`routing-feedback-router-merge-handoff.md` or equivalent) | Makes the coverage number an explicit, agreed contract state rather than a silent gap | None — additive documentation, no code change | documentation-writer (haiku) | 2 |
| Append `sessions.id` non-uniqueness gotcha to shared measurement recipe | `docs/project_plans/exploration/routing-feedback-success-signal/spikes/SHARED-CONTEXT.md` | Prevents a third independent rediscovery of the same join bug | None | documentation-writer (haiku) | 3 |
| Scope decoupled Tier 1 Feature Contract for Claude Code subagent skill-inheritance fix | `docs/project_plans/feature_contracts/[slug].md` (new) | Fixes the 51.3% system-wide inheritance failure for session-detail/analytics correctness — explicitly not a DI-1 unblocker | None named; standard Tier 1 flow | prd-writer / feature-planner (sonnet) | 4 (optional, on its own merits) |
