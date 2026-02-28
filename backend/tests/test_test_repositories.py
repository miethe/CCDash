import unittest

import aiosqlite

from backend import config
from backend.db.repositories.base import (
    TestDefinitionRepository,
    TestDomainRepository,
    TestIntegrityRepository,
    TestMappingRepository,
    TestResultRepository,
    TestRunRepository,
)
from backend.db.repositories.test_definitions import SqliteTestDefinitionRepository
from backend.db.repositories.test_domains import SqliteTestDomainRepository
from backend.db.repositories.test_integrity import SqliteTestIntegrityRepository
from backend.db.repositories.test_mappings import SqliteTestMappingRepository
from backend.db.repositories.test_results import SqliteTestResultRepository
from backend.db.repositories.test_runs import SqliteTestRunRepository
from backend.db.sqlite_migrations import run_migrations


class TestVisualizerRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._prev_flag = config.CCDASH_TEST_VISUALIZER_ENABLED
        config.CCDASH_TEST_VISUALIZER_ENABLED = True
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)

        self.run_repo = SqliteTestRunRepository(self.db)
        self.definition_repo = SqliteTestDefinitionRepository(self.db)
        self.result_repo = SqliteTestResultRepository(self.db)
        self.domain_repo = SqliteTestDomainRepository(self.db)
        self.mapping_repo = SqliteTestMappingRepository(self.db)
        self.integrity_repo = SqliteTestIntegrityRepository(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()
        config.CCDASH_TEST_VISUALIZER_ENABLED = self._prev_flag

    async def test_feature_flag_gates_table_creation(self) -> None:
        prev = config.CCDASH_TEST_VISUALIZER_ENABLED
        config.CCDASH_TEST_VISUALIZER_ENABLED = False
        db = await aiosqlite.connect(":memory:")
        db.row_factory = aiosqlite.Row
        try:
            await run_migrations(db)
            async with db.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'test_runs'"
            ) as cur:
                self.assertIsNone(await cur.fetchone())

            config.CCDASH_TEST_VISUALIZER_ENABLED = True
            await run_migrations(db)
            async with db.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'test_runs'"
            ) as cur:
                self.assertIsNotNone(await cur.fetchone())
        finally:
            await db.close()
            config.CCDASH_TEST_VISUALIZER_ENABLED = prev

    async def test_protocol_runtime_checks(self) -> None:
        self.assertIsInstance(self.run_repo, TestRunRepository)
        self.assertIsInstance(self.definition_repo, TestDefinitionRepository)
        self.assertIsInstance(self.result_repo, TestResultRepository)
        self.assertIsInstance(self.domain_repo, TestDomainRepository)
        self.assertIsInstance(self.mapping_repo, TestMappingRepository)
        self.assertIsInstance(self.integrity_repo, TestIntegrityRepository)

    async def test_definition_get_or_create_is_idempotent(self) -> None:
        first = await self.definition_repo.get_or_create(
            project_id="project-1",
            path="tests/test_api.py",
            name="test_health",
            framework="pytest",
            tags=["smoke"],
            owner="qa",
        )
        second = await self.definition_repo.get_or_create(
            project_id="project-1",
            path="tests/test_api.py",
            name="test_health",
            framework="pytest",
            tags=["smoke"],
            owner="qa",
        )

        self.assertEqual(first["test_id"], second["test_id"])
        async with self.db.execute("SELECT COUNT(*) FROM test_definitions") as cur:
            row = await cur.fetchone()
            self.assertEqual(row[0], 1)

    async def test_run_repository_queries_and_latest_for_feature(self) -> None:
        test_id = "test-1"
        await self.definition_repo.upsert(
            {
                "test_id": test_id,
                "project_id": "project-1",
                "path": "tests/test_feature.py",
                "name": "test_feature",
                "framework": "pytest",
            },
            project_id="project-1",
        )
        await self.mapping_repo.upsert(
            {
                "project_id": "project-1",
                "test_id": test_id,
                "feature_id": "feature-1",
                "provider_source": "repo_heuristics",
                "confidence": 0.7,
            }
        )

        await self.run_repo.upsert(
            {
                "run_id": "run-1",
                "project_id": "project-1",
                "timestamp": "2026-02-28T10:00:00Z",
                "agent_session_id": "session-1",
            }
        )
        await self.run_repo.upsert(
            {
                "run_id": "run-2",
                "project_id": "project-1",
                "timestamp": "2026-02-28T11:00:00Z",
                "agent_session_id": "session-1",
            }
        )
        await self.result_repo.upsert({"run_id": "run-1", "test_id": test_id, "status": "passed"})
        await self.result_repo.upsert({"run_id": "run-2", "test_id": test_id, "status": "failed"})

        by_project = await self.run_repo.list_by_project("project-1")
        self.assertEqual(by_project[0]["run_id"], "run-2")

        by_session = await self.run_repo.list_by_session("project-1", "session-1")
        self.assertEqual(len(by_session), 2)

        latest = await self.run_repo.get_latest_for_feature("project-1", "feature-1")
        self.assertIsNotNone(latest)
        self.assertEqual(latest["run_id"], "run-2")

    async def test_result_repository_is_append_only(self) -> None:
        await self.definition_repo.upsert(
            {
                "test_id": "test-append",
                "project_id": "project-1",
                "path": "tests/test_append.py",
                "name": "test_append",
            },
            project_id="project-1",
        )
        await self.run_repo.upsert(
            {"run_id": "run-a", "project_id": "project-1", "timestamp": "2026-02-28T09:00:00Z"}
        )
        await self.result_repo.upsert({"run_id": "run-a", "test_id": "test-append", "status": "passed"})
        await self.result_repo.upsert({"run_id": "run-a", "test_id": "test-append", "status": "failed"})

        same_row = await self.result_repo.get_by_id("run-a", "test-append")
        self.assertIsNotNone(same_row)
        self.assertEqual(same_row["status"], "passed")

        await self.run_repo.upsert(
            {"run_id": "run-b", "project_id": "project-1", "timestamp": "2026-02-28T10:00:00Z"}
        )
        await self.result_repo.upsert({"run_id": "run-b", "test_id": "test-append", "status": "failed"})

        history = await self.result_repo.get_history_for_test("test-append")
        self.assertEqual(len(history), 2)
        latest = await self.result_repo.get_latest_status("test-append")
        self.assertIsNotNone(latest)
        self.assertEqual(latest["run_id"], "run-b")
        self.assertEqual(latest["status"], "failed")

    async def test_domain_tree_builds_parent_child_structure(self) -> None:
        parent = await self.domain_repo.get_or_create_by_name("project-1", "Core")
        child = await self.domain_repo.get_or_create_by_name(
            "project-1",
            "Auth",
            parent_id=parent["domain_id"],
        )

        self.assertEqual(child["parent_id"], parent["domain_id"])
        tree = await self.domain_repo.list_tree("project-1")
        self.assertEqual(len(tree), 1)
        self.assertEqual(tree[0]["domain_id"], parent["domain_id"])
        self.assertEqual(len(tree[0]["children"]), 1)
        self.assertEqual(tree[0]["children"][0]["domain_id"], child["domain_id"])

    async def test_mapping_repository_primary_selection(self) -> None:
        await self.definition_repo.upsert(
            {
                "test_id": "test-map",
                "project_id": "project-1",
                "path": "tests/test_map.py",
                "name": "test_map",
            },
            project_id="project-1",
        )
        await self.mapping_repo.upsert(
            {
                "project_id": "project-1",
                "test_id": "test-map",
                "feature_id": "feature-1",
                "provider_source": "repo_heuristics",
                "confidence": 0.4,
            }
        )
        await self.mapping_repo.upsert(
            {
                "project_id": "project-1",
                "test_id": "test-map",
                "feature_id": "feature-1",
                "provider_source": "semantic_llm",
                "confidence": 0.9,
            }
        )

        primary = await self.mapping_repo.get_primary_for_test("project-1", "test-map")
        self.assertEqual(len(primary), 1)
        self.assertEqual(primary[0]["provider_source"], "semantic_llm")

        await self.mapping_repo.upsert(
            {
                "project_id": "project-1",
                "test_id": "test-map",
                "feature_id": "feature-1",
                "provider_source": "repo_heuristics",
                "confidence": 0.95,
            }
        )
        primary_after = await self.mapping_repo.get_primary_for_test("project-1", "test-map")
        self.assertEqual(len(primary_after), 1)
        self.assertEqual(primary_after[0]["provider_source"], "repo_heuristics")

    async def test_integrity_repository_filters(self) -> None:
        await self.integrity_repo.upsert(
            {
                "signal_id": "sig-1",
                "project_id": "project-1",
                "git_sha": "sha-1",
                "file_path": "tests/test_one.py",
                "signal_type": "assertion_removed",
                "created_at": "2026-02-28T09:00:00Z",
            }
        )
        await self.integrity_repo.upsert(
            {
                "signal_id": "sig-2",
                "project_id": "project-1",
                "git_sha": "sha-2",
                "file_path": "tests/test_two.py",
                "signal_type": "skip_introduced",
                "created_at": "2026-02-28T10:00:00Z",
            }
        )

        all_rows = await self.integrity_repo.list_by_project("project-1")
        self.assertEqual(len(all_rows), 2)

        by_sha = await self.integrity_repo.list_by_sha("project-1", "sha-1")
        self.assertEqual(len(by_sha), 1)
        self.assertEqual(by_sha[0]["signal_id"], "sig-1")

        since_rows = await self.integrity_repo.list_since("project-1", "2026-02-28T09:30:00Z")
        self.assertEqual(len(since_rows), 1)
        self.assertEqual(since_rows[0]["signal_id"], "sig-2")


if __name__ == "__main__":
    unittest.main()
