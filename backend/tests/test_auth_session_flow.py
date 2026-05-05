import base64
from urllib.parse import parse_qs, urlparse

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.adapters.auth.providers.base import HostedAuthValidationContext
from backend.adapters.auth.session_state import (
    sign_payload,
    state_cookie_name,
    verify_payload,
)
from backend.application.context import (
    AuthProviderMetadata,
    Principal,
    PrincipalMembership,
    PrincipalSubject,
)
from backend.application.services.authentication import AuthenticationService
from backend.config import AuthProviderConfig
from backend.routers.auth import auth_router
from backend.runtime.bootstrap import build_runtime_app


ISSUER = "https://issuer.example.test"
AUTHORIZATION_ENDPOINT = "https://issuer.example.test/oauth2/authorize"


def _config(provider: str = "oidc", **overrides) -> AuthProviderConfig:
    values = {
        "provider": provider,
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


def _principal() -> Principal:
    return Principal(
        subject="oidc:user-123",
        display_name="User One",
        auth_mode="oidc",
        email="user@example.test",
        is_authenticated=True,
        groups=("engineering", "admin"),
        scopes=("read:project",),
        memberships=(
            PrincipalMembership(
                workspace_id="workspace-1",
                role="admin",
                scope_type="workspace",
                enterprise_id="enterprise-1",
            ),
        ),
        provider=AuthProviderMetadata(
            provider_id="oidc",
            issuer=ISSUER,
            audience="ccdash-api",
            tenant_id="enterprise-1",
            hosted=True,
        ),
        normalized_subject=PrincipalSubject(
            subject="user-123",
            provider_id="oidc",
            issuer=ISSUER,
        ),
    )


def _app(service: AuthenticationService) -> FastAPI:
    app = FastAPI()
    app.state.auth_service = service
    app.include_router(auth_router)
    return app


class _MockHostedProvider:
    provider_id = "oidc"

    def __init__(self) -> None:
        self.last_token = None
        self.last_context = None

    async def resolve(self, token, *, validation_context=None):
        return await self.verify(token, validation_context=validation_context)

    async def verify(self, token, *, validation_context=None):
        self.last_token = token
        self.last_context = validation_context
        return _principal()


def test_signed_cookie_rejects_expired_and_tampered_values() -> None:
    value = sign_payload(
        {"subject": "user-123"},
        kind="auth_session",
        secret="secret",
        ttl_seconds=10,
        now=100,
    )

    envelope = verify_payload(value, kind="auth_session", secret="secret", now=105)
    assert envelope is not None
    assert envelope.payload["subject"] == "user-123"

    assert verify_payload(f"{value}x", kind="auth_session", secret="secret", now=105) is None
    assert verify_payload(value, kind="auth_session", secret="wrong", now=105) is None
    assert verify_payload(value, kind="auth_session", secret="secret", now=110) is None


def test_login_start_sets_state_cookie_and_returns_oidc_authorization_url() -> None:
    async def discovery_fetcher(url: str):
        assert url == f"{ISSUER}/.well-known/openid-configuration"
        return {"authorization_endpoint": AUTHORIZATION_ENDPOINT}

    service = AuthenticationService(
        _config(),
        runtime_profile="api",
        discovery_fetcher=discovery_fetcher,
    )
    client = TestClient(_app(service))

    response = client.get("/api/auth/login/start?redirect=false&redirectTo=/dashboard")

    assert response.status_code == 200
    authorization_url = response.json()["authorizationUrl"]
    parsed = urlparse(authorization_url)
    params = parse_qs(parsed.query)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == AUTHORIZATION_ENDPOINT
    assert params["client_id"] == ["client-1"]
    assert params["redirect_uri"] == ["https://app.example.test/api/auth/callback"]
    assert params["scope"] == ["openid profile email"]
    assert params["code_challenge_method"] == ["S256"]
    assert params["state"][0]
    assert params["nonce"][0]
    assert state_cookie_name(service.config) in client.cookies


def test_callback_id_token_verifies_provider_sets_session_and_session_endpoint_reads_it() -> None:
    mock_provider = _MockHostedProvider()

    async def discovery_fetcher(_url: str):
        return {"authorization_endpoint": AUTHORIZATION_ENDPOINT}

    service = AuthenticationService(
        _config(),
        runtime_profile="api",
        provider_factory=lambda _config: mock_provider,
        discovery_fetcher=discovery_fetcher,
    )
    client = TestClient(_app(service))

    login = client.get("/api/auth/login/start?redirect=false&redirectTo=/app", follow_redirects=False)
    state = parse_qs(urlparse(login.json()["authorizationUrl"]).query)["state"][0]
    callback = client.get(
        f"/api/auth/callback?state={state}&id_token=fake-id-token",
        follow_redirects=False,
    )

    assert callback.status_code == 303
    assert callback.headers["location"] == "/app"
    assert mock_provider.last_token == "fake-id-token"
    assert isinstance(mock_provider.last_context, HostedAuthValidationContext)
    assert mock_provider.last_context.expected_state == state
    assert mock_provider.last_context.expected_nonce

    session = client.get("/api/auth/session")
    assert session.status_code == 200
    payload = session.json()
    assert payload["authenticated"] is True
    assert payload["provider"] == "oidc"
    assert payload["subject"] == "oidc:user-123"
    assert payload["displayName"] == "User One"
    assert payload["email"] == "user@example.test"
    assert payload["groups"] == ["engineering", "admin"]
    assert payload["scopes"] == ["read:project"]
    assert payload["memberships"][0]["workspaceId"] == "workspace-1"
    assert payload["authMode"] == "oidc"
    assert payload["localMode"] is False


def test_callback_with_code_documents_unimplemented_exchange() -> None:
    service = AuthenticationService(_config(), runtime_profile="api")
    client = TestClient(_app(service))

    login = client.get("/api/auth/login/start?redirect=false", follow_redirects=False)
    state = parse_qs(urlparse(login.json()["authorizationUrl"]).query)["state"][0]
    response = client.get(f"/api/auth/callback?state={state}&code=auth-code", follow_redirects=False)

    assert response.status_code == 501
    assert response.json()["detail"] == "OAuth authorization code exchange is not implemented yet."


def test_logout_clears_session_cookie_and_missing_session_is_anonymous() -> None:
    mock_provider = _MockHostedProvider()
    service = AuthenticationService(
        _config(),
        runtime_profile="api",
        provider_factory=lambda _config: mock_provider,
    )
    client = TestClient(_app(service))

    assert client.get("/api/auth/session").json()["authenticated"] is False

    login = client.get("/api/auth/login/start?redirect=false", follow_redirects=False)
    state = parse_qs(urlparse(login.json()["authorizationUrl"]).query)["state"][0]
    assert (
        client.get(
            f"/api/auth/callback?state={state}&id_token=fake-id-token",
            follow_redirects=False,
        ).status_code
        == 303
    )
    assert client.get("/api/auth/session").json()["authenticated"] is True

    logout = client.post("/api/auth/logout")
    assert logout.status_code == 200
    assert logout.json() == {"ok": True}
    assert client.get("/api/auth/session").json()["authenticated"] is False


def test_local_mode_session_reports_local_operator_without_cookie() -> None:
    service = AuthenticationService(_config("local", deployment_mode="local"), runtime_profile="local")
    client = TestClient(_app(service))

    payload = client.get("/api/auth/session").json()

    assert payload["authenticated"] is True
    assert payload["authMode"] == "local"
    assert payload["localMode"] is True
    assert payload["subject"] == "local:local-operator"


def test_clerk_login_start_fails_clearly_without_browser_redirect_surface() -> None:
    publishable_host = base64_url("example.accounts.dev$")
    service = AuthenticationService(
        _config(
            "clerk",
            clerk_publishable_key=f"pk_test_{publishable_host}",
            clerk_secret_key="clerk-secret",
            clerk_jwt_key="clerk-jwt-key",
        ),
        runtime_profile="api",
    )
    client = TestClient(_app(service))

    response = client.get("/api/auth/login/start?redirect=false")

    assert response.status_code == 503
    assert "Clerk browser login redirect is not configured" in response.json()["detail"]
    assert service.provider_metadata()["frontendApiHost"] == "example.accounts.dev"


def test_auth_router_is_registered_in_runtime_bootstrap() -> None:
    app = build_runtime_app("test")
    routes = {getattr(route, "path", "") for route in app.routes}

    assert "/api/auth/session" in routes
    assert "/api/auth/login/start" in routes
    assert "/api/auth/callback" in routes
    assert "/api/auth/logout" in routes


def base64_url(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")
