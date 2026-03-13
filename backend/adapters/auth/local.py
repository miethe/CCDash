"""Local no-auth identity and authorization adapters."""
from __future__ import annotations

from backend.application.context import Principal, PrincipalMembership, RequestContext, RequestMetadata
from backend.application.ports import AuthorizationDecision


class LocalIdentityProvider:
    async def get_principal(self, metadata: RequestMetadata, *, runtime_profile: str) -> Principal:
        workspace_id = str(metadata.headers.get("x-ccdash-project-id") or "").strip()
        memberships = (
            (PrincipalMembership(workspace_id=workspace_id, role="owner"),)
            if workspace_id
            else ()
        )
        return Principal(
            subject=f"{runtime_profile}:local-operator",
            display_name="Local Operator",
            auth_mode="local",
            is_authenticated=True,
            groups=("local", runtime_profile),
            memberships=memberships,
        )


class PermitAllAuthorizationPolicy:
    async def authorize(
        self,
        context: RequestContext,
        *,
        action: str,
        resource: str | None = None,
    ) -> AuthorizationDecision:
        _ = (context, action, resource)
        return AuthorizationDecision(
            allowed=True,
            reason="Local and test profiles use a permissive authorization baseline.",
        )
