from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.application.context import (
    AuthProviderMetadata,
    EnterpriseScope,
    Principal,
    PrincipalMembership,
    PrincipalSubject,
    ProjectScope,
    RequestContext,
    TeamScope,
    TenancyContext,
    TraceContext,
    WorkspaceScope,
)
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.adapters.auth.local import PermitAllAuthorizationPolicy
from backend.application.services.audit import record_authorization_decision
from backend.application.services.authentication import AuthenticationService
from backend.application.services.authorization import RoleBindingAuthorizationPolicy
from backend.config import AuthProviderConfig
from backend.db.repositories.identity_access import LocalAccessDecisionLogRepository
from backend.request_scope import require_http_authorization
from backend.routers.auth import auth_router


ISSUER = "https://issuer.example.test"


class _AuthoritativeDescriptor:
    authoritative = True


class _CapturingAccessDecisionRepo:
    def __init__(self) -> None:
        self.records: list[dict] = []

    def describe_capability(self) -> _AuthoritativeDescriptor:
        return _AuthoritativeDescriptor()

    async def record_access_decision(self, record: dict) -> None:
        self.records.append(record)


class _AuditSecurity:
    def __init__(self, repo: _CapturingAccessDecisionRepo) -> None:
        self.repo = repo

    def access_decision_logs(self) -> _CapturingAccessDecisionRepo:
        return self.repo


class _Storage:
    def __init__(self, repo: _CapturingAccessDecisionRepo) -> None:
        self.repo = repo

    def audit_security(self) -> _AuditSecurity:
        return _AuditSecurity(self.repo)


def _context(
    *,
    authenticated: bool = True,
    memberships: tuple[PrincipalMembership, ...] = (),
    scopes: tuple[str, ...] = (),
    auth_mode: str = "oidc",
    runtime_profile: str = "api",
) -> RequestContext:
    is_local = auth_mode == "local"
    workspace = WorkspaceScope(workspace_id="workspace-1", root_path=Path("/tmp/workspace"))
    project = ProjectScope(
        project_id="project-1",
        project_name="Project One",
        root_path=Path("/tmp/workspace/project-1"),
        sessions_dir=Path("/tmp/workspace/project-1/sessions"),
        docs_dir=Path("/tmp/workspace/project-1/docs"),
        progress_dir=Path("/tmp/workspace/project-1/progress"),
    )
    return RequestContext(
        principal=Principal(
            subject=f"{auth_mode}:user-1" if auth_mode != "local" else "local:local-operator",
            display_name="User One" if auth_mode != "local" else "Local Operator",
            auth_mode=auth_mode,
            is_authenticated=authenticated,
            groups=("local",) if auth_mode == "local" else (),
            memberships=memberships,
            scopes=scopes,
            provider=AuthProviderMetadata(
                provider_id=auth_mode,
                issuer=None if auth_mode == "local" else ISSUER,
                audience=None if auth_mode == "local" else "ccdash-api",
                tenant_id=None if auth_mode == "local" else "enterprise-1",
                hosted=auth_mode != "local",
            ),
            normalized_subject=PrincipalSubject(
                subject="local-operator" if auth_mode == "local" else "user-1",
                provider_id=auth_mode,
                issuer=None if auth_mode == "local" else ISSUER,
            ),
        ),
        workspace=workspace,
        project=project,
        runtime_profile=runtime_profile,
        trace=TraceContext(
            request_id="req-1",
            client_host="203.0.113.10",
            path="/api/admin/settings",
            method="POST",
        ),
        enterprise=None if is_local else EnterpriseScope(enterprise_id="enterprise-1"),
        team=None if is_local else TeamScope(team_id="team-1", enterprise_id="enterprise-1"),
        tenancy=TenancyContext(
            enterprise_id=None if is_local else "enterprise-1",
            team_id=None if is_local else "team-1",
            workspace_id="workspace-1",
            project_id="project-1",
        ),
    )


