"""Tests for lightweight MCP runtime bootstrapping."""
from __future__ import annotations

import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiosqlite

from backend import config
from backend.adapters.auth.local import LocalIdentityProvider, PermitAllAuthorizationPolicy
from backend.adapters.integrations.local import NoopIntegrationClient
from backend.adapters.jobs.local import InProcessJobScheduler
from backend.adapters.storage.local import LocalStorageUnitOfWork
from backend.adapters.workspaces.local import ProjectManagerWorkspaceRegistry
from backend.application.ports import CorePorts
from backend.models import Project
from backend.mcp import bootstrap as mcp_bootstrap
from backend.project_manager import ProjectManager
from backend.runtime.container import RuntimeContainer


def _build_ports(db: aiosqlite.Connection, manager: ProjectManager) -> CorePorts:
    return CorePorts(
        identity_provider=LocalIdentityProvider(),
        authorization_policy=PermitAllAuthorizationPolicy(),
        workspace_registry=ProjectManagerWorkspaceRegistry(manager),
        storage=LocalStorageUnitOfWork(db),
        job_scheduler=InProcessJobScheduler(),
        integration_client=NoopIntegrationClient(),
    )


class MCPBootstrapTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        mcp_bootstrap._container = None

    async def asyncTearDown(self) -> None:
        mcp_bootstrap._container = None

    async def test_bootstrap_and_shutdown_mcp_remain_lightweight_and_build_request_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ProjectManager(Path(tmpdir) / "projects.json")
            project_root = Path(tmpdir) / "project-123"
            project_root.mkdir(parents=True, exist_ok=True)
            manager.add_project(
                Project(
                    id="project-123",
                    name="Project 123",
                    path=str(project_root),
                    description="Test project used for MCP bootstrap coverage.",
                    repoUrl="",
                    planDocsPath="docs/project_plans/",
                )
            )

            db = await aiosqlite.connect(":memory:")
            self.addAsyncCleanup(db.close)
            ports = _build_ports(db, manager)

            get_connection = AsyncMock(return_value=db)
            close_connection = AsyncMock()
            startup = AsyncMock(side_effect=AssertionError("MCP bootstrap must not call RuntimeContainer.startup()."))
            shutdown = AsyncMock(side_effect=AssertionError("MCP shutdown must not call RuntimeContainer.shutdown()."))

            with ExitStack() as stack:
                stack.enter_context(patch.object(mcp_bootstrap.connection, "get_connection", get_connection))
                stack.enter_context(patch.object(mcp_bootstrap.connection, "close_connection", close_connection))
                build_core_ports = stack.enter_context(
                    patch.object(mcp_bootstrap, "build_core_ports", return_value=ports)
                )
                stack.enter_context(patch.object(RuntimeContainer, "startup", startup))
                stack.enter_context(patch.object(RuntimeContainer, "shutdown", shutdown))

                container = await mcp_bootstrap.bootstrap_mcp()
                context, returned_ports = await mcp_bootstrap.get_app_request(
                    tool_name="ccdash_project_status",
                    project_id="project-123",
                    container=container,
                )
                await mcp_bootstrap.shutdown_mcp()

        self.assertIs(container.profile, mcp_bootstrap.MCP_PROFILE)
        self.assertIs(container.db, db)
        self.assertIs(container.ports, ports)
        self.assertIsNone(container.sync)
        self.assertIsNone(container.job_adapter)
        self.assertIsNone(container.lifecycle)
        self.assertEqual(context.runtime_profile, "test")
        self.assertEqual(context.trace.method, "MCP")
        self.assertEqual(context.trace.path, "mcp://ccdash/ccdash_project_status")
        self.assertEqual(context.principal.auth_mode, "local")
        self.assertIsNotNone(context.project)
        self.assertEqual(context.project.project_id, "project-123")
        self.assertIs(returned_ports, ports)
        get_connection.assert_awaited_once()
        build_core_ports.assert_called_once_with(
            db,
            runtime_profile=mcp_bootstrap.MCP_PROFILE,
            storage_profile=config.STORAGE_PROFILE,
        )
        startup.assert_not_awaited()
        shutdown.assert_not_awaited()
        close_connection.assert_awaited_once()
        self.assertIsNone(mcp_bootstrap._container)
