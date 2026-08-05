---
type: progress
schema_version: 2
doc_type: progress
prd: automatic-session-naming
feature_slug: automatic-session-naming
title: 'Automatic Session Naming - Phase 1: Provider-set names are ingested and visible
  (M1)'
phase: 1
status: completed
started: 2026-08-05T00:00Z
completed: 2026-08-05T02:30Z
created: '2026-08-04'
updated: '2026-08-05'
prd_ref: docs/project_plans/PRDs/enhancements/automatic-session-naming-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/automatic-session-naming-v1.md
commit_refs:
- 9c3d724
- 8c1daf9
- 8d66d9f
- 8f2b3d9
- ed023ae
- b10c896
- 7a6efbf
pr_refs: []
overall_progress: 100
completion_estimate: on-track
total_tasks: 5
completed_tasks: 5
in_progress_tasks: 0
blocked_tasks: 0
execution_model: sequential
milestone_id: M1
depends_on: []
gate_lens:
- validator
mode_d: true
mode_d_reason: 'This phase performs a schema migration (sessions.session_name + sessions.session_name_source,
  schema v49->v50, dual DDL SQLite+Postgres). Per project Mode-D policy (auth · payments/billing
  · schema migrations · data deletion · secret rotation · infrastructure), this HALTS
  for explicit human approval before the migration is applied to any shared environment
  (node PG in particular). This is a process gate, not a technical risk; schedule
  it as an explicit approval checkpoint, not a silent step.

  '
tasks:
- id: T1-001
  description: 'Schema migration: add session_name TEXT + session_name_source TEXT
    (nullable) to `sessions` in BOTH SQLite and Postgres DDL (v49->v50). Add provenance
    module backend/parsers/session_name_provenance.py (four-token closed vocabulary:
    provider_persisted > derived_deterministic > derived_embedding_transfer (reserved)
    > derived_generative; operator_set reserved). Verify COLUMN_PARITY_DRIFT_ALLOWLIST
    stays green (0 new entries expected). MODE-D: halts for explicit human approval
    before landing against a shared environment.

    '
  status: completed
  dependencies: []
  acceptance_refs:
  - FR-1
  - FR-2
  verified_by: []
  evidence:
  - commit: 9c3d724
  started: 2026-08-05T00:00Z
  completed: 2026-08-05T00:00Z
- id: T1-002
  description: 'Parser ingest: Claude Code parser reads the `ai-title` record into
    sessionName/sessionNameSource (provider_persisted), asserting `ai-title.sessionId`
    equals the file''s own session id and skipping on mismatch (handle `.orphaned-<ts>-<hash>`
    suffixes). Codex parser stops discarding `thread_name_updated.thread_name` and
    also reads `session_meta.payload.git.branch` into AgentSession.gitBranch (currently
    hardcoded None) for reuse as M2''s deterministic fallback source.

    '
  status: completed
  dependencies:
  - T1-001
  acceptance_refs:
  - FR-3
  - FR-4
  - FR-5
  verified_by: []
  evidence:
  - test: backend/tests/test_session_naming.py
  - commit: 8c1daf9
  started: 2026-08-05T00:00Z
  completed: 2026-08-05T00:30Z
- id: T1-003
  description: 'Persist + propagate: sessions repositories (SQLite + Postgres) write
    the two new columns via existing INSERT/ON CONFLICT UPDATE path (no new repository
    method). AgentSession (models.py + types.ts) gains sessionName/sessionNameSource.
    Wire routers/api.py (list_sessions, get_session), PlanningAgentSessionCardDTO
    + planning_sessions.py card builders, and client_v1 sessions endpoints. Resolve
    OQ-1 (LinkedFeatureSessionDTO.title reuse-vs-distinct-field) before adding a second
    title field to that DTO.

    '
  status: completed
  dependencies:
  - T1-002
  acceptance_refs:
  - FR-6
  - FR-8
  - FR-9
  - FR-11
  - OQ-1
  verified_by: []
  evidence:
  - test: backend/tests/test_session_name_persistence.py
  - commit: 8f2b3d9
  started: 2026-08-05T00:30Z
  completed: 2026-08-05T01:30Z
