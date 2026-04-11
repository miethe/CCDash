---
schema_version: "1.0"
doc_type: phase_plan
title: "Phase 1: Agent Query Foundation"
description: "Implement transport-neutral composite query services and Pydantic DTOs for project status, feature forensics, workflow diagnostics, and AAR reporting."
status: in-progress
created: "2026-04-02"
updated: "2026-04-11"
phase: 1
phase_title: "Agent Query Foundation"
feature_slug: "ccdash-cli-mcp-enablement"
prd_ref: "docs/project_plans/PRDs/features/ccdash-cli-mcp-enablement-v1.md"
plan_ref: "docs/project_plans/implementation_plans/features/ccdash-cli-mcp-enablement-v1.md"
entry_criteria:
  - Architecture review approves query service contracts
  - Existing CorePorts, repositories, and domain services are stable
  - Test SQLite DB available for integration tests
exit_criteria:
  - All 4 query services implemented with >90% line coverage
  - All DTOs include status, data_freshness, generated_at, source_refs fields
  - Graceful degradation (status: partial) tested when subsystems unavailable
  - Phase 2 REST endpoints can call these services without modification
priority: critical
effort_estimate: 8-10
effort_estimate_unit: story_points
duration_estimate: 5-7
duration_estimate_unit: days
---

# Phase 1: Agent Query Foundation

## Phase Overview

**Goal**: Create a transport-neutral query layer (`backend/application/services/agent_queries/`) with four composite query services and supporting Pydantic DTOs. These services aggregate data from multiple repositories and existing domain services to answer high-level agent questions without requiring transport logic (HTTP, CLI, MCP).

**Critical for**: Phases 2, 3, and 4 all depend on Phase 1 services being stable and complete.

**Key Invariant**: No business logic duplication. All three delivery surfaces (REST, CLI, MCP) call these services unchanged.

**Reuse Rule**: Reuse existing shared models and workflow helpers where shapes already exist; only add new DTOs for agent-specific aggregates that cannot be expressed by current models.

---

## Task Breakdown

### P1-T1: Create Package Structure and Shared Models

**Effort**: 1 story point  
**Duration**: 0.5–1 day  
**Assignee**: Backend Engineer  
**Depends on**: Nothing

**Description**:
Create the `backend/application/services/agent_queries/` package and define all shared Pydantic DTOs, nested submodels, and canonical freshness/source-reference helpers in a models module.

**Detailed Tasks**:

1. Create `backend/application/services/agent_queries/__init__.py` (empty or minimal imports)
2. Create `backend/application/services/agent_queries/models.py` with the following Pydantic models:
   - `ProjectStatusDTO`, `FeatureForensicsDTO`, `WorkflowDiagnosticsDTO`, `AARReportDTO`
   - Nested submodels: `SessionSummary`, `CostSummary`, `WorkflowSummary`, `TimelineData`, `KeyMetrics`, `TurningPoint`, `WorkflowObservation`, `Bottleneck`, `SessionRef`, `DocumentRef`, `TaskRef`
   - Common envelope fields: `status: Literal["ok", "partial", "error"]`, `data_freshness: datetime`, `generated_at: datetime`, `source_refs: list[str]`
3. Create `backend/application/services/agent_queries/_filters.py` with helper functions:
   - `resolve_project(context, ports, requested_project_id)` → ProjectScope
   - `resolve_time_window(since, until, default_days)` → tuple[datetime, datetime]
   - `normalize_entity_ids(session_ids, feature_ids, etc.)` → normalized list
   - `derive_data_freshness(...)` and `collect_source_refs(...)` as canonical helpers
4. Export shared DTOs, nested submodels, and helpers from `backend/application/services/agent_queries/__init__.py`

**Files to Create**:
- `backend/application/services/agent_queries/__init__.py`
- `backend/application/services/agent_queries/models.py` (~300 lines)
- `backend/application/services/agent_queries/_filters.py` (~100 lines)

**Acceptance Criteria**:
- [ ] All 4 DTO classes defined with complete fields
- [ ] All DTOs are Pydantic BaseModel subclasses with proper type hints
- [ ] DTOs serialize/deserialize correctly via `.model_dump()` and `.model_validate()`
- [ ] Shared filter helpers have clear docstrings and type hints
- [ ] Package imports work: `from backend.application.services.agent_queries import ProjectStatusDTO, ...`

