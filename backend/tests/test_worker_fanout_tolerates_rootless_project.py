"""Regression coverage for root-less registry rows in worker-watch fan-out."""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from backend.application.ports.core import ProjectBinding
from backend.models import Project
from backend.runtime.container import RuntimeContainer
from backend.runtime.profiles import get_runtime_profile
from backend.services.project_paths.resolver import ProjectPathResolver


class _Registry:
    """Small registry that exercises production path resolution for each project."""

    def __init__(self, projects: list[Project]) -> None:
        self._projects = {project.id: project for project in projects}
        self._resolver = ProjectPathResolver()

    def list_projects(self) -> list[Project]:
        return list(self._projects.values())

    def resolve_project_binding(
        self,
        project_id: str,
        *,
        allow_active_fallback: bool = True,
    ) -> ProjectBinding | None:
        _ = allow_active_fallback
        project = self._projects.get(project_id)
        if project is None:
            return None
        return ProjectBinding(
            project=project,
            paths=self._resolver.resolve_project(project),
            source="explicit",
            requested_project_id=project_id,
        )


class WorkerFanOutRootlessProjectTests(unittest.TestCase):
    def test_fan_out_skips_rootless_project_and_keeps_normal_binding(self) -> None:
        normal = Project(id="project-normal", name="Normal", path=str(Path.cwd()))
        rootless = Project.model_validate(
            {
                "id": "ccp-unattributed",
                "name": "Unattributed",
                "path": "",
                "pathConfig": {},
            }
        )
        registry = _Registry([normal, rootless])
        container = RuntimeContainer(profile=get_runtime_profile("worker-watch"))

        with patch("backend.runtime.container.build_workspace_registry", return_value=registry):
            with self.assertLogs("ccdash.runtime", level="WARNING") as logs:
                primary, bindings = container._resolve_watcher_fan_out_bindings()

        self.assertIsNone(primary)
        self.assertEqual([binding.project.id for binding in bindings], ["project-normal"])
        self.assertEqual(len(logs.output), 1)
        self.assertIn("project_id=ccp-unattributed", logs.output[0])
        self.assertIn("code=missing_filesystem_path", logs.output[0])

