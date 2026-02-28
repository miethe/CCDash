---
type: progress
schema_version: 2
doc_type: progress
prd: "test-visualizer"
feature_slug: "test-visualizer"
prd_ref: /docs/project_plans/PRDs/features/test-visualizer-v1.md
plan_ref: /docs/project_plans/implementation_plans/features/test-visualizer-v1/phase-8-testing-polish.md
phase: 8
title: "Testing & Polish"
status: "planning"
started: "2026-02-28"
completed: null
commit_refs: []
pr_refs: []

overall_progress: 0
completion_estimate: "on-track"

total_tasks: 5
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0

owners: ["python-backend-engineer"]
contributors: ["frontend-developer"]

tasks:
  - id: "TASK-8.1"
    description: "Fill in stub test files from earlier phases. Achieve > 80% coverage targets for all 5 service modules using _FakeRepo pattern. Targets: parsers/test_results.py >90%, services/test_health.py >80%, services/test_ingest.py >80%, services/mapping_resolver.py >85%, services/integrity_detector.py >80%."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["phases-1-7-complete"]
    estimated_effort: "2pt"
    priority: "high"

  - id: "TASK-8.2"
    description: "Implement full integration test suite in test_test_visualizer_router.py using in-memory SQLite. Cover all 9 endpoints plus error cases: idempotency, feature flag disable (503), 404 cases, invalid cursor (400)."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["TASK-8.1"]
    estimated_effort: "2pt"
    priority: "high"

  - id: "TASK-8.3"
    description: "Implement performance test file. Seed realistic data volumes. Verify: ingest 100 tests < 500ms, bulk ingest 100x100 < 5s, domain health 100 domains < 500ms, feature timeline 12 months < 2s. Document any SQLite index additions needed."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["TASK-8.2"]
    estimated_effort: "1pt"
    priority: "medium"

  - id: "TASK-8.4"
    description: "Audit and fix all edge cases: malformed XML (400), bulk ingest > 1000 tests (chunked upserts), git not found (graceful), 503 UI graceful degradation, empty domain empty state, TestTimeline with 1 data point, test name truncation > 50 chars."
    status: "pending"
    assigned_to: ["python-backend-engineer", "frontend-developer"]
    dependencies: ["phases-1-7-complete"]
    estimated_effort: "2pt"
    priority: "high"

  - id: "TASK-8.5"
    description: "Run axe-core against all new components. Fix violations. Verify keyboard navigation for DomainTreeView and TestResultTable. Add missing aria attributes (role=tree, aria-expanded, aria-valuenow on HealthGauge, role=table)."
    status: "pending"
    assigned_to: ["frontend-developer"]
    dependencies: ["phases-5-6-complete"]
    estimated_effort: "1pt"
    priority: "high"

parallelization:
  batch_1: ["TASK-8.1", "TASK-8.4", "TASK-8.5"]
  batch_2: ["TASK-8.2"]
  batch_3: ["TASK-8.3"]
  critical_path: ["TASK-8.1", "TASK-8.2", "TASK-8.3"]
  estimated_total_time: "8pt / ~1 week"

blockers:
  - "Requires Phases 1-7 complete"

success_criteria:
  - "backend/.venv/bin/python -m pytest backend/tests/ -v — all tests pass"
  - "Coverage > 80% for new services (run with --cov=backend/services)"
  - "TypeScript compilation passes: npx tsc --noEmit"
  - "No new ESLint errors"
  - "Feature flag CCDASH_TEST_VISUALIZER_ENABLED=false disables subsystem completely"
  - "Single-run ingest (100 tests) < 500ms"
  - "Domain health query (100 domains) < 500ms"
  - "Feature timeline (12 months) < 2s"
  - "TestingPage initial render < 1s with mock data"
  - "Zero axe-core violations on Testing Page"
  - "DomainTreeView keyboard navigable (arrows + Enter)"
  - "All status badges include text label (not color-only)"
  - "HealthGauge has aria-valuenow/min/max"

files_modified:
  - "backend/tests/test_test_results_parser.py"
  - "backend/tests/test_test_ingest_service.py"
  - "backend/tests/test_test_health_service.py"
  - "backend/tests/test_test_visualizer_router.py"
  - "backend/tests/test_mapping_resolver.py"
  - "backend/tests/test_integrity_detector.py"
  - "backend/tests/test_test_repositories.py"
  - "backend/tests/test_test_visualizer_performance.py"
---

# test-visualizer - Phase 8: Testing & Polish

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

Use CLI to update progress:

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py -f .claude/progress/test-visualizer/phase-8-progress.md -t TASK-8.X -s completed
```

---

## Objective

Harden the Test Visualizer for production. Completes stub test files from earlier phases, achieves >80% backend coverage, implements integration tests for all 9 endpoints, runs performance benchmarks, handles all edge cases, verifies accessibility compliance (WCAG 2.1 AA), and validates feature flag rollback behavior.

---

## Orchestration Quick Reference

### Batch Execution Commands

```bash
# Batch 1 (parallel — backend tests, edge cases, a11y can run concurrently)
Task("python-backend-engineer", "Execute TASK-8.1: Complete all backend unit tests achieving >80% coverage across 5 service modules")
Task("python-backend-engineer", "Execute TASK-8.4: Audit and fix all backend and frontend edge cases from the edge case table")
Task("frontend-developer", "Execute TASK-8.5: Run axe-core accessibility checks, fix violations, verify keyboard nav for tree and table")

# Batch 2 (after TASK-8.1)
Task("python-backend-engineer", "Execute TASK-8.2: Implement full integration test suite for all 9 endpoints with in-memory SQLite")

# Batch 3 (after TASK-8.2)
Task("python-backend-engineer", "Execute TASK-8.3: Implement performance benchmarks, seed realistic data, verify all 4 timing targets met")
```

---

## Implementation Notes

_To be filled during implementation._

---

## Completion Notes

_To be filled when phase completes._
