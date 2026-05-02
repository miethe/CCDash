"""Generic OIDC JWT validation provider."""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, cast

import aiohttp
import jwt
from cachetools import TTLCache
from jwt import PyJWKSet
from jwt.exceptions import PyJWTError

from backend.adapters.auth.bearer import RequestAuthenticationError
from backend.adapters.auth.providers.base import HostedAuthValidationContext
from backend.application.context import (
    AuthProviderMetadata,
    Principal,
    PrincipalMembership,
    PrincipalSubject,
    ScopeType,
)


JsonFetcher = Callable[[str], Awaitable[Mapping[str, Any]]]


@dataclass(frozen=True, slots=True)
class OIDCProviderSettings:
    provider_id: str
    issuer: str
    audience: str | tuple[str, ...]
    jwks_url: str = ""
    allowed_algorithms: tuple[str, ...] = ("RS256",)
    allowed_authorized_parties: tuple[str, ...] = ()
    jwks_cache_ttl_seconds: int = 300
    discovery_cache_ttl_seconds: int = 3600
    fetch_timeout_seconds: float = 5.0


class GenericOIDCProvider:
    """Validate OIDC-style JWTs against issuer discovery and JWKS keys."""

    def __init__(
        self,
        settings: OIDCProviderSettings,
        *,
        discovery_fetcher: JsonFetcher | None = None,
        jwks_fetcher: JsonFetcher | None = None,
    ) -> None:
        self._settings = settings
        self._discovery_fetcher = discovery_fetcher or self._fetch_json
        self._jwks_fetcher = jwks_fetcher or self._fetch_json
        self._discovery_cache: TTLCache[str, Mapping[str, Any]] = TTLCache(
            maxsize=8,
            ttl=max(settings.discovery_cache_ttl_seconds, 1),
        )
        self._jwks_cache: TTLCache[str, Mapping[str, Any]] = TTLCache(
            maxsize=8,
            ttl=max(settings.jwks_cache_ttl_seconds, 1),
        )

    @property
    def provider_id(self) -> str:
        return self._settings.provider_id

    async def resolve(
        self,
        token: str | None,
        *,
        validation_context: HostedAuthValidationContext | None = None,
    ) -> Principal:
        return await self.verify(token, validation_context=validation_context)

    async def verify(
        self,
        token: str | None,
        *,
        validation_context: HostedAuthValidationContext | None = None,
    ) -> Principal:
        self._validate_metadata()
        raw_token = str(token or "").strip()
        if not raw_token:
            raise RequestAuthenticationError(401, "Hosted auth token required.")

        claims = await self._decode(raw_token)
        self._validate_claims(claims, validation_context or HostedAuthValidationContext())
        return principal_from_claims(
            claims,
            provider_id=self.provider_id,
            issuer=str(claims.get("iss") or self._settings.issuer).strip(),
            audience=",".join(_audiences(self._settings.audience)),
        )

    def _validate_metadata(self) -> None:
        if not self.provider_id.strip():
            raise RequestAuthenticationError(503, "OIDC provider metadata is missing provider_id.")
        if not self._settings.issuer.strip():
            raise RequestAuthenticationError(503, "OIDC provider metadata is missing issuer.")
        if not _audiences(self._settings.audience):
            raise RequestAuthenticationError(503, "OIDC provider metadata is missing audience.")
        if not self._settings.allowed_algorithms:
            raise RequestAuthenticationError(503, "OIDC provider metadata is missing allowed algorithms.")

    async def _decode(self, token: str) -> Mapping[str, Any]:
        try:
            header = jwt.get_unverified_header(token)
        except PyJWTError as exc:
            raise RequestAuthenticationError(401, "Hosted auth token header is invalid.") from exc

        algorithm = str(header.get("alg") or "").strip()
        if algorithm not in self._settings.allowed_algorithms:
            raise RequestAuthenticationError(401, "Hosted auth token algorithm is not allowed.")

        key = await self._resolve_signing_key(header)
        try:
            return jwt.decode(
                token,
                key=key,
                algorithms=list(self._settings.allowed_algorithms),
                audience=list(_audiences(self._settings.audience)),
                issuer=self._settings.issuer,
                options={"require": ["exp", "iss", "aud", "sub"]},
            )
        except PyJWTError as exc:
            raise RequestAuthenticationError(401, "Hosted auth token rejected.") from exc

    async def _resolve_signing_key(self, header: Mapping[str, Any]) -> Any:
        kid = str(header.get("kid") or "").strip()
        if not kid:
            raise RequestAuthenticationError(401, "Hosted auth token is missing key id.")

        jwks_url = await self._resolve_jwks_url()
        jwks = await self._get_jwks(jwks_url)
        key = self._find_key(jwks, kid)
        if key is None:
            jwks = await self._get_jwks(jwks_url, force_refresh=True)
            key = self._find_key(jwks, kid)
        if key is None:
            raise RequestAuthenticationError(401, "Hosted auth token signing key was not found.")
        return key

    async def _resolve_jwks_url(self) -> str:
        configured = self._settings.jwks_url.strip()
        if configured:
            return configured

        issuer = self._settings.issuer.rstrip("/")
        discovery_url = f"{issuer}/.well-known/openid-configuration"
        discovery = self._discovery_cache.get(discovery_url)
        if discovery is None:
            discovery = await self._discovery_fetcher(discovery_url)
            self._discovery_cache[discovery_url] = discovery

        discovered_issuer = str(discovery.get("issuer") or "").strip()
        if discovered_issuer != self._settings.issuer:
            raise RequestAuthenticationError(503, "OIDC discovery issuer does not match provider metadata.")
        jwks_url = str(discovery.get("jwks_uri") or "").strip()
        if not jwks_url:
            raise RequestAuthenticationError(503, "OIDC discovery metadata is missing jwks_uri.")
        return jwks_url

    async def _get_jwks(self, jwks_url: str, *, force_refresh: bool = False) -> Mapping[str, Any]:
        if not force_refresh:
            cached = self._jwks_cache.get(jwks_url)
            if cached is not None:
                return cached

        jwks = await self._jwks_fetcher(jwks_url)
        if not isinstance(jwks.get("keys"), list):
            raise RequestAuthenticationError(503, "OIDC JWKS metadata is invalid.")
        self._jwks_cache[jwks_url] = jwks
        return jwks

    async def _fetch_json(self, url: str) -> Mapping[str, Any]:
        timeout = aiohttp.ClientTimeout(total=self._settings.fetch_timeout_seconds)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    if response.status >= 400:
                        raise RequestAuthenticationError(503, "OIDC provider metadata fetch failed.")
                    payload = await response.json()
        except RequestAuthenticationError:
            raise
        except Exception as exc:
            raise RequestAuthenticationError(503, "OIDC provider metadata fetch failed.") from exc
        if not isinstance(payload, Mapping):
            raise RequestAuthenticationError(503, "OIDC provider metadata response is invalid.")
        return payload

    def _find_key(self, jwks: Mapping[str, Any], kid: str) -> Any | None:
        try:
            keyset = PyJWKSet.from_dict(dict(jwks))
            return keyset[kid].key
        except Exception:
            return None

    def _validate_claims(
        self,
        claims: Mapping[str, Any],
        validation_context: HostedAuthValidationContext,
    ) -> None:
        subject = str(claims.get("sub") or "").strip()
        if not subject:
            raise RequestAuthenticationError(401, "Hosted auth token is missing subject.")

        if validation_context.expected_nonce is not None:
            nonce = str(claims.get("nonce") or "")
            if nonce != validation_context.expected_nonce:
                raise RequestAuthenticationError(401, "Hosted auth token nonce rejected.")

        if validation_context.expected_state is not None:
            presented_state = (
                validation_context.presented_state
                if validation_context.presented_state is not None
                else claims.get("state")
            )
            if str(presented_state or "") != validation_context.expected_state:
                raise RequestAuthenticationError(401, "Hosted auth state rejected.")

        if validation_context.authorized_party is not None:
            authorized_party = str(claims.get("azp") or claims.get("authorized_party") or "")
            if authorized_party != validation_context.authorized_party:
                raise RequestAuthenticationError(401, "Hosted auth authorized party rejected.")

        if self._settings.allowed_authorized_parties:
            authorized_party = str(claims.get("azp") or claims.get("authorized_party") or "")
            if authorized_party not in self._settings.allowed_authorized_parties:
                raise RequestAuthenticationError(401, "Hosted auth authorized party rejected.")


