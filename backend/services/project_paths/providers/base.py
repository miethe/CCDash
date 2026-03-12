from __future__ import annotations

from pathlib import Path
from typing import Protocol

from backend.models import Project, ProjectPathReference
from backend.services.project_paths.models import ResolvedProjectPath


class PathResolutionError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class ProjectPathProvider(Protocol):
    def resolve(
        self,
        reference: ProjectPathReference,
        *,
        project: Project,
        refresh: bool = False,
    ) -> ResolvedProjectPath:
        ...
