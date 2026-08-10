"""Tests for the provider dimension backfill job (M2-002).

``SqliteProviderDimensionsRepository.backfill_provider_dimensions_from_sessions``
derives ``provider_dimensions`` / ``provider_channels`` / ``provider_credentials``
rows from existing ``sessions`` rows (provider-channel-credential-entities-v1
milestone, SCHEMA_VERSION 52).

Covers the M2-002 acceptance criteria:
1. Idempotent: running the backfill twice against an unchanged ``sessions``
   table yields identical direct ``SELECT COUNT(*)`` row counts on every
   table, and the second run inserts nothing (verified via a fresh
   direct-count query per ADR-007, never trusting the method's own return
   value alone).
2. A NULL/empty ``ica_key`` produces no ``provider_credentials`` row and no
   error -- the common path, not an edge case.
3. An unrecognised/unknown ``providerChannel`` token does not raise and
   round-trips unchanged through ``provider_channels``.
4. A credential row for a non-ICA channel (e.g. "subscription") is
   creatable -- the table is not ICA-specific.
5. A secret-shaped ``ica_key`` is SKIPPED (counted, not raised) and never
   persisted; it does not abort the rest of the backfill pass.

Run as a named module (unscoped collection can hang this repo):
    backend/.venv/bin/python -m pytest backend/tests/test_provider_dimension_backfill.py -q -p no:cacheprovider
"""
from __future__ import annotations

import tempfile
import types
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite

from backend.db.repositories.provider_dimensions import SqliteProviderDimensionsRepository
from backend.db.repositories.sessions import SqliteSessionRepository
from backend.db.sqlite_migrations import run_migrations
from backend.model_identity import derive_provider_identity


class _BackfillTestBase(unittest.IsolatedAsyncioTestCase):
    """Real migrated SQLite, real upsert paths, real backfill."""

    async def asyncSetUp(self) -> None:
        self._tmpdir = Path(tempfile.mkdtemp())
        self.db = await aiosqlite.connect(str(self._tmpdir / "t.db"))
        self.db.row_factory = aiosqlite.Row
        # Independent SQLite connection MUST issue PRAGMA busy_timeout = 30000.
        await self.db.execute("PRAGMA busy_timeout = 30000")
        await run_migrations(self.db)
        self.session_repo = SqliteSessionRepository(self.db)
        self.repo = SqliteProviderDimensionsRepository(self.db)
        self.project_id = "proj1"

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def _count(self, table: str) -> int:
        cursor = await self.db.execute(f"SELECT COUNT(*) FROM {table}")
        (count,) = await cursor.fetchone()
        return int(count)

    async def _seed(self, session_id: str, **overrides) -> None:
        data = {
            "id": session_id,
            "taskId": "",
            "status": "completed",
            "model": "claude-sonnet-5",
            "platformType": "Claude Code",
            "startedAt": "2026-01-01T00:00:00Z",
            "endedAt": "2026-01-01T00:10:00Z",
        }
        data.update(overrides)
        await self.session_repo.upsert(data, self.project_id)


