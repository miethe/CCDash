import tempfile
import unittest
from pathlib import Path

import aiosqlite

from backend import config
from backend.adapters.auth.claims_mapping import principal_from_claims, select_claim_scope
from backend.adapters.auth.local import PermitAllAuthorizationPolicy
from backend.adapters.jobs.local import InProcessJobScheduler
from backend.adapters.integrations.local import NoopIntegrationClient
from backend.adapters.storage.local import LocalStorageUnitOfWork
from backend.adapters.workspaces.local import ProjectManagerWorkspaceRegistry
from backend.application.context import Principal, RequestMetadata
from backend.application.ports import CorePorts
from backend.models import Project
from backend.project_manager import ProjectManager
from backend.runtime.container import RuntimeContainer
from backend.runtime.profiles import get_runtime_profile


ISSUER = "https://issuer.example.test"


class ClaimMappingTests(unittest.TestCase):
    def test_oidc_claims_map_to_existing_principal_memberships(self) -> None:
        principal = principal_from_claims(
            {
                "sub": "user-1",
                "email": "user@example.test",
                "enterprise_id": "Enterprise One",
                "team_id": "Platform Team",
                "workspace_id": "workspace-1",
                "project_id": "project-1",
                "ccdash_role": "PM",
                "groups": ["Platform Team", "Reviewers"],
                "scope": "project:read",
            },
            provider_id="oidc",
            issuer=ISSUER,
            audience="ccdash-api",
        )

        self.assertEqual(principal.provider.tenant_id, "enterprise-one")
        self.assertEqual(principal.normalized_subject.stable_id, f"oidc:{ISSUER}:user:user-1")
        self.assertEqual(principal.scopes, ("project:read",))
        self.assertIn("Reviewers", principal.groups)
        memberships = {(m.scope_type, m.effective_scope_id, m.role, m.enterprise_id) for m in principal.memberships}
        self.assertIn(("project", "project-1", "PM", "enterprise-one"), memberships)
        self.assertIn(("team", "platform-team", "PM", "enterprise-one"), memberships)
        self.assertIn(("team", "reviewers", "PM", "enterprise-one"), memberships)

    def test_clerk_org_and_group_variants_map_provider_neutrally(self) -> None:
        principal = principal_from_claims(
            {
                "sub": "user_clerk_1",
                "org_id": "org_acme",
                "org_role": "enterprise_admin",
                "groups": ["Team/Alpha"],
                "workspace": "workspace-2",
            },
            provider_id="clerk",
            issuer="https://clerk.example.test",
            audience="ccdash-api",
        )

        self.assertEqual(principal.subject, "clerk:user_clerk_1")
        self.assertEqual(principal.provider.provider_id, "clerk")
        self.assertEqual(principal.provider.tenant_id, "org_acme")
        memberships = {(m.scope_type, m.effective_scope_id, m.role, m.enterprise_id) for m in principal.memberships}
        self.assertIn(("workspace", "workspace-2", "enterprise_admin", "org_acme"), memberships)
        self.assertIn(("team", "team:alpha", "enterprise_admin", "org_acme"), memberships)

    def test_scope_selection_prefers_claims_for_hosted_team_and_project_falls_back_to_claim(self) -> None:
        principal = principal_from_claims(
            {
                "sub": "user-1",
                "enterprise_id": "ent-1",
                "team_id": "team-claim",
                "workspace_id": "workspace-1",
                "project_id": "project-claim",
            },
            provider_id="oidc",
            issuer=ISSUER,
            audience="ccdash-api",
        )

        selection = select_claim_scope(
            principal,
            RequestMetadata(
                headers={
                    "x-ccdash-team-id": "team-header",
                },
                method="GET",
                path="/api/projects/active",
            ),
        )

        self.assertEqual(selection.enterprise_id, "ent-1")
        self.assertEqual(selection.team_id, "team-claim")
        self.assertEqual(selection.workspace_id, "workspace-1")
        self.assertEqual(selection.project_id, "project-claim")

    def test_malformed_and_empty_claims_do_not_create_fake_scope_memberships(self) -> None:
        with self.assertRaises(ValueError):
            principal_from_claims({}, provider_id="oidc", issuer=ISSUER, audience="ccdash-api")

        principal = principal_from_claims(
            {
                "sub": "user-1",
                "groups": [{"bad": "shape"}, None, ""],
                "ccdash_memberships": [{"workspace_id": ""}, {"project_id": None}, "bad"],
            },
            provider_id="oidc",
            issuer=ISSUER,
            audience="ccdash-api",
        )

        self.assertEqual(principal.groups, ())
        self.assertEqual(principal.memberships, ())


