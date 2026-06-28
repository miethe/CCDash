"""AuthContext: immutable per-request authentication context for workspace-scoped tokens.

This module provides the AuthContext dataclass that is injected into every
authenticated request.  It is transport-neutral — the same shape is produced
by WorkspaceTokenAuthBackend (api/worker profiles) and synthesized for the
local profile via AuthContext.synthesize_local().

ADR-008 §Auth Flow defines the shape; this module implements it.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AuthContext:
    """Immutable auth context resolved from a workspace-scoped bearer token.

    Fields
    ------
    workspace_id : str
        The workspace (logical tenant) the token belongs to.
    project_id : str
        The specific project the token is scoped to (v1: 1 token → 1 project).
    token_id : str
        Stable opaque identifier for the resolved token row (used for revocation
        lookups and audit trails).
    scope : str
        Permission scope; one of ``"ingest_write"``, ``"read"``, ``"admin"``.
    """

    workspace_id: str
    project_id: str
    token_id: str
    scope: str

    @classmethod
    def synthesize_local(cls, project_id: str) -> "AuthContext":
        """Return a synthetic AuthContext for the ``local`` runtime profile.

        The local profile does not issue real tokens; this classmethod creates
        an AuthContext with well-known sentinel values that downstream code can
        pass to repository scoping without special-casing the runtime profile.

        Parameters
        ----------
        project_id:
            The bound project id for the local runtime (from
            ``RuntimeContainer.project_binding.project.id``).
        """
        return cls(
            workspace_id="default-local",
            project_id=project_id,
            token_id="local-bearer",
            scope="admin",
        )