class BasicBackfillTests(_BackfillTestBase):
    async def test_ordinary_sessions_populate_all_three_tables(self) -> None:
        await self._seed(
            "s1",
            model="claude-sonnet-5",
            platformType="Claude Code",
            launcher="ica-claude.sh",
            icaKey="CC1",
        )

        stats = await self.repo.backfill_provider_dimensions_from_sessions(self.project_id)

        # Direct-count assertions (ADR-007) -- never trust the method's own
        # return value alone.
        self.assertEqual(await self._count("provider_dimensions"), 1)
        self.assertEqual(await self._count("provider_channels"), 1)
        self.assertEqual(await self._count("provider_credentials"), 1)

        self.assertEqual(stats["sessions_scanned"], 1)
        self.assertEqual(stats["providers_inserted"], 1)
        self.assertEqual(stats["channels_inserted"], 1)
        self.assertEqual(stats["credentials_inserted"], 1)
        self.assertEqual(stats["credentials_skipped_secret"], 0)

        identity = derive_provider_identity("claude-sonnet-5", "Claude Code", "ica-claude.sh", None)
        dimension = await self.repo.get_provider_dimension(identity["providerId"])
        self.assertIsNotNone(dimension)
        self.assertEqual(dimension["provider_vendor"], identity["providerVendor"])

        channel_row = await self.repo.get_provider_channel(identity["providerChannel"])
        self.assertIsNotNone(channel_row)

        credential_row = await self.repo.get_provider_credential(identity["providerChannel"], "CC1")
        self.assertIsNotNone(credential_row)
        self.assertEqual(credential_row["provider_id"], identity["providerId"])

    async def test_backfill_is_idempotent(self) -> None:
        """AC1: running twice yields identical row counts; second run inserts nothing."""
        await self._seed("s1", model="claude-sonnet-5", launcher="ica-claude.sh", icaKey="CC1")
        await self._seed("s2", model="gpt-5.6-terra", platformType="Codex", icaKey="CC2")
        await self._seed("s3", model="claude-opus-5")  # no ica_key at all

        first = await self.repo.backfill_provider_dimensions_from_sessions(self.project_id)
        counts_after_first = {
            "provider_dimensions": await self._count("provider_dimensions"),
            "provider_channels": await self._count("provider_channels"),
            "provider_credentials": await self._count("provider_credentials"),
        }

        second = await self.repo.backfill_provider_dimensions_from_sessions(self.project_id)
        counts_after_second = {
            "provider_dimensions": await self._count("provider_dimensions"),
            "provider_channels": await self._count("provider_channels"),
            "provider_credentials": await self._count("provider_credentials"),
        }

        # Identical direct row counts across both runs.
        self.assertEqual(counts_after_first, counts_after_second)
        self.assertGreater(counts_after_first["provider_dimensions"], 0)

        # The second run must insert nothing new.
        self.assertEqual(second["providers_inserted"], 0)
        self.assertEqual(second["channels_inserted"], 0)
        self.assertEqual(second["credentials_inserted"], 0)
        # First run did the actual inserting.
        self.assertGreater(first["providers_inserted"], 0)

    async def test_null_ica_key_produces_no_credential_row_and_no_error(self) -> None:
        """AC2: NULL ica_key is the common path -- no credential row, no error."""
        await self._seed("s1", model="claude-sonnet-5", icaKey=None)
        await self._seed("s2", model="claude-opus-5")  # also defaults to no icaKey

        stats = await self.repo.backfill_provider_dimensions_from_sessions(self.project_id)

        self.assertEqual(stats["sessions_scanned"], 2)
        self.assertEqual(stats["credentials_inserted"], 0)
        self.assertEqual(stats["credentials_skipped_secret"], 0)
        self.assertEqual(await self._count("provider_credentials"), 0)
        # Providers/channels still derive normally even with no ica_key.
        self.assertGreater(await self._count("provider_dimensions"), 0)
        self.assertGreater(await self._count("provider_channels"), 0)

    async def test_empty_string_ica_key_treated_as_absent(self) -> None:
        await self._seed("s1", model="claude-sonnet-5", icaKey="   ")

        stats = await self.repo.backfill_provider_dimensions_from_sessions(self.project_id)

        self.assertEqual(stats["credentials_inserted"], 0)
        self.assertEqual(await self._count("provider_credentials"), 0)

    async def test_unknown_channel_token_does_not_raise_and_round_trips(self) -> None:
        """AC3: an unrecognised channel is stored and read back unchanged."""
        # No launcher, no model_variant -> _provider_channel derives "unknown".
        await self._seed("s1", model="claude-sonnet-5", launcher=None, modelVariant=None)

        stats = await self.repo.backfill_provider_dimensions_from_sessions(self.project_id)

        self.assertEqual(stats["channels_inserted"], 1)
        channel_row = await self.repo.get_provider_channel("unknown")
        self.assertIsNotNone(channel_row)
        self.assertEqual(channel_row["channel"], "unknown")

    async def test_credential_row_for_non_ica_channel_is_creatable(self) -> None:
        """AC4: provider_credentials is not ICA-specific -- a subscription-channel
        credential name is creatable too."""
        await self._seed(
            "s1",
            model="claude-sonnet-5",
            launcher="claude-code-cli",  # -> "subscription" channel (Rule 1, no "ica"/"api" substring)
            icaKey="prod-api-key-name",
        )

        stats = await self.repo.backfill_provider_dimensions_from_sessions(self.project_id)

        identity = derive_provider_identity("claude-sonnet-5", "Claude Code", "claude-code-cli", None)
        self.assertEqual(identity["providerChannel"], "subscription")
        self.assertEqual(stats["credentials_inserted"], 1)
        credential_row = await self.repo.get_provider_credential("subscription", "prod-api-key-name")
        self.assertIsNotNone(credential_row)

    async def test_secret_shaped_ica_key_is_skipped_not_raised(self) -> None:
        """AC5: a poisoned row must not abort the pass, and must not be written."""
        await self._seed("good", model="claude-sonnet-5", icaKey="CC1")
        await self._seed(
            "poisoned",
            model="claude-opus-5",
            icaKey="sk-ant-abcdefghijklmnopqrstuvwxyz0123456789",  # secret-shaped
        )
        await self._seed("also_good", model="gpt-5.6-terra", platformType="Codex", icaKey="CC3")

        # Must not raise -- the whole pass completes despite the poisoned row.
        stats = await self.repo.backfill_provider_dimensions_from_sessions(self.project_id)

        self.assertEqual(stats["sessions_scanned"], 3)
        self.assertEqual(stats["credentials_skipped_secret"], 1)
        # Exactly the two good credentials landed; direct count confirms it.
        self.assertEqual(await self._count("provider_credentials"), 2)
        credential_names = {
            row["credential_name"] for row in await self.repo.list_provider_credentials()
        }
        self.assertNotIn("sk-ant-abcdefghijklmnopqrstuvwxyz0123456789", credential_names)
        self.assertIn("CC1", credential_names)
        self.assertIn("CC3", credential_names)

        # Providers/channels for the poisoned session's OWN row are still
        # derived normally -- only its credential is skipped.
        poisoned_identity = derive_provider_identity("claude-opus-5", "Claude Code", None, None)
        self.assertIsNotNone(await self.repo.get_provider_dimension(poisoned_identity["providerId"]))

        # Idempotent even with a poisoned row present: re-running is stable.
        second = await self.repo.backfill_provider_dimensions_from_sessions(self.project_id)
        self.assertEqual(second["credentials_inserted"], 0)
        self.assertEqual(second["credentials_skipped_secret"], 1)
        self.assertEqual(await self._count("provider_credentials"), 2)


