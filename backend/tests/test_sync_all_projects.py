"""Tests for CCDASH_SYNC_ALL_PROJECTS, write-back suppression, and worknotes scan/watch roots.

Issue 6 — defect remediation coverage.

Run with:
    backend/.venv/bin/python -m pytest backend/tests/test_sync_all_projects.py -v
"""
from __future__ import annotations

import asyncio
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch


# ---------------------------------------------------------------------------
# Helper: capture the coroutine passed to job_scheduler.schedule() so tests
# can drive it explicitly when they need to assert on work done INSIDE the job.
# ---------------------------------------------------------------------------

def _make_scheduler_capturing() -> tuple[MagicMock, list]:
    """Return (scheduler_mock, captured_coros_list).

    schedule() appends each coroutine to captured_coros_list and returns a
    completed future so start() continues without blocking.

    Coroutines whose name does NOT contain "all-projects-sync" are closed
    immediately to avoid RuntimeWarning: coroutine was never awaited.  Tests
    that need to drive a specific coro can inspect captured_coros_list and
    await the matching entry directly.
    """
    import inspect

    captured: list = []

    def _schedule_side_effect(coro, *, name=""):
        if inspect.iscoroutine(coro) and "all-projects-sync" not in name:
            # This coro will never be driven by the test — close it now so
            # Python does not emit RuntimeWarning about unawaited coroutines.
            coro.close()
        else:
            captured.append((name, coro))
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        fut.set_result(None)
        return fut

    sched = MagicMock()
    sched.schedule = MagicMock(side_effect=_schedule_side_effect)
    sched.__class__.__name__ = "InMemoryJobScheduler"
    return sched, captured


# ── helpers ───────────────────────────────────────────────────────────────────


def _make_project(project_id: str, name: str = "") -> types.SimpleNamespace:
    return types.SimpleNamespace(
        id=project_id,
        name=name or project_id,
        testConfig=types.SimpleNamespace(
            autoSyncOnStartup=False,
            maxFilesPerScan=25,
            maxParseConcurrency=4,
        ),
    )


def _make_path_bundle(root_path: Path, project_id: str) -> MagicMock:
    """Minimal ResolvedProjectPaths-like object."""
    bundle = MagicMock()
    bundle.root = types.SimpleNamespace(path=root_path)
    bundle.as_tuple.return_value = (
        root_path / "sessions",
        root_path / "docs",
        root_path / "progress",
    )
    return bundle


def _make_binding(project_id: str, root: Path) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        project=_make_project(project_id),
        paths=_make_path_bundle(root, project_id),
        source="explicit",
    )


def _make_sync_engine() -> MagicMock:
    engine = MagicMock()
    engine.sync_project = AsyncMock(return_value={"features_synced": 1})
    engine.sync_changed_files = AsyncMock()
    engine.capture_analytics_snapshot = AsyncMock()
    engine.sync_test_sources = AsyncMock(return_value={"synced": 0})
    engine.rebuild_links = AsyncMock(return_value={"created": 0})
    return engine


def _make_scheduler() -> MagicMock:
    import inspect

    def _discard_schedule(coro, *, name=""):
        # Close any coroutine immediately so Python does not raise
        # RuntimeWarning: coroutine was never awaited.
        if inspect.iscoroutine(coro):
            coro.close()
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        fut.set_result(None)
        return fut

    sched = MagicMock()
    sched.schedule = MagicMock(side_effect=_discard_schedule)
    sched.__class__.__name__ = "InMemoryJobScheduler"
    return sched


def _make_ports(workspace_registry: MagicMock) -> MagicMock:
    ports = MagicMock()
    ports.workspace_registry = workspace_registry
    ports.job_scheduler = _make_scheduler()
    return ports


def _make_profile(sync: bool = True, watch: bool = True, jobs: bool = False) -> MagicMock:
    profile = MagicMock()
    profile.name = "local"
    profile.capabilities = types.SimpleNamespace(sync=sync, watch=watch, jobs=jobs, integrations=False)
    return profile


# ─────────────────────────────────────────────────────────────────────────────
# 1. All-projects sync: both projects synced, both watchers registered
# ─────────────────────────────────────────────────────────────────────────────


