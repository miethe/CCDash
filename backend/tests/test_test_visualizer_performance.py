import time
import unittest

import aiosqlite

from backend import config
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


if __name__ == "__main__":
    unittest.main()
