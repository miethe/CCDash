"""Provider-neutral claim to CCDash scope mapping.

The mapper keeps provider-specific token shapes at the auth adapter edge and
emits the existing Principal/PrincipalMembership structures consumed by RBAC.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import re
from typing import Any, cast

from backend.application.context import (
    AuthProviderMetadata,
    Principal,
    PrincipalMembership,
    PrincipalSubject,
    RequestMetadata,
    ScopeType,
)


_CLAIM_ID_PATTERN = re.compile(r"[^a-zA-Z0-9_.:-]+")


@dataclass(frozen=True, slots=True)
class ClaimScopeSelection:
    """Deterministic scope identifiers resolved from principal claims."""

    enterprise_id: str | None = None
    enterprise_name: str | None = None
    team_id: str | None = None
    team_name: str | None = None
    workspace_id: str | None = None
    project_id: str | None = None


def principal_from_claims(
    claims: Mapping[str, Any],
    *,
    provider_id: str,
    issuer: str,
    audience: str | None,
    auth_mode: str = "oidc",
) -> Principal:
    """Build a Principal from validated Local/Clerk/OIDC-style claims."""
    subject = _string_value(claims, "sub", "subject", "user_id", "id")
    if not subject:
        raise ValueError("Provider claims are missing a subject.")

    display_name = _first_claim(claims, ("name", "preferred_username", "username", "email")) or subject
    email = _first_claim(claims, ("email", "primary_email"))
    groups = _unique(
        (
            *_claim_values(claims, ("groups", "group", "ccdash_groups")),
            *_claim_values(claims, ("roles", "role", "org_role")),
        )
    )
    scopes = _unique((*_scope_values(claims.get("scope")), *_scope_values(claims.get("scp"))))
    tenant_id = _enterprise_id_from_claims(claims)

    return Principal(
        subject=f"{provider_id}:{subject}",
        display_name=display_name,
        auth_mode=auth_mode,
        email=email,
        is_authenticated=True,
        groups=groups,
        memberships=memberships_from_claims(claims, provider_id=provider_id),
        provider=AuthProviderMetadata(
            provider_id=provider_id,
            issuer=issuer,
            audience=audience,
            tenant_id=tenant_id,
            hosted=provider_id != "local",
        ),
        normalized_subject=PrincipalSubject(
            subject=subject,
            kind="user",
            provider_id=provider_id,
            issuer=issuer,
        ),
        scopes=scopes,
    )


def memberships_from_claims(
    claims: Mapping[str, Any],
    *,
    provider_id: str,
) -> tuple[PrincipalMembership, ...]:
    """Map explicit and provider-native scope claims into RBAC memberships."""
    memberships: list[PrincipalMembership] = []
    enterprise_id = _enterprise_id_from_claims(claims)

    explicit = claims.get("ccdash_memberships", claims.get("memberships"))
    if isinstance(explicit, Iterable) and not isinstance(explicit, (str, bytes, Mapping)):
        for item in explicit:
            if isinstance(item, Mapping):
                membership = _membership_from_mapping(item, provider_id=provider_id)
                if membership is not None:
                    memberships.append(membership)

    direct = _membership_from_mapping(claims, provider_id=provider_id)
    if direct is not None:
        memberships.append(direct)

    role = _role_from_claims(claims)
    for team_id in _team_ids_from_claims(claims, enterprise_id=enterprise_id):
        memberships.append(
            PrincipalMembership(
                workspace_id=team_id,
                role=role,
                scope_type="team",
                scope_id=team_id,
                enterprise_id=enterprise_id,
                team_id=team_id,
                binding_id=f"{provider_id}:team:{team_id}",
                source=f"{provider_id}_claim",
            )
        )

    deduped: dict[tuple[str, str, str, str | None], PrincipalMembership] = {}
    for membership in memberships:
        key = (
            str(membership.scope_type),
            membership.effective_scope_id,
            membership.role,
            membership.enterprise_id,
        )
        deduped.setdefault(key, membership)
    return tuple(deduped.values())


def select_claim_scope(
    principal: Principal,
    metadata: RequestMetadata,
) -> ClaimScopeSelection:
    """Select request scope ids from a hosted principal and explicit headers.

    Headers are request-local selectors. Principal memberships provide the
    deterministic fallback for hosted requests when no selector is supplied.
    """
    enterprise_id = principal.provider.tenant_id if principal.provider is not None else None
    enterprise_name = _header(metadata, "x-ccdash-enterprise-name")
    team_id: str | None = None
    team_name = _header(metadata, "x-ccdash-team-name")
    workspace_id = _header(metadata, "x-ccdash-workspace-id")
    project_id = _header(metadata, "x-ccdash-project-id")

    for membership in principal.memberships:
        enterprise_id = enterprise_id or membership.enterprise_id
        if membership.scope_type == "team":
            team_id = team_id or membership.effective_scope_id
        else:
            team_id = team_id or membership.team_id
        if membership.scope_type == "workspace":
            workspace_id = workspace_id or membership.effective_scope_id
        if membership.scope_type == "project":
            project_id = project_id or membership.effective_scope_id
            workspace_id = workspace_id or membership.workspace_id

    team_id = team_id or _header(metadata, "x-ccdash-team-id")

    return ClaimScopeSelection(
        enterprise_id=enterprise_id,
        enterprise_name=enterprise_name,
        team_id=team_id,
        team_name=team_name,
        workspace_id=workspace_id,
        project_id=project_id,
    )


def _membership_from_mapping(
    values: Mapping[str, Any],
    *,
    provider_id: str,
) -> PrincipalMembership | None:
    enterprise_id = _enterprise_id_from_claims(values)
    workspace_id = _string_value(values, "workspace_id", "workspace", "ccdash_workspace_id")
    project_id = _string_value(values, "project_id", "project", "ccdash_project_id")
    team_id = _string_value(values, "team_id", "team", "ccdash_team_id")

    scope_type: ScopeType | None = None
    scope_id: str | None = None
    if project_id:
        scope_type = cast(ScopeType, "project")
        scope_id = project_id
    elif workspace_id:
        scope_type = cast(ScopeType, "workspace")
        scope_id = workspace_id
    elif team_id:
        scope_type = cast(ScopeType, "team")
        scope_id = team_id
    elif enterprise_id:
        scope_type = cast(ScopeType, "enterprise")
        scope_id = enterprise_id

    if scope_type is None or scope_id is None:
        return None

    role = _role_from_claims(values)
    return PrincipalMembership(
        workspace_id=workspace_id or project_id or team_id or enterprise_id or "",
        role=role,
        scope_type=scope_type,
        scope_id=scope_id,
        enterprise_id=enterprise_id,
        team_id=team_id,
        binding_id=_string_value(values, "binding_id") or f"{provider_id}:{scope_type}:{scope_id}:{role}",
        source=f"{provider_id}_claim",
    )


def _team_ids_from_claims(
    claims: Mapping[str, Any],
    *,
    enterprise_id: str | None,
) -> tuple[str, ...]:
    explicit = _string_value(claims, "team_id", "team", "ccdash_team_id")
    candidates: list[str] = [explicit] if explicit else []
    candidates.extend(_claim_values(claims, ("groups", "group", "ccdash_groups")))

    normalized: list[str] = []
    for candidate in candidates:
        team_id = _normalize_claim_id(candidate)
        if not team_id:
            continue
        if enterprise_id and team_id.startswith(f"{enterprise_id}:"):
            team_id = team_id[len(enterprise_id) + 1 :]
        normalized.append(team_id)
    return _unique(normalized)


def _enterprise_id_from_claims(claims: Mapping[str, Any]) -> str | None:
    value = _first_claim(
        claims,
        (
            "ccdash_enterprise_id",
            "enterprise_id",
            "tenant_id",
            "tid",
            "org_id",
            "organization_id",
            "organization",
        ),
    )
    return _normalize_claim_id(value) if value else None


def _role_from_claims(claims: Mapping[str, Any]) -> str:
    role = _string_value(claims, "ccdash_role", "role", "org_role")
    if role:
        return role
    roles = _claim_values(claims, ("roles", "ccdash_roles"))
    return roles[0] if roles else "member"


def _first_claim(claims: Mapping[str, Any], names: Iterable[str]) -> str | None:
    for name in names:
        value = claims.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, Mapping):
            nested = _string_value(value, "id", "slug", "name")
            if nested:
                return nested
    return None


def _claim_values(claims: Mapping[str, Any], names: Iterable[str]) -> tuple[str, ...]:
    values: list[str] = []
    for name in names:
        value = claims.get(name)
        if isinstance(value, str):
            parts = value.split() if " " in value else (value,)
        elif isinstance(value, Iterable) and not isinstance(value, (str, bytes, Mapping)):
            parts = value
        else:
            parts = ()
        for part in parts:
            if not isinstance(part, (str, int, float)):
                continue
            normalized = str(part).strip()
            if normalized:
                values.append(normalized)
    return tuple(values)


def _scope_values(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split() if part.strip())
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, Mapping)):
        return tuple(
            str(part).strip()
            for part in value
            if isinstance(part, (str, int, float)) and str(part).strip()
        )
    return ()


def _string_value(values: Mapping[str, Any], *names: str) -> str | None:
    for name in names:
        value = values.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _header(metadata: RequestMetadata, name: str) -> str | None:
    value = metadata.headers.get(name)
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_claim_id(value: str | None) -> str | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    normalized = normalized.replace("/", ":").lower()
    normalized = _CLAIM_ID_PATTERN.sub("-", normalized).strip("-")
    return normalized or None


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            unique.append(value)
    return tuple(unique)
