import time
import unittest

import aiosqlite

from backend import config
from backend.db.factory import (
    get_test_integrity_repository,
    get_test_result_repository,
    get_test_run_repository,
)
from backend.db.sqlite_migrations import run_migrations
from backend.models import IngestRunRequest
from backend.services.test_health import TestHealthService
from backend.services.test_ingest import ingest_run


class TestTestVisualizerPerformance(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._prev_enabled = config.CCDASH_TEST_VISUALIZER_ENABLED
        config.CCDASH_TEST_VISUALIZER_ENABLED = True
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()
        config.CCDASH_TEST_VISUALIZER_ENABLED = self._prev_enabled

    async def _seed_large_suite_run(
        self,
        *,
        run_id: str = "run-perf-7000",
        project_id: str = "project-perf",
        test_count: int = 7000,
    ) -> None:
        await self.db.execute(
            """
            INSERT INTO test_runs (
                run_id, project_id, timestamp, git_sha, branch, agent_session_id,
                status, total_tests, passed_tests, failed_tests, skipped_tests, duration_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                project_id,
                "2026-03-01T18:00:00Z",
                "sha-large-suite",
                "main",
                "session-large-suite",
                "failed",
                test_count,
                int(test_count * 0.84),
                int(test_count * 0.16),
                0,
                120000,
            ),
        )
        await self.db.execute(
            """
            INSERT INTO test_domains (domain_id, project_id, name, parent_id, tier)
            VALUES ('domain-perf', ?, 'Performance Domain', NULL, 'core')
            """,
            (project_id,),
        )

        definition_rows = []
        result_rows = []
        mapping_rows = []
        for index in range(test_count):
            test_id = f"perf-case-{index:04d}"
            definition_rows.append(
                (
                    test_id,
                    project_id,
                    f"tests/perf/test_case_{index:04d}.py",
                    f"test_case_{index:04d}",
                    "pytest",
                )
            )
            result_rows.append(
                (
                    run_id,
                    test_id,
                    "failed" if index % 6 == 0 else "passed",
                    5 + (index % 50),
                )
            )
            mapping_rows.append(
                (
                    project_id,
                    test_id,
                    "feature-perf",
                    "domain-perf",
                    "repo_heuristics",
                    0.95,
                    1,
                    1,
                )
            )

        await self.db.executemany(
            """
            INSERT INTO test_definitions (test_id, project_id, path, name, framework)
            VALUES (?, ?, ?, ?, ?)
            """,
            definition_rows,
        )
        await self.db.executemany(
            """
            INSERT INTO test_results (run_id, test_id, status, duration_ms)
            VALUES (?, ?, ?, ?)
            """,
            result_rows,
        )
        await self.db.executemany(
            """
            INSERT INTO test_feature_mappings (
                project_id, test_id, feature_id, domain_id, provider_source, confidence, version, is_primary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            mapping_rows,
        )
        await self.db.commit()

    async def test_ingest_100_tests_under_500ms(self) -> None:
        rows = []
        for index in range(100):
            rows.append(
                {
                    "path": f"tests/perf/test_case_{index}.py",
                    "name": f"test_case_{index}",
                    "framework": "pytest",
                    "status": "passed" if index % 5 else "failed",
                    "duration_ms": 4,
                }
            )

        payload = IngestRunRequest(
            run_id="run-perf-100",
            project_id="project-perf",
            timestamp="2026-03-01T14:00:00Z",
            git_sha="sha-perf-100",
            test_results=rows,
            metadata={"kind": "perf"},
        )
        start = time.perf_counter()
        response = await ingest_run(payload, self.db)
        elapsed_ms = (time.perf_counter() - start) * 1000

        self.assertEqual(response.status, "created")
        self.assertEqual(response.test_results_inserted, 100)
        self.assertLess(
            elapsed_ms,
            500,
            f"ingest_run(100 tests) took {elapsed_ms:.1f}ms; expected < 500ms",
        )

    async def test_domain_health_100_domains_under_500ms(self) -> None:
        await self.db.execute(
            """
            INSERT INTO test_runs (
                run_id, project_id, timestamp, git_sha, status, total_tests, passed_tests, failed_tests, skipped_tests
            ) VALUES ('run-health-perf', 'project-perf', '2026-03-01T15:00:00Z', 'sha-health', 'complete', 1000, 800, 200, 0)
            """
        )

        domain_rows = []
        for index in range(100):
            domain_rows.append(
                (
                    f"dom-{index}",
                    "project-perf",
                    f"Domain {index}",
                    None,
                    "core",
                )
            )
        await self.db.executemany(
            """
            INSERT INTO test_domains (domain_id, project_id, name, parent_id, tier)
            VALUES (?, ?, ?, ?, ?)
            """,
            domain_rows,
        )

        result_rows = []
        mapping_rows = []
        for index in range(1000):
            test_id = f"perf-test-{index}"
            domain_id = f"dom-{index % 100}"
            result_rows.append(
                (
                    "run-health-perf",
                    test_id,
                    "passed" if index % 5 else "failed",
                    5,
                )
            )
            mapping_rows.append(
                (
                    "project-perf",
                    test_id,
                    f"feature-{index % 120}",
                    domain_id,
                    "repo_heuristics",
                    0.9,
                    1,
                    1,
                )
            )

        await self.db.executemany(
            """
            INSERT INTO test_results (run_id, test_id, status, duration_ms)
            VALUES (?, ?, ?, ?)
            """,
            result_rows,
        )
        await self.db.executemany(
            """
            INSERT INTO test_feature_mappings (
                project_id, test_id, feature_id, domain_id, provider_source, confidence, version, is_primary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            mapping_rows,
        )
        await self.db.commit()

        service = TestHealthService(self.db)
        start = time.perf_counter()
        rollups = await service.get_domain_rollups(project_id="project-perf")
        elapsed_ms = (time.perf_counter() - start) * 1000

        self.assertEqual(len(rollups), 100)
        self.assertLess(
            elapsed_ms,
            500,
            f"get_domain_rollups(100 domains, 1000 tests) took {elapsed_ms:.1f}ms; expected < 500ms",
        )

    async def test_run_results_query_7000_suite_under_1500ms(self) -> None:
        await self._seed_large_suite_run()
        result_repo = get_test_result_repository(self.db)

        start = time.perf_counter()
        rows, total = await result_repo.list_by_run_filtered(
            "run-perf-7000",
            statuses=["failed"],
            query="perf-case",
            sort_by="duration",
            sort_order="desc",
            limit=250,
            offset=0,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000

        self.assertGreater(total, 0)
        self.assertEqual(len(rows), 250)
        self.assertLess(
            elapsed_ms,
            1500,
            f"list_by_run_filtered(7000 suite) took {elapsed_ms:.1f}ms; expected < 1500ms",
        )

    async def test_runs_feature_filter_under_1000ms(self) -> None:
        await self._seed_large_suite_run()
        run_repo = get_test_run_repository(self.db)

        start = time.perf_counter()
        rows, total = await run_repo.list_filtered(
            "project-perf",
            feature_id="feature-perf",
            limit=20,
            offset=0,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000

        self.assertGreaterEqual(total, 1)
        self.assertGreaterEqual(len(rows), 1)
        self.assertEqual(rows[0]["run_id"], "run-perf-7000")
        self.assertLess(
            elapsed_ms,
            1000,
            f"list_filtered(feature_id) took {elapsed_ms:.1f}ms; expected < 1000ms",
        )

    async def test_history_query_under_800ms(self) -> None:
        await self.db.execute(
            """
            INSERT INTO test_definitions (test_id, project_id, path, name, framework)
            VALUES ('history-test', 'project-perf', 'tests/perf/test_history.py', 'test_history', 'pytest')
            """
        )
        run_rows = []
        result_rows = []
        for index in range(500):
            run_id = f"run-history-{index:04d}"
            timestamp = f"2026-03-01T{(index % 24):02d}:{(index % 60):02d}:00Z"
            run_rows.append(
                (
                    run_id,
                    "project-perf",
                    timestamp,
                    f"sha-history-{index:04d}",
                    "main",
                    "session-history",
                    "complete",
                    1,
                    1 if index % 5 else 0,
                    0 if index % 5 else 1,
                    0,
                    10,
                )
            )
            result_rows.append(
                (
                    run_id,
                    "history-test",
                    "passed" if index % 5 else "failed",
                    10 + (index % 5),
                )
            )
        await self.db.executemany(
            """
            INSERT INTO test_runs (
                run_id, project_id, timestamp, git_sha, branch, agent_session_id,
                status, total_tests, passed_tests, failed_tests, skipped_tests, duration_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            run_rows,
        )
        await self.db.executemany(
            """
            INSERT INTO test_results (run_id, test_id, status, duration_ms)
            VALUES (?, ?, ?, ?)
            """,
            result_rows,
        )
        await self.db.commit()

        result_repo = get_test_result_repository(self.db)
        start = time.perf_counter()
        rows, total = await result_repo.list_history_for_test(
            project_id="project-perf",
            test_id="history-test",
            since="2026-03-01T00:00:00Z",
            limit=150,
            offset=0,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000

        self.assertEqual(total, 500)
        self.assertEqual(len(rows), 150)
        self.assertLess(
            elapsed_ms,
            800,
            f"list_history_for_test(500 runs) took {elapsed_ms:.1f}ms; expected < 800ms",
        )

    async def test_integrity_alert_filter_query_under_800ms(self) -> None:
        rows = []
        for index in range(5000):
            rows.append(
                (
                    f"sig-perf-{index:05d}",
                    "project-perf",
                    f"sha-integrity-{index % 31}",
                    f"tests/perf/test_file_{index % 70}.py",
                    None,
                    "assertion_removed" if index % 3 == 0 else "skip_introduced",
                    "high" if index % 4 == 0 else "medium",
                    "{}",
                    "[]",
                    "session-hot" if index % 5 == 0 else "session-cold",
                    f"2026-03-01T{(index % 24):02d}:{(index % 60):02d}:00Z",
                )
            )
        await self.db.executemany(
            """
            INSERT INTO test_integrity_signals (
                signal_id, project_id, git_sha, file_path, test_id, signal_type,
                severity, details_json, linked_run_ids_json, agent_session_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        await self.db.commit()

        integrity_repo = get_test_integrity_repository(self.db)
        start = time.perf_counter()
        filtered_rows, total = await integrity_repo.list_filtered(
            project_id="project-perf",
            signal_type="assertion_removed",
            severity="high",
            agent_session_id="session-hot",
            limit=200,
            offset=0,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000

        self.assertGreater(total, 0)
        self.assertGreater(len(filtered_rows), 0)
        self.assertLess(
            elapsed_ms,
            800,
            f"list_filtered(integrity alerts) took {elapsed_ms:.1f}ms; expected < 800ms",
        )


if __name__ == "__main__":
    unittest.main()
