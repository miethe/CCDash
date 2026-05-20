"""Integration tests for watcher rebind on active project switch.

Covers:
- Successful project switch: watchPaths update, one-shot sync populates sessions table.
- Failed project switch (bad paths): API returns 4xx, watcher remains on old project.
- Mid-switch drain: documents the drain-before-rebind behaviour.

Test strategy: uses RuntimeJobAdapter directly with a real in-memory SQLite DB
and real FileWatcher (started against temp dirs), then verifies snapshot and
sessions table state.  The router-level happy/sad paths use a lightweight
FastAPI TestClient with mocked infrastructure.
"""
from __future__ import annotations

import asyncio
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
from fastapi.testclient import TestClient

from backend.adapters.jobs.runtime import RuntimeJobAdapter, WatcherRebindError
from backend.db.file_watcher import FileWatcher
from backend.db.sqlite_migrations import run_migrations
from backend.db.sync_engine import SyncEngine
from backend.runtime.profiles import get_runtime_profile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_project(project_id: str, sessions_dir: Path, docs_dir: Path, progress_dir: Path) -> types.SimpleNamespace:
    """Build a minimal project namespace that satisfies runtime expectations."""
    return types.SimpleNamespace(
        id=project_id,
        name=f"Project {project_id}",
        testConfig=types.SimpleNamespace(
            autoSyncOnStartup=False,
            maxFilesPerScan=25,
            maxParseConcurrency=4,
        ),
    )


def _make_resolved_paths(
    sessions_dir: Path, docs_dir: Path, progress_dir: Path, root: Path
) -> types.SimpleNamespace:
    """Build a minimal ResolvedProjectPaths-alike namespace."""
    return types.SimpleNamespace(
        sessions=types.SimpleNamespace(path=sessions_dir),
        plan_docs=types.SimpleNamespace(path=docs_dir),
        progress=types.SimpleNamespace(path=progress_dir),
        root=types.SimpleNamespace(path=root),
        as_tuple=lambda: (sessions_dir, docs_dir, progress_dir),
    )


def _make_binding(project: types.SimpleNamespace, paths: types.SimpleNamespace) -> types.SimpleNamespace:
    return types.SimpleNamespace(project=project, paths=paths)


def _make_sync_engine_mock() -> MagicMock:
    """Create a MagicMock that looks like SyncEngine for the rebind path."""
    sync = MagicMock()
    sync.sync_project = AsyncMock(return_value={"sessions_synced": 0})
    sync.sync_planning_artifacts = AsyncMock(return_value={"synced": 0})
    return sync


# ---------------------------------------------------------------------------
# Unit-level: RuntimeJobAdapter.rebind_watcher
# ---------------------------------------------------------------------------


