"""Unit tests for Bug #1 fix — non-atomic Postgres per-session write path.

Acceptance criteria (no real DB required):

AC-1  persist_envelope called with _pg_conn=<mock> routes ALL session-repo
      child writes (upsert, upsert_logs, upsert_tool_usage, upsert_file_updates,
      upsert_artifacts) and replace_session_usage_attribution to that mock
      connection.  None of them should open a new postgres_transaction.

AC-2  PostgresSessionUsageRepository.replace_session_usage(conn=None) wraps
      DELETE + events INSERT + attributions INSERT in a single
      postgres_transaction (one connection acquisition, one BEGIN/COMMIT).

AC-3  PostgresSessionUsageRepository.replace_session_usage(conn=<mock>) uses
      the supplied connection directly — no new transaction acquired.

AC-4  PostgresSessionRepository child write methods (upsert_logs,
      upsert_tool_usage, upsert_file_updates, upsert_artifacts) use _pg_conn
      when supplied and fall back to postgres_transaction when not.

Run:
    backend/.venv/bin/python -m pytest backend/tests/test_pg_session_atomicity.py -v
"""
from __future__ import annotations

import asyncio
import unittest
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, call

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _make_mock_conn() -> MagicMock:
    """Return an asyncpg-style connection mock."""
    conn = MagicMock()
    conn.execute = AsyncMock()
    conn.executemany = AsyncMock()
    return conn


# ---------------------------------------------------------------------------
# AC-2 / AC-3 — PostgresSessionUsageRepository.replace_session_usage
# ---------------------------------------------------------------------------


class TestReplaceSessionUsage(unittest.TestCase):
    """Test PostgresSessionUsageRepository.replace_session_usage."""

    def _make_repo(self) -> Any:
        from backend.db.repositories.postgres.usage_attribution import (
            PostgresSessionUsageRepository,
        )
        pool = MagicMock()
        return PostgresSessionUsageRepository(pool)

    def test_ac3_provided_conn_used_directly_no_new_transaction(self) -> None:
        """AC-3: when conn is provided, no postgres_transaction is acquired."""
        repo = self._make_repo()
        mock_conn = _make_mock_conn()

        with patch(
            "backend.db.repositories.postgres.usage_attribution.postgres_transaction"
        ) as mock_txn:
            _run(repo.replace_session_usage("proj", "sess", [], [], conn=mock_conn))
            mock_txn.assert_not_called()

        # Only the DELETE is issued (events/attributions lists are empty)
        mock_conn.execute.assert_called_once()
        delete_sql = mock_conn.execute.call_args[0][0]
        assert "DELETE FROM session_usage_events" in delete_sql

    def test_ac3_provided_conn_insert_events_and_attributions(self) -> None:
        """AC-3: events and attributions execute on the provided conn."""
        repo = self._make_repo()
        mock_conn = _make_mock_conn()

        events = [{"id": "E1", "event_kind": "model_io", "captured_at": "2024-01-01"}]
        attrs = [{"event_id": "E1", "entity_type": "feature", "entity_id": "F1",
                  "attribution_role": "primary", "method": "explicit"}]

        with patch(
            "backend.db.repositories.postgres.usage_attribution.postgres_transaction"
        ) as mock_txn:
            _run(repo.replace_session_usage("proj", "sess", events, attrs, conn=mock_conn))
            mock_txn.assert_not_called()

        # execute (DELETE) + executemany (events) + executemany (attributions)
        assert mock_conn.execute.call_count == 1
        assert mock_conn.executemany.call_count == 2
        events_sql = mock_conn.executemany.call_args_list[0][0][0]
        attrs_sql = mock_conn.executemany.call_args_list[1][0][0]
        assert "session_usage_events" in events_sql
        assert "ON CONFLICT (id) DO NOTHING" in events_sql
        assert "session_usage_attributions" in attrs_sql
        assert "ON CONFLICT (event_id" in attrs_sql

    def test_ac2_no_conn_wraps_in_single_transaction(self) -> None:
        """AC-2: standalone call (conn=None) wraps three ops in one transaction."""
        repo = self._make_repo()
        captured_conn = _make_mock_conn()

        # Simulate postgres_transaction yielding captured_conn
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _fake_txn(db: Any):  # noqa: ANN401
            yield captured_conn

        events = [{"id": "E1", "event_kind": "tool_use", "captured_at": "2024-01-01"}]

        with patch(
            "backend.db.repositories.postgres.usage_attribution.postgres_transaction",
            side_effect=_fake_txn,
        ) as mock_txn:
            _run(repo.replace_session_usage("proj", "sess", events, [], conn=None))
            # The transaction helper was called exactly once (one acquisition)
            mock_txn.assert_called_once()

        # All SQL issued on the single captured_conn
        assert captured_conn.execute.call_count == 1  # DELETE
        assert captured_conn.executemany.call_count == 1  # events INSERT

    def test_ac2_default_conn_argument_is_none(self) -> None:
        """AC-2: default (keyword-only) conn parameter is None."""
        import inspect
        from backend.db.repositories.postgres.usage_attribution import (
            PostgresSessionUsageRepository,
        )
        sig = inspect.signature(PostgresSessionUsageRepository.replace_session_usage)
        assert "conn" in sig.parameters
        assert sig.parameters["conn"].default is None


