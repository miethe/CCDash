---
schema_version: 2
doc_type: progress
title: "Phase 0 — Cross-project session correctness — Progress"
status: pending
created: 2026-06-11
updated: 2026-06-11
phase: 0
phase_title: "Cross-project session correctness foundation"
feature_slug: ccdash-core-remediation
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-core-remediation-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-core-remediation-v1.md
phase_plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-core-remediation-v1/phase-0-correctness.md
overall_progress: 0
completion_estimate: 0

owners: []
contributors: []
commit_refs: []
pr_refs: []

tasks:
  - id: T0-001
    subject: "SQLite project_id enforcement"
    status: pending
    assigned_to: data-layer-expert
    assigned_model: sonnet
    description: "Add optional project_id param to get_by_id/get_many_by_ids in backend/db/repositories/sessions.py; strict-equality predicate when non-empty, active-project fallback on None/''."

  - id: T0-002
    subject: "Postgres project_id enforcement"
    status: pending
    assigned_to: data-layer-expert
    assigned_model: sonnet
    description: "Mirror T0-001 in backend/db/repositories/postgres/sessions.py with identical predicate logic in the same change set to avoid backend drift."

  - id: T0-003
    subject: "Call-site audit + threading (~11 sites)"
    status: pending
    assigned_to: data-layer-expert
    assigned_model: sonnet
    description: "Enumerate ~11 invocations of get_by_id/get_many_by_ids/family derivation across routers and agent_queries; forward explicit project_id where in scope, None where intentionally active-bound."

  - id: T0-004
    subject: "Family anchor-derived project_id"
    status: pending
    assigned_to: data-layer-expert
    assigned_model: sonnet
    description: "In get_session_family_v1 (_client_v1_sessions.py:269) derive project_id from the anchor row and thread it through all descendant/ancestor lookups and drilldown queries."

  - id: T0-005
    subject: "ADR-007 collision tests (SQLite)"
    status: pending
    assigned_to: data-layer-expert
    assigned_model: sonnet
    description: "New backend/tests/test_session_repository_project_scope.py: seed two projects with shared session ids; assert get_by_id/get_many_by_ids never leak across projects; cover None and '' project_id with direct-count DB assertions."

  - id: T0-006
    subject: "Collision/parity tests (Postgres)"
    status: pending
    assigned_to: data-layer-expert
    assigned_model: sonnet
    description: "Parameterize the T0-005 fixture to also run against Postgres (CCDASH_DB_BACKEND=postgres); assert identical zero-leak behavior; skip with explicit reason if Postgres unreachable."

  - id: T0-007
    subject: "Family-scope test"
    status: pending
    assigned_to: data-layer-expert
    assigned_model: sonnet
    description: "Assert get_session_family_v1 for a non-active project returns only that project's tree; anchor-not-found-in-project returns empty/None with no active-project fallback."

  - id: T0-008
    subject: "Regression + PG seam review"
    status: pending
    assigned_to: senior-code-reviewer
    assigned_model: sonnet
    description: "Run existing named backend session/repository suites; confirm no active-project regression; Bash-enabled senior-code-reviewer signs off the Postgres WHERE-clause seam (ADR-007 PG-only-bug risk)."

parallelization:
  batch_1:
    # Schema/repo changes — SQLite and Postgres must ship together (same change set, Risk Hotspot: drift)
    tasks: [T0-001, T0-002]
  batch_2:
    # Call-site threading and family scoping — depend on T0-001/T0-002 signatures landing first
    tasks: [T0-003, T0-004]
  batch_3:
    # Tests validate the changes from batches 1+2; collision tests depend on both backends being fixed
    tasks: [T0-005, T0-006, T0-007]
  batch_4:
    # Final gate: regression run + PG seam sign-off; requires all prior tasks complete
    tasks: [T0-008]
---

# Phase 0 — Cross-project session correctness

Mechanical parameter-threading phase: enforce `project_id` on ID-based session reads in both
SQLite and Postgres backends, scope `get_session_family_v1` to anchor-derived project, thread
~11 call sites, and pin a permanent ADR-007 collision-test fixture. Hard prerequisite for
Phases 2 and 3 (cross-project reads).

## Entry Criteria

- PRD `ccdash-core-remediation-v1.md` approved; decisions-block locked (Phases 0–12).
- Diagnostic verdicts confirmed: `get_by_id`/`get_many_by_ids` are project-unsafe in both backends; `get_session_family_v1` is active-project-bound.
- Backend venv available (`backend/.venv`); SQLite default DB present; Postgres reachable for parity tests (or marked skip-with-reason if unavailable).

## Exit Criteria

- ADR-007 collision tests green: two projects with overlapping session IDs — each `get_by_id` returns exactly its own project's row, never the other.
- `get_many_by_ids` enforces project_id in both SQLite and Postgres.
- `get_session_family_v1` is project-scoped; family anchor derives and propagates project_id end-to-end.
- All ~11 ID-based call sites thread project_id; existing backend suites pass; no regression in active-project reads.
- NULL/'' project_id inputs tolerated (documented behavior, not a crash).

## Blockers

_None._