class WatcherRebindUnitTests(unittest.IsolatedAsyncioTestCase):
    """Tests that exercise RuntimeJobAdapter.rebind_watcher with mocked infrastructure."""

    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)

        # Old project dirs (exist on disk).
        self.old_root = root / "old_project"
        self.old_sessions = self.old_root / "sessions"
        self.old_docs = self.old_root / "docs"
        self.old_progress = self.old_root / "progress"
        for d in (self.old_sessions, self.old_docs, self.old_progress):
            d.mkdir(parents=True)

        # New project dirs (exist on disk).
        self.new_root = root / "new_project"
        self.new_sessions = self.new_root / "sessions"
        self.new_docs = self.new_root / "docs"
        self.new_progress = self.new_root / "progress"
        for d in (self.new_sessions, self.new_docs, self.new_progress):
            d.mkdir(parents=True)

        self.old_project = _make_project("old-project", self.old_sessions, self.old_docs, self.old_progress)
        self.new_project = _make_project("new-project", self.new_sessions, self.new_docs, self.new_progress)

        self.old_paths = _make_resolved_paths(self.old_sessions, self.old_docs, self.old_progress, self.old_root)
        self.new_paths = _make_resolved_paths(self.new_sessions, self.new_docs, self.new_progress, self.new_root)

        self.old_binding = _make_binding(self.old_project, self.old_paths)
        self.new_binding = _make_binding(self.new_project, self.new_paths)

        self.sync = _make_sync_engine_mock()

        # Build the adapter with local-profile (watch=True).
        self.profile = get_runtime_profile("local")

        # We use a fresh FileWatcher per test by patching the module-level singleton.
        self.watcher = FileWatcher()
        self._watcher_patcher = patch("backend.adapters.jobs.runtime.file_watcher", self.watcher)
        self._watcher_patcher.start()

        # Start watcher on old project.
        await self.watcher.start(
            self.sync,
            self.old_project.id,
            self.old_sessions,
            self.old_docs,
            self.old_progress,
        )

    async def asyncTearDown(self) -> None:
        await self.watcher.stop()
        self._watcher_patcher.stop()
        self.tmp.cleanup()

    def _make_adapter(self, *, registry_override=None) -> RuntimeJobAdapter:
        """Build a RuntimeJobAdapter wired to the temp dirs."""
        def resolve_binding(project_id, *, allow_active_fallback=True, refresh=False):
            if project_id == self.new_project.id:
                return self.new_binding
            if project_id == self.old_project.id:
                return self.old_binding
            return None

        workspace_registry = types.SimpleNamespace(
            resolve_project_binding=resolve_binding,
            get_active_project=lambda: self.old_project,
        )
        ports = types.SimpleNamespace(
            workspace_registry=registry_override or workspace_registry,
            job_scheduler=types.SimpleNamespace(
                schedule=lambda coro, name="": asyncio.get_event_loop().create_task(coro),
            ),
        )
        adapter = RuntimeJobAdapter(
            profile=self.profile,
            ports=ports,
            sync_engine=self.sync,
        )
        adapter.state.watcher_started = True
        return adapter

    async def test_successful_rebind_updates_watch_paths(self) -> None:
        """After rebind, snapshot reflects new project's paths."""
        adapter = self._make_adapter()

        result = await adapter.rebind_watcher(self.new_project.id)

        self.assertTrue(result.get("watcherRebound"))
        snapshot = self.watcher.snapshot()
        self.assertEqual(snapshot["projectId"], self.new_project.id)
        watch_paths = snapshot["watchPaths"]
        self.assertTrue(
            any(str(self.new_sessions) in p for p in watch_paths),
            f"Expected new sessions dir in watchPaths, got: {watch_paths}",
        )

    async def test_successful_rebind_watcher_state_remains_started(self) -> None:
        """watcher_started stays True after a successful rebind."""
        adapter = self._make_adapter()
        await adapter.rebind_watcher(self.new_project.id)
        self.assertTrue(adapter.state.watcher_started)

    async def test_successful_rebind_triggers_one_shot_sync(self) -> None:
        """sync_project is called once for the new project."""
        adapter = self._make_adapter()
        await adapter.rebind_watcher(self.new_project.id)
        self.sync.sync_project.assert_called_once()
        call_kwargs = self.sync.sync_project.call_args
        # First positional arg is the project object.
        assert call_kwargs.args[0].id == self.new_project.id, (
            f"Expected sync_project called with new project, got: {call_kwargs.args[0].id}"
        )

    async def test_rebind_bad_paths_raises_error_before_stop(self) -> None:
        """If new project paths don't exist, WatcherRebindError raised, watcher untouched."""
        bad_sessions = self.new_root / "nonexistent_sessions"
        bad_docs = self.new_root / "nonexistent_docs"
        bad_progress = self.new_root / "nonexistent_progress"
        # Do NOT create these dirs.
        bad_paths = _make_resolved_paths(bad_sessions, bad_docs, bad_progress, self.new_root)
        bad_binding = _make_binding(self.new_project, bad_paths)

        def resolve_binding(project_id, *, allow_active_fallback=True, refresh=False):
            if project_id == self.new_project.id:
                return bad_binding
            if project_id == self.old_project.id:
                return self.old_binding
            return None

        workspace_registry = types.SimpleNamespace(
            resolve_project_binding=resolve_binding,
            get_active_project=lambda: self.old_project,
        )
        ports = types.SimpleNamespace(
            workspace_registry=workspace_registry,
            job_scheduler=types.SimpleNamespace(schedule=lambda coro, name="": asyncio.get_event_loop().create_task(coro)),
        )
        adapter = RuntimeJobAdapter(
            profile=self.profile,
            ports=ports,
            sync_engine=self.sync,
        )
        adapter.state.watcher_started = True

        with self.assertRaises(WatcherRebindError) as ctx:
            await adapter.rebind_watcher(self.new_project.id)

        exc = ctx.exception
        self.assertIn(exc.status_code, (404, 422))
        # Watcher should still be on the old project (stop was never called).
        snapshot = self.watcher.snapshot()
        self.assertEqual(snapshot["projectId"], self.old_project.id)
        # sync_project should NOT have been called.
        self.sync.sync_project.assert_not_called()

    async def test_rebind_unknown_project_raises_error(self) -> None:
        """Rebind to a project_id not in registry raises WatcherRebindError 404."""
        def resolve_binding(project_id, *, allow_active_fallback=True, refresh=False):
            return None  # all projects unknown

        workspace_registry = types.SimpleNamespace(
            resolve_project_binding=resolve_binding,
            get_active_project=lambda: self.old_project,
        )
        ports = types.SimpleNamespace(
            workspace_registry=workspace_registry,
            job_scheduler=types.SimpleNamespace(schedule=lambda coro, name="": asyncio.get_event_loop().create_task(coro)),
        )
        adapter = RuntimeJobAdapter(
            profile=self.profile,
            ports=ports,
            sync_engine=self.sync,
        )
        adapter.state.watcher_started = True

        with self.assertRaises(WatcherRebindError) as ctx:
            await adapter.rebind_watcher("does-not-exist")

        self.assertEqual(ctx.exception.status_code, 404)

    async def test_rebind_drains_old_project_before_stop(self) -> None:
        """sync_planning_artifacts is called for the outgoing project before stop."""
        adapter = self._make_adapter()
        await adapter.rebind_watcher(self.new_project.id)
        self.sync.sync_planning_artifacts.assert_called_once()
        call_args = self.sync.sync_planning_artifacts.call_args
        self.assertEqual(call_args.args[0], self.old_project.id)

    async def test_rebind_api_profile_returns_watcher_not_enabled(self) -> None:
        """For the api profile (watch=False), rebind is a no-op."""
        api_profile = get_runtime_profile("api")
        ports = types.SimpleNamespace(
            workspace_registry=types.SimpleNamespace(resolve_project_binding=lambda *a, **kw: None),
        )
        adapter = RuntimeJobAdapter(
            profile=api_profile,
            ports=ports,
            sync_engine=self.sync,
        )
        result = await adapter.rebind_watcher("any-project")
        self.assertFalse(result.get("watcherRebound"))
        self.assertEqual(result.get("error"), "watcher_not_enabled")


