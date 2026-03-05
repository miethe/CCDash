import unittest
from unittest.mock import AsyncMock, patch

import aiosqlite

from backend import config
from backend.db.repositories.test_integrity import SqliteTestIntegrityRepository
from backend.db.repositories.test_results import SqliteTestResultRepository
from backend.db.repositories.test_runs import SqliteTestRunRepository
from backend.db.sqlite_migrations import run_migrations
from backend.services.integrity_detector import IntegrityDetector


class TestIntegrityDetector(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._prev_enabled = config.CCDASH_TEST_VISUALIZER_ENABLED
        self._prev_root = config.CCDASH_PROJECT_ROOT
        config.CCDASH_TEST_VISUALIZER_ENABLED = True
        config.CCDASH_PROJECT_ROOT = "."

        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)

        self.run_repo = SqliteTestRunRepository(self.db)
        self.result_repo = SqliteTestResultRepository(self.db)
        self.integrity_repo = SqliteTestIntegrityRepository(self.db)
        await self._seed_history()

    async def asyncTearDown(self) -> None:
        await self.db.close()
        config.CCDASH_TEST_VISUALIZER_ENABLED = self._prev_enabled
        config.CCDASH_PROJECT_ROOT = self._prev_root

    async def _seed_history(self) -> None:
        await self.db.execute(
            """
            INSERT INTO test_definitions (test_id, project_id, path, name, framework)
            VALUES ('test-auth-login', 'project-1', 'tests/auth/test_login.py', 'test_login', 'pytest')
            """
        )
        await self.run_repo.upsert(
            {
                "run_id": "run-old",
                "project_id": "project-1",
                "timestamp": "2026-03-01T11:00:00Z",
                "git_sha": "sha-old",
                "agent_session_id": "session-1",
            }
        )
        await self.result_repo.upsert(
            {
                "run_id": "run-old",
                "test_id": "test-auth-login",
                "status": "failed",
            }
        )
        await self.run_repo.upsert(
            {
                "run_id": "run-new",
                "project_id": "project-1",
                "timestamp": "2026-03-01T12:00:00Z",
                "git_sha": "sha-new",
                "agent_session_id": "session-1",
            }
        )
        await self.result_repo.upsert(
            {
                "run_id": "run-new",
                "test_id": "test-auth-login",
                "status": "passed",
            }
        )

    async def test_returns_empty_when_git_unavailable(self) -> None:
        detector = IntegrityDetector(self.db, git_repo_path="")
        with patch.object(detector, "_git_available", return_value=False):
            rows = await detector.check_run(run_id="run-new", git_sha="sha-new", project_id="project-1")
        self.assertEqual(rows, [])

    async def test_detects_all_signal_types_and_persists(self) -> None:
        detector = IntegrityDetector(self.db, git_repo_path=".")
        diff = "\n".join(
            [
                "diff --git a/tests/auth/test_login.py b/tests/auth/test_login.py",
                "--- a/tests/auth/test_login.py",
                "+++ b/tests/auth/test_login.py",
                "@@ -1,5 +1,9 @@",
                " def test_login():",
                "-    assert response.status_code == 200",
                "+    pytest.skip('temporarily disabled')",
                "+    pytest.xfail('known issue')",
                "+    try:",
                "+        execute_login()",
                "+    except Exception:",
                "+        pass",
            ]
        )

        with patch.object(detector, "_git_available", return_value=True), patch.object(
            detector,
            "_get_git_diff",
            new=AsyncMock(return_value=diff),
        ):
            rows = await detector.check_run(run_id="run-new", git_sha="sha-new", project_id="project-1")

        signal_types = sorted({row.signal_type for row in rows})
        self.assertEqual(
            signal_types,
            [
                "assertion_removed",
                "broad_exception",
                "edited_before_green",
                "skip_introduced",
                "xfail_added",
            ],
        )

        stored = await self.integrity_repo.list_by_project("project-1", limit=50, offset=0)
        self.assertGreaterEqual(len(stored), 5)

    async def test_ignores_non_test_file_diff(self) -> None:
        detector = IntegrityDetector(self.db, git_repo_path=".")
        diff = "\n".join(
            [
                "diff --git a/docs/readme.md b/docs/readme.md",
                "--- a/docs/readme.md",
                "+++ b/docs/readme.md",
                "@@ -1 +1 @@",
                "-old",
                "+new",
            ]
        )
        with patch.object(detector, "_git_available", return_value=True), patch.object(
            detector,
            "_get_git_diff",
            new=AsyncMock(return_value=diff),
        ):
            rows = await detector.check_run(run_id="run-new", git_sha="sha-new", project_id="project-1")
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
