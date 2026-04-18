"""Launch preparation application service (PCP-503).

Assembles a LaunchPreparationDTO for a given plan batch and initiates
plan-driven execution runs, bridging PhaseOperationsDTO, worktree contexts,
and provider capability metadata.

Does NOT duplicate execution policy, command normalization, or runtime start.
Delegates to ExecutionApplicationService.create_run for actual run creation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.application.services.common import require_project
from backend.application.services.execution import ExecutionApplicationService
from backend.application.services.agent_queries import PlanningQueryService
from backend.models import (
    ExecutionRunCreateRequest,
    LaunchApprovalRequirementDTO,
    LaunchBatchSummaryDTO,
    LaunchBatchTaskSummary,
    LaunchPreparationDTO,
    LaunchPreparationRequest,
    LaunchStartRequest,
    LaunchStartResponse,
    LaunchWorktreeSelectionDTO,
    WorktreeContextDTO,
)
from backend.services.launch_providers import default_provider_catalog, resolve_provider


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _worktree_row_to_dto(row: dict[str, Any]) -> WorktreeContextDTO:
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


class LaunchPreparationApplicationService:
    def __init__(
        self,
        *,
        planning_service: PlanningQueryService | None = None,
        execution_service: ExecutionApplicationService | None = None,
    ) -> None:
        self._planning = planning_service or PlanningQueryService()
        self._execution = execution_service or ExecutionApplicationService()

    async def prepare(
        self,
        context: RequestContext,
        ports: CorePorts,
        req: LaunchPreparationRequest,
    ) -> LaunchPreparationDTO:
        project = require_project(context, ports)
        phase_ops = await self._planning.get_phase_operations(
            context,
            ports,
            feature_id=req.featureId,
            phase_number=req.phaseNumber,
            project_id_override=req.projectId,
        )
        if phase_ops.status == "error" and not phase_ops.phase_token:
            raise HTTPException(
                status_code=404,
                detail=f"Phase {req.phaseNumber} not found for feature '{req.featureId}'",
            )

        batch = self._build_batch_summary(req.batchId, phase_ops)

        providers = default_provider_catalog()
        selected_provider = resolve_provider(providers, req.providerPreference)
        selected_model = req.modelPreference or selected_provider.defaultModel

        worktree_repo = ports.storage.worktree_contexts()
        worktree_rows = await worktree_repo.list(
            project.id,
            feature_id=req.featureId,
            phase_number=req.phaseNumber,
            batch_id=req.batchId,
            limit=20,
            offset=0,
        )
        candidates = [_worktree_row_to_dto(row) for row in worktree_rows]

        worktree_selection = LaunchWorktreeSelectionDTO()
        if req.worktreeContextId:
            match = next(
                (c for c in candidates if c.id == req.worktreeContextId),
                None,
            )
            if match is None:
                other_row = await worktree_repo.get_by_id(req.worktreeContextId)
                if other_row and str(other_row.get("project_id") or "") == project.id:
                    match = _worktree_row_to_dto(other_row)
                    candidates.append(match)
            if match is not None:
                worktree_selection = LaunchWorktreeSelectionDTO(
                    worktreeContextId=match.id,
                    branch=match.branch,
                    worktreePath=match.worktreePath,
                    baseBranch=match.baseBranch,
                    notes=match.notes,
                )
        elif candidates:
            primary = candidates[0]
            worktree_selection = LaunchWorktreeSelectionDTO(
                worktreeContextId=primary.id,
                branch=primary.branch,
                worktreePath=primary.worktreePath,
                baseBranch=primary.baseBranch,
                notes=primary.notes,
            )
        else:
            worktree_selection = LaunchWorktreeSelectionDTO(createIfMissing=True)

        approval = self._derive_approval(batch, selected_provider)
        warnings: list[str] = []
        if not selected_provider.supported:
            warnings.append(
                f"Provider '{selected_provider.provider}' is not supported in this environment."
            )
        if not batch.isReady:
            warnings.append(
                f"Batch '{batch.batchId}' is not ready: {batch.blockedReason or batch.readinessState}."
            )

        return LaunchPreparationDTO(
            projectId=project.id,
            featureId=req.featureId,
            phaseNumber=req.phaseNumber,
            batchId=req.batchId,
            batch=batch,
            providers=providers,
            selectedProvider=selected_provider.provider,
            selectedModel=selected_model,
            worktreeCandidates=candidates,
            worktreeSelection=worktree_selection,
            approval=approval,
            warnings=warnings,
            generatedAt=_now_iso(),
        )

    async def start(
        self,
        context: RequestContext,
        ports: CorePorts,
        req: LaunchStartRequest,
    ) -> LaunchStartResponse:
        project = require_project(context, ports)
        phase_ops = await self._planning.get_phase_operations(
            context,
            ports,
            feature_id=req.featureId,
            phase_number=req.phaseNumber,
            project_id_override=req.projectId,
        )
        if phase_ops.status == "error" and not phase_ops.phase_token:
            raise HTTPException(
                status_code=404,
                detail=f"Phase {req.phaseNumber} not found for feature '{req.featureId}'",
            )

        batch = self._build_batch_summary(req.batchId, phase_ops)
        if not batch.isReady and req.approvalDecision != "approved":
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Batch '{req.batchId}' is not ready "
                    f"({batch.blockedReason or batch.readinessState}). "
                    "Explicit approvalDecision='approved' required to override."
                ),
            )

        providers = default_provider_catalog()
        selected_provider = resolve_provider(providers, req.provider)
        if not selected_provider.supported:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Provider '{selected_provider.provider}' is not supported "
                    "in this environment."
                ),
            )

        worktree_repo = ports.storage.worktree_contexts()
        worktree_context_id = (req.worktree.worktreeContextId or "").strip()
        worktree_row: dict[str, Any] | None = None
        if worktree_context_id:
            worktree_row = await worktree_repo.get_by_id(worktree_context_id)
            if worktree_row is None or str(worktree_row.get("project_id") or "") != project.id:
                raise HTTPException(
                    status_code=404,
                    detail=f"Worktree context '{worktree_context_id}' not found",
                )
        elif req.worktree.createIfMissing:
            worktree_row = await worktree_repo.create(
                {
                    "id": uuid4().hex,
                    "project_id": project.id,
                    "feature_id": req.featureId,
                    "phase_number": req.phaseNumber,
                    "batch_id": req.batchId,
                    "branch": req.worktree.branch,
                    "worktree_path": req.worktree.worktreePath,
                    "base_branch": req.worktree.baseBranch,
                    "status": "ready",
                    "provider": selected_provider.provider,
                    "notes": req.worktree.notes,
                    "metadata_json": {},
                    "created_by": req.actor or "user",
                }
            )
            worktree_context_id = str(worktree_row.get("id") or "")

        command = self._compose_command(req, batch, selected_provider)
        execution_req = ExecutionRunCreateRequest(
            command=command,
            cwd=req.worktree.worktreePath or ".",
            envProfile=req.envProfile or "default",
            featureId=req.featureId,
            metadata={
                "launch": {
                    "provider": selected_provider.provider,
                    "model": req.model,
                    "batchId": req.batchId,
                    "phaseNumber": req.phaseNumber,
                    "worktreeContextId": worktree_context_id,
                    "approvalDecision": req.approvalDecision or "none",
                    **(req.metadata or {}),
                }
            },
        )
        run_row = await self._execution.create_run(context, ports, execution_req)
        run_id = str(run_row.get("id") or "")

        if worktree_row is not None and run_id:
            await worktree_repo.update(
                str(worktree_row.get("id")),
                {"last_run_id": run_id, "status": "in_use"},
            )

        warnings: list[str] = []
        if not batch.isReady:
            warnings.append(f"Launched against non-ready batch '{batch.batchId}' with operator override.")

        return LaunchStartResponse(
            runId=run_id,
            worktreeContextId=worktree_context_id,
            status=str(run_row.get("status") or "queued"),
            requiresApproval=bool(run_row.get("requires_approval")),
            warnings=warnings,
        )

    # ── Helpers ───────────────────────────────────────────────

    def _build_batch_summary(
        self,
        batch_id: str,
        phase_ops: Any,
    ) -> LaunchBatchSummaryDTO:
        task_by_id = {t.task_id: t for t in phase_ops.tasks or []}
        target_batch = None
        for entry in phase_ops.phase_batches or []:
            entry_id = str(entry.get("id") or entry.get("batch_id") or "")
            if entry_id == batch_id:
                target_batch = entry
                break
        if target_batch is None:
            raise HTTPException(
                status_code=404,
                detail=f"Batch '{batch_id}' not found in phase {phase_ops.phase_number}",
            )

        task_ids = list(target_batch.get("task_ids") or target_batch.get("tasks") or [])
        tasks = []
        owners: set[str] = set()
        for task_id in task_ids:
            task = task_by_id.get(task_id)
            if task is None:
                tasks.append(LaunchBatchTaskSummary(taskId=task_id))
                continue
            owners.update(task.assignees or [])
            tasks.append(
                LaunchBatchTaskSummary(
                    taskId=task.task_id,
                    title=task.title,
                    status=task.status,
                    assignees=list(task.assignees or []),
                    blockers=list(task.blockers or []),
                )
            )

        is_ready = bool(target_batch.get("is_ready", False))
        readiness_raw = str(target_batch.get("readiness_state") or "").lower()
        if readiness_raw in {"ready", "blocked", "partial", "unknown"}:
            readiness_state = readiness_raw
        elif is_ready:
            readiness_state = "ready"
        elif batch_id in (phase_ops.blocked_batch_ids or []):
            readiness_state = "blocked"
        else:
            readiness_state = "unknown"

        blocked_reason = str(target_batch.get("blocked_reason") or "")

        return LaunchBatchSummaryDTO(
            batchId=batch_id,
            phaseNumber=phase_ops.phase_number,
            featureId=phase_ops.feature_id,
            featureName=getattr(phase_ops, "feature_name", "") or "",
            phaseTitle=phase_ops.phase_title,
            readinessState=readiness_state,
            isReady=is_ready,
            blockedReason=blocked_reason,
            taskIds=task_ids,
            tasks=tasks,
            owners=sorted(owners),
            dependencies=list(target_batch.get("dependencies") or []),
        )

    def _derive_approval(
        self,
        batch: LaunchBatchSummaryDTO,
        provider: Any,
    ) -> LaunchApprovalRequirementDTO:
        requirement = "none"
        reasons: list[str] = []
        risk = "low"
        if provider.requiresApproval:
            requirement = "required"
            reasons.append("provider_requires_approval")
            risk = "medium"
        if not batch.isReady:
            requirement = "required"
            reasons.append("batch_not_ready")
            risk = "high"
        return LaunchApprovalRequirementDTO(
            requirement=requirement,
            reasonCodes=reasons,
            riskLevel=risk,
        )

    def _compose_command(
        self,
        req: LaunchStartRequest,
        batch: LaunchBatchSummaryDTO,
        provider: Any,
    ) -> str:
        if req.commandOverride and req.commandOverride.strip():
            return req.commandOverride.strip()
        # V1 local provider: emit a descriptive no-op echo; PCP-504 UI surfaces
        # this as a preview so operators can override. Real provider routing
        # happens via commandOverride or future provider-specific composers.
        task_list = ", ".join(batch.taskIds) or "(no tasks)"
        return (
            f"echo 'CCDash launch prep | feature={req.featureId} "
            f"phase={req.phaseNumber} batch={req.batchId} "
            f"provider={provider.provider} tasks=[{task_list}]'"
        )
