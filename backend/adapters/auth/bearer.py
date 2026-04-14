"""Minimal bearer-token auth adapter for hosted API requests."""
from __future__ import annotations

import os

from backend.application.context import Principal, PrincipalMembership, RequestMetadata


class RequestAuthenticationError(Exception):
    """Raised when request authentication fails at the identity-provider seam."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class StaticBearerTokenIdentityProvider:
    """Validate a shared bearer token for protected hosted API routes."""

    def __init__(self, *, token_env_var: str = "CCDASH_API_BEARER_TOKEN") -> None:
        self._token_env_var = token_env_var

    async def get_principal(self, metadata: RequestMetadata, *, runtime_profile: str) -> Principal:
        workspace_id = str(metadata.headers.get("x-ccdash-project-id") or "").strip()
        memberships = (
            (PrincipalMembership(workspace_id=workspace_id, role="operator"),)
            if workspace_id
            else ()
        )

        if not self._requires_bearer_auth(metadata, runtime_profile=runtime_profile):
            return Principal(
                subject=f"{runtime_profile}:anonymous-api-client",
                display_name="Anonymous API Client",
                auth_mode="anonymous",
                is_authenticated=False,
                groups=(runtime_profile, "api"),
                memberships=memberships,
            )

        expected_token = os.getenv(self._token_env_var, "").strip()
        if not expected_token:
            raise RequestAuthenticationError(
                503,
                f"API bearer auth is enabled but {self._token_env_var} is not configured.",
            )

        presented_token = self._extract_bearer_token(metadata)
        if presented_token is None:
            raise RequestAuthenticationError(401, "Bearer token required for /api/v1 requests.")
        if presented_token != expected_token:
            raise RequestAuthenticationError(403, "Bearer token rejected for /api/v1 request.")

        return Principal(
            subject="api:bearer-client",
            display_name="Bearer API Client",
            auth_mode="bearer",
            is_authenticated=True,
            groups=(runtime_profile, "api", "authenticated"),
            memberships=memberships,
        )

    def _requires_bearer_auth(self, metadata: RequestMetadata, *, runtime_profile: str) -> bool:
        return runtime_profile == "api" and str(metadata.path or "").startswith("/api/v1")

    def _extract_bearer_token(self, metadata: RequestMetadata) -> str | None:
        header = str(metadata.headers.get("authorization") or "").strip()
        if not header:
            return None
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer":
            return None
        normalized = token.strip()
        return normalized or None