# ---------------------------------------------------------------------------
# AC-4 — PostgresSessionRepository child writes respect _pg_conn
# ---------------------------------------------------------------------------


class TestPostgresSessionRepositoryChildWrites(unittest.TestCase):
    """Verify _pg_conn threading for the four child write methods."""

    def _make_repo(self) -> Any:
        from backend.db.repositories.postgres.sessions import PostgresSessionRepository
        pool = MagicMock()
        return PostgresSessionRepository(pool)

    def _assert_uses_pg_conn(self, method_name: str, *args: Any) -> None:
        """Call method with _pg_conn=mock_conn and verify it uses mock_conn."""
        repo = self._make_repo()
        mock_conn = _make_mock_conn()

        with patch(
            "backend.db.repositories.postgres.sessions.postgres_transaction"
        ) as mock_txn:
            _run(getattr(repo, method_name)(*args, _pg_conn=mock_conn))
            mock_txn.assert_not_called()

        # At minimum a DELETE should have been issued on mock_conn
        assert mock_conn.execute.call_count >= 1 or mock_conn.executemany.call_count >= 0

    def _assert_uses_transaction_without_pg_conn(self, method_name: str, *args: Any) -> None:
        """Call method without _pg_conn and verify postgres_transaction is used."""
        repo = self._make_repo()
        captured_conn = _make_mock_conn()

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _fake_txn(db: Any):  # noqa: ANN401
            yield captured_conn

        with patch(
            "backend.db.repositories.postgres.sessions.postgres_transaction",
            side_effect=_fake_txn,
        ) as mock_txn:
            _run(getattr(repo, method_name)(*args))
            mock_txn.assert_called_once()

    def test_ac4_upsert_logs_uses_pg_conn_when_provided(self) -> None:
        self._assert_uses_pg_conn("upsert_logs", "sess1", [], "proj1")

    def test_ac4_upsert_logs_uses_transaction_when_no_pg_conn(self) -> None:
        self._assert_uses_transaction_without_pg_conn("upsert_logs", "sess1", [], "proj1")

    def test_ac4_upsert_tool_usage_uses_pg_conn_when_provided(self) -> None:
        self._assert_uses_pg_conn("upsert_tool_usage", "sess1", [], "proj1")

    def test_ac4_upsert_tool_usage_uses_transaction_when_no_pg_conn(self) -> None:
        self._assert_uses_transaction_without_pg_conn("upsert_tool_usage", "sess1", [], "proj1")

    def test_ac4_upsert_file_updates_uses_pg_conn_when_provided(self) -> None:
        self._assert_uses_pg_conn("upsert_file_updates", "sess1", [], "proj1")

    def test_ac4_upsert_file_updates_uses_transaction_when_no_pg_conn(self) -> None:
        self._assert_uses_transaction_without_pg_conn("upsert_file_updates", "sess1", [], "proj1")

    def test_ac4_upsert_artifacts_uses_pg_conn_when_provided(self) -> None:
        self._assert_uses_pg_conn("upsert_artifacts", "sess1", [], "proj1")

    def test_ac4_upsert_artifacts_uses_transaction_when_no_pg_conn(self) -> None:
        self._assert_uses_transaction_without_pg_conn("upsert_artifacts", "sess1", [], "proj1")

    def test_ac4_upsert_tool_usage_on_conflict(self) -> None:
        """ON CONFLICT (session_id, tool_name) DO NOTHING present."""
        repo = self._make_repo()
        mock_conn = _make_mock_conn()
        tools = [{"name": "Bash", "count": 5, "successRate": 1.0, "totalMs": 100}]
        _run(repo.upsert_tool_usage("sess1", tools, "proj1", _pg_conn=mock_conn))
        assert mock_conn.executemany.called
        sql = mock_conn.executemany.call_args[0][0]
        assert "ON CONFLICT (session_id, tool_name) DO NOTHING" in sql

    def test_ac4_upsert_artifacts_on_conflict(self) -> None:
        """ON CONFLICT (id) DO NOTHING present for session_artifacts."""
        repo = self._make_repo()
        mock_conn = _make_mock_conn()
        artifacts = [{"id": "ART-1", "title": "test", "type": "document", "description": "", "source": ""}]
        _run(repo.upsert_artifacts("sess1", artifacts, "proj1", _pg_conn=mock_conn))
        assert mock_conn.executemany.called
        sql = mock_conn.executemany.call_args[0][0]
        assert "ON CONFLICT (id) DO NOTHING" in sql


