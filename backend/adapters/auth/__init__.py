"""Authentication and authorization adapters."""

from backend.adapters.auth.bearer import RequestAuthenticationError, StaticBearerTokenIdentityProvider
from backend.adapters.auth.local import LocalIdentityProvider, PermitAllAuthorizationPolicy
from backend.adapters.auth.provider_factory import (
    AuthProviderRegistry,
    HostedBearerTokenIdentityProvider,
    create_auth_identity_provider,
    create_hosted_auth_provider,
)
from backend.adapters.auth.providers import (
    ClerkJWTProvider,
    ClerkJWTProviderSettings,
    GenericOIDCProvider,
    HostedAuthProvider,
    HostedAuthValidationContext,
    OIDCProviderSettings,
)

__all__ = [
    "AuthProviderRegistry",
    "ClerkJWTProvider",
    "ClerkJWTProviderSettings",
    "GenericOIDCProvider",
    "HostedAuthProvider",
    "HostedAuthValidationContext",
    "HostedBearerTokenIdentityProvider",
    "LocalIdentityProvider",
    "OIDCProviderSettings",
    "PermitAllAuthorizationPolicy",
    "RequestAuthenticationError",
    "StaticBearerTokenIdentityProvider",
    "create_auth_identity_provider",
    "create_hosted_auth_provider",
]
