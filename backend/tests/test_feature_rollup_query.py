"""Tests for SqliteFeatureRollupRepository.get_feature_session_rollups.

Fixtures: 5 features with mixed linked-session counts (0, 1, 5, 20 sessions),
mixed tasks/docs/tests.

Covers:
  - session_counts totals per feature
  - subthread_count math when roots + children exist
  - token totals sum correctly
  - `missing` lists unknown IDs correctly
  - 101 IDs raises ValueError (via FeatureRollupQuery model)
  - feature with zero links still appears in `rollups` with zeros
  - test_metrics gated by include_test_metrics
"""
from __future__ import annotations

import unittest
import uuid
from datetime import datetime, timezone

import aiosqlite

from backend.db.repositories.feature_queries import FeatureRollupQuery
from backend.db.repositories.feature_rollup import SqliteFeatureRollupRepository
from backend.db.sqlite_migrations import run_migrations, _TEST_VISUALIZER_TABLES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PROJECT_ID = "test-project"


def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _seed_feature(db: aiosqlite.Connection, fid: str, name: str) -> None:
    now = _now()
    await db.execute(
        """INSERT INTO features (id, project_id, name, status, created_at, updated_at, data_json)
           VALUES (?, ?, ?, ?, ?, ?, '{}')
           ON CONFLICT(id) DO NOTHING""",
        (fid, PROJECT_ID, name, "in-progress", now, now),
    )


async def _seed_session(
    db: aiosqlite.Connection,
    session_id: str,
    *,
    parent_session_id: str | None = None,
    total_cost: float = 1.0,
    display_cost_usd: float | None = None,
    observed_tokens: int = 100,
    model_io_tokens: int = 80,
    cache_input_tokens: int = 20,
    model: str = "claude-sonnet-4-5",
    thread_kind: str = "",
) -> None:
    now = _now()
    await db.execute(
        """INSERT INTO sessions (
            id, project_id, task_id, status, model,
            platform_type, total_cost, display_cost_usd,
            observed_tokens, model_io_tokens, cache_input_tokens,
            parent_session_id, started_at, ended_at, created_at, updated_at, source_file,
            thread_kind, root_session_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO NOTHING""",
        (
            session_id, PROJECT_ID, "", "completed", model,
            "Claude Code", total_cost, display_cost_usd,
            observed_tokens, model_io_tokens, cache_input_tokens,
            parent_session_id, now, now, now, now, f"{session_id}.jsonl",
            thread_kind, session_id,
        ),
    )


async def _link_feature_session(
    db: aiosqlite.Connection, feature_id: str, session_id: str
) -> None:
    now = _now()
    await db.execute(
        """INSERT INTO entity_links (
            source_type, source_id, target_type, target_id, link_type,
            origin, confidence, depth, sort_order, created_at
        ) VALUES ('feature', ?, 'session', ?, 'related', 'auto', 1.0, 0, 0, ?)
        ON CONFLICT(source_type, source_id, target_type, target_id, link_type) DO NOTHING""",
        (feature_id, session_id, now),
    )


async def _link_feature_document(
    db: aiosqlite.Connection, feature_id: str, doc_id: str
) -> None:
    now = _now()
    await db.execute(
        """INSERT INTO entity_links (
            source_type, source_id, target_type, target_id, link_type,
            origin, confidence, depth, sort_order, created_at
        ) VALUES ('feature', ?, 'document', ?, 'related', 'auto', 1.0, 0, 0, ?)
        ON CONFLICT(source_type, source_id, target_type, target_id, link_type) DO NOTHING""",
        (feature_id, doc_id, now),
    )


async def _link_feature_task(
    db: aiosqlite.Connection, feature_id: str, task_id: str
) -> None:
    now = _now()
    await db.execute(
        """INSERT INTO entity_links (
            source_type, source_id, target_type, target_id, link_type,
            origin, confidence, depth, sort_order, created_at
        ) VALUES ('feature', ?, 'task', ?, 'related', 'auto', 1.0, 0, 0, ?)
        ON CONFLICT(source_type, source_id, target_type, target_id, link_type) DO NOTHING""",
        (feature_id, task_id, now),
    )


