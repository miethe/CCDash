"""Tests for lightweight CLI runtime bootstrapping."""
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
from backend.cli import runtime as cli_runtime
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


class CLIRuntimeBootstrapTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._original_project_override = cli_runtime.PROJECT_OVERRIDE
        cli_runtime.PROJECT_OVERRIDE = None
        cli_runtime._container = None

    async def asyncTearDown(self) -> None:
        cli_runtime.PROJECT_OVERRIDE = self._original_project_override
        cli_runtime._container = None

    async def test_bootstrap_and_shutdown_cli_remain_lightweight_and_build_request_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ProjectManager(Path(tmpdir) / "projects.json")
            db = await aiosqlite.connect(":memory:")
            self.addAsyncCleanup(db.close)
            ports = _build_ports(db, manager)

            get_connection = AsyncMock(return_value=db)
            close_connection = AsyncMock()
            startup = AsyncMock(side_effect=AssertionError("CLI bootstrap must not call RuntimeContainer.startup()."))
            shutdown = AsyncMock(side_effect=AssertionError("CLI shutdown must not call RuntimeContainer.shutdown()."))

            with ExitStack() as stack:
                stack.enter_context(patch.object(cli_runtime.connection, "get_connection", get_connection))
                stack.enter_context(patch.object(cli_runtime.connection, "close_connection", close_connection))
                build_core_ports = stack.enter_context(
                    patch.object(cli_runtime, "build_core_ports", return_value=ports)
                )
                stack.enter_context(patch.object(RuntimeContainer, "startup", startup))
                stack.enter_context(patch.object(RuntimeContainer, "shutdown", shutdown))

                container = await cli_runtime.bootstrap_cli()
                context, returned_ports = await cli_runtime.get_app_request(container)
                await cli_runtime.shutdown_cli()

        self.assertIs(container.profile, cli_runtime.CLI_PROFILE)
        self.assertIs(container.db, db)
        self.assertIs(container.ports, ports)
        self.assertIsNone(container.sync)
        self.assertIsNone(container.job_adapter)
        self.assertIsNone(container.lifecycle)
        self.assertEqual(context.runtime_profile, "test")
        self.assertEqual(context.trace.method, "CLI")
        self.assertEqual(context.trace.path, "cli://ccdash")
        self.assertEqual(context.principal.auth_mode, "local")
        self.assertIsNotNone(context.project)
        self.assertEqual(context.project.project_id, "default-skillmeat")
        self.assertIs(returned_ports, ports)
        get_connection.assert_awaited_once()
        build_core_ports.assert_called_once_with(
            db,
            runtime_profile=cli_runtime.CLI_PROFILE,
            storage_profile=config.STORAGE_PROFILE,
        )
        startup.assert_not_awaited()
        shutdown.assert_not_awaited()
        close_connection.assert_awaited_once()
        self.assertIsNone(cli_runtime._container)