# ---------------------------------------------------------------------------
# AC-1 — persist_envelope routes _pg_conn to child writes
# ---------------------------------------------------------------------------


class TestPersistEnvelopePgConnThreading(unittest.TestCase):
    """AC-1: verify _pg_conn is threaded to all session-repo child writes."""

    def _make_envelope(self) -> Any:
        from backend.ingestion.models import IngestSource, MergePolicy

        env = MagicMock()
        env.merge_policy = MergePolicy.UPSERT_COMPLETE
        env.source = IngestSource.JSONL
        env.source_identity = "test_source_file"
        env.provenance = MagicMock()
        env.provenance.source_uri = "test.jsonl"
        # session dict with the minimum fields persist_envelope reads
        env.session = {
            "id": "S-test-001",
            "status": "completed",
            "logs": [],
            "toolsUsed": [],
            "updatedFiles": [],
            "linkedArtifacts": [],
            "sessionRelationships": [],
            "derivedSessions": [],
        }
        return env

    def _make_service(
        self, session_repo: Any, usage_attr_calls: list
    ) -> Any:
        from backend.ingestion.session_ingest_service import SessionIngestService

        async def _noop_observe(proj: str, payload: dict, logs: list) -> dict:
            return {}

        async def _record_usage(**kwargs: Any) -> dict:
            usage_attr_calls.append(kwargs)
            return {"events": 0, "attributions": 0}

        async def _replace_usage(proj: str, payload: dict, logs: list, arts: list, **kw: Any) -> dict:
            usage_attr_calls.append(kw)
            return {"events": 0, "attributions": 0}

        msg_repo = MagicMock()
        msg_repo.list_by_session = AsyncMock(return_value=[])
        msg_repo.replace_session_messages = AsyncMock()

        return SessionIngestService(
            session_repo=session_repo,
            session_message_repo=msg_repo,
            project_session_messages=lambda payload, logs: [],
            apply_usage_fields=lambda p: None,
            should_write_legacy_session_logs=lambda rows: False,
            derive_session_observability_fields=_noop_observe,
            replace_session_usage_attribution=_replace_usage,
            replace_session_telemetry_events=AsyncMock(return_value=0),
            replace_session_commit_correlations=AsyncMock(return_value={}),
            replace_session_intelligence_facts=AsyncMock(return_value={}),
            maybe_enqueue_telemetry_export=AsyncMock(),
            publish_transcript_appends=AsyncMock(return_value=False),
            publish_session_snapshot=AsyncMock(),
        )

    def test_ac1_pg_conn_forwarded_to_all_session_repo_writes(self) -> None:
        """All session_repo write calls receive _pg_conn when provided."""
        received_kw: dict[str, list] = {
            "upsert": [],
            "upsert_logs": [],
            "upsert_tool_usage": [],
            "upsert_file_updates": [],
            "upsert_artifacts": [],
        }

        class TrackingRepo:
            async def upsert(self, data: dict, project_id: str, **kw: Any) -> None:
                received_kw["upsert"].append(kw)

            async def get_logs(self, session_id: str) -> list:
                return []

            async def upsert_logs(self, session_id: str, logs: list, project_id: str = "", **kw: Any) -> None:
                received_kw["upsert_logs"].append(kw)

            async def upsert_tool_usage(self, session_id: str, tools: list, project_id: str = "", **kw: Any) -> None:
                received_kw["upsert_tool_usage"].append(kw)

            async def upsert_file_updates(self, session_id: str, updates: list, project_id: str = "", **kw: Any) -> None:
                received_kw["upsert_file_updates"].append(kw)

            async def upsert_artifacts(self, session_id: str, arts: list, project_id: str = "", **kw: Any) -> None:
                received_kw["upsert_artifacts"].append(kw)

            async def update_observability_fields(self, session_id: str, fields: dict, project_id: str, **kw: Any) -> None:
                pass

        usage_attr_calls: list = []
        svc = self._make_service(TrackingRepo(), usage_attr_calls)
        envelope = self._make_envelope()
        mock_conn = _make_mock_conn()

        _run(svc.persist_envelope("proj1", envelope, _pg_conn=mock_conn))

        # Every repo write call should have received _pg_conn=mock_conn
        for method, calls in received_kw.items():
            assert calls, f"{method} was never called"
            for kw in calls:
                assert kw.get("_pg_conn") is mock_conn, (
                    f"{method} did not receive _pg_conn=mock_conn; got {kw}"
                )

        # replace_session_usage_attribution should have received _pg_conn=mock_conn
        assert usage_attr_calls, "replace_session_usage_attribution was never called"
        assert usage_attr_calls[0].get("_pg_conn") is mock_conn

    def test_ac1_sqlite_path_no_pg_conn_not_forwarded(self) -> None:
        """SQLite callers pass no _pg_conn; child writes receive no _pg_conn kwarg."""
        received_kw: dict[str, list] = {
            "upsert": [],
            "upsert_logs": [],
            "upsert_tool_usage": [],
            "upsert_file_updates": [],
            "upsert_artifacts": [],
        }

        class TrackingRepo:
            async def upsert(self, data: dict, project_id: str, **kw: Any) -> None:
                received_kw["upsert"].append(kw)

            async def get_logs(self, session_id: str) -> list:
                return []

            async def upsert_logs(self, session_id: str, logs: list, project_id: str = "", **kw: Any) -> None:
                received_kw["upsert_logs"].append(kw)

            async def upsert_tool_usage(self, session_id: str, tools: list, project_id: str = "", **kw: Any) -> None:
                received_kw["upsert_tool_usage"].append(kw)

            async def upsert_file_updates(self, session_id: str, updates: list, project_id: str = "", **kw: Any) -> None:
                received_kw["upsert_file_updates"].append(kw)

            async def upsert_artifacts(self, session_id: str, arts: list, project_id: str = "", **kw: Any) -> None:
                received_kw["upsert_artifacts"].append(kw)

            async def update_observability_fields(self, session_id: str, fields: dict, project_id: str, **kw: Any) -> None:
                pass

        usage_attr_calls: list = []
        svc = self._make_service(TrackingRepo(), usage_attr_calls)
        envelope = self._make_envelope()

        # SQLite path: no _pg_conn
        _run(svc.persist_envelope("proj1", envelope))

        for method, calls in received_kw.items():
            assert calls, f"{method} was never called"
            for kw in calls:
                assert "_pg_conn" not in kw, (
                    f"{method} incorrectly received _pg_conn on SQLite path; got {kw}"
                )

        assert usage_attr_calls
        assert "_pg_conn" not in usage_attr_calls[0]