# ── Fix 1 extension: providers/channels skip-on-poison (not just credentials) ──


class _PoisonedProviderRepo(SqliteProviderDimensionsRepository):
    """Test double: raises ``ValueError`` from ``upsert_provider_dimension``
    for one specific ``provider_id`` and from ``upsert_provider_channel`` for
    one specific ``channel``, delegating to the real implementation
    otherwise.

    Real derived ``provider_vendor``/``provider_surface``/``provider_label``
    values are drawn from a small closed enum (see
    ``backend/model_identity.py``'s ``_provider_vendor``/``_provider_surface``)
    and can never actually be secret-shaped through the normal backfill
    derivation path -- that is exactly why the backfill docstring calls a
    poisoned provider/channel row "should never happen by contract". This
    double exercises the ``providers_skipped_secret`` /
    ``channels_skipped_secret`` skip-and-continue mechanism directly at the
    seam that matters (the ``try/except ValueError`` in
    ``_run_provider_backfill``) without needing to fabricate a real
    secret-shaped derived value.
    """

    def __init__(
        self,
        db,
        *,
        poison_provider_id: str | None = None,
        poison_channel: str | None = None,
    ) -> None:
        super().__init__(db)
        self._poison_provider_id = poison_provider_id
        self._poison_channel = poison_channel

    async def upsert_provider_dimension(self, *, provider_id: str, **kwargs) -> None:
        if provider_id == self._poison_provider_id:
            raise ValueError("simulated secret-shaped provider_id (test double)")
        await super().upsert_provider_dimension(provider_id=provider_id, **kwargs)

    async def upsert_provider_channel(self, *, channel: str, **kwargs) -> None:
        if channel == self._poison_channel:
            raise ValueError("simulated secret-shaped label (test double)")
        await super().upsert_provider_channel(channel=channel, **kwargs)


