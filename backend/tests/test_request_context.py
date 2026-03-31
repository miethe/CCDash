import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiosqlite
from starlette.requests import Request

from backend.adapters.auth.local import LocalIdentityProvider, PermitAllAuthorizationPolicy
from backend.adapters.jobs.local import InProcessJobScheduler
from backend.adapters.integrations.local import NoopIntegrationClient
from backend.adapters.storage.local import LocalStorageUnitOfWork
from backend.adapters.workspaces.local import ProjectManagerWorkspaceRegistry
from backend.application.context import Principal, RequestContext, RequestMetadata, TraceContext
from backend.application.ports import CorePorts
from backend.db.repositories.sessions import SqliteSessionRepository
from backend.project_manager import ProjectManager
from backend.request_scope import get_core_ports
from backend.runtime.bootstrap_test import build_test_app
from backend.runtime.container import RuntimeContainer
from backend.runtime.dependencies import get_request_context
from backend.runtime.profiles import get_runtime_profile


class LocalAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_identity_provider_returns_local_operator_principal(self) -> None:
        provider = LocalIdentityProvider()

        principal = await provider.get_principal(
            RequestMetadata(
                headers={"x-ccdash-project-id": "project-1"},
                method="GET",
                path="/api/health",
                client_host="127.0.0.1",
            ),
            runtime_profile="local",
        )

        self.assertEqual(principal.subject, "local:local-operator")
        self.assertEqual(principal.auth_mode, "local")
        self.assertEqual(principal.memberships[0].workspace_id, "project-1")

    async def test_permit_all_authorization_policy_allows_any_action(self) -> None:
        policy = PermitAllAuthorizationPolicy()

        decision = await policy.authorize(
            RequestContext(
                principal=Principal(subject="local:local-operator", display_name="Local Operator", auth_mode="local"),
                workspace=None,
                project=None,
                runtime_profile="local",
                trace=TraceContext(request_id="req-1"),
            ),
            action="projects:list",
            resource="projects",
        )

        self.assertTrue(decision.allowed)

    async def test_workspace_registry_resolves_active_project_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ProjectManager(Path(tmpdir) / "projects.json")
            registry = ProjectManagerWorkspaceRegistry(manager)

            workspace, project = registry.resolve_scope()

        self.assertIsNotNone(workspace)
        self.assertIsNotNone(project)
        self.assertEqual(workspace.workspace_id, "default-skillmeat")
        self.assertEqual(project.project_id, "default-skillmeat")

    async def test_storage_unit_of_work_uses_explicit_local_repository_bindings(self) -> None:
        db = await aiosqlite.connect(":memory:")
        try:
            storage = LocalStorageUnitOfWork(db)

            repo = storage.sessions()

            self.assertIsInstance(repo, SqliteSessionRepository)
            self.assertIs(repo, storage.sessions())
        finally:
            await db.close()

    async def test_factory_adapter_compat_resolves_same_sqlite_repos_as_local_adapter(self) -> None:
        from backend.adapters.storage.local import FactoryStorageUnitOfWork

        db = await aiosqlite.connect(":memory:")
        try:
            storage = FactoryStorageUnitOfWork(db)

            repo = storage.sessions()

            self.assertIsInstance(repo, SqliteSessionRepository)
            self.assertIs(repo, storage.sessions())
        finally:
            await db.close()

    async def test_factory_adapter_compat_resolves_same_sqlite_repos_as_local_adapter(self) -> None:
        """FactoryStorageUnitOfWork is a compat alias (subclass of LocalStorageUnitOfWork).
        Existing consumers that import it directly continue to receive SQLite
        repositories, preserving backward compatibility without requiring code changes.
        """
        from backend.adapters.storage.local import FactoryStorageUnitOfWork

        db = await aiosqlite.connect(":memory:")
        try:
            storage = FactoryStorageUnitOfWork(db)

            repo = storage.sessions()

            self.assertIsInstance(repo, SqliteSessionRepository)
            self.assertIs(repo, storage.sessions())  # result is cached
        finally:
            await db.close()

    async def test_in_process_job_scheduler_runs_coroutine(self) -> None:
        scheduler = InProcessJobScheduler()
        marker: list[str] = []

        async def _job() -> None:
            marker.append("ran")

        task = scheduler.schedule(_job(), name="test-job")
        await task

        self.assertEqual(marker, ["ran"])


class RequestContextTests(unittest.IsolatedAsyncioTestCase):
    async def test_runtime_container_builds_request_context_in_local_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ProjectManager(Path(tmpdir) / "projects.json")
            db = await aiosqlite.connect(":memory:")
            try:
                container = RuntimeContainer(profile=get_runtime_profile("local"))
                container.db = db
                container.ports = CorePorts(
                    identity_provider=LocalIdentityProvider(),
                    authorization_policy=PermitAllAuthorizationPolicy(),
                    workspace_registry=ProjectManagerWorkspaceRegistry(manager),
                    storage=LocalStorageUnitOfWork(db),
                    job_scheduler=InProcessJobScheduler(),
                    integration_client=NoopIntegrationClient(),
                )
                context = await container.build_request_context(
                    RequestMetadata(
                        headers={"x-request-id": "req-123"},
                        method="GET",
                        path="/api/projects/active",
                        client_host="127.0.0.1",
                    )
                )
            finally:
                await db.close()

        self.assertEqual(context.runtime_profile, "local")
        self.assertEqual(context.trace.request_id, "req-123")
        self.assertIsNotNone(context.project)
        self.assertEqual(context.project.project_id, "default-skillmeat")
        self.assertIsNotNone(context.storage_scope)
        self.assertEqual(context.storage_scope.isolation_mode, "dedicated")
        self.assertEqual([binding.scope_type for binding in context.scope_bindings], ["workspace", "project"])


class RequestContextRouteIntegrationTests(unittest.TestCase):
    def test_health_route_declares_request_context_dependency(self) -> None:
        app = build_test_app()
        health_route = next(route for route in app.routes if getattr(route, "path", None) == "/api/health")
        dependency_calls = {dependency.call for dependency in health_route.dependant.dependencies}

        self.assertIn(get_request_context, dependency_calls)

    def test_request_context_dependency_builds_context_for_fastapi_request(self) -> None:
        app = build_test_app()
        fake_context = RequestContext(
            principal=Principal(subject="test:local-operator", display_name="Local Operator", auth_mode="local"),
            workspace=None,
            project=None,
            runtime_profile="test",
            trace=TraceContext(request_id="req-1"),
        )

        async def _resolve() -> RequestContext:
            request = Request(
                {
                    "type": "http",
                    "app": app,
                    "method": "GET",
                    "path": "/api/health",
                    "headers": [(b"x-request-id", b"req-1")],
                    "client": ("127.0.0.1", 9000),
                    "query_string": b"",
                    "server": ("testserver", 80),
                    "scheme": "http",
                    "root_path": "",
                    "http_version": "1.1",
                }
            )
            with patch.object(RuntimeContainer, "build_request_context", AsyncMock(return_value=fake_context)) as build_request_context:
                context = await get_request_context(request, app.state.runtime_container)
                build_request_context.assert_awaited_once()
                return context

        context = asyncio.run(_resolve())
        self.assertEqual(context.trace.request_id, "req-1")

    def test_projects_route_declares_core_ports_dependency(self) -> None:
        app = build_test_app()
        route = next(route for route in app.routes if getattr(route, "path", None) == "/api/projects")
        dependency_calls = {dependency.call for dependency in route.dependant.dependencies}

        self.assertIn(get_core_ports, dependency_calls)