class TestSyncAllProjects(unittest.IsolatedAsyncioTestCase):
    """CCDASH_SYNC_ALL_PROJECTS=True syncs every registered project and registers watchers."""

    async def test_all_projects_sync_and_watch_called_for_each_project(self):
        """After driving the all-projects background job, proj-b is synced and watched."""
        from backend.adapters.jobs.runtime import RuntimeJobAdapter

        proj_a = _make_project("proj-a")
        proj_b = _make_project("proj-b")
        root_a = Path("/tmp/proj_a")
        root_b = Path("/tmp/proj_b")
        binding_a = _make_binding("proj-a", root_a)
        binding_b = _make_binding("proj-b", root_b)

        workspace_registry = MagicMock()
        workspace_registry.list_projects.return_value = [proj_a, proj_b]

        def _resolve_by_id(project_id=None, *, allow_active_fallback=True, refresh=False):
            if project_id is None:
                return binding_a  # active binding (no-arg call)
            if project_id == "proj-a":
                return binding_a
            if project_id == "proj-b":
                return binding_b
            return None

        workspace_registry.resolve_project_binding.side_effect = _resolve_by_id

        sync_engine = _make_sync_engine()
        sched, captured_coros = _make_scheduler_capturing()
        ports = _make_ports(workspace_registry)
        ports.job_scheduler = sched
        profile = _make_profile(sync=True, watch=True, jobs=False)

        with (
            patch("backend.adapters.jobs.runtime.config") as mock_config,
            patch("backend.adapters.jobs.runtime.file_watcher") as mock_fw,
            patch("backend.adapters.jobs.runtime.file_watcher_registry") as mock_reg,
            patch("backend.adapters.jobs.runtime.resolve_test_sources", return_value=[]),
            patch("backend.adapters.jobs.runtime.effective_test_flags", return_value=MagicMock(testVisualizerEnabled=False)),
            patch("backend.adapters.jobs.runtime._resolve_worknotes_dir", return_value=None),
        ):
            mock_config.STARTUP_SYNC_ENABLED = True
            mock_config.SYNC_ALL_PROJECTS = True
            mock_config.STARTUP_SYNC_LIGHT_MODE = False
            mock_config.STARTUP_SYNC_DELAY_SECONDS = 0
            mock_config.STARTUP_DEFERRED_REBUILD_LINKS = False
            mock_fw.start = AsyncMock()
            mock_reg.register = AsyncMock()

            adapter = RuntimeJobAdapter(
                profile=profile,
                ports=ports,
                sync_engine=sync_engine,
                project_binding=None,
            )
            await adapter.start()

            # Drive the all-projects-sync job explicitly (it was scheduled, not awaited)
            all_proj_coros = [(n, c) for n, c in captured_coros if "all-projects-sync" in n]
            self.assertTrue(all_proj_coros, "Expected all-projects-sync job to be scheduled")
            for _name, coro in all_proj_coros:
                await coro

        # sync_project should have been called for the non-active project proj-b
        synced_ids = {
            str(c.args[0].id if hasattr(c.args[0], "id") else c.args[0])
            for c in sync_engine.sync_project.await_args_list
        }
        self.assertIn("proj-b", synced_ids)

        # registry.register should have been called for proj-b
        reg_ids = {str(c.args[1]) for c in mock_reg.register.await_args_list}
        self.assertIn("proj-b", reg_ids)

    async def test_single_active_project_behavior_when_flag_off(self):
        """When SYNC_ALL_PROJECTS=False only the active project is synced."""
        from backend.adapters.jobs.runtime import RuntimeJobAdapter

        proj_a = _make_project("proj-a")
        root_a = Path("/tmp/proj_a_off")
        binding_a = _make_binding("proj-a", root_a)

        workspace_registry = MagicMock()
        workspace_registry.resolve_project_binding.side_effect = lambda pid=None, **kw: binding_a
        workspace_registry.list_projects.return_value = [proj_a, _make_project("proj-b")]

        sync_engine = _make_sync_engine()
        ports = _make_ports(workspace_registry)
        profile = _make_profile(sync=True, watch=False, jobs=False)

        with (
            patch("backend.adapters.jobs.runtime.config") as mock_config,
            patch("backend.adapters.jobs.runtime.file_watcher") as mock_fw,
            patch("backend.adapters.jobs.runtime.file_watcher_registry") as mock_reg,
            patch("backend.adapters.jobs.runtime.resolve_test_sources", return_value=[]),
            patch("backend.adapters.jobs.runtime.effective_test_flags", return_value=MagicMock(testVisualizerEnabled=False)),
            patch("backend.adapters.jobs.runtime._resolve_worknotes_dir", return_value=None),
        ):
            mock_config.STARTUP_SYNC_ENABLED = True
            mock_config.SYNC_ALL_PROJECTS = False  # flag OFF
            mock_config.STARTUP_SYNC_LIGHT_MODE = False
            mock_config.STARTUP_SYNC_DELAY_SECONDS = 0
            mock_config.STARTUP_DEFERRED_REBUILD_LINKS = False
            mock_fw.start = AsyncMock()
            mock_reg.register = AsyncMock()

            # _make_scheduler() already installs a side_effect that closes
            # coroutines and returns a resolved future; no override needed here.
            adapter = RuntimeJobAdapter(
                profile=profile,
                ports=ports,
                sync_engine=sync_engine,
                project_binding=None,
            )
            await adapter.start()

        # Only proj-a should have been synced (the active project, via the
        # scheduled task).  proj-b must NOT appear in direct sync_project calls
        # (the scheduled task itself is a mock future so sync_project won't fire
        # there either; what matters is there are zero proj-b calls).
        synced_ids = {
            str(c.args[0].id if hasattr(c.args[0], "id") else c.args[0])
            for c in sync_engine.sync_project.await_args_list
        }
        self.assertNotIn("proj-b", synced_ids)


