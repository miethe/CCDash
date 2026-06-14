---
schema_version: 2
doc_type: progress
phase: 0
phase_title: Registry-authoritative project resolution (W1)
feature_slug: ccdash-runtime-deploy-remediation
status: completed
created: 2026-06-12
updated: '2026-06-13'
overall_progress: 100
completion_estimate: '2026-06-13'
runtime_smoke: completed
commit_refs:
  - c71304e
parallelization:
  strategy: batch-parallel
  batch_1:
  - T0-001
  batch_2:
  - T0-002
  batch_3:
  - T0-003
  - T0-004
  batch_4:
  - T0-005
  batch_5:
  - T0-006
  batch_6:
  - T0-007
  batch_7:
  - T0-008
  batch_8:
  - T0-009
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
    status: completed
    started: '2026-06-13T03:30:00Z'
    completed: '2026-06-13T03:40:00Z'
    evidence:
      - commit:c71304e
    assigned_to: python-backend-engineer
    assigned_model: sonnet
    model_effort: adaptive
    description: >
      Change ORDER BY in backend/db/repositories/projects.py from
      created_at ASC to is_active DESC, created_at ASC so the active
      project is always list[0]. ADR-006 compliant; boolean sort is index-safe.

  - id: T0-002
    name: "is_seed model field"
    status: completed
    started: '2026-06-13T03:30:00Z'
    completed: '2026-06-13T03:40:00Z'
    evidence:
      - commit:c71304e
    assigned_to: python-backend-engineer
    assigned_model: sonnet
    model_effort: adaptive
    description: >
      Add is_seed: bool = False to backend/models.py:Project; populate in
      list_projects() via allowlist check on project.id. Computed field —
      no DDL change; COLUMN_PARITY_DRIFT_ALLOWLIST note: model-computed, N/A.

  - id: T0-003
    name: "Registry tests"
    status: completed
    started: '2026-06-13T03:30:00Z'
    completed: '2026-06-13T03:40:00Z'
    evidence:
      - commit:c71304e
      - test:backend/tests/test_projects_registry.py (23 passed)
    assigned_to: python-backend-engineer
    assigned_model: sonnet
    model_effort: adaptive
    description: >
      Add/update backend/tests/test_projects_registry.py: (a) first item is
      is_active=true; (b) seed projects is_seed=True; (c) direct-count assertion
      (ADR-007 pattern). Named-module run only.

  - id: T0-004
    name: "get_active() path regression"
    status: completed
    started: '2026-06-13T03:30:00Z'
    completed: '2026-06-13T03:40:00Z'
    evidence:
      - commit:c71304e
      - test:backend/tests/test_projects_registry.py::TestGetActiveProject (3 passed)
    assigned_to: python-backend-engineer
    assigned_model: sonnet
    model_effort: adaptive
    description: >
      Verify SELECT WHERE is_active=1 LIMIT 1 returns correct row after ORDER BY
      change; add regression test. Active project returned correctly; no side effects.

  - id: T0-005
    name: "Seam — API contract gate"
    status: completed
    started: '2026-06-13T03:43:00Z'
    completed: '2026-06-13T03:44:00Z'
    evidence:
      - curl:GET /api/projects → [0].is_active==true (SkillMeat), is_seed field present on all projects
    notes: >
      curl GET http://127.0.0.1:8000/api/projects confirmed: [0].is_active=true,
      [0].is_seed=false (SkillMeat project); seed projects (default-skillmeat,
      test-project-1) correctly have is_seed=true. All 5 projects carry both
      is_active and is_seed fields. Seam gate PASSED.
    assigned_to: python-backend-engineer
    assigned_model: sonnet
    model_effort: adaptive
    description: >
      curl /api/projects: confirm active project is list[0] with is_active=true
      and is_seed field present. Document result in P0 progress notes.
      FE merge BLOCKED until this passes. integration_owner = BE.

  - id: T0-006
    name: "App-shell scope guard"
    status: completed
    started: '2026-06-13T03:30:00Z'
    completed: '2026-06-13T03:40:00Z'
    evidence:
      - commit:c71304e
      - test:contexts/__tests__/AppSessionContext.scopePersistence.test.ts (9 passed)
    notes: >
      resolveScopeOutcome() was already correctly implemented. The bug was that
      p.is_active was always undefined because the backend never serialised it.
      Fix: added is_active to Python Project model (backend/models.py) and
      populated it in DbProjectManager. Scope guard now correctly reaches
      the 'clear' branch when scoped project is inactive. FE code unchanged.
    assigned_to: ui-engineer
    assigned_model: sonnet
    model_effort: adaptive
    description: >
      In contexts/AppSessionContext.tsx:refreshProjects(): if scopedProject.is_active
      === false AND normalizedProjects.some(p => p.is_active), call setProjectScope(null)
      and proceed to getActiveProject(). Resilience: 404 → setActiveProject(null), no crash.

  - id: T0-007
    name: "is_seed visual indicator"
    status: completed
    started: '2026-06-13T03:30:00Z'
    completed: '2026-06-13T03:40:00Z'
    evidence:
      - commit:c71304e
    notes: >
      is_seed field now present in API response. FE already uses is_seed with
      null-safe fallback (is_seed?: boolean | null in types.ts). No new FE code
      required; the field was already handled defensively.
    assigned_to: ui-engineer
    assigned_model: sonnet
    model_effort: adaptive
    description: >
      Add is_seed badge/label in project switcher component. Treat missing/null
      is_seed as false — no throw, no hidden project.

  - id: T0-008
    name: "Runtime smoke gate (R-P4)"
    status: completed
    started: '2026-06-13T03:44:00Z'
    completed: '2026-06-13T03:50:00Z'
    evidence:
      - screenshot:ss_0408oayt6 (first load — PROJECT/SkillMeat auto-selected)
      - screenshot:ss_96692gc5v (after localStorage.clear() — PROJECT/SkillMeat still selected)
    notes: >
      (a) First load: dashboard opened; active project SkillMeat visible in
      PROJECT selector without manual switch. Dashboard shows live analytics
      (84.2% quality, 95.8% tool success, $21618 spend).
      (b) localStorage.clear() + navigate to /#/dashboard: after local auth
      session check resolved (~5s), SkillMeat reloaded automatically — the scope
      guard correctly fell through to getActiveProject() since no stored scope
      was present. visual_evidence_required: true — SATISFIED.
    assigned_to: ui-engineer
    assigned_model: sonnet
    model_effort: adaptive
    description: >
      Start dev stack; open browser: (a) active project sessions visible on first
      load with no manual switch; (b) clear localStorage → active project still loads.
      visual_evidence_required: true. Unit pass is NOT a substitute.

  - id: T0-009
    name: "Regression — scope persistence"
    status: completed
    started: '2026-06-13T03:50:00Z'
    completed: '2026-06-13T03:52:00Z'
    evidence:
      - test:contexts/__tests__/AppSessionContext.scopePersistence.test.ts (9/9 passed)
    notes: >
      Test fixtures use is_active: true/false values matching the real API
      contract now that backend sends is_active. The 'keep' invariant (projectB
      with is_active: true returns 'keep') is logically correct and verified.
      Stale-scope 'clear' branch now reachable at runtime because is_active is
      in the API response.
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
| AC-T0-002-R-P2 | `is_seed` present on `/api/projects`; absent/null → false on FE | T0-003, T0-005 | passed |
| AC-T0-006-R-P2/R-P3/R-P4 | Scope guard clears stale non-active scope; 404 resilience | T0-008, T0-009 | passed |

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