def _audiences(audience: str | tuple[str, ...]) -> tuple[str, ...]:
    if isinstance(audience, str):
        return (audience.strip(),) if audience.strip() else ()
    return tuple(part.strip() for part in audience if str(part).strip())


def principal_from_claims(
    claims: Mapping[str, Any],
    *,
    provider_id: str,
    issuer: str,
    audience: str | None,
) -> Principal:
    subject = str(claims["sub"]).strip()
    display_name = _first_claim(claims, ("name", "preferred_username", "email")) or subject
    email = _first_claim(claims, ("email",))
    groups = _unique((*_claim_values(claims, ("groups",)), *_claim_values(claims, ("roles", "role"))))
    scopes = _unique((*_scope_values(claims.get("scope")), *_scope_values(claims.get("scp"))))
    tenant_id = _first_claim(
        claims,
        ("tenant_id", "tid", "org_id", "organization_id", "enterprise_id"),
    )

    return Principal(
        subject=f"{provider_id}:{subject}",
        display_name=display_name,
        auth_mode="oidc",
        email=email,
        is_authenticated=True,
        groups=groups,
        memberships=_memberships_from_claims(claims),
        provider=AuthProviderMetadata(
            provider_id=provider_id,
            issuer=issuer,
            audience=audience,
            tenant_id=tenant_id,
            hosted=True,
        ),
        normalized_subject=PrincipalSubject(
            subject=subject,
            kind="user",
            provider_id=provider_id,
            issuer=issuer,
        ),
        scopes=scopes,
    )


