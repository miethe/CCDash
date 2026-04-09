---
schema_version: "1.0"
doc_type: phase_plan
title: "Phase 2: REST Composite Endpoints"
description: "Expose agent query services over HTTP via /api/agent/* endpoints to validate contracts before CLI and MCP implementation."
status: draft
created: "2026-04-02"
updated: "2026-04-02"
phase: 2
phase_title: "REST Composite Endpoints"
feature_slug: "ccdash-cli-mcp-enablement"
prd_ref: "docs/project_plans/PRDs/features/ccdash-cli-mcp-enablement-v1.md"
plan_ref: "docs/project_plans/implementation_plans/features/ccdash-cli-mcp-enablement-v1.md"
entry_criteria:
  - Phase 1 (agent query services) complete and tested
  - Phase 1 architecture review approved
  - FastAPI application running and routing structure understood
exit_criteria:
  - All 4 REST endpoints implemented at /api/agent/* paths
  - All endpoints appear in OpenAPI schema with examples
  - FastAPI TestClient tests pass for all endpoints
  - No duplicate service calls per request
  - Contract is final (no changes needed to Phase 1 DTOs)
priority: high
effort_estimate: 4-5
effort_estimate_unit: story_points
duration_estimate: 2-3
duration_estimate_unit: days
---

# Phase 2: REST Composite Endpoints

## Phase Overview

**Goal**: Expose the Phase 1 agent query services over REST endpoints at `/api/agent/*` as a validation gate. These endpoints are the canonical HTTP interface for agent-consumable intelligence and provide working examples for CLI and MCP implementations.

**Why Phase 2 First**: Testing contracts via REST before CLI and MCP ensures the service interfaces are well-designed and complete. Discovering issues here prevents rework in later phases.

**Key Invariant**: Each endpoint calls exactly one query service, no more, no less. No inline logic, no double-fetching.

---

## Task Breakdown

### P2-T1: Create agent.py Router and Dependency Injection

**Effort**: 1 story point  
**Duration**: 0.5–1 day  
**Assignee**: Backend Engineer  
**Depends on**: Phase 1 complete

**Description**:
Create the `backend/routers/agent.py` module and register it with the FastAPI app.

**Detailed Tasks**:

1. Create `backend/routers/agent.py`:
   ```python
   from fastapi import APIRouter, Depends, HTTPException
   from backend.application.context import RequestContext
   from backend.application.ports import CorePorts
   from backend.application.services.common import resolve_application_request
   from backend.application.services.agent_queries import (
       ProjectStatusQueryService,
       FeatureForensicsQueryService,
       WorkflowDiagnosticsQueryService,
       ReportingQueryService,
   )

   router = APIRouter(prefix="/agent", tags=["agent"])

   async def get_context_and_ports(
       request: Request,
   ) -> tuple[RequestContext, CorePorts]:
       """Dependency for injecting context and ports into handlers."""
       context = await resolve_application_request(request)
       ports = request.app.state.container.core_ports  # from RuntimeContainer
       return context, ports
   ```

2. Register router in `backend/runtime/bootstrap.py`:
   ```python
   from backend.routers import agent
   
   # In build_runtime_app() function, add:
   app.include_router(agent.router)
   ```

3. Ensure HTTP status codes and error handling:
   - 200 OK for successful queries
   - 404 Not Found for unknown feature_id
   - 422 Unprocessable Entity for invalid parameters
   - 500 Internal Server Error only for true service errors (not for "status: partial")

**Files to Create/Modify**:
- `backend/routers/agent.py` (new, ~50 lines of structure)
- `backend/runtime/bootstrap.py` (modify to import and register router)

**Acceptance Criteria**:
- [ ] Router module created and imports all query services
- [ ] Router registered with FastAPI app
- [ ] Dependency injection works (can call handlers without errors)
- [ ] OpenAPI schema reflects agent prefix

---

### P2-T2: Implement /api/agent/project-status Endpoint

**Effort**: 1 story point  
**Duration**: 0.5–1 day  
**Assignee**: Backend Engineer  
**Depends on**: P2-T1

**Description**:
Implement the GET endpoint for project status.

**Detailed Tasks**:

1. Add to `backend/routers/agent.py`:
   ```python
   @router.get(
       "/project-status",
       response_model=ProjectStatusDTO,
       summary="Get current project status",
       description="Returns a comprehensive project status including feature counts, "
                   "recent session activity, cost trends, and sync freshness.",
       example={"status": "ok", "project_id": "my-project", ...},
   )
   async def get_project_status(
       context: RequestContext = Depends(get_context),
       ports: CorePorts = Depends(get_ports),
       project_id: str | None = None,
   ) -> ProjectStatusDTO:
       """Get high-level project status and metrics."""
       service = ProjectStatusQueryService()
       return await service.get_status(context, ports, project_id_override=project_id)
   ```

2. Query parameter:
   - `project_id` (optional): Override active project

3. Response:
   - HTTP 200 with `ProjectStatusDTO` JSON body (including `status: ok` or `status: partial`)
   - HTTP 200 with `status: error` if project ID invalid

**Files to Modify**:
- `backend/routers/agent.py`

**Test File**:
- `backend/tests/routers/test_agent_router.py` (add test_get_project_status)

**Acceptance Criteria**:
- [ ] Endpoint accessible at GET `/api/agent/project-status`
- [ ] Returns ProjectStatusDTO with all fields
- [ ] Optional project_id query param works
- [ ] OpenAPI schema includes endpoint with description
- [ ] FastAPI TestClient test passes

---

### P2-T3: Implement /api/agent/feature-forensics/{feature_id} Endpoint

**Effort**: 1 story point  
**Duration**: 0.5–1 day  
**Assignee**: Backend Engineer  
**Depends on**: P2-T1

**Description**:
Implement the GET endpoint for feature forensics by feature ID.

**Detailed Tasks**:

1. Add to `backend/routers/agent.py`:
   ```python
   @router.get(
       "/feature-forensics/{feature_id}",
       response_model=FeatureForensicsDTO,
       summary="Get feature development forensics",
       description="Returns comprehensive history and metrics for a feature "
                   "including linked sessions, documents, iteration count, and cost.",
   )
   async def get_feature_forensics(
       feature_id: str,
       context: RequestContext = Depends(get_context),
       ports: CorePorts = Depends(get_ports),
   ) -> FeatureForensicsDTO:
       """Get detailed forensics for a specific feature."""
       service = FeatureForensicsQueryService()
       result = await service.get_forensics(context, ports, feature_id)
       if result.status == "error":
           raise HTTPException(status_code=404, detail=f"Feature {feature_id} not found")
       return result
   ```

2. Path parameter:
   - `feature_id` (required): The feature to analyze

3. Response:
   - HTTP 200 with `FeatureForensicsDTO`
   - HTTP 404 if feature not found (check `status: error`)

**Files to Modify**:
- `backend/routers/agent.py`

**Test File**:
- `backend/tests/routers/test_agent_router.py` (add test_get_feature_forensics)

**Acceptance Criteria**:
- [ ] Endpoint accessible at GET `/api/agent/feature-forensics/{feature_id}`
- [ ] Returns FeatureForensicsDTO with all fields
- [ ] Returns HTTP 404 for unknown feature
- [ ] Path parameter validation works
- [ ] OpenAPI schema includes endpoint with example

---

### P2-T4: Implement /api/agent/workflow-diagnostics and /api/agent/reports/aar Endpoints

**Effort**: 1 story point  
**Duration**: 0.5–1 day  
**Assignee**: Backend Engineer  
**Depends on**: P2-T1

**Description**:
Implement the two remaining endpoints for workflow diagnostics and AAR reporting.

**Detailed Tasks**:

1. Add workflow diagnostics GET endpoint:
   ```python
   @router.get(
       "/workflow-diagnostics",
       response_model=WorkflowDiagnosticsDTO,
       summary="Analyze workflow effectiveness",
       description="Returns per-workflow effectiveness scores, session counts, "
                   "success/failure mix, and failure patterns.",
   )
   async def get_workflow_diagnostics(
       context: RequestContext = Depends(get_context),
       ports: CorePorts = Depends(get_ports),
       feature_id: str | None = None,
   ) -> WorkflowDiagnosticsDTO:
       """Get workflow diagnostics and effectiveness analysis."""
       service = WorkflowDiagnosticsQueryService()
       return await service.get_diagnostics(context, ports, feature_id=feature_id)
   ```

2. Add AAR report POST endpoint:
   ```python
   @router.post(
       "/reports/aar",
       response_model=AARReportDTO,
       summary="Generate after-action review",
       description="Generate a structured after-action review for a feature "
                   "with scope, timeline, metrics, and lessons learned.",
   )
   async def generate_aar_report(
       request_body: AARReportRequest,  # feature_id, project_id (optional)
       context: RequestContext = Depends(get_context),
       ports: CorePorts = Depends(get_ports),
   ) -> AARReportDTO:
       """Generate an after-action review for a feature."""
       service = ReportingQueryService()
       return await service.generate_aar(context, ports, request_body.feature_id)
   ```

3. Define request model:
   ```python
   class AARReportRequest(BaseModel):
       feature_id: str
       project_id: str | None = None
   ```

4. Response codes:
   - HTTP 200 for successful AAR generation
   - HTTP 404 if feature not found

**Files to Modify**:
- `backend/routers/agent.py`

**Test File**:
- `backend/tests/routers/test_agent_router.py` (add tests for both endpoints)

**Acceptance Criteria**:
- [ ] GET `/api/agent/workflow-diagnostics` returns WorkflowDiagnosticsDTO
- [ ] POST `/api/agent/reports/aar` with valid feature_id returns AARReportDTO
- [ ] Both endpoints appear in OpenAPI schema
- [ ] Query/body parameters documented
- [ ] FastAPI TestClient tests pass

---

### P2-T5: Integration Tests and OpenAPI Documentation

**Effort**: 1 story point  
**Duration**: 1 day  
**Assignee**: Backend Engineer (Test-Focused)  
**Depends on**: P2-T2, P2-T3, P2-T4

**Description**:
Write comprehensive tests for all agent endpoints and verify OpenAPI documentation.

**Detailed Tasks**:

1. Create `backend/tests/routers/test_agent_router.py`:
   - Test all 4 endpoints with FastAPI TestClient
   - Verify response codes (200, 404, 422)
   - Verify response structure (status, data, fields)
   - Verify error handling (stale sync, missing data)
   - Test optional parameters (project_id override, feature_id filter)

2. Test scenarios per endpoint:
   - **Happy path**: Valid request, complete data returned
   - **Partial availability**: Subsystem unavailable, status: partial returned
   - **Invalid input**: Bad feature_id, missing required params
   - **Empty project**: No sessions, features, workflows

3. Verify OpenAPI documentation:
   - Navigate to `/docs` in running app
   - Verify all `/api/agent/*` endpoints visible
   - Verify request/response schemas populated
   - Verify example values shown
   - Test "Try it out" functionality in Swagger UI

4. Create example curl commands in docstring or separate guide:
   ```bash
   curl http://localhost:8000/api/agent/project-status
   curl http://localhost:8000/api/agent/feature-forensics/feature-123
   curl http://localhost:8000/api/agent/workflow-diagnostics
   curl -X POST http://localhost:8000/api/agent/reports/aar \
     -H "Content-Type: application/json" \
     -d '{"feature_id": "feature-123"}'
   ```

**Files to Create**:
- `backend/tests/routers/test_agent_router.py` (~400 lines)

**Acceptance Criteria**:
- [ ] All FastAPI TestClient tests pass
- [ ] Each endpoint tested for happy path and error cases
- [ ] OpenAPI schema includes all endpoints with descriptions
- [ ] Example curl commands work
- [ ] Response schemas match Phase 1 DTOs exactly

---

### P2-T6: Verify No Business Logic Duplication

**Effort**: 0.5 story points (part of code review, not separate task)  
**Duration**: 0.5 day  
**Assignee**: Code Reviewer  
**Depends on**: All P2 tasks

**Description**:
Code review checkpoint to verify router handlers are thin adapters only.

**Checklist**:
- [ ] Each endpoint handler is 5–10 lines (instantiate service, call method, return)
- [ ] No complex logic in router (filtering, aggregation, etc.)
- [ ] No database queries in router (all via services)
- [ ] No duplicate service calls per endpoint
- [ ] Service called exactly once per request
- [ ] All error handling delegated to service (returns status: error or status: partial)

---

## Quality Gate

All of the following must be true to declare Phase 2 complete:

1. **All 4 endpoints implemented** (project-status, feature-forensics, workflow-diagnostics, reports/aar)
2. **All endpoints registered** with FastAPI and visible in OpenAPI schema (`/docs`)
3. **No inline query logic** in router handlers (verified by code review)
4. **Each endpoint calls exactly one service** (verified by request/response logs)
5. **All FastAPI TestClient tests passing**
6. **Example curl commands work**
7. **Response structure matches Phase 1 DTOs** (no schema changes needed)
8. **No HTTP handler throws unhandled exception** (all errors returned as structured DTO with status: error)

---

## Files Summary

**New files created**:
- `backend/routers/agent.py` (~150 lines)
- `backend/tests/routers/test_agent_router.py` (~400 lines)

**Files modified**:
- `backend/runtime/bootstrap.py` (add import and router registration, ~5 lines)

**Total new code**: ~555 lines

---

## Dependencies

### External
- FastAPI (already in requirements)
- Pydantic (already in requirements)

### Internal
- `backend.application.services.agent_queries.*` (Phase 1)
- `backend.application.context.RequestContext`
- `backend.application.ports.CorePorts`
- `backend.runtime.container.RuntimeContainer`

### Sequencing
Phase 2 depends on Phase 1 completion. Can proceed immediately after Phase 1 quality gate passes.

---

## Effort Breakdown

| Task | Effort | Duration |
|------|--------|----------|
| P2-T1: Router structure | 1 pt | 0.5–1 d |
| P2-T2: project-status endpoint | 1 pt | 0.5–1 d |
| P2-T3: feature-forensics endpoint | 1 pt | 0.5–1 d |
| P2-T4: workflow-diagnostics + aar endpoints | 1 pt | 0.5–1 d |
| P2-T5: Integration tests + OpenAPI verification | 1 pt | 1 d |
| P2-T6: Code review | 0.5 pt | 0.5 d |
| **Total** | **4–5 pts** | **2–3 d** |

---

## Success Metrics

- [ ] All REST endpoint tests passing
- [ ] OpenAPI schema complete and example-rich
- [ ] No duplicate service calls per request
- [ ] Response latency <100 ms (p95) on local SQLite
- [ ] All curl examples functional

---

## Next Phase

After Phase 2 is complete:
- **Phase 3**: Implement CLI using the same query services (can reference REST contract as example)
- **Phase 4**: Implement MCP tools using the same query services (can reference REST contract as example)
- Both Phase 3 and 4 can proceed in parallel after Phase 1 is stable

Phase 2 serves as the contract validation gate. If service contracts change during Phase 3/4, update REST endpoints first, then update CLI/MCP in parallel.
