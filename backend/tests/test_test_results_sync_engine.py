import tempfile
import unittest
from pathlib import Path

import aiosqlite

from backend import config
from backend.db.sqlite_migrations import run_migrations
from backend.db.sync_engine import SyncEngine


class SyncEngineTestResultsIngestionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._prev_test_flag = config.CCDASH_TEST_VISUALIZER_ENABLED
        config.CCDASH_TEST_VISUALIZER_ENABLED = True
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()
        config.CCDASH_TEST_VISUALIZER_ENABLED = self._prev_test_flag

    async def test_sync_test_results_ingests_then_skips_unchanged_xml(self) -> None:
        xml = """<?xml version="1.0" encoding="utf-8"?>
<testsuite name="suite">
  <testcase classname="tests.test_sample.TestSample" name="test_ok" time="0.005"/>
</testsuite>
"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            results_dir = Path(tmp_dir)
            xml_path = results_dir / "results.xml"
            xml_path.write_text(xml, encoding="utf-8")

            engine = SyncEngine(self.db)
            first = await engine.sync_test_results("project-1", results_dir)
            second = await engine.sync_test_results("project-1", results_dir)

        self.assertEqual(first["synced"], 1)
        self.assertEqual(first["errors"], 0)
        self.assertEqual(second["skipped"], 1)

        async with self.db.execute("SELECT COUNT(*) FROM test_runs") as cur:
            run_count = await cur.fetchone()
        self.assertEqual(run_count[0], 1)

        async with self.db.execute("SELECT COUNT(*) FROM test_results") as cur:
            result_count = await cur.fetchone()
        self.assertEqual(result_count[0], 1)

    async def test_sync_changed_files_processes_xml_when_test_results_dir_is_watched(self) -> None:
        xml = """<?xml version="1.0" encoding="utf-8"?>
<testsuite name="suite">
  <testcase classname="tests.test_sample.TestSample" name="test_changed" time="0.005"/>
</testsuite>
"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            sessions_dir = root / "sessions"
            docs_dir = root / "docs"
            progress_dir = root / "progress"
            results_dir = root / "test-results"
            sessions_dir.mkdir()
            docs_dir.mkdir()
            progress_dir.mkdir()
            results_dir.mkdir()
            xml_path = results_dir / "results.xml"
            xml_path.write_text(xml, encoding="utf-8")

            engine = SyncEngine(self.db)
            stats = await engine.sync_changed_files(
                "project-1",
                [("modified", xml_path)],
                sessions_dir=sessions_dir,
                docs_dir=docs_dir,
                progress_dir=progress_dir,
                test_results_dir=results_dir,
                trigger="api",
            )

        self.assertEqual(stats["tests"], 1)


if __name__ == "__main__":
    unittest.main()