def _first_claim(claims: Mapping[str, Any], names: Iterable[str]) -> str | None:
    for name in names:
        value = claims.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _claim_values(claims: Mapping[str, Any], names: Iterable[str]) -> tuple[str, ...]:
    values: list[str] = []
    for name in names:
        value = claims.get(name)
        if isinstance(value, str):
            parts = (value.split() if " " in value else (value,))
        elif isinstance(value, Iterable) and not isinstance(value, (bytes, Mapping)):
            parts = value
        else:
            parts = ()
        values.extend(str(part).strip() for part in parts if str(part).strip())
    return tuple(values)


def _scope_values(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split() if part.strip())
    if isinstance(value, Iterable) and not isinstance(value, (bytes, Mapping)):
        return tuple(str(part).strip() for part in value if str(part).strip())
    return ()


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            unique.append(value)
    return tuple(unique)


def _memberships_from_claims(claims: Mapping[str, Any]) -> tuple[PrincipalMembership, ...]:
    memberships: list[PrincipalMembership] = []
    explicit = claims.get("ccdash_memberships", claims.get("memberships"))
    if isinstance(explicit, Iterable) and not isinstance(explicit, (str, bytes, Mapping)):
        for item in explicit:
            if isinstance(item, Mapping):
                membership = _membership_from_mapping(item)
                if membership is not None:
                    memberships.append(membership)

    direct = _membership_from_mapping(claims)
    if direct is not None:
        memberships.append(direct)

    deduped: dict[tuple[str, str, str], PrincipalMembership] = {}
    for membership in memberships:
        key = (membership.scope_type, membership.effective_scope_id, membership.role)
        deduped.setdefault(key, membership)
    return tuple(deduped.values())


def _membership_from_mapping(values: Mapping[str, Any]) -> PrincipalMembership | None:
    workspace_id = _string_value(values, "workspace_id", "workspace")
    project_id = _string_value(values, "project_id", "project")
    if not workspace_id and not project_id:
        return None

    role = _string_value(values, "role")
    if not role:
        roles = _claim_values(values, ("roles",))
        role = roles[0] if roles else "member"

    enterprise_id = _string_value(values, "enterprise_id", "org_id", "organization_id")
    team_id = _string_value(values, "team_id")
    scope_type: ScopeType = "workspace"
    scope_id = workspace_id
    if project_id:
        scope_type = cast(ScopeType, "project")
        scope_id = project_id

    return PrincipalMembership(
        workspace_id=workspace_id or project_id or "",
        role=role,
        scope_type=scope_type,
        scope_id=scope_id,
        enterprise_id=enterprise_id,
        team_id=team_id,
        binding_id=_string_value(values, "binding_id"),
        source="oidc_claim",
    )


def _string_value(values: Mapping[str, Any], *names: str) -> str | None:
    for name in names:
        value = values.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