---

### P1-T2: Implement ProjectStatusQueryService

**Effort**: 3 story points  
**Duration**: 2–3 days  
**Assignee**: Backend Engineer  
**Depends on**: P1-T1

**Description**:
Implement the service that answers "what is the current state of this project?" by aggregating feature counts, recent session activity, cost trends, workflow summaries, sync freshness, and notable anomalies.

**Detailed Tasks**:

1. Create `backend/application/services/agent_queries/project_status.py`
2. Implement `ProjectStatusQueryService` class with signature:
   ```python
   class ProjectStatusQueryService:
       async def get_status(
           self,
           context: RequestContext,
           ports: CorePorts,
           project_id_override: str | None = None,
       ) -> ProjectStatusDTO:
           """Get high-level project status and trends."""
   ```
3. Implementation should:
   - Call `ports.storage.sessions().list_paginated(...)` or `SessionIntelligenceReadService.list_sessions(...)` for recent activity
   - Call `ports.storage.features().list_all(project_id)` and/or `count(project_id)` to count by status
   - Call `AnalyticsOverviewService.get_overview(context, ports)` for cost/token data
   - Call `list_workflow_registry(...)` from `backend.services.workflow_registry` to identify top workflows
   - Check cache freshness via `ports.storage.sync_state().list_all(project_id)`
   - Aggregate into a single `ProjectStatusDTO`
   - If any subsystem errors, return `status: partial` with available data; return `status: error` only when the project context cannot be resolved or no usable data is available

4. Populate `ProjectStatusDTO` fields:
   - `project_id`, `project_name`
   - `status: ok|partial|error`
   - `feature_counts: dict[str, int]` (by status: todo, in_progress, blocked, done)
   - `recent_sessions: list[SessionSummary]` (last 7 days, top 10)
   - `cost_last_7d: CostSummary` (total, by model, by workflow)
   - `top_workflows: list[WorkflowSummary]` (by session count)
   - `sync_freshness: datetime` (when cache was last updated)
   - `blocked_features: list[str]` (feature IDs flagged as blocked)
   - `data_freshness: datetime` (most recent record in DB)
   - `generated_at: datetime` (when this DTO was assembled)
   - `source_refs: list[str]` (entity IDs included)

**Files to Create**:
- `backend/application/services/agent_queries/project_status.py` (~200 lines)

**Unit Test File**:
- `backend/tests/test_agent_queries_project_status.py` (~300 lines with mocks)

**Acceptance Criteria**:
- [ ] Service returns `ProjectStatusDTO` with all required fields
- [ ] Calls to repositories are correct (no N+1 queries)
- [ ] Returns `status: ok` on full success, `status: partial` when a subsystem is unavailable, and `status: error` only when no usable project data exists
- [ ] `data_freshness` comes from the canonical freshness helper and `source_refs` only include source entity IDs actually used in the response
- [ ] DTO serializes to JSON and can be deserialized back
- [ ] Unit tests pass with mocked CorePorts and repositories
- [ ] Coverage >90% for the service method

---

### P1-T3: Implement FeatureForensicsQueryService

**Effort**: 3 story points  
**Duration**: 2–3 days  
**Assignee**: Backend Engineer  
**Depends on**: P1-T1

**Description**:
Implement the service that answers "what happened during development of this feature?" by aggregating feature metadata, linked sessions and documents, iteration count, cost, workflow mix, and failure patterns.

**Detailed Tasks**:

1. Create `backend/application/services/agent_queries/feature_forensics.py`
2. Implement `FeatureForensicsQueryService` with signature:
   ```python
   class FeatureForensicsQueryService:
       async def get_forensics(
           self,
           context: RequestContext,
           ports: CorePorts,
           feature_id: str,
       ) -> FeatureForensicsDTO:
           """Get detailed feature development history and forensics."""
   ```
