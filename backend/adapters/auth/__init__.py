"""Authentication and authorization adapters."""

from backend.adapters.auth.local import LocalIdentityProvider, PermitAllAuthorizationPolicy

__all__ = ["LocalIdentityProvider", "PermitAllAuthorizationPolicy"]
