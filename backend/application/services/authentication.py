"""Browser/session-flow authentication service."""
from __future__ import annotations

import base64
import hashlib
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import aiohttp
from fastapi import Request

from backend.adapters.auth.bearer import RequestAuthenticationError
from backend.adapters.auth.provider_factory import create_hosted_auth_provider
from backend.adapters.auth.providers.base import HostedAuthProvider, HostedAuthValidationContext
from backend.adapters.auth.session_state import (
    SignedCookieEnvelope,
    new_token,
    read_session_cookie,
    read_state_cookie,
    sign_payload,
)
from backend.application.context import (
    AuthProviderMetadata,
    Principal,
    PrincipalMembership,
    PrincipalSubject,
)
from backend.config import AuthProviderConfig


JsonFetcher = Callable[[str], Awaitable[Mapping[str, Any]]]
HostedProviderFactory = Callable[[AuthProviderConfig], HostedAuthProvider]

SESSION_TTL_SECONDS = 3600
STATE_TTL_SECONDS = 300


@dataclass(frozen=True, slots=True)
class LoginStart:
    authorization_url: str
    state_cookie: str
    state_cookie_max_age_seconds: int = STATE_TTL_SECONDS


@dataclass(frozen=True, slots=True)
class CallbackSession:
    principal: Principal
    session_cookie: str
    session_cookie_max_age_seconds: int = SESSION_TTL_SECONDS
    redirect_to: str = "/"


