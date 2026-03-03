"""Execution API router for in-app local terminal runs."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from backend import config
from backend.db import connection
from backend.db.factory import get_execution_repository
from backend.models import (
    ExecutionApprovalDTO,
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
from backend.project_manager import project_manager
from backend.services.execution_policy import evaluate_execution_policy
from backend.services.execution_runtime import get_execution_runtime


execution_router = APIRouter(prefix="/api/execution", tags=["execution"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _active_project_or_400() -> Any:
    project = project_manager.get_active_project()
    if not project:
        raise HTTPException(status_code=400, detail="No active project")
    return project


def _workspace_root(project: Any) -> Path:
    base = str(getattr(project, "path", "") or config.CCDASH_PROJECT_ROOT).strip() or config.CCDASH_PROJECT_ROOT
    return Path(base).expanduser().resolve(strict=False)


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


def _to_approval_dto(row: dict[str, Any]) -> ExecutionApprovalDTO:
    return ExecutionApprovalDTO(
        id=int(row.get("id")) if row.get("id") is not None else None,
        runId=str(row.get("run_id") or ""),
        decision=str(row.get("decision") or "pending"),
        reason=str(row.get("reason") or ""),
        requestedAt=str(row.get("requested_at") or ""),
        resolvedAt=str(row.get("resolved_at") or ""),
        requestedBy=str(row.get("requested_by") or ""),
        resolvedBy=str(row.get("resolved_by") or ""),
    )


def _assert_run_project(row: dict | None, project_id: str, run_id: str) -> dict:
    if not row or str(row.get("project_id") or "") != project_id:
        raise HTTPException(status_code=404, detail=f"Execution run '{run_id}' not found")
    return row


async def _queue_runtime_start(
    *,
    db: Any,
    run_row: dict,
    command_tokens: list[str],
    project_root: str,
) -> None:
    runtime = get_execution_runtime()
    await runtime.start_run(
        db=db,
        run_id=str(run_row.get("id") or ""),
        command_tokens=command_tokens,
        cwd=str(run_row.get("cwd") or ""),
        env_profile=str(run_row.get("env_profile") or "default"),
        project_root=project_root,
    )


async def _create_execution_run(
    *,
    db: Any,
    project: Any,
    req: ExecutionRunCreateRequest,
    retry_of_run_id: str = "",
) -> dict:
    repo = get_execution_repository(db)
    policy = evaluate_execution_policy(
        command=req.command,
        workspace_root=_workspace_root(project),
        cwd=req.cwd or ".",
        env_profile=req.envProfile or "default",
    )

    run_id = uuid4().hex
    now = _now_iso()
    initial_status = "queued" if policy.verdict == "allow" else "blocked"
    run_row = await repo.create_run(
        {
            "id": run_id,
            "project_id": project.id,
            "feature_id": req.featureId,
            "provider": "local",
            "source_command": req.command,
            "normalized_command": policy.normalized_command,
            "cwd": policy.resolved_cwd,
            "env_profile": req.envProfile or "default",
            "recommendation_rule_id": req.recommendationRuleId,
            "risk_level": policy.risk_level,
            "policy_verdict": policy.verdict,
            "requires_approval": policy.requires_approval,
            "status": initial_status,
            "retry_of_run_id": retry_of_run_id,
            "metadata_json": req.metadata or {},
            "created_at": now,
            "updated_at": now,
        }
    )

    await repo.append_run_events(
        run_id,
        [
            {
                "stream": "system",
                "event_type": "policy",
                "payload_text": f"Policy verdict: {policy.verdict}",
                "payload_json": {
                    "verdict": policy.verdict,
                    "riskLevel": policy.risk_level,
                    "requiresApproval": policy.requires_approval,
                    "reasonCodes": policy.reason_codes,
                },
                "occurred_at": now,
            }
        ],
    )

    if policy.verdict == "deny":
        await repo.append_run_events(
            run_id,
            [
                {
                    "stream": "system",
                    "event_type": "status",
                    "payload_text": "Run blocked by policy.",
                    "payload_json": {"status": "blocked"},
                    "occurred_at": _now_iso(),
                }
            ],
        )
        return (await repo.get_run(run_id)) or run_row

    if policy.verdict == "requires_approval":
        approval = await repo.create_approval(
            {
                "run_id": run_id,
                "decision": "pending",
                "reason": "",
                "requested_at": _now_iso(),
                "requested_by": "user",
            }
        )
        await repo.append_run_events(
            run_id,
            [
                {
                    "stream": "system",
                    "event_type": "approval",
                    "payload_text": "Approval required before run can start.",
                    "payload_json": {"approval": _to_approval_dto(approval).model_dump()},
                    "occurred_at": _now_iso(),
                }
            ],
        )
        return (await repo.get_run(run_id)) or run_row

    await _queue_runtime_start(
        db=db,
        run_row=run_row,
        command_tokens=policy.command_tokens,
        project_root=str(_workspace_root(project)),
    )
    return (await repo.get_run(run_id)) or run_row


@execution_router.post("/policy-check", response_model=ExecutionPolicyResultDTO)
async def check_execution_policy(req: ExecutionPolicyCheckRequest) -> ExecutionPolicyResultDTO:
    project = _active_project_or_400()
    policy = evaluate_execution_policy(
        command=req.command,
        workspace_root=_workspace_root(project),
        cwd=req.cwd,
        env_profile=req.envProfile,
    )
    return _to_policy_dto(policy)


@execution_router.post("/runs", response_model=ExecutionRunDTO)
async def create_execution_run(req: ExecutionRunCreateRequest) -> ExecutionRunDTO:
    project = _active_project_or_400()
    db = await connection.get_connection()
    created = await _create_execution_run(db=db, project=project, req=req)
    return _to_run_dto(created)


@execution_router.get("/runs", response_model=list[ExecutionRunDTO])
async def list_execution_runs(
    feature_id: str | None = None,
    limit: int = 40,
    offset: int = 0,
) -> list[ExecutionRunDTO]:
    project = _active_project_or_400()
    safe_limit = min(200, max(1, int(limit or 40)))
    safe_offset = max(0, int(offset or 0))
    db = await connection.get_connection()
    repo = get_execution_repository(db)
    rows = await repo.list_runs(
        project.id,
        feature_id=str(feature_id or "").strip() or None,
        limit=safe_limit,
        offset=safe_offset,
    )
    return [_to_run_dto(row) for row in rows]


@execution_router.get("/runs/{run_id}", response_model=ExecutionRunDTO)
async def get_execution_run(run_id: str) -> ExecutionRunDTO:
    project = _active_project_or_400()
    db = await connection.get_connection()
    repo = get_execution_repository(db)
    row = _assert_run_project(await repo.get_run(run_id), project.id, run_id)
    return _to_run_dto(row)


@execution_router.get("/runs/{run_id}/events", response_model=ExecutionRunEventPageDTO)
async def list_execution_run_events(
    run_id: str,
    after_sequence: int = 0,
    limit: int = 200,
) -> ExecutionRunEventPageDTO:
    project = _active_project_or_400()
    safe_after = max(0, int(after_sequence or 0))
    safe_limit = min(1000, max(1, int(limit or 200)))
    db = await connection.get_connection()
    repo = get_execution_repository(db)
    _assert_run_project(await repo.get_run(run_id), project.id, run_id)
    rows = await repo.list_events_after_sequence(
        run_id,
        after_sequence=safe_after,
        limit=safe_limit,
    )
    items = [_to_event_dto(row) for row in rows]
    next_sequence = max([safe_after, *[item.sequenceNo for item in items]])
    return ExecutionRunEventPageDTO(runId=run_id, items=items, nextSequence=next_sequence)


@execution_router.post("/runs/{run_id}/approve", response_model=ExecutionRunDTO)
async def approve_execution_run(run_id: str, req: ExecutionApprovalRequest) -> ExecutionRunDTO:
    project = _active_project_or_400()
    db = await connection.get_connection()
    repo = get_execution_repository(db)
    row = _assert_run_project(await repo.get_run(run_id), project.id, run_id)

    if not bool(row.get("requires_approval")):
        raise HTTPException(status_code=400, detail="Run does not require approval")

    approval = await repo.resolve_approval(
        run_id,
        decision=req.decision,
        reason=req.reason,
        resolved_by=req.actor,
    )
    if approval is None:
        raise HTTPException(status_code=400, detail="No pending approval for this run")

    now = _now_iso()
    if req.decision == "denied":
        row = await repo.update_run(
            run_id,
            {
                "status": "blocked",
                "updated_at": now,
            },
        )
        await repo.append_run_events(
            run_id,
            [
                {
                    "stream": "system",
                    "event_type": "approval",
                    "payload_text": "Run approval denied.",
                    "payload_json": {"approval": _to_approval_dto(approval).model_dump()},
                    "occurred_at": now,
                }
            ],
        )
        return _to_run_dto(_assert_run_project(row, project.id, run_id))

    policy = evaluate_execution_policy(
        command=str(row.get("source_command") or ""),
        workspace_root=_workspace_root(project),
        cwd=str(row.get("cwd") or "."),
        env_profile=str(row.get("env_profile") or "default"),
    )
    if policy.verdict == "deny":
        row = await repo.update_run(
            run_id,
            {
                "status": "blocked",
                "policy_verdict": "deny",
                "updated_at": now,
            },
        )
        await repo.append_run_events(
            run_id,
            [
                {
                    "stream": "system",
                    "event_type": "policy",
                    "payload_text": "Approval accepted, but policy now denies execution.",
                    "payload_json": {"reasonCodes": policy.reason_codes},
                    "occurred_at": now,
                }
            ],
        )
        return _to_run_dto(_assert_run_project(row, project.id, run_id))

    row = await repo.update_run(
        run_id,
        {
            "approved_by": req.actor,
            "approved_at": now,
            "status": "queued",
            "updated_at": now,
        },
    )
    await repo.append_run_events(
        run_id,
        [
            {
                "stream": "system",
                "event_type": "approval",
                "payload_text": "Run approved.",
                "payload_json": {"approval": _to_approval_dto(approval).model_dump()},
                "occurred_at": now,
            }
        ],
    )
    await _queue_runtime_start(
        db=db,
        run_row=_assert_run_project(row, project.id, run_id),
        command_tokens=policy.command_tokens,
        project_root=str(_workspace_root(project)),
    )
    latest = _assert_run_project(await repo.get_run(run_id), project.id, run_id)
    return _to_run_dto(latest)


@execution_router.post("/runs/{run_id}/cancel", response_model=ExecutionRunDTO)
async def cancel_execution_run(run_id: str, req: ExecutionCancelRequest) -> ExecutionRunDTO:
    project = _active_project_or_400()
    db = await connection.get_connection()
    repo = get_execution_repository(db)
    row = _assert_run_project(await repo.get_run(run_id), project.id, run_id)
    if str(row.get("status") or "") not in {"queued", "running"}:
        return _to_run_dto(row)

    runtime = get_execution_runtime()
    await runtime.cancel_run(db=db, run_id=run_id, reason=req.reason)
    updated = await repo.update_run(
        run_id,
        {
            "status": "canceled",
            "ended_at": _now_iso(),
            "updated_at": _now_iso(),
        },
    )
    return _to_run_dto(_assert_run_project(updated, project.id, run_id))


@execution_router.post("/runs/{run_id}/retry", response_model=ExecutionRunDTO)
async def retry_execution_run(run_id: str, req: ExecutionRetryRequest) -> ExecutionRunDTO:
    project = _active_project_or_400()
    db = await connection.get_connection()
    repo = get_execution_repository(db)
    row = _assert_run_project(await repo.get_run(run_id), project.id, run_id)
    status = str(row.get("status") or "")
    if status not in {"failed", "canceled", "blocked"}:
        raise HTTPException(status_code=400, detail=f"Run with status '{status}' cannot be retried")
    if status == "failed" and not req.acknowledgeFailure:
        raise HTTPException(status_code=400, detail="Retry requires acknowledgeFailure=true for failed runs")

    metadata = row.get("metadata_json", {}) if isinstance(row.get("metadata_json"), dict) else {}
    merged_metadata = dict(metadata)
    merged_metadata.update(req.metadata or {})
    merged_metadata["retryOfRunId"] = run_id

    retry_request = ExecutionRunCreateRequest(
        command=str(row.get("source_command") or ""),
        cwd=str(row.get("cwd") or "."),
        envProfile=str(row.get("env_profile") or "default"),
        featureId=str(row.get("feature_id") or ""),
        recommendationRuleId=str(row.get("recommendation_rule_id") or ""),
        metadata=merged_metadata,
    )
    created = await _create_execution_run(
        db=db,
        project=project,
        req=retry_request,
        retry_of_run_id=run_id,
    )
    return _to_run_dto(created)
