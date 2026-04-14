---
schema_version: "1.0"
doc_type: phase_plan
title: "Phase 2: REST Composite Endpoints"
description: "Expose Phase 1 agent query services over /api/agent/* routes using current CCDash router, DI, registration, and test conventions."
status: in-progress
created: "2026-04-02"
updated: "2026-04-11"
phase: 2
phase_title: "REST Composite Endpoints"
feature_slug: "ccdash-cli-mcp-enablement"
prd_ref: "docs/project_plans/PRDs/features/ccdash-cli-mcp-enablement-v1.md"
plan_ref: "docs/project_plans/implementation_plans/features/ccdash-cli-mcp-enablement-v1.md"
entry_criteria:
  - Phase 1 is complete in-repo; use ../../../../../.claude/progress/ccdash-cli-mcp-enablement-v1/phase-1-progress.md as the frozen contract/evidence artifact
  - Router wiring must follow backend/request_scope.py and backend/runtime/bootstrap.py
  - Router tests must follow existing top-level async unittest modules under backend/tests/
exit_criteria:
  - All 4 REST endpoints are implemented at /api/agent/* paths
  - Router registration matches backend/runtime/bootstrap.py include_router style
  - Handlers use backend/request_scope.py dependencies and resolve_application_request(...)
  - Top-level async router tests pass for happy-path and error/partial cases
  - No Phase 1 DTO changes are required after REST validation
priority: high
effort_estimate: 4-5
effort_estimate_unit: story_points
duration_estimate: 2-3
duration_estimate_unit: days
---

# Phase 2: REST Composite Endpoints

## Execution Baseline

- Phase 1 is already complete. Treat [Phase 1 progress](../../../../../.claude/progress/ccdash-cli-mcp-enablement-v1/phase-1-progress.md) as the frozen service contract and completion evidence.
- Phase 2 tracking lives in [phase-2-progress.md](../../../../../.claude/progress/ccdash-cli-mcp-enablement-v1/phase-2-progress.md).
- This phase validates the HTTP adapter only. Do not reopen Phase 1 service design unless a real contract defect is discovered.

## Repo Patterns To Mirror

- Router prefix lives in the router object: use `APIRouter(prefix="/api/agent", tags=["agent"])`.
- Dependency wiring comes from [backend/request_scope.py](../../../../../backend/request_scope.py): `get_request_context` and `get_core_ports`.
- When a handler needs the shared wrapper, call `resolve_application_request(request_context, core_ports, core_ports.storage.db, ...)` as existing routers do.
- Register the router by importing the concrete router symbol into [backend/runtime/bootstrap.py](../../../../../backend/runtime/bootstrap.py) and including it inside `_register_routers()`.
- Follow current router module conventions: create module-scope service instances instead of instantiating services inside every handler when reuse is straightforward.
- Follow current test conventions: add a top-level async unittest module under `backend/tests/` and call router handlers directly with patched collaborators. Do not introduce `backend/tests/routers/` or `FastAPI TestClient` as the primary pattern for this phase.

## Scope

Implement these HTTP surfaces only:

1. `GET /api/agent/project-status`
2. `GET /api/agent/feature-forensics/{feature_id}`
3. `GET /api/agent/workflow-diagnostics`
4. `POST /api/agent/reports/aar`

## Task Breakdown

### P2-T1: Router Scaffold, DI, and Registration

**Depends on**: Phase 1 complete  
**Goal**: Create the router module in the same style as existing backend routers.

Implementation target:

```python
from fastapi import APIRouter, Depends, Query

from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.application.services import resolve_application_request
from backend.application.services.agent_queries import (
    FeatureForensicsQueryService,
    ProjectStatusQueryService,
    ReportingQueryService,
    WorkflowDiagnosticsQueryService,
)
from backend.request_scope import get_core_ports, get_request_context


agent_router = APIRouter(prefix="/api/agent", tags=["agent"])
project_status_query_service = ProjectStatusQueryService()
feature_forensics_query_service = FeatureForensicsQueryService()
workflow_diagnostics_query_service = WorkflowDiagnosticsQueryService()
reporting_query_service = ReportingQueryService()


async def _resolve_app_request(
    request_context: RequestContext,
    core_ports: CorePorts,
    *,
    requested_project_id: str | None = None,
):
    return await resolve_application_request(
        request_context,
        core_ports,
        core_ports.storage.db,
        requested_project_id=requested_project_id,
    )
```

Registration target in `backend/runtime/bootstrap.py`:

```python
from backend.routers.agent import agent_router


def _register_routers(app: FastAPI) -> None:
    ...
    app.include_router(agent_router)
```

Acceptance criteria:

- [ ] Router prefix is `/api/agent`
- [ ] DI uses `get_request_context` and `get_core_ports`
- [ ] Shared request wrapper uses `resolve_application_request(...)`
- [ ] Router registration matches existing explicit import/include style
- [ ] Query services are created at module scope

### P2-T2: Read Endpoints for Project Status and Feature Forensics

**Depends on**: P2-T1  
**Goal**: Add the two GET handlers that validate Phase 1 read contracts.

Implementation notes:

- Use `response_model=...` on each route.
- Use `Query(..., description=...)` for documented optional params.
- Add concise handler docstrings; avoid route-decorator `example=` usage unless a repo precedent appears during implementation.
- Return the Phase 1 DTO directly when the service already encodes `ok`/`partial`/`error`.
- If HTTP translation is still required for a true not-found case, keep it minimal and consistent.

Suggested handler shape:

```python
@agent_router.get("/project-status", response_model=ProjectStatusDTO)
async def get_project_status(
    project_id: str | None = Query(default=None, description="Optional project override."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> ProjectStatusDTO:
    """Return the current project status snapshot for agent consumers."""
    app_request = await _resolve_app_request(
        request_context,
        core_ports,
        requested_project_id=project_id,
    )
    return await project_status_query_service.get_status(
        app_request.context,
        app_request.ports,
        project_id_override=project_id,
    )
```

Acceptance criteria:

- [ ] `GET /api/agent/project-status` delegates once to `ProjectStatusQueryService`
- [ ] `GET /api/agent/feature-forensics/{feature_id}` delegates once to `FeatureForensicsQueryService`
- [ ] Optional params are documented with `Query`
- [ ] No inline aggregation, repository calls, or duplicate service invocations

### P2-T3: Read Endpoints for Workflow Diagnostics and AAR

**Depends on**: P2-T1  
**Goal**: Add the remaining GET/POST handlers while keeping request schema honest about current service capabilities.

Implementation notes:

- `WorkflowDiagnosticsQueryService` stays a straight read adapter with an optional `feature_id` filter.
- `ReportingQueryService.generate_aar(...)` currently accepts `feature_id` only. If `project_id` is included in the POST body for forward compatibility, mark it as reserved/ignored in the request model description and do not pass it through in Phase 2.

Suggested request model:

```python
class AARReportRequest(BaseModel):
    feature_id: str
    project_id: str | None = Field(
        default=None,
        description="Reserved for future project-scoped AAR generation. Ignored in Phase 2.",
    )
```

Acceptance criteria:

- [ ] `GET /api/agent/workflow-diagnostics` delegates once to `WorkflowDiagnosticsQueryService`
- [ ] `POST /api/agent/reports/aar` delegates once to `ReportingQueryService.generate_aar(...)`
- [ ] `project_id` is either omitted or explicitly documented as reserved/ignored
- [ ] Response models stay aligned with Phase 1 DTOs

### P2-T4: Router Test Coverage and Contract Verification

**Depends on**: P2-T2, P2-T3  
**Goal**: Validate the router using the repo’s existing test style and close the contract gate.

Test strategy:

- Create `backend/tests/test_agent_router.py`.
- Use `unittest.IsolatedAsyncioTestCase`.
- Import the router module directly and call handler functions with patched query services/collaborators.
- Cover happy-path, partial-response, invalid input, and not-found translation cases as appropriate.
- Verify the router stays thin: each handler resolves request scope once and delegates to one query service once.

Acceptance criteria:

- [ ] New top-level async unittest module exists at `backend/tests/test_agent_router.py`
- [ ] No `FastAPI TestClient` dependency is introduced as the main Phase 2 test strategy
- [ ] OpenAPI visibility is verified after router registration
- [ ] Phase 1 DTO shapes remain unchanged after endpoint validation

## Delivery Checklist

- [ ] `backend/routers/agent.py`
- [ ] `backend/runtime/bootstrap.py`
- [ ] `backend/tests/test_agent_router.py`
- [ ] Focused test command documented and runnable
- [ ] Phase 2 progress artifact updated as tasks complete

## Suggested Validation Commands

```bash
backend/.venv/bin/python -m pytest backend/tests/test_agent_router.py -q
backend/.venv/bin/python -m pytest backend/tests/test_execution_router.py backend/tests/test_test_visualizer_router.py backend/tests/test_agent_router.py -q
```

## Definition of Done

Phase 2 is complete only when:

1. All four `/api/agent/*` handlers are implemented and registered.
2. The router follows `backend/request_scope.py` and `backend/runtime/bootstrap.py` conventions exactly.
3. Tests pass using the repo’s top-level async router-test style.
4. No Phase 1 DTO contract changes are needed after REST validation.
