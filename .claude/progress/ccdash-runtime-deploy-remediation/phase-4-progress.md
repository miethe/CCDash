---
schema_version: 2
doc_type: progress
phase: 4
phase_title: "Finding triage & cleanup (W4)"
feature_slug: ccdash-runtime-deploy-remediation
status: not-started
created: 2026-06-12
updated: 2026-06-12
overall_progress: 0
completion_estimate: null
parallelization:
  strategy: batch-parallel
  batch_1: [T4-001, T4-002, T4-003, T4-004, T4-005, T4-006]
  batch_2: [T4-007]
---

# Phase 4 Progress — Finding triage & cleanup (W4)

## Objective

Resolve or formally defer all 6 accumulated W4 findings from
`.claude/findings/ccdash-core-remediation-findings.md`. Runs in Wave 2 alongside P3
to fill review wait. Every finding exits with `status: resolved` or `status: deferred`
with rationale and promotion trigger.

---

## Task Table

```yaml
tasks:
  - id: T4-001
    name: "F-W3-001 doc patch"
    status: pending
    assigned_to: documentation-writer
    assigned_model: haiku
    model_effort: adaptive
    description: >
      Remove overclaim "across all sync triggers" from AC-8.2 prose in
      ccdash-core-remediation implementation plan; append targeted clarification note.
      No code change. No regression in coverage report.

  - id: T4-002
    name: "F-W3-002 coroutine fix"
    status: pending
    assigned_to: python-backend-engineer
    assigned_model: sonnet
    model_effort: adaptive
    description: >
      Fix three unawaited-coroutine RuntimeWarning instances in
      backend/tests/test_sync_all_projects.py (await coroutines or restructure).
      pytest -W error::RuntimeWarning backend/tests/test_sync_all_projects.py must
      exit 0. Named-module only.

  - id: T4-003
    name: "F-001 FK fixture triage"
    status: pending
    assigned_to: python-backend-engineer
    assigned_model: sonnet
    model_effort: adaptive
    description: >
      Investigate FK fixture failures in session-repository test suites (<=1 hour
      effort cap). Fix if feasible; otherwise update finding to status: deferred with
      root-cause note and target_epic reference.

  - id: T4-004
    name: "F-002 test_runtime_bootstrap comment"
    status: pending
    assigned_to: python-backend-engineer
    assigned_model: sonnet
    model_effort: adaptive
    description: >
      Add header comment to backend/tests/test_runtime_bootstrap.py: "Run as named
      module only (python -m pytest backend/tests/test_runtime_bootstrap.py). Do NOT
      run with a dev server active — causes segfault." No code change.

  - id: T4-005
    name: "F-003 ac-coverage-report fix"
    status: pending
    assigned_to: python-backend-engineer
    assigned_model: sonnet
    model_effort: adaptive
    description: >
      Fix ac-coverage-report.py nested-list verified_by parsing so structured YAML
      AC blocks (with nested lists) are classified as covered, not "uncovered".
      Script run against a phase file with structured ACs reports them as covered.

  - id: T4-006
    name: "F-W6-001 deferred note"
    status: pending
    assigned_to: documentation-writer
    assigned_model: haiku
    model_effort: adaptive
    description: >
      Update finding F-W6-001 to status: deferred; add promotion trigger:
      "if correlation totals are used for billing or quota enforcement".

  - id: T4-007
    name: "Findings close-out"
    status: pending
    assigned_to: documentation-writer
    assigned_model: haiku
    model_effort: adaptive
    description: >
      Update .claude/findings/ccdash-core-remediation-findings.md with final status
      for all 6 findings (F-W3-001, F-W3-002, F-001, F-002, F-003, F-W6-001).
      All 6 must have status: resolved or status: deferred + rationale.
```

---

## AC Coverage

| AC ID | Description | Verified By | Verdict |
|-------|-------------|-------------|---------|
| F-W3-001 | Overclaim text removed | T4-001 doc patch | pending |
| F-W3-002 | `pytest -W error::RuntimeWarning test_sync_all_projects.py` exits 0 | T4-002 | pending |
| F-001 | FK fixture dispositioned (resolved or deferred+note) | T4-003 | pending |
| F-002 | Header comment in `test_runtime_bootstrap.py` | T4-004 | pending |
| F-003 | `ac-coverage-report.py` classifies nested `verified_by` as covered | T4-005 | pending |
| F-W6-001 | Finding shows `status: deferred` + promotion trigger | T4-006 | pending |

---

## Quick Reference

**Batch dispatch hints for orchestrator:**

- **batch_1** → *Six independent tasks — fan out in parallel:*
  - `Task(documentation-writer, "T4-001: remove overclaim prose in ccdash-core-remediation implementation plan AC-8.2")`
  - `Task(python-backend-engineer, "T4-002: fix unawaited-coroutine RuntimeWarnings in backend/tests/test_sync_all_projects.py")`
  - `Task(python-backend-engineer, "T4-003: triage FK fixture failures in session-repository tests — <=1hr effort cap; fix or deferred+note")`
  - `Task(python-backend-engineer, "T4-004: add named-module-only header comment to backend/tests/test_runtime_bootstrap.py")`
  - `Task(python-backend-engineer, "T4-005: fix nested verified_by parsing in .claude/skills/artifact-tracking/scripts/ac-coverage-report.py")`
  - `Task(documentation-writer, "T4-006: mark F-W6-001 status: deferred with promotion trigger in findings doc")`
- **batch_2** → `Task(documentation-writer, "T4-007: findings close-out — set final status for all 6 findings in .claude/findings/ccdash-core-remediation-findings.md")`

**Quality gates before phase close:**
- `pytest -W error::RuntimeWarning backend/tests/test_sync_all_projects.py` passes (named module)
- All 6 findings in `.claude/findings/ccdash-core-remediation-findings.md` dispositioned
- `ac-coverage-report.py` correctly classifies structured AC blocks as covered

**Key files:** `backend/tests/test_sync_all_projects.py`, `backend/tests/test_runtime_bootstrap.py`, `.claude/skills/artifact-tracking/scripts/ac-coverage-report.py`, `.claude/findings/ccdash-core-remediation-findings.md`
