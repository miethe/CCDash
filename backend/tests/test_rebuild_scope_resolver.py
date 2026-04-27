"""Tests for BE-204: RebuildScope / _should_rebuild_links_after_full_sync.

TEST-505 — runtime-performance-hardening-v1 Phase 5.

Covers:
  - force=True → kind="full"
  - link-logic version change → kind="full"
  - one or more entity counters > 0 → kind="entities_changed"
  - no counters changed, version matches → kind="none"
  - edge: empty stats dict (all keys absent) → kind="none"
  - edge: exactly one counter == 1 (at-threshold) → kind="entities_changed"
  - RebuildScope.should_rebuild and .reason helpers
"""

import unittest

from backend.db.sync_engine import RebuildScope, SyncEngine


def _engine(version: str = "1") -> SyncEngine:
    """Return a minimal SyncEngine stub with _linking_logic_version set."""
    engine = SyncEngine.__new__(SyncEngine)
    engine._linking_logic_version = version
    return engine


_MATCHING_LINK_STATE = {"logicVersion": "1"}
_STALE_LINK_STATE = {"logicVersion": "0"}

_ZERO_STATS: dict = {
    "sessions_synced": 0,
    "documents_synced": 0,
    "tasks_synced": 0,
    "features_synced": 0,
    "commit_correlations_backfilled": 0,
}

_LARGE_STATS: dict = {
    "sessions_synced": 50,
    "documents_synced": 30,
    "tasks_synced": 20,
    "features_synced": 10,
    "commit_correlations_backfilled": 5,
}


class TestRebuildScopeDataclass(unittest.TestCase):
    """Unit tests for the RebuildScope value object."""

    def test_full_scope_should_rebuild_is_true(self) -> None:
        scope = RebuildScope(kind="full")
        self.assertTrue(scope.should_rebuild)

    def test_entities_changed_scope_should_rebuild_is_true(self) -> None:
        scope = RebuildScope(kind="entities_changed", entity_ids=[])
        self.assertTrue(scope.should_rebuild)

    def test_none_scope_should_rebuild_is_false(self) -> None:
        scope = RebuildScope(kind="none")
        self.assertFalse(scope.should_rebuild)

    def test_full_scope_reason_is_full(self) -> None:
        self.assertEqual(RebuildScope(kind="full").reason, "full")

    def test_entities_changed_scope_reason_is_entities_changed(self) -> None:
        self.assertEqual(RebuildScope(kind="entities_changed", entity_ids=[]).reason, "entities_changed")

    def test_none_scope_reason_is_up_to_date(self) -> None:
        self.assertEqual(RebuildScope(kind="none").reason, "up_to_date")


class TestScopeResolverForce(unittest.TestCase):
    """force=True always returns kind='full'."""

    def test_force_true_returns_full_even_when_stats_are_zero(self) -> None:
        engine = _engine("1")
        scope = engine._should_rebuild_links_after_full_sync(
            force=True,
            link_state=_MATCHING_LINK_STATE,
            stats=_ZERO_STATS,
        )
        self.assertEqual(scope.kind, "full")
        self.assertTrue(scope.should_rebuild)

    def test_force_true_returns_full_even_when_link_state_matches(self) -> None:
        engine = _engine("1")
        scope = engine._should_rebuild_links_after_full_sync(
            force=True,
            link_state=_MATCHING_LINK_STATE,
            stats=_ZERO_STATS,
        )
        self.assertEqual(scope.kind, "full")


class TestScopeResolverVersionChange(unittest.TestCase):
    """Stale link-logic version → kind='full'."""

    def test_version_change_returns_full_scope(self) -> None:
        engine = _engine("2")  # engine is at v2, DB state records v0/v1
        scope = engine._should_rebuild_links_after_full_sync(
            force=False,
            link_state=_STALE_LINK_STATE,
            stats=_ZERO_STATS,
        )
        self.assertEqual(scope.kind, "full")
        self.assertTrue(scope.should_rebuild)
        self.assertEqual(scope.reason, "full")