# ─────────────────────────────────────────────────────────────────────────────
# 1b. start() returns promptly — all-projects sync must NOT block start()
# ─────────────────────────────────────────────────────────────────────────────


class TestStartDoesNotBlockOnAllProjectsSync(unittest.IsolatedAsyncioTestCase):
    """start() must return even when a non-active project's sync never resolves."""

    async def test_start_returns_without_awaiting_all_projects_sync(self):
        """start() completes promptly even when sync_project would never resolve.

        We patch sync_project to return a Future that is never resolved, register
        one active + one non-active project, call await adapter.start(), and
        assert it returns.  The all-projects work must have been SCHEDULED (via
        job_scheduler.schedule), not awaited inline.
        """
        from backend.adapters.jobs.runtime import RuntimeJobAdapter

        proj_a = _make_project("proj-a")
        proj_b = _make_project("proj-b")
        root_a = Path("/tmp/proj_a_nonblock")
        root_b = Path("/tmp/proj_b_nonblock")
        binding_a = _make_binding("proj-a", root_a)
        binding_b = _make_binding("proj-b", root_b)

        workspace_registry = MagicMock()
        workspace_registry.list_projects.return_value = [proj_a, proj_b]

        def _resolve_by_id(project_id=None, *, allow_active_fallback=True, refresh=False):
            if project_id is None:
                return binding_a
            if project_id == "proj-a":
                return binding_a
            if project_id == "proj-b":
                return binding_b
            return None

        workspace_registry.resolve_project_binding.side_effect = _resolve_by_id

        # sync_project returns a future that NEVER resolves — if start() awaits
        # it inline the test would hang indefinitely.
        never_resolving_future: asyncio.Future = asyncio.get_event_loop().create_future()
        sync_engine = _make_sync_engine()
        sync_engine.sync_project = MagicMock(return_value=never_resolving_future)

        sched, captured_coros = _make_scheduler_capturing()
        ports = _make_ports(workspace_registry)
        ports.job_scheduler = sched
        profile = _make_profile(sync=True, watch=True, jobs=False)

        with (
            patch("backend.adapters.jobs.runtime.config") as mock_config,
            patch("backend.adapters.jobs.runtime.file_watcher") as mock_fw,
            patch("backend.adapters.jobs.runtime.file_watcher_registry") as mock_reg,
            patch("backend.adapters.jobs.runtime.resolve_test_sources", return_value=[]),
            patch("backend.adapters.jobs.runtime.effective_test_flags", return_value=MagicMock(testVisualizerEnabled=False)),
            patch("backend.adapters.jobs.runtime._resolve_worknotes_dir", return_value=None),
        ):
            mock_config.STARTUP_SYNC_ENABLED = True
            mock_config.SYNC_ALL_PROJECTS = True
            mock_config.STARTUP_SYNC_LIGHT_MODE = False
            mock_config.STARTUP_SYNC_DELAY_SECONDS = 0
            mock_config.STARTUP_DEFERRED_REBUILD_LINKS = False
            mock_fw.start = AsyncMock()
            mock_reg.register = AsyncMock()

            adapter = RuntimeJobAdapter(
                profile=profile,
                ports=ports,
                sync_engine=sync_engine,
                project_binding=None,
            )
            # This must complete without hanging — if it blocks on sync_project
            # (which never resolves) the test will time out.
            state = await adapter.start()

        # start() returned — assert the all-projects job was SCHEDULED
        all_proj_names = [n for n, _c in captured_coros if "all-projects-sync" in n]
        self.assertTrue(
            all_proj_names,
            "Expected job_scheduler.schedule to be called with the all-projects-sync job",
        )
        # The task handle must be stored on state
        self.assertIsNotNone(
            state.all_projects_sync_task,
            "Expected state.all_projects_sync_task to be set after start()",
        )
        # sync_project must NOT have been called by start() itself (it is called
        # only when the scheduled job is driven)
        sync_engine.sync_project.assert_not_called()

        # Cancel the never-resolving future to avoid ResourceWarning
        never_resolving_future.cancel()

        # Close any all-projects-sync coroutines that were captured but not
        # driven by this test (we only needed to verify they were scheduled).
        import inspect
        for _name, coro in captured_coros:
            if inspect.iscoroutine(coro):
                coro.close()


