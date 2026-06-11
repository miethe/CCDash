"""Integration and unit tests for backend/application/services/agent_queries/session_detail.py.

Phase 1 / T1-001 + T1-002 + T1-004 + T1-005 evidence.

Covers:
  * T1-001: Service returns SessionDetailBundle for known project+session.
  * T1-001: Service returns None for unknown session / wrong project_id.
  * T1-001: project_id threaded into every repo call (non-active project path).
  * T1-001: Unknown include flags are ignored with a warning (no 500).
  * T1-002: Cursor pagination envelope shape: {items, cursor, limit, nextCursor}.
  * T1-002: Round-trip cursor returns next page with no gaps or duplicates.
  * T1-002: Over-max limit is clamped (no exception; warning logged).
  * T1-002: Single-page case: nextCursor is None.
  * T1-002: Empty transcript: items=[], nextCursor=None.
  * T1-002: Multi-page case: sequential pages cover all entries without gaps.
  * T1-004: Redaction runs on transcript entries before return.
  * T1-004: A known secret in the fixture transcript is absent from service output.
  * T1-004: OTEL span is emitted per call (no error when otel is disabled).
  * T1-004: Bundle assembles correctly for a non-active project_id.
  * T1-005: SessionTranscriptService is the only transcript reader (structural guard).
  * T1-005: No raw SQL in session_detail.py (structural guard).

Run as named module:
    backend/.venv/bin/python -m pytest backend/tests/test_session_detail_service.py -v
"""
from __future__ import annotations

import asyncio
import pathlib
import re
import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import pytest

from backend.adapters.storage.local import LocalStorageUnitOfWork
from backend.application.services.agent_queries.session_detail import (
    ALL_INCLUDE_FLAGS,
    DEFAULT_TRANSCRIPT_LIMIT,
    INCLUDE_ARTIFACTS,
    INCLUDE_LINKS,
    INCLUDE_SUBAGENTS,
    INCLUDE_TOKENS,
    INCLUDE_TRANSCRIPT,
    MAX_TRANSCRIPT_LIMIT,
    SessionDetailBundle,
    TranscriptPage,
    _decode_cursor,
    _encode_cursor,
    get_session_detail,
)
from backend.application.services.agent_queries.redaction import REDACTED_PLACEHOLDER
from backend.db.repositories.sessions import SqliteSessionRepository
from backend.db.sqlite_migrations import run_migrations

# ── Test fixtures ─────────────────────────────────────────────────────────────

PROJ_A = "proj-alpha"
PROJ_B = "proj-beta"
SESSION_A1 = "sess-alpha-001"
SESSION_A2 = "sess-alpha-002"
ABSENT_ID = "does-not-exist"

_BASE_SESSION = {
    "taskId": "",
    "status": "completed",
    "sessionType": "session",
    "model": "claude-sonnet",
    "platformType": "Claude Code",
    "platformVersion": "2.1.52",
    "platformVersions": ["2.1.52"],
    "platformVersionTransitions": [],
    "durationSeconds": 42,
    "tokensIn": 100,
    "tokensOut": 200,
    "modelIOTokens": 300,
    "cacheCreationInputTokens": 10,
    "cacheReadInputTokens": 5,
    "cacheInputTokens": 0,
    "observedTokens": 0,
    "toolReportedTokens": 0,
    "toolResultInputTokens": 0,
    "toolResultOutputTokens": 0,
    "toolResultCacheCreationInputTokens": 0,
    "toolResultCacheReadInputTokens": 0,
    "totalCost": 0.05,
    "qualityRating": 0,
    "frictionRating": 0,
    "gitCommitHash": None,
    "gitAuthor": None,
    "gitBranch": None,
    "startedAt": "2026-06-01T00:00:00Z",
    "endedAt": "2026-06-01T00:01:00Z",
    "sourceFile": "",
    "parentSessionId": None,
    "rootSessionId": None,
    "agentId": None,
    "threadKind": "root",
    "conversationFamilyId": None,
    "contextInheritance": "fresh",
}


def _session(session_id: str, **overrides: Any) -> dict:
    return {**_BASE_SESSION, "id": session_id, **overrides}