async def _seed_document(
    db: aiosqlite.Connection, doc_id: str, doc_type: str = "prd"
) -> None:
    now = _now()
    await db.execute(
        """INSERT INTO documents (
            id, project_id, title, file_path, doc_type, frontmatter_json, source_file,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO NOTHING""",
        (doc_id, PROJECT_ID, f"Doc {doc_id}", f"/docs/{doc_id}.md", doc_type,
         "{}", f"{doc_id}.md", now, now),
    )


async def _seed_commit_correlation(
    db: aiosqlite.Connection, feature_id: str, session_id: str, commit_hash: str
) -> None:
    now = _now()
    source_key = f"{session_id}:{commit_hash}"
    await db.execute(
        """INSERT INTO commit_correlations (
            project_id, session_id, commit_hash, feature_id,
            window_start, window_end, source_key, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, '{}')
        ON CONFLICT(project_id, source_key) DO NOTHING""",
        (PROJECT_ID, session_id, commit_hash, feature_id, now, now, source_key),
    )


async def _seed_test_definition(
    db: aiosqlite.Connection, test_id: str
) -> None:
    now = _now()
    await db.execute(
        """INSERT INTO test_definitions (test_id, project_id, path, name, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(test_id) DO NOTHING""",
        (test_id, PROJECT_ID, f"tests/{test_id}.py", test_id, now, now),
    )


async def _seed_test_run(db: aiosqlite.Connection, run_id: str) -> None:
    now = _now()
    await db.execute(
        """INSERT INTO test_runs (
            run_id, project_id, git_sha, timestamp, metadata_json
        ) VALUES (?, ?, ?, ?, '{}')
        ON CONFLICT(run_id) DO NOTHING""",
        (run_id, PROJECT_ID, "abc123", now),
    )


async def _seed_test_result(
    db: aiosqlite.Connection, run_id: str, test_id: str, status: str
) -> None:
    now = _now()
    await db.execute(
        """INSERT INTO test_results (run_id, test_id, status, created_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(run_id, test_id) DO UPDATE SET status = excluded.status""",
        (run_id, test_id, status, now),
    )


