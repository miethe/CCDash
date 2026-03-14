"""Execution API router for in-app local terminal runs."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.application.services import resolve_application_request
from backend.application.services.execution import ExecutionApplicationService
from backend.models import (
    ExecutionApprovalRequest,
    ExecutionCancelRequest,
    ExecutionPolicyCheckRequest,
    ExecutionPolicyResultDTO,
    ExecutionRetryRequest,
    ExecutionRunCreateRequest,
    ExecutionRunDTO,
    ExecutionRunEventDTO,
    ExecutionRunEventPageDTO,
)
from backend.request_scope import get_core_ports, get_request_context


execution_router = APIRouter(prefix="/api/execution", tags=["execution"])
execution_application_service = ExecutionApplicationService()


def _to_policy_dto(result: Any) -> ExecutionPolicyResultDTO:
    return ExecutionPolicyResultDTO(
        verdict=result.verdict,
        riskLevel=result.risk_level,
        requiresApproval=result.requires_approval,
        normalizedCommand=result.normalized_command,
        commandTokens=result.command_tokens,
        resolvedCwd=result.resolved_cwd,
        reasonCodes=result.reason_codes,
    )


def _to_run_dto(row: dict[str, Any]) -> ExecutionRunDTO:
    return ExecutionRunDTO(
        id=str(row.get("id") or ""),
        projectId=str(row.get("project_id") or ""),
        featureId=str(row.get("feature_id") or ""),
        provider=str(row.get("provider") or "local"),
        sourceCommand=str(row.get("source_command") or ""),
        normalizedCommand=str(row.get("normalized_command") or ""),
        cwd=str(row.get("cwd") or ""),
        envProfile=str(row.get("env_profile") or "default"),
        recommendationRuleId=str(row.get("recommendation_rule_id") or ""),
        riskLevel=str(row.get("risk_level") or "medium"),
        policyVerdict=str(row.get("policy_verdict") or "allow"),
        requiresApproval=bool(row.get("requires_approval")),
        approvedBy=str(row.get("approved_by") or ""),
        approvedAt=str(row.get("approved_at") or ""),
        status=str(row.get("status") or "queued"),
        exitCode=row.get("exit_code"),
        startedAt=str(row.get("started_at") or ""),
        endedAt=str(row.get("ended_at") or ""),
        retryOfRunId=str(row.get("retry_of_run_id") or ""),
        metadata=row.get("metadata_json", {}) if isinstance(row.get("metadata_json"), dict) else {},
        createdAt=str(row.get("created_at") or ""),
        updatedAt=str(row.get("updated_at") or ""),
    )


def _to_event_dto(row: dict[str, Any]) -> ExecutionRunEventDTO:
    return ExecutionRunEventDTO(
        id=int(row.get("id")) if row.get("id") is not None else None,
        runId=str(row.get("run_id") or ""),
        sequenceNo=int(row.get("sequence_no") or 0),
        stream=str(row.get("stream") or "system"),
        eventType=str(row.get("event_type") or "status"),
        payloadText=str(row.get("payload_text") or ""),
        payload=row.get("payload_json", {}) if isinstance(row.get("payload_json"), dict) else {},
        occurredAt=str(row.get("occurred_at") or ""),
    )


async def _resolve_request(
    request_context: RequestContext,
    core_ports: CorePorts,
):
    return await resolve_application_request(request_context, core_ports, core_ports.storage.db)


@execution_router.post("/policy-check", response_model=ExecutionPolicyResultDTO)
async def check_execution_policy(
    req: ExecutionPolicyCheckRequest,
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> ExecutionPolicyResultDTO:
    app_request = await _resolve_request(request_context, core_ports)
    policy = await execution_application_service.check_policy(app_request.context, app_request.ports, req)
    return _to_policy_dto(policy)


@execution_router.post("/runs", response_model=ExecutionRunDTO)
async def create_execution_run(
    req: ExecutionRunCreateRequest,
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> ExecutionRunDTO:
    app_request = await _resolve_request(request_context, core_ports)
    created = await execution_application_service.create_run(app_request.context, app_request.ports, req)
    return _to_run_dto(created)


@execution_router.get("/runs", response_model=list[ExecutionRunDTO])
async def list_execution_runs(
    feature_id: str | None = None,
    limit: int = 40,
    offset: int = 0,
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> list[ExecutionRunDTO]:
    app_request = await _resolve_request(request_context, core_ports)
    rows = await execution_application_service.list_runs(
        app_request.context,
        app_request.ports,
        feature_id=feature_id,
        limit=limit,
        offset=offset,
    )
    return [_to_run_dto(row) for row in rows]


@execution_router.get("/runs/{run_id}", response_model=ExecutionRunDTO)
async def get_execution_run(
    run_id: str,
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> ExecutionRunDTO:
    app_request = await _resolve_request(request_context, core_ports)
    row = await execution_application_service.get_run(app_request.context, app_request.ports, run_id)
    return _to_run_dto(row)


@execution_router.get("/runs/{run_id}/events", response_model=ExecutionRunEventPageDTO)
async def list_execution_run_events(
    run_id: str,
    after_sequence: int = 0,
    limit: int = 200,
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> ExecutionRunEventPageDTO:
    app_request = await _resolve_request(request_context, core_ports)
    rows = await execution_application_service.list_events(
        app_request.context,
        app_request.ports,
        run_id,
        after_sequence=after_sequence,
        limit=limit,
    )
    safe_after = max(0, int(after_sequence or 0))
    items = [_to_event_dto(row) for row in rows]
    next_sequence = max([safe_after, *[item.sequenceNo for item in items]])
    return ExecutionRunEventPageDTO(runId=run_id, items=items, nextSequence=next_sequence)


@execution_router.post("/runs/{run_id}/approve", response_model=ExecutionRunDTO)
async def approve_execution_run(
    run_id: str,
    req: ExecutionApprovalRequest,
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> ExecutionRunDTO:
    app_request = await _resolve_request(request_context, core_ports)
    row = await execution_application_service.approve_run(app_request.context, app_request.ports, run_id, req)
    return _to_run_dto(row)


@execution_router.post("/runs/{run_id}/cancel", response_model=ExecutionRunDTO)
async def cancel_execution_run(
    run_id: str,
    req: ExecutionCancelRequest,
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> ExecutionRunDTO:
    app_request = await _resolve_request(request_context, core_ports)
    row = await execution_application_service.cancel_run(app_request.context, app_request.ports, run_id, req)
    return _to_run_dto(row)


@execution_router.post("/runs/{run_id}/retry", response_model=ExecutionRunDTO)
async def retry_execution_run(
    run_id: str,
    req: ExecutionRetryRequest,
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> ExecutionRunDTO:
    app_request = await _resolve_request(request_context, core_ports)
    row = await execution_application_service.retry_run(app_request.context, app_request.ports, run_id, req)
    return _to_run_dto(row)