3. Implementation should:
   - Fetch feature via `ports.storage.features().get_by_id(feature_id)` or the existing feature lookup helper
   - Fetch linked sessions via `SessionIntelligenceReadService.list_sessions(feature_id=feature_id)` and fall back to repository pagination plus entity-link correlation only if the service output is insufficient
   - Fetch linked docs via `ports.storage.documents().list_paginated(..., filters={"feature": feature_id, "include_progress": True})`
   - Fetch linked tasks via `ports.storage.tasks().list_by_feature(feature_id)`
   - Use `ports.storage.entity_links().get_links_for("feature", feature_id, "related")` as needed for cross-entity provenance
   - Compute iteration count (number of session generations for this feature)
   - Compute total cost/tokens (sum across all linked sessions)
   - Analyze workflow mix (tool usage patterns across sessions)
   - Detect rework signals (repeated attempts, backtracking)
   - Extract failure patterns from session logs
   - Assemble into `FeatureForensicsDTO`
   - Return `status: partial` when supporting subsystems are unavailable; return `status: error` when the feature cannot be resolved or no usable feature context exists
   - Keep the narrative output deterministic and directly derivable from the assembled inputs so tests can assert on it

4. Populate `FeatureForensicsDTO` fields:
   - `feature_id`, `feature_slug`, `status` (done, in_progress, etc.)
   - `linked_sessions: list[SessionRef]` (with costs, durations, tools used)
   - `linked_documents: list[DocumentRef]` (PRDs, plans, ADRs)
   - `linked_tasks: list[TaskRef]` (by status)
   - `iteration_count: int` (how many session generations)
   - `total_cost: float`, `total_tokens: int`
   - `workflow_mix: dict[str, float]` (% of tool usage by workflow)
   - `rework_signals: list[str]` (heuristics: repeated rollbacks, long iteration cycles)
   - `failure_patterns: list[str]` (common error patterns)
   - `representative_sessions: list[SessionRef]` (e.g., longest, most complex, failed)
   - `summary_narrative: str` (one-paragraph English summary of feature development)
   - `data_freshness`, `generated_at`, `source_refs` (standard envelope)

**Files to Create**:
- `backend/application/services/agent_queries/feature_forensics.py` (~250 lines)

**Unit Test File**:
- `backend/tests/test_agent_queries_feature_forensics.py` (~300 lines with mocks)

**Acceptance Criteria**:
- [ ] Service returns `FeatureForensicsDTO` with all required fields
- [ ] Iteration count correctly computed from linked sessions
- [ ] Rework signals and failure patterns detected (or empty if none)
- [ ] Summary narrative generated and deterministic from the assembled inputs
- [ ] Returns `status: ok` on full success, `status: partial` for missing subsystem data, and `status: error` only for missing feature context
- [ ] `data_freshness` comes from the canonical freshness helper and `source_refs` only include source entity IDs actually used in the response
- [ ] Unit tests >90% coverage

---

### P1-T4: Implement WorkflowDiagnosticsQueryService

**Effort**: 2 story points  
**Duration**: 1–2 days  
**Assignee**: Backend Engineer  
**Depends on**: P1-T1

**Description**:
Implement the service that answers "which workflows are effective or problematic?" by scoring per-workflow effectiveness, counting sessions, analyzing success/failure mix, and identifying failure patterns.

**Detailed Tasks**:

1. Create `backend/application/services/agent_queries/workflow_intelligence.py`
2. Implement `WorkflowDiagnosticsQueryService` with signature:
   ```python
   class WorkflowDiagnosticsQueryService:
       async def get_diagnostics(
           self,
           context: RequestContext,
           ports: CorePorts,
           feature_id: str | None = None,
       ) -> WorkflowDiagnosticsDTO:
           """Analyze workflow effectiveness across project or single feature."""
   ```
3. Implementation should:
   - Reuse workflow registry and effectiveness helpers from `backend.services.workflow_registry` and `backend.services.workflow_effectiveness`
   - Call `list_workflow_registry(...)` and `detect_failure_patterns(...)` rather than introducing a synthetic registry class
   - For each workflow, compute:
     - Effectiveness score: `(successful_sessions / total_sessions) * (cost_efficiency) * (speed_score)`
     - Session count, success/failure ratio
     - Average cost per session
     - Common failure patterns (from execution logs)
   - Optional feature filter: if `feature_id` provided, analyze workflows only for that feature's sessions
   - Return `WorkflowDiagnosticsDTO` with per-workflow analytics
   - Return `status: partial` if registry data is unavailable and `status: error` only when no workflow context can be assembled