async def _seed_test_feature_mapping(
    db: aiosqlite.Connection, feature_id: str, test_id: str
) -> None:
    await db.execute(
        """INSERT INTO test_feature_mappings (
            project_id, test_id, feature_id, provider_source, confidence, version
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(test_id, feature_id, provider_source, version) DO NOTHING""",
        (PROJECT_ID, test_id, feature_id, "pytest", 0.9, 1),
    )


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestFeatureRollupQuery(unittest.IsolatedAsyncioTestCase):
    """All tests use an in-memory SQLite database seeded via helpers above."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        # Explicitly create test-visualizer tables (gated by config flag in production)
        await self.db.executescript(_TEST_VISUALIZER_TABLES)

        # Feature IDs
        self.F_ZERO = "F-ZERO"    # 0 linked sessions
        self.F_ONE = "F-ONE"      # 1 linked session
        self.F_FIVE = "F-FIVE"    # 5 linked sessions (mix of roots + children)
        self.F_TWENTY = "F-TWENTY"  # 20 linked sessions
        self.F_DOCS = "F-DOCS"    # sessions + docs + tasks

        all_fids = [self.F_ZERO, self.F_ONE, self.F_FIVE, self.F_TWENTY, self.F_DOCS]
        for fid in all_fids:
            await _seed_feature(self.db, fid, f"Feature {fid}")

        # F_ZERO: exists but no entity_links
        # (no sessions inserted)

        # F_ONE: 1 session, primary (no parent)
        s1 = _uid()
        await _seed_session(self.db, s1, total_cost=2.0, observed_tokens=200,
                            model_io_tokens=160, cache_input_tokens=40)
        await _link_feature_session(self.db, self.F_ONE, s1)
        self._f_one_session = s1

        # F_FIVE: 5 sessions — 2 primary (no parent), 3 children of root[0]
        roots5 = [_uid() for _ in range(2)]
        children5 = [_uid() for _ in range(3)]
        for r in roots5:
            await _seed_session(self.db, r, total_cost=1.0, observed_tokens=100,
                                model_io_tokens=80, cache_input_tokens=20)
            await _link_feature_session(self.db, self.F_FIVE, r)
        for c in children5:
            await _seed_session(self.db, c, parent_session_id=roots5[0],
                                total_cost=0.5, observed_tokens=50,
                                model_io_tokens=40, cache_input_tokens=10)
            await _link_feature_session(self.db, self.F_FIVE, c)
        self._f_five_roots = roots5
        self._f_five_children = children5

        # F_TWENTY: 20 sessions all primary (no parent_session_id)
        sessions20 = [_uid() for _ in range(20)]
        for s in sessions20:
            await _seed_session(self.db, s, total_cost=0.1, observed_tokens=10,
                                model_io_tokens=8, cache_input_tokens=2)
            await _link_feature_session(self.db, self.F_TWENTY, s)

        # F_DOCS: 2 sessions, 3 docs (2 prd + 1 spec), 2 tasks, 1 commit
        s_d1, s_d2 = _uid(), _uid()
        for s in [s_d1, s_d2]:
            await _seed_session(self.db, s, total_cost=1.5, observed_tokens=150,
                                model_io_tokens=120, cache_input_tokens=30)
            await _link_feature_session(self.db, self.F_DOCS, s)

        doc_prd1, doc_prd2, doc_spec = _uid(), _uid(), _uid()
        for did, dtype in [(doc_prd1, "prd"), (doc_prd2, "prd"), (doc_spec, "spec")]:
            await _seed_document(self.db, did, dtype)
            await _link_feature_document(self.db, self.F_DOCS, did)

        task1, task2 = _uid(), _uid()
        for tid in [task1, task2]:
            await _link_feature_task(self.db, self.F_DOCS, tid)

        commit_hash = "deadbeefcafe"
        await _seed_commit_correlation(self.db, self.F_DOCS, s_d1, commit_hash)

        # Test metrics: F_DOCS has 3 tests, 1 failing
        run_id = _uid()
        await _seed_test_run(self.db, run_id)
        for i in range(3):
            tid = f"test-{self.F_DOCS}-{i}"
            await _seed_test_definition(self.db, tid)
            status = "failed" if i == 0 else "passed"
            await _seed_test_result(self.db, run_id, tid, status)
            await _seed_test_feature_mapping(self.db, self.F_DOCS, tid)

        await self.db.commit()
        self.repo = SqliteFeatureRollupRepository(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _query(self, fids: list[str], **kwargs) -> FeatureRollupQuery:
        return FeatureRollupQuery(
            feature_ids=fids,
            include_fields={"session_counts", "token_cost_totals",
                            "model_provider_summary", "latest_activity",
                            "doc_metrics"},
            include_freshness=False,
            **kwargs,
        )

    # ------------------------------------------------------------------
    # session_counts
    # ------------------------------------------------------------------

    async def test_session_count_zero_for_unlinked_feature(self) -> None:
        q = self._query([self.F_ZERO])
        batch = await self.repo.get_feature_session_rollups(PROJECT_ID, q)
        self.assertIn(self.F_ZERO, batch.rollups)
        entry = batch.rollups[self.F_ZERO]
        self.assertEqual(entry.session_count, 0)
        self.assertEqual(entry.primary_session_count, 0)
        self.assertEqual(entry.subthread_count, 0)

    async def test_session_count_one(self) -> None:
        q = self._query([self.F_ONE])
        batch = await self.repo.get_feature_session_rollups(PROJECT_ID, q)
        entry = batch.rollups[self.F_ONE]
        self.assertEqual(entry.session_count, 1)
        self.assertEqual(entry.primary_session_count, 1)
        self.assertEqual(entry.subthread_count, 0)

    async def test_session_count_five_with_subthreads(self) -> None:
        q = self._query([self.F_FIVE])
        batch = await self.repo.get_feature_session_rollups(PROJECT_ID, q)
        entry = batch.rollups[self.F_FIVE]
        self.assertEqual(entry.session_count, 5)
        # 2 roots (no parent_session_id), 3 children
        self.assertEqual(entry.primary_session_count, 2)
        self.assertEqual(entry.subthread_count, 3)

    async def test_session_count_twenty(self) -> None:
        q = self._query([self.F_TWENTY])
        batch = await self.repo.get_feature_session_rollups(PROJECT_ID, q)
        entry = batch.rollups[self.F_TWENTY]
        self.assertEqual(entry.session_count, 20)
        self.assertEqual(entry.primary_session_count, 20)
        self.assertEqual(entry.subthread_count, 0)

    # ------------------------------------------------------------------
    # token / cost totals
    # ------------------------------------------------------------------

    async def test_token_totals_f_one(self) -> None:
        q = self._query([self.F_ONE])
        batch = await self.repo.get_feature_session_rollups(PROJECT_ID, q)
        entry = batch.rollups[self.F_ONE]
        self.assertAlmostEqual(entry.total_cost, 2.0)
        self.assertEqual(entry.observed_tokens, 200)
        self.assertEqual(entry.model_io_tokens, 160)
        self.assertEqual(entry.cache_input_tokens, 40)

    async def test_token_totals_f_five(self) -> None:
        # 2 roots @ 100 each + 3 children @ 50 each = 350 observed_tokens
        q = self._query([self.F_FIVE])
        batch = await self.repo.get_feature_session_rollups(PROJECT_ID, q)
        entry = batch.rollups[self.F_FIVE]
        self.assertEqual(entry.observed_tokens, 350)
        # total_cost: 2*1.0 + 3*0.5 = 3.5
        self.assertAlmostEqual(entry.total_cost, 3.5)

    async def test_token_totals_f_twenty(self) -> None:
        q = self._query([self.F_TWENTY])
        batch = await self.repo.get_feature_session_rollups(PROJECT_ID, q)
        entry = batch.rollups[self.F_TWENTY]
        self.assertAlmostEqual(entry.total_cost, 20 * 0.1, places=5)
        self.assertEqual(entry.observed_tokens, 20 * 10)

    async def test_token_totals_zero_for_unlinked_feature(self) -> None:
        q = self._query([self.F_ZERO])
        batch = await self.repo.get_feature_session_rollups(PROJECT_ID, q)
        entry = batch.rollups[self.F_ZERO]
        self.assertEqual(entry.total_cost, 0.0)
        self.assertEqual(entry.observed_tokens, 0)

    # ------------------------------------------------------------------
    # missing IDs
    # ------------------------------------------------------------------

    async def test_missing_unknown_id(self) -> None:
        unknown = "F-DOES-NOT-EXIST"
        q = self._query([self.F_ONE, unknown])
        batch = await self.repo.get_feature_session_rollups(PROJECT_ID, q)
        self.assertIn(unknown, batch.missing)
        self.assertNotIn(unknown, batch.rollups)
        self.assertIn(self.F_ONE, batch.rollups)

    async def test_missing_all_unknown(self) -> None:
        q = self._query(["X-1", "X-2", "X-3"])
        batch = await self.repo.get_feature_session_rollups(PROJECT_ID, q)
        self.assertEqual(set(batch.missing), {"X-1", "X-2", "X-3"})
        self.assertEqual(batch.rollups, {})

    async def test_missing_empty_when_all_known(self) -> None:
        q = self._query([self.F_ZERO, self.F_ONE])
        batch = await self.repo.get_feature_session_rollups(PROJECT_ID, q)
        self.assertEqual(batch.missing, [])

    # ------------------------------------------------------------------
    # 101 ID cap via FeatureRollupQuery validator
    # ------------------------------------------------------------------

    def test_101_ids_raises_value_error(self) -> None:
        ids = [f"F-{i:04d}" for i in range(101)]
        with self.assertRaises(ValueError) as ctx:
            FeatureRollupQuery(feature_ids=ids)
        self.assertIn("100", str(ctx.exception))

    def test_100_ids_accepted(self) -> None:
        ids = [f"F-{i:04d}" for i in range(100)]
        query = FeatureRollupQuery(feature_ids=ids)
        self.assertEqual(len(query.feature_ids), 100)

    # ------------------------------------------------------------------
    # Zero-link feature still appears in rollups with zeros
    # ------------------------------------------------------------------

    async def test_zero_link_feature_in_rollups_not_missing(self) -> None:
        q = self._query([self.F_ZERO])
        batch = await self.repo.get_feature_session_rollups(PROJECT_ID, q)
        self.assertIn(self.F_ZERO, batch.rollups)
        self.assertNotIn(self.F_ZERO, batch.missing)
        entry = batch.rollups[self.F_ZERO]
        self.assertEqual(entry.feature_id, self.F_ZERO)

    # ------------------------------------------------------------------
    # doc_metrics
    # ------------------------------------------------------------------

    async def test_doc_metrics_for_f_docs(self) -> None:
        q = self._query([self.F_DOCS])
        batch = await self.repo.get_feature_session_rollups(PROJECT_ID, q)
        entry = batch.rollups[self.F_DOCS]
        self.assertEqual(entry.linked_doc_count, 3)
        self.assertEqual(entry.linked_task_count, 2)
        self.assertEqual(entry.linked_commit_count, 1)

        # doc type breakdown: 2 prd, 1 spec
        types = {d["doc_type"]: d["count"] for d in (entry.linked_doc_counts_by_type or [])}
        self.assertEqual(types.get("prd"), 2)
        self.assertEqual(types.get("spec"), 1)

    async def test_doc_metrics_zero_for_unlinked(self) -> None:
        q = self._query([self.F_ZERO])
        batch = await self.repo.get_feature_session_rollups(PROJECT_ID, q)
        entry = batch.rollups[self.F_ZERO]
        self.assertEqual(entry.linked_doc_count, 0)
        self.assertEqual(entry.linked_task_count, 0)
        self.assertEqual(entry.linked_commit_count, 0)

    # ------------------------------------------------------------------
    # test_metrics gating
    # ------------------------------------------------------------------

    async def test_test_metrics_excluded_by_default(self) -> None:
        q = self._query([self.F_DOCS], include_test_metrics=False)
        batch = await self.repo.get_feature_session_rollups(PROJECT_ID, q)
        entry = batch.rollups[self.F_DOCS]
        self.assertIsNone(entry.test_count)
        self.assertIsNone(entry.failing_test_count)

    async def test_test_metrics_included_when_requested(self) -> None:
        q = FeatureRollupQuery(
            feature_ids=[self.F_DOCS],
            include_fields={"session_counts", "doc_metrics", "test_metrics"},
            include_test_metrics=True,
            include_freshness=False,
        )
        batch = await self.repo.get_feature_session_rollups(PROJECT_ID, q)
        entry = batch.rollups[self.F_DOCS]
        self.assertEqual(entry.test_count, 3)
        self.assertEqual(entry.failing_test_count, 1)

    async def test_test_metrics_zero_for_feature_with_no_tests(self) -> None:
        q = FeatureRollupQuery(
            feature_ids=[self.F_ZERO],
            include_fields={"session_counts", "test_metrics"},
            include_test_metrics=True,
            include_freshness=False,
        )
        batch = await self.repo.get_feature_session_rollups(PROJECT_ID, q)
        entry = batch.rollups[self.F_ZERO]
        self.assertEqual(entry.test_count, 0)

    # ------------------------------------------------------------------
    # Batch: all features together
    # ------------------------------------------------------------------

    async def test_batch_all_features(self) -> None:
        fids = [self.F_ZERO, self.F_ONE, self.F_FIVE, self.F_TWENTY, self.F_DOCS]
        q = self._query(fids)
        batch = await self.repo.get_feature_session_rollups(PROJECT_ID, q)
        self.assertEqual(len(batch.rollups), 5)
        self.assertEqual(batch.missing, [])
        self.assertEqual(batch.rollups[self.F_ZERO].session_count, 0)
        self.assertEqual(batch.rollups[self.F_ONE].session_count, 1)
        self.assertEqual(batch.rollups[self.F_FIVE].session_count, 5)
        self.assertEqual(batch.rollups[self.F_TWENTY].session_count, 20)

    # ------------------------------------------------------------------
    # generated_at / cache_version
    # ------------------------------------------------------------------

    async def test_batch_has_generated_at(self) -> None:
        q = self._query([self.F_ONE])
        batch = await self.repo.get_feature_session_rollups(PROJECT_ID, q)
        self.assertIsNotNone(batch.generated_at)
        # Should be a valid ISO8601-ish string
        self.assertIn("T", batch.generated_at)

    async def test_batch_has_cache_version(self) -> None:
        q = self._query([self.F_ONE])
        batch = await self.repo.get_feature_session_rollups(PROJECT_ID, q)
        self.assertIsInstance(batch.cache_version, str)

    # ------------------------------------------------------------------
    # Precision
    # ------------------------------------------------------------------

    async def test_precision_eventually_consistent_by_default(self) -> None:
        q = self._query([self.F_ONE])
        batch = await self.repo.get_feature_session_rollups(PROJECT_ID, q)
        self.assertEqual(batch.rollups[self.F_ONE].precision, "eventually_consistent")


if __name__ == "__main__":
    unittest.main()
