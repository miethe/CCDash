import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException

from backend import config
from backend.application.context import (
    EnterpriseScope,
    Principal,
    PrincipalMembership,
    ProjectScope,
    RequestContext,
    TeamScope,
    TenancyContext,
    TraceContext,
    WorkspaceScope,
)
from backend.application.services.authorization import (
    AuthorizationDenied,
    RoleBindingAuthorizationPolicy,
    check_authorization,
    require_authorization,
)
from backend.runtime.profiles import get_runtime_profile
from backend.runtime_ports import build_core_ports
from backend.adapters.auth.local import PermitAllAuthorizationPolicy
from backend.request_scope import require_http_authorization


def _enterprise_storage_profile() -> config.StorageProfileConfig:
    return config.StorageProfileConfig(
        profile="enterprise",
        db_backend="postgres",
        database_url="postgresql://example/test",
        filesystem_source_of_truth=False,
    )


def _context(
    *,
    memberships: tuple[PrincipalMembership, ...] = (),
    scopes: tuple[str, ...] = (),
    enterprise_id: str | None = "enterprise-1",
    team_id: str | None = "team-1",
    workspace_id: str | None = "workspace-1",
    project_id: str | None = "project-1",
    authenticated: bool = True,
) -> RequestContext:
    workspace = WorkspaceScope(workspace_id=workspace_id, root_path=Path("/tmp/workspace")) if workspace_id else None
    project = (
        ProjectScope(
            project_id=project_id,
            project_name=project_id,
            root_path=Path("/tmp/workspace") / project_id,
            sessions_dir=Path("/tmp/workspace") / project_id / "sessions",
            docs_dir=Path("/tmp/workspace") / project_id / "docs",
            progress_dir=Path("/tmp/workspace") / project_id / "progress",
        )
        if project_id
        else None
    )
    return RequestContext(
        principal=Principal(
            subject="oidc:user-1",
            display_name="User One",
            auth_mode="oidc",
            is_authenticated=authenticated,
            memberships=memberships,
            scopes=scopes,
        ),
        workspace=workspace,
        project=project,
        runtime_profile="api",
        trace=TraceContext(request_id="req-1"),
        enterprise=EnterpriseScope(enterprise_id=enterprise_id) if enterprise_id else None,
        team=TeamScope(team_id=team_id, enterprise_id=enterprise_id or "") if team_id and enterprise_id else None,
        tenancy=TenancyContext(
            enterprise_id=enterprise_id,
            team_id=team_id,
            workspace_id=workspace_id,
            project_id=project_id,
        ),
    )


class RoleBindingAuthorizationPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_project_role_allows_bound_project_permission(self) -> None:
        policy = RoleBindingAuthorizationPolicy()
        context = _context(
            memberships=(
                PrincipalMembership(
                    workspace_id="workspace-1",
                    role="PM",
                    scope_type="project",
                    scope_id="project-1",
                    enterprise_id="enterprise-1",
                    team_id="team-1",
                ),
            )
        )

        decision = await policy.authorize(context, action="project:update")

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.code, "permission_allowed")
        self.assertIn("PM", decision.reason)

    async def test_explicit_deny_role_wins_over_allow(self) -> None:
        policy = RoleBindingAuthorizationPolicy()
        context = _context(
            memberships=(
                PrincipalMembership(
                    workspace_id="workspace-1",
                    role="PM",
                    scope_type="project",
                    scope_id="project-1",
                ),
                PrincipalMembership(
                    workspace_id="workspace-1",
                    role="deny:project:update",
                    scope_type="project",
                    scope_id="project-1",
                    binding_id="deny-binding",
                ),
            )
        )

        decision = await policy.authorize(context, action="project:update")

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, "permission_explicitly_denied")
        self.assertIn("deny-binding", decision.reason)

    async def test_direct_scope_allows_action_without_role_binding(self) -> None:
        policy = RoleBindingAuthorizationPolicy()
        context = _context(scopes=("project:read",))

        decision = await policy.authorize(context, action="project:read")

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.code, "permission_allowed")
        self.assertIn("principal.scopes", decision.reason)

    async def test_legacy_oauth_scope_order_is_normalized(self) -> None:
        policy = RoleBindingAuthorizationPolicy()
        context = _context(scopes=("read:project",))

        decision = await policy.authorize(context, action="project:read")

        self.assertTrue(decision.allowed)

    async def test_enterprise_role_inherits_to_project_scope(self) -> None:
        policy = RoleBindingAuthorizationPolicy()
        context = _context(
            memberships=(
                PrincipalMembership(
                    workspace_id="enterprise-1",
                    role="EA",
                    scope_type="enterprise",
                    scope_id="enterprise-1",
                ),
            )
        )

        decision = await policy.authorize(context, action="cache.links:rebuild")

        self.assertTrue(decision.allowed)

    async def test_team_role_inherits_to_project_scope(self) -> None:
        policy = RoleBindingAuthorizationPolicy()
        context = _context(
            memberships=(
                PrincipalMembership(
                    workspace_id="team-1",
                    role="TA",
                    scope_type="team",
                    scope_id="team-1",
                    enterprise_id="enterprise-1",
                ),
            )
        )

        decision = await policy.authorize(context, action="planning.writeback:sync")

        self.assertTrue(decision.allowed)

    async def test_workspace_role_inherits_to_project_scope(self) -> None:
        policy = RoleBindingAuthorizationPolicy()
        context = _context(
            memberships=(
                PrincipalMembership(
                    workspace_id="workspace-1",
                    role="PM",
                    scope_type="workspace",
                    scope_id="workspace-1",
                    enterprise_id="enterprise-1",
                ),
            )
        )

        decision = await policy.authorize(context, action="document.link:create")

        self.assertTrue(decision.allowed)

    async def test_user_role_binding_allows_direct_principal_grant(self) -> None:
        policy = RoleBindingAuthorizationPolicy()
        context = _context(
            memberships=(
                PrincipalMembership(
                    workspace_id="oidc:user-1",
                    role="PV",
                    scope_type="user",
                    scope_id="oidc:user-1",
                ),
            )
        )

        decision = await policy.authorize(context, action="project:read")

        self.assertTrue(decision.allowed)

    async def test_project_mismatch_denies_bound_project_role(self) -> None:
        policy = RoleBindingAuthorizationPolicy()
        context = _context(
            project_id="project-2",
            memberships=(
                PrincipalMembership(
                    workspace_id="workspace-1",
                    role="PM",
                    scope_type="project",
                    scope_id="project-1",
                ),
            ),
        )

        decision = await policy.authorize(context, action="project:update")

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, "permission_not_granted")

    async def test_direct_scope_deny_overrides_direct_scope_allow(self) -> None:
        policy = RoleBindingAuthorizationPolicy()
        context = _context(scopes=("project:read", "deny:project:read"))

        decision = await policy.authorize(context, action="project:read")

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, "permission_explicitly_denied")

    async def test_unauthenticated_principal_denies_before_policy_grants(self) -> None:
        policy = RoleBindingAuthorizationPolicy()
        context = _context(scopes=("project:read",), authenticated=False)

        decision = await policy.authorize(context, action="project:read")

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, "principal_unauthenticated")


