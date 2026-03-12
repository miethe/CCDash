import json
import tempfile
import unittest
from pathlib import Path

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
            self.assertEqual(persisted["skillMeat"]["collectionId"], "")

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


if __name__ == "__main__":
    unittest.main()
