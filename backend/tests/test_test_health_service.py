import unittest

import aiosqlite

from backend import config
from backend.db.repositories.features import SqliteFeatureRepository
from backend.db.repositories.sessions import SqliteSessionRepository
from backend.db.sqlite_migrations import run_migrations
from backend.services.test_health import TestHealthService


class TestHealthServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._prev_flag = config.CCDASH_TEST_VISUALIZER_ENABLED
        config.CCDASH_TEST_VISUALIZER_ENABLED = True

        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        await self._seed()

    async def asyncTearDown(self) -> None:
        await self.db.close()
        config.CCDASH_TEST_VISUALIZER_ENABLED = self._prev_flag

    async def _seed(self) -> None:
        await self.db.execute(
            """
            INSERT INTO test_domains (domain_id, project_id, name, tier)
            VALUES ('dom-1', 'project-1', 'Core', 'core')
            """
        )
        await self.db.execute(
            """
            INSERT INTO test_definitions (test_id, project_id, path, name, framework)
            VALUES ('test-1', 'project-1', 'tests/test_core.py', 'test_core', 'pytest')
            """
        )
        await self.db.execute(
            """
            INSERT INTO test_runs (
                run_id, project_id, timestamp, git_sha, branch, agent_session_id,
                status, total_tests, passed_tests, failed_tests, skipped_tests, duration_ms
            ) VALUES
                ('run-1', 'project-1', '2026-02-28T10:00:00Z', 'sha-1', 'main', 'session-1', 'complete', 1, 1, 0, 0, 11),
                ('run-2', 'project-1', '2026-02-28T11:00:00Z', 'sha-1', 'main', 'session-1', 'failed', 1, 0, 1, 0, 12)
            """
        )
        await self.db.execute(
            """
            INSERT INTO test_results (run_id, test_id, status, duration_ms)
            VALUES ('run-1', 'test-1', 'passed', 11), ('run-2', 'test-1', 'failed', 12)
            """
        )
        await self.db.execute(
            """
            INSERT INTO test_feature_mappings (
                project_id, test_id, feature_id, domain_id, provider_source, confidence, version, is_primary
            ) VALUES ('project-1', 'test-1', 'feature-1', 'dom-1', 'repo_heuristics', 0.9, 1, 1)
            """
        )
        await self.db.execute(
            """
            INSERT INTO test_integrity_signals (
                signal_id, project_id, git_sha, file_path, test_id, signal_type,
                severity, linked_run_ids_json, agent_session_id, created_at
            ) VALUES
                (
                    'sig-1', 'project-1', 'sha-1', 'tests/test_core.py', 'test-1',
                    'assertion_removed', 'high', '["run-2"]', 'session-1', '2026-02-28T11:00:00Z'
                )
            """
        )

        feature_repo = SqliteFeatureRepository(self.db)
        await feature_repo.upsert(
            {
                "id": "feature-1",
                "name": "Feature One",
                "status": "in-progress",
            },
            project_id="project-1",
        )

        session_repo = SqliteSessionRepository(self.db)
        await session_repo.upsert(
            {
                "id": "session-1",
                "status": "completed",
                "startedAt": "2026-02-28T09:00:00Z",
                "endedAt": "2026-02-28T12:00:00Z",
                "sourceFile": "fixtures/session-1.jsonl",
            },
            project_id="project-1",
        )

        await self.db.execute(
            """
            INSERT INTO commit_correlations (
                project_id, session_id, root_session_id, commit_hash, feature_id,
                window_start, window_end, source_key, payload_json
            ) VALUES (
                'project-1', 'session-1', 'session-1', 'sha-1', 'feature-1',
                '2026-02-28T09:00:00Z', '2026-02-28T12:00:00Z', 'corr-1', '{}'
            )
            """
        )
        await self.db.commit()

    async def test_domain_rollups_and_feature_health(self) -> None:
        service = TestHealthService(self.db)

        rollups = await service.get_domain_rollups("project-1")
        self.assertEqual(len(rollups), 1)
        self.assertEqual(rollups[0].domain_id, "dom-1")
        self.assertEqual(rollups[0].failed, 1)
        self.assertLess(rollups[0].integrity_score, 1.0)

        features, total = await service.list_feature_health("project-1", limit=50)
        self.assertEqual(total, 1)
        self.assertEqual(features[0].feature_id, "feature-1")
        self.assertEqual(features[0].failed, 1)

    async def test_feature_timeline_and_correlation(self) -> None:
        service = TestHealthService(self.db)

        timeline = await service.get_feature_timeline(
            project_id="project-1",
            feature_id="feature-1",
            since="2026-02-01T00:00:00Z",
            until=None,
            include_signals=True,
        )
        self.assertEqual(timeline.feature_id, "feature-1")
        self.assertEqual(len(timeline.timeline), 1)
        self.assertTrue(timeline.last_red)

        correlation = await service.get_correlation(run_id="run-2", project_id="project-1")
        self.assertIsNotNone(correlation)
        assert correlation is not None
        self.assertEqual(correlation.run.run_id, "run-2")
        self.assertEqual(len(correlation.features), 1)
        self.assertEqual(len(correlation.integrity_signals), 1)


if __name__ == "__main__":
    unittest.main()
