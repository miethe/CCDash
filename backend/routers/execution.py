"""Execution API router for in-app local terminal runs."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from backend import config
from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.application.services import resolve_application_request
from backend.application.services.common import require_project
from backend.application.services.execution import ExecutionApplicationService
from backend.application.services.launch_preparation import LaunchPreparationApplicationService
from backend.observability import otel
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
    LaunchCapabilitiesDTO,
    LaunchPreparationDTO,
    LaunchPreparationRequest,
    LaunchStartRequest,
    LaunchStartResponse,
    WorktreeContextCreateRequest,
    WorktreeContextDTO,
    WorktreeContextListResponse,
    WorktreeContextUpdateRequest,
)
from backend.request_scope import get_core_ports, get_request_context
from backend.services.launch_providers import default_provider_catalog


execution_router = APIRouter(prefix="/api/execution", tags=["execution"])
execution_application_service = ExecutionApplicationService()
launch_preparation_service = LaunchPreparationApplicationService()


def _require_launch_enabled() -> None:
    if not config.CCDASH_LAUNCH_PREP_ENABLED:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "launch_disabled",
                "message": "Plan-driven launch preparation is disabled.",
                "hint": "Set CCDASH_LAUNCH_PREP_ENABLED=true to enable.",
            },
        )


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


# ── Worktree context helpers ──────────────────────────────────────────────────


def _to_worktree_dto(row: dict[str, Any]) -> WorktreeContextDTO:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    return WorktreeContextDTO(
        id=str(row.get("id") or ""),
        projectId=str(row.get("project_id") or ""),
        featureId=str(row.get("feature_id") or ""),
        phaseNumber=row.get("phase_number"),
        batchId=str(row.get("batch_id") or ""),
        branch=str(row.get("branch") or ""),
        worktreePath=str(row.get("worktree_path") or ""),
        baseBranch=str(row.get("base_branch") or ""),
        baseCommitSha=str(row.get("base_commit_sha") or ""),
        status=str(row.get("status") or "draft"),
        lastRunId=str(row.get("last_run_id") or ""),
        provider=str(row.get("provider") or "local"),
        notes=str(row.get("notes") or ""),
        metadata=metadata if isinstance(metadata, dict) else {},
        createdBy=str(row.get("created_by") or ""),
        createdAt=str(row.get("created_at") or ""),
        updatedAt=str(row.get("updated_at") or ""),
    )


# ── Launch preparation endpoints ──────────────────────────────────────────────


@execution_router.get("/launch/capabilities", response_model=LaunchCapabilitiesDTO)
async def get_launch_capabilities() -> LaunchCapabilitiesDTO:
    with otel.start_span("launch.capabilities"):
        enabled = bool(config.CCDASH_LAUNCH_PREP_ENABLED)
        providers = default_provider_catalog() if enabled else []
        return LaunchCapabilitiesDTO(
            enabled=enabled,
            disabledReason="" if enabled else "CCDASH_LAUNCH_PREP_ENABLED is false",
            providers=providers,
            planningEnabled=bool(config.CCDASH_PLANNING_CONTROL_PLANE_ENABLED),
        )


@execution_router.post(
    "/launch/prepare",
    response_model=LaunchPreparationDTO,
    dependencies=[Depends(_require_launch_enabled)],
)
async def prepare_launch(
    req: LaunchPreparationRequest,
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> LaunchPreparationDTO:
    with otel.start_span(
        "launch.prepare",
        {
            "project_id": req.projectId,
            "feature_id": req.featureId,
            "phase_number": req.phaseNumber,
            "batch_id": req.batchId,
        },
    ):
        app_request = await _resolve_request(request_context, core_ports)
        return await launch_preparation_service.prepare(app_request.context, app_request.ports, req)


@execution_router.post(
    "/launch/start",
    response_model=LaunchStartResponse,
    dependencies=[Depends(_require_launch_enabled)],
)
async def start_launch(
    req: LaunchStartRequest,
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> LaunchStartResponse:
    with otel.start_span(
        "launch.start",
        {
            "project_id": req.projectId,
            "feature_id": req.featureId,
            "phase_number": req.phaseNumber,
            "batch_id": req.batchId,
            "provider": req.provider,
        },
    ):
        app_request = await _resolve_request(request_context, core_ports)
        return await launch_preparation_service.start(app_request.context, app_request.ports, req)


# ── Worktree context CRUD endpoints ──────────────────────────────────────────


@execution_router.get("/worktree-contexts", response_model=WorktreeContextListResponse)
async def list_worktree_contexts(
    feature_id: str | None = None,
    phase_number: int | None = None,
    batch_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> WorktreeContextListResponse:
    app_request = await _resolve_request(request_context, core_ports)
    project = require_project(app_request.context, app_request.ports)
    repo = app_request.ports.storage.worktree_contexts()
    safe_limit = min(200, max(1, int(limit or 50)))
    safe_offset = max(0, int(offset or 0))
    rows = await repo.list(
        project.id,
        feature_id=str(feature_id or "").strip() or None,
        phase_number=phase_number,
        batch_id=str(batch_id or "").strip() or None,
        status=str(status or "").strip() or None,
        limit=safe_limit,
        offset=safe_offset,
    )
    total = await repo.count(
        project.id,
        feature_id=str(feature_id or "").strip() or None,
        phase_number=phase_number,
        batch_id=str(batch_id or "").strip() or None,
        status=str(status or "").strip() or None,
    )
    return WorktreeContextListResponse(
        items=[_to_worktree_dto(row) for row in rows],
        total=int(total),
    )


@execution_router.post("/worktree-contexts", response_model=WorktreeContextDTO)
async def create_worktree_context(
    req: WorktreeContextCreateRequest,
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> WorktreeContextDTO:
    app_request = await _resolve_request(request_context, core_ports)
    project = require_project(app_request.context, app_request.ports)
    repo = app_request.ports.storage.worktree_contexts()
    row = await repo.create(
        {
            "project_id": project.id,
            "feature_id": req.featureId,
            "phase_number": req.phaseNumber,
            "batch_id": req.batchId,
            "branch": req.branch,
            "worktree_path": req.worktreePath,
            "base_branch": req.baseBranch,
            "base_commit_sha": req.baseCommitSha,
            "status": "draft",
            "provider": req.provider,
            "notes": req.notes,
            "metadata_json": req.metadata or {},
            "created_by": req.createdBy,
        }
    )
    return _to_worktree_dto(row)


@execution_router.patch(
    "/worktree-contexts/{context_id}",
    response_model=WorktreeContextDTO,
)
async def update_worktree_context(
    context_id: str,
    req: WorktreeContextUpdateRequest,
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> WorktreeContextDTO:
    app_request = await _resolve_request(request_context, core_ports)
    project = require_project(app_request.context, app_request.ports)
    repo = app_request.ports.storage.worktree_contexts()
    existing = await repo.get_by_id(context_id)
    if existing is None or str(existing.get("project_id") or "") != project.id:
        raise HTTPException(status_code=404, detail=f"Worktree context '{context_id}' not found")
    updates: dict[str, Any] = {}
    for camel, snake in (
        ("status", "status"),
        ("branch", "branch"),
        ("worktreePath", "worktree_path"),
        ("baseBranch", "base_branch"),
        ("baseCommitSha", "base_commit_sha"),
        ("lastRunId", "last_run_id"),
        ("notes", "notes"),
    ):
        value = getattr(req, camel)
        if value is not None:
            updates[snake] = value
    if req.metadata is not None:
        updates["metadata_json"] = req.metadata
    if not updates:
        return _to_worktree_dto(existing)
    row = await repo.update(context_id, updates)
    return _to_worktree_dto(row or existing)
