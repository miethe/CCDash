---
title: "Implementation Plan — Phase 0: Cross-project session correctness"
schema_version: 2
doc_type: phase_plan
status: draft
created: 2026-06-10
updated: 2026-06-10
phase: 0
phase_title: "Cross-project session correctness"
prd_ref: /Users/miethe/dev/homelab/development/CCDash/docs/project_plans/PRDs/enhancements/ccdash-core-remediation-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-core-remediation-v1.md
feature_slug: ccdash-core-remediation
feature_version: "v1"
scope: "Enforce project_id on ID-based session reads (SQLite + Postgres) with NULL/'' tolerance, propagate project_id through session-family derivation, audit/fix drilldown queries, thread ~11 call sites, and pin ADR-007 collision tests — the hard prerequisite for all cross-project reads."
effort_estimate: "3 pts"
priority: critical
risk_level: high
category: "product-planning"
tags: [implementation, phase, cross-project, correctness, data-layer, adr-007]
adr_refs:
  - docs/project_plans/adrs/adr-007-db-write-failure-surfacing-standard.md
related_documents:
  - /Users/miethe/dev/homelab/development/CCDash/docs/project_plans/PRDs/enhancements/ccdash-core-remediation-v1.md
  - /Users/miethe/dev/homelab/development/CCDash/.claude/worknotes/ccdash-core-remediation/decisions-block.md
  - docs/project_plans/reports/investigations/ccdash-core-remediation-diagnostic-v1.md
changelog_required: true
files_affected:
  - backend/db/repositories/sessions.py
  - backend/db/repositories/postgres/sessions.py
  - backend/routers/_client_v1_sessions.py
  - backend/db/repositories/base.py
  - backend/tests/test_session_repository_project_scope.py
entry_criteria:
  - "PRD `ccdash-core-remediation-v1.md` approved; decisions-block locked (Phases 0–12)."
  - "Diagnostic verdicts confirmed: `get_by_id`/`get_many_by_ids` are project-unsafe in both backends; `get_session_family_v1` is active-project-bound."
  - "Backend venv available (`backend/.venv`); SQLite default DB present; Postgres reachable for parity tests (or marked skip-with-reason if unavailable)."
exit_criteria:
  - "ADR-007 collision tests green: two projects with overlapping session IDs — each `get_by_id` returns exactly its own project's row, never the other."
  - "`get_many_by_ids` enforces project_id in both SQLite and Postgres."
  - "`get_session_family_v1` is project-scoped; family anchor derives and propagates project_id end-to-end."
  - "All ~11 ID-based call sites thread project_id; existing backend suites pass; no regression in active-project reads."
  - "NULL/'' project_id inputs tolerated (documented behavior, not a crash)."
---

# Implementation Plan — Phase 0: Cross-project session correctness

**Plan ID**: `IMPL-2026-06-10-CCDASH-CORE-REMEDIATION-P0`
**Date**: 2026-06-10
**Author**: Implementation Planner Agent
**Parent PRD**: `/Users/miethe/dev/homelab/development/CCDash/docs/project_plans/PRDs/enhancements/ccdash-core-remediation-v1.md`
**Decisions Block**: `.claude/worknotes/ccdash-core-remediation/decisions-block.md`
**ADRs**: ADR-006 (DB-authoritative registry), ADR-007 (DB write failure surfacing)

**Complexity**: Small (mechanical param-threading + tests across two backends)
**Total Estimated Effort**: 3 pts
**Wave**: 1 (blocking — no other phase ships before this is green)

## Overview

CCDash's session repositories were written for a single active project. `get_by_id` and
`get_many_by_ids` omit `project_id` from their WHERE clauses in **both** backends despite a
composite primary key `(project_id, id)`. `get_session_family_v1` is active-project-bound.
These defects are dormant today (only the active project is read) but turn active the moment
cross-project reads ship in Phases 2/3 — they would return rows from the **wrong project**.

This phase is a **hard prerequisite** (per PRD §Constraints and decisions-block Risk Hotspots):
Phases 2 and 3 are blocked until Phase 0 is green. The work is deliberately mechanical —
thread a `project_id` parameter through ID-based reads, scope family derivation, audit drilldown
queries, and pin a permanent collision-test fixture. It does **not** introduce new retrieval
engines or response shapes.