class ProviderAndChannelSkipOnPoisonTests(_BackfillTestBase):
    async def test_poisoned_provider_id_is_skipped_not_raised(self) -> None:
        """A poisoned provider_dimensions row must not abort the pass; it is
        counted in providers_skipped_secret and never written."""
        await self._seed("s1", model="claude-sonnet-5", launcher="ica-claude.sh", icaKey="CC1")
        await self._seed("s2", model="gpt-5.6-terra", platformType="Codex", icaKey="CC2")

        good_identity = derive_provider_identity("claude-sonnet-5", "Claude Code", "ica-claude.sh", None)
        poisoned_identity = derive_provider_identity("gpt-5.6-terra", "Codex", None, None)

        repo = _PoisonedProviderRepo(
            self.db, poison_provider_id=poisoned_identity["providerId"]
        )

        # Must not raise -- the whole pass completes despite the poisoned provider row.
        stats = await repo.backfill_provider_dimensions_from_sessions(self.project_id)

        self.assertEqual(stats["sessions_scanned"], 2)
        self.assertEqual(stats["providers_skipped_secret"], 1)
        self.assertEqual(stats["providers_inserted"], 1)

        # The good provider landed; the poisoned one never did (direct count).
        self.assertIsNotNone(await repo.get_provider_dimension(good_identity["providerId"]))
        self.assertIsNone(await repo.get_provider_dimension(poisoned_identity["providerId"]))
        self.assertEqual(await self._count("provider_dimensions"), 1)

        # Channels for BOTH sessions still derive normally -- only the
        # poisoned row's provider_dimensions entry was skipped.
        self.assertGreaterEqual(await self._count("provider_channels"), 1)

    async def test_poisoned_channel_is_skipped_not_raised(self) -> None:
        """A poisoned provider_channels row must not abort the pass; it is
        counted in channels_skipped_secret and never written."""
        await self._seed("s1", model="claude-sonnet-5", launcher="ica-claude.sh", icaKey="CC1")
        await self._seed("s2", model="claude-opus-5", launcher=None, modelVariant=None)

        good_identity = derive_provider_identity("claude-sonnet-5", "Claude Code", "ica-claude.sh", None)
        poisoned_identity = derive_provider_identity("claude-opus-5", "Claude Code", None, None)

        repo = _PoisonedProviderRepo(
            self.db, poison_channel=poisoned_identity["providerChannel"]
        )

        stats = await repo.backfill_provider_dimensions_from_sessions(self.project_id)

        self.assertEqual(stats["sessions_scanned"], 2)
        self.assertEqual(stats["channels_skipped_secret"], 1)

        self.assertIsNotNone(await repo.get_provider_channel(good_identity["providerChannel"]))
        self.assertIsNone(await repo.get_provider_channel(poisoned_identity["providerChannel"]))

        # provider_dimensions rows for BOTH sessions still derive normally --
        # only the poisoned row's provider_channels entry was skipped.
        self.assertEqual(await self._count("provider_dimensions"), 2)


# ── sync-engine non-abort contract (provider backfill is optional enrichment) ──


def _make_project(project_id: str, name: str = "") -> types.SimpleNamespace:
    return types.SimpleNamespace(
        id=project_id,
        name=name or project_id,
        testConfig=types.SimpleNamespace(
            autoSyncOnStartup=False,
            maxFilesPerScan=25,
            maxParseConcurrency=4,
        ),
    )


@contextmanager
def _noop_span(*args, **kwargs):
    yield None


def _make_sync_engine_for_provider_backfill_test(*, raising_backfill: bool) -> "object":
    """Minimal SyncEngine, all phases mocked out except the assertion under
    test: whether a raising provider_dimensions_repo backfill aborts the
    surrounding sync pass (it must not -- see backend/db/sync_engine.py's
    provider-channel-credential-entities-v1 (M2) block)."""
    from backend.db.sync_engine import SyncEngine

    engine = SyncEngine.__new__(SyncEngine)
    engine._rglob_cache = {}
    engine._linking_logic_version = "1"
    engine._source_identity_policy = MagicMock()
    engine._sync_in_flight: set = set()

    engine.session_repo = MagicMock()
    engine.session_repo.backfill_skill_name_inheritance = AsyncMock(
        return_value={"rows": 0, "session_name_rows": 0}
    )
    engine.session_repo.backfill_ica_spend_attribution = AsyncMock(return_value={"rows": 0})

    if raising_backfill:
        engine.provider_dimensions_repo = MagicMock()
        engine.provider_dimensions_repo.backfill_provider_dimensions_from_sessions = AsyncMock(
            side_effect=RuntimeError("boom: simulated provider backfill failure")
        )
    else:
        engine.provider_dimensions_repo = MagicMock()
        engine.provider_dimensions_repo.backfill_provider_dimensions_from_sessions = AsyncMock(
            return_value={"providers_inserted": 3}
        )

    engine.document_repo = MagicMock()
    engine.task_repo = MagicMock()
    engine.feature_repo = MagicMock()
    engine.link_repo = MagicMock()
    engine.sync_repo = MagicMock()
    engine.session_message_repo = MagicMock()
    engine.session_intelligence_repo = MagicMock()
    engine.analytics_repo = MagicMock()
    engine.session_usage_repo = MagicMock()
    engine.telemetry_queue_repo = MagicMock()
    engine.pricing_catalog_repo = MagicMock()
    engine.pricing_catalog_service = MagicMock()
    engine.scan_manifest_repo = MagicMock()
    engine.tag_repo = MagicMock()
    engine.telemetry_transformer = MagicMock()
    engine._session_ingest_service = None
    engine._ops_lock = __import__("asyncio").Lock()
    engine._operations = {}
    engine._operation_order = []
    engine._active_operation_ids = set()
    engine._max_operation_history = 40
    engine._git_doc_dates_cache_key = ""
    engine._git_doc_dates_cache_index = {}
    engine._git_doc_dates_cache_dirty = set()
    engine._test_source_errors = {}
    engine._test_source_synced_at = {}

    engine._start_operation = AsyncMock(return_value="op-test-1")
    engine._update_operation = AsyncMock()
    engine._finish_operation = AsyncMock()

    engine._sync_sessions = AsyncMock(return_value={"synced": 1, "skipped": 0})
    engine._sync_documents = AsyncMock(return_value={"synced": 2, "skipped": 0})
    engine._sync_progress = AsyncMock(return_value={"synced": 3, "skipped": 0})
    engine._sync_features = AsyncMock(return_value={"synced": 4})
    engine._dispatch_link_rebuild = AsyncMock(return_value={"created": 5})
    engine.capture_analytics_snapshot = AsyncMock(return_value={})
    engine._maybe_backfill_session_usage_fields = AsyncMock(return_value={})
    engine._maybe_backfill_session_observability_fields = AsyncMock(return_value={})
    engine._maybe_backfill_session_usage_attribution = AsyncMock(return_value={})
    engine._maybe_backfill_telemetry_events = AsyncMock(return_value={})
    engine._maybe_backfill_commit_correlations = AsyncMock(return_value={})
    engine.rebuild_links = AsyncMock(return_value={"created": 0})
    engine._load_link_state = AsyncMock(return_value={})
    engine._save_link_state = AsyncMock()
    engine._capture_analytics = AsyncMock()

    return engine