# ---------------------------------------------------------------------------
# Integration: full DB + real FileWatcher + one-shot sync
# ---------------------------------------------------------------------------


class WatcherRebindIntegrationTests(unittest.IsolatedAsyncioTestCase):
    """Tests that spin up a real SyncEngine + SQLite DB and verify DB state."""

    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)

        # Old project
        self.old_sessions = root / "old" / "sessions"
        self.old_docs = root / "old" / "docs"
        self.old_progress = root / "old" / "progress"
        for d in (self.old_sessions, self.old_docs, self.old_progress):
            d.mkdir(parents=True)

        # New project
        self.new_sessions = root / "new" / "sessions"
        self.new_docs = root / "new" / "docs"
        self.new_progress = root / "new" / "progress"
        for d in (self.new_sessions, self.new_docs, self.new_progress):
            d.mkdir(parents=True)

        self.old_root = root / "old"
        self.new_root = root / "new"

        self.old_project = _make_project("old-proj", self.old_sessions, self.old_docs, self.old_progress)
        self.new_project = _make_project("new-proj", self.new_sessions, self.new_docs, self.new_progress)

        self.old_paths = _make_resolved_paths(self.old_sessions, self.old_docs, self.old_progress, self.old_root)
        self.new_paths = _make_resolved_paths(self.new_sessions, self.new_docs, self.new_progress, self.new_root)

        self.old_binding = _make_binding(self.old_project, self.old_paths)
        self.new_binding = _make_binding(self.new_project, self.new_paths)

        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await self.db.execute("PRAGMA foreign_keys=ON")
        await run_migrations(self.db)

        self.sync_engine = SyncEngine(self.db)

        self.watcher = FileWatcher()
        self._watcher_patcher = patch("backend.adapters.jobs.runtime.file_watcher", self.watcher)
        self._watcher_patcher.start()

        # Start watcher on old project.
        await self.watcher.start(
            self.sync_engine,
            self.old_project.id,
            self.old_sessions,
            self.old_docs,
            self.old_progress,
        )

    async def asyncTearDown(self) -> None:
        await self.watcher.stop()
        self._watcher_patcher.stop()
        await self.db.close()
        self.tmp.cleanup()

    def _make_adapter(self) -> RuntimeJobAdapter:
        def resolve_binding(project_id, *, allow_active_fallback=True, refresh=False):
            if project_id == self.new_project.id:
                return self.new_binding
            if project_id == self.old_project.id:
                return self.old_binding
            return None

        workspace_registry = types.SimpleNamespace(
            resolve_project_binding=resolve_binding,
            get_active_project=lambda: self.old_project,
        )
        ports = types.SimpleNamespace(
            workspace_registry=workspace_registry,
            job_scheduler=types.SimpleNamespace(
                schedule=lambda coro, name="": asyncio.get_event_loop().create_task(coro),
            ),
        )
        profile = get_runtime_profile("local")
        adapter = RuntimeJobAdapter(
            profile=profile,
            ports=ports,
            sync_engine=self.sync_engine,
        )
        adapter.state.watcher_started = True
        return adapter

    async def _session_count(self, project_id: str) -> int:
        async with self.db.execute(
            "SELECT COUNT(*) AS count FROM sessions WHERE project_id = ?",
            (project_id,),
        ) as cur:
            row = await cur.fetchone()
        return int(row["count"]) if row else 0

    def _write_session_file(self, sessions_dir: Path, filename: str, project_id: str) -> Path:
        """Write a minimal valid JSONL session file."""
        path = sessions_dir / filename
        entry = {
            "type": "user",
            "timestamp": "2026-05-20T10:00:00Z",
            "uuid": f"u-{filename}",
            "message": {"role": "user", "content": f"Hello from {project_id}"},
        }
        path.write_text(json.dumps(entry) + "\n", encoding="utf-8")
        return path

    async def test_successful_rebind_populates_sessions_table_for_new_project(self) -> None:
        """After rebind, a session file in the new project appears in the sessions table."""
        # Write a session file in new project BEFORE rebind (one-shot sync must pick it up).
        self._write_session_file(self.new_sessions, "new-session.jsonl", self.new_project.id)

        adapter = self._make_adapter()
        result = await adapter.rebind_watcher(self.new_project.id)

        self.assertTrue(result.get("watcherRebound"))
        count = await self._session_count(self.new_project.id)
        self.assertGreater(count, 0, "Expected at least one session row for the new project after rebind")

    async def test_successful_rebind_updates_snapshot_to_new_project(self) -> None:
        """After rebind, file_watcher.snapshot() reflects the new project's ID and paths."""
        adapter = self._make_adapter()
        await adapter.rebind_watcher(self.new_project.id)

        snapshot = self.watcher.snapshot()
        self.assertEqual(snapshot["projectId"], self.new_project.id)
        watch_paths = snapshot["watchPaths"]
        self.assertTrue(
            any(str(self.new_sessions) in p for p in watch_paths),
            f"new sessions dir not in watchPaths: {watch_paths}",
        )

    async def test_failed_rebind_bad_paths_leaves_watcher_on_old_project(self) -> None:
        """Bad paths → WatcherRebindError raised, watcher stays on old project, table unchanged."""
        bad_paths = _make_resolved_paths(
            self.new_root / "no-sessions",
            self.new_root / "no-docs",
            self.new_root / "no-progress",
            self.new_root,
        )
        bad_binding = _make_binding(self.new_project, bad_paths)

        def resolve_binding(project_id, *, allow_active_fallback=True, refresh=False):
            if project_id == self.new_project.id:
                return bad_binding
            if project_id == self.old_project.id:
                return self.old_binding
            return None

        workspace_registry = types.SimpleNamespace(
            resolve_project_binding=resolve_binding,
            get_active_project=lambda: self.old_project,
        )
        ports = types.SimpleNamespace(
            workspace_registry=workspace_registry,
            job_scheduler=types.SimpleNamespace(schedule=lambda coro, name="": asyncio.get_event_loop().create_task(coro)),
        )
        adapter = RuntimeJobAdapter(
            profile=get_runtime_profile("local"),
            ports=ports,
            sync_engine=self.sync_engine,
        )
        adapter.state.watcher_started = True

        with self.assertRaises(WatcherRebindError):
            await adapter.rebind_watcher(self.new_project.id)

        # Watcher must still be running (not stopped).
        self.assertTrue(self.watcher.is_running, "Watcher should still be running after bad-paths rebind failure")
        snapshot = self.watcher.snapshot()
        self.assertEqual(snapshot["projectId"], self.old_project.id, "Watcher should still point to old project")
        # Sessions table should have no rows for new project.
        count = await self._session_count(self.new_project.id)
        self.assertEqual(count, 0)


