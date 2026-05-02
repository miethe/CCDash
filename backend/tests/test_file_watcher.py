import json
import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock

import aiosqlite
from watchfiles import Change

from backend.adapters.jobs.runtime import RuntimeJobAdapter
from backend.db.file_watcher import FileWatcher
from backend.db.sqlite_migrations import run_migrations
from backend.db.sync_engine import SyncEngine
from backend.runtime.profiles import get_runtime_profile
from backend.runtime.storage_contract import get_runtime_storage_contract
from backend.services.test_config import ResolvedTestSource


class RuntimeWatcherContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_api_runtime_contract_disables_incidental_watcher_and_sync(self) -> None:
        contract = get_runtime_storage_contract(get_runtime_profile("api"))

        self.assertEqual(contract.allowed_storage_profiles, ("enterprise",))
        self.assertEqual(contract.sync_behavior, "no_incidental_sync_or_watch")
        self.assertNotIn("watcher_runtime", contract.readiness_checks)
        self.assertNotIn("startup_sync", contract.readiness_checks)

    async def test_worker_watch_contract_requires_watcher_and_startup_sync(self) -> None:
        contract = get_runtime_storage_contract(get_runtime_profile("worker-watch"))

        self.assertIn("watcher_runtime", contract.readiness_checks)
        self.assertIn("startup_sync", contract.readiness_checks)

    async def test_job_adapter_does_not_resolve_binding_or_start_watcher_for_api_profile(self) -> None:
        workspace_registry = types.SimpleNamespace(resolve_project_binding=Mock())
        ports = types.SimpleNamespace(workspace_registry=workspace_registry)
        adapter = RuntimeJobAdapter(
            profile=get_runtime_profile("api"),
            ports=ports,
            sync_engine=object(),
        )

        state = await adapter.start()
        status = adapter.status_snapshot()

        workspace_registry.resolve_project_binding.assert_not_called()
        self.assertFalse(state.watcher_started)
        self.assertEqual(status["watcher"], "not_expected")
        self.assertEqual(
            status["watcherDetail"],
            {
                "state": "not_expected",
                "expected": False,
                "enabled": False,
                "configured": False,
                "running": False,
                "watchPathCount": 0,
                "watchPaths": [],
                "lastChangeSyncAt": None,
                "lastChangeCount": None,
                "lastSyncStatus": None,
                "lastSyncError": None,
            },
        )


class FileWatcherClassificationTests(unittest.TestCase):
    def test_classify_changes_only_accepts_test_artifacts_inside_watched_test_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            sessions_dir = root / "sessions"
            docs_dir = root / "docs"
            progress_dir = root / "progress"
            test_dir = root / "pytest-results"
            ignored_dir = root / "random-results"
            for directory in (sessions_dir, docs_dir, progress_dir, test_dir, ignored_dir):
                directory.mkdir()

            watcher = FileWatcher()
            test_source = ResolvedTestSource(
                platform_id="pytest",
                enabled=True,
                watch=True,
                results_dir=str(test_dir),
                resolved_dir=test_dir,
                patterns=["**/*.xml"],
            )

            classified = watcher._classify_changes(
                {
                    (Change.modified, str(sessions_dir / "session.jsonl")),
                    (Change.modified, str(docs_dir / "note.md")),
                    (Change.modified, str(test_dir / "junit.xml")),
                    (Change.modified, str(ignored_dir / "junit.xml")),
                    (Change.modified, str(sessions_dir / "scratch.tmp")),
                },
                sessions_dir=sessions_dir,
                docs_dir=docs_dir,
                progress_dir=progress_dir,
                test_sources=[test_source],
            )

        self.assertEqual(
            {(change_type, path.name) for change_type, path in classified},
            {
                ("modified", "session.jsonl"),
                ("modified", "note.md"),
                ("modified", "junit.xml"),
            },
        )

    def test_resolve_watch_paths_omits_disabled_test_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            sessions_dir = root / "sessions"
            docs_dir = root / "docs"
            progress_dir = root / "progress"
            enabled_dir = root / "enabled-tests"
            disabled_dir = root / "disabled-tests"
            for directory in (sessions_dir, docs_dir, progress_dir, enabled_dir, disabled_dir):
                directory.mkdir()

            watcher = FileWatcher()
            watch_paths = watcher._resolve_watch_paths(
                sessions_dir,
                docs_dir,
                progress_dir,
                test_sources=[
                    ResolvedTestSource(
                        platform_id="enabled",
                        enabled=True,
                        watch=True,
                        results_dir=str(enabled_dir),
                        resolved_dir=enabled_dir,
                        patterns=["**/*.xml"],
                    ),
                    ResolvedTestSource(
                        platform_id="disabled",
                        enabled=False,
                        watch=True,
                        results_dir=str(disabled_dir),
                        resolved_dir=disabled_dir,
                        patterns=["**/*.xml"],
                    ),
                ],
            )

        self.assertEqual(watch_paths, [sessions_dir, docs_dir, progress_dir, enabled_dir])


class JsonlAppendIncrementalSyncTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await self.db.execute("PRAGMA foreign_keys=ON")
        await run_migrations(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_sync_changed_files_reprocesses_jsonl_after_append(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            sessions_dir = root / "sessions"
            docs_dir = root / "docs"
            progress_dir = root / "progress"
            for directory in (sessions_dir, docs_dir, progress_dir):
                directory.mkdir()
            session_path = sessions_dir / "append-session.jsonl"

            first_entry = {
                "type": "user",
                "timestamp": "2026-05-02T10:00:00Z",
                "uuid": "u1",
                "message": {"role": "user", "content": "Start the work"},
            }
            appended_entry = {
                "type": "assistant",
                "timestamp": "2026-05-02T10:00:01Z",
                "uuid": "a1",
                "parentUuid": "u1",
                "message": {
                    "role": "assistant",
                    "model": "claude-sonnet",
                    "content": [{"type": "text", "text": "Finished the first step"}],
                },
            }
            session_path.write_text(json.dumps(first_entry) + "\n", encoding="utf-8")

            engine = SyncEngine(self.db)
            first = await engine.sync_changed_files(
                "project-1",
                [("modified", session_path)],
                sessions_dir=sessions_dir,
                docs_dir=docs_dir,
                progress_dir=progress_dir,
            )
            first_mtime = session_path.stat().st_mtime

            with session_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(appended_entry) + "\n")
            os.utime(session_path, (first_mtime + 1, first_mtime + 1))

            second = await engine.sync_changed_files(
                "project-1",
                [("modified", session_path)],
                sessions_dir=sessions_dir,
                docs_dir=docs_dir,
                progress_dir=progress_dir,
            )

            session_id = "S-append-session"
            messages = await engine.session_message_repo.list_by_session(session_id)
            async with self.db.execute(
                "SELECT file_mtime FROM sync_state WHERE file_path = ?",
                (str(session_path),),
            ) as cur:
                sync_state = await cur.fetchone()

        self.assertEqual(first["sessions"], 1)
        self.assertEqual(second["sessions"], 1)
        self.assertEqual([message["content"] for message in messages], ["Start the work", "Finished the first step"])
        self.assertIsNotNone(sync_state)
        self.assertGreater(float(sync_state["file_mtime"]), 0)


if __name__ == "__main__":
    unittest.main()