- id: T1-004
  description: 'FE title-chain wiring: feed session.sessionName as explicitTitle into
    the existing deriveSessionCardTitle/deriveTranscriptIntelligenceTitle chain (no
    new fallback logic) across SessionCard.tsx, SessionInspector.tsx, SessionInspectorPanels.tsx,
    PlanningAgentSessionBoard.tsx, MultiProjectSessionBoard.tsx. Satisfy AC-ESC-1:
    no surface may render session_name via dangerouslySetInnerHTML or an unsanitised
    raw-HTML/markdown sink. Null session_name must render the per-surface fallback
    (see PRD §11 Resilience Acceptance table) with no crash.

    '
  status: completed
  dependencies:
  - T1-003
  acceptance_refs:
  - FR-10
  - AC-ESC-1
  verified_by: []
  evidence:
  - commit: b10c896
  started: 2026-08-05T01:30Z
  completed: 2026-08-05T02:00Z
- id: T1-005
  description: 'Test + smoke coverage for this milestone: dedicated test file (provenance
    module unit tests, ai-title/thread_name_updated fixtures, sessionId-mismatch skip
    case, column-parity assertion, FE null-resilience vitest coverage); browser smoke
    of session inspector, session links, and planning board per the plan''s AC->command->evidence
    matrix.

    '
  status: completed
  dependencies:
  - T1-004
  acceptance_refs:
  - FR-3
  - FR-4
  - AC-ESC-1
  verified_by: []
  evidence:
  - commit: 7a6efbf
  started: 2026-08-05T02:00Z
  completed: 2026-08-05T02:30Z
parallelization:
  batch_1:
  - T1-001
  batch_2:
  - T1-002
  batch_3:
  - T1-003
  batch_4:
  - T1-004
  critical_path:
  - T1-001
  - T1-002
  - T1-003
  - T1-004
  - T1-005
  estimated_total_time: n/a - milestone dispatched as one unit; provider/model resolve
    at dispatch via delegation-router
blockers: []
success_criteria:
- id: SC-1
  description: Dual DDL (SQLite + Postgres) ships in one change set; COLUMN_PARITY_DRIFT_ALLOWLIST
    check stays green.
  status: met
- id: SC-2
  description: A real Claude Code session (ai-title) and a real Codex session (thread_name_updated)
    each surface their provider name, provenance provider_persisted, in session detail,
    search, and the planning board.
  status: met
- id: SC-3
  description: session_name is escaped/sanitised on every FE render path (AC-ESC-1);
    no surface renders it as trusted HTML.
  status: met
- id: SC-4
  description: Null session_name renders the defined per-surface fallback (PRD §11
    table) on every listed surface; no crash.
  status: met
- id: SC-5
  description: OQ-1 (LinkedFeatureSessionDTO.title) is resolved before a second title
    field is added to that DTO.
  status: met
notes: 'AC -> command -> evidence rows owned by this phase (full matrix lives in the
  plan): "Dual DDL + parity" -> `pytest backend/tests/ -k "column_parity" -v`; "Provider
  names ingest" -> `pytest backend/tests/test_session_naming.py -v`; "Attribution
  assertion" (same file, mismatch case); "Null resilience (FE)" -> `npx vitest run
  components/__tests__`; "Runtime smoke (UI)" -> `npm run dev` + browser check. Sequencing
  is load-bearing (plan §Sequencing): the provenance rank established here must exist
  before M2 writes any fallback, and the schema migration is a serialization barrier
  — nothing else may land against the `sessions` table concurrently while T1-001 is
  in flight.

  '
progress: 100
---

# automatic-session-naming - Phase 1: Provider-set names are ingested and visible (M1)

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

Use CLI to update progress:

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/automatic-session-naming/phase-1-progress.md -t T1-001 -s completed
```

---

## Objective

Both provider-set names (Claude Code `ai-title`, Codex `thread_name_updated`) reach the
database and every read surface, with provenance `provider_persisted`, escaped on render, and
resilient to null.

## Mode-D — halts for explicit human approval

This milestone's first task (T1-001) is a schema migration (`sessions.session_name` +
`sessions.session_name_source`, v49→v50, dual DDL). Per the project's Mode-D policy, this halts
for explicit human approval before landing against any shared environment — do not proceed past
T1-001 without that approval, and treat it as a serialization barrier: nothing else may land
against the `sessions` table concurrently while it is in flight.

## Milestone AC (from the implementation plan)

Dual DDL + parity check green; a real Claude Code session and a real Codex session each surface
their provider name in detail, search, and the planning board; `session_name` is escaped on
render (it can arrive caller-controlled via the NDJSON ingest path); null renders the defined
per-surface fallback; OQ-1 resolved before a second title field is added to the same DTO.

## Gate plan

`gate_lens: [validator]` — deliberately not security-gated (this extends an established
parse+render contract; escaping is tracked as AC-ESC-1, not a security-review trigger).

---

## Completion Notes

Summary of phase completion (fill in when phase is complete):

- What was built
- Key learnings
- Unexpected challenges
- Recommendations for next phase
