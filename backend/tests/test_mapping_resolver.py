import tempfile
import unittest
from pathlib import Path

import aiosqlite

from backend import config
from backend.db.repositories.features import SqliteFeatureRepository
from backend.db.repositories.test_domains import SqliteTestDomainRepository
from backend.db.repositories.test_mappings import SqliteTestMappingRepository
from backend.db.repositories.test_results import SqliteTestResultRepository
from backend.db.repositories.test_runs import SqliteTestRunRepository
from backend.db.sqlite_migrations import run_migrations
from backend.services.mapping_resolver import (
    MappingCandidate,
    MappingProvider,
    MappingResolver,
    RepoHeuristicsProvider,
    SemanticLLMProvider,
    TestMetadataProvider,
    validate_semantic_mapping_file,
)


class TestMappingResolver(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._prev_enabled = config.CCDASH_TEST_VISUALIZER_ENABLED
        self._prev_root = config.CCDASH_PROJECT_ROOT
        config.CCDASH_TEST_VISUALIZER_ENABLED = True

        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)

        self.feature_repo = SqliteFeatureRepository(self.db)
        self.mapping_repo = SqliteTestMappingRepository(self.db)
        self.domain_repo = SqliteTestDomainRepository(self.db)
        self.run_repo = SqliteTestRunRepository(self.db)
        self.result_repo = SqliteTestResultRepository(self.db)
        await self._seed_features()

    async def asyncTearDown(self) -> None:
        await self.db.close()
        config.CCDASH_TEST_VISUALIZER_ENABLED = self._prev_enabled
        config.CCDASH_PROJECT_ROOT = self._prev_root

    async def _seed_features(self) -> None:
        await self.feature_repo.upsert({"id": "login", "name": "Login"}, project_id="project-1")
        await self.feature_repo.upsert({"id": "feature-auth-login", "name": "Auth Login"}, project_id="project-1")
        await self.feature_repo.upsert({"id": "checkout", "name": "Checkout"}, project_id="project-1")

    async def test_providers_implement_protocol(self) -> None:
        self.assertIsInstance(RepoHeuristicsProvider(self.db), MappingProvider)
        self.assertIsInstance(TestMetadataProvider(self.db), MappingProvider)
        self.assertIsInstance(SemanticLLMProvider({"mappings": []}), MappingProvider)

    async def test_repo_heuristics_provider_maps_domain_and_feature(self) -> None:
        provider = RepoHeuristicsProvider(self.db)
        rows = await provider.resolve(
            [
                {
                    "test_id": "test-1",
                    "path": "tests/auth/test_login.py",
                    "name": "test_login_valid",
                    "framework": "pytest",
                    "tags": [],
                }
            ],
            project_id="project-1",
            context={},
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].feature_id, "login")
        self.assertGreaterEqual(rows[0].confidence, 0.5)
        self.assertTrue(rows[0].domain_id)
        domain = await self.domain_repo.get_by_id(rows[0].domain_id or "")
        self.assertEqual(str((domain or {}).get("name") or "").lower(), "auth")

    async def test_test_metadata_provider_reads_markers_and_tags(self) -> None:
        provider = TestMetadataProvider(self.db)
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_path = Path(tmp_dir) / "tests" / "auth" / "test_login.py"
            source_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.write_text(
                "\n".join(
                    [
                        "import pytest",
                        "@pytest.mark.feature('feature-auth-login')",
                        "@pytest.mark.domain('auth')",
                        "def test_login_ok():",
                        "    assert True",
                    ]
                ),
                encoding="utf-8",
            )
            config.CCDASH_PROJECT_ROOT = tmp_dir

            rows = await provider.resolve(
                [
                    {
                        "test_id": "test-2",
                        "path": "tests/auth/test_login.py",
                        "name": "test_login_ok",
                        "framework": "pytest",
                        "tags": [],
                    },
                    {
                        "test_id": "test-3",
                        "path": "tests/other/test_checkout.py",
                        "name": "test_checkout",
                        "framework": "pytest",
                        "tags": ["feature:checkout", "domain:commerce"],
                    },
                ],
                project_id="project-1",
                context={"project_root": tmp_dir},
            )

        by_test = {}
        for row in rows:
            by_test.setdefault(row.test_id, []).append(row)

        self.assertIn("test-2", by_test)
        self.assertEqual(by_test["test-2"][0].feature_id, "feature-auth-login")
        self.assertAlmostEqual(by_test["test-2"][0].confidence, 0.9, places=2)
        self.assertIn("test-3", by_test)
        self.assertEqual(by_test["test-3"][0].feature_id, "checkout")

    async def test_test_metadata_provider_does_not_create_domain_without_feature_match(self) -> None:
        provider = TestMetadataProvider(self.db)
        before = await self.domain_repo.list_paginated(0, 500, project_id="project-1")
        before_ids = {str(row.get("domain_id") or "") for row in before}

        rows = await provider.resolve(
            [
                {
                    "test_id": "test-orphan-domain",
                    "path": "tests/unknown/test_anything.py",
                    "name": "test_anything",
                    "framework": "pytest",
                    "tags": ["domain:unknown", "feature:not-a-real-feature"],
                }
            ],
            project_id="project-1",
            context={},
        )

        after = await self.domain_repo.list_paginated(0, 500, project_id="project-1")
        after_ids = {str(row.get("domain_id") or "") for row in after}
        self.assertEqual(rows, [])
        self.assertSetEqual(before_ids, after_ids)

    async def test_semantic_provider_and_validation(self) -> None:
        valid, message = validate_semantic_mapping_file(
            {"mappings": [{"test_id": "test-1", "feature_id": "login", "confidence": 0.92}]}
        )
        self.assertTrue(valid, message)

        valid, message = validate_semantic_mapping_file({"mappings": [{"test_id": "test-1"}]})
        self.assertFalse(valid)
        self.assertIn("feature_id", message)

        provider = SemanticLLMProvider(
            {
                "generated_by": "semantic-agent",
                "mappings": [
                    {
                        "test_id": "test-1",
                        "feature_id": "login",
                        "domain_id": "dom-auth",
                        "confidence": 0.95,
                        "rationale": "Direct login checks",
                    }
                ],
            }
        )
        rows = await provider.resolve(
            [{"test_id": "test-1", "path": "tests/auth/test_login.py", "name": "test_login"}],
            project_id="project-1",
            context={},
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].feature_id, "login")
        self.assertEqual(rows[0].domain_id, "dom-auth")
        self.assertGreaterEqual(rows[0].confidence, 0.9)

    async def test_resolver_conflict_resolution_picks_single_primary(self) -> None:
        class _ProviderA:
            name = "provider_a"
            priority = 30

            async def resolve(self, test_definitions, project_id, context):
                _ = test_definitions, project_id, context
                return [MappingCandidate("test-1", "login", "dom-a", 0.8, self.name)]

        class _ProviderB:
            name = "provider_b"
            priority = 40

            async def resolve(self, test_definitions, project_id, context):
                _ = test_definitions, project_id, context
                return [MappingCandidate("test-1", "checkout", "dom-b", 0.7, self.name)]

        class _ProviderLow:
            name = "provider_low"
            priority = 50

            async def resolve(self, test_definitions, project_id, context):
                _ = test_definitions, project_id, context
                return [MappingCandidate("test-1", "checkout", "dom-b", 0.4, self.name)]

        resolver = MappingResolver(self.db, providers=[_ProviderA(), _ProviderB(), _ProviderLow()])
        result = await resolver.resolve(
            project_id="project-1",
            test_definitions=[{"test_id": "test-1", "path": "tests/test_any.py", "name": "test_any"}],
            context={"run_id": "run-mock", "version": 1},
        )

        self.assertEqual(result.stored_count, 3)
        primary = await self.mapping_repo.get_primary_for_test("project-1", "test-1")
        self.assertEqual(len(primary), 1)
        self.assertEqual(primary[0]["feature_id"], "login")

    async def test_resolver_reuses_cached_mapping_when_definition_unchanged(self) -> None:
        class _Provider:
            name = "provider_cache"
            priority = 10

            async def resolve(self, test_definitions, project_id, context):
                _ = test_definitions, project_id, context
                return [MappingCandidate("test-cache-1", "login", "dom-cache", 0.91, self.name)]

        resolver = MappingResolver(self.db, providers=[_Provider()])
        definition = [{"test_id": "test-cache-1", "path": "tests/auth/test_login.py", "name": "test_login"}]

        first = await resolver.resolve(
            project_id="project-1",
            test_definitions=definition,
            context={"source": "unit_test", "version": 2},
        )
        second = await resolver.resolve(
            project_id="project-1",
            test_definitions=definition,
            context={"source": "unit_test", "version": 2},
        )

        self.assertEqual(first.stored_count, 1)
        self.assertEqual(second.stored_count, 0)
        self.assertEqual(second.tests_reused_cached, 1)

    async def test_repo_heuristics_provider_creates_subdomain_for_large_domain_group(self) -> None:
        provider = RepoHeuristicsProvider(self.db)
        definitions = [
            {
                "test_id": f"test-hier-{i}",
                "path": "tests/auth/api/test_login.py",
                "name": f"test_login_case_{i}",
                "framework": "pytest",
                "tags": [],
            }
            for i in range(45)
        ]

        rows = await provider.resolve(definitions, project_id="project-1", context={})
        self.assertGreaterEqual(len(rows), 1)

        domain_id = rows[0].domain_id or ""
        leaf = await self.domain_repo.get_by_id(domain_id)
        self.assertEqual(str((leaf or {}).get("name") or "").lower(), "api")

        parent_id = str((leaf or {}).get("parent_id") or "")
        parent = await self.domain_repo.get_by_id(parent_id)
        self.assertEqual(str((parent or {}).get("name") or "").lower(), "auth")

    async def test_path_fallback_provider_maps_unknown_tests(self) -> None:
        resolver = MappingResolver(self.db, provider_sources=["path_fallback"])
        result = await resolver.resolve(
            project_id="project-1",
            test_definitions=[
                {"test_id": "test-fallback-1", "path": "tests/odd/shape/spec_case.py", "name": "spec_case"}
            ],
            context={"source": "unit_test", "version": 2, "force_recompute": True},
        )

        self.assertEqual(result.primary_count, 1)
        mappings = await self.mapping_repo.get_primary_for_test("project-1", "test-fallback-1")
        self.assertEqual(len(mappings), 1)
        self.assertEqual(str(mappings[0].get("provider_source") or ""), "path_fallback")

    async def test_resolve_for_run_uses_run_results(self) -> None:
        await self.db.execute(
            """
            INSERT INTO test_definitions (test_id, project_id, path, name, framework)
            VALUES ('test-run-1', 'project-1', 'tests/auth/test_login.py', 'test_login_happy', 'pytest')
            """
        )
        await self.run_repo.upsert(
            {
                "run_id": "run-phase-7",
                "project_id": "project-1",
                "timestamp": "2026-03-01T12:00:00Z",
                "git_sha": "abc1234",
            }
        )
        await self.result_repo.upsert(
            {
                "run_id": "run-phase-7",
                "test_id": "test-run-1",
                "status": "passed",
            }
        )

        resolver = MappingResolver(self.db)
        result = await resolver.resolve_for_run(run_id="run-phase-7", project_id="project-1")
        rerun = await resolver.resolve_for_run(run_id="run-phase-7", project_id="project-1")

        self.assertGreaterEqual(result.stored_count, 1)
        self.assertEqual(rerun.stored_count, 0)
        self.assertGreaterEqual(rerun.tests_reused_cached, 1)
        mappings = await self.mapping_repo.list_by_test("project-1", "test-run-1")
        self.assertTrue(mappings)


if __name__ == "__main__":
    unittest.main()
