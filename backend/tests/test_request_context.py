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
from backend.application.context import (
    EnterpriseScope,
    OwnershipResolutionHint,
    Principal,
    RequestContext,
    RequestMetadata,
    ScopeBinding,
    StorageScope,
    TeamScope,
    TenancyContext,
    TraceContext,
)
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


class TenancyContextContractTests(unittest.TestCase):
    """DPM-303 — Tenancy, scope, and ownership contract through context seams."""

    def test_tenancy_context_defaults_to_local_mode(self) -> None:
        tenancy = TenancyContext()

        self.assertIsNone(tenancy.enterprise_id)
        self.assertIsNone(tenancy.team_id)
        self.assertIsNone(tenancy.workspace_id)
        self.assertIsNone(tenancy.project_id)
        self.assertFalse(tenancy.is_enterprise_scoped)
        self.assertFalse(tenancy.is_team_scoped)
        self.assertEqual(tenancy.scope_depth, 0)
        self.assertEqual(tenancy.scope_chain, ())
        self.assertEqual(tenancy.ownership_posture_default, "scope-owned")

    def test_tenancy_context_enterprise_scoped(self) -> None:
        tenancy = TenancyContext(
            enterprise_id="ent-1",
            workspace_id="ws-1",
            project_id="proj-1",
            ownership_posture_default="directly-ownable",
        )

        self.assertTrue(tenancy.is_enterprise_scoped)
        self.assertFalse(tenancy.is_team_scoped)
        self.assertEqual(tenancy.scope_depth, 3)
        self.assertEqual(
            tenancy.scope_chain,
            (("enterprise", "ent-1"), ("workspace", "ws-1"), ("project", "proj-1")),
        )
        self.assertEqual(tenancy.ownership_posture_default, "directly-ownable")

    def test_tenancy_context_full_hierarchy(self) -> None:
        tenancy = TenancyContext(
            enterprise_id="ent-1",
            team_id="team-alpha",
            workspace_id="ws-1",
            project_id="proj-1",
        )

        self.assertTrue(tenancy.is_enterprise_scoped)
        self.assertTrue(tenancy.is_team_scoped)
        self.assertEqual(tenancy.scope_depth, 4)
        self.assertEqual(
            tenancy.scope_chain,
            (
                ("enterprise", "ent-1"),
                ("team", "team-alpha"),
                ("workspace", "ws-1"),
                ("project", "proj-1"),
            ),
        )

    def test_request_context_is_local_mode(self) -> None:
        context = RequestContext(
            principal=Principal(subject="local:local-operator", display_name="Local Operator", auth_mode="local"),
            workspace=None,
            project=None,
            runtime_profile="local",
            trace=TraceContext(request_id="req-1"),
        )

        self.assertTrue(context.is_local_mode)
        self.assertIsNone(context.enterprise)
        self.assertIsNone(context.team)
        self.assertIsNone(context.effective_enterprise_id)
        self.assertIsNone(context.effective_tenant_id)

    def test_request_context_enterprise_mode_from_enterprise_scope(self) -> None:
        context = RequestContext(
            principal=Principal(subject="oidc:user-1", display_name="User One", auth_mode="oidc"),
            workspace=None,
            project=None,
            runtime_profile="api",
            trace=TraceContext(request_id="req-1"),
            enterprise=EnterpriseScope(enterprise_id="ent-abc"),
            tenancy=TenancyContext(enterprise_id="ent-abc"),
        )

        self.assertFalse(context.is_local_mode)
        self.assertEqual(context.effective_enterprise_id, "ent-abc")

    def test_request_context_enterprise_mode_from_storage_scope(self) -> None:
        context = RequestContext(
            principal=Principal(subject="oidc:user-1", display_name="User One", auth_mode="oidc"),
            workspace=None,
            project=None,
            runtime_profile="api",
            trace=TraceContext(request_id="req-1"),
            storage_scope=StorageScope(enterprise_id="ent-storage"),
        )

        self.assertEqual(context.effective_enterprise_id, "ent-storage")

    def test_request_context_tenant_id_prefers_storage_scope(self) -> None:
        context = RequestContext(
            principal=Principal(subject="oidc:user-1", display_name="User One", auth_mode="oidc"),
            workspace=None,
            project=None,
            runtime_profile="api",
            trace=TraceContext(request_id="req-1"),
            storage_scope=StorageScope(enterprise_id="ent-1", tenant_id="tenant-x", isolation_mode="tenant"),
            tenancy=TenancyContext(enterprise_id="ent-1"),
        )

        self.assertEqual(context.effective_tenant_id, "tenant-x")


