---
type: progress
schema_version: 2
doc_type: progress
prd: automatic-session-naming
feature_slug: automatic-session-naming
title: "Automatic Session Naming - Phase 2: Every session has a better-than-UUID name, with zero model calls (M2)"
phase: 2
status: pending
started: null
completed: null
created: 2026-08-04
updated: 2026-08-04
prd_ref: docs/project_plans/PRDs/enhancements/automatic-session-naming-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/automatic-session-naming-v1.md
commit_refs: []
pr_refs: []
overall_progress: 0
completion_estimate: "on-track"
total_tasks: 4
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
execution_model: sequential
milestone_id: M2
depends_on: ["M1"]
gate_lens: [validator]

tasks:
  - id: "T2-001"
    description: >
      Extend the existing one-hop subagent-inheritance call site
      (backend/db/sync_engine.py:3307, backfill_skill_name_inheritance) so
      Claude subagent sidechains (isSidechain=true) inherit the parent
      session's session_name, provenance derived_deterministic. Fall back to
      the existing agent-name record when no parent name exists. Do not add
      a new inheritance mechanism or extend beyond the single explicit
      one-hop case.
    status: pending
    dependencies: []
    acceptance_refs: ["FR-7"]
    verified_by: []
    evidence: []

  - id: "T2-002"
    description: >
      Codex codex_exec headless sessions fall back to session_meta.payload
      .git.branch (read into AgentSession.gitBranch by T1-002), provenance
      derived_deterministic, when no provider name exists.
    status: pending
    dependencies: []
    acceptance_refs: ["FR-7"]
    verified_by: []
    evidence: []

  - id: "T2-003"
    description: >
      Close the remaining fallback chain (last-prompt, then truncated
      first-message) for any interactive session still unnamed after M1 +
      T2-001/T2-002, so no surface ever renders a bare UUID when a
      deterministic fallback value exists. Enforce the provenance rank at
      every write: a weaker source (derived_deterministic) must never
      overwrite a stronger one (provider_persisted) already present.
    status: pending
    dependencies: ["T2-001", "T2-002"]
    acceptance_refs: ["FR-7"]
    verified_by: []
    evidence: []

  - id: "T2-004"
    description: >
      Test coverage: assert no session in either excluded segment (Claude
      subagent sidechains, Codex codex_exec) renders a bare UUID when a
      parent title or branch value exists; assert every fallback write
      carries derived_deterministic; assert a weaker source never overwrites
      a stronger one. Re-run the no-bare-UUID smoke query and the M1 FE
      runtime smoke to confirm no regression.
    status: pending
    dependencies: ["T2-003"]
    acceptance_refs: ["FR-7"]
    verified_by: []
    evidence: []

parallelization:
  batch_1: ["T2-001", "T2-002"]
  batch_2: ["T2-003"]
  batch_3: ["T2-004"]
  critical_path: ["T2-001", "T2-003", "T2-004"]
  estimated_total_time: "n/a - milestone dispatched as one unit; provider/model resolve at dispatch via delegation-router"

blockers: []

success_criteria:
  - id: "SC-1"
    description: "No surface renders a bare UUID for a session where a deterministic fallback value exists."
    status: pending
  - id: "SC-2"
    description: "Every fallback write carries provenance derived_deterministic."
    status: pending
  - id: "SC-3"
    description: "Subagent inheritance reuses the existing one-hop call site (sync_engine.py:3307) rather than a new mechanism."
    status: pending
  - id: "SC-4"
    description: "A weaker source never overwrites a stronger one already present on session_name."
    status: pending

notes: >
  AC -> command -> evidence row owned by this phase: "No bare UUID /
  fallbacks" -> `backend/.venv/bin/ccdash session search "" --limit 50
  --json` -> every row has a non-UUID session_name with a provenance token.
  Sequencing is load-bearing (plan §Sequencing): M2's fallback chain must not
  overwrite a provider-set name, so M1's provenance rank must already exist
  before any fallback here is written. Depends on M1 (all M1 tasks complete
  and its Mode-D approval landed).
---

# automatic-session-naming - Phase 2: Every session has a better-than-UUID name, with zero model calls (M2)

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

Use CLI to update progress:

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/automatic-session-naming/phase-2-progress.md -t T2-001 -s completed
```

---

## Objective

The deterministic chain closes most of the remaining gap with no model call: subagent sessions
inherit the parent title, Codex headless sessions use `git.branch`, and the remainder falls
through `last-prompt` then a truncated first message.

## Milestone AC (from the implementation plan)

No surface renders a bare UUID; each fallback writes `derived_deterministic`; subagent
inheritance reuses the existing call site rather than a new mechanism; a weaker source never
overwrites a stronger one.

## Gate plan

`gate_lens: [validator]`.

---

## Completion Notes

Summary of phase completion (fill in when phase is complete):

- What was built
- Key learnings
- Unexpected challenges
- Recommendations for next phase