def _protected_action_app(
    request_context: RequestContext,
    authorization_policy: object,
) -> FastAPI:
    app = FastAPI()
    ports = SimpleNamespace(authorization_policy=authorization_policy, storage=None)

    async def _request_context() -> RequestContext:
        return request_context

    @app.post("/protected/execution-runs")
    async def protected_execution_run(
        context: RequestContext = Depends(_request_context),
    ) -> dict[str, object]:
        decision = await require_http_authorization(
            context,
            ports,
            action="execution.run:create",
            resource="project:project-1",
        )
        return {
            "ok": True,
            "action": "execution.run:create",
            "decision": decision.code,
            "runtimeProfile": context.runtime_profile,
            "authMode": context.principal.auth_mode,
        }

    return app


def test_denied_http_authorization_records_principal_attribution() -> None:
    async def run() -> None:
        repo = _CapturingAccessDecisionRepo()
        ports = CorePorts(
            identity_provider=SimpleNamespace(),
            authorization_policy=RoleBindingAuthorizationPolicy(),
            workspace_registry=SimpleNamespace(),
            storage=_Storage(repo),
            job_scheduler=SimpleNamespace(),
            integration_client=SimpleNamespace(),
        )

        with patch("backend.observability.otel.record_auth_authorization_decision") as metric:
            try:
                await require_http_authorization(
                    _context(),
                    ports,
                    action="admin.settings:update",
                    resource="project:project-1",
                )
            except HTTPException as exc:
                raised = exc
            else:  # pragma: no cover - defensive assertion shape
                raise AssertionError("Expected HTTPException")

        assert raised.status_code == 403
        assert repo.records
        record = repo.records[0]
        assert record["principal_id"] == f"oidc:{ISSUER}:user:user-1"
        assert record["requested_action"] == "admin.settings:update"
        assert record["resource_type"] == "project"
        assert record["resource_id"] == "project-1"
        assert record["decision"] == "deny"
        metadata = record["metadata_json"]
        assert metadata["subject"] == "oidc:user-1"
        assert metadata["stable_subject"] == f"oidc:{ISSUER}:user:user-1"
        assert metadata["provider"] == "oidc"
        assert metadata["issuer"] == ISSUER
        assert metadata["client"] == "203.0.113.10"
        assert metadata["path"] == "/api/admin/settings"
        metric.assert_called_once()

    asyncio.run(run())


def test_local_access_decision_repository_remains_noop_and_non_authoritative() -> None:
    async def run() -> None:
        repo = LocalAccessDecisionLogRepository(db=object())

        descriptor = repo.describe_capability()
        await repo.record_access_decision({"id": "audit-1"})

        assert descriptor.supported is False
        assert descriptor.authoritative is False
        assert descriptor.storage_profile == "local"

    asyncio.run(run())


def test_local_audit_storage_is_skipped_by_authorization_audit_service() -> None:
    async def run() -> None:
        local_repo = LocalAccessDecisionLogRepository(db=object())
        storage = SimpleNamespace(
            audit_security=lambda: SimpleNamespace(access_decision_logs=lambda: local_repo)
        )

        with patch.object(local_repo, "record_access_decision", wraps=local_repo.record_access_decision) as writer:
            await record_authorization_decision(
                _context(),
                storage,
                AuthorizationDecision(
                    allowed=False,
                    code="permission_not_granted",
                    reason="Permission is not granted.",
                ),
                action="admin.settings:update",
                resource="project:project-1",
            )

        writer.assert_not_called()

    asyncio.run(run())


def test_hosted_protected_action_without_authenticated_principal_returns_401() -> None:
    client = TestClient(
        _protected_action_app(
            _context(authenticated=False),
            RoleBindingAuthorizationPolicy(),
        )
    )

    response = client.post("/protected/execution-runs")

    assert response.status_code == 401
    detail = response.json()["detail"]
    assert detail["error"] == "unauthorized"
    assert detail["code"] == "principal_unauthenticated"
    assert detail["action"] == "execution.run:create"
    assert detail["resource"] == "project:project-1"