class AuthorizationHelperTests(unittest.IsolatedAsyncioTestCase):
    async def test_helper_returns_allowed_decision(self) -> None:
        policy = RoleBindingAuthorizationPolicy()
        context = _context(
            memberships=(
                PrincipalMembership(
                    workspace_id="workspace-1",
                    role="PM",
                    scope_type="project",
                    scope_id="project-1",
                ),
            )
        )

        decision = await require_authorization(policy, context, action="project:update")

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.code, "permission_allowed")

    async def test_check_helper_preserves_authorize_call_shape(self) -> None:
        policy = RoleBindingAuthorizationPolicy()
        context = _context(scopes=("read:project",))

        decision = await check_authorization(policy, context, action="project:read", resource=None)

        self.assertTrue(decision.allowed)

    async def test_http_helper_maps_unauthenticated_denial_to_401(self) -> None:
        policy = RoleBindingAuthorizationPolicy()
        context = _context(scopes=("project:read",), authenticated=False)
        ports = SimpleNamespace(authorization_policy=policy)

        with self.assertRaises(HTTPException) as raised:
            await require_http_authorization(context, ports, action="project:read")

        self.assertEqual(raised.exception.status_code, 401)
        self.assertEqual(raised.exception.detail["error"], "unauthorized")
        self.assertEqual(raised.exception.detail["code"], "principal_unauthenticated")

    async def test_http_helper_maps_authenticated_denial_to_403(self) -> None:
        policy = RoleBindingAuthorizationPolicy()
        context = _context()
        ports = SimpleNamespace(authorization_policy=policy)

        with self.assertRaises(HTTPException) as raised:
            await require_http_authorization(context, ports, action="admin.settings:update")

        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(raised.exception.detail["error"], "forbidden")
        self.assertEqual(raised.exception.detail["code"], "permission_not_granted")

    async def test_http_helper_propagates_denial_reason_and_code(self) -> None:
        policy = RoleBindingAuthorizationPolicy()
        context = _context(
            memberships=(
                PrincipalMembership(
                    workspace_id="workspace-1",
                    role="deny:project:update",
                    scope_type="project",
                    scope_id="project-1",
                    binding_id="deny-binding",
                ),
            )
        )
        ports = SimpleNamespace(authorization_policy=policy)

        with self.assertRaises(HTTPException) as raised:
            await require_http_authorization(
                context,
                ports,
                action="project:update",
                resource="project:project-1",
            )

        detail = raised.exception.detail
        self.assertEqual(detail["code"], "permission_explicitly_denied")
        self.assertIn("deny-binding", detail["reason"])
        self.assertEqual(detail["action"], "project:update")
        self.assertEqual(detail["resource"], "project:project-1")

    async def test_service_helper_denial_remains_transport_neutral(self) -> None:
        policy = RoleBindingAuthorizationPolicy()
        context = _context()

        with self.assertRaises(AuthorizationDenied) as raised:
            await require_authorization(policy, context, action="admin.role:manage")

        self.assertNotIsInstance(raised.exception, HTTPException)
        self.assertEqual(raised.exception.code, "permission_not_granted")
        self.assertEqual(raised.exception.action, "admin.role:manage")


class AuthorizationCompositionTests(unittest.TestCase):
    def test_api_profile_uses_role_binding_policy_by_default(self) -> None:
        ports = build_core_ports(
            object(),
            runtime_profile=get_runtime_profile("api"),
            storage_profile=_enterprise_storage_profile(),
            authorization_policy=None,
        )

        self.assertIsInstance(ports.authorization_policy, RoleBindingAuthorizationPolicy)

    def test_local_and_test_profiles_keep_permit_all_policy(self) -> None:
        local_ports = build_core_ports(object(), runtime_profile=get_runtime_profile("local"))
        test_ports = build_core_ports(object(), runtime_profile=get_runtime_profile("test"))

        self.assertIsInstance(local_ports.authorization_policy, PermitAllAuthorizationPolicy)
        self.assertIsInstance(test_ports.authorization_policy, PermitAllAuthorizationPolicy)


if __name__ == "__main__":
    unittest.main()
