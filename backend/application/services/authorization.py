"""Role-binding authorization evaluator for CCDash RBAC."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Mapping

from backend.application.context import PrincipalMembership, RequestContext
from backend.application.ports import AuthorizationDecision


PERMISSIONS: frozenset[str] = frozenset(
    {
        "project:list",
        "project:read",
        "project:create",
        "project:update",
        "project:switch",
        "document:read",
        "document.link:create",
        "document.metadata:read",
        "task:read",
        "planning.task:update",
        "session:read",
        "session.artifact:read",
        "session.timeline:read",
        "test:read",
        "test.metrics:read",
        "test.sync:trigger",
        "test.run:ingest",
        "test.mapping:import",
        "test.mapping:backfill",
        "execution:read",
        "execution.run:create",
        "execution.run:approve",
        "execution.run:cancel",
        "execution.run:retry",
        "execution.launch:prepare",
        "execution.launch:start",
        "worktree_context:create",
        "worktree_context:update",
        "integration:read",
        "integration.skillmeat:sync",
        "integration.skillmeat:backfill",
        "integration.skillmeat.memory:generate",
        "integration.skillmeat.memory:review",
        "integration.skillmeat.memory:publish",
        "integration.github:read_settings",
        "integration.github:update_settings",
        "integration.github:validate",
        "integration.github.workspace:refresh",
        "integration.github:write_probe",
        "analytics:read",
        "analytics.export:prometheus",
        "analytics.alert:create",
        "analytics.alert:update",
        "analytics.alert:delete",
        "analytics.notification:read",
        "admin.settings:read",
        "admin.settings:update",
        "admin.user:manage",
        "admin.role:manage",
        "admin.audit:read",
        "codebase:read_tree",
        "codebase:file_read",
        "codebase:activity_read",
        "cache:read_status",
        "cache.operation:read",
        "cache.sync:trigger",
        "cache.links:rebuild",
        "cache.paths:sync",
        "entity_link:create",
        "link_audit:run",
        "live:subscribe",
        "live.execution:subscribe",
        "live.session:subscribe",
        "live.feature:subscribe",
        "live.project:subscribe",
        "session_mapping:read",
        "session_mapping:diagnose",
        "session_mapping:update",
        "admin.pricing:read",
        "admin.pricing:update",
        "admin.pricing:sync",
        "admin.pricing:reset",
        "admin.pricing:delete",
        "feature:read",
        "feature.rollup:compute",
        "report.aar:generate",
        "planning.open_question:resolve",
        "planning.writeback:sync",
    }
)


_READ_PERMISSIONS = frozenset(
    permission
    for permission in PERMISSIONS
    if permission.endswith(":read")
    or permission.endswith(".metadata:read")
    or permission.endswith(".artifact:read")
    or permission.endswith(".timeline:read")
    or permission.endswith(".metrics:read")
    or permission.endswith(":read_tree")
    or permission.endswith(":activity_read")
    or permission.endswith(":read_status")
    or permission.endswith(".operation:read")
    or permission.endswith(":diagnose")
    or permission.endswith(":switch")
)

_PROJECT_MEMBER_PERMISSIONS = frozenset(
    {
        "project:read",
        "project:update",
        "project:switch",
        "document:read",
        "document.link:create",
        "document.metadata:read",
        "task:read",
        "planning.task:update",
        "session:read",
        "session.artifact:read",
        "session.timeline:read",
        "test:read",
        "test.metrics:read",
        "test.sync:trigger",
        "test.run:ingest",
        "test.mapping:import",
        "test.mapping:backfill",
        "execution:read",
        "execution.run:create",
        "execution.run:cancel",
        "execution.run:retry",
        "execution.launch:prepare",
        "worktree_context:create",
        "worktree_context:update",
        "integration:read",
        "integration.github.workspace:refresh",
        "analytics:read",
        "analytics.alert:create",
        "analytics.alert:update",
        "analytics.alert:delete",
        "analytics.notification:read",
        "codebase:read_tree",
        "codebase:file_read",
        "codebase:activity_read",
        "cache:read_status",
        "cache.operation:read",
        "cache.sync:trigger",
        "cache.links:rebuild",
        "entity_link:create",
        "link_audit:run",
        "live:subscribe",
        "live.execution:subscribe",
        "live.session:subscribe",
        "live.feature:subscribe",
        "live.project:subscribe",
        "session_mapping:read",
        "session_mapping:diagnose",
        "session_mapping:update",
        "feature:read",
        "feature.rollup:compute",
        "report.aar:generate",
        "planning.open_question:resolve",
        "planning.writeback:sync",
    }
)

ROLE_PERMISSIONS: Mapping[str, frozenset[str]] = {
    "EA": PERMISSIONS,
    "TA": PERMISSIONS
    - frozenset(
        {
            "admin.settings:update",
            "admin.pricing:update",
            "admin.pricing:sync",
            "admin.pricing:reset",
            "admin.pricing:delete",
            "cache.paths:sync",
        }
    ),
    "PM": _PROJECT_MEMBER_PERMISSIONS,
    "PV": frozenset(
        {
            "project:list",
            "project:read",
            "project:switch",
            "document:read",
            "document.metadata:read",
            "task:read",
            "session:read",
            "session.artifact:read",
            "session.timeline:read",
            "test:read",
            "analytics:read",
            "codebase:read_tree",
            "codebase:activity_read",
            "live:subscribe",
            "live.session:subscribe",
            "live.feature:subscribe",
            "live.project:subscribe",
            "session_mapping:read",
            "session_mapping:diagnose",
            "feature:read",
            "report.aar:generate",
        }
    ),
    "IO": frozenset(
        permission for permission in PERMISSIONS if permission == "integration:read" or permission.startswith("integration.")
    ),
    "XA": frozenset(
        {
            "execution:read",
            "execution.run:approve",
            "execution.launch:start",
            "live:subscribe",
            "live.execution:subscribe",
        }
    ),
    "AA": _READ_PERMISSIONS
    | frozenset(
        {
            "analytics.export:prometheus",
            "analytics.notification:read",
            "admin.audit:read",
            "link_audit:run",
            "report.aar:generate",
        }
    ),
}

ROLE_ALIASES: Mapping[str, str] = {
    "enterprise_admin": "EA",
    "enterprise-admin": "EA",
    "enterprise:admin": "EA",
    "team_admin": "TA",
    "team-admin": "TA",
    "team:admin": "TA",
    "project_maintainer": "PM",
    "project-maintainer": "PM",
    "project:maintainer": "PM",
    "project_owner": "PM",
    "project-owner": "PM",
    "maintainer": "PM",
    "owner": "PM",
    "operator": "PM",
    "admin": "PM",
    "project_viewer": "PV",
    "project-viewer": "PV",
    "project:viewer": "PV",
    "viewer": "PV",
    "member": "PV",
    "integration_operator": "IO",
    "integration-operator": "IO",
    "integration:operator": "IO",
    "execution_approver": "XA",
    "execution-approver": "XA",
    "execution:approver": "XA",
    "analyst": "AA",
    "auditor": "AA",
    "analyst_auditor": "AA",
    "analyst-auditor": "AA",
}

_SCOPE_DEPTH: Mapping[str, int] = {
    "user": 0,
    "enterprise": 1,
    "team": 2,
    "workspace": 3,
    "project": 4,
    "owned_entity": 5,
}
_RESOURCE_PATTERN = re.compile(
    r"^(?P<scope>user|enterprise|team|workspace|project|owned_entity)[:/](?P<scope_id>[^:/]+)$"
)


@dataclass(frozen=True, slots=True)
class _Grant:
    role: str
    permission: str
    source: str
    scope_type: str
    scope_id: str | None
    specificity: int
    deny: bool = False


class RoleBindingAuthorizationPolicy:
    """Evaluate principal roles, direct scopes, and request scope containment."""

    async def authorize(
        self,
        context: RequestContext,
        *,
        action: str,
        resource: str | None = None,
    ) -> AuthorizationDecision:
        permission = normalize_permission(action)
        if not context.principal.is_authenticated:
            return AuthorizationDecision(
                allowed=False,
                code="principal_unauthenticated",
                reason="Principal is not authenticated.",
            )

        target_scope = _target_scope(context, resource)
        grants = list(_direct_scope_grants(context, permission, target_scope))
        for membership in context.principal.memberships:
            grants.extend(_membership_grants(context, membership, permission, target_scope))

        matching_denies = [grant for grant in grants if grant.deny and grant.permission == permission]
        if matching_denies:
            grant = max(matching_denies, key=lambda item: item.specificity)
            return AuthorizationDecision(
                allowed=False,
                code="permission_explicitly_denied",
                reason=(
                    f"Permission '{permission}' is explicitly denied by {grant.source} "
                    f"at {grant.scope_type}:{grant.scope_id or '*'}."
                ),
            )

        matching_allows = [grant for grant in grants if not grant.deny and grant.permission == permission]
        if matching_allows:
            grant = max(matching_allows, key=lambda item: item.specificity)
            return AuthorizationDecision(
                allowed=True,
                code="permission_allowed",
                reason=(
                    f"Permission '{permission}' is allowed by role '{grant.role}' from {grant.source} "
                    f"at {grant.scope_type}:{grant.scope_id or '*'}."
                ),
            )

        return AuthorizationDecision(
            allowed=False,
            code="permission_not_granted",
            reason=f"Permission '{permission}' is not granted for the requested scope.",
        )


def normalize_permission(value: str) -> str:
    permission = str(value or "").strip()
    if not permission:
        return ""
    if permission in PERMISSIONS:
        return permission
    head, sep, tail = permission.partition(":")
    legacy = f"{tail}:{head}" if sep and tail else permission
    if legacy in PERMISSIONS:
        return legacy
    return permission


def _direct_scope_grants(
    context: RequestContext,
    permission: str,
    target_scope: tuple[str | None, str | None],
) -> Iterable[_Grant]:
    for raw_scope in context.principal.scopes:
        effect, scope_permission = _scope_effect(raw_scope)
        normalized = normalize_permission(scope_permission)
        if not _permission_matches_scope(normalized, permission):
            continue
        if not _principal_scope_contains(context, target_scope):
            continue
        yield _Grant(
            role="direct_scope",
            permission=permission,
            source=f"principal.scopes:{raw_scope}",
            scope_type=target_scope[0] or "request",
            scope_id=target_scope[1],
            specificity=_SCOPE_DEPTH.get(target_scope[0] or "", 0),
            deny=effect == "deny",
        )


def _membership_grants(
    context: RequestContext,
    membership: PrincipalMembership,
    permission: str,
    target_scope: tuple[str | None, str | None],
) -> Iterable[_Grant]:
    role_effect, role_name = _role_effect(membership.role)
    if role_effect == "deny" and normalize_permission(role_name) in {permission, "*"}:
        permissions = frozenset({permission})
        normalized_role = role_name
    else:
        normalized_role = _normalize_role(role_name)
        permissions = ROLE_PERMISSIONS.get(normalized_role, frozenset())
    if permission not in permissions:
        return ()
    if not _membership_contains(context, membership, target_scope):
        return ()
    return (
        _Grant(
            role=normalized_role,
            permission=permission,
            source=f"membership:{membership.binding_id or membership.source or membership.role}",
            scope_type=str(membership.scope_type),
            scope_id=membership.effective_scope_id,
            specificity=_SCOPE_DEPTH.get(str(membership.scope_type), 0),
            deny=role_effect == "deny",
        ),
    )


def _role_effect(raw_role: str) -> tuple[str, str]:
    role = str(raw_role or "").strip()
    lowered = role.lower()
    for prefix in ("deny:", "deny.", "deny/"):
        if lowered.startswith(prefix):
            return "deny", role[len(prefix) :].strip()
    return "allow", role


def _scope_effect(raw_scope: str) -> tuple[str, str]:
    scope = str(raw_scope or "").strip()
    lowered = scope.lower()
    for prefix in ("deny:", "deny.", "deny/"):
        if lowered.startswith(prefix):
            return "deny", scope[len(prefix) :].strip()
    return "allow", scope


def _normalize_role(role: str) -> str:
    value = str(role or "").strip()
    if value.upper() in ROLE_PERMISSIONS:
        return value.upper()
    return ROLE_ALIASES.get(value.lower(), value)


def _permission_matches_scope(scope_permission: str, permission: str) -> bool:
    if scope_permission == "*":
        return True
    if scope_permission == permission:
        return True
    if scope_permission.endswith(":*"):
        return permission.startswith(scope_permission[:-1])
    if scope_permission.endswith(".*"):
        return permission.startswith(scope_permission[:-1])
    return False


def _target_scope(context: RequestContext, resource: str | None) -> tuple[str | None, str | None]:
    if resource:
        match = _RESOURCE_PATTERN.match(str(resource).strip())
        if match:
            return match.group("scope"), match.group("scope_id")
    if context.project is not None:
        return "project", context.project.project_id
    if context.workspace is not None:
        return "workspace", context.workspace.workspace_id
    if context.team is not None:
        return "team", context.team.team_id
    if context.enterprise is not None:
        return "enterprise", context.enterprise.enterprise_id
    return None, None


def _principal_scope_contains(
    context: RequestContext,
    target_scope: tuple[str | None, str | None],
) -> bool:
    target_type, target_id = target_scope
    if target_type is None:
        return True
    return _request_scope_id(context, target_type) == target_id


def _membership_contains(
    context: RequestContext,
    membership: PrincipalMembership,
    target_scope: tuple[str | None, str | None],
) -> bool:
    target_type, target_id = target_scope
    binding_type = str(membership.scope_type)
    binding_id = membership.effective_scope_id
    if not _membership_ancestry_matches(context, membership):
        return False
    if target_type is None:
        return True
    if binding_type == "user":
        return binding_id in {context.principal.subject, context.principal.stable_subject}
    if binding_type == "owned_entity":
        return target_type == "owned_entity" and binding_id == target_id
    binding_depth = _SCOPE_DEPTH.get(binding_type)
    target_depth = _SCOPE_DEPTH.get(target_type)
    if binding_depth is None or target_depth is None or binding_depth > target_depth:
        return False
    if binding_type == target_type:
        return binding_id == target_id
    return _request_scope_id(context, binding_type) == binding_id


def _membership_ancestry_matches(context: RequestContext, membership: PrincipalMembership) -> bool:
    if membership.enterprise_id is not None:
        enterprise_id = context.tenancy.enterprise_id or context.effective_enterprise_id
        if enterprise_id != membership.enterprise_id:
            return False
    if membership.team_id is not None and context.tenancy.team_id != membership.team_id:
        return False
    if membership.scope_type == "team" and membership.enterprise_id is None:
        if context.tenancy.team_id != membership.effective_scope_id:
            return False
    return True


def _request_scope_id(context: RequestContext, scope_type: str) -> str | None:
    if scope_type == "enterprise":
        return context.tenancy.enterprise_id or context.effective_enterprise_id
    if scope_type == "team":
        return context.tenancy.team_id
    if scope_type == "workspace":
        return context.tenancy.workspace_id or (context.workspace.workspace_id if context.workspace else None)
    if scope_type == "project":
        return context.tenancy.project_id or (context.project.project_id if context.project else None)
    return None
