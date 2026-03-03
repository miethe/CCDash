import types
import unittest
from unittest.mock import AsyncMock, patch

import aiosqlite

from fastapi import BackgroundTasks, HTTPException

from backend import config
from backend.db.repositories.features import SqliteFeatureRepository
from backend.db.repositories.sessions import SqliteSessionRepository
from backend.db.sqlite_migrations import run_migrations
from backend.models import IngestRunResponse
from backend.routers import test_visualizer as router


class TestVisualizerRouterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._prev_enabled = router.config.CCDASH_TEST_VISUALIZER_ENABLED
        self._prev_integrity = router.config.CCDASH_INTEGRITY_SIGNALS_ENABLED
        self._prev_semantic = router.config.CCDASH_SEMANTIC_MAPPING_ENABLED
        self._prev_enabled_cfg = config.CCDASH_TEST_VISUALIZER_ENABLED

        router.config.CCDASH_TEST_VISUALIZER_ENABLED = True
        router.config.CCDASH_INTEGRITY_SIGNALS_ENABLED = True
        router.config.CCDASH_SEMANTIC_MAPPING_ENABLED = True
        config.CCDASH_TEST_VISUALIZER_ENABLED = True

        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)

        await self._seed_fixtures()

    async def asyncTearDown(self) -> None:
        await self.db.close()
        router.config.CCDASH_TEST_VISUALIZER_ENABLED = self._prev_enabled
        router.config.CCDASH_INTEGRITY_SIGNALS_ENABLED = self._prev_integrity
        router.config.CCDASH_SEMANTIC_MAPPING_ENABLED = self._prev_semantic
        config.CCDASH_TEST_VISUALIZER_ENABLED = self._prev_enabled_cfg

    async def _seed_fixtures(self) -> None:
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
            VALUES
                ('run-1', 'test-1', 'passed', 11),
                ('run-2', 'test-1', 'failed', 12)
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

    def _json_request(self, payload: dict) -> types.SimpleNamespace:
        async def _json() -> dict:
            return payload

        async def _form() -> dict:
            return {}

        return types.SimpleNamespace(
            headers={"content-type": "application/json"},
            json=_json,
            form=_form,
        )

    def _request_with_sync_engine(self, sync_engine: object) -> types.SimpleNamespace:
        return types.SimpleNamespace(
            app=types.SimpleNamespace(
                state=types.SimpleNamespace(sync_engine=sync_engine)
            )
        )

    async def test_ingest_returns_503_when_feature_flag_disabled(self) -> None:
        router.config.CCDASH_TEST_VISUALIZER_ENABLED = False
        request = self._json_request({})

        with self.assertRaises(HTTPException) as ctx:
            await router.ingest_test_run(request)

        self.assertEqual(ctx.exception.status_code, 503)

    async def test_ingest_returns_400_for_invalid_json_payload(self) -> None:
        router.config.CCDASH_TEST_VISUALIZER_ENABLED = True
        request = self._json_request({"project_id": "project-1"})

        with self.assertRaises(HTTPException) as ctx:
            await router.ingest_test_run(request)

        self.assertEqual(ctx.exception.status_code, 400)

    async def test_ingest_json_calls_service_and_sets_mapping_queue_flag(self) -> None:
        router.config.CCDASH_TEST_VISUALIZER_ENABLED = True
        router.config.CCDASH_INTEGRITY_SIGNALS_ENABLED = False
        request = self._json_request(
            {
                "run_id": "run-1",
                "project_id": "project-1",
                "timestamp": "2026-02-28T13:00:00Z",
                "test_results": [],
            }
        )
        fake_response = IngestRunResponse(
            run_id="run-1",
            status="created",
            test_definitions_upserted=0,
            test_results_inserted=0,
            test_results_skipped=0,
            mapping_trigger_queued=False,
            integrity_check_queued=False,
            errors=[],
        )
        created_coroutines = []

        def _fake_create_task(coro):
            created_coroutines.append(coro)
            coro.close()
            return object()

        with patch.object(router.connection, "get_connection", new=AsyncMock(return_value=object())), patch.object(router, "ingest_run", new=AsyncMock(return_value=fake_response)), patch.object(router.asyncio, "create_task", side_effect=_fake_create_task) as create_task:
            payload = await router.ingest_test_run(request)

        self.assertEqual(payload.run_id, "run-1")
        self.assertTrue(payload.mapping_trigger_queued)
        self.assertFalse(payload.integrity_check_queued)
        self.assertEqual(create_task.call_count, 1)
        self.assertEqual(len(created_coroutines), 1)

    async def test_get_domain_health_and_feature_health(self) -> None:
        with patch.object(router.connection, "get_connection", new=AsyncMock(return_value=self.db)):
            domains = await router.get_domain_health(types.SimpleNamespace(), project_id="project-1")
            features = await router.get_feature_health(
                types.SimpleNamespace(),
                project_id="project-1",
                limit=10,
                cursor=None,
            )

        self.assertEqual(len(domains), 1)
        self.assertEqual(domains[0].domain_id, "dom-1")
        self.assertEqual(domains[0].failed, 1)
        self.assertEqual(features.total, 1)
        self.assertEqual(len(features.items), 1)
        self.assertEqual(features.items[0].feature_id, "feature-1")

    async def test_run_detail_runs_history_timeline_and_integrity_endpoints(self) -> None:
        with patch.object(router.connection, "get_connection", new=AsyncMock(return_value=self.db)):
            run_detail = await router.get_run_detail(types.SimpleNamespace(), run_id="run-2")
            run_detail_light = await router.get_run_detail(
                types.SimpleNamespace(),
                run_id="run-2",
                include_results=False,
            )
            run_results = await router.list_run_results(
                types.SimpleNamespace(),
                run_id="run-2",
                project_id="project-1",
                limit=10,
                statuses="failed",
                query="core",
            )
            runs = await router.list_runs(types.SimpleNamespace(), project_id="project-1", limit=1)
            history = await router.get_test_history(
                types.SimpleNamespace(),
                test_id="test-1",
                project_id="project-1",
                limit=10,
            )
            timeline = await router.get_feature_timeline(
                types.SimpleNamespace(),
                feature_id="feature-1",
                project_id="project-1",
            )
            alerts = await router.list_integrity_alerts(
                types.SimpleNamespace(),
                project_id="project-1",
                limit=10,
            )

        self.assertEqual(run_detail.run.run_id, "run-2")
        self.assertEqual(len(run_detail.results), 1)
        self.assertEqual(len(run_detail_light.results), 0)
        self.assertEqual(len(run_detail_light.definitions), 0)
        self.assertEqual(run_results.total, 1)
        self.assertEqual(len(run_results.items), 1)
        self.assertIn("test-1", run_results.definitions)
        self.assertEqual(runs.total, 2)
        self.assertEqual(len(runs.items), 1)
        self.assertIsNotNone(runs.next_cursor)
        self.assertEqual(history.total, 2)
        self.assertEqual(len(timeline.timeline), 1)
        self.assertEqual(alerts.total, 1)

    async def test_domain_filters_apply_to_runs_and_run_results(self) -> None:
        await self.db.execute(
            """
            INSERT INTO test_domains (domain_id, project_id, name, tier)
            VALUES ('dom-2', 'project-1', 'UX', 'support')
            """
        )
        await self.db.execute(
            """
            INSERT INTO test_definitions (test_id, project_id, path, name, framework)
            VALUES ('test-2', 'project-1', 'tests/test_ui.py', 'test_ui', 'pytest')
            """
        )
        await self.db.execute(
            """
            INSERT INTO test_runs (
                run_id, project_id, timestamp, git_sha, branch, agent_session_id,
                status, total_tests, passed_tests, failed_tests, skipped_tests, duration_ms
            ) VALUES
                ('run-3', 'project-1', '2026-02-28T12:00:00Z', 'sha-2', 'main', 'session-2', 'complete', 1, 1, 0, 0, 15)
            """
        )
        await self.db.execute(
            """
            INSERT INTO test_results (run_id, test_id, status, duration_ms)
            VALUES ('run-3', 'test-2', 'passed', 15)
            """
        )
        await self.db.execute(
            """
            INSERT INTO test_feature_mappings (
                project_id, test_id, feature_id, domain_id, provider_source, confidence, version, is_primary
            ) VALUES ('project-1', 'test-2', 'feature-2', 'dom-2', 'repo_heuristics', 0.85, 1, 1)
            """
        )
        await self.db.commit()

        with patch.object(router.connection, "get_connection", new=AsyncMock(return_value=self.db)):
            dom1_runs = await router.list_runs(
                types.SimpleNamespace(),
                project_id="project-1",
                domain_id="dom-1",
                limit=10,
            )
            dom2_runs = await router.list_runs(
                types.SimpleNamespace(),
                project_id="project-1",
                domain_id="dom-2",
                limit=10,
            )
            dom1_results = await router.list_run_results(
                types.SimpleNamespace(),
                run_id="run-2",
                project_id="project-1",
                domain_id="dom-1",
                limit=10,
            )
            dom2_results = await router.list_run_results(
                types.SimpleNamespace(),
                run_id="run-2",
                project_id="project-1",
                domain_id="dom-2",
                limit=10,
            )
            run3_dom2_results = await router.list_run_results(
                types.SimpleNamespace(),
                run_id="run-3",
                project_id="project-1",
                domain_id="dom-2",
                limit=10,
            )

        self.assertEqual({item.run_id for item in dom1_runs.items}, {"run-1", "run-2"})
        self.assertEqual({item.run_id for item in dom2_runs.items}, {"run-3"})
        self.assertEqual(dom1_results.total, 1)
        self.assertEqual(len(dom1_results.items), 1)
        self.assertEqual(dom2_results.total, 0)
        self.assertEqual(len(dom2_results.items), 0)
        self.assertEqual(run3_dom2_results.total, 1)
        self.assertEqual(len(run3_dom2_results.items), 1)

    async def test_correlate_endpoint_and_missing_run(self) -> None:
        with patch.object(router.connection, "get_connection", new=AsyncMock(return_value=self.db)):
            correlation = await router.correlate_run(
                types.SimpleNamespace(),
                run_id="run-2",
                project_id="project-1",
            )

            self.assertEqual(correlation.run.run_id, "run-2")
            self.assertEqual(correlation.links["testing_page_url"], "/#/tests?run_id=run-2")
            self.assertEqual(len(correlation.features), 1)

            with self.assertRaises(HTTPException) as ctx:
                await router.correlate_run(
                    types.SimpleNamespace(),
                    run_id="run-missing",
                    project_id="project-1",
                )

        self.assertEqual(ctx.exception.status_code, 404)

    async def test_invalid_cursor_returns_400(self) -> None:
        with patch.object(router.connection, "get_connection", new=AsyncMock(return_value=self.db)):
            with self.assertRaises(HTTPException) as ctx:
                await router.list_runs(
                    types.SimpleNamespace(),
                    project_id="project-1",
                    cursor="not-base64",
                )

        self.assertEqual(ctx.exception.status_code, 400)

    async def test_import_mappings_endpoint(self) -> None:
        request = self._json_request(
            {
                "project_id": "project-1",
                "mapping_file": {
                    "version": "1",
                    "generated_by": "semantic-mapper",
                    "mappings": [
                        {
                            "test_id": "test-1",
                            "feature_id": "feature-1",
                            "domain_id": "dom-1",
                            "confidence": 0.92,
                        }
                    ],
                },
            }
        )
        with patch.object(router.connection, "get_connection", new=AsyncMock(return_value=self.db)):
            payload = await router.import_mappings(request)

        self.assertEqual(payload["project_id"], "project-1")
        self.assertGreaterEqual(payload["stored_count"], 1)

    async def test_backfill_mappings_endpoint(self) -> None:
        await self.db.execute("DELETE FROM test_feature_mappings WHERE project_id = 'project-1'")
        await self.db.execute(
            """
            UPDATE test_definitions
            SET path = 'tests/test_feature_1.py', name = 'test_feature_1'
            WHERE test_id = 'test-1'
            """
        )
        await self.db.commit()

        with patch.object(router.connection, "get_connection", new=AsyncMock(return_value=self.db)):
            payload = await router.backfill_mappings(
                types.SimpleNamespace(),
                body=router.BackfillTestMappingsRequest(project_id="project-1", run_limit=10),
            )

        self.assertEqual(payload.project_id, "project-1")
        self.assertGreaterEqual(payload.runs_processed, 1)
        self.assertGreaterEqual(payload.tests_considered, 1)
        self.assertGreaterEqual(payload.tests_resolved, 1)
        self.assertGreaterEqual(payload.mappings_stored, 1)
        self.assertTrue(payload.resolver_version)

    async def test_backfill_mappings_start_endpoint_queues_background_operation(self) -> None:
        class _FakeSyncEngine:
            def __init__(self) -> None:
                self.started: list[dict] = []
                self.updated: list[dict] = []

            async def start_operation(self, kind, project_id, trigger="api", metadata=None):
                self.started.append(
                    {
                        "kind": kind,
                        "project_id": project_id,
                        "trigger": trigger,
                        "metadata": metadata or {},
                    }
                )
                return "OP-BACKFILL-1"

            async def update_operation(self, operation_id, **kwargs):
                self.updated.append({"operation_id": operation_id, **kwargs})

            async def finish_operation(self, operation_id, **kwargs):
                return None

        engine = _FakeSyncEngine()
        request = self._request_with_sync_engine(engine)
        background = BackgroundTasks()

        payload = await router.start_backfill_mappings(
            request,
            background,
            body=router.BackfillTestMappingsRequest(project_id="project-1", run_limit=10),
        )

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["mode"], "background")
        self.assertEqual(payload["operationId"], "OP-BACKFILL-1")
        self.assertEqual(len(background.tasks), 1)
        self.assertEqual(engine.started[0]["kind"], "test_mapping_backfill")
        self.assertEqual(engine.started[0]["project_id"], "project-1")

    async def test_mapping_resolver_detail_endpoint(self) -> None:
        with patch.object(router.connection, "get_connection", new=AsyncMock(return_value=self.db)):
            payload = await router.mapping_resolver_detail(
                types.SimpleNamespace(),
                project_id="project-1",
                run_limit=5,
            )

        self.assertEqual(payload.project_id, "project-1")
        self.assertGreaterEqual(len(payload.runs), 1)
        first = payload.runs[0]
        self.assertGreaterEqual(first.total_results, 0)
        self.assertGreaterEqual(first.coverage, 0.0)

    async def test_import_mappings_rejects_invalid_payload_and_flag(self) -> None:
        bad_request = self._json_request(
            {
                "project_id": "project-1",
                "mapping_file": {"mappings": [{"test_id": "test-1"}]},
            }
        )
        with patch.object(router.connection, "get_connection", new=AsyncMock(return_value=self.db)):
            with self.assertRaises(HTTPException) as ctx:
                await router.import_mappings(bad_request)
        self.assertEqual(ctx.exception.status_code, 400)

        router.config.CCDASH_SEMANTIC_MAPPING_ENABLED = False
        request = self._json_request({"project_id": "project-1", "mapping_file": {"mappings": []}})
        with self.assertRaises(HTTPException) as disabled_ctx:
            await router.import_mappings(request)
        self.assertEqual(disabled_ctx.exception.status_code, 503)

    async def test_get_endpoints_return_503_when_feature_flag_disabled(self) -> None:
        router.config.CCDASH_TEST_VISUALIZER_ENABLED = False

        with self.assertRaises(HTTPException) as ctx:
            await router.get_domain_health(types.SimpleNamespace(), project_id="project-1")

        self.assertEqual(ctx.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