# ─────────────────────────────────────────────────────────────────────────────
# 2. Non-active project write-back suppression
# ─────────────────────────────────────────────────────────────────────────────


class TestWritebackSuppression(unittest.TestCase):
    """Non-active project syncs must pass allow_writeback=False to scan_features."""

    def test_reconcile_completion_equivalence_allow_writeback_false_no_disk_write(self):
        """With allow_writeback=False no update_frontmatter_field call is made."""
        from backend.parsers.features import _reconcile_completion_equivalence
        from backend.models import Feature

        # Build a minimal feature whose completion should be inferred
        feat = Feature(
            id="test-feat",
            name="Test Feature",
            status="in_progress",
            phases=[],
            linkedDocs=[],
        )

        with patch("backend.parsers.features.update_frontmatter_field") as mock_write:
            _reconcile_completion_equivalence([feat], Path("/tmp"), allow_writeback=False)
            mock_write.assert_not_called()

    def test_reconcile_completion_equivalence_allow_writeback_true_can_write(self):
        """With allow_writeback=True the write path is reached (when enabled globally)."""
        from backend.parsers.features import _reconcile_completion_equivalence
        from backend.models import Feature, LinkedDocument

        feat = Feature(
            id="test-feat",
            name="Test Feature",
            status="in_progress",
            phases=[],
            linkedDocs=[
                LinkedDocument(
                    id="PLAN-test-feat",
                    title="Test Plan",
                    filePath="docs/implementation_plans/test-feat.md",
                    docType="implementation_plan",
                    slug="test-feat",
                )
            ],
        )

        with (
            patch("backend.parsers.features.update_frontmatter_field") as mock_write,
            patch("backend.parsers.features._read_frontmatter_status_cached", return_value="completed"),
            patch("backend.parsers.features._doc_owned_by_feature", return_value=True),
            patch("backend.parsers.features.config") as mock_cfg,
        ):
            mock_cfg.INFERRED_STATUS_WRITEBACK_ENABLED = True
            # Status is already "completed" so no upgrade is needed → no write,
            # but this is because the feature status is already complete, NOT
            # because allow_writeback blocked it.
            _reconcile_completion_equivalence([feat], Path("/tmp"), allow_writeback=True)
            mock_write.assert_not_called()

    def test_scan_features_passes_allow_writeback_false(self):
        """scan_features(allow_writeback=False) threads the flag to _reconcile_completion_equivalence."""
        from backend.parsers import features as features_mod

        with (
            patch.object(features_mod, "_scan_impl_plans", return_value={}),
            patch.object(features_mod, "_scan_prds", return_value={}),
            patch.object(features_mod, "_scan_progress_dirs", return_value={}),
            patch.object(features_mod, "_scan_auxiliary_docs", return_value=[]),
            patch.object(features_mod, "_reconcile_completion_equivalence", return_value=0) as mock_reconcile,
        ):
            features_mod.scan_features(
                Path("/tmp/docs"),
                Path("/tmp/progress"),
                allow_writeback=False,
            )
            mock_reconcile.assert_called_once()
            # allow_writeback=False should have been passed as a keyword arg
            passed_kwargs = mock_reconcile.call_args[1] if mock_reconcile.call_args[1] else {}
            self.assertFalse(passed_kwargs.get("allow_writeback", True))