Architecture and conventions are defined in root `CLAUDE.md` (Router→Service→Repository pattern;
"Independent SQLite connections must issue `PRAGMA busy_timeout = 30000`"; "Every new write path
must use `retry_on_locked` and ship a direct-count assertion test" per ADR-007). This plan does
not restate them — it references them.

### Design notes (bake in; do not re-discover)

- **Backward compatibility**: `project_id` is added as an **optional** parameter. When `None`,
  the read falls back to the current active-project-resolution behavior so existing callers and
  the active-project hot path are unchanged. New cross-project callers pass an explicit `project_id`.
- **NULL/'' tolerance**: A passed `project_id` that is `None` or empty string `''` must not crash
  and must not silently match arbitrary rows. Empty/None → treat as "unscoped, resolve active"
  (documented). A concrete non-empty `project_id` → strict equality in WHERE clause.
- **Family anchor**: `get_session_family_v1` derives `project_id` from the anchor session row
  rather than from the active-project singleton, then threads that derived id to all descendant/
  ancestor lookups.
- **Two-backend parity**: Every WHERE-clause change ships in both `sessions.py` (SQLite) and
  `postgres/sessions.py` in the **same change set** (Risk Hotspot: column/clause drift).
- **No new columns** in this phase — the composite PK already carries `project_id`.

### Files affected (from decisions-block key-files — NOT re-read here)

| File | Role in Phase 0 |
|------|-----------------|
| `backend/db/repositories/sessions.py` (≈206 `get_by_id`, ≈215 `get_many_by_ids`) | SQLite project_id enforcement |
| `backend/db/repositories/postgres/sessions.py` (≈142 `get_by_id`, ≈148 `get_many_by_ids`) | Postgres project_id enforcement |
| `backend/routers/_client_v1_sessions.py` (≈269 `get_session_family_v1`) | Family anchor-derived project_id + drilldown scope |
| `backend/db/repositories/base.py` | `retry_on_locked` usage on any touched write path (ADR-007) |
| `backend/tests/test_session_repository_project_scope.py` (new) | ADR-007 collision + parity + NULL/'' tolerance tests |

## Entry Criteria

See frontmatter `entry_criteria`. Summary: PRD approved, diagnostic verdicts confirmed, venv +
both DB backends available (Postgres skip-with-reason permitted if unreachable).

## Exit Criteria

See frontmatter `exit_criteria`. The phase **cannot** be marked `completed` while any ADR-007
collision test is red or any existing backend suite regresses. There are no `*.tsx` files in this
phase, so no runtime smoke gate applies (R-P4 not triggered).

## Acceptance Criteria (structured)

The cross-cutting ACs below use scope words ("both backends", "all ID-based reads", "end-to-end")
and therefore expand per **Plan Generator Rule R-P1**. These are backend/data-layer ACs with no UI
surfaces, so `target_surfaces` lists transport/data surfaces (path strings) rather than `.tsx`
components, and `visual_evidence_required` is `false`.

#### AC P0.1: project_id enforced on all ID-based session reads (both backends)
- target_surfaces:
    - backend/db/repositories/sessions.py            # get_by_id, get_many_by_ids (SQLite)
    - backend/db/repositories/postgres/sessions.py   # get_by_id, get_many_by_ids (Postgres)
- propagation_contract: >
    Each read accepts an optional `project_id`. When a non-empty value is supplied it is added to
    the WHERE clause as strict equality alongside the existing id predicate (composite PK
    (project_id, id)). When None/'' it falls back to active-project resolution unchanged.
    Both backends apply identical predicate logic in the same change set.
- resilience: >
    project_id=None or '' → unscoped active-project resolution (current behavior, no crash).
    project_id present but matching no row → returns None / empty list (not another project's row).
- visual_evidence_required: false
- verified_by:
    - T0-005
    - T0-006

#### AC P0.2: Zero cross-project row leak (ADR-007 collision fixture, permanent)
- target_surfaces:
    - backend/tests/test_session_repository_project_scope.py
    - backend/db/repositories/sessions.py
    - backend/db/repositories/postgres/sessions.py
- propagation_contract: >
    Seed two projects with the SAME session id. get_by_id(id, project_id=A) returns A's row;
    get_by_id(id, project_id=B) returns B's row; neither ever returns the other. get_many_by_ids
    with mixed/colliding ids returns only the rows for the requested project. Asserted against both
    backends (Postgres skip-with-reason if unreachable).
- resilience: >
    Test also covers absent project (returns None) and empty-string project_id (resolves active,
    no leak). Uses direct-count DB assertions per ADR-007, not service-layer mocks.
- visual_evidence_required: false
- verified_by:
    - T0-005
    - T0-006

#### AC P0.3: Session family derivation is project-scoped (anchor-derived, end-to-end)
- target_surfaces:
    - backend/routers/_client_v1_sessions.py   # get_session_family_v1 (~269)
- propagation_contract: >
    get_session_family_v1 derives project_id from the anchor session row (not the active-project
    singleton) and threads that derived project_id into every descendant/ancestor lookup and any
    drilldown query it issues, so a family request for a non-active project returns that project's
    tree only.
- resilience: >
    Anchor not found in the requested project → empty/None family (no fallback to active project).
    Missing/None project_id on the request → resolves active project (documented), no leak.
- visual_evidence_required: false
- verified_by:
    - T0-007
    - T0-008

#### AC P0.4: All ID-based call sites thread project_id; active-project path unchanged
- target_surfaces:
    - backend/routers/_client_v1_sessions.py
    - backend/routers/agent.py
    - backend/application/services/agent_queries/
    - backend/db/repositories/sessions.py
    - backend/db/repositories/postgres/sessions.py
- propagation_contract: >
    The ~11 call sites that invoke get_by_id / get_many_by_ids / family derivation are audited and
    updated to forward an explicit project_id where one is in scope; sites with no cross-project
    context pass None and retain active-project behavior. No call site silently drops project_id.
- resilience: >
    Existing active-project reads behave identically (regression-guarded by existing suites).
    Any unscoped site is documented as intentionally active-bound in the audit task notes.
- visual_evidence_required: false
- verified_by:
    - T0-003
    - T0-008

## Task Table

**Column conventions** (per template): `Estimate` = task size (points); `Model` = executor model;
`Effort` = reasoning budget (claude: `adaptive`|`extended`). Subagent + model routing follow the
decisions-block Agent Routing / Model Routing tables (executors sonnet/adaptive; docs haiku/adaptive;
PG seam review escalates to a Bash-enabled `senior-code-reviewer`).

| Task ID | Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort |
|---------|------|-------------|---------------------|----------|-------------|-------|--------|
| T0-001 | SQLite project_id enforcement | Add optional `project_id` param to `get_by_id` / `get_many_by_ids` in `backend/db/repositories/sessions.py` (~206/~215); add strict-equality predicate when non-empty; fall back to active resolution on None/''. Preserve `PRAGMA busy_timeout = 30000` on any independent connection; route any touched write through `retry_on_locked` (ADR-007). | AC P0.1 (SQLite half); active-project reads unchanged | 1 pt | data-layer-expert | sonnet | adaptive |
| T0-002 | Postgres project_id enforcement | Mirror T0-001 in `backend/db/repositories/postgres/sessions.py` (~142/~148) with identical predicate logic, in the same change set to avoid backend drift (Risk Hotspot: column/clause drift). | AC P0.1 (Postgres half); parity with SQLite predicate | 1 pt | data-layer-expert | sonnet | adaptive |
| T0-003 | Call-site audit + threading (~11 sites) | Enumerate the ~11 invocations of `get_by_id` / `get_many_by_ids` / family derivation across `_client_v1_sessions.py`, `routers/agent.py`, and `application/services/agent_queries/`; forward explicit `project_id` where in scope, pass None where intentionally active-bound, and record each decision in task notes. No silent drops. | AC P0.4 | 0.5 pts | data-layer-expert | sonnet | adaptive |
| T0-004 | Family anchor-derived project_id | In `get_session_family_v1` (`_client_v1_sessions.py:269`) derive `project_id` from the anchor row and thread it through descendant/ancestor lookups and drilldown queries; audit any other active-project-bound drilldown queries in this module and fix. | AC P0.3 | 0.5 pts | data-layer-expert | sonnet | adaptive |
| T0-005 | ADR-007 collision tests (SQLite) | New `backend/tests/test_session_repository_project_scope.py`: seed two projects with shared session ids; assert `get_by_id`/`get_many_by_ids` never leak across projects; cover None and '' project_id; direct-count DB assertions per ADR-007. Runnable as a named test file (never unscoped `pytest backend/tests`). | AC P0.1, AC P0.2 (SQLite) | 0.5 pts | data-layer-expert | sonnet | adaptive |
| T0-006 | Collision/parity tests (Postgres) | Parameterize the T0-005 fixture to also run against Postgres (`CCDASH_DB_BACKEND=postgres`); assert identical zero-leak behavior. If Postgres is unreachable in this environment, mark skip with explicit reason (not silent pass). | AC P0.1, AC P0.2 (Postgres) | 0.5 pts | data-layer-expert | sonnet | adaptive |
| T0-007 | Family-scope test | Assert `get_session_family_v1` for a non-active project returns only that project's tree; anchor-not-found-in-project returns empty/None (no active-project fallback). | AC P0.3 | 0.25 pts | data-layer-expert | sonnet | adaptive |
| T0-008 | Regression + PG seam review | Run existing named backend session/repository suites; confirm no active-project regression. Escalate the WHERE-clause changes to a **Bash-enabled** `senior-code-reviewer` for PG seam sign-off (per memory: edit-less reviewers missed 3 PG-only bugs). | AC P0.4; no regression; PG seam signed off | 0.25 pts | senior-code-reviewer (WITH Bash) | sonnet | adaptive |

### Test invocation note

Per user-memory hazard ("CCDash pytest collection hangs"): run the new and existing tests as
**named files**, e.g.:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_session_repository_project_scope.py -v
```

Never run an unscoped `pytest backend/tests`.

## Phase 0 Quality Gates

- [ ] AC P0.1 — project_id enforced on `get_by_id` / `get_many_by_ids` in **both** backends (T0-001, T0-002).
- [ ] AC P0.2 — ADR-007 collision tests green: 2 projects, shared ids, zero leak; direct-count assertions (T0-005, T0-006).
- [ ] AC P0.3 — `get_session_family_v1` project-scoped via anchor-derived project_id, end-to-end (T0-004, T0-007).
- [ ] AC P0.4 — ~11 ID-based call sites audited + threaded; active path unchanged (T0-003).
- [ ] NULL/'' project_id tolerated (documented, no crash, no leak).
- [ ] Existing named backend suites pass (no active-project regression).
- [ ] Bash-enabled `senior-code-reviewer` signs off the Postgres seam (T0-008).
- [ ] **task-completion-validator** confirms all ACs map to passing verification tasks.

## Quality Gate / Sign-off

- **Primary validator**: `task-completion-validator` (mandatory per CLAUDE.md phase-exit policy).
- **Special gate (this phase)**: `senior-code-reviewer` **WITH Bash** for the Postgres seam
  (decisions-block Agent Routing, Phase 0 reviewer; ADR-007 PG-only-bug risk). This is in addition
  to, not a substitute for, the validator.
- **No runtime smoke gate**: no `*.tsx` in `files_affected` (R-P4 not triggered); this is a pure
  data-layer phase. A clean named-test pass + PG seam review is the bar.

## Dependencies & Downstream

- **Blocks**: Phase 2 (`/api/v1` detail/transcript) and Phase 3 (MCP/CLI session tools) — neither
  may ship before Phase 0 is green (PRD §Constraints; decisions-block critical path `0 → 1 → 2 → 3`).
- **Depended on by**: every cross-project read in the program. The collision fixture (T0-005/006)
  is a **permanent** regression guard, not a one-time check.

## Risk Notes (phase-local)

| Risk | Severity | Mitigation |
|------|----------|------------|
| Cross-project read leaks wrong project's rows | High | Phase 0 is a hard prerequisite; T0-005/006 assert project_id never returns another project's rows; downstream phases blocked until green. |
| Backend predicate drift (SQLite vs Postgres) | High | T0-001 and T0-002 ship in the same change set; parity asserted by T0-006. |
| Silent active-project fallback masking a missing project_id | Med | NULL/'' tolerance is explicit + documented; T0-007 asserts anchor-not-found returns empty (no silent active fallback). |
| Postgres unavailable in dev env | Low | T0-006 permits skip-with-reason; PG seam review (T0-008) still required before sign-off. |
