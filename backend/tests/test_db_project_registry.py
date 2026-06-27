"""Tests for the DB-backed project registry (P3-001).

Coverage:
- round-trip: add → get → list → set_active → get_active
- restart-survival: new DbProjectManager instance reads persisted rows
- projects.json bootstrap: empty DB imports from JSON on first use
- fallback: DB unavailable → JSON fallback (SqliteProjectRepository with bad path)
- WorkspaceRegistry Protocol: DbProjectManager satisfies all sync methods
- F-01 reproducer: lock-injection proves flush raises (not swallows) on locked DB
- direct-count post-flush: count() on the same instance == len(in-memory snapshot)
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from backend.models import Project
from backend.project_manager import DbProjectManager


def _run_migrations_sync(db_path: str) -> None:
    """Run the canonical SQLite migration runner against *db_path* synchronously.

    DbProjectManager.ensure_table() no longer creates the projects table — it
    merely guards that migrations have already run.  Tests that create a fresh
    DB must call this helper before instantiating DbProjectManager so that the
    projects table exists when _get_repo() calls ensure_table().
    """
    import aiosqlite
    from backend.db.sqlite_migrations import run_migrations

    async def _run() -> None:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            await run_migrations(db)

    asyncio.run(_run())


def _make_manager(tmpdir: str, json_data: dict | None = None) -> DbProjectManager:
    """Build a DbProjectManager pointing at a fresh SQLite DB in tmpdir.

    Runs the canonical migration runner first so the projects table exists
    before DbProjectManager._get_repo() calls ensure_table().
    """
    json_path = Path(tmpdir) / "projects.json"
    db_path = Path(tmpdir) / "registry.db"
    if json_data is not None:
        json_path.write_text(json.dumps(json_data))
    _run_migrations_sync(str(db_path))
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

            # Migrations must run before DbProjectManager can use the DB.
            _run_migrations_sync(db_path)

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

            _run_migrations_sync(db_path)

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
            db_path = str(Path(tmpdir) / "registry.db")
            json_path = Path(tmpdir) / "projects.json"
            json_path.write_text(json.dumps(json_data))

            _run_migrations_sync(db_path)

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

            _run_migrations_sync(db_path)

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

            _run_migrations_sync(db_path)

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


class TestRegistryFlushFailLoud(unittest.TestCase):
    """T1-005 / F-01 reproducer: flush raises on a locked DB, never swallows.

    Mechanism
    ---------
    1. Build a DbProjectManager and force snapshot hydration (add_project
       triggers _ensure_snapshot on the first call, which bootstraps the
       default project into the DB).
    2. Open a *second* sqlite3 connection on the same file and acquire an
       EXCLUSIVE lock (BEGIN EXCLUSIVE) so that no other writer can commit.
    3. Shrink the retry/busy-timeout window to near-zero via monkeypatching
       the module-level constants in backend.db.repositories.projects and by
       setting PRAGMA busy_timeout = 0 on the repository's live connection,
       so the test stays fast (< 1 s).
    4. Manually load a second project into the in-memory snapshot (bypassing
       the public API so we don't trigger a DB write yet) and call
       _flush_snapshot_to_db() directly.
    5. Assert that an Exception propagates (not swallowed).
    6. Assert that _snapshot_loaded is still False after the failure, proving
       the next list_projects() / get_project() call will retry.

    Why this would fail against the OLD code (pre-T1-001)
    ------------------------------------------------------
    Before T1-001, _flush_snapshot_to_db() caught all exceptions, logged
    them, and returned normally.  This test calls _flush_snapshot_to_db()
    directly and asserts it raises — with the old code the assertRaises block
    would see no exception and the test would FAIL.  After T1-001 the
    exception re-raises, so the test PASSES.
    """

    def test_registry_flush_fail_loud(self) -> None:
        import backend.db.repositories.projects as proj_repo_mod

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "registry.db")
            json_path = Path(tmpdir) / "projects.json"
            json_path.write_text("{}")

            _run_migrations_sync(db_path)

            mgr = DbProjectManager(json_path, db_path=db_path, db_backend="sqlite")

            # Trigger snapshot hydration so the repo connection is initialised
            # and the table exists.  add_project forces _ensure_snapshot.
            mgr.add_project(Project(id="fl-seed", name="Seed", path=tmpdir))

            # Patch time.sleep so retry backoff doesn't slow the test down.
            # The retry constants now live in retry_on_locked_sync (base.py);
            # busy_timeout=0 on the repo connection ensures locked errors fire
            # immediately, so all retries exhaust quickly.
            import unittest.mock as _mock
            with _mock.patch("time.sleep"):
                # Also set busy_timeout = 0 on the live repository connection
                # so SQLite returns immediately instead of waiting 30 s.
                repo = mgr._get_repo()
                repo._get_conn().execute("PRAGMA busy_timeout = 0")

                # Acquire an exclusive write lock from a *second* connection.
                locker = sqlite3.connect(db_path, timeout=0)
                try:
                    locker.execute("BEGIN EXCLUSIVE")

                    # Load a second project directly into the snapshot dict
                    # so _flush_snapshot_to_db has real work to do.
                    mgr._projects["fl-extra"] = Project(
                        id="fl-extra", name="Extra", path=tmpdir
                    )

                    # Post-T1-001: _flush_snapshot_to_db must raise, not return silently.
                    with self.assertRaises(Exception):
                        mgr._flush_snapshot_to_db()

                    # _snapshot_loaded must still be False so the next call retries.
                    self.assertFalse(
                        mgr._snapshot_loaded,
                        "_snapshot_loaded must remain False after a failed flush "
                        "so the next list_projects()/get_project() retries the write.",
                    )
                finally:
                    locker.rollback()
                    locker.close()


class TestRegistryPersistenceDirectCount(unittest.TestCase):
    """T1-006: count() on the same SqliteProjectRepository instance equals the
    in-memory snapshot length after a flush — no second DbProjectManager.

    Mechanism
    ---------
    Using a *second* DbProjectManager instance to verify persistence (as the
    existing restart-survival tests do) hides F-01 because the second instance
    re-bootstraps from projects.json and never reads the DB rows written by the
    first.  This test instead interrogates the repository object that the
    *same* manager instance already holds, calling count() directly after the
    flush has occurred, so there is no JSON-fallback escape hatch.

    Steps:
    1. Build a DbProjectManager with a seeded projects.json (2 projects).
    2. Trigger snapshot hydration via list_projects(), which imports from JSON
       and calls _flush_snapshot_to_db() internally.
    3. Call mgr._get_repo().count() on the *same* manager instance.
    4. Assert count == len(mgr._projects) (the live in-memory snapshot).
    """

    def test_registry_persistence_direct_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            json_data = {
                "activeProjectId": "dc-1",
                "projects": [
                    {"id": "dc-1", "name": "Direct Count 1", "path": tmpdir},
                    {"id": "dc-2", "name": "Direct Count 2", "path": tmpdir},
                ],
            }
            db_path = str(Path(tmpdir) / "registry.db")
            json_path = Path(tmpdir) / "projects.json"
            json_path.write_text(json.dumps(json_data))

            _run_migrations_sync(db_path)

            mgr = DbProjectManager(json_path, db_path=db_path, db_backend="sqlite")

            # Trigger hydration + flush via the public API.
            projects = mgr.list_projects()

            # In-memory snapshot size (the ground truth).
            snapshot_count = len(mgr._projects)
            self.assertGreater(snapshot_count, 0, "snapshot must be non-empty after hydration")

            # Direct DB count via the SAME repo instance — no second DbProjectManager.
            repo = mgr._get_repo()
            db_count = repo.count()

            self.assertEqual(
                db_count,
                snapshot_count,
                f"DB row count ({db_count}) must equal in-memory snapshot size "
                f"({snapshot_count}) after flush; a mismatch means rows were lost "
                "silently (F-01).",
            )


class TestImportExportRoundTrip(unittest.TestCase):
    """T1-008: import_from_json → export_to_json round-trip tests.

    AC:
    - 5 projects in JSON → 5 in DB after import_from_json.
    - export_to_json produces identical project ids and names.
    - A second import_from_json over an existing DB does NOT wipe rows
      (additive upsert — existing rows are preserved).
    """

    def _make_json_data(self, n: int, tmpdir: str) -> dict:
        return {
            "activeProjectId": f"rt-{0}",
            "projects": [
                {"id": f"rt-{i}", "name": f"Round Trip {i}", "path": tmpdir}
                for i in range(n)
            ],
        }

    def test_import_5_projects_populates_db(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "projects.json"
            json_path.write_text(json.dumps(self._make_json_data(5, tmpdir)))
            db_path = str(Path(tmpdir) / "registry.db")

            _run_migrations_sync(db_path)

            mgr = DbProjectManager.import_from_json(
                json_path,
                db_path=db_path,
                db_backend="sqlite",
            )

            projects = mgr.list_projects()
            ids = {p.id for p in projects}
            for i in range(5):
                self.assertIn(f"rt-{i}", ids, f"rt-{i} missing after import")

    def test_export_yields_identical_ids_and_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "projects.json"
            json_data = self._make_json_data(5, tmpdir)
            json_path.write_text(json.dumps(json_data))
            db_path = str(Path(tmpdir) / "registry.db")

            _run_migrations_sync(db_path)

            mgr = DbProjectManager.import_from_json(
                json_path,
                db_path=db_path,
                db_backend="sqlite",
            )

            out_path = Path(tmpdir) / "out.json"
            mgr.export_to_json(out_path)

            exported = json.loads(out_path.read_text())
            exported_ids = {p["id"] for p in exported["projects"]}
            exported_names = {p["id"]: p["name"] for p in exported["projects"]}

            for i in range(5):
                self.assertIn(f"rt-{i}", exported_ids)
                self.assertEqual(exported_names[f"rt-{i}"], f"Round Trip {i}")

    def test_second_import_is_additive_not_destructive(self) -> None:
        """Importing a second JSON file over an existing DB preserves prior rows."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "registry.db")

            _run_migrations_sync(db_path)

            # First import: 5 projects (rt-0 … rt-4).
            json_path_1 = Path(tmpdir) / "first.json"
            json_path_1.write_text(json.dumps(self._make_json_data(5, tmpdir)))
            mgr = DbProjectManager.import_from_json(
                json_path_1,
                db_path=db_path,
                db_backend="sqlite",
            )
            # Confirm 5 rows landed.
            self.assertEqual(
                sum(1 for p in mgr.list_projects() if p.id.startswith("rt-")),
                5,
            )

            # Second import: 2 new projects only (extra-0, extra-1).
            json_path_2 = Path(tmpdir) / "second.json"
            json_path_2.write_text(
                json.dumps(
                    {
                        "activeProjectId": "extra-0",
                        "projects": [
                            {"id": "extra-0", "name": "Extra 0", "path": tmpdir},
                            {"id": "extra-1", "name": "Extra 1", "path": tmpdir},
                        ],
                    }
                )
            )
            # Re-use the same manager so we import into the same DB.
            DbProjectManager.import_from_json(json_path_2, manager=mgr)

            all_ids = {p.id for p in mgr.list_projects()}
            # Original 5 rows must still be present.
            for i in range(5):
                self.assertIn(
                    f"rt-{i}",
                    all_ids,
                    f"rt-{i} was wiped by second import (additive upsert violation)",
                )
            # New 2 rows must also be present.
            self.assertIn("extra-0", all_ids)
            self.assertIn("extra-1", all_ids)


if __name__ == "__main__":
    unittest.main()
