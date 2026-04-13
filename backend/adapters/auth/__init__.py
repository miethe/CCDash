"""Authentication and authorization adapters."""

from backend.adapters.auth.bearer import RequestAuthenticationError, StaticBearerTokenIdentityProvider
from backend.adapters.auth.local import LocalIdentityProvider, PermitAllAuthorizationPolicy

__all__ = [
    "LocalIdentityProvider",
    "PermitAllAuthorizationPolicy",
    "RequestAuthenticationError",
    "StaticBearerTokenIdentityProvider",
]
