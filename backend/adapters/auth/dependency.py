"""FastAPI dependency for resolving AuthContext from the Authorization header.

This module wires the WorkspaceTokenAuthBackend (api/worker profiles) into the
FastAPI dependency injection graph and provides the ``get_auth_context``
dependency that injects an AuthContext into every authenticated endpoint.

The ``x-ccdash-project-id`` header is demoted from a routing input to an
*equality assertion* (ADR-010 §Decision):
- If present and equal to AuthContext.project_id — pass through.
- If present and NOT equal to AuthContext.project_id — 403 with code
  ``workspace_project_mismatch``.
- If absent — no assertion; AuthContext.project_id is used as-is.

Deprecation notice: ``x-ccdash-project-id`` as a routing/selection mechanism
is deprecated as of ADR-010. It will be removed in v2 when repository callers
have been fully migrated to use AuthContext.project_id directly.
"""
from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, Request

from backend.adapters.auth.context import AuthContext
from backend.adapters.auth.workspace_token import WorkspaceTokenAuthBackend
from backend.db.connection import get_connection

logger = logging.getLogger("ccdash.auth.dependency")

# Process-global flag: log the x-ccdash-project-id deprecation warning once.
_PROJECT_ID_HEADER_DEPRECATION_WARNED: bool = False


def _get_workspace_token_backend() -> WorkspaceTokenAuthBackend:
    """Return a per-process WorkspaceTokenAuthBackend singleton."""
    if not hasattr(_get_workspace_token_backend, "_instance"):
        _get_workspace_token_backend._instance = WorkspaceTokenAuthBackend(get_db=get_connection)  # type: ignore[attr-defined]
    return _get_workspace_token_backend._instance  # type: ignore[attr-defined]


async def get_auth_context(
    request: Request,
    backend: WorkspaceTokenAuthBackend = Depends(_get_workspace_token_backend),
) -> AuthContext:
    """Resolve and return the AuthContext for the current request.

    Extracts the ``Authorization: Bearer <secret>`` header, verifies via
    ``WorkspaceTokenAuthBackend.verify()``, and attaches the result to
    ``request.state.auth_context``.

    Raises
    ------
    HTTPException(401, code="invalid_token")
        Bearer header is absent or the secret has no matching active token.
    HTTPException(401, code="revoked_token")
        The secret matched a row with ``revoked_at IS NOT NULL``.
    HTTPException(403, code="workspace_project_mismatch")
        ``x-ccdash-project-id`` header was present but differs from
        ``AuthContext.project_id``.
    """
    # Re-use cached context within the same request to avoid double-verification.
    cached = getattr(request.state, "auth_context", None)
    if isinstance(cached, AuthContext):
        return cached

    secret = _extract_bearer_secret(request)
    if secret is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_token", "message": "Bearer token required."},
        )

    ctx = await backend.verify(secret)
    if ctx is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_token", "message": "Bearer token is invalid."},
        )

    # Equality-only assertion on x-ccdash-project-id (ADR-010 §Decision).
    # NOTE: this header is DEPRECATED as a routing input; it will be removed
    # in v2.  Log a process-level deprecation warning on first occurrence.
    requested_project_id = _header(request, "x-ccdash-project-id")
    if requested_project_id:
        _warn_project_id_header_deprecated()
        if requested_project_id != ctx.project_id:
            logger.warning(
                "auth.dependency: workspace_project_mismatch "
                "(header_project_id=%s, token_project_id=%s, workspace_id=%s)",
                requested_project_id,
                ctx.project_id,
                ctx.workspace_id,
            )
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "workspace_project_mismatch",
                    "message": (
                        "x-ccdash-project-id does not match the project bound to this token."
                    ),
                },
            )

    request.state.auth_context = ctx
    return ctx


# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #


def _extract_bearer_secret(request: Request) -> str | None:
    """Parse ``Authorization: Bearer <secret>`` and return the secret."""
    header = str(request.headers.get("authorization") or "").strip()
    if not header:
        return None
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer":
        return None
    normalized = token.strip()
    return normalized or None


def _header(request: Request, key: str) -> str | None:
    value = request.headers.get(key.lower())
    if value is None:
        return None
    clean = str(value).strip()
    return clean or None


def _warn_project_id_header_deprecated() -> None:
    """Emit a process-level DeprecationWarning for x-ccdash-project-id once.

    ADR-010 §Decision: the x-ccdash-project-id header has been demoted from
    a routing input to an equality-assertion only.  Callers should stop sending
    it; in v2 the header will be ignored entirely and then removed.
    """
    global _PROJECT_ID_HEADER_DEPRECATION_WARNED  # noqa: PLW0603
    if not _PROJECT_ID_HEADER_DEPRECATION_WARNED:
        import warnings

        warnings.warn(
            "x-ccdash-project-id header is deprecated as a routing input per ADR-010. "
            "Stop sending this header; it will be removed in v2. "
            "Project routing is now driven by the workspace token's project_id.",
            DeprecationWarning,
            stacklevel=4,
        )
        logger.warning(
            "auth.dependency: x-ccdash-project-id header observed (DEPRECATED per ADR-010). "
            "This header is now treated as an equality assertion only. "
            "Remove it from clients before the v2 migration."
        )
        _PROJECT_ID_HEADER_DEPRECATION_WARNED = True
