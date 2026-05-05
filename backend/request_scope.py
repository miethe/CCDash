"""FastAPI dependency helpers that avoid importing the runtime package."""
from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Request, status

from backend.adapters.auth import RequestAuthenticationError
from backend.application.context import RequestContext, RequestMetadata
from backend.application.services.authorization import (
    AuthorizationDenied,
    require_authorization,
)
from backend.application.services.audit import record_authorization_decision
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.observability import otel


def get_runtime_container(request: Request) -> Any:
    container = getattr(request.app.state, "runtime_container", None)
    if container is None or not hasattr(container, "build_request_context"):
        raise HTTPException(status_code=500, detail="Runtime container is unavailable")
    return container


def get_core_ports(
    request: Request,
    container: Any = Depends(get_runtime_container),
) -> CorePorts:
    ports = getattr(request.app.state, "core_ports", None)
    if isinstance(ports, CorePorts):
        return ports
    ports = getattr(container, "ports", None)
    if isinstance(ports, CorePorts):
        return ports
    raise HTTPException(status_code=500, detail="Runtime ports are unavailable")


async def get_request_context(
    request: Request,
    container: Any = Depends(get_runtime_container),
) -> RequestContext:
    cached = getattr(request.state, "request_context", None)
    if isinstance(cached, RequestContext):
        return cached

    metadata = RequestMetadata(
        headers={key.lower(): value for key, value in request.headers.items()},
        method=request.method,
        path=request.url.path,
        client_host=request.client.host if request.client else None,
    )
    try:
        context = await container.build_request_context(metadata)
    except RequestAuthenticationError as exc:
        otel.record_auth_session_error(
            provider="request",
            status=str(exc.status_code),
            reason=exc.detail,
            runtime_profile=_runtime_profile_name(request),
        )
        otel.log_auth_event(
            "auth.request_context.error",
            provider="request",
            status=str(exc.status_code),
            reason=exc.detail,
            path=request.url.path,
            client=request.client.host if request.client else "",
            runtime_profile=_runtime_profile_name(request),
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    request.state.request_context = context
    return context


def authorization_http_exception(denial: AuthorizationDenied) -> HTTPException:
    status_code = (
        status.HTTP_401_UNAUTHORIZED
        if denial.unauthenticated
        else status.HTTP_403_FORBIDDEN
    )
    error = "unauthorized" if status_code == status.HTTP_401_UNAUTHORIZED else "forbidden"
    return HTTPException(
        status_code=status_code,
        detail={
            "error": error,
            "code": denial.code,
            "reason": denial.reason,
            "action": denial.action,
            "resource": denial.resource,
        },
    )


async def require_http_authorization(
    request_context: RequestContext,
    core_ports: CorePorts,
    *,
    action: str,
    resource: str | None = None,
) -> AuthorizationDecision:
    try:
        decision = await require_authorization(
            core_ports.authorization_policy,
            request_context,
            action=action,
            resource=resource,
        )
        await record_authorization_decision(
            request_context,
            getattr(core_ports, "storage", None),
            decision,
            action=action,
            resource=resource,
        )
        return decision
    except AuthorizationDenied as exc:
        await record_authorization_decision(
            request_context,
            getattr(core_ports, "storage", None),
            exc.decision,
            action=exc.action,
            resource=exc.resource,
        )
        raise authorization_http_exception(exc) from exc


def _runtime_profile_name(request: Request) -> str:
    runtime_profile = getattr(request.app.state, "runtime_profile", None)
    return str(getattr(runtime_profile, "name", runtime_profile or "unknown"))
