"""Shared CCDash -> SkillMeat trust metadata contract.

Hosted CCDash deployments call SkillMeat under the same provider/delegation
model used for inbound auth. The outbound contract is intentionally metadata
only: configured SkillMeat API keys still act as explicit service credentials,
while Clerk/OIDC/static hosted principals add deterministic delegation headers
that preserve the original subject and request scope for SkillMeat AAA.
"""
from __future__ import annotations

from dataclasses import dataclass

from backend.application.context import RequestContext


TRUST_CONTRACT_VERSION = "ccdash-skillmeat-shared-auth-v1"


@dataclass(frozen=True, slots=True)
class SkillMeatTrustMetadata:
    """Provider-neutral trust metadata attached to outbound SkillMeat calls."""

    provider_id: str
    principal_subject: str
    principal_stable_subject: str
    principal_kind: str
    auth_mode: str
    delegation_reason: str
    issuer: str = ""
    audience: str = ""
    enterprise_id: str = ""
    team_id: str = ""
    workspace_id: str = ""
    project_id: str = ""
    scopes: tuple[str, ...] = ()
    scope_chain: tuple[tuple[str, str], ...] = ()
    roles: tuple[str, ...] = ()
    trace_id: str = ""
    contract: str = TRUST_CONTRACT_VERSION
    delegation_mode: str = "shared-provider-trust"

    def as_headers(self) -> dict[str, str]:
        headers = {
            "X-CCDash-Trust-Contract": self.contract,
            "X-CCDash-Delegation-Mode": self.delegation_mode,
            "X-CCDash-Delegation-Reason": self.delegation_reason,
            "X-CCDash-Auth-Provider": self.provider_id,
            "X-CCDash-Auth-Mode": self.auth_mode,
            "X-CCDash-Principal-Subject": self.principal_subject,
            "X-CCDash-Principal-Stable-Subject": self.principal_stable_subject,
            "X-CCDash-Principal-Kind": self.principal_kind,
        }
        optional = {
            "X-CCDash-Auth-Issuer": self.issuer,
            "X-CCDash-Auth-Audience": self.audience,
            "X-CCDash-Enterprise-Id": self.enterprise_id,
            "X-CCDash-Team-Id": self.team_id,
            "X-CCDash-Workspace-Id": self.workspace_id,
            "X-CCDash-Project-Id": self.project_id,
            "X-CCDash-Auth-Scopes": ",".join(self.scopes),
            "X-CCDash-Scope-Chain": ";".join(f"{scope}:{scope_id}" for scope, scope_id in self.scope_chain),
            "X-CCDash-Scope-Roles": ";".join(self.roles),
            "X-CCDash-Trace-Id": self.trace_id,
        }
        headers.update({key: value for key, value in optional.items() if value})
        return {key: _header_value(value) for key, value in headers.items()}


def build_skillmeat_trust_metadata(
    context: RequestContext | None,
    *,
    delegation_reason: str,
) -> SkillMeatTrustMetadata | None:
    """Build hosted trust metadata from request context, or None for local/no-auth."""
    if context is None or context.is_local_mode:
        return None

    principal = context.principal
    provider = principal.provider
    if provider is None or not provider.hosted or not principal.is_authenticated:
        return None

    return SkillMeatTrustMetadata(
        provider_id=str(provider.provider_id or principal.auth_mode),
        issuer=str(provider.issuer or ""),
        audience=str(provider.audience or ""),
        principal_subject=str(principal.subject),
        principal_stable_subject=str(principal.stable_subject),
        principal_kind=str(principal.kind),
        auth_mode=str(principal.auth_mode),
        delegation_reason=delegation_reason,
        enterprise_id=str(context.effective_enterprise_id or ""),
        team_id=str(context.tenancy.team_id or ""),
        workspace_id=str(context.tenancy.workspace_id or ""),
        project_id=str(context.tenancy.project_id or ""),
        scopes=tuple(sorted({scope for scope in principal.scopes if scope})),
        scope_chain=tuple(context.tenancy.scope_chain),
        roles=_scope_roles(context),
        trace_id=str(context.trace.request_id or ""),
    )


def _scope_roles(context: RequestContext) -> tuple[str, ...]:
    roles = []
    for binding in context.scope_bindings:
        if not binding.role:
            continue
        roles.append(f"{binding.scope_type}:{binding.scope_id}={binding.role}")
    return tuple(sorted(roles))


def _header_value(value: str) -> str:
    return str(value).replace("\r", " ").replace("\n", " ").strip()