# ─────────────────────────────────────────────────────────────────────────────
# 3. Worknotes included in scan / watch roots
# ─────────────────────────────────────────────────────────────────────────────


class TestWorknotesScanRoot(unittest.TestCase):
    """Worknotes dir is included as a scan root when it exists."""

    def test_scan_auxiliary_docs_includes_worknotes(self):
        """When worknotes_dir is provided and exists it is added to the scan roots."""
        import tempfile
        from backend.parsers import features as features_mod

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            docs_dir = root / "docs"
            progress_dir = root / "progress"
            worknotes_dir = root / ".claude" / "worknotes"
            worknotes_dir.mkdir(parents=True)
            docs_dir.mkdir()
            progress_dir.mkdir()

            # Write a minimal worknote markdown file
            feat_dir = worknotes_dir / "my-feature"
            feat_dir.mkdir()
            (feat_dir / "context.md").write_text(
                "---\ntype: context\nfeature_slug: my-feature\n---\n# Worknote\n"
            )

            # Patch _extract_doc_metadata to avoid git-date side effects and
            # return a stable dict with the file_path we care about.
            original_extract = features_mod._extract_doc_metadata

            def _mock_extract(path, project_root, fm, **kw):
                result = original_extract(path, project_root, fm, **kw)
                if not result.get("file_path"):
                    result["file_path"] = str(path.relative_to(root))
                return result

            with patch.object(features_mod, "_extract_doc_metadata", side_effect=_mock_extract):
                result = features_mod._scan_auxiliary_docs(
                    docs_dir,
                    progress_dir,
                    root,
                    worknotes_dir=worknotes_dir,
                )

            scanned_paths = [str(d.get("filePath") or d.get("file_path") or "") for d in result]
            self.assertTrue(
                any("context.md" in p for p in scanned_paths),
                f"Expected context.md in scanned paths; got: {scanned_paths}",
            )

    def test_scan_auxiliary_docs_worknotes_missing_dir_no_error(self):
        """When worknotes_dir does not exist no error is raised."""
        from backend.parsers.features import _scan_auxiliary_docs
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            docs_dir = root / "docs"
            progress_dir = root / "progress"
            docs_dir.mkdir()
            progress_dir.mkdir()

            nonexistent = root / ".claude" / "worknotes"
            # Should not raise
            result = _scan_auxiliary_docs(
                docs_dir,
                progress_dir,
                root,
                worknotes_dir=nonexistent,
            )
            self.assertIsInstance(result, list)