class AuthenticationService:
    """Coordinates hosted auth browser flows without owning runtime composition."""

    def __init__(
        self,
        config: AuthProviderConfig,
        *,
        runtime_profile: str,
        provider_factory: HostedProviderFactory = create_hosted_auth_provider,
        discovery_fetcher: JsonFetcher | None = None,
    ) -> None:
        self.config = config
        self.runtime_profile = runtime_profile
        self._provider_factory = provider_factory
        self._discovery_fetcher = discovery_fetcher or self._fetch_json

    @property
    def signing_secret(self) -> str:
        if self.config.clerk_secret_key:
            return self.config.clerk_secret_key
        if self.config.oidc_client_secret:
            return self.config.oidc_client_secret
        if self.config.api_bearer_token:
            return self.config.api_bearer_token
        if self.config.clerk_jwt_key:
            return self.config.clerk_jwt_key
        return f"ccdash-{self.runtime_profile}-local-session-secret"

    def provider_metadata(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "provider": self.config.provider,
            "runtimeProfile": self.runtime_profile,
            "authMode": "local" if self._is_local_mode else "oidc",
            "hosted": self.config.provider in {"oidc", "clerk"},
            "localMode": self._is_local_mode,
        }
        if self.config.provider == "oidc":
            payload.update(
                {
                    "issuer": self.config.oidc_issuer or None,
                    "clientId": self.config.oidc_client_id or None,
                    "callbackUrl": self.config.oidc_callback_url or None,
                }
            )
        if self.config.provider == "clerk":
            payload.update(
                {
                    "publishableKeyConfigured": bool(self.config.clerk_publishable_key),
                    "frontendApiHost": clerk_frontend_api_host(self.config.clerk_publishable_key),
                }
            )
        return payload

    async def start_login(self, *, redirect_to: str = "/") -> LoginStart:
        if self._is_local_mode:
            raise RequestAuthenticationError(400, "Local auth mode does not use hosted login.")
        state = new_token()
        nonce = new_token()
        verifier = new_token(48)
        challenge = _code_challenge(verifier)
        normalized_redirect = _safe_redirect_path(redirect_to)
        state_cookie = sign_payload(
            {
                "state": state,
                "nonce": nonce,
                "codeVerifier": verifier,
                "redirectTo": normalized_redirect,
                "provider": self.config.provider,
            },
            kind="auth_state",
            secret=self.signing_secret,
            ttl_seconds=STATE_TTL_SECONDS,
        )
        authorization_url = await self._authorization_url(
            state=state,
            nonce=nonce,
            code_challenge=challenge,
        )
        return LoginStart(authorization_url=authorization_url, state_cookie=state_cookie)

    async def handle_callback(
        self,
        request: Request,
        *,
        state: str | None,
        id_token: str | None,
        code: str | None,
    ) -> CallbackSession:
        state_envelope = read_state_cookie(request, self.config, secret=self.signing_secret)
        state_payload = dict(state_envelope.payload) if state_envelope is not None else {}
        expected_state = str(state_payload.get("state") or "")
        expected_nonce = str(state_payload.get("nonce") or "")
        if not expected_state or str(state or "") != expected_state:
            raise RequestAuthenticationError(401, "Hosted auth state rejected.")

        if id_token:
            provider = self._provider_factory(self.config)
            principal = await provider.verify(
                id_token,
                validation_context=HostedAuthValidationContext(
                    expected_nonce=expected_nonce or None,
                    expected_state=expected_state,
                    presented_state=state,
                    authorized_party=self._authorized_party(),
                ),
            )
            session_cookie = sign_payload(
                principal_to_session_payload(principal),
                kind="auth_session",
                secret=self.signing_secret,
                ttl_seconds=SESSION_TTL_SECONDS,
            )
            return CallbackSession(
                principal=principal,
                session_cookie=session_cookie,
                redirect_to=_safe_redirect_path(str(state_payload.get("redirectTo") or "/")),
            )

        if code:
            raise RequestAuthenticationError(501, "OAuth authorization code exchange is not implemented yet.")
        raise RequestAuthenticationError(400, "Hosted auth callback requires id_token or code.")

    def session_payload(self, request: Request) -> dict[str, Any]:
        if self._is_local_mode:
            return principal_session_response(
                local_principal(self.runtime_profile),
                provider=self.config.provider,
                local_mode=True,
            )
        envelope = read_session_cookie(request, self.config, secret=self.signing_secret)
        if envelope is None:
            return anonymous_session_payload(provider=self.config.provider, local_mode=False)
        principal = principal_from_session_payload(envelope)
        if principal is None:
            return anonymous_session_payload(provider=self.config.provider, local_mode=False)
        payload = principal_session_response(principal, provider=self.config.provider, local_mode=False)
        payload["expiresAt"] = envelope.expires_at
        return payload

    @property
    def _is_local_mode(self) -> bool:
        return self.config.provider == "local" or self.runtime_profile in {"local", "test"}

    def _authorized_party(self) -> str | None:
        if self.config.provider == "clerk" and len(self.config.clerk_authorized_parties) == 1:
            return self.config.clerk_authorized_parties[0]
        return None

    async def _authorization_url(self, *, state: str, nonce: str, code_challenge: str) -> str:
        if self.config.provider == "oidc":
            return await self._oidc_authorization_url(
                state=state,
                nonce=nonce,
                code_challenge=code_challenge,
            )
        if self.config.provider == "clerk":
            host = clerk_frontend_api_host(self.config.clerk_publishable_key)
            if not host:
                raise RequestAuthenticationError(
                    503,
                    "Clerk hosted login requires a configured publishable key or frontend API host.",
                )
            raise RequestAuthenticationError(
                503,
                "Clerk browser login redirect is not configured; use the Clerk frontend SDK and send id_token to /api/auth/callback.",
            )
        raise RequestAuthenticationError(503, f"Auth provider {self.config.provider} does not support hosted login.")

    async def _oidc_authorization_url(self, *, state: str, nonce: str, code_challenge: str) -> str:
        if not self.config.oidc_issuer.strip():
            raise RequestAuthenticationError(503, "OIDC issuer is not configured.")
        if not self.config.oidc_client_id.strip():
            raise RequestAuthenticationError(503, "OIDC client id is not configured.")
        if not self.config.oidc_callback_url.strip():
            raise RequestAuthenticationError(503, "OIDC callback URL is not configured.")
        authorization_endpoint = await self._oidc_authorization_endpoint()
        query = {
            "response_type": "code",
            "client_id": self.config.oidc_client_id,
            "redirect_uri": self.config.oidc_callback_url,
            "scope": "openid profile email",
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return f"{authorization_endpoint}?{urlencode(query)}"

    async def _oidc_authorization_endpoint(self) -> str:
        issuer = self.config.oidc_issuer.rstrip("/")
        discovery_url = f"{issuer}/.well-known/openid-configuration"
        try:
            discovery = await self._discovery_fetcher(discovery_url)
        except Exception:
            discovery = {}
        endpoint = str(discovery.get("authorization_endpoint") or "").strip()
        return endpoint or f"{issuer}/authorize"

    async def _fetch_json(self, url: str) -> Mapping[str, Any]:
        timeout = aiohttp.ClientTimeout(total=5.0)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                if response.status >= 400:
                    return {}
                payload = await response.json()
        return payload if isinstance(payload, Mapping) else {}


def principal_to_session_payload(principal: Principal) -> dict[str, Any]:
    provider = principal.provider
    normalized = principal.normalized_subject
    return {
        "subject": principal.subject,
        "displayName": principal.display_name,
        "email": principal.email,
        "authenticated": principal.is_authenticated,
        "authMode": principal.auth_mode,
        "groups": list(principal.groups),
        "scopes": list(principal.scopes),
        "kind": principal.kind,
        "provider": {
            "providerId": provider.provider_id,
            "issuer": provider.issuer,
            "audience": provider.audience,
            "tenantId": provider.tenant_id,
            "hosted": provider.hosted,
        }
        if provider is not None
        else None,
        "normalizedSubject": {
            "subject": normalized.subject,
            "kind": normalized.kind,
            "providerId": normalized.provider_id,
            "issuer": normalized.issuer,
        }
        if normalized is not None
        else None,
        "memberships": [
            {
                "workspaceId": membership.workspace_id,
                "role": membership.role,
                "scopeType": membership.scope_type,
                "scopeId": membership.scope_id,
                "enterpriseId": membership.enterprise_id,
                "teamId": membership.team_id,
                "bindingId": membership.binding_id,
                "source": membership.source,
            }
            for membership in principal.memberships
        ],
    }


def principal_from_session_payload(envelope: SignedCookieEnvelope) -> Principal | None:
    payload = envelope.payload
    subject = _string(payload.get("subject"))
    display_name = _string(payload.get("displayName"))
    if not subject or not display_name:
        return None
    provider = _provider_from_payload(payload.get("provider"))
    normalized = _normalized_from_payload(payload.get("normalizedSubject"))
    return Principal(
        subject=subject,
        display_name=display_name,
        auth_mode=_string(payload.get("authMode")) or "oidc",
        email=_string(payload.get("email")),
        is_authenticated=bool(payload.get("authenticated", True)),
        groups=tuple(_string_list(payload.get("groups"))),
        scopes=tuple(_string_list(payload.get("scopes"))),
        kind=_string(payload.get("kind")) or "user",
        provider=provider,
        normalized_subject=normalized,
        memberships=tuple(_memberships_from_payload(payload.get("memberships"))),
    )


def principal_session_response(principal: Principal, *, provider: str, local_mode: bool) -> dict[str, Any]:
    session_payload = principal_to_session_payload(principal)
    session_payload["authenticated"] = principal.is_authenticated
    session_payload["provider"] = principal.auth_provider_id or provider
    session_payload["authMode"] = principal.auth_mode
    session_payload["localMode"] = local_mode
    return session_payload


def anonymous_session_payload(*, provider: str, local_mode: bool) -> dict[str, Any]:
    return {
        "authenticated": False,
        "subject": None,
        "displayName": None,
        "email": None,
        "groups": [],
        "scopes": [],
        "memberships": [],
        "provider": provider,
        "authMode": "anonymous",
        "localMode": local_mode,
    }


def local_principal(runtime_profile: str) -> Principal:
    return Principal(
        subject=f"{runtime_profile}:local-operator",
        display_name="Local Operator",
        auth_mode="local",
        is_authenticated=True,
        groups=("local", runtime_profile),
    )


def clerk_frontend_api_host(publishable_key: str) -> str | None:
    key = publishable_key.strip()
    for prefix in ("pk_test_", "pk_live_"):
        if key.startswith(prefix):
            encoded = key.removeprefix(prefix)
            try:
                decoded = base64.urlsafe_b64decode(f"{encoded}{'=' * (-len(encoded) % 4)}").decode("utf-8")
            except Exception:
                return None
            host = decoded.rstrip("$").strip()
            return host or None
    return None


def _provider_from_payload(value: Any) -> AuthProviderMetadata | None:
    if not isinstance(value, Mapping):
        return None
    provider_id = _string(value.get("providerId"))
    if not provider_id:
        return None
    return AuthProviderMetadata(
        provider_id=provider_id,
        issuer=_string(value.get("issuer")),
        audience=_string(value.get("audience")),
        tenant_id=_string(value.get("tenantId")),
        hosted=bool(value.get("hosted", False)),
    )


def _normalized_from_payload(value: Any) -> PrincipalSubject | None:
    if not isinstance(value, Mapping):
        return None
    subject = _string(value.get("subject"))
    if not subject:
        return None
    return PrincipalSubject(
        subject=subject,
        kind=_string(value.get("kind")) or "user",
        provider_id=_string(value.get("providerId")),
        issuer=_string(value.get("issuer")),
    )


def _memberships_from_payload(value: Any) -> list[PrincipalMembership]:
    if not isinstance(value, list):
        return []
    memberships: list[PrincipalMembership] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        workspace_id = _string(item.get("workspaceId"))
        role = _string(item.get("role"))
        if not workspace_id or not role:
            continue
        memberships.append(
            PrincipalMembership(
                workspace_id=workspace_id,
                role=role,
                scope_type=_string(item.get("scopeType")) or "workspace",
                scope_id=_string(item.get("scopeId")),
                enterprise_id=_string(item.get("enterpriseId")),
                team_id=_string(item.get("teamId")),
                binding_id=_string(item.get("bindingId")),
                source=_string(item.get("source")),
            )
        )
    return memberships


def _string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _safe_redirect_path(value: str) -> str:
    normalized = str(value or "").strip()
    if normalized.startswith("/") and not normalized.startswith("//"):
        return normalized
    return "/"


def _code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
