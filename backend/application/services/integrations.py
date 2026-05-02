"""Application services for integration orchestration."""
from __future__ import annotations

import asyncio
from typing import Any

from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.application.services.common import require_project, resolve_project
from backend.models import (
    SessionMemoryDraftGenerateRequest,
    SessionMemoryDraftPublishRequest,
    SessionMemoryDraftReviewRequest,
    SkillMeatConfigValidationRequest,
)
from backend.services.integrations.skillmeat_client import SkillMeatClient, SkillMeatClientError
from backend.services.integrations.skillmeat_memory_drafts import generate_session_memory_drafts
from backend.services.integrations.skillmeat_refresh import refresh_skillmeat_cache
from backend.services.integrations.skillmeat_sync import sync_skillmeat_definitions
from backend.services.stack_observations import backfill_session_stack_observations


class SkillMeatApplicationService:
    def _client_for_project(self, project: Any) -> SkillMeatClient:
        config = getattr(project, "skillMeat", None)
        if config is None or not bool(getattr(config, "enabled", False)):
            raise ValueError("SkillMeat integration is not enabled for this project")
        base_url = str(getattr(config, "baseUrl", "") or "").strip()
        project_mapping_id = str(getattr(config, "projectId", "") or "").strip()
        if not base_url or not project_mapping_id:
            raise ValueError("SkillMeat base URL and project ID are required for publish operations")
        return SkillMeatClient(
            base_url=base_url,
            timeout_seconds=float(getattr(config, "requestTimeoutSeconds", 5.0) or 5.0),
            aaa_enabled=bool(getattr(config, "aaaEnabled", False)),
            api_key=str(getattr(config, "apiKey", "") or ""),
        )

    async def validate_config(self, req: SkillMeatConfigValidationRequest) -> dict[str, Any]:
        base_url = str(req.baseUrl or "").strip()
        if not base_url:
            return {
                "baseUrl": {"state": "idle", "message": "Enter a SkillMeat base URL to run validation.", "httpStatus": None},
                "projectMapping": {
                    "state": "idle",
                    "message": "Project path validation is waiting for a base URL.",
                    "httpStatus": None,
                },
                "auth": {
                    "state": "idle",
                    "message": "Auth validation is waiting for a base URL.",
                    "httpStatus": None,
                },
            }

        client = SkillMeatClient(
            base_url=base_url,
            timeout_seconds=float(req.requestTimeoutSeconds or 5.0),
            aaa_enabled=bool(req.aaaEnabled),
            api_key=str(req.apiKey or ""),
        )

        try:
            await client.validate_base_url()
            base_status = {"state": "success", "message": "SkillMeat responded at the configured base URL.", "httpStatus": None}
        except SkillMeatClientError as exc:
            failure = {"state": "error", "message": exc.detail or str(exc), "httpStatus": exc.status_code}
            auth_status = failure if req.aaaEnabled else {
                "state": "idle",
                "message": "Enable AAA to validate credentials.",
                "httpStatus": None,
            }
            return {
                "baseUrl": failure,
                "projectMapping": {
                    "state": "idle",
                    "message": "Project ID validation is blocked until the base URL responds.",
                    "httpStatus": None,
                },
                "auth": auth_status,
            }

        if req.aaaEnabled:
            api_key = str(req.apiKey or "").strip()
            auth_status = (
                {"state": "success", "message": "The configured credential was accepted by SkillMeat.", "httpStatus": None}
                if api_key
                else {"state": "warning", "message": "AAA is enabled, but no API key is configured.", "httpStatus": None}
            )
        else:
            auth_status = {"state": "success", "message": "Local no-auth mode is active. No credential is required.", "httpStatus": None}

        configured_project_id = str(req.projectId or "").strip()
        if not configured_project_id:
            project_status = {"state": "warning", "message": "Set the SkillMeat project ID to validate project mapping.", "httpStatus": None}
        else:
            try:
                await client.get_project(configured_project_id)
                project_status = {"state": "success", "message": "SkillMeat resolved the configured project ID.", "httpStatus": None}
            except SkillMeatClientError as exc:
                project_status = {
                    "state": "warning" if exc.status_code == 404 else "error",
                    "message": exc.detail or str(exc),
                    "httpStatus": exc.status_code,
                }

        return {
            "baseUrl": base_status,
            "projectMapping": project_status,
            "auth": auth_status,
        }

    async def sync(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        requested_project_id: str | None = None,
    ) -> dict[str, Any]:
        project = require_project(context, ports, requested_project_id=requested_project_id)
        return await sync_skillmeat_definitions(ports.storage.db, project)

    async def refresh(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        requested_project_id: str | None = None,
    ) -> dict[str, Any]:
        project = require_project(context, ports, requested_project_id=requested_project_id)
        return await refresh_skillmeat_cache(
            ports.storage.db,
            project,
            force_observation_recompute=True,
        )

    async def list_definitions(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        definition_type: str | None,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        project = require_project(context, ports)
        return await ports.storage.agentic_intelligence().list_external_definitions(
            str(project.id),
            definition_type=definition_type,
            limit=limit,
            offset=offset,
        )

    async def backfill_observations(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        requested_project_id: str | None,
        limit: int,
        force_recompute: bool,
    ) -> dict[str, Any]:
        project = require_project(context, ports, requested_project_id=requested_project_id)
        return await backfill_session_stack_observations(
            ports.storage.db,
            project,
            limit=limit,
            force_recompute=force_recompute,
        )

    async def list_observations(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        project = resolve_project(context, ports)
        if project is None:
            return []

        repo = ports.storage.agentic_intelligence()
        rows = await repo.list_stack_observations(str(project.id), limit=limit, offset=offset)
        if not rows:
            return []
        observations = await asyncio.gather(
            *[
                repo.get_stack_observation(str(project.id), str(row.get("session_id") or ""))
                for row in rows
            ]
        )
        return [obs for obs in observations if obs]

    async def list_memory_drafts(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        requested_project_id: str | None,
        session_id: str | None,
        status: str | None,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        project = require_project(context, ports, requested_project_id=requested_project_id)
        repo = ports.storage.agentic_intelligence()
        normalized_session_id = str(session_id or "").strip() or None
        normalized_status = str(status or "").strip() or None
        rows = await repo.list_session_memory_drafts(
            str(project.id),
            session_id=normalized_session_id,
            status=normalized_status,
            limit=limit,
            offset=offset,
        )
        total = await repo.count_session_memory_drafts(
            str(project.id),
            session_id=normalized_session_id,
            status=normalized_status,
        )
        return {
            "generatedAt": "",
            "total": total,
            "offset": offset,
            "limit": limit,
            "items": rows,
        }

    async def generate_memory_drafts(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        requested_project_id: str | None,
        req: SessionMemoryDraftGenerateRequest,
    ) -> dict[str, Any]:
        project = require_project(context, ports, requested_project_id=requested_project_id)
        return await generate_session_memory_drafts(
            context,
            ports,
            project=project,
            session_id=req.sessionId,
            limit=req.limit,
            actor=req.actor,
        )

    async def review_memory_draft(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        requested_project_id: str | None,
        draft_id: int,
        req: SessionMemoryDraftReviewRequest,
    ) -> dict[str, Any] | None:
        project = require_project(context, ports, requested_project_id=requested_project_id)
        return await ports.storage.agentic_intelligence().review_session_memory_draft(
            str(project.id),
            draft_id,
            decision=req.decision,
            actor=req.actor,
            notes=req.notes,
        )

    async def publish_memory_draft(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        requested_project_id: str | None,
        draft_id: int,
        req: SessionMemoryDraftPublishRequest,
    ) -> dict[str, Any] | None:
        project = require_project(context, ports, requested_project_id=requested_project_id)
        repo = ports.storage.agentic_intelligence()
        draft = await repo.get_session_memory_draft(str(project.id), draft_id)
        if draft is None:
            return None
        if str(draft.get("status") or "") != "approved":
            raise ValueError("Only approved memory drafts can be published")

        project_config = getattr(project, "skillMeat", None)
        project_mapping_id = str(getattr(project_config, "projectId", "") or "").strip()
        client = self._client_for_project(project)
        modules = await client.list_context_modules(project_id=project_mapping_id)

        module_name = str(draft.get("module_name") or "")
        module = next((item for item in modules if str(item.get("name") or "") == module_name), None)
        if module is None:
            module = await client.create_context_module(
                project_id=project_mapping_id,
                name=module_name,
                description=str(draft.get("module_description") or ""),
            )

        memory_payload = await client.add_context_module_memory(
            str(module.get("id") or ""),
            memory_type=str(draft.get("memory_type") or "learning"),
            title=str(draft.get("title") or ""),
            content=str(draft.get("content") or ""),
            confidence=float(draft.get("confidence") or 0.0),
            metadata={
                "ccdashProjectId": str(project.id),
                "sessionId": str(draft.get("session_id") or ""),
                "featureId": str(draft.get("feature_id") or ""),
                "workflowRef": str(draft.get("workflow_ref") or ""),
                "sourceMessageId": str(draft.get("source_message_id") or ""),
                "sourceLogId": str(draft.get("source_log_id") or ""),
                "contentHash": str(draft.get("content_hash") or ""),
                "evidence": draft.get("evidence_json") if isinstance(draft.get("evidence_json"), dict) else {},
            },
        )
        return await repo.record_session_memory_draft_publish_attempt(
            str(project.id),
            draft_id,
            actor=req.actor,
            notes=req.notes,
            module_id=str(module.get("id") or ""),
            memory_id=str(memory_payload.get("id") or ""),
            source_url=str(memory_payload.get("source_url") or memory_payload.get("url") or ""),
        )
