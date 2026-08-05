---
type: progress
schema_version: 2
doc_type: progress
prd: automatic-session-naming
feature_slug: automatic-session-naming
title: "Automatic Session Naming - Phase 3: Derived naming closes the remainder, local-by-default (M3)"
phase: 3
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
total_tasks: 5
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
execution_model: sequential
milestone_id: M3
depends_on: ["M2"]
gate_lens: [security, validator]
gate_lens_reason: irreversible-outward
# Carried verbatim from plan wave_plan.M3: the Lane B hosted-egress path is an
# irreversible-outward action (transcript-derived text can leave the box once
# sent) — routing_constraints also pin this milestone's egress boundary as
# claude-primary, no offload, with mandatory Opus review before merge.

tasks:
  - id: "T3-001"
    description: >
      Scaffold SessionNamingSweepJob (backend/adapters/jobs/
      session_naming_sweep_job.py), mirroring AARReviewSweepJob's shape
      exactly (conditional registration in RuntimeContainer.startup(), beside
      the aar_review_sweep_job= block, for worker/worker-watch profiles only).
      Candidate-selection query: session_name IS NULL, excluding rows already
      resolved by M1/M2. Idempotency: any non-null session_name from any
      source is never re-derived.
    status: pending
    dependencies: []
    acceptance_refs: ["FR-12", "FR-15"]
    verified_by: []
    evidence: []

  - id: "T3-002"
    description: >
      Lane A (local) backend: new Ollama HTTP client, selected by
      CCDASH_SESSION_NAMING_BACKEND=local (the default). Naming job reads
      input text via the redacted bundle (session_detail.get_session_detail,
      which already runs redact_entries) — never a raw JSONL read. Test
      asserting default config resolves to the local backend and the hosted
      path is unreachable without the opt-in flag (zero egress by default).
    status: pending
    dependencies: ["T3-001"]
    acceptance_refs: ["FR-13", "FR-14"]
    verified_by: []
    evidence: []

  - id: "T3-003"
    description: >
      Lane B (hosted) backend: reuse backend/services/ai_insight.py's httpx
      transport pattern, gated behind CCDASH_SESSION_NAMING_BACKEND=hosted
      AND the redaction gate (CCDASH_REDACTION_PATTERNS_ENABLED). Every
      outbound Lane B prompt must have passed redact_entries first — assert
      by a positive test before the flag can be flipped on in any deployment.
      Add CCDASH_GEMINI_API_KEY to the compose x-backend-shared-env allowlist
      in this same change (same gap class as 5cb8e00's five other flags).
      MUST stay claude-primary per plan routing_constraints — no offload;
      requires Opus review before merge.
    status: pending
    dependencies: ["T3-001"]
    acceptance_refs: ["FR-13", "FR-14", "FR-18"]
    verified_by: []
    evidence: []

  - id: "T3-004"
    description: >
      Guards: CCDASH_SESSION_NAMING_ENABLED (kill-switch, default false for
      the derive-worker), CCDASH_SESSION_NAMING_QUOTA (default 200/tick),
      CCDASH_SESSION_NAMING_WINDOW_HOURS (default 24),
      CCDASH_SESSION_NAMING_SWEEP_INTERVAL_SECONDS (default 1800) — mirrors
      the AAR-review-loop flag pattern. Fail-open: any model-call failure
      leaves session_name NULL and logs, never crashes the sweep tick or
      blocks the next candidate, never blocks sync. Offline CLI leaves the
      field null as a contract state (worker-only enrichment).
    status: pending
    dependencies: ["T3-001"]
    acceptance_refs: ["FR-16", "FR-17"]
    verified_by: []
    evidence: []

  - id: "T3-005"
    description: >
      Test + security coverage: static-walk-contract test mirroring
      test_aar_review_no_llm_imports.py (inverted — positive assertion that
      no router/service on the read path imports a model client); positive
      redact_entries-before-outbound-prompt assertion test for Lane B;
      zero-egress-by-default test; idempotency test. Opus/security review of
      the Lane B egress path and its redaction-gate wiring before merge, per
      gate_lens: [security, validator].
    status: pending
    dependencies: ["T3-002", "T3-003", "T3-004"]
    acceptance_refs: ["FR-14", "FR-15", "FR-17"]
    verified_by: []
    evidence: []

parallelization:
  batch_1: ["T3-001"]
  batch_2: ["T3-002", "T3-003", "T3-004"]
  batch_3: ["T3-005"]
  critical_path: ["T3-001", "T3-003", "T3-005"]
  estimated_total_time: "n/a - milestone dispatched as one unit; provider/model resolve at dispatch via delegation-router"

blockers: []

success_criteria:
  - id: "SC-1"
    description: "SessionNamingSweepJob is worker-side and persists results; no read/render path calls a model, asserted by test."
    status: pending
  - id: "SC-2"
    description: "Default config performs zero egress, asserted by test; the hosted backend is unreachable without an explicit opt-in flag AND the redaction gate."
    status: pending
  - id: "SC-3"
    description: "Idempotency holds — a session with a non-null session_name from any source is never re-derived."
    status: pending
  - id: "SC-4"
    description: "Quota + kill-switch flags follow the AAR-loop pattern; failures fail open and never block sync."
    status: pending
  - id: "SC-5"
    description: "The offline CLI leaves session_name null as a contract state."
    status: pending

notes: >
  AC -> command -> evidence rows owned by this phase: "Zero egress by
  default" -> `pytest backend/tests/ -k "naming_egress" -v`; "No model call
  on read path" -> `pytest backend/tests/ -k "naming_read_path" -v`.
  gate_lens_reason=irreversible-outward is carried verbatim from the plan's
  wave_plan.M3 — do not drop it when re-deriving this file. Depends on M2
  (idempotency here is defined as "any name already present," which requires
  M1 and M2 to already be populating names).
---

# automatic-session-naming - Phase 3: Derived naming closes the remainder, local-by-default (M3)

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

Use CLI to update progress:

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py \
  -f .claude/progress/automatic-session-naming/phase-3-progress.md -t T3-001 -s completed
```

---

## Objective

A worker-side `SessionNamingSweepJob` names the residual population (28.7% of the local corpus)
via one of two pluggable backends. Local is the default and sends nothing off-box.

## Milestone AC (from the implementation plan)

Job is worker-side and persists results — no read/render path calls a model, asserted by test;
default config performs zero egress, asserted by test; the hosted backend requires both an
explicit opt-in flag and the redaction gate; idempotency holds (never re-derive when any name is
present from any source); quota + kill-switch flags follow the AAR-loop pattern; failures fail
open and never block sync; the offline CLI leaves the field null as a contract state.

## Gate plan

`gate_lens: [security, validator]`, `gate_lens_reason: irreversible-outward` — the Lane B egress
path and its redaction-gate wiring MUST stay claude-primary (no offload) per the plan's
routing_constraints, and require Opus review before merge.

---

## Completion Notes

Summary of phase completion (fill in when phase is complete):

- What was built
- Key learnings
- Unexpected challenges
- Recommendations for next phase
