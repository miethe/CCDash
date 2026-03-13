"""Integration endpoints for SkillMeat sync, cache access, and observation backfill."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from backend import config
from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.application.services import resolve_application_request
from backend.application.services.integrations import SkillMeatApplicationService
from backend.models import (
    GitHubCredentialValidationRequest,
    GitHubCredentialValidationResponse,
    GitHubIntegrationSettings,
    GitHubIntegrationSettingsResponse,
    GitHubIntegrationSettingsUpdateRequest,
    GitHubPathValidationRequest,
    GitHubPathValidationResponse,
    GitHubProbeResult,
    GitHubWorkspaceRefreshRequest,
    GitHubWorkspaceRefreshResponse,
    GitHubWriteCapabilityRequest,
    GitHubWriteCapabilityResponse,
    Project,
    ProjectPathReference,
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
from backend.request_scope import get_core_ports, get_request_context
from backend.services.agentic_intelligence_flags import require_skillmeat_integration_enabled
from backend.services.integrations.github_settings_store import GitHubSettingsStore
from backend.services.project_paths.providers.base import PathResolutionError
from backend.services.project_paths.providers.filesystem import FilesystemProjectPathProvider
from backend.services.project_paths.resolver import _normalize_relative_path
from backend.services.repo_workspaces.cache import RepoWorkspaceCache
from backend.services.repo_workspaces.manager import RepoWorkspaceManager, RepoWorkspaceError
from backend.services.integrations.skillmeat_client import SkillMeatClient, SkillMeatClientError


integrations_router = APIRouter(prefix="/api/integrations/skillmeat", tags=["integrations"])
github_integrations_router = APIRouter(prefix="/api/integrations/github", tags=["integrations"])
github_settings_store = GitHubSettingsStore()
skillmeat_application_service = SkillMeatApplicationService()


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


def _github_probe(state: str, message: str, *, path: str = "") -> GitHubProbeResult:
    return GitHubProbeResult(
        state=state,
        message=message,
        checkedAt=_now_iso(),
        path=path,
    )


def _github_settings_from_request(
    request_settings: GitHubIntegrationSettingsUpdateRequest | None = None,
) -> GitHubIntegrationSettings:
    current = github_settings_store.load()
    if request_settings is None:
        return current
    return GitHubIntegrationSettings(
        enabled=bool(request_settings.enabled),
        provider="github",
        baseUrl=str(request_settings.baseUrl or current.baseUrl or "https://github.com").strip() or "https://github.com",
        username=str(request_settings.username or current.username or "git").strip() or "git",
        token=str(request_settings.token or "").strip() or current.token,
        cacheRoot=str(request_settings.cacheRoot or current.cacheRoot or config.REPO_WORKSPACE_CACHE_DIR).strip(),
        writeEnabled=bool(request_settings.writeEnabled),
    )


def _workspace_manager_for_settings(settings: GitHubIntegrationSettings) -> RepoWorkspaceManager:
    cache_root = Path(settings.cacheRoot or config.REPO_WORKSPACE_CACHE_DIR).expanduser()
    return RepoWorkspaceManager(RepoWorkspaceCache(cache_root))


def _validation_project(project: Project | None = None) -> Project:
    if project is not None:
        return project
    return Project(
        id="validation",
        name="Validation",
        path=str(config.PROJECT_ROOT),
        planDocsPath="docs/project_plans/",
        sessionsPath=str(Path.home() / ".claude" / "sessions"),
        progressPath=".claude/progress",
    )


def _resolve_reference_with_settings(
    reference: ProjectPathReference,
    *,
    settings: GitHubIntegrationSettings,
    project: Project | None = None,
    root_reference: ProjectPathReference | None = None,
    refresh: bool = False,
) -> Path:
    project_model = _validation_project(project)
    if reference.sourceKind == "filesystem":
        provider = FilesystemProjectPathProvider()
        return provider.resolve(reference, project=project_model).path
    if reference.sourceKind == "github_repo":
        repo_ref = reference.repoRef
        if repo_ref is None:
            raise PathResolutionError("invalid_github_url", "GitHub references require repoRef.")
        workspace_root = _workspace_manager_for_settings(settings).ensure_workspace(repo_ref, settings, refresh=refresh)
        repo_subpath = str(repo_ref.repoSubpath or "").strip().strip("/")
        candidate = (workspace_root / repo_subpath).resolve(strict=False) if repo_subpath else workspace_root.resolve(strict=False)
        if repo_subpath and not candidate.exists():
            raise PathResolutionError("missing_subpath", f"Subpath '{repo_subpath}' was not found in the GitHub workspace.")
        return candidate
    if reference.sourceKind == "project_root":
        base_reference = root_reference or (project.pathConfig.root if project is not None else None)
        if base_reference is None:
            raise PathResolutionError("missing_root", "A project_root reference needs a root reference.")
        base_path = _resolve_reference_with_settings(
            base_reference,
            settings=settings,
            project=project_model,
            refresh=refresh,
        )
        relative_path = _normalize_relative_path(reference.relativePath)
        candidate = (base_path / relative_path).resolve(strict=False)
        try:
            candidate.relative_to(base_path.resolve(strict=False))
        except ValueError as exc:
            raise PathResolutionError("invalid_relative_path", "Resolved path escapes the project root.") from exc
        return candidate
    raise PathResolutionError("unsupported_source_kind", f"Unsupported source kind '{reference.sourceKind}'.")


@integrations_router.post("/validate-config", response_model=SkillMeatConfigValidationResponse)
async def validate_skillmeat_config(req: SkillMeatConfigValidationRequest):
    require_skillmeat_integration_enabled()
    payload = await skillmeat_application_service.validate_config(req)
    return SkillMeatConfigValidationResponse(
        baseUrl=_probe_result(
            str(payload["baseUrl"].get("state") or "idle"),
            str(payload["baseUrl"].get("message") or ""),
            http_status=payload["baseUrl"].get("httpStatus"),
        ),
        projectMapping=_probe_result(
            str(payload["projectMapping"].get("state") or "idle"),
            str(payload["projectMapping"].get("message") or ""),
            http_status=payload["projectMapping"].get("httpStatus"),
        ),
        auth=_probe_result(
            str(payload["auth"].get("state") or "idle"),
            str(payload["auth"].get("message") or ""),
            http_status=payload["auth"].get("httpStatus"),
        ),
    )


async def _resolve_skillmeat_request(
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


@integrations_router.post("/sync", response_model=SkillMeatDefinitionSyncResponse)
async def sync_skillmeat(
    req: SkillMeatSyncRequest | None = None,
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
):
    require_skillmeat_integration_enabled()
    requested_project_id = str((req.projectId if req else "") or "").strip() or None
    app_request = await _resolve_skillmeat_request(
        request_context,
        core_ports,
        requested_project_id=requested_project_id,
    )
    payload = await skillmeat_application_service.sync(
        app_request.context,
        app_request.ports,
        requested_project_id=requested_project_id,
    )
    source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    warnings = payload.get("warnings", [])
    project = app_request.project
    return SkillMeatDefinitionSyncResponse(
        projectId=str(payload.get("projectId") or project.id),
        source=_to_source_dto(source, getattr(project, "skillMeat", None)),
        totalDefinitions=int(payload.get("totalDefinitions") or 0),
        countsByType=payload.get("countsByType", {}) if isinstance(payload.get("countsByType"), dict) else {},
        fetchedAt=str(payload.get("fetchedAt") or ""),
        warnings=[SkillMeatSyncWarning(**warning) for warning in warnings if isinstance(warning, dict)],
    )


@integrations_router.post("/refresh", response_model=SkillMeatRefreshResponse)
async def refresh_skillmeat(
    req: SkillMeatSyncRequest | None = None,
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
):
    require_skillmeat_integration_enabled()
    requested_project_id = str((req.projectId if req else "") or "").strip() or None
    app_request = await _resolve_skillmeat_request(
        request_context,
        core_ports,
        requested_project_id=requested_project_id,
    )
    payload = await skillmeat_application_service.refresh(
        app_request.context,
        app_request.ports,
        requested_project_id=requested_project_id,
    )
    project = app_request.project
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
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
):
    require_skillmeat_integration_enabled()
    app_request = await _resolve_skillmeat_request(request_context, core_ports)
    rows = await skillmeat_application_service.list_definitions(
        app_request.context,
        app_request.ports,
        definition_type=definition_type,
        limit=limit,
        offset=offset,
    )
    return [_to_definition_dto(row) for row in rows]


@integrations_router.post("/observations/backfill", response_model=SkillMeatObservationBackfillResponse)
async def backfill_skillmeat_observations(
    req: SkillMeatObservationBackfillRequest,
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
):
    require_skillmeat_integration_enabled()
    app_request = await _resolve_skillmeat_request(
        request_context,
        core_ports,
        requested_project_id=req.projectId,
    )
    payload = await skillmeat_application_service.backfill_observations(
        app_request.context,
        app_request.ports,
        requested_project_id=req.projectId,
        limit=req.limit,
        force_recompute=req.forceRecompute,
    )
    warnings = payload.get("warnings", [])
    project = app_request.project
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
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
):
    require_skillmeat_integration_enabled()
    app_request = await _resolve_skillmeat_request(request_context, core_ports)
    rows = await skillmeat_application_service.list_observations(
        app_request.context,
        app_request.ports,
        limit=limit,
        offset=offset,
    )
    return [_to_observation_dto(row) for row in rows]


@github_integrations_router.get("/settings", response_model=GitHubIntegrationSettingsResponse)
async def get_github_settings():
    return github_settings_store.to_response()


@github_integrations_router.put("/settings", response_model=GitHubIntegrationSettingsResponse)
async def update_github_settings(req: GitHubIntegrationSettingsUpdateRequest):
    settings = github_settings_store.save(req)
    return github_settings_store.to_response(settings)


@github_integrations_router.post("/validate-credential", response_model=GitHubCredentialValidationResponse)
async def validate_github_credential(req: GitHubCredentialValidationRequest):
    settings = _github_settings_from_request(req.settings)
    if not settings.enabled:
        return GitHubCredentialValidationResponse(
            auth=_github_probe("warning", "GitHub integration is disabled."),
            repoAccess=_github_probe("idle", "Enable GitHub integration to validate repository access."),
        )

    auth = _github_probe(
        "success" if str(settings.token or "").strip() else "warning",
        "GitHub token configured for managed workspace operations."
        if str(settings.token or "").strip()
        else "No token configured. Public repositories can still be resolved.",
    )

    repo_access = _github_probe("idle", "No GitHub-backed project root selected for validation.")
    project = _project_for_request_or_active(req.projectId) if str(req.projectId or "").strip() else None
    root_reference = project.pathConfig.root if project is not None else None
    if root_reference is not None and root_reference.sourceKind == "github_repo":
        try:
            resolved = _resolve_reference_with_settings(
                root_reference,
                settings=settings,
                project=project,
                refresh=False,
            )
            repo_access = _github_probe("success", "Repository access validated via managed workspace bootstrap.", path=str(resolved))
        except PathResolutionError as exc:
            state = "warning" if exc.code in {"auth_failure", "missing_branch"} else "error"
            repo_access = _github_probe(state, exc.message)
        except RepoWorkspaceError as exc:
            state = "warning" if exc.code in {"auth_failure", "missing_branch"} else "error"
            repo_access = _github_probe(state, exc.detail)

    return GitHubCredentialValidationResponse(auth=auth, repoAccess=repo_access)


@github_integrations_router.post("/validate-path", response_model=GitHubPathValidationResponse)
async def validate_github_path(req: GitHubPathValidationRequest):
    settings = github_settings_store.load()
    project = _project_for_request_or_active(req.projectId) if str(req.projectId or "").strip() else None
    try:
        resolved = _resolve_reference_with_settings(
            req.reference,
            settings=settings,
            project=project,
            root_reference=req.rootReference,
            refresh=False,
        )
        return GitHubPathValidationResponse(
            reference=req.reference,
            status=_github_probe("success", "Path reference resolved successfully.", path=str(resolved)),
            resolvedLocalPath=str(resolved),
        )
    except PathResolutionError as exc:
        state = "warning" if exc.code in {"missing_branch", "missing_subpath"} else "error"
        return GitHubPathValidationResponse(
            reference=req.reference,
            status=_github_probe(state, exc.message),
            resolvedLocalPath="",
        )


@github_integrations_router.post("/refresh-workspace", response_model=GitHubWorkspaceRefreshResponse)
async def refresh_github_workspace(req: GitHubWorkspaceRefreshRequest):
    settings = github_settings_store.load()
    project = _project_for_request_or_active(req.projectId) if str(req.projectId or "").strip() else None
    reference = req.reference or (project.pathConfig.root if project is not None else None)
    if reference is None:
        return GitHubWorkspaceRefreshResponse(
            projectId=str(getattr(project, "id", "")),
            status=_github_probe("idle", "Choose a GitHub-backed path reference to refresh."),
            resolvedLocalPath="",
        )

    try:
        resolved = _resolve_reference_with_settings(
            reference,
            settings=settings,
            project=project,
            refresh=bool(req.force),
        )
        return GitHubWorkspaceRefreshResponse(
            projectId=str(getattr(project, "id", "")),
            status=_github_probe("success", "GitHub workspace refreshed successfully.", path=str(resolved)),
            resolvedLocalPath=str(resolved),
        )
    except PathResolutionError as exc:
        state = "warning" if exc.code in {"missing_branch", "missing_subpath"} else "error"
        return GitHubWorkspaceRefreshResponse(
            projectId=str(getattr(project, "id", "")),
            status=_github_probe(state, exc.message),
            resolvedLocalPath="",
        )


@github_integrations_router.post("/check-write-capability", response_model=GitHubWriteCapabilityResponse)
async def check_github_write_capability(req: GitHubWriteCapabilityRequest):
    settings = github_settings_store.load()
    project = _project_for_request_or_active(req.projectId) if str(req.projectId or "").strip() else None
    reference = req.reference or (project.pathConfig.root if project is not None else None)
    repo_ref = reference.repoRef if reference is not None else None

    if repo_ref is None or reference.sourceKind != "github_repo":
        return GitHubWriteCapabilityResponse(
            projectId=str(getattr(project, "id", "")),
            canWrite=False,
            status=_github_probe("idle", "Select a GitHub-backed reference to evaluate write capability."),
        )

    token_configured = bool(str(settings.token or "").strip())
    can_write = bool(settings.writeEnabled and repo_ref.writeEnabled and token_configured)
    message = (
        "GitHub writes are enabled for this workspace."
        if can_write
        else "GitHub writes remain read-only until integration writes, repo writes, and a token are configured."
    )
    return GitHubWriteCapabilityResponse(
        projectId=str(getattr(project, "id", "")),
        canWrite=can_write,
        status=_github_probe("success" if can_write else "warning", message),
    )
