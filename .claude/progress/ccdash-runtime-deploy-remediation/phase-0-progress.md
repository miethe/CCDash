---
schema_version: 2
doc_type: progress
phase: 0
phase_title: "Registry-authoritative project resolution (W1)"
feature_slug: ccdash-runtime-deploy-remediation
status: not-started
created: 2026-06-12
updated: 2026-06-12
overall_progress: 0
completion_estimate: null
runtime_smoke: pending
parallelization:
  strategy: batch-parallel
  batch_1: [T0-001]
  batch_2: [T0-002]
  batch_3: [T0-003, T0-004]
  batch_4: [T0-005]
  batch_5: [T0-006]
  batch_6: [T0-007]
  batch_7: [T0-008]
  batch_8: [T0-009]
---

# Phase 0 Progress — Registry-authoritative project resolution (W1)

## Objective

Fix the registry-authority leak in project selection: `list_projects()` returns active project first
(`ORDER BY is_active DESC`), expose `is_seed` as a computed model field, and guard the FE app-shell
scope so a stale non-active project does not short-circuit `getActiveProject()` on first load.
T0-005 is the seam gate: no FE change may merge until the API contract is verified.

---

## Task Table

```yaml
tasks:
  - id: T0-001
    name: "list_projects() ORDER BY"
    status: pending
    assigned_to: python-backend-engineer
    assigned_model: sonnet
    model_effort: adaptive
    description: >
      Change ORDER BY in backend/db/repositories/projects.py from
      created_at ASC to is_active DESC, created_at ASC so the active
      project is always list[0]. ADR-006 compliant; boolean sort is index-safe.

  - id: T0-002
    name: "is_seed model field"
    status: pending
    assigned_to: python-backend-engineer
    assigned_model: sonnet
    model_effort: adaptive
    description: >
      Add is_seed: bool = False to backend/models.py:Project; populate in
      list_projects() via allowlist check on project.id. Computed field —
      no DDL change; COLUMN_PARITY_DRIFT_ALLOWLIST note: model-computed, N/A.

  - id: T0-003
    name: "Registry tests"
    status: pending
    assigned_to: python-backend-engineer
    assigned_model: sonnet
    model_effort: adaptive
    description: >
      Add/update backend/tests/test_projects_registry.py: (a) first item is
      is_active=true; (b) seed projects is_seed=True; (c) direct-count assertion
      (ADR-007 pattern). Named-module run only.

  - id: T0-004
    name: "get_active() path regression"
    status: pending
    assigned_to: python-backend-engineer
    assigned_model: sonnet
    model_effort: adaptive
    description: >
      Verify SELECT WHERE is_active=1 LIMIT 1 returns correct row after ORDER BY
      change; add regression test. Active project returned correctly; no side effects.

  - id: T0-005
    name: "Seam — API contract gate"
    status: pending
    assigned_to: python-backend-engineer
    assigned_model: sonnet
    model_effort: adaptive
    description: >
      curl /api/projects: confirm active project is list[0] with is_active=true
      and is_seed field present. Document result in P0 progress notes.
      FE merge BLOCKED until this passes. integration_owner = BE.

  - id: T0-006
    name: "App-shell scope guard"
    status: pending
    assigned_to: ui-engineer
    assigned_model: sonnet
    model_effort: adaptive
    description: >
      In contexts/AppSessionContext.tsx:refreshProjects(): if scopedProject.is_active
      === false AND normalizedProjects.some(p => p.is_active), call setProjectScope(null)
      and proceed to getActiveProject(). Resilience: 404 → setActiveProject(null), no crash.

  - id: T0-007
    name: "is_seed visual indicator"
    status: pending
    assigned_to: ui-engineer
    assigned_model: sonnet
    model_effort: adaptive
    description: >
      Add is_seed badge/label in project switcher component. Treat missing/null
      is_seed as false — no throw, no hidden project.

  - id: T0-008
    name: "Runtime smoke gate (R-P4)"
    status: pending
    assigned_to: ui-engineer
    assigned_model: sonnet
    model_effort: adaptive
    description: >
      Start dev stack; open browser: (a) active project sessions visible on first
      load with no manual switch; (b) clear localStorage → active project still loads.
      visual_evidence_required: true. Unit pass is NOT a substitute.

  - id: T0-009
    name: "Regression — scope persistence"
    status: pending
    assigned_to: ui-engineer
    assigned_model: sonnet
    model_effort: adaptive
    description: >
      Switch to non-seed is_active=true project B, reload, confirm project B still
      selected. Default-only logic must not stomp explicit selection.
```

---

## AC Coverage

| AC ID | Description | Verified By | Verdict |
|-------|-------------|-------------|---------|
| AC-T0-002-R-P2 | `is_seed` present on `/api/projects`; absent/null → false on FE | T0-003, T0-005 | pending |
| AC-T0-006-R-P2/R-P3/R-P4 | Scope guard clears stale non-active scope; 404 resilience | T0-008, T0-009 | pending |

---

## Quick Reference

**Batch dispatch hints for orchestrator:**

- **batch_1** → `Task(python-backend-engineer, "T0-001: list_projects() ORDER BY fix in backend/db/repositories/projects.py")`
- **batch_2** → `Task(python-backend-engineer, "T0-002: is_seed model field in backend/models.py, populate in list_projects()")`
- **batch_3** → `Task(python-backend-engineer, "T0-003: registry tests in backend/tests/test_projects_registry.py")` + `Task(python-backend-engineer, "T0-004: get_active() path regression test")`
- **batch_4** → `Task(python-backend-engineer, "T0-005: seam API contract gate — curl /api/projects, document result, block FE on failure")`
- **batch_5** → `Task(ui-engineer, "T0-006: App-shell scope guard in contexts/AppSessionContext.tsx")`
- **batch_6** → `Task(ui-engineer, "T0-007: is_seed visual indicator in project switcher")`
- **batch_7** → `Task(ui-engineer, "T0-008: Runtime smoke gate — browser smoke, screenshot evidence required")`
- **batch_8** → `Task(ui-engineer, "T0-009: Regression — scope persistence across reload")`

**Quality gates before phase close:**
- `pytest backend/tests/test_projects_registry.py` passes (named module)
- `curl GET /api/projects` → `[0].is_active==true`, `is_seed` field present
- Runtime smoke screenshot on file (T0-008); `runtime_smoke: skipped` + reason if unavailable
- Regression T0-009 passes

**Key files:** `backend/db/repositories/projects.py`, `backend/models.py`, `backend/routers/projects.py`, `contexts/AppSessionContext.tsx`
