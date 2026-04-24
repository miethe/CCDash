"""Legacy parity tests for the FeatureCardDTO + rollup contract (P5-001).

Goal: prove the new SqliteFeatureRollupRepository.get_feature_session_rollups()
produces the same card-level metrics that the legacy
GET /features/{id}/linked-sessions endpoint would have provided to the
frontend for derivation.

Legacy derivation (frontend, ProjectBoard):
  session_count         = len(links)
  primary_session_count = len([l for l in links if not l.isSubthread])
  subthread_count       = len([l for l in links if l.isSubthread])
  total_cost            = sum(l.totalCost for l in links)
  observed_tokens       = sum(l.observedTokens for l in links)
  cache_input_tokens    = sum(l.cacheInputTokens for l in links)
  latest_session_at     = max(l.startedAt for l in links) or ""

Where isSubthread = bool(parent_session_id) OR session_type == "subagent".
The tests in this file use only parent_session_id as the subthread signal
(matching the dominant path in the legacy router, line 1453).

Parity exceptions are documented inline with # parity-exception: comments.

Each test stays under ~60 lines.
"""
from __future__ import annotations

import unittest
from datetime import datetime

import aiosqlite

from backend.db.repositories.feature_queries import FeatureRollupQuery
from backend.db.repositories.feature_rollup import SqliteFeatureRollupRepository
from backend.db.sqlite_migrations import run_migrations

# ---------------------------------------------------------------------------
# Fixture helpers (thin shims into the shared factory module)
# ---------------------------------------------------------------------------
from backend.tests.fixtures.feature_surface import (
    link_feature_session,
    seed_feature,
    seed_session,
)

PROJECT = "parity-project"


def _q(fids: list[str], fields=None) -> FeatureRollupQuery:
    return FeatureRollupQuery(
        feature_ids=fids,
        include_fields=set(
            fields
            or {"session_counts", "token_cost_totals", "latest_activity"}
        ),
        include_freshness=False,
    )


# ---------------------------------------------------------------------------
# Legacy derivation helpers (mirrors frontend ProjectBoard aggregation logic)
# ---------------------------------------------------------------------------

def _legacy_session_count(sessions: list[dict]) -> int:
    return len(sessions)


def _legacy_primary_count(sessions: list[dict]) -> int:
    return sum(1 for s in sessions if not s.get("parent_session_id"))


def _legacy_subthread_count(sessions: list[dict]) -> int:
    return sum(1 for s in sessions if s.get("parent_session_id"))


def _legacy_total_cost(sessions: list[dict]) -> float:
    return sum(float(s.get("total_cost") or 0) for s in sessions)


def _legacy_observed_tokens(sessions: list[dict]) -> int:
    return sum(int(s.get("observed_tokens") or 0) for s in sessions)


def _legacy_cache_input_tokens(sessions: list[dict]) -> int:
    return sum(int(s.get("cache_input_tokens") or 0) for s in sessions)


def _legacy_latest_session_at(sessions: list[dict]) -> str | None:
    timestamps: list[str] = [
        str(s["started_at"]) for s in sessions if s.get("started_at")
    ]
    return max(timestamps) if timestamps else None


# ---------------------------------------------------------------------------
# Base class: in-memory SQLite + rollup repo
# ---------------------------------------------------------------------------

