from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.models import PathSourceKind, ProjectPathReference


@dataclass(frozen=True)
class ResolvedProjectPath:
    field: str
    source_kind: PathSourceKind
    requested: ProjectPathReference
    path: Path
    diagnostic: str = ""


@dataclass(frozen=True)
class ResolvedProjectPaths:
    project_id: str
    root: ResolvedProjectPath
    plan_docs: ResolvedProjectPath
    sessions: ResolvedProjectPath
    progress: ResolvedProjectPath

    def as_tuple(self) -> tuple[Path, Path, Path]:
        return (self.sessions.path, self.plan_docs.path, self.progress.path)
