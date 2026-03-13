"""Application services for integration orchestration."""
from __future__ import annotations

from typing import Any

from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.application.services.common import require_project, resolve_project
from backend.models import SkillMeatConfigValidationRequest
from backend.services.integrations.skillmeat_client import SkillMeatClient, SkillMeatClientError
from backend.services.integrations.skillmeat_refresh import refresh_skillmeat_cache
from backend.services.integrations.skillmeat_sync import sync_skillmeat_definitions
from backend.services.stack_observations import backfill_session_stack_observations


class SkillMeatApplicationService:
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
        hydrated: list[dict[str, Any]] = []
        for row in rows:
            observation = await repo.get_stack_observation(str(project.id), str(row.get("session_id") or ""))
            if observation:
                hydrated.append(observation)
        return hydrated
