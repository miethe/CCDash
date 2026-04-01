"""Code-owned scope and ownership contract for enterprise identity storage."""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal


ScopeType = Literal["enterprise", "team", "workspace", "project", "owned_entity"]
OwnershipMode = Literal["scope-rooted", "directly-owned", "inherits-parent-scope"]
OwnerSubjectType = Literal["user", "team", "enterprise"]


@dataclass(frozen=True, slots=True)
class ScopeContract:
    scope_type: ScopeType
    storage_key: str
    scope_identifier_kind: str
    membership_supported: bool
    role_binding_supported: bool
    parent_scope_types: tuple[ScopeType, ...]
    ownership_mode: OwnershipMode
    notes: str


SCOPE_CONTRACTS = MappingProxyType(
    {
        "enterprise": ScopeContract(
            scope_type="enterprise",
            storage_key="enterprise_id",
            scope_identifier_kind="enterprise",
            membership_supported=True,
            role_binding_supported=True,
            parent_scope_types=(),
            ownership_mode="scope-rooted",
            notes="Enterprise is the hosted root scope and anchors tenant or enterprise isolation.",
        ),
        "team": ScopeContract(
            scope_type="team",
            storage_key="team_id",
            scope_identifier_kind="team",
            membership_supported=True,
            role_binding_supported=True,
            parent_scope_types=("enterprise",),
            ownership_mode="scope-rooted",
            notes="Teams live under an enterprise scope and may own directly ownable canonical entities.",
        ),
        "workspace": ScopeContract(
            scope_type="workspace",
            storage_key="workspace_id",
            scope_identifier_kind="workspace",
            membership_supported=True,
            role_binding_supported=True,
            parent_scope_types=("enterprise", "team"),
            ownership_mode="scope-rooted",
            notes="Workspace scope governs project collections and most app metadata.",
        ),
        "project": ScopeContract(
            scope_type="project",
            storage_key="project_id",
            scope_identifier_kind="project",
            membership_supported=True,
            role_binding_supported=True,
            parent_scope_types=("workspace", "team", "enterprise"),
            ownership_mode="scope-rooted",
            notes="Projects inherit hosted scope from the governing workspace while remaining the current request-path boundary.",
        ),
        "owned_entity": ScopeContract(
            scope_type="owned_entity",
            storage_key="owner_subject_id",
            scope_identifier_kind="owned-entity",
            membership_supported=False,
            role_binding_supported=False,
            parent_scope_types=("project", "workspace", "team", "enterprise"),
            ownership_mode="directly-owned",
            notes=(
                "Directly ownable canonical entities reserve owner subject primitives but still remain bounded by enterprise "
                "or project scope for tenancy and inheritance."
            ),
        ),
    }
)


DIRECT_OWNER_SUBJECT_TYPES: tuple[OwnerSubjectType, ...] = ("user", "team", "enterprise")

SCOPE_INHERITANCE_RULES = MappingProxyType(
    {
        "memberships": "Membership rows inherit ownership from the governing principal and scope identifier roots.",
        "role_bindings": "Role bindings inherit scope ownership and never reserve direct owner subject columns.",
        "audit_records": "Privileged action and access decision audit rows are scope-rooted, not directly ownable.",
        "direct_entities": (
            "Directly ownable canonical entities reserve enterprise or tenant scope plus owner_subject_type, "
            "owner_subject_id, and visibility."
        ),
    }
)

