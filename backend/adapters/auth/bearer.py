"""Minimal bearer-token auth adapter for hosted API requests."""
from __future__ import annotations

import os
from typing import Any

from backend.application.context import Principal, PrincipalMembership, RequestMetadata


class RequestAuthenticationError(Exception):
    """Raised when request authentication fails at the identity-provider seam."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class StaticBearerTokenIdentityProvider:
    """Validate a shared bearer token for protected hosted API routes."""

    BEARER_PROTECTED_PATH_PREFIX = "/api/v1"
    ANONYMOUS_FALLBACK_WARNING_CODE = "anonymous_fallback_outside_bearer_path"

    def __init__(self, *, token_env_var: str = "CCDASH_API_BEARER_TOKEN") -> None:
        self._token_env_var = token_env_var

    @classmethod
    def describe_runtime_guardrail(
        cls,
        *,
        runtime_profile: str,
        bearer_token_configured: bool,
    ) -> dict[str, Any]:
        applies = runtime_profile == "api"
        warnings = (
            [
                {
                    "code": cls.ANONYMOUS_FALLBACK_WARNING_CODE,
                    "category": "auth",
                    "severity": "warn",
                    "summary": (
                        "Hosted bearer auth only protects /api/v1; other hosted routes may still allow anonymous access."
                    ),
                }
            ]
            if applies
            else []
        )
        return {
            "mode": "path_scoped_static_bearer" if applies else "not_applicable",
            "applies": applies,
            "bearerTokenConfigured": bearer_token_configured if applies else False,
            "bearerProtectedPathPrefix": cls.BEARER_PROTECTED_PATH_PREFIX if applies else None,
            "anonymousFallbackEnabled": applies,
            "anonymousFallbackReasonCode": cls.ANONYMOUS_FALLBACK_WARNING_CODE if applies else None,
            "summary": (
                "Hosted API auth is constrained to the bearer-protected /api/v1 path boundary."
                if applies
                else "This runtime does not use the hosted bearer path boundary."
            ),
            "warnings": warnings,
            "warningCodes": [str(warning["code"]) for warning in warnings],
        }

    async def get_principal(self, metadata: RequestMetadata, *, runtime_profile: str) -> Principal:
        workspace_id = str(metadata.headers.get("x-ccdash-project-id") or "").strip()
        memberships = (
            (PrincipalMembership(workspace_id=workspace_id, role="operator"),)
            if workspace_id
            else ()
        )
        bearer_required = self._requires_bearer_auth(metadata, runtime_profile=runtime_profile)
        presented_token = self._extract_bearer_token(metadata)

        if not bearer_required and presented_token is None:
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

        if presented_token is None:
            raise RequestAuthenticationError(401, "Bearer token required for /api/v1 requests.")
        if presented_token != expected_token:
            detail = (
                "Bearer token rejected for /api/v1 request."
                if bearer_required
                else "Bearer token rejected for API request."
            )
            raise RequestAuthenticationError(403, detail)

        return Principal(
            subject="api:bearer-client",
            display_name="Bearer API Client",
            auth_mode="bearer",
            is_authenticated=True,
            groups=(runtime_profile, "api", "authenticated"),
            memberships=memberships,
        )

    def _requires_bearer_auth(self, metadata: RequestMetadata, *, runtime_profile: str) -> bool:
        return runtime_profile == "api" and str(metadata.path or "").startswith(
            self.BEARER_PROTECTED_PATH_PREFIX
        )

    def _extract_bearer_token(self, metadata: RequestMetadata) -> str | None:
        header = str(metadata.headers.get("authorization") or "").strip()
        if not header:
            return None
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer":
            return None
        normalized = token.strip()
        return normalized or None