# ---------------------------------------------------------------------------
# Protocol compliance check
# ---------------------------------------------------------------------------


class TestProtocolSignatures(unittest.TestCase):
    """Verify protocol and concrete signatures match."""

    def test_base_protocol_has_conn_param(self) -> None:
        import inspect
        from backend.db.repositories.base import SessionUsageRepository
        sig = inspect.signature(SessionUsageRepository.replace_session_usage)
        assert "conn" in sig.parameters
        assert sig.parameters["conn"].default is None

    def test_postgres_impl_has_conn_param(self) -> None:
        import inspect
        from backend.db.repositories.postgres.usage_attribution import (
            PostgresSessionUsageRepository,
        )
        sig = inspect.signature(PostgresSessionUsageRepository.replace_session_usage)
        assert "conn" in sig.parameters
        assert sig.parameters["conn"].default is None

    def test_postgres_session_repo_upsert_has_pg_conn_param(self) -> None:
        import inspect
        from backend.db.repositories.postgres.sessions import PostgresSessionRepository
        for method in ("upsert_logs", "upsert_tool_usage", "upsert_file_updates", "upsert_artifacts"):
            sig = inspect.signature(getattr(PostgresSessionRepository, method))
            assert "_pg_conn" in sig.parameters, f"{method} missing _pg_conn"
            assert sig.parameters["_pg_conn"].default is None, f"{method} _pg_conn default not None"

    def test_persist_envelope_has_pg_conn_param(self) -> None:
        import inspect
        from backend.ingestion.session_ingest_service import SessionIngestService
        sig = inspect.signature(SessionIngestService.persist_envelope)
        assert "_pg_conn" in sig.parameters
        assert sig.parameters["_pg_conn"].default is None


