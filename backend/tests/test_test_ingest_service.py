import unittest

import aiosqlite

from backend import config
from backend.db.sqlite_migrations import run_migrations
from backend.models import IngestRunRequest
from backend.services.test_ingest import ingest_run


class TestIngestServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._prev_flag = config.CCDASH_TEST_VISUALIZER_ENABLED
        config.CCDASH_TEST_VISUALIZER_ENABLED = True
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await self.db.execute("PRAGMA foreign_keys=ON")
        await run_migrations(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()
        config.CCDASH_TEST_VISUALIZER_ENABLED = self._prev_flag

    def _payload(self, run_id: str, rows: list[dict], session_id: str = "") -> IngestRunRequest:
        return IngestRunRequest(
            run_id=run_id,
            project_id="project-1",
            timestamp="2026-02-28T12:00:00Z",
            git_sha="abc1234",
            branch="feat/test-visualizer",
            agent_session_id=session_id,
            test_results=rows,
            metadata={"source": "unit-test"},
        )

    async def test_ingest_run_is_idempotent_for_duplicate_run_results(self) -> None:
        row = {
            "path": "tests/test_api.py",
            "name": "test_health",
            "framework": "pytest",
            "status": "passed",
            "duration_ms": 10,
        }
        first = await ingest_run(self._payload("run-1", [row]), self.db)
        second = await ingest_run(self._payload("run-1", [row]), self.db)

        self.assertEqual(first.status, "created")
        self.assertEqual(first.test_results_inserted, 1)
        self.assertEqual(first.test_results_skipped, 0)
        self.assertEqual(first.test_definitions_upserted, 1)

        self.assertEqual(second.status, "skipped")
        self.assertEqual(second.test_results_inserted, 0)
        self.assertEqual(second.test_results_skipped, 1)

        async with self.db.execute("SELECT COUNT(*) FROM test_results WHERE run_id = ?", ("run-1",)) as cur:
            row_count = await cur.fetchone()
        self.assertEqual(row_count[0], 1)

    async def test_ingest_run_partial_reingest_inserts_only_missing_rows(self) -> None:
        existing = {
            "path": "tests/test_auth.py",
            "name": "test_login",
            "framework": "pytest",
            "status": "passed",
        }
        missing = {
            "path": "tests/test_auth.py",
            "name": "test_logout",
            "framework": "pytest",
            "status": "failed",
            "error_message": "assert False",
        }

        await ingest_run(self._payload("run-2", [existing]), self.db)
        updated = await ingest_run(self._payload("run-2", [existing, missing]), self.db)

        self.assertEqual(updated.status, "updated")
        self.assertEqual(updated.test_results_inserted, 1)
        self.assertEqual(updated.test_results_skipped, 1)

        async with self.db.execute("SELECT COUNT(*) FROM test_results WHERE run_id = ?", ("run-2",)) as cur:
            row_count = await cur.fetchone()
        self.assertEqual(row_count[0], 2)

    async def test_ingest_run_accepts_unknown_agent_session_with_warning(self) -> None:
        row = {
            "path": "tests/test_ping.py",
            "name": "test_ping",
            "framework": "pytest",
            "status": "passed",
        }
        response = await ingest_run(self._payload("run-3", [row], session_id="session-missing"), self.db)

        self.assertEqual(response.status, "created")
        self.assertTrue(any("Unknown agent_session_id" in item for item in response.errors))

    async def test_ingest_run_reports_missing_required_fields(self) -> None:
        bad_payload = IngestRunRequest(
            run_id="",
            project_id="project-1",
            timestamp="",
            test_results=[],
        )
        response = await ingest_run(bad_payload, self.db)

        self.assertEqual(response.status, "skipped")
        self.assertTrue(response.errors)


if __name__ == "__main__":
    unittest.main()
