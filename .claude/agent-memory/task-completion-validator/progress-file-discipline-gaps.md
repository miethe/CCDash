---
name: progress-file-discipline-gaps
description: Recurring pattern in CCDash phase-execution runs — a task summary claims "[completed]" with a commit ref, but the phase progress YAML frontmatter still shows status:pending for that task, and/or a reported mid-phase blocker never gets written into the YAML blockers:[] field.
metadata:
  type: project
---

Observed 2026-07-21 in `.claude/progress/research-foundry-run-telemetry/phase-3-progress.md`:
T3-000 (backend-architect seam task) was reported as `[completed] commit:e3d10af` in the task
summary handed to the reviewer, and the commit is real and substantive (173-line contract-mapping
doc). But the progress YAML's `T3-000` entry still shows `status: pending`, no `started`/`completed`
timestamps, no `evidence` block. Separately, T3-006's own completion report describes a detailed
disk-full (ENOSPC) blocker mid-task, but the YAML's top-level `blockers: []` was never updated to
record it — the Error Recovery policy in the dev-execution skill explicitly requires "Document the
blocker in progress tracker," and that step was skipped even though the same session correctly used
`update-status.py` for T3-001 through T3-005.

**Why:** the progress YAML is the single source of truth other agents/reviewers read cheaply (vs.
re-deriving from git log / task summaries). A completed-looking task summary is not sufficient
evidence on its own — the CLI-first update step is a separate, sometimes-skipped action.

**How to apply:** as a reviewer, always diff the task summary's claimed status against the actual
progress YAML for every task, not just the ones flagged as blocked. A real git commit existing does
not imply the tracker was updated; check both independently. Flag any task marked `[completed]` in
prose but `pending` in YAML as a required fix (cheap CLI-script fix, not a rejection of the
underlying work) — see [[env-disk-full-hazard]] for the related blocker-recording gap.

**Recurrence (2026-07-31, proof-to-routing-loop-v1 Phase 2, T2-004):** same pattern, with a new
wrinkle worth checking for specifically: the skipped task justified the omission by claiming it
"matches the T2-002/T2-003 convention of not touching phase-2-progress.md." `git log --stat` on the
actual T2-002/T2-003 commits (86e97a9, a9506c1) showed each DID have its own dedicated
`docs(progress): mark T2-00x completed` commit updating that exact file — the stated precedent was
false on inspection, not just an inconsistent one-off. Lesson: when a task cites "the same convention
as task X" to justify skipping tracker hygiene, verify task X's actual commits (`git log --stat
<its-sha>`) rather than trusting the citation — a fabricated-precedent excuse is a stronger signal
than a bare omission.

**Recurrence (2026-07-31, proof-to-routing-loop-v1 Phase 5, T5-001–T5-004):** a variant, not a repeat
— here the phase progress YAML (`phase-5-progress.md`) is *honestly* left `status: pending` despite
`completed_tasks: 4`/`progress: 100`, because the executor correctly recognized an unmet, explicit,
plan-authored decision gate (D9: socialize the D5 metric-payload shape to the router owner,
MeatySkills/`ibm-main`, before Phase 5 seals — stated three times in the phase-split plan file
`docs/project_plans/implementation_plans/.../phase-5-transport-surfaces.md`, including an unchecked
Quality Gate checkbox and a still-placeholder `### Learnings` section). This is the *good* half of the
pattern — self-honest status. But the *same* sub-pattern from the T3-006 case recurs: `blockers: []`
in the YAML frontmatter stays empty even though the phase's own Completion Notes prose explicitly
flags the unresolved D9 item as needing an orchestrator decision. Lesson reinforced: `blockers: []`
staying empty is not evidence no blocker exists — always cross-check prose Completion Notes AND any
phase-specific plan-split file's Quality Gates/Learnings sections (not just the progress YAML) before
trusting an empty `blockers` array. Also worth checking: whether new non-trivial logic shipped in the
phase (here, an in-memory FR-7 counter-reassembly function) has real committed test coverage, or only
an uncommitted "manual harness" claimed in the task summary — grep for the function name across
`backend/tests/` rather than trusting the claim.

**Resolution (2026-07-31, same phase, follow-up review)**: both gaps flagged in the entry above were
genuinely closed, verified independently (re-ran tests, re-read code, fetched the GitHub issue via
`gh api`, not just trusted the commit messages): (1) D9 socialization — a real GitHub issue was
opened (`github.com/miethe/MeatySkills/issues/1`, confirmed via `gh api`, content matches the
plan's Learnings section verbatim); (2) enabled/seeded reassembly test coverage —
`test_client_v1_routing_rollup.py` added (21 new tests, all genuinely exercise
`_build_response_from_rows`/`_row_to_key_dto`, confirmed the summation logic byte-matches
`RoutingRollupQueryService.compute_coverage_counters`'s policy by reading both functions
side-by-side). `phase-5-progress.md` flipped `pending`→`completed` correctly. One residual,
cosmetic-only gap survived the fix pass: the phase-*plan* file's own frontmatter
(`phase-5-transport-surfaces.md`) still reads `status: draft` even after the progress YAML and body
Quality Gates section were fully updated to reflect completion — the `complete-phase.py` hygiene hook
(DI-135, documented in root CLAUDE.md) exists for exactly this and apparently wasn't run. Third
variant of the same family: tracker-hygiene gaps show up in the progress YAML, the `blockers[]`
array, AND now the phase-plan doc's own frontmatter — check all three, not just one, on every review.