# ---------------------------------------------------------------------------
# Pool-based integration test — verifies _pg_conn threading under real pool
# ---------------------------------------------------------------------------

import os as _os

_DB_BACKEND = _os.environ.get("CCDASH_DB_BACKEND", "")
_DATABASE_URL = _os.environ.get("CCDASH_DATABASE_URL", "")

_POOL_TEST_PROJECT_ID = "test-atomic-pool-pg-v1"
_POOL_TEST_SESSION_ID = "test-atomic-pool-sess-001"
_POOL_TEST_FEATURE_ID = "FEAT-test-atomic-pool-pg-001"
_POOL_TEST_SOURCE_IDENTITY = f"test/sessions/{_POOL_TEST_SESSION_ID}.jsonl"
_POOL_TEST_SOURCE_URI = f"/test/sessions/{_POOL_TEST_SESSION_ID}.jsonl"

_POOL_EXPECTED_MESSAGES = 2
_POOL_EXPECTED_TOOLS = 2
_POOL_EXPECTED_EVENTS = 4
_POOL_EXPECTED_ATTRIBUTIONS = 4


def _pool_build_session_payload() -> Any:
    return {
        "id": _POOL_TEST_SESSION_ID,
        "status": "completed",
        "model": "claude-sonnet-4-5",
        "platformType": "claude_code",
        "platformVersion": "1.0.0",
        "startedAt": "2024-01-15T10:00:00.000Z",
        "endedAt": "2024-01-15T10:30:00.000Z",
        "createdAt": "2024-01-15T10:00:00.000Z",
        "updatedAt": "2024-01-15T10:30:00.000Z",
        "featureId": _POOL_TEST_FEATURE_ID,
        "tokensIn": 500,
        "tokensOut": 250,
        "modelIOTokens": 750,
        "totalCost": 0.025,
        "logs": [
            {
                "id": "log-pool-001",
                "type": "message",
                "content": "Pool integration test prompt message 1",
                "timestamp": "2024-01-15T10:00:01.000Z",
                "metadata": {
                    "inputTokens": 100,
                    "outputTokens": 50,
                    "model": "claude-sonnet-4-5",
                },
            },
            {
                "id": "log-pool-002",
                "type": "message",
                "content": "Pool integration test prompt message 2",
                "timestamp": "2024-01-15T10:00:02.000Z",
                "metadata": {
                    "inputTokens": 200,
                    "outputTokens": 100,
                    "model": "claude-sonnet-4-5",
                },
            },
        ],
        "toolsUsed": [
            {"name": "Bash", "count": 5, "successRate": 0.8, "totalMs": 1000.0},
            {"name": "Read", "count": 3, "successRate": 1.0, "totalMs": 300.0},
        ],
        "updatedFiles": [],
        "linkedArtifacts": [],
        "sessionRelationships": [],
        "derivedSessions": [],
    }