4. Populate `WorkflowDiagnosticsDTO` fields:
   - `project_id`
   - `status: ok|partial|error`
   - `workflows: list[WorkflowDiagnostic]` with:
     - `workflow_id`, `workflow_name`
     - `effectiveness_score: float` (0–1)
     - `session_count: int`, `success_count: int`, `failure_count: int`
     - `cost_efficiency: float` (sessions per dollar)
     - `common_failures: list[str]` (top 3 failure patterns)
     - `representative_sessions: list[SessionRef]` (successful and failed examples)
   - `top_performers: list[WorkflowDiagnostic]` (by effectiveness_score)
   - `problem_workflows: list[WorkflowDiagnostic]` (by failure_rate or effectiveness < 0.5)
   - `data_freshness`, `generated_at`, `source_refs`

**Files to Create**:
- `backend/application/services/agent_queries/workflow_intelligence.py` (~180 lines)

**Unit Test File**:
- `backend/tests/test_agent_queries_workflow_diagnostics.py` (~250 lines with mocks)

**Acceptance Criteria**:
- [ ] Service returns `WorkflowDiagnosticsDTO` with all workflows analyzed
- [ ] Effectiveness score correctly computed
- [ ] Feature filter (if provided) correctly scopes analysis
- [ ] Returns `status: ok` on full success, `status: partial` when registry/effectiveness data is unavailable, and `status: error` only when no workflow context exists
- [ ] `data_freshness` comes from the canonical freshness helper and `source_refs` only include source entity IDs actually used in the response
- [ ] Unit tests >90% coverage

---

### P1-T5: Implement ReportingQueryService (AAR)

**Effort**: 2 story points  
**Duration**: 1–2 days  
**Assignee**: Backend Engineer  
**Depends on**: P1-T1

**Description**:
Implement the service that answers "what was accomplished and learned during this feature development?" by generating an after-action review (AAR) report with scope, timeline, key metrics, turning points, workflow observations, and lessons.

**Detailed Tasks**:

1. Create `backend/application/services/agent_queries/reporting.py`
2. Implement `ReportingQueryService` with signature:
   ```python
   class ReportingQueryService:
       async def generate_aar(
           self,
           context: RequestContext,
           ports: CorePorts,
           feature_id: str,
       ) -> AARReportDTO:
           """Generate an AAR report for a feature."""
   ```
3. Implementation should:
   - Reuse the existing feature/session/document/task correlation helpers instead of re-deriving them
   - Fetch feature via `ports.storage.features().get_by_id(feature_id)` or the existing feature lookup helper
   - Fetch all linked sessions, compute timeline (start → end)
   - Fetch linked docs via `ports.storage.documents().list_paginated(..., filters={"feature": feature_id, "include_progress": True})`
   - Fetch linked tasks via `ports.storage.tasks().list_by_feature(feature_id)`
   - Compute key metrics: total cost, total tokens, iteration count, duration
   - Identify turning points (first success, major pivots, breakthroughs)
   - Analyze workflow sequence (which workflows used, in what order)
   - Extract bottlenecks (where time/cost accumulated most)
   - Identify successful patterns (workflows with high success rate)
   - Generate narrative sections (scope statement, timeline, findings, lessons) deterministically from the assembled inputs
   - Assemble into `AARReportDTO`
   - Return `status: partial` when supporting subsystems are unavailable; return `status: error` when the feature cannot be resolved or no usable feature context exists

4. Populate `AARReportDTO` fields:
   - `feature_id`, `feature_slug`
   - `scope_statement: str` (one-paragraph description of feature scope)
   - `timeline: TimelineData` (start date, end date, duration_days)
   - `key_metrics: KeyMetrics` (total_cost, total_tokens, session_count, iteration_count)
   - `turning_points: list[TurningPoint]` (date, event, impact description)
   - `workflow_observations: list[WorkflowObservation]` (workflow_id, frequency, effectiveness, notes)
   - `bottlenecks: list[Bottleneck]` (description, cost_impact, sessions_affected)
   - `successful_patterns: list[str]` (e.g., "workflow A → workflow B had 90% success rate")
   - `lessons_learned: list[str]` (e.g., "parallelizing workflows A and B reduced duration by 40%")
   - `evidence_links: list[str]` (session IDs, document paths for reference)
   - `data_freshness`, `generated_at`, `source_refs`

**Files to Create**:
- `backend/application/services/agent_queries/reporting.py` (~220 lines)

**Unit Test File**:
- `backend/tests/test_agent_queries_reporting.py` (~280 lines with mocks)

