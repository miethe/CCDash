"""FastAPI dependency helpers that avoid importing the runtime package."""
from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Request

from backend.application.context import RequestContext, RequestMetadata
from backend.application.ports import CorePorts


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
    context = await container.build_request_context(metadata)
    request.state.request_context = context
    return context
