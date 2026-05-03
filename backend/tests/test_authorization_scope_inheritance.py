import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

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
    AUTHORIZATION_SCOPE_RULES,
    RoleBindingAuthorizationPolicy,
)


def _context(
    *,
    subject: str = "oidc:user-1",
    memberships: tuple[PrincipalMembership, ...] = (),
    enterprise_id: str | None = "enterprise-1",
    team_id: str | None = "team-1",
    workspace_id: str | None = "workspace-1",
    project_id: str | None = "project-1",
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
            subject=subject,
            display_name="User One",
            auth_mode="oidc",
            memberships=memberships,
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


class AuthorizationScopeRuleArtifactTests(unittest.TestCase):
    def test_scope_rules_document_order_and_conflict_precedence(self) -> None:
        self.assertEqual(
            AUTHORIZATION_SCOPE_RULES.evaluation_order,
            ("enterprise", "team", "user", "workspace", "project", "owned_entity"),
        )
        self.assertEqual(
            AUTHORIZATION_SCOPE_RULES.resource_scope_order,
            ("enterprise", "team", "workspace", "project", "owned_entity"),
        )
        self.assertTrue(AUTHORIZATION_SCOPE_RULES.explicit_deny_overrides_allow)
        self.assertIn("specific", AUTHORIZATION_SCOPE_RULES.allow_resolution)

    def test_scope_rules_document_inheritance_edges(self) -> None:
        self.assertEqual(
            AUTHORIZATION_SCOPE_RULES.inherited_descendants["enterprise"],
            ("team", "workspace", "project", "owned_entity"),
        )
        self.assertEqual(
            AUTHORIZATION_SCOPE_RULES.inherited_descendants["team"],
            ("workspace", "project", "owned_entity"),
        )
        self.assertEqual(
            AUTHORIZATION_SCOPE_RULES.inherited_descendants["workspace"],
            ("project", "owned_entity"),
        )
        self.assertEqual(AUTHORIZATION_SCOPE_RULES.inherited_descendants["project"], ("owned_entity",))

    def test_scope_rules_document_direct_user_and_owned_entity_behavior(self) -> None:
        self.assertEqual(
            AUTHORIZATION_SCOPE_RULES.direct_user_grant_subject_fields,
            ("principal.subject", "principal.stable_subject"),
        )
        self.assertTrue(AUTHORIZATION_SCOPE_RULES.direct_user_grants_are_additive)
        self.assertEqual(
            AUTHORIZATION_SCOPE_RULES.owned_entity_parent_scopes,
            ("enterprise", "team", "workspace", "project"),
        )
        self.assertTrue(AUTHORIZATION_SCOPE_RULES.owned_entity_direct_bindings_are_exact)

    def test_scope_rules_are_immutable(self) -> None:
        with self.assertRaises(FrozenInstanceError):
            AUTHORIZATION_SCOPE_RULES.explicit_deny_overrides_allow = False  # type: ignore[misc]
        with self.assertRaises(TypeError):
            AUTHORIZATION_SCOPE_RULES.inherited_descendants["project"] = ()  # type: ignore[index]


class AuthorizationScopeInheritanceBehaviorTests(unittest.IsolatedAsyncioTestCase):
    async def test_enterprise_grant_inherits_to_team_workspace_and_project(self) -> None:
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

        for resource in ("team:team-1", "workspace:workspace-1", "project:project-1"):
            with self.subTest(resource=resource):
                decision = await policy.authorize(context, action="project:read", resource=resource)

                self.assertTrue(decision.allowed)

    async def test_team_grant_inherits_to_workspace_and_project(self) -> None:
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

        for resource in ("workspace:workspace-1", "project:project-1"):
            with self.subTest(resource=resource):
                decision = await policy.authorize(context, action="planning.writeback:sync", resource=resource)

                self.assertTrue(decision.allowed)

    async def test_workspace_grant_inherits_to_project(self) -> None:
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

        decision = await policy.authorize(context, action="document.link:create", resource="project:project-1")

        self.assertTrue(decision.allowed)

    async def test_project_grant_does_not_inherit_upward_to_workspace(self) -> None:
        policy = RoleBindingAuthorizationPolicy()
        context = _context(
            memberships=(
                PrincipalMembership(
                    workspace_id="project-1",
                    role="PM",
                    scope_type="project",
                    scope_id="project-1",
                    enterprise_id="enterprise-1",
                ),
            )
        )

        decision = await policy.authorize(context, action="document.link:create", resource="workspace:workspace-1")

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, "permission_not_granted")

    async def test_user_direct_grants_apply_only_to_the_bound_principal(self) -> None:
        policy = RoleBindingAuthorizationPolicy()
        self_context = _context(
            subject="oidc:user-1",
            memberships=(
                PrincipalMembership(
                    workspace_id="oidc:user-1",
                    role="PV",
                    scope_type="user",
                    scope_id="oidc:user-1",
                ),
            ),
        )
        other_user_context = _context(
            subject="oidc:user-1",
            memberships=(
                PrincipalMembership(
                    workspace_id="oidc:user-2",
                    role="PV",
                    scope_type="user",
                    scope_id="oidc:user-2",
                ),
            ),
        )

        self_decision = await policy.authorize(self_context, action="project:read", resource="project:project-1")
        other_user_decision = await policy.authorize(
            other_user_context,
            action="project:read",
            resource="project:project-1",
        )

        self.assertTrue(self_decision.allowed)
        self.assertFalse(other_user_decision.allowed)
        self.assertEqual(other_user_decision.code, "permission_not_granted")

    async def test_owned_entity_exact_binding_and_parent_scope_inheritance(self) -> None:
        policy = RoleBindingAuthorizationPolicy()
        parent_context = _context(
            memberships=(
                PrincipalMembership(
                    workspace_id="project-1",
                    role="PM",
                    scope_type="project",
                    scope_id="project-1",
                ),
            )
        )
        owned_entity_context = _context(
            memberships=(
                PrincipalMembership(
                    workspace_id="entity-1",
                    role="PV",
                    scope_type="owned_entity",
                    scope_id="entity-1",
                ),
            )
        )

        parent_decision = await policy.authorize(
            parent_context,
            action="document:read",
            resource="owned_entity:entity-1",
        )
        exact_decision = await policy.authorize(
            owned_entity_context,
            action="document:read",
            resource="owned_entity:entity-1",
        )
        upward_decision = await policy.authorize(
            owned_entity_context,
            action="document:read",
            resource="project:project-1",
        )

        self.assertTrue(parent_decision.allowed)
        self.assertTrue(exact_decision.allowed)
        self.assertFalse(upward_decision.allowed)

    async def test_explicit_deny_overrides_more_general_allow(self) -> None:
        policy = RoleBindingAuthorizationPolicy()
        context = _context(
            memberships=(
                PrincipalMembership(
                    workspace_id="enterprise-1",
                    role="EA",
                    scope_type="enterprise",
                    scope_id="enterprise-1",
                    binding_id="enterprise-allow",
                ),
                PrincipalMembership(
                    workspace_id="project-1",
                    role="deny:project:update",
                    scope_type="project",
                    scope_id="project-1",
                    binding_id="project-deny",
                ),
            )
        )

        decision = await policy.authorize(context, action="project:update", resource="project:project-1")

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, "permission_explicitly_denied")
        self.assertIn("project-deny", decision.reason)


if __name__ == "__main__":
    unittest.main()
