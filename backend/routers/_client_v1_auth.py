"""Single injectable auth dependency for /api/v1 routes.

OQ-6 / T10-004 — optional LAN bearer token gate.

Design (ADR-008 forward-compat):
  Identity resolution lives in ONE place: ``require_v1_auth``.  It is wired
  onto ``client_v1_router`` via ``dependencies=[Depends(require_v1_auth)]``
  so every /api/v1 route is gated automatically.

  A future workspace-scoped (workspace_id, hashed_token) resolver supersedes
  ``require_v1_auth`` by replacing THIS function — NO handler body needs to
  change.  Single token assumptions must never appear in handler code.

Auth behaviour:
  - CCDASH_API_TOKEN unset (default) → no-op; all /api/v1 requests are allowed.
  - CCDASH_API_TOKEN set → every /api/v1 request must present
    ``Authorization: Bearer <token>``; missing → 401; wrong → 403.

This dependency is SEPARATE from the hosted-API
``CCDASH_API_BEARER_TOKEN`` / ``static_bearer`` provider which applies only
when runtime_profile == "api".  Both mechanisms coexist independently.
"""
from __future__ import annotations

import hmac

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer_scheme = HTTPBearer(auto_error=False)


def _get_configured_token() -> str:
    """Return the configured CCDASH_API_TOKEN (empty string when not set)."""
    # Late import so the dependency is test-patchable via os.environ.
    from backend import config as _cfg
    return getattr(_cfg, "CCDASH_API_TOKEN", "").strip()


async def require_v1_auth(
    request: Request,  # noqa: ARG001 — reserved for future per-request workspace resolution
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> None:
    """No-op when CCDASH_API_TOKEN is unset; validate bearer token when set.

    Forward-compat (ADR-008): this is the single identity-resolution point for
    all /api/v1 routes.  Replace THIS function to upgrade to workspace-scoped
    authentication — no handler rewrite required.
    """
    configured_token = _get_configured_token()
    if not configured_token:
        # Auth not configured — local-trust default, allow all requests.
        return

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required for /api/v1 requests.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not hmac.compare_digest(credentials.credentials, configured_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bearer token rejected for /api/v1 request.",
        )