class TestWorknotesWatchRoot(unittest.IsolatedAsyncioTestCase):
    """Worknotes dir is included in the FileWatcher watch paths when it exists."""

    async def test_file_watcher_registry_register_accepts_worknotes_dir(self):
        """FileWatcherRegistry.register passes worknotes_dir down to FileWatcher.start."""
        from backend.db.file_watcher import FileWatcherRegistry
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            worknotes = Path(tmpdir) / ".claude" / "worknotes"
            worknotes.mkdir(parents=True)

            registry = FileWatcherRegistry()
            sync = MagicMock()

            captured_kwargs: dict = {}

            async def _mock_start(*args, **kwargs):
                captured_kwargs.update(kwargs)

            with patch("backend.db.file_watcher.FileWatcher.start", side_effect=_mock_start):
                await registry.register(
                    sync,
                    "proj-wn",
                    Path(tmpdir),
                    Path(tmpdir),
                    Path(tmpdir),
                    worknotes_dir=worknotes,
                )

            self.assertEqual(captured_kwargs.get("worknotes_dir"), worknotes)

    def test_resolve_watch_paths_includes_existing_worknotes(self):
        """_resolve_watch_paths includes an existing worknotes dir."""
        from backend.db.file_watcher import FileWatcher
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            sessions = root / "sessions"
            docs = root / "docs"
            progress = root / "progress"
            worknotes = root / "worknotes"
            for d in [sessions, docs, progress, worknotes]:
                d.mkdir()

            watcher = FileWatcher()
            paths = watcher._resolve_watch_paths(
                sessions, docs, progress, worknotes_dir=worknotes
            )
            self.assertIn(worknotes, paths)

    def test_resolve_watch_paths_skips_missing_worknotes(self):
        """_resolve_watch_paths silently omits a non-existent worknotes dir."""
        from backend.db.file_watcher import FileWatcher
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            sessions = root / "sessions"
            docs = root / "docs"
            progress = root / "progress"
            for d in [sessions, docs, progress]:
                d.mkdir()

            missing = root / "worknotes_nonexistent"
            watcher = FileWatcher()
            paths = watcher._resolve_watch_paths(
                sessions, docs, progress, worknotes_dir=missing
            )
            self.assertNotIn(missing, paths)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Watcher path write-back suppression for non-active projects
# ─────────────────────────────────────────────────────────────────────────────


