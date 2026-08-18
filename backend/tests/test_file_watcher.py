import asyncio
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
from backend.db import file_watcher as file_watcher_module
from backend.db.file_watcher import FileWatcher
from backend.db.sqlite_migrations import run_migrations
from backend.db.sync_engine import SyncEngine
from backend.runtime.profiles import get_runtime_profile
from backend.runtime.storage_contract import get_runtime_storage_contract
from backend.services.source_identity import SourceIdentityPolicy, SourceRootAlias, SourceRootId
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
        # job_scheduler=None: _maybe_start_drain_loop (backend/adapters/jobs/runtime.py)
        # only starts the durable drain loop when
        # isinstance(ports.job_scheduler, DurableJobScheduler); any other value
        # (including None, the memory-backend default) makes that check False and
        # the method returns early as a no-op, which is exactly the api-profile
        # behaviour this test is asserting.
        ports = types.SimpleNamespace(workspace_registry=workspace_registry, job_scheduler=None)
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
                (engine._canonical_source_key("project-1", session_path, "session"),),
            ) as cur:
                sync_state = await cur.fetchone()

        self.assertEqual(first["sessions"], 1)
        self.assertEqual(second["sessions"], 1)
        self.assertEqual([message["content"] for message in messages], ["Start the work", "Finished the first step"])
        self.assertIsNotNone(sync_state)
        self.assertGreater(float(sync_state["file_mtime"]), 0)

    async def test_alias_session_reingest_keeps_replace_scoped_tables_stable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            host_sessions = root / "host-sessions"
            host_sessions.mkdir()
            container_sessions = root / "container-sessions"
            container_sessions.symlink_to(host_sessions, target_is_directory=True)
            docs_dir = root / "docs"
            progress_dir = root / "progress"
            docs_dir.mkdir()
            progress_dir.mkdir()

            session_path = host_sessions / "alias-session.jsonl"
            session_path.write_text(
                json.dumps(
                    {
                        "type": "user",
                        "timestamp": "2026-05-02T10:00:00Z",
                        "uuid": "u1",
                        "message": {"role": "user", "content": "Start alias work"},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            alias_path = container_sessions / "alias-session.jsonl"

            engine = SyncEngine(self.db)
            engine._source_identity_policy = SourceIdentityPolicy(
                aliases=(
                    SourceRootAlias(
                        root_id=SourceRootId("session_mount"),
                        alias_path=host_sessions,
                    ),
                    SourceRootAlias(
                        root_id=SourceRootId("session_mount"),
                        alias_path=container_sessions,
                    ),
                )
            )

            first = await engine._sync_single_session("project-1", session_path)
            counts_after_first = await self._table_counts(
                "sessions",
                "session_messages",
                "telemetry_events",
                "session_usage_attributions",
                "sync_state",
            )
            second = await engine._sync_single_session("project-1", alias_path, force=True)
            counts_after_second = await self._table_counts(
                "sessions",
                "session_messages",
                "telemetry_events",
                "session_usage_attributions",
                "sync_state",
            )
            source_files = await self._session_source_files()

        self.assertTrue(first)
        self.assertTrue(second)
        self.assertEqual(counts_after_first, counts_after_second)
        self.assertEqual(len(source_files), 1)
        self.assertIn("ccdash-source:v1/project-1/session/session_mount/alias-session.jsonl", source_files)

    async def _table_counts(self, *table_names: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for table_name in table_names:
            async with self.db.execute(f"SELECT COUNT(*) AS count FROM {table_name}") as cur:
                row = await cur.fetchone()
                counts[table_name] = int(row["count"])
        return counts

    async def _session_source_files(self) -> set[str]:
        async with self.db.execute("SELECT source_file FROM sessions") as cur:
            rows = await cur.fetchall()
        return {str(row["source_file"]) for row in rows}


class _ScriptedAwatch:
    """Stand-in for ``watchfiles.awatch`` that replays a fixed tick script.

    ``_watch_loop`` consumes ``awatch(*paths, stop_event=...)`` as an async
    iterator, so a callable returning an async generator is a faithful
    substitute. The generator ends after the scripted ticks, which lets
    ``_watch_loop`` return normally instead of being cancelled — so a test can
    await it directly and then inspect the resulting snapshot.
    """

    def __init__(self, ticks: list[set[tuple[Change, str]]]) -> None:
        self.ticks = ticks
        self.call_count = 0

    def __call__(self, *paths, **kwargs):
        self.call_count += 1
        return self._iterate()

    async def _iterate(self):
        for tick in self.ticks:
            yield tick
            # Yield to the loop between ticks so any per-tick timeout the
            # watcher installed gets a chance to fire.
            await asyncio.sleep(0)


class WatcherPerTickProgressTests(unittest.IsolatedAsyncioTestCase):
    """Regression coverage for the 2026-08-13 loop-dead incident (AC1-AC3).

    The Mac watcher stayed alive for ~44h while dispatching nothing: the loop
    never exited, so ``is_running`` was True, and every snapshot field that
    could have revealed the stall was written only inside ``if classified:``.
    """

    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.sessions_dir = root / "sessions"
        self.docs_dir = root / "docs"
        self.progress_dir = root / "progress"
        for directory in (self.sessions_dir, self.docs_dir, self.progress_dir):
            directory.mkdir()

        self._orig_awatch = file_watcher_module.awatch
        self._orig_timeout = file_watcher_module.config.WATCHER_DISPATCH_TIMEOUT_SECONDS

    async def asyncTearDown(self) -> None:
        file_watcher_module.awatch = self._orig_awatch
        file_watcher_module.config.WATCHER_DISPATCH_TIMEOUT_SECONDS = self._orig_timeout
        self._tmp.cleanup()

    def _install_ticks(self, ticks: list[set[tuple[Change, str]]]) -> _ScriptedAwatch:
        scripted = _ScriptedAwatch(ticks)
        file_watcher_module.awatch = scripted
        return scripted

    async def _drain(self, watcher: FileWatcher, sync_engine) -> None:
        watcher._running = True
        await watcher._watch_loop(
            sync_engine,
            "proj-loop-dead",
            self.sessions_dir,
            self.docs_dir,
            self.progress_dir,
            [self.sessions_dir],
        )

    async def test_hung_dispatch_times_out_and_later_ticks_are_still_observed(self) -> None:
        """AC1: a dispatch that never returns must not wedge the watch loop.

        Mechanism B of the incident: ``sync_changed_files`` awaiting a DB pool
        whose connections were all reset. Without the bounded dispatch the
        first tick blocks forever and tick 2 is never seen at all.
        """
        # Short override — never the production default (120s).
        file_watcher_module.config.WATCHER_DISPATCH_TIMEOUT_SECONDS = 1

        dispatch_calls: list[int] = []

        async def _never_returns(project_id, classified, *args, **kwargs):
            dispatch_calls.append(len(classified))
            await asyncio.sleep(999)

        sync_engine = types.SimpleNamespace(sync_changed_files=_never_returns)

        # Tick 1 carries one raw change, tick 2 carries two — so the tick
        # counters prove WHICH tick was observed last, not merely that one was.
        self._install_ticks([
            {(Change.modified, str(self.sessions_dir / "one.jsonl"))},
            {
                (Change.modified, str(self.sessions_dir / "two.jsonl")),
                (Change.modified, str(self.sessions_dir / "three.jsonl")),
            },
        ])

        watcher = FileWatcher()
        await self._drain(watcher, sync_engine)

        snapshot = watcher.snapshot()

        # The load-bearing assertion: the SECOND tick was dispatched at all.
        self.assertEqual(len(dispatch_calls), 2, "second tick was never observed — loop wedged")
        self.assertEqual(snapshot["lastTickRawChangeCount"], 2)
        self.assertEqual(snapshot["lastTickClassifiedChangeCount"], 2)
        # Both ticks had real classified work and a genuinely attempted (but
        # timed-out) dispatch, so this belongs to the FAILURE counter, not
        # the "nothing to classify" counter — see the churn-vs-failure split
        # documented on FileWatcherSnapshot.
        self.assertEqual(snapshot["consecutiveFailedDispatches"], 2)
        self.assertEqual(snapshot["consecutiveTicksWithoutDispatch"], 0)
        self.assertEqual(snapshot["lastSyncStatus"], "failed")
        self.assertIn("timed out", str(snapshot["lastSyncError"]))
        self.assertIsNotNone(snapshot["lastTickAt"])

    async def test_repeated_timeouts_on_real_work_trip_watcher_is_inert(self) -> None:
        """End-to-end TIMEOUT path THROUGH the threshold: the existing timeout
        test above stops at 2 timed-out dispatches and never calls
        ``watcher_is_inert`` at all. This drives ``_watch_loop`` with enough
        timing-out dispatches on real classified work (one raw+classified
        change per tick, never junk) to reach ``min_inert_ticks``, then feeds
        the resulting real snapshot into the predicate and asserts it trips —
        proving the wiring end-to-end, not just the predicate's logic on a
        hand-built dict.
        """
        from datetime import datetime, timedelta, timezone

        from backend.db.file_watcher import watcher_is_inert

        file_watcher_module.config.WATCHER_DISPATCH_TIMEOUT_SECONDS = 1

        min_inert_ticks = 5

        async def _never_returns(project_id, classified, *args, **kwargs):
            await asyncio.sleep(999)

        sync_engine = types.SimpleNamespace(sync_changed_files=_never_returns)

        self._install_ticks([
            {(Change.modified, str(self.sessions_dir / f"real-{i}.jsonl"))}
            for i in range(min_inert_ticks)
        ])

        watcher = FileWatcher()
        await self._drain(watcher, sync_engine)

        snapshot = watcher.snapshot()
        self.assertEqual(snapshot["consecutiveFailedDispatches"], min_inert_ticks)
        self.assertIsNone(snapshot["lastSuccessfulDispatchAt"])

        now = datetime.now(timezone.utc)
        aged_snapshot = dict(snapshot)
        aged_snapshot["lastTickAt"] = (now - timedelta(seconds=5)).isoformat().replace("+00:00", "Z")
        self.assertTrue(
            watcher_is_inert(
                aged_snapshot,
                now=now,
                stale_seconds=900,
                min_inert_ticks=min_inert_ticks,
            )
        )

    async def test_empty_classification_tick_advances_progress_fields_only(self) -> None:
        """AC2: mechanism A — classify returns empty forever.

        The tick-level fields must advance (proving the loop is turning) while
        ``lastChangeSyncAt`` stays untouched (proving nothing was dispatched).
        Before the fix, both stayed None and an inert watcher was byte-for-byte
        indistinguishable from a healthy idle one.
        """
        dispatch_calls: list[object] = []

        async def _record(project_id, classified, *args, **kwargs):
            dispatch_calls.append(classified)

        sync_engine = types.SimpleNamespace(sync_changed_files=_record)

        # ``.tmp`` is classified away, so ``classified`` is empty.
        self._install_ticks([
            {(Change.modified, str(self.sessions_dir / "scratch.tmp"))},
            {(Change.modified, str(self.sessions_dir / "other.tmp"))},
        ])

        watcher = FileWatcher()
        await self._drain(watcher, sync_engine)

        snapshot = watcher.snapshot()

        self.assertEqual(dispatch_calls, [], "empty classification must not dispatch")
        # Tick-level progress advanced …
        self.assertIsNotNone(snapshot["lastTickAt"])
        self.assertEqual(snapshot["lastTickRawChangeCount"], 1)
        self.assertEqual(snapshot["lastTickClassifiedChangeCount"], 0)
        self.assertEqual(snapshot["consecutiveTicksWithoutDispatch"], 2)
        # … while the dispatch-level fields did NOT.
        self.assertIsNone(snapshot["lastChangeSyncAt"])
        self.assertIsNone(snapshot["lastChangeCount"])
        self.assertIsNone(snapshot["lastSyncStatus"])
        self.assertIsNone(snapshot["lastSyncError"])

    async def test_classified_changes_log_renders_counts_in_message_text(self) -> None:
        """AC3: the counts must survive into the RENDERED message.

        Asserting on ``record.raw_change_count`` would only test the ``extra=``
        dict — invisible to every plain-text consumer (``podman logs``, a tail
        over the relay), which is why the incident could not be diagnosed from
        the log it had already written. So this asserts on
        ``record.getMessage()``.
        """
        async def _noop(project_id, classified, *args, **kwargs):
            return None

        sync_engine = types.SimpleNamespace(sync_changed_files=_noop)

        # 2 raw changes, 1 of which classifies (the ``.tmp`` is dropped).
        self._install_ticks([
            {
                (Change.modified, str(self.sessions_dir / "kept.jsonl")),
                (Change.modified, str(self.sessions_dir / "dropped.tmp")),
            },
        ])

        watcher = FileWatcher()
        with self.assertLogs("ccdash.watcher", level="INFO") as captured:
            await self._drain(watcher, sync_engine)

        rendered = [
            record.getMessage()
            for record in captured.records
            if "classified changes" in record.getMessage()
        ]
        self.assertEqual(len(rendered), 1, f"expected one classified-changes line, got {rendered}")
        message = rendered[0]
        self.assertIn("raw=2", message)
        self.assertIn("classified=1", message)


if __name__ == "__main__":
    unittest.main()