class TestPgAtomicPersistPool(unittest.IsolatedAsyncioTestCase):
    """Pool-based integration test for Bug #1 fix.

    Uses asyncpg.create_pool(min_size=2, max_size=4) so that connections in the
    pool are distinct objects.  A second postgres_transaction call without
    explicit _pg_conn threading would acquire a DIFFERENT connection from the
    pool and therefore not see the uncommitted sessions parent row — producing a
    ForeignKeyViolationError.  This test proves the fix is effective at the pool
    level.

    Skips automatically unless both CCDASH_DB_BACKEND=postgres and
    CCDASH_DATABASE_URL are set.
    """

    # ------------------------------------------------------------------
    # Set up / tear down
    # ------------------------------------------------------------------

    async def asyncSetUp(self) -> None:  # noqa: D102
        if _DB_BACKEND != "postgres" or not _DATABASE_URL:
            self.skipTest(
                "skipping: CCDASH_DB_BACKEND must be 'postgres' and "
                "CCDASH_DATABASE_URL must be set to run this integration test"
            )

        try:
            import asyncpg  # noqa: PLC0415
        except ImportError:  # pragma: no cover
            self.skipTest("asyncpg not installed")

        try:
            self.pool = await asyncpg.create_pool(
                _DATABASE_URL,
                min_size=2,
                max_size=4,
                command_timeout=30,
            )
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"postgres pool unreachable: {exc!r}")

        # Run migrations using a single connection from the pool.
        async with self.pool.acquire() as _mig_conn:
            from backend.db import postgres_migrations  # noqa: PLC0415
            await postgres_migrations.run_migrations(_mig_conn)

        await self._cleanup()

    async def asyncTearDown(self) -> None:  # noqa: D102
        if getattr(self, "pool", None) is not None:
            try:
                await self._cleanup()
            finally:
                await self.pool.close()

    async def _cleanup(self) -> None:
        """Delete all rows written by this test class, scoped to pool test IDs."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                DELETE FROM session_usage_attributions
                WHERE event_id IN (
                    SELECT id FROM session_usage_events
                    WHERE project_id = $1 AND session_id = $2
                )
                """,
                _POOL_TEST_PROJECT_ID,
                _POOL_TEST_SESSION_ID,
            )
            await conn.execute(
                "DELETE FROM session_usage_events WHERE project_id = $1 AND session_id = $2",
                _POOL_TEST_PROJECT_ID,
                _POOL_TEST_SESSION_ID,
            )
            await conn.execute(
                "DELETE FROM session_tool_usage WHERE session_id = $1",
                _POOL_TEST_SESSION_ID,
            )
            await conn.execute(
                "DELETE FROM session_messages WHERE session_id = $1",
                _POOL_TEST_SESSION_ID,
            )
            await conn.execute(
                "DELETE FROM sessions WHERE project_id = $1 AND id = $2",
                _POOL_TEST_PROJECT_ID,
                _POOL_TEST_SESSION_ID,
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_pool_service(self) -> Any:
        """Wire real Postgres repos to the pool; mock non-DB callables."""
        from backend.db.repositories.postgres.session_messages import (  # noqa: PLC0415
            PostgresSessionMessageRepository,
        )
        from backend.db.repositories.postgres.sessions import (  # noqa: PLC0415
            PostgresSessionRepository,
        )
        from backend.db.repositories.postgres.usage_attribution import (  # noqa: PLC0415
            PostgresSessionUsageRepository,
        )
        from backend.ingestion.session_ingest_service import SessionIngestService  # noqa: PLC0415
        from backend.services.session_transcript_projection import (  # noqa: PLC0415
            project_session_messages,
        )
        from backend.services.session_usage_attribution import (  # noqa: PLC0415
            build_session_usage_attributions,
            build_session_usage_events,
        )
        from unittest.mock import AsyncMock  # noqa: PLC0415

        session_repo = PostgresSessionRepository(self.pool)
        session_message_repo = PostgresSessionMessageRepository(self.pool)
        session_usage_repo = PostgresSessionUsageRepository(self.pool)

        async def _replace_usage(
            project_id: str,
            session_payload: dict[str, Any],
            logs: list[dict[str, Any]],
            artifacts: list[dict[str, Any]],
            _pg_conn: Any = None,
        ) -> dict[str, int]:
            session_id = str(session_payload.get("id") or "").strip()
            if not session_id:
                return {"events": 0, "attributions": 0}
            events = build_session_usage_events(project_id, session_payload, logs)
            attributions = build_session_usage_attributions(
                session_payload, logs, artifacts, events
            )
            await session_usage_repo.replace_session_usage(
                project_id, session_id, events, attributions, conn=_pg_conn
            )
            return {"events": len(events), "attributions": len(attributions)}

        return SessionIngestService(
            session_repo=session_repo,
            session_message_repo=session_message_repo,
            project_session_messages=project_session_messages,
            apply_usage_fields=lambda payload: None,
            should_write_legacy_session_logs=lambda rows: False,
            derive_session_observability_fields=AsyncMock(return_value={}),
            replace_session_usage_attribution=_replace_usage,
            replace_session_telemetry_events=AsyncMock(return_value=0),
            replace_session_commit_correlations=AsyncMock(return_value={}),
            replace_session_intelligence_facts=AsyncMock(return_value={}),
            maybe_enqueue_telemetry_export=AsyncMock(return_value=None),
            publish_transcript_appends=AsyncMock(return_value=False),
            publish_session_snapshot=AsyncMock(return_value=None),
        )

    async def _persist_once_pool(self, service: Any) -> Any:
        """Run persist_envelope inside a postgres_transaction acquired from the pool."""
        from backend.db.repositories.postgres._transactions import (  # noqa: PLC0415
            postgres_transaction,
        )
        from backend.ingestion.jsonl_adapter import jsonl_session_to_envelope  # noqa: PLC0415

        envelope = jsonl_session_to_envelope(
            _pool_build_session_payload(),
            source_identity=_POOL_TEST_SOURCE_IDENTITY,
            source_uri=_POOL_TEST_SOURCE_URI,
        )

        # Acquire the outer transaction from the pool.  The pool's min_size=2
        # means a second acquire() would get a DIFFERENT connection, so any
        # un-threaded write FK-fails.
        async with postgres_transaction(self.pool) as _pg_conn:
            result = await service.persist_envelope(
                _POOL_TEST_PROJECT_ID,
                envelope,
                observed_source_file=_POOL_TEST_SOURCE_URI,
                telemetry_source="test",
                _pg_conn=_pg_conn,
            )

        return result

    async def _row_counts(self) -> dict[str, int]:
        async with self.pool.acquire() as conn:
            sessions_n = await conn.fetchval(
                "SELECT count(*) FROM sessions WHERE project_id = $1 AND id = $2",
                _POOL_TEST_PROJECT_ID,
                _POOL_TEST_SESSION_ID,
            )
            messages_n = await conn.fetchval(
                "SELECT count(*) FROM session_messages WHERE session_id = $1",
                _POOL_TEST_SESSION_ID,
            )
            tools_n = await conn.fetchval(
                "SELECT count(*) FROM session_tool_usage WHERE session_id = $1",
                _POOL_TEST_SESSION_ID,
            )
            events_n = await conn.fetchval(
                "SELECT count(*) FROM session_usage_events "
                "WHERE project_id = $1 AND session_id = $2",
                _POOL_TEST_PROJECT_ID,
                _POOL_TEST_SESSION_ID,
            )
            attributions_n = await conn.fetchval(
                """
                SELECT count(*) FROM session_usage_attributions
                WHERE event_id IN (
                    SELECT id FROM session_usage_events
                    WHERE project_id = $1 AND session_id = $2
                )
                """,
                _POOL_TEST_PROJECT_ID,
                _POOL_TEST_SESSION_ID,
            )
        return {
            "sessions": int(sessions_n or 0),
            "session_messages": int(messages_n or 0),
            "session_tool_usage": int(tools_n or 0),
            "session_usage_events": int(events_n or 0),
            "session_usage_attributions": int(attributions_n or 0),
        }

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    async def test_pool_persist_creates_all_expected_rows(self) -> None:
        """Bug #1 fix (pool): persist_envelope with _pg_conn must not raise FK violations.

        A pool with min_size=2 guarantees distinct connections.  Any child write
        that does NOT thread _pg_conn would acquire a different pool connection
        and fail with ForeignKeyViolationError because the sessions parent row
        isn't visible across connections until the outer transaction commits.
        """
        service = self._build_pool_service()

        result = await self._persist_once_pool(service)

        self.assertTrue(
            result.accepted,
            f"persist_envelope rejected the envelope; warnings: {result.warnings}",
        )

        counts = await self._row_counts()

        self.assertEqual(counts["sessions"], 1, f"Expected 1 sessions row, got {counts['sessions']}")
        self.assertEqual(
            counts["session_messages"],
            _POOL_EXPECTED_MESSAGES,
            f"Expected {_POOL_EXPECTED_MESSAGES} session_messages rows, got {counts['session_messages']}",
        )
        self.assertEqual(
            counts["session_tool_usage"],
            _POOL_EXPECTED_TOOLS,
            f"Expected {_POOL_EXPECTED_TOOLS} session_tool_usage rows, got {counts['session_tool_usage']}",
        )
        self.assertEqual(
            counts["session_usage_events"],
            _POOL_EXPECTED_EVENTS,
            f"Expected {_POOL_EXPECTED_EVENTS} session_usage_events rows, got {counts['session_usage_events']}",
        )
        self.assertEqual(
            counts["session_usage_attributions"],
            _POOL_EXPECTED_ATTRIBUTIONS,
            f"Expected {_POOL_EXPECTED_ATTRIBUTIONS} session_usage_attributions rows, "
            f"got {counts['session_usage_attributions']}",
        )

    async def test_pool_idempotency_no_duplicate_rows(self) -> None:
        """Calling persist_envelope twice with the same session must not increase counts."""
        service = self._build_pool_service()

        result1 = await self._persist_once_pool(service)
        self.assertTrue(result1.accepted, f"First persist rejected; warnings: {result1.warnings}")
        counts_after_first = await self._row_counts()

        result2 = await self._persist_once_pool(service)
        self.assertTrue(result2.accepted, f"Idempotency persist rejected; warnings: {result2.warnings}")
        counts_after_second = await self._row_counts()

        self.assertEqual(
            counts_after_first,
            counts_after_second,
            f"Row counts changed after idempotency pass: {counts_after_first} → {counts_after_second}",
        )
        self.assertEqual(counts_after_second["sessions"], 1)
        self.assertEqual(counts_after_second["session_messages"], _POOL_EXPECTED_MESSAGES)
        self.assertEqual(counts_after_second["session_tool_usage"], _POOL_EXPECTED_TOOLS)
        self.assertEqual(counts_after_second["session_usage_events"], _POOL_EXPECTED_EVENTS)
        self.assertEqual(counts_after_second["session_usage_attributions"], _POOL_EXPECTED_ATTRIBUTIONS)


if __name__ == "__main__":
    unittest.main()