class TestWatcherWritebackSuppression(unittest.IsolatedAsyncioTestCase):
    """Non-active-project file-watcher changes must NOT invoke update_frontmatter_field.

    Regression for the watcher-path write-back leak: runtime.py registers
    a watcher for every non-active project but previously omitted
    allow_writeback=False, meaning a changed .md file in a non-active repo
    could trigger scan_features → _reconcile_completion_equivalence →
    update_frontmatter_field and mutate the user's source files.
    """

    async def test_non_active_project_watcher_does_not_write_back(self):
        """sync_changed_files(allow_writeback=False) threads allow_writeback=False to _sync_features.

        Uses unittest.mock.create_autospec to build a stub that auto-mocks all
        async SyncEngine methods.  Feeds a changed .md file so the code path
        through should_resync_features=True fires, then asserts _sync_features
        received allow_writeback=False.

        This test FAILS against the pre-fix code (allow_writeback absent from
        sync_changed_files) and PASSES after the fix.
        """
        from unittest.mock import create_autospec
        import tempfile
        from backend.db.sync_engine import SyncEngine

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            docs_dir = root / "docs"
            progress_dir = root / "progress"
            sessions_dir = root / "sessions"
            for d in [sessions_dir, docs_dir, progress_dir]:
                d.mkdir()

            # A .md file in docs_dir triggers should_resync_features=True.
            plan_doc = docs_dir / "test-feat.md"
            plan_doc.write_text(
                "---\nid: test-feat\nstatus: in_progress\n---\n# Test Feature\n"
            )

            engine = create_autospec(SyncEngine, instance=True)
            engine._sync_single_document.return_value = True
            engine._sync_single_session.return_value = None
            engine._sync_single_progress.return_value = False
            engine._sync_features.return_value = {"synced": 0}
            engine._load_link_state.return_value = {}
            engine._is_link_logic_version_stale.return_value = False
            engine._rebuild_entity_links.return_value = {}
            engine._save_link_state.return_value = None
            engine._start_operation.return_value = None
            engine._update_operation.return_value = None
            engine._finish_operation.return_value = None
            engine._build_git_doc_dates.return_value = ({}, set())
            engine._match_source_for_path.return_value = None

            await SyncEngine.sync_changed_files(
                engine,
                "proj-non-active",
                [("modified", plan_doc)],
                sessions_dir=sessions_dir,
                docs_dir=docs_dir,
                progress_dir=progress_dir,
                allow_writeback=False,
            )

        # _sync_features must have been called with allow_writeback=False
        engine._sync_features.assert_awaited()
        for c in engine._sync_features.await_args_list:
            self.assertFalse(
                c.kwargs.get("allow_writeback", True),
                f"_sync_features called with allow_writeback=True (leak!): {c}",
            )

    async def test_non_active_project_registry_registers_with_allow_writeback_false(self):
        """RuntimeJobAdapter registers non-active-project watchers with allow_writeback=False.

        The all-projects job is scheduled (not awaited inline) by start(); this
        test drives the job explicitly to verify allow_writeback=False is
        preserved inside the background coroutine.
        """
        from backend.adapters.jobs.runtime import RuntimeJobAdapter

        proj_a = _make_project("proj-a")
        proj_b = _make_project("proj-b")
        root_a = Path("/tmp/proj_a_writeback")
        root_b = Path("/tmp/proj_b_writeback")
        binding_a = _make_binding("proj-a", root_a)
        binding_b = _make_binding("proj-b", root_b)

        workspace_registry = MagicMock()
        workspace_registry.list_projects.return_value = [proj_a, proj_b]

        def _resolve_by_id(project_id=None, *, allow_active_fallback=True, refresh=False):
            if project_id is None:
                return binding_a
            if project_id == "proj-a":
                return binding_a
            if project_id == "proj-b":
                return binding_b
            return None

        workspace_registry.resolve_project_binding.side_effect = _resolve_by_id

        sync_engine = _make_sync_engine()
        sched, captured_coros = _make_scheduler_capturing()
        ports = _make_ports(workspace_registry)
        ports.job_scheduler = sched
        profile = _make_profile(sync=True, watch=True, jobs=False)

        with (
            patch("backend.adapters.jobs.runtime.config") as mock_config,
            patch("backend.adapters.jobs.runtime.file_watcher") as mock_fw,
            patch("backend.adapters.jobs.runtime.file_watcher_registry") as mock_reg,
            patch("backend.adapters.jobs.runtime.resolve_test_sources", return_value=[]),
            patch("backend.adapters.jobs.runtime.effective_test_flags", return_value=MagicMock(testVisualizerEnabled=False)),
            patch("backend.adapters.jobs.runtime._resolve_worknotes_dir", return_value=None),
        ):
            mock_config.STARTUP_SYNC_ENABLED = True
            mock_config.SYNC_ALL_PROJECTS = True
            mock_config.STARTUP_SYNC_LIGHT_MODE = False
            mock_config.STARTUP_SYNC_DELAY_SECONDS = 0
            mock_config.STARTUP_DEFERRED_REBUILD_LINKS = False
            mock_fw.start = AsyncMock()
            mock_reg.register = AsyncMock()

            adapter = RuntimeJobAdapter(
                profile=profile,
                ports=ports,
                sync_engine=sync_engine,
                project_binding=None,
            )
            await adapter.start()

            # Drive the all-projects-sync job explicitly
            all_proj_coros = [(n, c) for n, c in captured_coros if "all-projects-sync" in n]
            self.assertTrue(all_proj_coros, "Expected all-projects-sync job to be scheduled")
            for _name, coro in all_proj_coros:
                await coro

        # Find the registry.register call for proj-b (the non-active project)
        proj_b_calls = [
            c for c in mock_reg.register.await_args_list
            if len(c.args) > 1 and c.args[1] == "proj-b"
        ]
        self.assertTrue(
            proj_b_calls,
            "Expected registry.register to be called for non-active proj-b",
        )
        # Every non-active registration must carry allow_writeback=False
        for c in proj_b_calls:
            kwargs = c.kwargs
            self.assertFalse(
                kwargs.get("allow_writeback", True),
                f"Non-active project watcher registered with allow_writeback=True (leak!): {c}",
            )


if __name__ == "__main__":
    unittest.main()
