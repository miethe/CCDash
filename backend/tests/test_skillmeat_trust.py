import unittest
from pathlib import Path
from unittest.mock import patch

from backend.application.context import (
    AuthProviderMetadata,
    EnterpriseScope,
    Principal,
    PrincipalMembership,
    PrincipalSubject,
    ProjectScope,
    RequestContext,
    ScopeBinding,
    TeamScope,
    TenancyContext,
    TraceContext,
    WorkspaceScope,
)
from backend.services.integrations.skillmeat_client import SkillMeatClient
from backend.services.integrations.skillmeat_trust import build_skillmeat_trust_metadata


def _local_context() -> RequestContext:
    return RequestContext(
        principal=Principal(subject="local:operator", display_name="Local Operator", auth_mode="local"),
        workspace=WorkspaceScope(workspace_id="workspace-1", root_path=Path("/tmp/workspace")),
        project=ProjectScope(
            project_id="project-1",
            project_name="Project 1",
            root_path=Path("/tmp/workspace"),
            sessions_dir=Path("/tmp/workspace/.claude/sessions"),
            docs_dir=Path("/tmp/workspace/docs"),
            progress_dir=Path("/tmp/workspace/.claude/progress"),
        ),
        runtime_profile="local",
        trace=TraceContext(request_id="req-local"),
        tenancy=TenancyContext(workspace_id="workspace-1", project_id="project-1"),
    )


def _hosted_context(provider_id: str = "oidc") -> RequestContext:
    principal = Principal(
        subject=f"{provider_id}:user-1",
        display_name="Hosted User",
        auth_mode="oidc" if provider_id == "oidc" else provider_id,
        memberships=(
            PrincipalMembership(
                workspace_id="project-1",
                role="PM",
                scope_type="project",
                scope_id="project-1",
                enterprise_id="ent-1",
                team_id="team-1",
            ),
        ),
        provider=AuthProviderMetadata(
            provider_id=provider_id,
            issuer=f"https://{provider_id}.issuer.test",
            audience="ccdash-api",
            tenant_id="ent-1",
            hosted=True,
        ),
        normalized_subject=PrincipalSubject(
            subject="user-1",
            kind="user",
            provider_id=provider_id,
            issuer=f"https://{provider_id}.issuer.test",
        ),
        scopes=("integration.skillmeat:sync", "project:read"),
    )
    return RequestContext(
        principal=principal,
        workspace=WorkspaceScope(workspace_id="workspace-1", root_path=Path("/tmp/workspace")),
        project=ProjectScope(
            project_id="project-1",
            project_name="Project 1",
            root_path=Path("/tmp/workspace"),
            sessions_dir=Path("/tmp/workspace/.claude/sessions"),
            docs_dir=Path("/tmp/workspace/docs"),
            progress_dir=Path("/tmp/workspace/.claude/progress"),
        ),
        runtime_profile="api",
        trace=TraceContext(request_id="req-hosted"),
        enterprise=EnterpriseScope(enterprise_id="ent-1"),
        team=TeamScope(team_id="team-1", enterprise_id="ent-1"),
        scope_bindings=(
            ScopeBinding(scope_type="enterprise", scope_id="ent-1", role="EA"),
            ScopeBinding(scope_type="team", scope_id="team-1", role="TA"),
            ScopeBinding(scope_type="workspace", scope_id="workspace-1", role="PM"),
            ScopeBinding(scope_type="project", scope_id="project-1", role="PM"),
        ),
        tenancy=TenancyContext(
            enterprise_id="ent-1",
            team_id="team-1",
            workspace_id="workspace-1",
            project_id="project-1",
        ),
    )


