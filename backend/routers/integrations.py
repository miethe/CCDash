"""Integration endpoints for SkillMeat sync, cache access, and observation backfill."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend.db import connection
from backend.db.factory import get_agentic_intelligence_repository
from backend.models import (
    SessionStackComponent,
    SessionStackObservation,
    SkillMeatConfigValidationRequest,
    SkillMeatConfigValidationResponse,
    SkillMeatDefinition,
    SkillMeatRefreshResponse,
    SkillMeatDefinitionSource,
    SkillMeatFeatureFlags,
    SkillMeatProbeResult,
    SkillMeatDefinitionSyncResponse,
    SkillMeatObservationBackfillRequest,
    SkillMeatObservationBackfillResponse,
    SkillMeatProjectConfig,
    SkillMeatSyncRequest,
    SkillMeatSyncWarning,
)
from backend.project_manager import project_manager
from backend.services.agentic_intelligence_flags import require_skillmeat_integration_enabled
from backend.services.integrations.skillmeat_client import SkillMeatClient, SkillMeatClientError
from backend.services.integrations.skillmeat_refresh import refresh_skillmeat_cache
from backend.services.integrations.skillmeat_sync import sync_skillmeat_definitions
from backend.services.stack_observations import backfill_session_stack_observations


integrations_router = APIRouter(prefix="/api/integrations/skillmeat", tags=["integrations"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _active_project_or_400() -> Any:
    project = project_manager.get_active_project()
    if not project:
        raise HTTPException(status_code=400, detail="No active project")
    return project


def _project_for_request_or_active(project_id: str | None = None) -> Any:
    requested_project_id = str(project_id or "").strip()
    if requested_project_id:
        project = project_manager.get_project(requested_project_id)
        if not project:
            raise HTTPException(status_code=404, detail=f"Project '{requested_project_id}' not found")
        return project
    return _active_project_or_400()


def _to_source_dto(row: dict[str, Any], project_config: SkillMeatProjectConfig | None = None) -> SkillMeatDefinitionSource:
    config = project_config or SkillMeatProjectConfig()
    return SkillMeatDefinitionSource(
        id=int(row.get("id")) if row.get("id") is not None else None,
        projectId=str(row.get("project_id") or ""),
        sourceKind=str(row.get("source_kind") or "skillmeat"),
        enabled=bool(row.get("enabled")),
        baseUrl=str(row.get("base_url") or getattr(config, "baseUrl", "")),
        projectMapping=row.get("project_mapping_json", {}) if isinstance(row.get("project_mapping_json"), dict) else {},
        featureFlags=SkillMeatFeatureFlags(**(row.get("feature_flags_json", {}) if isinstance(row.get("feature_flags_json"), dict) else {})),
        lastSyncedAt=str(row.get("last_synced_at") or ""),
        lastSyncStatus=str(row.get("last_sync_status") or "never"),
        lastSyncError=str(row.get("last_sync_error") or ""),
        createdAt=str(row.get("created_at") or ""),
        updatedAt=str(row.get("updated_at") or ""),
    )


def _to_definition_dto(row: dict[str, Any]) -> SkillMeatDefinition:
    return SkillMeatDefinition(
        id=int(row.get("id")) if row.get("id") is not None else None,
        projectId=str(row.get("project_id") or ""),
        sourceId=int(row.get("source_id")) if row.get("source_id") is not None else None,
        definitionType=str(row.get("definition_type") or ""),
        externalId=str(row.get("external_id") or ""),
        displayName=str(row.get("display_name") or ""),
        version=str(row.get("version") or ""),
        sourceUrl=str(row.get("source_url") or ""),
        resolutionMetadata=row.get("resolution_metadata_json", {}) if isinstance(row.get("resolution_metadata_json"), dict) else {},
        rawSnapshot=row.get("raw_snapshot_json", {}) if isinstance(row.get("raw_snapshot_json"), dict) else {},
        fetchedAt=str(row.get("fetched_at") or ""),
        createdAt=str(row.get("created_at") or ""),
        updatedAt=str(row.get("updated_at") or ""),
    )


def _to_component_dto(row: dict[str, Any]) -> SessionStackComponent:
    return SessionStackComponent(
        id=int(row.get("id")) if row.get("id") is not None else None,
        observationId=int(row.get("observation_id")) if row.get("observation_id") is not None else None,
        projectId=str(row.get("project_id") or ""),
        componentType=str(row.get("component_type") or ""),
        componentKey=str(row.get("component_key") or ""),
        status=str(row.get("status") or "explicit"),
        confidence=float(row.get("confidence") or 0.0),
        externalDefinitionId=int(row.get("external_definition_id")) if row.get("external_definition_id") is not None else None,
        externalDefinitionType=str(row.get("external_definition_type") or ""),
        externalDefinitionExternalId=str(row.get("external_definition_external_id") or ""),
        sourceAttribution=str(row.get("source_attribution") or ""),
        payload=row.get("component_payload_json", {}) if isinstance(row.get("component_payload_json"), dict) else {},
        createdAt=str(row.get("created_at") or ""),
        updatedAt=str(row.get("updated_at") or ""),
    )


def _to_observation_dto(row: dict[str, Any]) -> SessionStackObservation:
    components = row.get("components", [])
    return SessionStackObservation(
        id=int(row.get("id")) if row.get("id") is not None else None,
        projectId=str(row.get("project_id") or ""),
        sessionId=str(row.get("session_id") or ""),
        featureId=str(row.get("feature_id") or ""),
        workflowRef=str(row.get("workflow_ref") or ""),
        confidence=float(row.get("confidence") or 0.0),
        source=str(row.get("observation_source") or "backfill"),
        evidence=row.get("evidence_json", {}) if isinstance(row.get("evidence_json"), dict) else {},
        components=[_to_component_dto(component) for component in components if isinstance(component, dict)],
        createdAt=str(row.get("created_at") or ""),
        updatedAt=str(row.get("updated_at") or ""),
    )


def _probe_result(state: str, message: str, *, http_status: int | None = None) -> SkillMeatProbeResult:
    return SkillMeatProbeResult(
        state=state,
        message=message,
        checkedAt=_now_iso(),
        httpStatus=http_status,
    )


@integrations_router.post("/validate-config", response_model=SkillMeatConfigValidationResponse)
async def validate_skillmeat_config(req: SkillMeatConfigValidationRequest):
    require_skillmeat_integration_enabled()
    base_url = str(req.baseUrl or "").strip()
    if not base_url:
        idle = _probe_result("idle", "Enter a SkillMeat base URL to run validation.")
        return SkillMeatConfigValidationResponse(
            baseUrl=idle,
            projectMapping=_probe_result("idle", "Project path validation is waiting for a base URL."),
            auth=_probe_result("idle", "Auth validation is waiting for a base URL."),
        )

    client = SkillMeatClient(
        base_url=base_url,
        timeout_seconds=float(req.requestTimeoutSeconds or 5.0),
        aaa_enabled=bool(req.aaaEnabled),
        api_key=str(req.apiKey or ""),
    )

    try:
        await client.validate_base_url()
        base_status = _probe_result("success", "SkillMeat responded at the configured base URL.")
    except SkillMeatClientError as exc:
        failure = _probe_result(
            "error",
            exc.detail or str(exc),
            http_status=exc.status_code,
        )
        auth_status = failure if req.aaaEnabled else _probe_result("idle", "Enable AAA to validate credentials.")
        return SkillMeatConfigValidationResponse(
            baseUrl=failure,
            projectMapping=_probe_result("idle", "Project ID validation is blocked until the base URL responds."),
            auth=auth_status,
        )

    if req.aaaEnabled:
        api_key = str(req.apiKey or "").strip()
        if api_key:
            auth_status = _probe_result("success", "The configured credential was accepted by SkillMeat.")
        else:
            auth_status = _probe_result("warning", "AAA is enabled, but no API key is configured.")
    else:
        auth_status = _probe_result("success", "Local no-auth mode is active. No credential is required.")

    configured_project_id = str(req.projectId or "").strip()
    if not configured_project_id:
        project_status = _probe_result("warning", "Set the SkillMeat project ID to validate project mapping.")
    else:
        try:
            await client.get_project(configured_project_id)
            project_status = _probe_result("success", "SkillMeat resolved the configured project ID.")
        except SkillMeatClientError as exc:
            state = "warning" if exc.status_code == 404 else "error"
            project_status = _probe_result(
                state,
                exc.detail or str(exc),
                http_status=exc.status_code,
            )

    return SkillMeatConfigValidationResponse(
        baseUrl=base_status,
        projectMapping=project_status,
        auth=auth_status,
    )


@integrations_router.post("/sync", response_model=SkillMeatDefinitionSyncResponse)
async def sync_skillmeat(req: SkillMeatSyncRequest | None = None):
    require_skillmeat_integration_enabled()
    requested_project_id = str((req.projectId if req else "") or "").strip()
    project = _project_for_request_or_active(requested_project_id)

    db = await connection.get_connection()
    payload = await sync_skillmeat_definitions(db, project)
    source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    warnings = payload.get("warnings", [])
    return SkillMeatDefinitionSyncResponse(
        projectId=str(payload.get("projectId") or project.id),
        source=_to_source_dto(source, getattr(project, "skillMeat", None)),
        totalDefinitions=int(payload.get("totalDefinitions") or 0),
        countsByType=payload.get("countsByType", {}) if isinstance(payload.get("countsByType"), dict) else {},
        fetchedAt=str(payload.get("fetchedAt") or ""),
        warnings=[SkillMeatSyncWarning(**warning) for warning in warnings if isinstance(warning, dict)],
    )


@integrations_router.post("/refresh", response_model=SkillMeatRefreshResponse)
async def refresh_skillmeat(req: SkillMeatSyncRequest | None = None):
    require_skillmeat_integration_enabled()
    requested_project_id = str((req.projectId if req else "") or "").strip()
    project = _project_for_request_or_active(requested_project_id)

    db = await connection.get_connection()
    payload = await refresh_skillmeat_cache(
        db,
        project,
        force_observation_recompute=True,
    )
    sync_payload = payload.get("sync") if isinstance(payload, dict) else {}
    if not isinstance(sync_payload, dict):
        sync_payload = {}
    backfill_payload = payload.get("backfill") if isinstance(payload, dict) else None
    if not isinstance(backfill_payload, dict):
        backfill_payload = None

    source = sync_payload.get("source") if isinstance(sync_payload.get("source"), dict) else {}
    sync_warnings = sync_payload.get("warnings", [])
    sync_response = SkillMeatDefinitionSyncResponse(
        projectId=str(sync_payload.get("projectId") or project.id),
        source=_to_source_dto(source, getattr(project, "skillMeat", None)),
        totalDefinitions=int(sync_payload.get("totalDefinitions") or 0),
        countsByType=sync_payload.get("countsByType", {}) if isinstance(sync_payload.get("countsByType"), dict) else {},
        fetchedAt=str(sync_payload.get("fetchedAt") or ""),
        warnings=[SkillMeatSyncWarning(**warning) for warning in sync_warnings if isinstance(warning, dict)],
    )
    backfill_response = None
    if backfill_payload is not None:
        backfill_response = SkillMeatObservationBackfillResponse(
            projectId=str(backfill_payload.get("projectId") or project.id),
            sessionsProcessed=int(backfill_payload.get("sessionsProcessed") or 0),
            observationsStored=int(backfill_payload.get("observationsStored") or 0),
            skippedSessions=int(backfill_payload.get("skippedSessions") or 0),
            resolvedComponents=int(backfill_payload.get("resolvedComponents") or 0),
            unresolvedComponents=int(backfill_payload.get("unresolvedComponents") or 0),
            generatedAt=str(backfill_payload.get("generatedAt") or ""),
            warnings=[
                SkillMeatSyncWarning(**warning)
                for warning in backfill_payload.get("warnings", [])
                if isinstance(warning, dict)
            ],
        )

    return SkillMeatRefreshResponse(
        projectId=str(project.id),
        sync=sync_response,
        backfill=backfill_response,
    )


@integrations_router.get("/definitions", response_model=list[SkillMeatDefinition])
async def list_skillmeat_definitions(
    definition_type: str | None = Query(default=None, alias="definitionType"),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
):
    require_skillmeat_integration_enabled()
    project = _active_project_or_400()
    db = await connection.get_connection()
    repo = get_agentic_intelligence_repository(db)
    rows = await repo.list_external_definitions(
        str(project.id),
        definition_type=definition_type,
        limit=limit,
        offset=offset,
    )
    return [_to_definition_dto(row) for row in rows]


@integrations_router.post("/observations/backfill", response_model=SkillMeatObservationBackfillResponse)
async def backfill_skillmeat_observations(req: SkillMeatObservationBackfillRequest):
    require_skillmeat_integration_enabled()
    project = _project_for_request_or_active(req.projectId)

    db = await connection.get_connection()
    payload = await backfill_session_stack_observations(
        db,
        project,
        limit=req.limit,
        force_recompute=req.forceRecompute,
    )
    warnings = payload.get("warnings", [])
    return SkillMeatObservationBackfillResponse(
        projectId=str(payload.get("projectId") or project.id),
        sessionsProcessed=int(payload.get("sessionsProcessed") or 0),
        observationsStored=int(payload.get("observationsStored") or 0),
        skippedSessions=int(payload.get("skippedSessions") or 0),
        resolvedComponents=int(payload.get("resolvedComponents") or 0),
        unresolvedComponents=int(payload.get("unresolvedComponents") or 0),
        generatedAt=str(payload.get("generatedAt") or ""),
        warnings=[SkillMeatSyncWarning(**warning) for warning in warnings if isinstance(warning, dict)],
    )


@integrations_router.get("/observations", response_model=list[SessionStackObservation])
async def list_skillmeat_observations(
    limit: int = Query(default=200, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
):
    require_skillmeat_integration_enabled()
    project = _active_project_or_400()
    db = await connection.get_connection()
    repo = get_agentic_intelligence_repository(db)
    rows = await repo.list_stack_observations(str(project.id), limit=limit, offset=offset)
    hydrated: list[SessionStackObservation] = []
    for row in rows:
        observation = await repo.get_stack_observation(str(project.id), str(row.get("session_id") or ""))
        if observation:
            hydrated.append(_to_observation_dto(observation))
    return hydrated