def test_hosted_protected_action_without_permission_returns_403() -> None:
    client = TestClient(
        _protected_action_app(
            _context(),
            RoleBindingAuthorizationPolicy(),
        )
    )

    response = client.post("/protected/execution-runs")

    assert response.status_code == 403
    detail = response.json()["detail"]
    assert detail["error"] == "forbidden"
    assert detail["code"] == "permission_not_granted"
    assert detail["action"] == "execution.run:create"
    assert detail["resource"] == "project:project-1"


def test_hosted_protected_action_with_permission_passes_through() -> None:
    client = TestClient(
        _protected_action_app(
            _context(scopes=("execution.run:create",)),
            RoleBindingAuthorizationPolicy(),
        )
    )

    response = client.post("/protected/execution-runs")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "action": "execution.run:create",
        "decision": "permission_allowed",
        "runtimeProfile": "api",
        "authMode": "oidc",
    }


def test_local_protected_action_uses_permissive_policy_pass_through() -> None:
    client = TestClient(
        _protected_action_app(
            _context(auth_mode="local", runtime_profile="local"),
            PermitAllAuthorizationPolicy(),
        )
    )

    response = client.post("/protected/execution-runs")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["action"] == "execution.run:create"
    assert payload["runtimeProfile"] == "local"
    assert payload["authMode"] == "local"


def test_login_start_failure_records_auth_observability() -> None:
    service = AuthenticationService(
        _config(oidc_issuer=""),
        runtime_profile="api",
    )
    client = TestClient(_app(service))

    with (
        patch("backend.observability.otel.record_auth_login_failure") as login_metric,
        patch("backend.observability.otel.log_auth_event") as auth_log,
    ):
        response = client.get("/api/auth/login/start?redirect=false")

    assert response.status_code == 503
    login_metric.assert_called_once()
    assert login_metric.call_args.kwargs["phase"] == "login"
    assert login_metric.call_args.kwargs["provider"] == "oidc"
    assert login_metric.call_args.kwargs["status"] == "503"
    auth_log.assert_called_once()


def test_callback_failure_records_auth_observability_and_issuer_health() -> None:
    service = AuthenticationService(_config(), runtime_profile="api")
    client = TestClient(_app(service))

    with (
        patch("backend.observability.otel.record_auth_login_failure") as login_metric,
        patch("backend.observability.otel.record_auth_issuer_health") as issuer_metric,
        patch("backend.observability.otel.log_auth_event") as auth_log,
    ):
        response = client.get("/api/auth/callback?state=unexpected&id_token=fake")

    assert response.status_code == 401
    login_metric.assert_called_once()
    assert login_metric.call_args.kwargs["phase"] == "callback"
    assert login_metric.call_args.kwargs["status"] == "401"
    issuer_metric.assert_called_once()
    assert issuer_metric.call_args.kwargs["status"] == "error"
    auth_log.assert_called_once()


def _app(service: AuthenticationService) -> FastAPI:
    app = FastAPI()
    app.state.auth_service = service
    app.include_router(auth_router)
    return app


def _config(**overrides) -> AuthProviderConfig:
    values = {
        "provider": "oidc",
        "runtime_profile": "api",
        "deployment_mode": "hosted",
        "oidc_issuer": ISSUER,
        "oidc_audience": "ccdash-api",
        "oidc_client_id": "client-1",
        "oidc_client_secret": "client-secret",
        "oidc_callback_url": "https://app.example.test/api/auth/callback",
        "oidc_jwks_url": "https://issuer.example.test/jwks.json",
        "clerk_publishable_key": "",
        "clerk_secret_key": "clerk-secret",
        "clerk_jwt_key": "clerk-jwt-key",
        "session_cookie_secure": False,
    }
    values.update(overrides)
    return AuthProviderConfig(**values)