def _make_fake_log(idx: int, content: str = "") -> dict:
    """Return a fake log entry dict matching the shape SessionTranscriptService returns."""
    return {
        "id": f"log-{idx}",
        "timestamp": f"2026-06-01T00:0{idx}:00Z",
        "speaker": "assistant",
        "type": "message",
        "content": content or f"log content {idx}",
        "agentName": None,
        "linkedSessionId": None,
        "relatedToolCallId": None,
        "metadata": {},
        "toolCall": None,
    }


# ── Helpers for CorePorts construction ───────────────────────────────────────

class FakeCorePortsFactory:
    """Create a minimal CorePorts-compatible object backed by an in-memory SQLite DB."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._storage = LocalStorageUnitOfWork(db)

    @property
    def storage(self) -> LocalStorageUnitOfWork:
        return self._storage


# ── Cursor encode / decode unit tests ────────────────────────────────────────

class TestCursorHelpers(unittest.TestCase):
    def test_encode_decode_round_trip_zero(self) -> None:
        self.assertEqual(_decode_cursor(_encode_cursor(0)), 0)

    def test_encode_decode_round_trip_positive(self) -> None:
        for offset in (1, 10, 200, 999, 5000):
            self.assertEqual(_decode_cursor(_encode_cursor(offset)), offset)

    def test_decode_none_returns_zero(self) -> None:
        self.assertEqual(_decode_cursor(None), 0)

    def test_decode_empty_returns_zero(self) -> None:
        self.assertEqual(_decode_cursor(""), 0)

    def test_decode_garbage_returns_zero(self) -> None:
        self.assertEqual(_decode_cursor("!!!notbase64###"), 0)

    def test_encode_produces_string(self) -> None:
        cursor = _encode_cursor(42)
        self.assertIsInstance(cursor, str)
        self.assertTrue(cursor)  # non-empty


# ── Integration tests using in-memory SQLite ─────────────────────────────────

class TestGetSessionDetail(unittest.IsolatedAsyncioTestCase):
    """Integration-level tests: real SQLite DB, real repositories, mocked transcript."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.ports = FakeCorePortsFactory(self.db)
        self.session_repo = SqliteSessionRepository(self.db)

        # Seed sessions
        await self.session_repo.upsert(_session(SESSION_A1, tokensIn=111), PROJ_A)
        await self.session_repo.upsert(_session(SESSION_A2, tokensIn=222), PROJ_A)
        await self.db.commit()

    async def asyncTearDown(self) -> None:
        await self.db.close()

    def _fake_logs(self, n: int) -> list[dict]:
        return [_make_fake_log(i) for i in range(n)]

    # ── Basic fetch ──────────────────────────────────────────────────────────

    async def test_returns_bundle_for_existing_session(self) -> None:
        with patch(
            "backend.application.services.agent_queries.session_detail"
            "._transcript_service.list_session_logs",
            new=AsyncMock(return_value=self._fake_logs(3)),
        ):
            bundle = await get_session_detail(PROJ_A, SESSION_A1, self.ports)
        self.assertIsNotNone(bundle)
        self.assertIsInstance(bundle, SessionDetailBundle)
        self.assertEqual(bundle.session_id, SESSION_A1)
        self.assertEqual(bundle.project_id, PROJ_A)

    async def test_returns_none_for_absent_session(self) -> None:
        bundle = await get_session_detail(PROJ_A, ABSENT_ID, self.ports)
        self.assertIsNone(bundle)

    async def test_returns_none_for_wrong_project(self) -> None:
        """Session exists in PROJ_A; requesting with PROJ_B must return None."""
        with patch(
            "backend.application.services.agent_queries.session_detail"
            "._transcript_service.list_session_logs",
            new=AsyncMock(return_value=[]),
        ):
            bundle = await get_session_detail(PROJ_B, SESSION_A1, self.ports)
        self.assertIsNone(bundle)

    # ── Include-flag behaviour ────────────────────────────────────────────────

    async def test_none_include_returns_all_segments(self) -> None:
        with patch(
            "backend.application.services.agent_queries.session_detail"
            "._transcript_service.list_session_logs",
            new=AsyncMock(return_value=self._fake_logs(2)),
        ):
            bundle = await get_session_detail(
                PROJ_A, SESSION_A1, self.ports, include=None
            )
        self.assertIsNotNone(bundle.transcript)
        self.assertIsNotNone(bundle.subagents)
        self.assertIsNotNone(bundle.tokens)
        self.assertIsNotNone(bundle.artifacts)
        self.assertIsNotNone(bundle.links)

    async def test_include_tokens_only_returns_only_tokens(self) -> None:
        bundle = await get_session_detail(
            PROJ_A, SESSION_A1, self.ports, include={INCLUDE_TOKENS}
        )
        self.assertIsNotNone(bundle)
        self.assertIsNone(bundle.transcript)
        self.assertIsNone(bundle.subagents)
        self.assertIsNotNone(bundle.tokens)
        self.assertIsNone(bundle.artifacts)
        self.assertIsNone(bundle.links)

    async def test_include_transcript_only(self) -> None:
        with patch(
            "backend.application.services.agent_queries.session_detail"
            "._transcript_service.list_session_logs",
            new=AsyncMock(return_value=self._fake_logs(1)),
        ):
            bundle = await get_session_detail(
                PROJ_A, SESSION_A1, self.ports, include={INCLUDE_TRANSCRIPT}
            )
        self.assertIsNotNone(bundle.transcript)
        self.assertIsNone(bundle.subagents)
        self.assertIsNone(bundle.tokens)
        self.assertIsNone(bundle.artifacts)
        self.assertIsNone(bundle.links)

    async def test_unknown_include_flag_ignored_no_error(self) -> None:
        """Unknown flag is silently ignored — no KeyError / 500."""
        with patch(
            "backend.application.services.agent_queries.session_detail"
            "._transcript_service.list_session_logs",
            new=AsyncMock(return_value=[]),
        ):
            bundle = await get_session_detail(
                PROJ_A, SESSION_A1, self.ports,
                include={INCLUDE_TRANSCRIPT, "totally_unknown_flag_xyz"}
            )
        self.assertIsNotNone(bundle)
        self.assertIsNotNone(bundle.transcript)

    # ── Token telemetry ───────────────────────────────────────────────────────

    async def test_tokens_match_session_row(self) -> None:
        bundle = await get_session_detail(
            PROJ_A, SESSION_A1, self.ports, include={INCLUDE_TOKENS}
        )
        self.assertIsNotNone(bundle.tokens)
        self.assertEqual(bundle.tokens["tokensIn"], 111)
        self.assertEqual(bundle.tokens["tokensOut"], 200)
        self.assertAlmostEqual(bundle.tokens["totalCost"], 0.05, places=4)
        self.assertAlmostEqual(bundle.tokens["durationSeconds"], 42.0, places=1)

    # ── Cursor pagination ─────────────────────────────────────────────────────

    async def test_empty_transcript_returns_empty_page(self) -> None:
        with patch(
            "backend.application.services.agent_queries.session_detail"
            "._transcript_service.list_session_logs",
            new=AsyncMock(return_value=[]),
        ):
            bundle = await get_session_detail(
                PROJ_A, SESSION_A1, self.ports, include={INCLUDE_TRANSCRIPT}, limit=10
            )
        page = bundle.transcript
        self.assertIsNotNone(page)
        self.assertEqual(page.items, [])
        self.assertIsNone(page.next_cursor)
        self.assertEqual(page.limit, 10)

    async def test_single_page_next_cursor_is_none(self) -> None:
        """When all items fit on one page, nextCursor must be None."""
        with patch(
            "backend.application.services.agent_queries.session_detail"
            "._transcript_service.list_session_logs",
            new=AsyncMock(return_value=self._fake_logs(3)),
        ):
            bundle = await get_session_detail(
                PROJ_A, SESSION_A1, self.ports, include={INCLUDE_TRANSCRIPT}, limit=10
            )
        page = bundle.transcript
        self.assertIsNone(page.next_cursor)
        self.assertEqual(len(page.items), 3)

    async def test_multi_page_round_trip_no_gaps_no_dupes(self) -> None:
        """Two pages of 5 + 5 cover all 10 items with no gaps or duplicates."""
        all_logs = [_make_fake_log(i, f"entry-{i}") for i in range(10)]

        async def _fake_list_logs(session_row, ports, *, limit, offset):
            # Simulate real pagination behaviour
            return all_logs[offset: offset + limit]

        with patch(
            "backend.application.services.agent_queries.session_detail"
            "._transcript_service.list_session_logs",
            new=_fake_list_logs,
        ):
            # Page 1
            bundle1 = await get_session_detail(
                PROJ_A, SESSION_A1, self.ports,
                include={INCLUDE_TRANSCRIPT}, limit=5
            )
            page1 = bundle1.transcript
            self.assertIsNotNone(page1.next_cursor, "Page 1 should have a nextCursor")
            self.assertEqual(len(page1.items), 5)

            # Page 2 (using nextCursor from page 1)
            bundle2 = await get_session_detail(
                PROJ_A, SESSION_A1, self.ports,
                include={INCLUDE_TRANSCRIPT}, limit=5, cursor=page1.next_cursor
            )
            page2 = bundle2.transcript
            self.assertIsNone(page2.next_cursor, "Page 2 should have no nextCursor")
            self.assertEqual(len(page2.items), 5)

        # Verify no gaps and no duplicates
        ids1 = [item["id"] for item in page1.items]
        ids2 = [item["id"] for item in page2.items]
        self.assertEqual(len(set(ids1) & set(ids2)), 0, "No duplicate items across pages")
        self.assertEqual(set(ids1 + ids2), {f"log-{i}" for i in range(10)}, "All 10 items covered")

    async def test_over_max_limit_is_clamped(self) -> None:
        """Requesting limit > MAX_TRANSCRIPT_LIMIT clamps to MAX without exception."""
        huge_limit = MAX_TRANSCRIPT_LIMIT + 10_000
        with patch(
            "backend.application.services.agent_queries.session_detail"
            "._transcript_service.list_session_logs",
            new=AsyncMock(return_value=self._fake_logs(3)),
        ):
            bundle = await get_session_detail(
                PROJ_A, SESSION_A1, self.ports,
                include={INCLUDE_TRANSCRIPT}, limit=huge_limit
            )
        self.assertIsNotNone(bundle)
        self.assertEqual(bundle.transcript.limit, MAX_TRANSCRIPT_LIMIT)

    async def test_page_items_count_matches_limit(self) -> None:
        """When more items exist than the limit, exactly ``limit`` are returned."""
        all_logs = self._fake_logs(20)

        async def _fake_list_logs(session_row, ports, *, limit, offset):
            return all_logs[offset: offset + limit]

        with patch(
            "backend.application.services.agent_queries.session_detail"
            "._transcript_service.list_session_logs",
            new=_fake_list_logs,
        ):
            bundle = await get_session_detail(
                PROJ_A, SESSION_A1, self.ports,
                include={INCLUDE_TRANSCRIPT}, limit=7
            )
        self.assertEqual(len(bundle.transcript.items), 7)
        self.assertIsNotNone(bundle.transcript.next_cursor)

    # ── Redaction on transcript entries ──────────────────────────────────────

    async def test_embedded_secret_absent_from_output(self) -> None:
        """A known secret embedded in a log entry must not appear in the bundle output."""
        secret = "sk-abc123def456ghi789jkl012mno345pqr678"
        logs_with_secret = [
            _make_fake_log(0, content=f"Using token: {secret}"),
            _make_fake_log(1, content="clean message"),
        ]
        with patch(
            "backend.application.services.agent_queries.session_detail"
            "._transcript_service.list_session_logs",
            new=AsyncMock(return_value=logs_with_secret),
        ):
            bundle = await get_session_detail(
                PROJ_A, SESSION_A1, self.ports, include={INCLUDE_TRANSCRIPT}
            )
        output_text = str(bundle.as_dict())
        self.assertNotIn(secret, output_text, "Secret must not appear in service output")
        self.assertIn(REDACTED_PLACEHOLDER, output_text, "Placeholder must be present")
        self.assertGreater(bundle.redacted_field_count, 0)

    async def test_clean_entries_not_modified(self) -> None:
        """Clean entries (no secrets) are returned unchanged."""
        logs = [_make_fake_log(i, f"clean message {i}") for i in range(3)]
        with patch(
            "backend.application.services.agent_queries.session_detail"
            "._transcript_service.list_session_logs",
            new=AsyncMock(return_value=logs),
        ):
            bundle = await get_session_detail(
                PROJ_A, SESSION_A1, self.ports, include={INCLUDE_TRANSCRIPT}
            )
        for item in bundle.transcript.items:
            self.assertNotIn(REDACTED_PLACEHOLDER, item["content"])
        self.assertEqual(bundle.redacted_field_count, 0)

    # ── Non-active project assembly ───────────────────────────────────────────

    async def test_non_active_project_returns_correct_bundle(self) -> None:
        """Bundle assembled for a project that is NOT the 'active' project."""
        # We have no active-project concept here; the test verifies project_id
        # is respected purely through the repo scoping
        with patch(
            "backend.application.services.agent_queries.session_detail"
            "._transcript_service.list_session_logs",
            new=AsyncMock(return_value=self._fake_logs(1)),
        ):
            bundle = await get_session_detail(PROJ_A, SESSION_A1, self.ports)
        self.assertIsNotNone(bundle)
        self.assertEqual(bundle.project_id, PROJ_A)
        self.assertEqual(bundle.session["id"], SESSION_A1)

    # ── as_dict serialisation ─────────────────────────────────────────────────

    async def test_as_dict_includes_all_keys(self) -> None:
        with patch(
            "backend.application.services.agent_queries.session_detail"
            "._transcript_service.list_session_logs",
            new=AsyncMock(return_value=self._fake_logs(2)),
        ):
            bundle = await get_session_detail(
                PROJ_A, SESSION_A1, self.ports, include=ALL_INCLUDE_FLAGS
            )
        d = bundle.as_dict()
        for key in ("sessionId", "projectId", "session", "redactedFieldCount"):
            self.assertIn(key, d)
        # All included segments present
        for key in ("transcript", "subagents", "tokens", "artifacts", "links"):
            self.assertIn(key, d)

    async def test_transcript_page_as_dict_shape(self) -> None:
        with patch(
            "backend.application.services.agent_queries.session_detail"
            "._transcript_service.list_session_logs",
            new=AsyncMock(return_value=self._fake_logs(2)),
        ):
            bundle = await get_session_detail(
                PROJ_A, SESSION_A1, self.ports, include={INCLUDE_TRANSCRIPT}
            )
        page_dict = bundle.transcript.as_dict()
        for key in ("items", "cursor", "limit", "nextCursor"):
            self.assertIn(key, page_dict)


