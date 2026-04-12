"""Lightweight runtime bootstrap for CLI commands."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

import typer

from backend import config
from backend.application.context import RequestContext, RequestMetadata
from backend.application.ports import CorePorts
from backend.cli.output import OutputMode
from backend.db import connection
from backend.runtime.container import RuntimeContainer
from backend.runtime.profiles import get_runtime_profile
from backend.runtime_ports import build_core_ports


T = TypeVar("T")

CLI_PROFILE = get_runtime_profile("test")
OUTPUT_MODE = OutputMode.human
PROJECT_OVERRIDE: str | None = None

_container: RuntimeContainer | None = None


async def bootstrap_cli() -> RuntimeContainer:
    """Bootstrap runtime state without FastAPI startup lifecycle side effects."""
    global _container
    if _container is not None:
        return _container

    db = await connection.get_connection()
    container = RuntimeContainer(profile=CLI_PROFILE)
    container.db = db
    container.ports = build_core_ports(
        db,
        runtime_profile=CLI_PROFILE,
        storage_profile=config.STORAGE_PROFILE,
    )
    _container = container
    return container


async def shutdown_cli() -> None:
    """Tear down lightweight runtime state for command completion."""
    global _container
    _container = None
    await connection.close_connection()


async def get_app_request(
    container: RuntimeContainer | None = None,
) -> tuple[RequestContext, CorePorts]:
    runtime = container or await bootstrap_cli()
    headers: dict[str, str] = {}
    if PROJECT_OVERRIDE:
        headers["x-ccdash-project-id"] = PROJECT_OVERRIDE

    context = await runtime.build_request_context(
        RequestMetadata(
            headers=headers,
            method="CLI",
            path="cli://ccdash",
        )
    )
    return context, runtime.require_ports()


async def execute_query(
    query: Callable[[RequestContext, CorePorts], Awaitable[T]],
) -> T:
    container = await bootstrap_cli()
    try:
        context, ports = await get_app_request(container)
        return await query(context, ports)
    finally:
        await shutdown_cli()


def run_async(awaitable: Awaitable[T]) -> T:
    try:
        return asyncio.run(awaitable)
    except KeyboardInterrupt as exc:
        raise typer.Exit(code=130) from exc


def project_resolution_error_message() -> str:
    if PROJECT_OVERRIDE:
        return f"Project '{PROJECT_OVERRIDE}' was not found."
    return "Could not resolve a project. Set an active project or pass --project <id>."


def feature_not_found_error_message(feature_id: str, project_id: str | None = None) -> str:
    if project_id:
        return f"Feature '{feature_id}' was not found in project '{project_id}'."
    return f"Feature '{feature_id}' was not found."

