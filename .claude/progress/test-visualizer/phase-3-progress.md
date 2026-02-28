---
type: progress
schema_version: 2
doc_type: progress
prd: "test-visualizer"
feature_slug: "test-visualizer"
prd_ref: /docs/project_plans/PRDs/features/test-visualizer-v1.md
plan_ref: /docs/project_plans/implementation_plans/features/test-visualizer-v1/phase-3-api.md
phase: 3
title: "API Layer"
status: "planning"
started: "2026-02-28"
completed: null
commit_refs: []
pr_refs: []

overall_progress: 0
completion_estimate: "on-track"

total_tasks: 8
completed_tasks: 0
in_progress_tasks: 0
blocked_tasks: 0
at_risk_tasks: 0

owners: ["python-backend-engineer"]
contributors: ["backend-architect"]

tasks:
  - id: "TASK-3.1"
    description: "Create backend/services/test_health.py with all method signatures and docstrings. Wire to repositories via factory. Return stub data initially."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["phase-1-complete"]
    estimated_effort: "1pt"
    priority: "high"

  - id: "TASK-3.2"
    description: "Implement get_domain_rollups() in TestHealthService. Query all domains, join with primary mappings, join with latest test_results, compute pass_rate and integrity_score. Return nested DomainHealthRollupDTO."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["TASK-3.1"]
    estimated_effort: "3pt"
    priority: "high"

  - id: "TASK-3.3"
    description: "Implement get_feature_health() and list_feature_health(). Filter by domain_id. Compute open_signals count from integrity table."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["TASK-3.2"]
    estimated_effort: "2pt"
    priority: "high"

  - id: "TASK-3.4"
    description: "Implement get_feature_timeline(). Group test results by day. Compute first_green, last_red, last_known_good from run timestamps. Include integrity signals on timeline."
    status: "pending"
    assigned_to: ["backend-architect"]
    dependencies: ["TASK-3.3"]
    estimated_effort: "2pt"
    priority: "high"

  - id: "TASK-3.5"
    description: "Implement get_correlation(). Join run -> sessions, run -> commit_correlations, run -> features via mappings, run -> integrity_signals. Build links dict with deep-link URLs."
    status: "pending"
    assigned_to: ["backend-architect"]
    dependencies: ["TASK-3.4"]
    estimated_effort: "2pt"
    priority: "high"

  - id: "TASK-3.6"
    description: "Implement all GET endpoints in test_visualizer.py router: GET /health/domains, GET /health/features, GET /runs/{run_id}, GET /runs, GET /{test_id}/history, GET /features/{feature_id}/timeline, GET /integrity/alerts, GET /correlate."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["TASK-3.5"]
    estimated_effort: "2pt"
    priority: "high"

  - id: "TASK-3.7"
    description: "Add OpenTelemetry spans to all endpoint handlers and TestHealthService methods. Include: span names, project_id, entity IDs, result counts."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["TASK-3.6"]
    estimated_effort: "1pt"
    priority: "medium"

  - id: "TASK-3.8"
    description: "Implement cursor encoding/decoding helpers. Apply to all list endpoints: GET /runs, GET /{test_id}/history, GET /health/features, GET /integrity/alerts. Return next_cursor: null when no more pages."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["TASK-3.6"]
    estimated_effort: "1pt"
    priority: "high"

parallelization:
  batch_1: ["TASK-3.1"]
  batch_2: ["TASK-3.2"]
  batch_3: ["TASK-3.3"]
  batch_4: ["TASK-3.4"]
  batch_5: ["TASK-3.5"]
  batch_6: ["TASK-3.6"]
  batch_7: ["TASK-3.7", "TASK-3.8"]
  critical_path: ["TASK-3.1", "TASK-3.2", "TASK-3.3", "TASK-3.4", "TASK-3.5", "TASK-3.6"]
  estimated_total_time: "14pt / ~1 week"

blockers:
  - "Requires Phase 1 complete (repositories and DTOs)"
  - "Requires Phase 2 complete (ingest endpoint and stub router)"

success_criteria:
  - "All 9 endpoints exist and return non-500 on valid requests"
  - "All endpoints return 503 when CCDASH_TEST_VISUALIZER_ENABLED=false"
  - "Domain health rollup returns nested tree structure"
  - "Feature timeline includes first_green, last_red, last_known_good fields"
  - "Correlation endpoint returns linked entity URLs"
  - "Cursor pagination works: second request with next_cursor returns different items"
  - "OpenTelemetry spans emitted"
  - "No raw SQL in router handlers"
  - "Performance: GET /health/domains with 100 domains < 500ms on SQLite"

files_modified:
  - "backend/routers/test_visualizer.py"
  - "backend/services/test_health.py"
  - "backend/models.py"
  - "backend/tests/test_test_visualizer_router.py"
  - "backend/tests/test_test_health_service.py"
---

# test-visualizer - Phase 3: API Layer

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

Use CLI to update progress:

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py -f .claude/progress/test-visualizer/phase-3-progress.md -t TASK-3.X -s completed
```

---

## Objective

Complete the REST API layer for the Test Visualizer. Creates TestHealthService for rollup computation and implements all 7+ GET endpoints in test_visualizer.py. Adds cursor-based pagination, ErrorResponse envelopes, OpenTelemetry spans, and the correlation endpoint that joins test data with session/commit/feature entities.

---

## Orchestration Quick Reference

### Batch Execution Commands

```bash
# Batch 1
Task("python-backend-engineer", "Execute TASK-3.1: Create TestHealthService skeleton in backend/services/test_health.py")

# Batch 2 (sequential — each depends on previous)
Task("python-backend-engineer", "Execute TASK-3.2: Implement get_domain_rollups() with pass_rate and integrity_score computation")
Task("python-backend-engineer", "Execute TASK-3.3: Implement get_feature_health() and list_feature_health() with domain filter")
Task("backend-architect", "Execute TASK-3.4: Implement get_feature_timeline() with daily grouping and first_green/last_red computation")
Task("backend-architect", "Execute TASK-3.5: Implement get_correlation() with cross-entity joins and deep-link URLs")

# Batch 3 (after TASK-3.5)
Task("python-backend-engineer", "Execute TASK-3.6: Implement all 8 GET endpoints in test_visualizer.py router")

# Batch 4 (parallel after TASK-3.6)
Task("python-backend-engineer", "Execute TASK-3.7: Add OpenTelemetry spans to all endpoint handlers")
Task("python-backend-engineer", "Execute TASK-3.8: Implement cursor pagination helpers and apply to all list endpoints")
```

---

## Implementation Notes

_To be filled during implementation._

---

## Completion Notes

_To be filled when phase completes._
