---
type: context
prd: automatic-session-naming
feature_slug: automatic-session-naming
title: "Automatic Session Naming - Development Context"
status: active
created: 2026-08-04
updated: 2026-08-04
prd_ref: docs/project_plans/PRDs/enhancements/automatic-session-naming-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/automatic-session-naming-v1.md
critical_notes_count: 0
implementation_decisions_count: 0
active_gotchas_count: 0
agent_contributors: []
agents: []
---

# automatic-session-naming - Development Context

> Orientation for the executor of M1/M2/M3, not a summary of the plan. Read the plan
> (`docs/project_plans/implementation_plans/enhancements/automatic-session-naming-v1.md`) for
> full milestone AC and the evidence matrix.

## Extend, don't parallel-build — the three reuses

The rubric is explicit: introducing a new equivalent of any of these is worse even if tests pass.

1. **FE title chain** — `deriveSessionCardTitle` / `deriveTranscriptIntelligenceTitle` in
   `components/SessionCard.tsx`. Already accepts `explicitTitle` and already falls through
   empty-string safely. M1 feeds it `session.sessionName`; it does not get replaced.
2. **Subagent inheritance call site** — `backend/db/sync_engine.py:3307`
   (`backfill_skill_name_inheritance`). M2 extends this one-hop, `(id, project_id)`-scoped join;
   it does not add a second inheritance mechanism.
3. **Worker-sweep-job shape** — `backend/adapters/jobs/aar_review_sweep_job.py` +
   `backend/runtime/container.py` (~210-218). M3's `SessionNamingSweepJob` copies this
   registration/guard/fail-open shape exactly.

## Provenance rank (four tokens, strongest to weakest, plus one reserved)

`provider_persisted` > `derived_deterministic` > `derived_embedding_transfer` (reserved, Lane C,
deferred) > `derived_generative`; `operator_set` reserved, unused. A weaker source must never
overwrite a stronger one already on `session_name`. Unrecognised tokens are "unknown provenance,"
never a hard-fail — same convention as `skill_name_source` / `effort_tier_source`.

## Two non-negotiable constraints

- **No model call on any read/render path.** Every read surface (REST, CLI, MCP, standalone CLI,
  NDJSON) renders an already-persisted `session_name` value. Only `SessionNamingSweepJob` (M3,
  worker-side, scheduled) touches a model.
- **Zero egress by default.** `CCDASH_SESSION_NAMING_BACKEND` defaults to `local` (Ollama). The
  `hosted` lane is CCDash's first transcript-content egress and must be default-off, opt-in, and
  gated behind `redact_entries` before any outbound prompt — assert both by test, not by
  documentation.

## Spikes (source of the measured figures cited in the plan/PRD)

- `docs/project_plans/exploration/automatic-session-naming/spikes/tech-claude-spike.md` —
  `ai-title` coverage/attribution measurements.
- `docs/project_plans/exploration/automatic-session-naming/spikes/tech-codex-spike.md` —
  `thread_name_updated` / `codex_exec` measurements.
- `docs/project_plans/exploration/automatic-session-naming/spikes/integration-spike.md` —
  transport fan-out, resilience table, OQ-1.
- `docs/project_plans/exploration/automatic-session-naming/spikes/derived-naming-spike.md` —
  4th-leg addendum scoping the M3 derive-worker lanes.

## Mode-D reminder

M1 is a schema migration (v49→v50) — halts for explicit human approval before landing against any
shared environment. See `.claude/progress/automatic-session-naming/phase-1-progress.md`
frontmatter (`mode_d: true`).

## References

- Progress: `.claude/progress/automatic-session-naming/phase-{1,2,3}-progress.md`
- Execution ledger (deviations/conservative choices, reviewed at each milestone boundary):
  `.claude/worknotes/automatic-session-naming/implementation-notes.md`