class _PrincipalIdentityProvider:
    def __init__(self, principal: Principal) -> None:
        self.principal = principal

    async def get_principal(self, metadata: RequestMetadata, *, runtime_profile: str) -> Principal:
        _ = metadata, runtime_profile
        return self.principal


class RuntimeClaimScopeTests(unittest.IsolatedAsyncioTestCase):
    async def test_hosted_context_resolves_project_from_claim_without_active_project_fallback(self) -> None:
        principal = principal_from_claims(
            {
                "sub": "user-1",
                "enterprise_id": "ent-1",
                "team_id": "team-1",
                "workspace_id": "project-2",
                "project_id": "project-2",
                "ccdash_role": "PM",
            },
            provider_id="oidc",
            issuer=ISSUER,
            audience="ccdash-api",
        )

        context = await self._build_context(principal)

        self.assertIsNotNone(context.project)
        self.assertEqual(context.project.project_id, "project-2")
        self.assertEqual(context.tenancy.enterprise_id, "ent-1")
        self.assertEqual(context.tenancy.team_id, "team-1")
        self.assertEqual(context.tenancy.project_id, "project-2")
        self.assertEqual([binding.scope_type for binding in context.scope_bindings], ["enterprise", "team", "workspace", "project"])
        self.assertEqual(context.scope_bindings[-1].principal_stable_subject, principal.stable_subject)

    async def test_hosted_context_with_no_project_claim_does_not_inherit_active_project(self) -> None:
        principal = principal_from_claims(
            {
                "sub": "user-1",
                "enterprise_id": "ent-1",
            },
            provider_id="oidc",
            issuer=ISSUER,
            audience="ccdash-api",
        )

        context = await self._build_context(principal)

        self.assertIsNone(context.workspace)
        self.assertIsNone(context.project)
        self.assertEqual(context.tenancy.enterprise_id, "ent-1")
        self.assertIsNone(context.tenancy.project_id)

    async def test_hosted_context_resolves_explicit_project_header_without_mutating_active_project(self) -> None:
        principal = principal_from_claims(
            {
                "sub": "user-1",
                "enterprise_id": "ent-1",
                "team_id": "team-1",
            },
            provider_id="oidc",
            issuer=ISSUER,
            audience="ccdash-api",
        )

        context, active_project_id = await self._build_context(
            principal,
            headers={"x-ccdash-project-id": "project-2"},
            include_active_project=True,
        )

        self.assertIsNotNone(context.project)
        self.assertEqual(context.project.project_id, "project-2")
        self.assertEqual(context.tenancy.project_id, "project-2")
        self.assertEqual(active_project_id, "project-1")

    async def test_local_principal_keeps_active_project_fallback(self) -> None:
        principal = Principal(
            subject="local:local-operator",
            display_name="Local Operator",
            auth_mode="local",
        )

        context = await self._build_context(principal)

        self.assertEqual(context.principal.auth_mode, "local")
        self.assertIsNotNone(context.project)
        self.assertEqual(context.project.project_id, "project-1")

    async def _build_context(
        self,
        principal: Principal,
        *,
        headers: dict[str, str] | None = None,
        include_active_project: bool = False,
    ):
        enterprise_profile = config.StorageProfileConfig(
            profile="enterprise",
            db_backend="postgres",
            database_url="postgresql://example/test",
            filesystem_source_of_truth=False,
            schema_name="storage-ent",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manager = ProjectManager(root / "projects.json")
            manager.add_project(Project(id="project-1", name="Project One", path=str(root / "project-1")))
            manager.add_project(Project(id="project-2", name="Project Two", path=str(root / "project-2")))
            manager.set_active_project("project-1")
            db = await aiosqlite.connect(":memory:")
            try:
                container = RuntimeContainer(profile=get_runtime_profile("test"))
                container.storage_profile = enterprise_profile
                container.db = db
                container.ports = CorePorts(
                    identity_provider=_PrincipalIdentityProvider(principal),
                    authorization_policy=PermitAllAuthorizationPolicy(),
                    workspace_registry=ProjectManagerWorkspaceRegistry(manager),
                    storage=LocalStorageUnitOfWork(db),
                    job_scheduler=InProcessJobScheduler(),
                    integration_client=NoopIntegrationClient(),
                )
                request_headers = {"x-request-id": "req-claims"}
                if headers:
                    request_headers.update(headers)
                context = await container.build_request_context(
                    RequestMetadata(
                        headers=request_headers,
                        method="GET",
                        path="/api/projects/active",
                    )
                )
                if include_active_project:
                    active = manager.get_active_project()
                    return context, active.id if active is not None else None
                return context
            finally:
                await db.close()


if __name__ == "__main__":
    unittest.main()
