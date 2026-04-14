"""Lightweight runtime bootstrap for MCP tool execution."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

from backend import config
from backend.application.context import RequestContext, RequestMetadata
from backend.application.ports import CorePorts
from backend.db import connection
from backend.runtime.container import RuntimeContainer
from backend.runtime.profiles import get_runtime_profile
from backend.runtime_ports import build_core_ports


T = TypeVar("T")

MCP_PROFILE = get_runtime_profile("test")

_container: RuntimeContainer | None = None


async def bootstrap_mcp() -> RuntimeContainer:
    global _container
    if _container is not None:
        return _container

    db = await connection.get_connection()
    container = RuntimeContainer(profile=MCP_PROFILE)
    container.db = db
    container.ports = build_core_ports(
        db,
        runtime_profile=MCP_PROFILE,
        storage_profile=config.STORAGE_PROFILE,
    )
    _container = container
    return container


async def shutdown_mcp() -> None:
    global _container
    _container = None
    await connection.close_connection()


async def get_app_request(
    *,
    tool_name: str,
    project_id: str | None = None,
    container: RuntimeContainer | None = None,
) -> tuple[RequestContext, CorePorts]:
    runtime = container or await bootstrap_mcp()
    headers: dict[str, str] = {}
    if project_id:
        headers["x-ccdash-project-id"] = project_id

    context = await runtime.build_request_context(
        RequestMetadata(
            headers=headers,
            method="MCP",
            path=f"mcp://ccdash/{tool_name}",
        )
    )
    return context, runtime.require_ports()


async def execute_query(
    query: Callable[[RequestContext, CorePorts], Awaitable[T]],
    *,
    tool_name: str,
    project_id: str | None = None,
) -> T:
    container = await bootstrap_mcp()
    context, ports = await get_app_request(
        tool_name=tool_name,
        project_id=project_id,
        container=container,
    )
    return await query(context, ports)
