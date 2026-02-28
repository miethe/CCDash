---
type: progress
schema_version: 2
doc_type: progress
prd: "test-visualizer"
feature_slug: "test-visualizer"
prd_ref: /docs/project_plans/PRDs/features/test-visualizer-v1.md
plan_ref: /docs/project_plans/implementation_plans/features/test-visualizer-v1/phase-2-ingestion.md
phase: 2
title: "Ingestion Pipeline"
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
  - id: "TASK-2.1"
    description: "Implement parse_junit_xml() in backend/parsers/test_results.py. Handle testsuites, testsuite, testcase. Extract status, duration, error messages. Generate stable test_id via SHA-256 hash."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["phase-1-complete"]
    estimated_effort: "3pt"
    priority: "high"

  - id: "TASK-2.2"
    description: "Extend parser to handle nested testsuites (flatten hierarchy), parameterized test name extraction (test_func[param1] -> base name + params), classname used for path inference when file attr absent."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["TASK-2.1"]
    estimated_effort: "2pt"
    priority: "high"

  - id: "TASK-2.3"
    description: "Implement sidecar detection: check for {xml_basename}.meta.json alongside XML. Merge run metadata (git_sha, branch, session_id, env_fingerprint). Allow per-test tag/owner overrides."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["TASK-2.1"]
    estimated_effort: "2pt"
    priority: "medium"

  - id: "TASK-2.4"
    description: "Implement _extract_error_fingerprint(). Strip line numbers, memory addresses, timestamps from error messages. Produce stable short hash for recurring failure grouping."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["TASK-2.1"]
    estimated_effort: "1pt"
    priority: "medium"

  - id: "TASK-2.5"
    description: "Create backend/routers/test_visualizer.py with router declaration and POST /api/tests/ingest endpoint. Wire to ingest service. Register router in backend/main.py. Gate with CCDASH_TEST_VISUALIZER_ENABLED flag."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["TASK-2.1", "phase-1-complete"]
    estimated_effort: "2pt"
    priority: "high"

  - id: "TASK-2.6"
    description: "Implement backend/services/test_ingest.py with ingest_run(payload: IngestRunRequest, db) -> IngestRunResponse. Orchestrates: validate payload, upsert test_run, upsert test_definitions, upsert test_results. Returns counts."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["TASK-2.5"]
    estimated_effort: "3pt"
    priority: "high"

  - id: "TASK-2.7"
    description: "Add _trigger_mapping_resolution() and _trigger_integrity_check() as async stubs called after successful ingest via asyncio.create_task(). Gate each by its feature flag. Log task creation."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["TASK-2.6"]
    estimated_effort: "1pt"
    priority: "medium"

  - id: "TASK-2.8"
    description: "Add sync_test_results() to SyncEngine. Configure TEST_RESULTS_DIR in config.py. Extend FileWatcher to watch for *.xml files in that directory and call sync_test_results(). Guard with TEST_RESULTS_DIR != ''."
    status: "pending"
    assigned_to: ["backend-architect"]
    dependencies: ["TASK-2.6"]
    estimated_effort: "2pt"
    priority: "low"

parallelization:
  batch_1: ["TASK-2.1"]
  batch_2: ["TASK-2.2", "TASK-2.3", "TASK-2.4", "TASK-2.5"]
  batch_3: ["TASK-2.6"]
  batch_4: ["TASK-2.7", "TASK-2.8"]
  critical_path: ["TASK-2.1", "TASK-2.5", "TASK-2.6", "TASK-2.7"]
  estimated_total_time: "16pt / ~1 week"

blockers:
  - "Requires Phase 1 complete (DB schema and repositories)"

success_criteria:
  - "parse_junit_xml() handles empty test suites without error"
  - "parse_junit_xml() handles malformed XML gracefully"
  - "POST /api/tests/ingest returns 200 on valid IngestRunRequest"
  - "POST /api/tests/ingest is idempotent: posting same run_id twice returns status: 'skipped'"
  - "POST /api/tests/ingest returns 503 when CCDASH_TEST_VISUALIZER_ENABLED=false"
  - "Unit tests cover: standard XML, parameterized tests, nested suites, missing sidecar, existing sidecar"

files_modified:
  - "backend/parsers/test_results.py"
  - "backend/services/test_ingest.py"
  - "backend/routers/test_visualizer.py"
  - "backend/db/sync_engine.py"
  - "backend/db/file_watcher.py"
  - "backend/config.py"
  - "backend/main.py"
  - "backend/models.py"
  - "backend/tests/test_test_results_parser.py"
  - "backend/tests/test_test_ingest_service.py"
---

# test-visualizer - Phase 2: Ingestion Pipeline

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

Use CLI to update progress:

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py -f .claude/progress/test-visualizer/phase-2-progress.md -t TASK-2.X -s completed
```

---

## Objective

Build the data ingest pipeline: JUnit XML parser, JSON enrichment sidecar, idempotent ingest REST endpoint (POST /api/tests/ingest), background task stubs for mapping and integrity, and optional file-watcher auto-ingestion. Ingestion is idempotent — re-posting the same run_id yields no duplicate rows.

---

## Orchestration Quick Reference

### Batch Execution Commands

```bash
# Batch 1 (foundation parser)
Task("python-backend-engineer", "Execute TASK-2.1: Implement parse_junit_xml() core in backend/parsers/test_results.py")

# Batch 2 (parallel after TASK-2.1)
Task("python-backend-engineer", "Execute TASK-2.2: Extend parser for parameterized and nested suite handling")
Task("python-backend-engineer", "Execute TASK-2.3: Implement JSON enrichment sidecar detection and merge")
Task("python-backend-engineer", "Execute TASK-2.4: Implement _extract_error_fingerprint() for recurring failure grouping")
Task("python-backend-engineer", "Execute TASK-2.5: Create stub router file backend/routers/test_visualizer.py with POST /api/tests/ingest")

# Batch 3 (after TASK-2.5)
Task("python-backend-engineer", "Execute TASK-2.6: Implement ingest service backend/services/test_ingest.py")

# Batch 4 (parallel after TASK-2.6)
Task("python-backend-engineer", "Execute TASK-2.7: Add async background task stubs _trigger_mapping_resolution and _trigger_integrity_check")
Task("backend-architect", "Execute TASK-2.8: Add sync_test_results() to SyncEngine and extend FileWatcher for XML watch")
```

---

## Implementation Notes

_To be filled during implementation._

---

## Completion Notes

_To be filled when phase completes._