class _ParityBase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.repo = SqliteFeatureRollupRepository(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def _raw_sessions(self, session_ids: list[str]) -> list[dict]:
        """Fetch raw session rows the legacy router would have loaded."""
        ph = ",".join("?" * len(session_ids))
        async with self.db.execute(
            f"SELECT * FROM sessions WHERE id IN ({ph})", session_ids
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class TestParityZeroSessions(_ParityBase):
    """A feature with no linked sessions: rollup zeros match legacy zeros."""

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.fid = "F-ZERO"
        await seed_feature(self.db, self.fid, project_id=PROJECT)
        await self.db.commit()

    async def test_parity_zero_sessions(self) -> None:
        legacy_sessions: list[dict] = []
        batch = await self.repo.get_feature_session_rollups(PROJECT, _q([self.fid]))
        e = batch.rollups[self.fid]

        self.assertEqual(e.session_count, _legacy_session_count(legacy_sessions))
        self.assertEqual(e.primary_session_count, _legacy_primary_count(legacy_sessions))
        self.assertEqual(e.subthread_count, _legacy_subthread_count(legacy_sessions))
        self.assertAlmostEqual(e.total_cost or 0.0, _legacy_total_cost(legacy_sessions))
        self.assertEqual(e.observed_tokens, _legacy_observed_tokens(legacy_sessions))


class TestParityOnePrimarySession(_ParityBase):
    """Single primary session: all card metrics must match legacy derivation."""

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.fid = "F-ONE"
        await seed_feature(self.db, self.fid, project_id=PROJECT)
        self.sid = await seed_session(
            self.db,
            project_id=PROJECT,
            total_cost=3.5,
            observed_tokens=350,
            model_io_tokens=280,
            cache_input_tokens=70,
            started_at="2026-04-20T10:00:00+00:00",
        )
        await link_feature_session(self.db, self.fid, self.sid)
        await self.db.commit()

    async def test_parity_one_primary_session(self) -> None:
        sessions = await self._raw_sessions([self.sid])
        batch = await self.repo.get_feature_session_rollups(PROJECT, _q([self.fid]))
        e = batch.rollups[self.fid]

        self.assertEqual(e.session_count, _legacy_session_count(sessions))            # 1
        self.assertEqual(e.primary_session_count, _legacy_primary_count(sessions))    # 1
        self.assertEqual(e.subthread_count, _legacy_subthread_count(sessions))        # 0
        self.assertAlmostEqual(float(e.total_cost or 0.0), _legacy_total_cost(sessions), places=5)  # 3.5
        self.assertEqual(e.observed_tokens, _legacy_observed_tokens(sessions))        # 350
        self.assertEqual(e.cache_input_tokens, _legacy_cache_input_tokens(sessions))  # 70

        # latest_session_at: both use MAX(started_at)
        # parity-exception: rollup stores ISO8601 from DB; legacy compared raw strings.
        # Both resolve to the same value for the same data — no truncation occurs here.
        self.assertIsNotNone(e.latest_session_at)


class TestParityMixedSubthreads(_ParityBase):
    """2 primary + 3 child sessions: subthread_count diverges from legacy if
    legacy also inherits unlisted subthreads (see parity-exception below)."""

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.fid = "F-MIX"
        await seed_feature(self.db, self.fid, project_id=PROJECT)

        # 2 primary sessions explicitly linked
        self.roots = []
        for i in range(2):
            sid = await seed_session(
                self.db,
                project_id=PROJECT,
                total_cost=1.0,
                observed_tokens=100,
                model_io_tokens=80,
                cache_input_tokens=20,
                started_at=f"2026-04-{20 + i}T10:00:00+00:00",
            )
            self.roots.append(sid)
            await link_feature_session(self.db, self.fid, sid)

        # 3 children of roots[0], all explicitly linked
        self.children = []
        for _ in range(3):
            cid = await seed_session(
                self.db,
                project_id=PROJECT,
                parent_session_id=self.roots[0],
                total_cost=0.5,
                observed_tokens=50,
                model_io_tokens=40,
                cache_input_tokens=10,
            )
            self.children.append(cid)
            await link_feature_session(self.db, self.fid, cid)

        await self.db.commit()

    async def test_parity_session_counts(self) -> None:
        all_sids = self.roots + self.children
        sessions = await self._raw_sessions(all_sids)
        batch = await self.repo.get_feature_session_rollups(PROJECT, _q([self.fid]))
        e = batch.rollups[self.fid]

        # Total session count: both paths count the same explicitly-linked set
        self.assertEqual(e.session_count, _legacy_session_count(sessions))            # 5

        # primary: no parent_session_id → 2 roots
        self.assertEqual(e.primary_session_count, _legacy_primary_count(sessions))    # 2

        # subthread: has parent_session_id → 3 children
        # parity-exception: the legacy linked-sessions router *also* expanded
        # unlisted subthreads via session_repo.list_paginated(root_session_id=…),
        # which would inflate subthread_count beyond the explicit link set.
        # The new rollup counts only sessions present in entity_links — it does
        # NOT inherit unlisted subthreads.  This is an intentional design change:
        # the new contract counts "linked sessions" not "all sessions in family".
        # Tests here assert rollup matches the explicitly-linked set (the safe
        # contract), not the expanded legacy set.
        self.assertEqual(e.subthread_count, _legacy_subthread_count(sessions))        # 3

    async def test_parity_token_cost_totals(self) -> None:
        all_sids = self.roots + self.children
        sessions = await self._raw_sessions(all_sids)
        batch = await self.repo.get_feature_session_rollups(PROJECT, _q([self.fid]))
        e = batch.rollups[self.fid]

        # 2*1.0 + 3*0.5 = 3.5
        self.assertAlmostEqual(float(e.total_cost or 0.0), _legacy_total_cost(sessions), places=5)
        # 2*100 + 3*50 = 350
        self.assertEqual(e.observed_tokens, _legacy_observed_tokens(sessions))
        # 2*20 + 3*10 = 70
        self.assertEqual(e.cache_input_tokens, _legacy_cache_input_tokens(sessions))


class TestParityTwentySessions(_ParityBase):
    """20 primary sessions: bulk token sums match."""

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.fid = "F-TWENTY"
        await seed_feature(self.db, self.fid, project_id=PROJECT)
        self.sids = []
        for i in range(20):
            sid = await seed_session(
                self.db,
                project_id=PROJECT,
                total_cost=0.1,
                observed_tokens=10,
                model_io_tokens=8,
                cache_input_tokens=2,
                started_at=f"2026-04-01T{i:02d}:00:00+00:00",
            )
            self.sids.append(sid)
            await link_feature_session(self.db, self.fid, sid)
        await self.db.commit()

    async def test_parity_twenty_sessions(self) -> None:
        sessions = await self._raw_sessions(self.sids)
        batch = await self.repo.get_feature_session_rollups(PROJECT, _q([self.fid]))
        e = batch.rollups[self.fid]

        self.assertEqual(e.session_count, 20)
        self.assertEqual(e.session_count, _legacy_session_count(sessions))
        self.assertEqual(e.primary_session_count, _legacy_primary_count(sessions))   # 20
        self.assertEqual(e.subthread_count, _legacy_subthread_count(sessions))        # 0

        # parity-exception: float summation over 20 rows may introduce sub-cent
        # floating-point rounding differences between Python sum() and SQLite SUM().
        # We assert within 5 decimal places (< $0.00001) rather than exact equality.
        self.assertAlmostEqual(
            float(e.total_cost or 0.0),
            _legacy_total_cost(sessions),
            places=5,
            msg="total_cost parity within 5 decimal places (float summation rounding)",
        )
        self.assertEqual(e.observed_tokens, _legacy_observed_tokens(sessions))        # 200


class TestParityLatestSessionAt(_ParityBase):
    """latest_session_at matches the MAX(started_at) the legacy router returns."""

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.fid = "F-LATEST"
        await seed_feature(self.db, self.fid, project_id=PROJECT)
        timestamps = [
            "2026-04-18T08:00:00+00:00",
            "2026-04-20T12:00:00+00:00",  # ← latest
            "2026-04-19T16:00:00+00:00",
        ]
        self.sids = []
        for ts in timestamps:
            sid = await seed_session(
                self.db, project_id=PROJECT,
                total_cost=1.0, observed_tokens=100,
                model_io_tokens=80, cache_input_tokens=20,
                started_at=ts,
            )
            self.sids.append(sid)
            await link_feature_session(self.db, self.fid, sid)
        self.expected_latest = "2026-04-20T12:00:00+00:00"
        await self.db.commit()

    async def test_parity_latest_session_at(self) -> None:
        sessions = await self._raw_sessions(self.sids)
        batch = await self.repo.get_feature_session_rollups(
            PROJECT,
            _q([self.fid], fields={"session_counts", "latest_activity"}),
        )
        e = batch.rollups[self.fid]

        legacy_latest = _legacy_latest_session_at(sessions)

        self.assertIsNotNone(e.latest_session_at)
        self.assertIsNotNone(legacy_latest)
        # parity-exception: rollup stores the raw DB string (may include timezone
        # offset or 'Z'); legacy used Python max() over the same DB column.
        # We normalise both to UTC epoch for comparison to tolerate ISO8601 variants.
        def _to_epoch(s: str) -> float:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()

        assert e.latest_session_at is not None
        assert legacy_latest is not None
        self.assertAlmostEqual(
            _to_epoch(e.latest_session_at),
            _to_epoch(legacy_latest),
            places=0,
            msg="latest_session_at epoch parity (timezone normalisation)",
        )


class TestParityBatchMultiFeature(_ParityBase):
    """Batch rollup for 3 features matches per-feature legacy derivation."""

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.features: dict[str, list[str]] = {}

        spec = {
            "F-A": {"n": 1, "cost": 2.0, "tokens": 200},
            "F-B": {"n": 3, "cost": 0.5, "tokens": 50},
            "F-C": {"n": 0, "cost": 0.0, "tokens": 0},
        }
        for fid, cfg in spec.items():
            await seed_feature(self.db, fid, project_id=PROJECT)
            sids = []
            for _ in range(cfg["n"]):
                sid = await seed_session(
                    self.db,
                    project_id=PROJECT,
                    total_cost=cfg["cost"],
                    observed_tokens=cfg["tokens"],
                    model_io_tokens=int(cfg["tokens"] * 0.8),
                    cache_input_tokens=int(cfg["tokens"] * 0.2),
                )
                sids.append(sid)
                await link_feature_session(self.db, fid, sid)
            self.features[fid] = sids
        await self.db.commit()

    async def test_parity_batch(self) -> None:
        fids = list(self.features.keys())
        batch = await self.repo.get_feature_session_rollups(PROJECT, _q(fids))

        for fid, sids in self.features.items():
            sessions = await self._raw_sessions(sids)
            e = batch.rollups[fid]

            self.assertEqual(
                e.session_count, _legacy_session_count(sessions),
                msg=f"{fid}: session_count",
            )
            self.assertAlmostEqual(
                e.total_cost or 0.0, _legacy_total_cost(sessions),
                places=5, msg=f"{fid}: total_cost",
            )
            self.assertEqual(
                e.observed_tokens or 0, _legacy_observed_tokens(sessions),
                msg=f"{fid}: observed_tokens",
            )

        # F-C has no sessions: must appear in rollups (not missing), with zero counts
        self.assertIn("F-C", batch.rollups)
        self.assertNotIn("F-C", batch.missing)
        self.assertEqual(batch.rollups["F-C"].session_count, 0)


class TestParityPrecisionField(_ParityBase):
    """Rollup precision is 'eventually_consistent' — legacy had no equivalent.

    parity-exception: the legacy linked-sessions route returned real-time data
    from the DB with no cache lag.  The new rollup marks precision as
    'eventually_consistent' because it may be served from a query cache.
    This is a documented contract change, not a data parity failure.
    """

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.fid = "F-PREC"
        await seed_feature(self.db, self.fid, project_id=PROJECT)
        sid = await seed_session(self.db, project_id=PROJECT, total_cost=1.0, observed_tokens=100,
                                 model_io_tokens=80, cache_input_tokens=20)
        await link_feature_session(self.db, self.fid, sid)
        await self.db.commit()

    async def test_precision_is_eventually_consistent(self) -> None:
        batch = await self.repo.get_feature_session_rollups(PROJECT, _q([self.fid]))
        e = batch.rollups[self.fid]
        # parity-exception: legacy route returned live data (no precision label).
        # New rollup always sets 'eventually_consistent' for session aggregates.
        self.assertEqual(e.precision, "eventually_consistent")


class TestParityMissingFeatureNotInRollups(_ParityBase):
    """Unknown feature IDs land in batch.missing, not batch.rollups.

    Legacy: the router would return 404.  New path: batch returns missing list.
    parity-exception: error semantics differ (404 vs graceful missing list).
    Both indicate "no data for this feature".
    """

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.known = "F-KNOWN"
        await seed_feature(self.db, self.known, project_id=PROJECT)
        await self.db.commit()

    async def test_missing_unknown_id(self) -> None:
        batch = await self.repo.get_feature_session_rollups(
            PROJECT, _q([self.known, "F-UNKNOWN"])
        )
        # parity-exception: legacy 404'd for unknown features; rollup returns missing list.
        self.assertIn("F-UNKNOWN", batch.missing)
        self.assertNotIn("F-UNKNOWN", batch.rollups)
        self.assertIn(self.known, batch.rollups)


if __name__ == "__main__":
    unittest.main()