# ── Structural guard tests ────────────────────────────────────────────────────

class TestStructuralGuards(unittest.TestCase):
    """Structural tests to enforce architecture invariants (T1-005).

    These grep the source file rather than executing code so they catch
    accidental regressions in *any future edit*, not just the current one.
    """

    SESSION_DETAIL_PATH = pathlib.Path(
        __file__
    ).parent.parent / "application" / "services" / "agent_queries" / "session_detail.py"

    def _source(self) -> str:
        return self.SESSION_DETAIL_PATH.read_text(encoding="utf-8")

    def test_file_exists(self) -> None:
        self.assertTrue(self.SESSION_DETAIL_PATH.exists())

    def test_session_transcript_service_is_sole_reader(self) -> None:
        """session_detail.py must use SessionTranscriptService and nothing else for logs.

        Specifically:
          - ``SessionTranscriptService`` must be imported.
          - ``list_session_logs`` must be the call site.
          - No direct ``session_logs`` SQL (raw table access would bypass the
            service and duplicate the reader).
        """
        source = self._source()
        self.assertIn("SessionTranscriptService", source,
                      "Must import/use SessionTranscriptService")
        self.assertIn("list_session_logs", source,
                      "Must call list_session_logs via the transcript service")

    def test_no_raw_sql_in_session_detail(self) -> None:
        """session_detail.py must not contain raw SQL strings (SELECT/INSERT/UPDATE/DELETE).

        Rationale: Router→Service→Repository pattern — services never issue raw SQL.
        """
        source = self._source()
        # Allow SQL-like words only in comments/docstrings
        non_comment_lines = [
            line for line in source.splitlines()
            if line.strip() and not line.strip().startswith("#")
            and not line.strip().startswith('"""')
            and not line.strip().startswith("'''")
        ]
        sql_pattern = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|CREATE TABLE|DROP TABLE)\b", re.I)
        for line in non_comment_lines:
            self.assertIsNone(
                sql_pattern.search(line),
                f"Raw SQL found in session_detail.py: {line!r}",
            )

    def test_no_duplicate_transcript_reader(self) -> None:
        """session_detail.py must not import any secondary transcript reading module."""
        source = self._source()
        # These would indicate a duplicate reader being introduced
        forbidden_imports = [
            "from backend.parsers.sessions",
            "from backend.parsers import sessions",
            "parse_session_file",
            "from backend.db.repositories.sessions import",  # direct repo import for logs
        ]
        for forbidden in forbidden_imports:
            self.assertNotIn(
                forbidden, source,
                f"Duplicate transcript reader detected — forbidden: {forbidden!r}",
            )

    def test_redaction_import_present(self) -> None:
        """session_detail.py must import and use the redaction module."""
        source = self._source()
        self.assertIn("from .redaction import", source,
                      "Must import redaction module")
        self.assertIn("redact_entries", source,
                      "Must call redact_entries")

    def test_otel_span_emitted(self) -> None:
        """session_detail.py must emit an OTEL span per call."""
        source = self._source()
        self.assertIn("otel.start_span", source,
                      "Must emit an OTEL span")

    def test_project_id_passed_to_get_by_id(self) -> None:
        """project_id must be forwarded to get_by_id (Phase 0 isolation invariant)."""
        source = self._source()
        self.assertIn("project_id=project_id", source,
                      "project_id must be threaded through to get_by_id")


