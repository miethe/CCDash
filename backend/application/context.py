"""Application-level request context contracts.

Phase 4 (DPM-303) extends the request context with explicit enterprise/team
scope objects, a stable TenancyContext key-set, and ownership-inheritance
semantics so follow-on auth/RBAC work has stable keys to bind against.

The tenancy hierarchy is: Enterprise -> Team -> Workspace -> Project -> Entity.
In local mode, enterprise and team remain None; the local operator has implicit
full-scope access without enterprise tenancy boundaries.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Mapping


OwnershipPosture = Literal["scope-owned", "directly-ownable", "inherits-parent-ownership"]
OwnerSubjectType = Literal["user", "team", "enterprise"]


@dataclass(frozen=True, slots=True)
class PrincipalMembership:
    workspace_id: str
    role: str


@dataclass(frozen=True, slots=True)
class Principal:
    subject: str
    display_name: str
    auth_mode: str
    email: str | None = None
    is_authenticated: bool = True
    groups: tuple[str, ...] = field(default_factory=tuple)
    memberships: tuple[PrincipalMembership, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class EnterpriseScope:
    """Enterprise-level tenancy scope.

    Only populated in hosted/enterprise storage profiles. Represents the
    top-level organizational boundary that gates identity, audit, and
    cross-team data visibility.
    """
    enterprise_id: str
    display_name: str = ""


@dataclass(frozen=True, slots=True)
class TeamScope:
    """Team-level scope within an enterprise.

    Only populated in hosted/enterprise storage profiles when the request
    carries team context. Represents the grouping boundary within an
    enterprise for ownership and access delegation.
    """
    team_id: str
    enterprise_id: str
    display_name: str = ""


@dataclass(frozen=True, slots=True)
class WorkspaceScope:
    workspace_id: str
    root_path: Path


@dataclass(frozen=True, slots=True)
class ProjectScope:
    project_id: str
    project_name: str
    root_path: Path
    sessions_dir: Path
    docs_dir: Path
    progress_dir: Path


@dataclass(frozen=True, slots=True)
class TraceContext:
    request_id: str
    correlation_id: str | None = None
    traceparent: str | None = None
    client_host: str | None = None
    user_agent: str | None = None
    path: str = ""
    method: str = "GET"


@dataclass(frozen=True, slots=True)
class RequestMetadata:
    headers: Mapping[str, str]
    method: str
    path: str
    client_host: str | None = None


@dataclass(frozen=True, slots=True)
class StorageScope:
    enterprise_id: str | None = None
    tenant_id: str | None = None
    isolation_mode: Literal["dedicated", "schema", "tenant"] = "dedicated"


@dataclass(frozen=True, slots=True)
class ScopeBinding:
    scope_type: Literal["enterprise", "team", "workspace", "project", "owned_entity"]
    scope_id: str
    parent_scope_type: str | None = None
    parent_scope_id: str | None = None
    ownership_mode: Literal["scope-rooted", "directly-owned", "inherits-parent-scope"] = "scope-rooted"


@dataclass(frozen=True, slots=True)
class TenancyContext:
    """Stable scope keys identifying the request's position in the tenancy hierarchy.

    Follow-on auth/RBAC work keys off these identifiers. In local mode, all
    fields except workspace_id and project_id remain None. The local operator
    has implicit full-scope access without enterprise tenancy boundaries.

    The ownership_posture_default captures the baseline posture the runtime
    assigns to entities created within this scope (aligning with the
    OwnershipPosture vocabulary from data_domains.py).
    """
    enterprise_id: str | None = None
    team_id: str | None = None
    workspace_id: str | None = None
    project_id: str | None = None
    ownership_posture_default: OwnershipPosture = "scope-owned"

    @property
    def is_enterprise_scoped(self) -> bool:
        """True when the request is within an enterprise tenancy boundary."""
        return self.enterprise_id is not None

    @property
    def is_team_scoped(self) -> bool:
        """True when the request carries explicit team context."""
        return self.team_id is not None

    @property
    def scope_depth(self) -> int:
        """Count of non-None scope levels, from enterprise down to project."""
        return sum(
            1 for v in (self.enterprise_id, self.team_id, self.workspace_id, self.project_id)
            if v is not None
        )

    @property
    def scope_chain(self) -> tuple[tuple[str, str], ...]:
        """Ordered (scope_type, scope_id) pairs from outermost to innermost.

        Only non-None levels are included. Follow-on RBAC policy evaluators
        walk this chain to resolve the effective permission set.
        """
        chain: list[tuple[str, str]] = []
        if self.enterprise_id is not None:
            chain.append(("enterprise", self.enterprise_id))
        if self.team_id is not None:
            chain.append(("team", self.team_id))
        if self.workspace_id is not None:
            chain.append(("workspace", self.workspace_id))
        if self.project_id is not None:
            chain.append(("project", self.project_id))
        return tuple(chain)


@dataclass(frozen=True, slots=True)
class OwnershipResolutionHint:
    """Describes how ownership should resolve for a given concern in this request scope.

    Aligns with OwnershipPosture in data_domains.py:
    - scope-owned: governed by the enclosing tenant/enterprise scope
    - directly-ownable: can carry owner_subject_type + owner_subject_id
    - inherits-parent-ownership: inherits from the parent entity's owner

    The principal_* fields capture the current request's principal identity
    so services can stamp ownership at entity creation time without
    re-resolving the identity chain.
    """
    posture: OwnershipPosture
    owner_subject_type: OwnerSubjectType | None = None
    owner_subject_id: str | None = None
    inherited_from_scope_type: str | None = None
    inherited_from_scope_id: str | None = None


@dataclass(frozen=True, slots=True)
class RequestContext:
    principal: Principal
    workspace: WorkspaceScope | None
    project: ProjectScope | None
    runtime_profile: str
    trace: TraceContext
    storage_scope: StorageScope | None = None
    scope_bindings: tuple[ScopeBinding, ...] = field(default_factory=tuple)
    enterprise: EnterpriseScope | None = None
    team: TeamScope | None = None
    tenancy: TenancyContext = field(default_factory=TenancyContext)

    @property
    def is_local_mode(self) -> bool:
        """True when running in a local (non-enterprise) identity context."""
        return self.enterprise is None and self.principal.auth_mode == "local"

    @property
    def effective_enterprise_id(self) -> str | None:
        """The enterprise identifier from tenancy, storage, or enterprise scope."""
        if self.tenancy.enterprise_id is not None:
            return self.tenancy.enterprise_id
        if self.storage_scope is not None and self.storage_scope.enterprise_id is not None:
            return self.storage_scope.enterprise_id
        if self.enterprise is not None:
            return self.enterprise.enterprise_id
        return None

    @property
    def effective_tenant_id(self) -> str | None:
        """The tenant identifier from storage scope (when using tenant isolation)."""
        if self.storage_scope is not None and self.storage_scope.tenant_id is not None:
            return self.storage_scope.tenant_id
        return self.effective_enterprise_id

    def ownership_hint_for_posture(self, posture: OwnershipPosture) -> OwnershipResolutionHint:
        """Build an ownership hint for a given posture within this request scope.

        Scope-owned concerns inherit the enterprise/tenant boundary.
        Directly-ownable concerns default to the principal as owner.
        Inherited concerns must resolve at query time from their parent.
        """
        if posture == "directly-ownable":
            return OwnershipResolutionHint(
                posture=posture,
                owner_subject_type="user",
                owner_subject_id=self.principal.subject,
            )
        if posture == "inherits-parent-ownership":
            return OwnershipResolutionHint(
                posture=posture,
                inherited_from_scope_type="parent_entity",
            )
        return OwnershipResolutionHint(
            posture=posture,
            inherited_from_scope_type="enterprise" if self.effective_enterprise_id else "workspace",
            inherited_from_scope_id=self.effective_enterprise_id or (
                self.workspace.workspace_id if self.workspace else None
            ),
        )
