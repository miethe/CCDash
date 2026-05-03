"""Shared helpers for request-scoped application services."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from backend.adapters.auth.claims_mapping import select_claim_scope
from backend.application.context import RequestContext, RequestMetadata, TenancyContext, TraceContext
from backend.application.ports import CorePorts
from backend.models import Project
from backend.runtime_ports import build_core_ports


@dataclass(frozen=True, slots=True)
class ApplicationRequest:
    context: RequestContext
    ports: CorePorts


async def resolve_application_request(
    request_context: Any,
    core_ports: Any,
    db: Any,
    *,
    requested_project_id: str | None = None,
    runtime_profile: str = "local",
) -> ApplicationRequest:
    ports = core_ports if isinstance(core_ports, CorePorts) else build_core_ports(db)
    context = (
        request_context
        if isinstance(request_context, RequestContext)
        else await build_compat_request_context(
            ports,
            requested_project_id=requested_project_id,
            runtime_profile=runtime_profile,
        )
    )
    return ApplicationRequest(context=context, ports=ports)


async def build_compat_request_context(
    ports: CorePorts,
    *,
    requested_project_id: str | None = None,
    runtime_profile: str = "local",
) -> RequestContext:
    metadata = RequestMetadata(headers={}, method="INTERNAL", path="")
    principal = await ports.identity_provider.get_principal(metadata, runtime_profile=runtime_profile)
    hosted_claim_scope = _principal_has_hosted_claim_scope(principal)
    claim_scope = select_claim_scope(principal, metadata) if hosted_claim_scope else None
    effective_project_id = str(requested_project_id or "").strip() or None
    if effective_project_id is None and claim_scope is not None:
        effective_project_id = claim_scope.project_id or claim_scope.workspace_id
    try:
        workspace_scope, project_scope = _resolve_workspace_scope(
            ports.workspace_registry,
            effective_project_id,
            allow_active_fallback=not hosted_claim_scope,
        )
    except Exception:
        workspace_scope = None
        project_scope = None

    request_id = f"compat-{uuid4()}"
    return RequestContext(
        principal=principal,
        workspace=workspace_scope,
        project=project_scope,
        runtime_profile=runtime_profile,
        trace=TraceContext(
            request_id=request_id,
            correlation_id=request_id,
            path="",
            method="INTERNAL",
        ),
        tenancy=TenancyContext(
            workspace_id=workspace_scope.workspace_id if workspace_scope else None,
            project_id=project_scope.project_id if project_scope else None,
        ),
    )


def resolve_project(
    context: RequestContext,
    ports: CorePorts,
    *,
    requested_project_id: str | None = None,
    required: bool = False,
) -> Project | None:
    project_id = str(requested_project_id or "").strip()
    if project_id:
        project = ports.workspace_registry.get_project(project_id)
        if project is None and required:
            raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
        return project

    if context.project is not None:
        scoped = ports.workspace_registry.get_project(context.project.project_id)
        if scoped is not None:
            return scoped

    if _principal_has_hosted_claim_scope(context.principal):
        if required:
            raise HTTPException(status_code=404, detail="No project selected for hosted request")
        return None

    project = ports.workspace_registry.get_active_project()
    if project is None and required:
        raise HTTPException(status_code=404, detail="No active project")
    return project


def require_project(context: RequestContext, ports: CorePorts, *, requested_project_id: str | None = None) -> Project:
    project = resolve_project(context, ports, requested_project_id=requested_project_id, required=True)
    if project is None:
        raise HTTPException(status_code=404, detail="No active project")
    return project


def _principal_has_hosted_claim_scope(principal: Any) -> bool:
    provider = getattr(principal, "provider", None)
    return bool(getattr(provider, "hosted", False))


def _resolve_workspace_scope(
    workspace_registry: Any,
    project_id: str | None,
    *,
    allow_active_fallback: bool,
) -> tuple[Any, Any]:
    try:
        return workspace_registry.resolve_scope(
            project_id,
            allow_active_fallback=allow_active_fallback,
        )
    except TypeError:
        if not allow_active_fallback and project_id is None:
            return None, None
        return workspace_registry.resolve_scope(project_id)