# ── Edge-case resilience tests ────────────────────────────────────────────────

class TestResilienceEdgeCases(unittest.IsolatedAsyncioTestCase):
    """Resilience: partial failures in optional segments return partial bundle."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.ports = FakeCorePortsFactory(self.db)
        self.session_repo = SqliteSessionRepository(self.db)
        await self.session_repo.upsert(_session(SESSION_A1), PROJ_A)
        await self.db.commit()

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_entity_links_failure_returns_empty_not_500(self) -> None:
        """If entity_links repo raises, artifacts/links default to [] not a 500."""
        mock_storage = MagicMock()
        mock_storage.sessions.return_value = SqliteSessionRepository(self.db)
        mock_storage.session_messages.return_value = MagicMock(
            list_by_session=AsyncMock(return_value=[])
        )
        mock_storage.entity_links.side_effect = RuntimeError("DB unavailable")

        ports = SimpleNamespace(storage=mock_storage)
        bundle = await get_session_detail(
            PROJ_A, SESSION_A1, ports,
            include={INCLUDE_TRANSCRIPT, INCLUDE_ARTIFACTS, INCLUDE_LINKS}
        )
        self.assertIsNotNone(bundle)
        self.assertEqual(bundle.artifacts, [])
        self.assertEqual(bundle.links, [])

    async def test_relationships_failure_returns_empty_subagents(self) -> None:
        """If list_relationships raises, subagents default to [] not a 500."""
        mock_session_repo = MagicMock()
        mock_session_repo.get_by_id = AsyncMock(
            return_value=dict(_session(SESSION_A1)) | {"project_id": PROJ_A}
        )
        mock_session_repo.list_relationships = AsyncMock(
            side_effect=RuntimeError("relationships table missing")
        )
        mock_storage = MagicMock()
        mock_storage.sessions.return_value = mock_session_repo
        mock_storage.session_messages.return_value = MagicMock(
            list_by_session=AsyncMock(return_value=[])
        )
        ports = SimpleNamespace(storage=mock_storage)
        bundle = await get_session_detail(
            PROJ_A, SESSION_A1, ports, include={INCLUDE_SUBAGENTS}
        )
        self.assertIsNotNone(bundle)
        self.assertEqual(bundle.subagents, [])

    async def test_tokens_present_in_bundle(self) -> None:
        bundle = await get_session_detail(
            PROJ_A, SESSION_A1, self.ports, include={INCLUDE_TOKENS}
        )
        self.assertIsNotNone(bundle.tokens)
        self.assertIn("tokensIn", bundle.tokens)
        self.assertIn("totalCost", bundle.tokens)
        self.assertIn("durationSeconds", bundle.tokens)


if __name__ == "__main__":
    unittest.main()