**Acceptance Criteria**:
- [ ] Service returns `AARReportDTO` with all sections populated
- [ ] Narrative sections (scope, lessons) are human-readable (not machine-generated gibberish)
- [ ] Timeline correctly computed from session start/end dates
- [ ] Turning points detected (or empty list if too few sessions)
- [ ] Returns `status: ok` on full success, `status: partial` when some source data is unavailable, and `status: error` only when no feature context exists
- [ ] `data_freshness` comes from the canonical freshness helper and `source_refs` only include source entity IDs actually used in the response
- [ ] Unit tests >90% coverage

---

### P1-T6: Write Unit Tests with Mocked CorePorts

**Effort**: 2 story points  
**Duration**: 2 days  
**Assignee**: Backend Engineer (Test-Focused)  
**Depends on**: P1-T2, P1-T3, P1-T4, P1-T5

**Description**:
Write shared fixtures and cross-service regression tests for all four query services using mocked CorePorts, repositories, and domain services. Target >90% line coverage across the module.

**Detailed Tasks**:

1. Create test fixtures in `backend/tests/conftest.py` (or new file):
   - Mock `CorePorts` factory
   - Mock repositories (SessionRepository, FeatureRepository, etc.)
   - Test data builders (fake sessions, features, documents)

2. Add shared helper tests and regression coverage:
   - `backend/tests/test_agent_queries_shared.py` for fixture helpers, shared envelope assertions, and cross-service regressions
   - Keep the per-service unit test modules owned by P1-T2 through P1-T5

3. Test coverage areas:
   - **Happy path**: Standard case with complete data
   - **Partial degradation**: One subsystem unavailable; service returns `status: partial`
   - **Multiple subsystem failures**: Verify no exception raised
   - **Empty data**: Empty sessions, features, workflows; service handles gracefully
   - **Edge cases**: Missing feature ID, null dates, zero sessions

4. Use pytest parametrization for variants (feature exists/not exists, sync fresh/stale, etc.)

**Files to Create/Modify**:
- `backend/tests/conftest.py` (or extend existing with new fixtures)
- `backend/tests/test_agent_queries_shared.py` (~150 lines)

**Acceptance Criteria**:
- [ ] All service tests pass
- [ ] Coverage report shows >90% coverage for agent_queries module
- [ ] All graceful degradation scenarios tested
- [ ] No mocked methods called more than necessary (no N+1)
- [ ] Test output is clear and readable (good test names)

---

### P1-T7: Write Integration Tests Against Test Database

**Effort**: 1 story point  
**Duration**: 1 day  
**Assignee**: Backend Engineer (Test-Focused)  
**Depends on**: P1-T6

**Description**:
Write integration tests that run the query services against a real SQLite test database with fixture data. Verify that services work end-to-end and handle real DB state.

**Detailed Tasks**:

1. Create `backend/tests/fixtures/agent_queries_test_data.py`:
   - Seed test SQLite DB with representative sessions, features, documents, tasks
   - Include multiple workflow types, success/failure cases, varying costs

2. Create `backend/tests/test_agent_queries_integration.py`:
   - Test each service with the fixture database
   - Verify results match expected structure
   - Check that all DTOs serialize/deserialize via `model_dump()` and JSON roundtrip

3. Test matrix:
   - Each service × common scenarios (single feature, multiple features, empty project, etc.)

**Files to Create**:
- `backend/tests/test_agent_queries_integration.py` (~200 lines)
- `backend/tests/fixtures/agent_queries_test_data.py` (~150 lines)

**Acceptance Criteria**:
- [ ] Integration tests pass against test SQLite DB
- [ ] All 4 services return valid DTOs from real data
- [ ] JSON roundtrip (DTO → dict → JSON → dict → DTO) works without data loss

---

### P1-T8: Architecture Review and Documentation

**Effort**: 1 story point  
**Duration**: 0.5–1 day  
**Assignee**: Backend Engineer + Architecture Reviewer  
**Depends on**: P1-T2 through P1-T7

**Description**:
Present query service architecture to architecture review team for sign-off. Document design decisions and future-proof patterns.

**Detailed Tasks**:

1. Prepare architecture review:
   - Present query service contracts (DTOs, method signatures)
   - Show dependency graph (which services call which repositories)
   - Demonstrate graceful degradation handling
   - Walk through one end-to-end example (e.g., project status → REST endpoint → CLI command)