class SkillMeatTrustMetadataTests(unittest.TestCase):
    def test_local_context_does_not_create_trust_metadata(self) -> None:
        metadata = build_skillmeat_trust_metadata(
            _local_context(),
            delegation_reason="skillmeat.definition.sync",
        )

        self.assertIsNone(metadata)

    def test_hosted_oidc_context_creates_deterministic_trust_headers(self) -> None:
        metadata = build_skillmeat_trust_metadata(
            _hosted_context("oidc"),
            delegation_reason="skillmeat.definition.sync",
        )

        self.assertIsNotNone(metadata)
        headers = metadata.as_headers()
        self.assertEqual(headers["X-CCDash-Trust-Contract"], "ccdash-skillmeat-shared-auth-v1")
        self.assertEqual(headers["X-CCDash-Delegation-Mode"], "shared-provider-trust")
        self.assertEqual(headers["X-CCDash-Delegation-Reason"], "skillmeat.definition.sync")
        self.assertEqual(headers["X-CCDash-Auth-Provider"], "oidc")
        self.assertEqual(headers["X-CCDash-Auth-Issuer"], "https://oidc.issuer.test")
        self.assertEqual(headers["X-CCDash-Principal-Stable-Subject"], "oidc:https://oidc.issuer.test:user:user-1")
        self.assertEqual(headers["X-CCDash-Enterprise-Id"], "ent-1")
        self.assertEqual(headers["X-CCDash-Team-Id"], "team-1")
        self.assertEqual(headers["X-CCDash-Workspace-Id"], "workspace-1")
        self.assertEqual(headers["X-CCDash-Project-Id"], "project-1")
        self.assertEqual(headers["X-CCDash-Auth-Scopes"], "integration.skillmeat:sync,project:read")
        self.assertEqual(headers["X-CCDash-Scope-Chain"], "enterprise:ent-1;team:team-1;workspace:workspace-1;project:project-1")
        self.assertEqual(
            headers["X-CCDash-Scope-Roles"],
            "enterprise:ent-1=EA;project:project-1=PM;team:team-1=TA;workspace:workspace-1=PM",
        )

    def test_hosted_clerk_context_uses_same_shared_provider_contract(self) -> None:
        metadata = build_skillmeat_trust_metadata(
            _hosted_context("clerk"),
            delegation_reason="skillmeat.memory.publish",
        )

        self.assertIsNotNone(metadata)
        headers = metadata.as_headers()
        self.assertEqual(headers["X-CCDash-Auth-Provider"], "clerk")
        self.assertEqual(headers["X-CCDash-Delegation-Reason"], "skillmeat.memory.publish")
        self.assertEqual(headers["X-CCDash-Delegation-Mode"], "shared-provider-trust")

    def test_client_sends_hosted_trust_headers_without_requiring_api_key(self) -> None:
        metadata = build_skillmeat_trust_metadata(
            _hosted_context("oidc"),
            delegation_reason="skillmeat.definition.sync",
        )
        client = SkillMeatClient(
            base_url="http://skillmeat.local",
            timeout_seconds=2.0,
            aaa_enabled=True,
            trust_metadata=metadata,
        )
        captured_request = None

        class _Response:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b'{"items":[]}'

        def fake_urlopen(req, timeout=0):
            nonlocal captured_request
            captured_request = req
            return _Response()

        with patch("backend.services.integrations.skillmeat_client.request.urlopen", side_effect=fake_urlopen):
            client._request_json("/api/v1/projects", {"limit": 1})

        self.assertIsNotNone(captured_request)
        headers = {key.lower(): value for key, value in captured_request.headers.items()}
        self.assertNotIn("authorization", headers)
        self.assertEqual(headers["x-ccdash-trust-contract"], "ccdash-skillmeat-shared-auth-v1")
        self.assertEqual(headers["x-ccdash-auth-provider"], "oidc")
        self.assertEqual(headers["x-ccdash-project-id"], "project-1")

    def test_client_without_trust_metadata_preserves_local_no_auth_headers(self) -> None:
        client = SkillMeatClient(base_url="http://skillmeat.local", timeout_seconds=2.0, aaa_enabled=False)
        captured_request = None

        class _Response:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b'{"items":[]}'

        def fake_urlopen(req, timeout=0):
            nonlocal captured_request
            captured_request = req
            return _Response()

        with patch("backend.services.integrations.skillmeat_client.request.urlopen", side_effect=fake_urlopen):
            client._request_json("/api/v1/projects", {"limit": 1})

        self.assertIsNotNone(captured_request)
        headers = {key.lower(): value for key, value in captured_request.headers.items()}
        self.assertNotIn("authorization", headers)
        self.assertFalse(any(key.startswith("x-ccdash-") for key in headers))


if __name__ == "__main__":
    unittest.main()
