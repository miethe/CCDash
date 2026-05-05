"""Auth provider registry and factory."""
from __future__ import annotations

from collections.abc import Callable, Mapping

from backend.adapters.auth.bearer import RequestAuthenticationError, StaticBearerTokenIdentityProvider
from backend.adapters.auth.local import LocalIdentityProvider
from backend.adapters.auth.providers import (
    ClerkJWTProvider,
    ClerkJWTProviderSettings,
    GenericOIDCProvider,
    HostedAuthProvider,
    HostedAuthValidationContext,
    OIDCProviderSettings,
)
from backend.application.context import Principal, RequestMetadata
from backend.application.ports import IdentityProvider
from backend.config import AuthProviderConfig


ProviderFactory = Callable[[AuthProviderConfig], IdentityProvider]


class HostedBearerTokenIdentityProvider:
    """Bridge hosted token verifiers into the existing request identity port."""

    def __init__(self, provider: HostedAuthProvider) -> None:
        self.provider = provider

    async def get_principal(self, metadata: RequestMetadata, *, runtime_profile: str) -> Principal:
        _ = runtime_profile
        token = self._extract_bearer_token(metadata)
        return await self.provider.verify(token)

    def _extract_bearer_token(self, metadata: RequestMetadata) -> str | None:
        header = str(metadata.headers.get("authorization") or "").strip()
        if not header:
            return None
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer":
            return None
        normalized = token.strip()
        return normalized or None


class AuthProviderRegistry:
    """Registry that maps configured provider names to identity providers."""

    def __init__(self, factories: Mapping[str, ProviderFactory] | None = None) -> None:
        self._factories: dict[str, ProviderFactory] = dict(factories or {})

    @classmethod
    def default(cls) -> "AuthProviderRegistry":
        return cls(
            {
                "local": _local_provider,
                "static_bearer": _static_bearer_provider,
                "oidc": _oidc_provider,
                "clerk": _clerk_provider,
            }
        )

    def register(self, provider: str, factory: ProviderFactory) -> None:
        self._factories[provider] = factory

    def create(self, config: AuthProviderConfig) -> IdentityProvider:
        factory = self._factories.get(config.provider)
        if factory is None:
            raise RequestAuthenticationError(503, f"Unsupported auth provider: {config.provider}.")
        return factory(config)


def create_auth_identity_provider(config: AuthProviderConfig) -> IdentityProvider:
    return AuthProviderRegistry.default().create(config)


def create_hosted_auth_provider(config: AuthProviderConfig) -> HostedAuthProvider:
    if config.provider == "oidc":
        return _generic_oidc_auth_provider(config)
    if config.provider == "clerk":
        return _clerk_auth_provider(config)
    raise RequestAuthenticationError(503, f"Auth provider {config.provider} is not a hosted token provider.")


def _local_provider(config: AuthProviderConfig) -> IdentityProvider:
    _ = config
    return LocalIdentityProvider()


def _static_bearer_provider(config: AuthProviderConfig) -> IdentityProvider:
    _ = config
    return StaticBearerTokenIdentityProvider()


def _oidc_provider(config: AuthProviderConfig) -> IdentityProvider:
    return HostedBearerTokenIdentityProvider(_generic_oidc_auth_provider(config))


def _clerk_provider(config: AuthProviderConfig) -> IdentityProvider:
    return HostedBearerTokenIdentityProvider(_clerk_auth_provider(config))


def _generic_oidc_auth_provider(config: AuthProviderConfig) -> HostedAuthProvider:
    return GenericOIDCProvider(
        OIDCProviderSettings(
            provider_id="oidc",
            issuer=config.oidc_issuer,
            audience=config.oidc_audience,
            jwks_url=config.oidc_jwks_url,
        )
    )


def _clerk_auth_provider(config: AuthProviderConfig) -> HostedAuthProvider:
    return ClerkJWTProvider(
        ClerkJWTProviderSettings(
            jwt_key=config.clerk_jwt_key,
            audience=config.clerk_audience,
            allowed_authorized_parties=config.clerk_authorized_parties,
        )
    )


__all__ = [
    "AuthProviderRegistry",
    "HostedAuthValidationContext",
    "HostedBearerTokenIdentityProvider",
    "create_auth_identity_provider",
    "create_hosted_auth_provider",
]