2. Create `backend/application/services/agent_queries/README.md`:
   - Overview of the agent_queries layer
   - When to add a new query service (criteria: requires 2+ domain queries)
   - How to add a new service (template, testing expectations)
   - Guidelines for DTO design (envelope, provenance fields)

3. Confirm no business logic duplication:
   - Query services use repositories and existing domain services only
   - No duplicate queries or complex logic outside existing patterns

**Files to Create**:
- `backend/application/services/agent_queries/README.md` (~150 lines)

**Acceptance Criteria**:
- [ ] Architecture review completed and approved
- [ ] No signoff blockers on query service design
- [ ] README provides clear guidance for future extensions
- [ ] No breaking changes to existing services or repositories

### Execution Order

- Batch 1: P1-T1
- Batch 2: P1-T2, P1-T3, P1-T4, P1-T5
- Batch 3: P1-T6
- Batch 4: P1-T7
- Batch 5: P1-T8

---

## Quality Gate

All of the following must be true to declare Phase 1 complete:

1. **All 4 query services implemented** (ProjectStatus, FeatureForensics, WorkflowDiagnostics, Reporting)
2. **All 4 DTOs include envelope fields** (status, data_freshness, generated_at, source_refs)
3. **Unit test coverage >90%** for agent_queries module (pytest coverage report)
4. **Graceful degradation tested**: Services return `status: partial` when subsystems unavailable, `status: error` only when no usable context exists, and `data_freshness` / `source_refs` come from the canonical helpers; no unhandled exceptions
5. **Integration tests passing** against test SQLite DB
6. **Architecture review signed off** on query service contracts
7. **No business logic duplication** with existing services (verified by code review)

---

## Files Summary

**New files created**:
- `backend/application/services/agent_queries/__init__.py`
- `backend/application/services/agent_queries/models.py`
- `backend/application/services/agent_queries/_filters.py`
- `backend/application/services/agent_queries/project_status.py`
- `backend/application/services/agent_queries/feature_forensics.py`
- `backend/application/services/agent_queries/workflow_intelligence.py`
- `backend/application/services/agent_queries/reporting.py`
- `backend/application/services/agent_queries/README.md`
- `backend/tests/test_agent_queries_project_status.py`
- `backend/tests/test_agent_queries_feature_forensics.py`
- `backend/tests/test_agent_queries_workflow_diagnostics.py`
- `backend/tests/test_agent_queries_reporting.py`
- `backend/tests/test_agent_queries_integration.py`
- `backend/tests/fixtures/agent_queries_test_data.py`

**Total new code**: ~2500 lines (services + tests)

---

## Dependencies

### External Dependencies
None new. Reuses existing:
- Pydantic (already in requirements)
- pytest (already in requirements)
- Existing CorePorts, repositories, domain services

### Internal Dependencies
- `backend.application.ports.core.CorePorts`
- `backend.application.context.RequestContext`
- `backend.db.repositories.*`
- `backend.application.services.*` (existing domain services)

### Sequencing
This phase is the critical path. Phases 2, 3, and 4 all depend on Phase 1 completion and stability.

---

## Effort Breakdown

| Task | Effort | Duration |
|------|--------|----------|
| P1-T1: Package structure | 1 pt | 0.5–1 d |
| P1-T2: ProjectStatusQueryService | 3 pts | 2–3 d |
| P1-T3: FeatureForensicsQueryService | 3 pts | 2–3 d |
| P1-T4: WorkflowDiagnosticsQueryService | 2 pts | 1–2 d |
| P1-T5: ReportingQueryService | 2 pts | 1–2 d |
| P1-T6: Unit tests | 2 pts | 2 d |
| P1-T7: Integration tests | 1 pt | 1 d |
| P1-T8: Architecture review | 1 pt | 0.5–1 d |
| **Total** | **8–10 pts** | **5–7 d** |

---

## Success Metrics

- [ ] All unit and integration tests passing
- [ ] Coverage report shows >90% coverage
- [ ] No warnings or linting errors
- [ ] Architecture review checklist complete
- [ ] Each DTO can serialize/deserialize without data loss
- [ ] Services handle missing/stale data gracefully

---

## Next Phase

After Phase 1 is complete:
- Phase 2: Create REST endpoints that call these services
- Phase 3: Create CLI commands that call these services (can start in parallel)
- Phase 4: Create MCP tools that call these services (can start in parallel)
