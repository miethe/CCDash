import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from backend.adapters.workspaces.local import ProjectManagerWorkspaceRegistry
from backend.models import Project, ProjectPathConfig
from backend.project_manager import DbProjectManager, ProjectManager


async def _run_migrations_async(db_path: str) -> None:
    import aiosqlite

    from backend.db.sqlite_migrations import run_migrations

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await run_migrations(db)


def _make_db_manager(tmpdir: str) -> DbProjectManager:
    """Build a DbProjectManager over a fresh migrated SQLite DB in *tmpdir*.

    Mirrors the fixture in ``test_db_project_registry.py``: migrations must
    have run before instantiation because ``ensure_table()`` only guards, it
    does not create.
    """
    json_path = Path(tmpdir) / "projects.json"
    db_path = Path(tmpdir) / "registry.db"
    asyncio.run(_run_migrations_async(str(db_path)))
    return DbProjectManager(json_path, db_path=str(db_path), db_backend="sqlite")


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


class DbProjectManagerEgressConsentTests(unittest.TestCase):
    """hosted-llm-anthropic-ica-lane-v1: consent must never be silently revoked.

    ``DbProjectManager.update_project`` upserts ``project.model_dump()``, and
    ``Project.llm_egress_consent`` defaults to False.  Any caller that rebuilds
    a Project without carrying the field forward would therefore wipe a
    previously granted consent -- these tests lock that behaviour down.
    """

    def test_update_project_preserves_consent_when_field_not_set(self) -> None:
        """THE regression test: an unrelated update must not revoke consent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_db_manager(tmpdir)
            mgr.add_project(
                Project(
                    id="p-consent-carry",
                    name="Consented",
                    path=tmpdir,
                    llm_egress_consent=True,
                )
            )
            self.assertTrue(mgr.get_project("p-consent-carry").llm_egress_consent)

            # A caller that rebuilds the model from scratch, changing only an
            # unrelated field and never mentioning llm_egress_consent.
            incoming = Project(id="p-consent-carry", name="Renamed", path=tmpdir)
            self.assertNotIn("llm_egress_consent", incoming.model_fields_set)

            mgr.update_project("p-consent-carry", incoming)

            result = mgr.get_project("p-consent-carry")
            self.assertEqual(result.name, "Renamed", "unrelated field must still be updated")
            self.assertTrue(
                result.llm_egress_consent,
                "llm_egress_consent must be preserved when the update payload does not set it",
            )

            # And it must be persisted, not just in-memory.
            mgr2 = _make_db_manager(tmpdir)
            self.assertTrue(
                mgr2.get_project("p-consent-carry").llm_egress_consent,
                "preserved consent must survive a fresh manager instance",
            )

    def test_new_project_defaults_to_consent_false(self) -> None:
        """add_project stays fail-closed: never carry/assume consent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_db_manager(tmpdir)
            project = Project(id="p-brand-new", name="Brand New", path=tmpdir)
            self.assertNotIn("llm_egress_consent", project.model_fields_set)

            mgr.add_project(project)

            self.assertIs(mgr.get_project("p-brand-new").llm_egress_consent, False)

    def test_explicit_grant_then_revoke_round_trips(self) -> None:
        """An explicit False must still revoke -- preservation is not a lock."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_db_manager(tmpdir)
            mgr.add_project(Project(id="p-toggle", name="Toggle", path=tmpdir))

            granted = mgr.get_project("p-toggle")
            granted.llm_egress_consent = True
            mgr.update_project("p-toggle", granted)
            self.assertTrue(mgr.get_project("p-toggle").llm_egress_consent, "grant must persist")

            revoked = mgr.get_project("p-toggle")
            revoked.llm_egress_consent = False
            mgr.update_project("p-toggle", revoked)
            self.assertFalse(mgr.get_project("p-toggle").llm_egress_consent, "explicit revoke must persist")


if __name__ == "__main__":
    unittest.main()