class SyncEngineProviderBackfillNonAbortTests(unittest.IsolatedAsyncioTestCase):
    """A raising provider-dimension backfill must not abort the rest of the
    sync pass (documents/tasks/features/links still run), and the failure
    must be observable in the returned stats dict, never swallowed silently."""

    async def _run_sync(self, engine, project) -> dict:
        with (
            patch("backend.observability.start_span", side_effect=_noop_span),
            patch("backend.db.sync_engine.aclear_project_cache", new_callable=AsyncMock),
            patch("backend.db.sync_engine.publish_feature_invalidation", new_callable=AsyncMock),
            patch("backend.db.sync_engine.publish_planning_invalidation", new_callable=AsyncMock),
            patch("backend.db.sync_engine.config") as mock_cfg,
        ):
            mock_cfg.SYNC_COALESCING_ENABLED = False
            mock_cfg.STARTUP_SYNC_LIGHT_MODE = False
            mock_cfg.STARTUP_DEFERRED_REBUILD_LINKS = False
            mock_cfg.INCREMENTAL_LINK_REBUILD_ENABLED = True
            mock_cfg.SYNC_RECENT_FIRST_ENABLED = True
            mock_cfg.SYNC_RECENT_FIRST_N = 200

            return await engine.sync_project(
                project,
                Path("/tmp/sessions"),
                Path("/tmp/docs"),
                Path("/tmp/progress"),
                trigger="api",
            )

    async def test_raising_backfill_does_not_abort_sync_pass(self) -> None:
        engine = _make_sync_engine_for_provider_backfill_test(raising_backfill=True)
        project = _make_project("proj-provider-backfill-raises")

        result = await self._run_sync(engine, project)

        # The pass completed -- downstream phases still ran (not aborted).
        engine._sync_documents.assert_awaited_once()
        engine._sync_progress.assert_awaited_once()
        engine._sync_features.assert_awaited_once()
        self.assertEqual(result["documents_synced"], 2)
        self.assertEqual(result["tasks_synced"], 3)
        self.assertEqual(result["features_synced"], 4)

        # The failure is observable, not silently swallowed.
        self.assertEqual(result["provider_dimensions_backfilled"], 0)
        self.assertIn("boom: simulated provider backfill failure", result["provider_dimensions_backfill_error"])

        # _finish_operation was never called with status="failed" -- the
        # outer except-and-reraise path was never triggered by this failure.
        for call in engine._finish_operation.await_args_list:
            self.assertNotEqual(call.kwargs.get("status"), "failed")

    async def test_happy_path_backfill_stats_unaffected(self) -> None:
        engine = _make_sync_engine_for_provider_backfill_test(raising_backfill=False)
        project = _make_project("proj-provider-backfill-ok")

        result = await self._run_sync(engine, project)

        self.assertEqual(result["provider_dimensions_backfilled"], 3)
        self.assertEqual(result["provider_dimensions_backfill_error"], "")
        self.assertEqual(result["documents_synced"], 2)


if __name__ == "__main__":
    unittest.main()
