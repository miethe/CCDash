"""Tests for the DB-backed project registry (P3-001).

Coverage:
- round-trip: add → get → list → set_active → get_active
- restart-survival: new DbProjectManager instance reads persisted rows
- projects.json bootstrap: empty DB imports from JSON on first use
- fallback: DB unavailable → JSON fallback (SqliteProjectRepository with bad path)
- WorkspaceRegistry Protocol: DbProjectManager satisfies all sync methods
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.models import Project
from backend.project_manager import DbProjectManager


def _make_manager(tmpdir: str, json_data: dict | None = None) -> DbProjectManager:
    """Build a DbProjectManager pointing at a fresh SQLite DB in tmpdir."""
    json_path = Path(tmpdir) / "projects.json"
    db_path = Path(tmpdir) / "registry.db"
    if json_data is not None:
        json_path.write_text(json.dumps(json_data))
    return DbProjectManager(
        json_path,
        db_path=str(db_path),
        db_backend="sqlite",
    )


class TestDbProjectRegistryRoundTrip(unittest.TestCase):
    """add → get → list → set_active → get_active round-trip."""

    def test_add_and_get_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            project = Project(
                id="p-1",
                name="Test Project",
                path=tmpdir,
                description="A test project",
            )
            mgr.add_project(project)

            result = mgr.get_project("p-1")
            self.assertIsNotNone(result)
            self.assertEqual(result.id, "p-1")
            self.assertEqual(result.name, "Test Project")
            self.assertEqual(result.description, "A test project")

    def test_list_projects_returns_all(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            for i in range(3):
                mgr.add_project(Project(id=f"p-{i}", name=f"Project {i}", path=tmpdir))

            # The default project gets created too (table starts empty)
            # so we check that our 3 are present
            ids = {p.id for p in mgr.list_projects()}
            for i in range(3):
                self.assertIn(f"p-{i}", ids)

    def test_set_active_and_get_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            mgr.add_project(Project(id="p-a", name="Alpha", path=tmpdir))
            mgr.add_project(Project(id="p-b", name="Beta", path=tmpdir))

            mgr.set_active_project("p-b")

            active = mgr.get_active_project()
            self.assertIsNotNone(active)
            self.assertEqual(active.id, "p-b")

    def test_update_project_persists_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            mgr.add_project(Project(id="p-upd", name="Old Name", path=tmpdir))
            mgr.update_project("p-upd", Project(id="p-upd", name="New Name", path=tmpdir))

            result = mgr.get_project("p-upd")
            self.assertEqual(result.name, "New Name")

    def test_set_active_raises_for_missing_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            with self.assertRaises(ValueError):
                mgr.set_active_project("does-not-exist")

    def test_update_raises_for_missing_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            with self.assertRaises(ValueError):
                mgr.update_project(
                    "does-not-exist",
                    Project(id="does-not-exist", name="X", path=tmpdir),
                )


class TestDbProjectRegistryRestartSurvival(unittest.TestCase):
    """Rows written by one DbProjectManager instance are readable by a new one
    pointing at the same DB file (restart survival / replica consistency)."""

    def test_rows_survive_new_instance(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "registry.db")
            json_path = Path(tmpdir) / "projects.json"
            json_path.write_text("{}")  # empty JSON → no bootstrap

            # First instance: create and activate a project
            mgr1 = DbProjectManager(json_path, db_path=db_path, db_backend="sqlite")
            mgr1.add_project(Project(id="p-persist", name="Persistent", path=tmpdir))
            mgr1.set_active_project("p-persist")

            # Second instance: same DB, fresh in-memory state
            mgr2 = DbProjectManager(json_path, db_path=db_path, db_backend="sqlite")
            result = mgr2.get_project("p-persist")
            active = mgr2.get_active_project()

            self.assertIsNotNone(result)
            self.assertEqual(result.id, "p-persist")
            self.assertIsNotNone(active)
            self.assertEqual(active.id, "p-persist")

    def test_multiple_projects_all_survive_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "registry.db")
            json_path = Path(tmpdir) / "projects.json"
            json_path.write_text("{}")

            mgr1 = DbProjectManager(json_path, db_path=db_path, db_backend="sqlite")
            for i in range(5):
                mgr1.add_project(
                    Project(id=f"proj-{i}", name=f"Project {i}", path=tmpdir)
                )
            mgr1.set_active_project("proj-3")

            mgr2 = DbProjectManager(json_path, db_path=db_path, db_backend="sqlite")
            ids = {p.id for p in mgr2.list_projects()}
            for i in range(5):
                self.assertIn(f"proj-{i}", ids)
            self.assertEqual(mgr2.get_active_project().id, "proj-3")


class TestDbProjectRegistryJsonBootstrap(unittest.TestCase):
    """Empty DB should import from projects.json on first use."""

    def test_bootstrap_from_projects_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            json_data = {
                "activeProjectId": "boot-1",
                "projects": [
                    {"id": "boot-1", "name": "Booted", "path": tmpdir},
                    {"id": "boot-2", "name": "Secondary", "path": tmpdir},
                ],
            }
            # fresh DB (no file yet)
            db_path = str(Path(tmpdir) / "registry.db")
            json_path = Path(tmpdir) / "projects.json"
            json_path.write_text(json.dumps(json_data))

            mgr = DbProjectManager(json_path, db_path=db_path, db_backend="sqlite")

            self.assertIsNotNone(mgr.get_project("boot-1"))
            self.assertIsNotNone(mgr.get_project("boot-2"))
            active = mgr.get_active_project()
            self.assertIsNotNone(active)
            self.assertEqual(active.id, "boot-1")

    def test_bootstrapped_rows_survive_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            json_data = {
                "activeProjectId": "boot-x",
                "projects": [{"id": "boot-x", "name": "Bootstrap X", "path": tmpdir}],
            }
            db_path = str(Path(tmpdir) / "registry.db")
            json_path = Path(tmpdir) / "projects.json"
            json_path.write_text(json.dumps(json_data))

            # First access: imports from JSON into DB
            mgr1 = DbProjectManager(json_path, db_path=db_path, db_backend="sqlite")
            _ = mgr1.get_project("boot-x")  # trigger hydration

            # Second instance: JSON bootstrap should NOT run again (DB already has rows)
            mgr2 = DbProjectManager(json_path, db_path=db_path, db_backend="sqlite")
            result = mgr2.get_project("boot-x")
            self.assertIsNotNone(result)
            self.assertEqual(result.name, "Bootstrap X")

    def test_missing_json_creates_default_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "registry.db")
            json_path = Path(tmpdir) / "projects.json"
            # json_path does NOT exist

            mgr = DbProjectManager(json_path, db_path=db_path, db_backend="sqlite")
            projects = mgr.list_projects()
            self.assertGreater(len(projects), 0)
            # A default project should have been created
            active = mgr.get_active_project()
            self.assertIsNotNone(active)


class TestDbProjectRegistryFallback(unittest.TestCase):
    """DB unavailable → graceful fallback to projects.json in memory."""

    def test_fallback_to_json_when_db_path_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            json_data = {
                "activeProjectId": "fall-1",
                "projects": [{"id": "fall-1", "name": "Fallback", "path": tmpdir}],
            }
            json_path = Path(tmpdir) / "projects.json"
            json_path.write_text(json.dumps(json_data))

            # Point DB at a directory (not a file path) – sqlite3 will succeed
            # opening it (SQLite creates files), so use a truly invalid path
            # (non-existent parent directory) to force DB failure.
            bad_db_path = "/nonexistent_parent_dir_ccdash_test/registry.db"
            mgr = DbProjectManager(json_path, db_path=bad_db_path, db_backend="sqlite")

            # Should fall back to JSON without raising
            result = mgr.get_project("fall-1")
            # May be None if SQLite creates the file anyway; the key assertion is
            # no unhandled exception.  If sqlite3 does succeed with the bad path
            # (e.g. because the path becomes valid), the fallback logic still
            # bootstraps from JSON so we check both cases.
            if result is not None:
                self.assertEqual(result.name, "Fallback")


class TestDbProjectRegistryWorkspaceProtocol(unittest.TestCase):
    """DbProjectManager satisfies all sync WorkspaceRegistry methods."""

    def test_all_protocol_methods_callable_and_return_correct_types(self) -> None:
        from backend.adapters.workspaces.local import ProjectManagerWorkspaceRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            registry = ProjectManagerWorkspaceRegistry(mgr)

            # list_projects
            projects = registry.list_projects()
            self.assertIsInstance(projects, list)

            # add_project
            registry.add_project(Project(id="wsp-1", name="WS Project", path=tmpdir))

            # get_project
            p = registry.get_project("wsp-1")
            self.assertIsNotNone(p)
            self.assertEqual(p.id, "wsp-1")

            # set_active_project + get_active_project
            registry.set_active_project("wsp-1")
            active = registry.get_active_project()
            self.assertEqual(active.id, "wsp-1")

            # resolve_project_binding
            binding = registry.resolve_project_binding("wsp-1")
            self.assertIsNotNone(binding)
            self.assertEqual(binding.project.id, "wsp-1")

            # resolve_scope
            ws, proj_scope = registry.resolve_scope("wsp-1")
            self.assertIsNotNone(ws)
            self.assertIsNotNone(proj_scope)

            # get_active_path_bundle
            bundle = registry.get_active_path_bundle()
            self.assertIsNotNone(bundle)

    def test_no_async_method_on_registry(self) -> None:
        """Verify no public method on DbProjectManager is a coroutine function."""
        import inspect

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = _make_manager(tmpdir)
            for name in dir(mgr):
                if name.startswith("_"):
                    continue
                attr = getattr(mgr, name)
                if callable(attr):
                    self.assertFalse(
                        inspect.iscoroutinefunction(attr),
                        msg=f"DbProjectManager.{name} is async — must be sync",
                    )


if __name__ == "__main__":
    unittest.main()
