---
type: progress
schema_version: 2
doc_type: progress
prd: "test-visualizer"
feature_slug: "test-visualizer"
prd_ref: /docs/project_plans/PRDs/features/test-visualizer-v1.md
plan_ref: /docs/project_plans/implementation_plans/features/test-visualizer-v1/phase-7-mapping-integrity.md
phase: 7
title: "Domain Mapping & Integrity Signals"
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
  - id: "TASK-7.1"
    description: "Define MappingProvider protocol (@runtime_checkable). Implement MappingResolver orchestrator with provider registration, conflict resolution (_merge_candidates()), confidence-based is_primary logic, and upsert to test_feature_mappings."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["phase-1-complete"]
    estimated_effort: "2pt"
    priority: "high"

  - id: "TASK-7.2"
    description: "Implement RepoHeuristicsProvider: path-based and naming-convention heuristic mapping. Fuzzy feature name matching against DB features (exact=0.9, fuzzy>80%=0.7, prefix=0.5). Domain creation/lookup."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["TASK-7.1"]
    estimated_effort: "2pt"
    priority: "high"

  - id: "TASK-7.3"
    description: "Implement TestMetadataProvider: extract @pytest.mark.feature(...) and @pytest.mark.domain(...) markers from test source files. Support tags_json fallback when CCDASH_PROJECT_ROOT not set."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["TASK-7.1"]
    estimated_effort: "2pt"
    priority: "high"

  - id: "TASK-7.4"
    description: "Implement SemanticLLMProvider that accepts pre-loaded mapping dict. Add POST /api/tests/mappings/import endpoint. Gate with CCDASH_SEMANTIC_MAPPING_ENABLED flag. Return 400 on malformed JSON."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["TASK-7.1"]
    estimated_effort: "2pt"
    priority: "medium"

  - id: "TASK-7.5"
    description: "Fill in Phase 2's _trigger_mapping_resolution() stub with actual MappingResolver.resolve_for_run() call. Wrap in try/except. Log resolution summary. Mapping errors must not bubble to ingest response."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["TASK-7.2", "TASK-7.3", "TASK-7.4"]
    estimated_effort: "1pt"
    priority: "high"

  - id: "TASK-7.6"
    description: "Implement IntegrityDetector.check_run() core: Git diff extraction via asyncio subprocess, test file change extraction, _git_available() guard. Graceful degradation when Git unavailable."
    status: "pending"
    assigned_to: ["backend-architect"]
    dependencies: ["phase-1-complete"]
    estimated_effort: "1pt"
    priority: "high"

  - id: "TASK-7.7"
    description: "Implement all 5 signal detection functions: assertion_removed, skip_introduced, xfail_added, broad_exception, edited_before_green. Each operates on diff text + prior test result. Store signals with correct severity."
    status: "pending"
    assigned_to: ["backend-architect"]
    dependencies: ["TASK-7.6"]
    estimated_effort: "2pt"
    priority: "high"

  - id: "TASK-7.8"
    description: "Fill in Phase 2's _trigger_integrity_check() stub. Add CCDASH_INTEGRITY_SIGNALS_ENABLED check. Add CCDASH_PROJECT_ROOT config var. Skip when disabled, log when skipped."
    status: "pending"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["TASK-7.7"]
    estimated_effort: "1pt"
    priority: "high"

parallelization:
  batch_1: ["TASK-7.1", "TASK-7.6"]
  batch_2: ["TASK-7.2", "TASK-7.3", "TASK-7.4", "TASK-7.7"]
  batch_3: ["TASK-7.5", "TASK-7.8"]
  critical_path: ["TASK-7.1", "TASK-7.2", "TASK-7.5"]
  estimated_total_time: "10pt / ~1 week"

blockers:
  - "Requires Phase 1 complete (test_feature_mappings and test_integrity_signals tables)"
  - "Requires Phase 2 complete (ingestion pipeline and background task hook stubs)"

success_criteria:
  - "MappingProvider protocol is @runtime_checkable"
  - "isinstance(provider, MappingProvider) passes for all 3 provider implementations"
  - "Conflict resolution: test mapped by two providers produces two DB rows, only one with is_primary=True"
  - "RepoHeuristicsProvider maps test in tests/auth/test_login.py to domain 'auth'"
  - "TestMetadataProvider extracts @pytest.mark.feature('my-feature') correctly"
  - "SemanticLLMProvider import endpoint returns 400 on malformed JSON"
  - "Integrity detector returns [] when git not installed (no exception)"
  - "assertion_removed signal detected on diff with removed assert line"
  - "skip_introduced signal detected on diff with added @pytest.mark.skip"
  - "Background tasks run without blocking ingest response"
  - "Unit tests: > 80% line coverage for mapping_resolver.py and integrity_detector.py"

files_modified:
  - "backend/services/mapping_resolver.py"
  - "backend/services/integrity_detector.py"
  - "backend/config.py"
  - "backend/routers/test_visualizer.py"
  - "backend/services/test_ingest.py"
  - "backend/tests/test_mapping_resolver.py"
  - "backend/tests/test_integrity_detector.py"
---

# test-visualizer - Phase 7: Domain Mapping & Integrity Signals

**YAML frontmatter is the source of truth for tasks, status, and assignments.** Do not duplicate in markdown.

Use CLI to update progress:

```bash
python .claude/skills/artifact-tracking/scripts/update-status.py -f .claude/progress/test-visualizer/phase-7-progress.md -t TASK-7.X -s completed
```

---

## Objective

Implement the intelligence layer: pluggable Domain Mapping Provider system (RepoHeuristics, TestMetadata, SemanticLLM providers) and the Integrity Signal Detection pipeline (5 signal types via Git diff analysis). Both run as background tasks triggered after ingestion, filling in the stubs created in Phase 2. Both fail gracefully when dependencies (Git, external LLM) are unavailable.

---

## Orchestration Quick Reference

### Batch Execution Commands

```bash
# Batch 1 (parallel foundations)
Task("python-backend-engineer", "Execute TASK-7.1: Define MappingProvider protocol and MappingResolver orchestrator with conflict resolution logic")
Task("backend-architect", "Execute TASK-7.6: Implement IntegrityDetector.check_run() core with Git diff extraction and graceful degradation")

# Batch 2 (parallel after Batch 1)
Task("python-backend-engineer", "Execute TASK-7.2: Implement RepoHeuristicsProvider with path-based and fuzzy feature name matching")
Task("python-backend-engineer", "Execute TASK-7.3: Implement TestMetadataProvider with pytest marker extraction")
Task("python-backend-engineer", "Execute TASK-7.4: Implement SemanticLLMProvider and POST /api/tests/mappings/import endpoint")
Task("backend-architect", "Execute TASK-7.7: Implement all 5 signal detection functions for IntegrityDetector")

# Batch 3 (parallel after Batch 2)
Task("python-backend-engineer", "Execute TASK-7.5: Wire _trigger_mapping_resolution() background task with MappingResolver.resolve_for_run()")
Task("python-backend-engineer", "Execute TASK-7.8: Wire _trigger_integrity_check() background task and add config vars")
```

---

## Implementation Notes

_To be filled during implementation._

---

## Completion Notes

_To be filled when phase completes._