# ---------------------------------------------------------------------------
# Router-level: POST /api/projects/active/{project_id}
# ---------------------------------------------------------------------------


class WatcherRebindRouterTests(unittest.TestCase):
    """Tests that exercise the FastAPI router via TestClient with dependency overrides."""

    def _build_test_app(
        self,
        *,
        rebind_result: dict | None = None,
        rebind_raises: Exception | None = None,
        project_id: str = "project-x",
        project_name: str = "Project X",
        include_job_adapter: bool = True,
    ):
        """Build a minimal FastAPI app with the projects router using dependency overrides.

        The projects router imports get_request_context from backend.runtime.dependencies
        (which contains an isinstance(container, RuntimeContainer) check) and get_core_ports
        from backend.request_scope.  We override both at their canonical callsites.
        """
        from fastapi import FastAPI
        from backend.routers.projects import projects_router
        from backend.request_scope import get_core_ports
        from backend.runtime import dependencies as runtime_deps

        app = FastAPI()
        app.include_router(projects_router)

        # Minimal project
        project = MagicMock()
        project.id = project_id
        project.name = project_name
        project.model_dump.return_value = {"id": project_id, "name": project_name}

        # Workspace registry
        workspace_registry = MagicMock()
        workspace_registry.get_project.return_value = project
        workspace_registry.get_active_project.return_value = project
        workspace_registry.set_active_project.return_value = None

        # Core ports
        core_ports = MagicMock()
        core_ports.workspace_registry = workspace_registry

        # Request context: non-hosted so we skip the hosted branch.
        request_context = MagicMock()
        request_context.principal = MagicMock()
        request_context.principal.provider = MagicMock()
        request_context.principal.provider.hosted = False

        # Override both dependency chains used by the projects router.
        # The router uses:
        #   - backend.request_scope.get_core_ports
        #   - backend.runtime.dependencies.get_request_context
        # Each depends internally on their own get_runtime_container.
        app.dependency_overrides[get_core_ports] = lambda: core_ports
        app.dependency_overrides[runtime_deps.get_request_context] = lambda: request_context
        app.dependency_overrides[runtime_deps.get_runtime_container] = lambda: MagicMock()

        # Job adapter on app.state
        if include_job_adapter:
            job_adapter = MagicMock()
            if rebind_raises is not None:
                job_adapter.rebind_watcher = AsyncMock(side_effect=rebind_raises)
            else:
                job_adapter.rebind_watcher = AsyncMock(return_value=rebind_result or {"watcherRebound": True})
            app.state.runtime_jobs = job_adapter

        return app

    def test_successful_switch_returns_200_with_watcher_rebound_true(self) -> None:
        app = self._build_test_app(rebind_result={"watcherRebound": True})
        client = TestClient(app, raise_server_exceptions=True)
        response = client.post("/api/projects/active/project-x")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body.get("watcherRebound"))

    def test_bad_paths_returns_4xx(self) -> None:
        exc = WatcherRebindError("No paths exist", status_code=422)
        app = self._build_test_app(rebind_raises=exc)
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/api/projects/active/project-x")
        self.assertIn(response.status_code, (404, 422))

    def test_no_job_adapter_returns_watcher_rebound_none(self) -> None:
        """If runtime_jobs is not in app.state, response still succeeds with watcherRebound=None."""
        app = self._build_test_app(include_job_adapter=False)
        client = TestClient(app, raise_server_exceptions=True)
        response = client.post("/api/projects/active/project-x")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIsNone(body.get("watcherRebound"))


if __name__ == "__main__":
    unittest.main()
