import unittest

import aiosqlite

from backend import config
from backend.db.repositories.analytics import SqliteAnalyticsRepository
from backend.db.repositories.entity_graph import SqliteEntityLinkRepository
from backend.db.repositories.features import SqliteFeatureRepository
from backend.db.repositories.sessions import SqliteSessionRepository
from backend.db.repositories.test_definitions import SqliteTestDefinitionRepository
from backend.db.repositories.test_domains import SqliteTestDomainRepository
from backend.db.repositories.test_runs import SqliteTestRunRepository
from backend.db.sqlite_migrations import _ensure_test_visualizer_tables, run_migrations


class Phase3RepositoryMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._prev_test_visualizer_enabled = config.CCDASH_TEST_VISUALIZER_ENABLED
        config.CCDASH_TEST_VISUALIZER_ENABLED = True
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        await _ensure_test_visualizer_tables(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()
        config.CCDASH_TEST_VISUALIZER_ENABLED = self._prev_test_visualizer_enabled

    async def test_analytics_repository_records_execution_event_and_reports_stats(self) -> None:
        analytics_repo = SqliteAnalyticsRepository(self.db)
        feature_repo = SqliteFeatureRepository(self.db)
        session_repo = SqliteSessionRepository(self.db)
        link_repo = SqliteEntityLinkRepository(self.db)

        await feature_repo.upsert(
            {"id": "feature-1", "name": "Feature One", "status": "in-progress"},
            project_id="project-1",
        )
        await session_repo.upsert(
            {"id": "session-1", "rootSessionId": "root-1", "sourceFile": "fixtures/session-1.jsonl"},
            project_id="project-1",
        )
        await session_repo.upsert(
            {"id": "session-2", "rootSessionId": "root-1", "sourceFile": "fixtures/session-2.jsonl"},
            project_id="project-1",
        )
        await link_repo.upsert(
            {
                "source_type": "feature",
                "source_id": "feature-1",
                "target_type": "session",
                "target_id": "session-1",
                "link_type": "related",
                "confidence": 0.55,
            }
        )

        await analytics_repo.record_execution_event(
            project_id="project-1",
            event_type="execution_command_copied",
            feature_id="feature-1",
            occurred_at="2026-03-01T10:00:00Z",
            source_key="ui-execution:event-1",
            payload_json='{"command":"pytest"}',
        )
        await self.db.execute(
            """
            INSERT INTO telemetry_events (
                project_id, session_id, root_session_id, feature_id, task_id, commit_hash,
                pr_number, phase, event_type, tool_name, model, agent, skill, status,
                duration_ms, token_input, token_output, cost_usd, occurred_at, sequence_no,
                source, source_key, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "project-1",
                "session-1",
                "root-1",
                "feature-1",
                "",
                "",
                "",
                "phase-1",
                "tool.aggregate",
                "pytest",
                "gpt-5",
                "worker",
                "skill-a",
                "ok",
                55,
                0,
                0,
                0.0,
                "2026-03-01T10:01:00Z",
                1,
                "worker",
                "event-2",
                '{"callCount": 3}',
            ),
        )
        await self.db.execute(
            """
            INSERT INTO telemetry_events (
                project_id, session_id, root_session_id, feature_id, task_id, commit_hash,
                pr_number, phase, event_type, tool_name, model, agent, skill, status,
                duration_ms, token_input, token_output, cost_usd, occurred_at, sequence_no,
                source, source_key, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "project-1",
                "session-1",
                "root-1",
                "feature-1",
                "",
                "",
                "",
                "phase-1",
                "session.lifecycle",
                "",
                "gpt-5",
                "worker",
                "skill-a",
                "ok",
                0,
                11,
                7,
                0.25,
                "2026-03-01T10:02:00Z",
                2,
                "worker",
                "event-3",
                "{}",
            ),
        )
        await self.db.commit()

        rows = await analytics_repo.list_artifact_analytics_rows(project_id="project-1")
        self.assertEqual(rows["artifact_rows"], [])
        self.assertEqual(rows["feature_rows"][0]["id"], "feature-1")

        async with self.db.execute(
            "SELECT event_type, feature_id, source_key FROM telemetry_events WHERE source_key = ?",
            ("ui-execution:event-1",),
        ) as cur:
            saved = await cur.fetchone()
        self.assertEqual(saved["event_type"], "execution_command_copied")
        self.assertEqual(saved["feature_id"], "feature-1")

        stats = await analytics_repo.get_prometheus_link_and_thread_stats("project-1")
        self.assertEqual(stats["link_stats"]["total_links"], 1)
        self.assertEqual(stats["link_stats"]["low_confidence"], 1)
        self.assertEqual(stats["thread_stats"]["max_fanout"], 2)

        telemetry = await analytics_repo.get_prometheus_telemetry_rows("project-1")
        self.assertEqual(telemetry["tool_rows"][0]["tool_name"], "pytest")
        self.assertEqual(int(telemetry["tool_rows"][0]["calls"]), 3)
        self.assertEqual(telemetry["model_rows"][0]["model"], "gpt-5")
        self.assertEqual(int(telemetry["event_rows"][0]["event_count"]), 1)

    async def test_test_definition_repository_get_many_by_ids_returns_map(self) -> None:
        repo = SqliteTestDefinitionRepository(self.db)
        await repo.upsert(
            {
                "test_id": "test-1",
                "project_id": "project-1",
                "path": "tests/test_core.py",
                "name": "test_core",
            }
        )
        await repo.upsert(
            {
                "test_id": "test-2",
                "project_id": "project-1",
                "path": "tests/test_edge.py",
                "name": "test_edge",
            }
        )

        rows = await repo.get_many_by_ids("project-1", ["test-2", "test-1", "", "test-1"])
        self.assertEqual(sorted(rows.keys()), ["test-1", "test-2"])
        self.assertEqual(rows["test-2"]["name"], "test_edge")

    async def test_test_domain_repository_prunes_only_unmapped_leaf_domains(self) -> None:
        repo = SqliteTestDomainRepository(self.db)
        definition_repo = SqliteTestDefinitionRepository(self.db)
        await repo.upsert({"domain_id": "dom-root", "project_id": "project-1", "name": "Root"})
        await repo.upsert(
            {"domain_id": "dom-child", "project_id": "project-1", "name": "Child", "parent_id": "dom-root"}
        )
        await repo.upsert({"domain_id": "dom-orphan", "project_id": "project-1", "name": "Orphan"})
        await definition_repo.upsert(
            {
                "test_id": "test-1",
                "project_id": "project-1",
                "path": "tests/test_core.py",
                "name": "test_core",
            }
        )
        await self.db.execute(
            """
            INSERT INTO test_feature_mappings (
                project_id, test_id, feature_id, domain_id, provider_source, confidence, version, is_primary
            ) VALUES ('project-1', 'test-1', 'feature-1', 'dom-child', 'repo_heuristics', 0.9, 1, 1)
            """
        )
        await self.db.commit()

        deleted = await repo.prune_unmapped_leaf_domains("project-1")
        self.assertEqual(deleted, 1)

        remaining = await repo.list_paginated(offset=0, limit=10, project_id="project-1")
        self.assertEqual(sorted(row["domain_id"] for row in remaining), ["dom-child", "dom-root"])

    async def test_test_run_repository_get_latest_commit_correlation_parses_payload(self) -> None:
        repo = SqliteTestRunRepository(self.db)
        await self.db.execute(
            """
            INSERT INTO commit_correlations (
                project_id, session_id, root_session_id, commit_hash, feature_id,
                window_start, window_end, source_key, payload_json
            ) VALUES
                ('project-1', 'session-1', 'session-1', 'sha-1', 'feature-1',
                 '2026-03-01T09:00:00Z', '2026-03-01T10:00:00Z', 'corr-1', '{"score": 1}'),
                ('project-1', 'session-2', 'session-2', 'sha-1', 'feature-2',
                 '2026-03-01T10:00:00Z', '2026-03-01T11:00:00Z', 'corr-2', '{"score": 2}')
            """
        )
        await self.db.commit()

        row = await repo.get_latest_commit_correlation("project-1", "sha-1")
        assert row is not None
        self.assertEqual(row["source_key"], "corr-2")
        self.assertEqual(row["payload_json"]["score"], 2)

    async def test_test_run_repository_get_metric_summary_aggregates_test_metrics(self) -> None:
        repo = SqliteTestRunRepository(self.db)
        await self.db.execute(
            """
            INSERT INTO test_metrics (project_id, platform, metric_type, metric_name, metric_value, unit, collected_at)
            VALUES
                ('project-1', 'pytest', 'coverage', 'line', 88.0, 'pct', '2026-03-01T10:00:00Z'),
                ('project-1', 'pytest', 'coverage', 'branch', 77.0, 'pct', '2026-03-01T10:01:00Z'),
                ('project-1', 'playwright', 'duration', 'suite', 123.0, 'ms', '2026-03-01T10:02:00Z')
            """
        )
        await self.db.commit()

        summary = await repo.get_metric_summary("project-1")
        self.assertEqual(summary["total_metrics"], 3)
        self.assertEqual(summary["latest_collected_at"], "2026-03-01T10:02:00Z")
        self.assertEqual(summary["by_platform"], {"playwright": 1, "pytest": 2})
        self.assertEqual(summary["by_metric_type"], {"coverage": 2, "duration": 1})


if __name__ == "__main__":
    unittest.main()
