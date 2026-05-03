import json
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from backend.adapters.workspaces.local import ProjectManagerWorkspaceRegistry
from backend.models import Project, ProjectPathConfig
from backend.project_manager import ProjectManager


class ProjectManagerTests(unittest.TestCase):
    def test_load_migrates_missing_skillmeat_config_and_persists_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "projects.json"
            storage_path.write_text(
                json.dumps(
                    {
                        "activeProjectId": "project-1",
                        "projects": [
                            {
                                "id": "project-1",
                                "name": "Project 1",
                                "path": "/tmp/project-1",
                            }
                        ],
                    }
                )
            )

            manager = ProjectManager(storage_path)

            project = manager.get_project("project-1")
            self.assertIsNotNone(project)
            self.assertFalse(project.skillMeat.enabled)

            stored = json.loads(storage_path.read_text())
            persisted = stored["projects"][0]
            self.assertIn("skillMeat", persisted)
            self.assertIn("pathConfig", persisted)
            self.assertEqual(persisted["pathConfig"]["planDocs"]["sourceKind"], "project_root")
            self.assertEqual(persisted["skillMeat"]["collectionId"], "")
            self.assertEqual(persisted["skillMeat"]["webBaseUrl"], "")

    def test_load_migrates_legacy_workspace_id_to_collection_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "projects.json"
            storage_path.write_text(
                json.dumps(
                    {
                        "activeProjectId": "project-1",
                        "projects": [
                            {
                                "id": "project-1",
                                "name": "Project 1",
                                "path": "/tmp/project-1",
                                "skillMeat": {
                                    "enabled": True,
                                    "baseUrl": "http://skillmeat.local",
                                    "projectId": "/tmp/skillmeat",
                                    "workspaceId": "legacy-collection",
                                },
                            }
                        ],
                    }
                )
            )

            manager = ProjectManager(storage_path)

            project = manager.get_project("project-1")
            self.assertIsNotNone(project)
            self.assertEqual(project.skillMeat.collectionId, "legacy-collection")

            stored = json.loads(storage_path.read_text())
            persisted = stored["projects"][0]["skillMeat"]
            self.assertEqual(persisted["collectionId"], "legacy-collection")
            self.assertNotIn("workspaceId", persisted)

    def test_project_rejects_root_inheriting_from_project_root(self) -> None:
        with self.assertRaises(ValidationError):
            Project(
                id="project-1",
                name="Project 1",
                path="/tmp/project-1",
                pathConfig=ProjectPathConfig.model_validate(
                    {
                        "root": {
                            "field": "root",
                            "sourceKind": "project_root",
                            "relativePath": "workspace",
                        }
                    }
                ),
            )

    def test_new_path_config_derives_legacy_fields(self) -> None:
        project = Project.model_validate(
            {
                "id": "project-1",
                "name": "Project 1",
                "path": "/tmp/placeholder",
                "pathConfig": {
                    "root": {
                        "field": "root",
                        "sourceKind": "filesystem",
                        "filesystemPath": "/tmp/project-1",
                    },
                    "planDocs": {
                        "field": "plan_docs",
                        "sourceKind": "project_root",
                        "relativePath": "plans",
                    },
                    "sessions": {
                        "field": "sessions",
                        "sourceKind": "filesystem",
                        "filesystemPath": "/tmp/sessions",
                    },
                    "progress": {
                        "field": "progress",
                        "sourceKind": "project_root",
                        "relativePath": ".claude/progress",
                    },
                },
            }
        )

        self.assertEqual(project.path, "/tmp/project-1")
        self.assertEqual(project.planDocsPath, "plans")
        self.assertEqual(project.sessionsPath, "/tmp/sessions")
        self.assertEqual(project.progressPath, ".claude/progress")

    def test_resolve_project_binding_prefers_explicit_project_over_active_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "projects.json"
            storage_path.write_text(
                json.dumps(
                    {
                        "activeProjectId": "project-active",
                        "projects": [
                            {
                                "id": "project-active",
                                "name": "Active Project",
                                "path": str(Path(tmpdir) / "active"),
                            },
                            {
                                "id": "project-worker",
                                "name": "Worker Project",
                                "path": str(Path(tmpdir) / "worker"),
                            },
                        ],
                    }
                )
            )

            manager = ProjectManager(storage_path)

            binding = manager.resolve_project_binding("project-worker", allow_active_fallback=False)

            self.assertIsNotNone(binding)
            assert binding is not None
            self.assertEqual(binding.project.id, "project-worker")
            self.assertEqual(binding.source, "explicit")
            self.assertEqual(binding.requested_project_id, "project-worker")

    def test_resolve_project_binding_returns_none_when_explicit_project_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "projects.json"
            storage_path.write_text(
                json.dumps(
                    {
                        "activeProjectId": "project-active",
                        "projects": [
                            {
                                "id": "project-active",
                                "name": "Active Project",
                                "path": str(Path(tmpdir) / "active"),
                            }
                        ],
                    }
                )
            )

            manager = ProjectManager(storage_path)

            binding = manager.resolve_project_binding("missing-project", allow_active_fallback=False)

            self.assertIsNone(binding)

    def test_workspace_registry_scope_resolution_can_disable_active_project_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "projects.json"
            storage_path.write_text(
                json.dumps(
                    {
                        "activeProjectId": "project-active",
                        "projects": [
                            {
                                "id": "project-active",
                                "name": "Active Project",
                                "path": str(Path(tmpdir) / "active"),
                            },
                            {
                                "id": "project-explicit",
                                "name": "Explicit Project",
                                "path": str(Path(tmpdir) / "explicit"),
                            },
                        ],
                    }
                )
            )
            registry = ProjectManagerWorkspaceRegistry(ProjectManager(storage_path))

            workspace, project = registry.resolve_scope(allow_active_fallback=False)
            explicit_workspace, explicit_project = registry.resolve_scope(
                "project-explicit",
                allow_active_fallback=False,
            )

            self.assertIsNone(workspace)
            self.assertIsNone(project)
            self.assertIsNotNone(explicit_workspace)
            self.assertIsNotNone(explicit_project)
            self.assertEqual(explicit_project.project_id, "project-explicit")

    def test_set_active_project_mutates_persisted_local_active_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "projects.json"
            storage_path.write_text(
                json.dumps(
                    {
                        "activeProjectId": "project-one",
                        "projects": [
                            {
                                "id": "project-one",
                                "name": "Project One",
                                "path": str(Path(tmpdir) / "one"),
                            },
                            {
                                "id": "project-two",
                                "name": "Project Two",
                                "path": str(Path(tmpdir) / "two"),
                            },
                        ],
                    }
                )
            )
            manager = ProjectManager(storage_path)

            manager.set_active_project("project-two")

            self.assertEqual(manager.get_active_project().id, "project-two")
            stored = json.loads(storage_path.read_text())
            self.assertEqual(stored["activeProjectId"], "project-two")


if __name__ == "__main__":
    unittest.main()