class TestScopeResolverEntitiesChanged(unittest.TestCase):
    """One or more entity counters > 0 → kind='entities_changed'."""

    def test_large_entity_change_set_returns_entities_changed(self) -> None:
        engine = _engine("1")
        scope = engine._should_rebuild_links_after_full_sync(
            force=False,
            link_state=_MATCHING_LINK_STATE,
            stats=_LARGE_STATS,
        )
        self.assertEqual(scope.kind, "entities_changed")
        self.assertTrue(scope.should_rebuild)
        self.assertIsNotNone(scope.entity_ids)

    def test_only_sessions_changed_returns_entities_changed(self) -> None:
        engine = _engine("1")
        stats = {**_ZERO_STATS, "sessions_synced": 3}
        scope = engine._should_rebuild_links_after_full_sync(
            force=False,
            link_state=_MATCHING_LINK_STATE,
            stats=stats,
        )
        self.assertEqual(scope.kind, "entities_changed")

    def test_only_documents_changed_returns_entities_changed(self) -> None:
        engine = _engine("1")
        stats = {**_ZERO_STATS, "documents_synced": 5}
        scope = engine._should_rebuild_links_after_full_sync(
            force=False,
            link_state=_MATCHING_LINK_STATE,
            stats=stats,
        )
        self.assertEqual(scope.kind, "entities_changed")

    def test_only_commit_correlations_changed_returns_entities_changed(self) -> None:
        engine = _engine("1")
        stats = {**_ZERO_STATS, "commit_correlations_backfilled": 2}
        scope = engine._should_rebuild_links_after_full_sync(
            force=False,
            link_state=_MATCHING_LINK_STATE,
            stats=stats,
        )
        self.assertEqual(scope.kind, "entities_changed")


class TestScopeResolverNoChange(unittest.TestCase):
    """All counters zero, version matches → kind='none'."""

    def test_no_change_sync_returns_none(self) -> None:
        engine = _engine("1")
        scope = engine._should_rebuild_links_after_full_sync(
            force=False,
            link_state=_MATCHING_LINK_STATE,
            stats=_ZERO_STATS,
        )
        self.assertEqual(scope.kind, "none")
        self.assertFalse(scope.should_rebuild)
        self.assertEqual(scope.reason, "up_to_date")


class TestScopeResolverEdgeCases(unittest.TestCase):
    """Edge cases: empty input, exactly-at-threshold."""

    def test_empty_stats_dict_returns_none(self) -> None:
        """All counter keys absent — defaults to 0 via stats.get(key, 0) → none."""
        engine = _engine("1")
        scope = engine._should_rebuild_links_after_full_sync(
            force=False,
            link_state=_MATCHING_LINK_STATE,
            stats={},
        )
        self.assertEqual(scope.kind, "none")
        self.assertFalse(scope.should_rebuild)

    def test_exactly_one_counter_at_one_is_at_threshold(self) -> None:
        """A single counter == 1 (minimum to trigger entities_changed)."""
        engine = _engine("1")
        stats = {**_ZERO_STATS, "tasks_synced": 1}
        scope = engine._should_rebuild_links_after_full_sync(
            force=False,
            link_state=_MATCHING_LINK_STATE,
            stats=stats,
        )
        self.assertEqual(scope.kind, "entities_changed")

    def test_all_counters_at_zero_is_below_threshold(self) -> None:
        """All counters == 0 — one below the threshold of 1 → none."""
        engine = _engine("1")
        scope = engine._should_rebuild_links_after_full_sync(
            force=False,
            link_state=_MATCHING_LINK_STATE,
            stats=_ZERO_STATS,
        )
        self.assertEqual(scope.kind, "none")

    def test_empty_link_state_dict_treated_as_version_mismatch(self) -> None:
        """link_state with no logicVersion key → version appears missing/None → treated as stale."""
        engine = _engine("1")
        scope = engine._should_rebuild_links_after_full_sync(
            force=False,
            link_state={},
            stats=_ZERO_STATS,
        )
        # Missing version ≠ current version → full rebuild.
        self.assertEqual(scope.kind, "full")


if __name__ == "__main__":
    unittest.main()