class OwnershipResolutionHintTests(unittest.TestCase):
    """DPM-303 — Ownership resolution hints from request context."""

    def _make_context(self, *, auth_mode: str = "local", enterprise_id: str | None = None) -> RequestContext:
        return RequestContext(
            principal=Principal(subject="test:user-1", display_name="Test User", auth_mode=auth_mode),
            workspace=None,
            project=None,
            runtime_profile="test",
            trace=TraceContext(request_id="req-1"),
            enterprise=EnterpriseScope(enterprise_id=enterprise_id) if enterprise_id else None,
            tenancy=TenancyContext(enterprise_id=enterprise_id),
        )

    def test_directly_ownable_defaults_to_principal(self) -> None:
        context = self._make_context()
        hint = context.ownership_hint_for_posture("directly-ownable")

        self.assertEqual(hint.posture, "directly-ownable")
        self.assertEqual(hint.owner_subject_type, "user")
        self.assertEqual(hint.owner_subject_id, "test:user-1")

    def test_inherits_parent_ownership(self) -> None:
        context = self._make_context()
        hint = context.ownership_hint_for_posture("inherits-parent-ownership")

        self.assertEqual(hint.posture, "inherits-parent-ownership")
        self.assertEqual(hint.inherited_from_scope_type, "parent_entity")
        self.assertIsNone(hint.owner_subject_type)

    def test_scope_owned_in_local_mode(self) -> None:
        context = self._make_context()
        hint = context.ownership_hint_for_posture("scope-owned")

        self.assertEqual(hint.posture, "scope-owned")
        self.assertEqual(hint.inherited_from_scope_type, "workspace")
        self.assertIsNone(hint.owner_subject_type)

    def test_scope_owned_in_enterprise_mode(self) -> None:
        context = self._make_context(enterprise_id="ent-1")
        hint = context.ownership_hint_for_posture("scope-owned")

        self.assertEqual(hint.posture, "scope-owned")
        self.assertEqual(hint.inherited_from_scope_type, "enterprise")
        self.assertEqual(hint.inherited_from_scope_id, "ent-1")


