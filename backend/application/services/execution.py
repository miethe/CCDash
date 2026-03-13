"""Application services for execution run orchestration."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from backend import config
from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.application.services.common import require_project
from backend.models import (
    ExecutionApprovalRequest,
    ExecutionCancelRequest,
    ExecutionPolicyCheckRequest,
    ExecutionRetryRequest,
    ExecutionRunCreateRequest,
)
from backend.services.execution_policy import evaluate_execution_policy
from backend.services.execution_runtime import get_execution_runtime


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _workspace_root(project: Any) -> Path:
    base = str(getattr(project, "path", "") or config.CCDASH_PROJECT_ROOT).strip() or config.CCDASH_PROJECT_ROOT
    return Path(base).expanduser().resolve(strict=False)


def _assert_run_project(row: dict | None, project_id: str, run_id: str) -> dict[str, Any]:
    if not row or str(row.get("project_id") or "") != project_id:
        raise HTTPException(status_code=404, detail=f"Execution run '{run_id}' not found")
    return row


class ExecutionApplicationService:
    async def check_policy(
        self,
        context: RequestContext,
        ports: CorePorts,
        req: ExecutionPolicyCheckRequest,
    ) -> Any:
        project = require_project(context, ports)
        return evaluate_execution_policy(
            command=req.command,
            workspace_root=_workspace_root(project),
            cwd=req.cwd,
            env_profile=req.envProfile,
        )

    async def create_run(
        self,
        context: RequestContext,
        ports: CorePorts,
        req: ExecutionRunCreateRequest,
        *,
        retry_of_run_id: str = "",
    ) -> dict[str, Any]:
        project = require_project(context, ports)
        repo = ports.storage.execution()
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
                        "payload_json": {"approval": dict(approval or {})},
                        "occurred_at": _now_iso(),
                    }
                ],
            )
            return (await repo.get_run(run_id)) or run_row

        await self._queue_runtime_start(
            ports=ports,
            run_row=run_row,
            command_tokens=policy.command_tokens,
            project_root=str(_workspace_root(project)),
        )
        return (await repo.get_run(run_id)) or run_row

    async def list_runs(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        feature_id: str | None,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        project = require_project(context, ports)
        safe_limit = min(200, max(1, int(limit or 40)))
        safe_offset = max(0, int(offset or 0))
        return await ports.storage.execution().list_runs(
            project.id,
            feature_id=str(feature_id or "").strip() or None,
            limit=safe_limit,
            offset=safe_offset,
        )

    async def get_run(self, context: RequestContext, ports: CorePorts, run_id: str) -> dict[str, Any]:
        project = require_project(context, ports)
        row = await ports.storage.execution().get_run(run_id)
        return _assert_run_project(row, project.id, run_id)

    async def list_events(
        self,
        context: RequestContext,
        ports: CorePorts,
        run_id: str,
        *,
        after_sequence: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        project = require_project(context, ports)
        repo = ports.storage.execution()
        _assert_run_project(await repo.get_run(run_id), project.id, run_id)
        safe_after = max(0, int(after_sequence or 0))
        safe_limit = min(1000, max(1, int(limit or 200)))
        return await repo.list_events_after_sequence(
            run_id,
            after_sequence=safe_after,
            limit=safe_limit,
        )

    async def approve_run(
        self,
        context: RequestContext,
        ports: CorePorts,
        run_id: str,
        req: ExecutionApprovalRequest,
    ) -> dict[str, Any]:
        project = require_project(context, ports)
        repo = ports.storage.execution()
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
            updated = await repo.update_run(run_id, {"status": "blocked", "updated_at": now})
            await repo.append_run_events(
                run_id,
                [
                    {
                        "stream": "system",
                        "event_type": "approval",
                        "payload_text": "Run approval denied.",
                        "payload_json": {"approval": dict(approval)},
                        "occurred_at": now,
                    }
                ],
            )
            return _assert_run_project(updated, project.id, run_id)

        policy = evaluate_execution_policy(
            command=str(row.get("source_command") or ""),
            workspace_root=_workspace_root(project),
            cwd=str(row.get("cwd") or "."),
            env_profile=str(row.get("env_profile") or "default"),
        )
        if policy.verdict == "deny":
            updated = await repo.update_run(
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
            return _assert_run_project(updated, project.id, run_id)

        updated = await repo.update_run(
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
                    "payload_json": {"approval": dict(approval)},
                    "occurred_at": now,
                }
            ],
        )
        await self._queue_runtime_start(
            ports=ports,
            run_row=_assert_run_project(updated, project.id, run_id),
            command_tokens=policy.command_tokens,
            project_root=str(_workspace_root(project)),
        )
        latest = await repo.get_run(run_id)
        return _assert_run_project(latest, project.id, run_id)

    async def cancel_run(
        self,
        context: RequestContext,
        ports: CorePorts,
        run_id: str,
        req: ExecutionCancelRequest,
    ) -> dict[str, Any]:
        project = require_project(context, ports)
        repo = ports.storage.execution()
        row = _assert_run_project(await repo.get_run(run_id), project.id, run_id)
        if str(row.get("status") or "") not in {"queued", "running"}:
            return row

        await get_execution_runtime().cancel_run(db=ports.storage.db, run_id=run_id, reason=req.reason)
        updated = await repo.update_run(
            run_id,
            {
                "status": "canceled",
                "ended_at": _now_iso(),
                "updated_at": _now_iso(),
            },
        )
        return _assert_run_project(updated, project.id, run_id)

    async def retry_run(
        self,
        context: RequestContext,
        ports: CorePorts,
        run_id: str,
        req: ExecutionRetryRequest,
    ) -> dict[str, Any]:
        project = require_project(context, ports)
        repo = ports.storage.execution()
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
        return await self.create_run(
            context,
            ports,
            retry_request,
            retry_of_run_id=run_id,
        )

    async def _queue_runtime_start(
        self,
        *,
        ports: CorePorts,
        run_row: dict[str, Any],
        command_tokens: list[str],
        project_root: str,
    ) -> None:
        await get_execution_runtime().start_run(
            db=ports.storage.db,
            run_id=str(run_row.get("id") or ""),
            command_tokens=command_tokens,
            cwd=str(run_row.get("cwd") or ""),
            env_profile=str(run_row.get("env_profile") or "default"),
            project_root=project_root,
        )
