"""Clerk JWT validation adapter for AUTH-101.

This verifies Clerk-style JWTs with either a configured public key or JWKS URL.
It intentionally does not implement Clerk browser/session flows; AUTH-102 owns
that deeper session behavior.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

import aiohttp
import jwt
from cachetools import TTLCache
from jwt import PyJWKSet
from jwt.exceptions import PyJWTError

from backend.adapters.auth.bearer import RequestAuthenticationError
from backend.adapters.auth.claims_mapping import principal_from_claims
from backend.adapters.auth.providers.base import HostedAuthValidationContext


JsonFetcher = Callable[[str], Awaitable[Mapping[str, Any]]]


@dataclass(frozen=True, slots=True)
class ClerkJWTProviderSettings:
    jwt_key: str
    audience: str = ""
    allowed_authorized_parties: tuple[str, ...] = ()
    allowed_algorithms: tuple[str, ...] = ("RS256",)
    jwks_cache_ttl_seconds: int = 300
    fetch_timeout_seconds: float = 5.0


class ClerkJWTProvider:
    """AUTH-101 Clerk JWT verifier backed by public key or JWKS validation."""

    provider_id = "clerk"

    def __init__(
        self,
        settings: ClerkJWTProviderSettings,
        *,
        jwks_fetcher: JsonFetcher | None = None,
    ) -> None:
        self._settings = settings
        self._jwks_fetcher = jwks_fetcher or self._fetch_json
        self._jwks_cache: TTLCache[str, Mapping[str, Any]] = TTLCache(
            maxsize=4,
            ttl=max(settings.jwks_cache_ttl_seconds, 1),
        )

    async def resolve(
        self,
        token: str | None,
        *,
        validation_context: HostedAuthValidationContext | None = None,
    ):
        return await self.verify(token, validation_context=validation_context)

    async def verify(
        self,
        token: str | None,
        *,
        validation_context: HostedAuthValidationContext | None = None,
    ):
        jwt_key = self._settings.jwt_key.strip()
        if not jwt_key:
            raise RequestAuthenticationError(503, "Clerk JWT verification key is not configured.")
        raw_token = str(token or "").strip()
        if not raw_token:
            raise RequestAuthenticationError(401, "Hosted auth token required.")

        try:
            header = jwt.get_unverified_header(raw_token)
        except PyJWTError as exc:
            raise RequestAuthenticationError(401, "Hosted auth token header is invalid.") from exc

        algorithm = str(header.get("alg") or "").strip()
        if algorithm not in self._settings.allowed_algorithms:
            raise RequestAuthenticationError(401, "Hosted auth token algorithm is not allowed.")

        key = await self._resolve_key(jwt_key, header)
        audiences = tuple(part.strip() for part in self._settings.audience.split(",") if part.strip())
        required = ["exp", "sub"]
        if audiences:
            required.append("aud")
        try:
            claims = jwt.decode(
                raw_token,
                key=key,
                algorithms=list(self._settings.allowed_algorithms),
                audience=list(audiences) if audiences else None,
                options={
                    "require": required,
                    "verify_aud": bool(audiences),
                    "verify_iss": False,
                },
            )
        except PyJWTError as exc:
            raise RequestAuthenticationError(401, "Hosted auth token rejected.") from exc

        self._validate_claims(claims, validation_context or HostedAuthValidationContext())
        issuer = str(claims.get("iss") or "").strip()
        return principal_from_claims(
            claims,
            provider_id=self.provider_id,
            issuer=issuer,
            audience=",".join(audiences) or None,
        )

    async def _resolve_key(self, jwt_key: str, header: Mapping[str, Any]) -> Any:
        if not jwt_key.startswith(("http://", "https://")):
            return jwt_key

        kid = str(header.get("kid") or "").strip()
        if not kid:
            raise RequestAuthenticationError(401, "Hosted auth token is missing key id.")
        jwks = await self._get_jwks(jwt_key)
        key = self._find_key(jwks, kid)
        if key is None:
            jwks = await self._get_jwks(jwt_key, force_refresh=True)
            key = self._find_key(jwks, kid)
        if key is None:
            raise RequestAuthenticationError(401, "Hosted auth token signing key was not found.")
        return key

    async def _get_jwks(self, url: str, *, force_refresh: bool = False) -> Mapping[str, Any]:
        if not force_refresh:
            cached = self._jwks_cache.get(url)
            if cached is not None:
                return cached
        jwks = await self._jwks_fetcher(url)
        if not isinstance(jwks.get("keys"), list):
            raise RequestAuthenticationError(503, "Clerk JWKS metadata is invalid.")
        self._jwks_cache[url] = jwks
        return jwks

    async def _fetch_json(self, url: str) -> Mapping[str, Any]:
        timeout = aiohttp.ClientTimeout(total=self._settings.fetch_timeout_seconds)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    if response.status >= 400:
                        raise RequestAuthenticationError(503, "Clerk JWKS metadata fetch failed.")
                    payload = await response.json()
        except RequestAuthenticationError:
            raise
        except Exception as exc:
            raise RequestAuthenticationError(503, "Clerk JWKS metadata fetch failed.") from exc
        if not isinstance(payload, Mapping):
            raise RequestAuthenticationError(503, "Clerk JWKS metadata response is invalid.")
        return payload

    def _find_key(self, jwks: Mapping[str, Any], kid: str) -> Any | None:
        try:
            return PyJWKSet.from_dict(dict(jwks))[kid].key
        except Exception:
            return None

    def _validate_claims(
        self,
        claims: Mapping[str, Any],
        validation_context: HostedAuthValidationContext,
    ) -> None:
        subject = str(claims.get("sub") or "").strip()
        issuer = str(claims.get("iss") or "").strip()
        if not subject:
            raise RequestAuthenticationError(401, "Hosted auth token is missing subject.")
        if not issuer:
            raise RequestAuthenticationError(401, "Hosted auth token is missing issuer.")

        if validation_context.expected_nonce is not None:
            if str(claims.get("nonce") or "") != validation_context.expected_nonce:
                raise RequestAuthenticationError(401, "Hosted auth token nonce rejected.")
        if validation_context.expected_state is not None:
            presented_state = (
                validation_context.presented_state
                if validation_context.presented_state is not None
                else claims.get("state")
            )
            if str(presented_state or "") != validation_context.expected_state:
                raise RequestAuthenticationError(401, "Hosted auth state rejected.")

        authorized_party = str(claims.get("azp") or claims.get("authorized_party") or "")
        if validation_context.authorized_party is not None and authorized_party != validation_context.authorized_party:
            raise RequestAuthenticationError(401, "Hosted auth authorized party rejected.")
        if self._settings.allowed_authorized_parties and authorized_party not in self._settings.allowed_authorized_parties:
            raise RequestAuthenticationError(401, "Hosted auth authorized party rejected.")
