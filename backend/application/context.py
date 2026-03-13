"""Application-level request context contracts."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping


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
class RequestContext:
    principal: Principal
    workspace: WorkspaceScope | None
    project: ProjectScope | None
    runtime_profile: str
    trace: TraceContext