class TenancyContextRuntimeContainerTests(unittest.IsolatedAsyncioTestCase):
    """DPM-303 — Verify container.build_request_context populates tenancy fields."""

    async def test_local_mode_tenancy_has_no_enterprise_or_team(self) -> None:
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
                        headers={"x-request-id": "req-tenancy-local"},
                        method="GET",
                        path="/api/projects/active",
                        client_host="127.0.0.1",
                    )
                )
            finally:
                await db.close()

        self.assertIsNone(context.enterprise)
        self.assertIsNone(context.team)
        self.assertTrue(context.is_local_mode)
        self.assertIsNone(context.tenancy.enterprise_id)
        self.assertIsNone(context.tenancy.team_id)
        self.assertIsNotNone(context.tenancy.workspace_id)
        self.assertIsNotNone(context.tenancy.project_id)
        self.assertEqual(context.tenancy.ownership_posture_default, "scope-owned")
        self.assertEqual(context.tenancy.scope_depth, 2)
        # Scope bindings should only have workspace and project (no enterprise/team)
        binding_types = [b.scope_type for b in context.scope_bindings]
        self.assertEqual(binding_types, ["workspace", "project"])

    async def test_enterprise_mode_tenancy_populates_enterprise_scope(self) -> None:
        """Simulate an enterprise-mode container by overriding the storage profile."""
        from backend import config

        enterprise_profile = config.StorageProfileConfig(
            profile="enterprise",
            db_backend="postgres",
            database_url="postgresql://example/test",
            filesystem_source_of_truth=False,
            shared_postgres_enabled=False,
            isolation_mode="dedicated",
            schema_name="acme_corp",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ProjectManager(Path(tmpdir) / "projects.json")
            db = await aiosqlite.connect(":memory:")
            try:
                container = RuntimeContainer(profile=get_runtime_profile("test"))
                container.storage_profile = enterprise_profile
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
                        headers={"x-request-id": "req-ent-1"},
                        method="GET",
                        path="/api/projects/active",
                        client_host="127.0.0.1",
                    )
                )
            finally:
                await db.close()

        self.assertIsNotNone(context.enterprise)
        self.assertEqual(context.enterprise.enterprise_id, "acme_corp")
        self.assertIsNone(context.team)
        self.assertEqual(context.tenancy.enterprise_id, "acme_corp")
        self.assertIsNone(context.tenancy.team_id)
        self.assertEqual(context.tenancy.ownership_posture_default, "directly-ownable")
        # Scope bindings should include enterprise
        binding_types = [b.scope_type for b in context.scope_bindings]
        self.assertIn("enterprise", binding_types)
        self.assertEqual(binding_types[0], "enterprise")

    async def test_enterprise_mode_with_team_header_populates_team_scope(self) -> None:
        from backend import config

        enterprise_profile = config.StorageProfileConfig(
            profile="enterprise",
            db_backend="postgres",
            database_url="postgresql://example/test",
            filesystem_source_of_truth=False,
            shared_postgres_enabled=False,
            isolation_mode="dedicated",
            schema_name="acme_corp",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ProjectManager(Path(tmpdir) / "projects.json")
            db = await aiosqlite.connect(":memory:")
            try:
                container = RuntimeContainer(profile=get_runtime_profile("test"))
                container.storage_profile = enterprise_profile
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
                        headers={
                            "x-request-id": "req-team-1",
                            "x-ccdash-team-id": "team-alpha",
                            "x-ccdash-team-name": "Alpha Team",
                        },
                        method="GET",
                        path="/api/sessions",
                        client_host="127.0.0.1",
                    )
                )
            finally:
                await db.close()

        self.assertIsNotNone(context.enterprise)
        self.assertIsNotNone(context.team)
        self.assertEqual(context.team.team_id, "team-alpha")
        self.assertEqual(context.team.enterprise_id, "acme_corp")
        self.assertEqual(context.team.display_name, "Alpha Team")
        self.assertEqual(context.tenancy.team_id, "team-alpha")
        self.assertTrue(context.tenancy.is_team_scoped)
        # Scope bindings chain: enterprise → team → workspace → project
        binding_types = [b.scope_type for b in context.scope_bindings]
        self.assertEqual(binding_types[0], "enterprise")
        self.assertEqual(binding_types[1], "team")
        # Team binding parent is enterprise
        team_binding = context.scope_bindings[1]
        self.assertEqual(team_binding.parent_scope_type, "enterprise")
        self.assertEqual(team_binding.parent_scope_id, "acme_corp")

    async def test_team_header_ignored_without_enterprise_scope(self) -> None:
        """Team scope requires an enterprise boundary — in local mode team headers are ignored."""
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
                        headers={
                            "x-request-id": "req-local-team",
                            "x-ccdash-team-id": "team-should-be-ignored",
                        },
                        method="GET",
                        path="/api/projects/active",
                        client_host="127.0.0.1",
                    )
                )
            finally:
                await db.close()

        self.assertIsNone(context.enterprise)
        self.assertIsNone(context.team)
        self.assertIsNone(context.tenancy.team_id)
        binding_types = [b.scope_type for b in context.scope_bindings]
        self.assertNotIn("team", binding_types)
        self.assertNotIn("enterprise", binding_types)


class StorageScopeTests(unittest.TestCase):
    """DPM-303 — StorageScope import needed for test_request_context_tenant_id_prefers_storage_scope."""

    pass  # StorageScope is tested via the OwnershipResolutionHintTests and TenancyContextRuntimeContainerTests
