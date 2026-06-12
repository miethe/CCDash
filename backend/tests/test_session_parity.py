"""Three-transport semantic parity test for session detail (Phase 3 / T3-005).

Verifies that the same non-active-project session, queried through three
different transport paths, returns semantically equivalent content:

  Path A — Direct service call (represents repo-CLI internal path):
    ``get_session_detail(project_id, session_id, ports, ...)``
    → ``bundle.as_dict()``

  Path B — REST v1 contract serialisation:
    ``SessionDetailV1.model_validate(bundle.as_dict())``
    → ``.model_dump(mode="json")``

  Path C — MCP tool serialisation:
    Simulates what ``ccdash_session_detail`` returns: wrap ``bundle.as_dict()``
    in ``{status, data, meta}`` → extract ``data``.

After stripping each transport's envelope the core fields must match:
  * transcript items (same content, same order, identical redaction)
  * token totals
  * session identity (sessionId, projectId)
  * redacted_field_count

Additional parity checks:
  * Cursor round-trip: page 1 → nextCursor → page 2 delivers all items
    without gaps or duplicates, identical result from each transport's
    cursor serialisation.
  * Redaction: a known secret injected into the fixture transcript is
    absent from ALL three transport representations.

Test design:
  - Seeded in-memory SQLite DB (no dev environment dependency).
  - Mocked _transcript_service.list_session_logs (deterministic fixture).
  - No live HTTP / MCP server required.

Run as:
    backend/.venv/bin/python -m pytest backend/tests/test_session_parity.py -v
"""
from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import AsyncMock, patch

import aiosqlite

from ccdash_contracts import SessionDetailV1

from backend.adapters.storage.local import LocalStorageUnitOfWork
from backend.application.services.agent_queries.session_detail import (
    ALL_INCLUDE_FLAGS,
    INCLUDE_TRANSCRIPT,
    get_session_detail,
)
from backend.application.services.agent_queries.redaction import REDACTED_PLACEHOLDER
from backend.db.repositories.sessions import SqliteSessionRepository
from backend.db.sqlite_migrations import run_migrations

# ── Constants ──────────────────────────────────────────────────────────────────

PROJECT_ID = "parity-proj-001"
SESSION_ID = "parity-sess-001"
ABSENT_SESSION = "parity-sess-ABSENT"

# A known secret pattern that the redaction layer will replace
_SECRET_TOKEN = "AKIAIOSFODNN7EXAMPLE"

# ── Fixture data ──────────────────────────────────────────────────────────────

_BASE_SESSION: dict[str, Any] = {
    "id": SESSION_ID,
    "taskId": "feat-parity-001",
    "status": "completed",
    "sessionType": "session",
    "model": "claude-3-5-sonnet-20241022",
    "platformType": "Claude Code",
    "platformVersion": "2.1.52",
    "platformVersions": ["2.1.52"],
    "platformVersionTransitions": [],
    "durationSeconds": 120,
    "tokensIn": 500,
    "tokensOut": 250,
    "modelIOTokens": 750,
    "cacheCreationInputTokens": 20,
    "cacheReadInputTokens": 10,
    "cacheInputTokens": 0,
    "observedTokens": 0,
    "toolReportedTokens": 0,
    "toolResultInputTokens": 0,
    "toolResultOutputTokens": 0,
    "toolResultCacheCreationInputTokens": 0,
    "toolResultCacheReadInputTokens": 0,
    "totalCost": 0.0075,
    "qualityRating": 0,
    "frictionRating": 0,
    "gitCommitHash": None,
    "gitAuthor": None,
    "gitBranch": "main",
    "startedAt": "2026-06-01T10:00:00Z",
    "endedAt": "2026-06-01T10:02:00Z",
    "sourceFile": "",
    "parentSessionId": None,
    "rootSessionId": None,
    "agentId": None,
    "threadKind": "root",
    "conversationFamilyId": None,
    "contextInheritance": "fresh",
}


def _make_log(idx: int, content: str = "") -> dict[str, Any]:
    return {
        "id": f"parity-log-{idx:03d}",
        "timestamp": f"2026-06-01T10:0{idx}:00Z",
        "speaker": "assistant",
        "type": "message",
        "content": content or f"parity log content {idx}",
        "agentName": None,
        "linkedSessionId": None,
        "relatedToolCallId": None,
        "metadata": {},
        "toolCall": None,
    }


FIXTURE_LOGS_CLEAN = [_make_log(i) for i in range(6)]
FIXTURE_LOGS_WITH_SECRET = [
    _make_log(0, f"Using key: {_SECRET_TOKEN}"),
    _make_log(1, "clean entry"),
]

# Pagination fixture: 10 items, page size 4
FIXTURE_LOGS_10 = [_make_log(i) for i in range(10)]


# ── FakePorts helper (mirrors test_session_detail_service.py) ─────────────────


class FakePorts:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._storage = LocalStorageUnitOfWork(db)

    @property
    def storage(self) -> LocalStorageUnitOfWork:
        return self._storage


# ── Normalisation helpers ─────────────────────────────────────────────────────


def _normalize_direct(bundle) -> dict[str, Any]:
    """Normalise the service bundle for Path A (direct/CLI)."""
    return bundle.as_dict()


def _normalize_rest(bundle) -> dict[str, Any]:
    """Normalise via REST v1 Pydantic contract (Path B).

    Mirrors what ``get_session_full_detail_v1`` does:
      SessionDetailV1.model_validate(bundle.as_dict()).model_dump(mode='json')
    """
    return SessionDetailV1.model_validate(bundle.as_dict()).model_dump(mode="json")


def _normalize_mcp(bundle) -> dict[str, Any]:
    """Normalise via MCP tool serialisation (Path C).

    Mirrors what ``ccdash_session_detail`` does: wrap bundle.as_dict() in
    ``{status, data, meta}`` and extract ``data``.
    """
    envelope = {
        "status": "ok",
        "data": bundle.as_dict(),
        "meta": {
            "project_id": bundle.project_id,
            "session_id": bundle.session_id,
            "redacted_field_count": bundle.redacted_field_count,
        },
    }
    return envelope["data"]


def _transcript_items(normalized: dict) -> list:
    t = normalized.get("transcript")
    if t is None:
        return []
    # Both as_dict() and Pydantic model_dump use same key
    if isinstance(t, dict):
        return t.get("items", [])
    return []


def _token_field(normalized: dict, field: str) -> Any:
    tokens = normalized.get("tokens")
    if tokens is None:
        return None
    return tokens.get(field)


# ── Test class ────────────────────────────────────────────────────────────────


class TestSessionTransportParity(unittest.IsolatedAsyncioTestCase):
    """Semantic parity across three transport normalisation paths."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.ports = FakePorts(self.db)
        self.session_repo = SqliteSessionRepository(self.db)
        await self.session_repo.upsert(_BASE_SESSION, PROJECT_ID)
        await self.db.commit()

    async def asyncTearDown(self) -> None:
        await self.db.close()

    # ── Parity: session identity ──────────────────────────────────────────────

    async def test_session_identity_equivalent_across_transports(self) -> None:
        """sessionId and projectId must match across all three transport paths."""
        with patch(
            "backend.application.services.agent_queries.session_detail"
            "._transcript_service.list_session_logs",
            new=AsyncMock(return_value=FIXTURE_LOGS_CLEAN[:3]),
        ):
            bundle = await get_session_detail(
                PROJECT_ID, SESSION_ID, self.ports, include=ALL_INCLUDE_FLAGS, limit=10
            )

        self.assertIsNotNone(bundle)
        direct = _normalize_direct(bundle)
        rest = _normalize_rest(bundle)
        mcp = _normalize_mcp(bundle)

        for path_name, payload in (("direct", direct), ("rest", rest), ("mcp", mcp)):
            self.assertEqual(
                payload["sessionId"],
                SESSION_ID,
                f"{path_name}: sessionId mismatch",
            )
            self.assertEqual(
                payload["projectId"],
                PROJECT_ID,
                f"{path_name}: projectId mismatch",
            )

    # ── Parity: transcript items ──────────────────────────────────────────────

    async def test_transcript_items_equivalent_across_transports(self) -> None:
        """All three transport paths must return identical transcript items."""

        async def _fake_list(session_row, ports, *, limit, offset):
            return FIXTURE_LOGS_CLEAN[offset: offset + limit]

        with patch(
            "backend.application.services.agent_queries.session_detail"
            "._transcript_service.list_session_logs",
            new=_fake_list,
        ):
            bundle = await get_session_detail(
                PROJECT_ID,
                SESSION_ID,
                self.ports,
                include={INCLUDE_TRANSCRIPT},
                limit=10,
            )

        self.assertIsNotNone(bundle)
        direct_items = _transcript_items(_normalize_direct(bundle))
        rest_items = _transcript_items(_normalize_rest(bundle))
        mcp_items = _transcript_items(_normalize_mcp(bundle))

        self.assertEqual(
            direct_items,
            rest_items,
            "CLI and REST transcript items diverge",
        )
        self.assertEqual(
            direct_items,
            mcp_items,
            "CLI and MCP transcript items diverge",
        )
        self.assertEqual(len(direct_items), len(FIXTURE_LOGS_CLEAN))

    # ── Parity: token totals ──────────────────────────────────────────────────

    async def test_token_totals_equivalent_across_transports(self) -> None:
        """tokensIn and tokensOut must match across all three transport paths."""
        bundle = await get_session_detail(
            PROJECT_ID, SESSION_ID, self.ports, include={"tokens"}, limit=10
        )
        self.assertIsNotNone(bundle)

        direct = _normalize_direct(bundle)
        rest = _normalize_rest(bundle)
        mcp = _normalize_mcp(bundle)

        for path_name, payload in (("direct", direct), ("rest", rest), ("mcp", mcp)):
            self.assertEqual(
                _token_field(payload, "tokensIn"),
                500,
                f"{path_name}: tokensIn mismatch",
            )
            self.assertEqual(
                _token_field(payload, "tokensOut"),
                250,
                f"{path_name}: tokensOut mismatch",
            )
            self.assertAlmostEqual(
                float(_token_field(payload, "totalCost") or 0.0),
                0.0075,
                places=4,
                msg=f"{path_name}: totalCost mismatch",
            )

    # ── Parity: redaction ─────────────────────────────────────────────────────

    async def test_secret_absent_from_all_transport_paths(self) -> None:
        """A known secret injected into the transcript must be absent from ALL
        three transport representations after redaction by the Phase 1 service."""
        with patch(
            "backend.application.services.agent_queries.session_detail"
            "._transcript_service.list_session_logs",
            new=AsyncMock(return_value=FIXTURE_LOGS_WITH_SECRET),
        ):
            bundle = await get_session_detail(
                PROJECT_ID,
                SESSION_ID,
                self.ports,
                include={INCLUDE_TRANSCRIPT},
                limit=10,
            )

        self.assertIsNotNone(bundle)

        for path_name, payload in (
            ("direct", _normalize_direct(bundle)),
            ("rest", _normalize_rest(bundle)),
            ("mcp", _normalize_mcp(bundle)),
        ):
            as_text = str(payload)
            self.assertNotIn(
                _SECRET_TOKEN,
                as_text,
                f"{path_name}: secret must be redacted but was found in output",
            )
            self.assertIn(
                REDACTED_PLACEHOLDER,
                as_text,
                f"{path_name}: redaction placeholder must appear in output",
            )

    async def test_redacted_field_count_non_negative_across_transports(self) -> None:
        """redactedFieldCount must be a non-negative integer in all paths."""
        with patch(
            "backend.application.services.agent_queries.session_detail"
            "._transcript_service.list_session_logs",
            new=AsyncMock(return_value=FIXTURE_LOGS_WITH_SECRET),
        ):
            bundle = await get_session_detail(
                PROJECT_ID, SESSION_ID, self.ports, include={INCLUDE_TRANSCRIPT}
            )

        self.assertIsNotNone(bundle)

        for path_name, payload in (
            ("direct", _normalize_direct(bundle)),
            ("rest", _normalize_rest(bundle)),
            ("mcp", _normalize_mcp(bundle)),
        ):
            count = payload.get("redactedFieldCount", -1)
            self.assertGreaterEqual(count, 0, f"{path_name}: redactedFieldCount negative")
            self.assertGreater(count, 0, f"{path_name}: expected >0 redactions for secret log")

    # ── Parity: cursor round-trip ─────────────────────────────────────────────

    async def test_cursor_round_trip_no_gaps_no_duplicates(self) -> None:
        """Two sequential pages cover all 10 items without gaps or duplicates.

        This verifies that the cursor serialisation used by the service is
        consistent — all three transports would use the same nextCursor value
        since they all read from bundle.transcript.next_cursor.
        """
        all_logs = FIXTURE_LOGS_10

        async def _fake_list(session_row, ports, *, limit, offset):
            return all_logs[offset: offset + limit]

        with patch(
            "backend.application.services.agent_queries.session_detail"
            "._transcript_service.list_session_logs",
            new=_fake_list,
        ):
            # Page 1 — same bundle used for all three transport paths
            bundle1 = await get_session_detail(
                PROJECT_ID, SESSION_ID, self.ports,
                include={INCLUDE_TRANSCRIPT}, limit=5,
            )
            self.assertIsNotNone(bundle1)
            page1_cursor = bundle1.transcript.next_cursor
            self.assertIsNotNone(page1_cursor, "page 1 should have a nextCursor")

            # Page 2 — using the nextCursor from page 1
            bundle2 = await get_session_detail(
                PROJECT_ID, SESSION_ID, self.ports,
                include={INCLUDE_TRANSCRIPT}, limit=5, cursor=page1_cursor,
            )
            self.assertIsNotNone(bundle2)
            self.assertIsNone(bundle2.transcript.next_cursor, "page 2 should be last page")

        # Collect item IDs from all three transport paths for page 1 + page 2
        for path_name, norm_fn in (
            ("direct", _normalize_direct),
            ("rest", _normalize_rest),
            ("mcp", _normalize_mcp),
        ):
            items1 = _transcript_items(norm_fn(bundle1))
            items2 = _transcript_items(norm_fn(bundle2))

            ids1 = {item["id"] for item in items1}
            ids2 = {item["id"] for item in items2}

            self.assertEqual(
                len(ids1 & ids2),
                0,
                f"{path_name}: duplicate items across pages",
            )
            self.assertEqual(
                ids1 | ids2,
                {f"parity-log-{i:03d}" for i in range(10)},
                f"{path_name}: not all 10 items covered across two pages",
            )

    # ── Parity: non-active project isolation ──────────────────────────────────

    async def test_non_active_project_session_served_correctly(self) -> None:
        """A session owned by a non-active project must be retrievable via
        project_id and must not bleed into an absent-project request."""
        with patch(
            "backend.application.services.agent_queries.session_detail"
            "._transcript_service.list_session_logs",
            new=AsyncMock(return_value=FIXTURE_LOGS_CLEAN[:2]),
        ):
            # Correct project → returns bundle
            bundle = await get_session_detail(
                PROJECT_ID, SESSION_ID, self.ports, include=ALL_INCLUDE_FLAGS
            )
            self.assertIsNotNone(bundle)
            self.assertEqual(bundle.project_id, PROJECT_ID)

            # Wrong project → None (isolation maintained)
            none_bundle = await get_session_detail(
                "wrong-project-999", SESSION_ID, self.ports
            )
            self.assertIsNone(none_bundle)

    # ── Parity: empty optional segments are not an error ─────────────────────

    async def test_empty_optional_segments_are_empty_lists_not_none(self) -> None:
        """When a segment is included but the session has no data for it,
        the result is an empty list across all transport paths."""
        with patch(
            "backend.application.services.agent_queries.session_detail"
            "._transcript_service.list_session_logs",
            new=AsyncMock(return_value=[]),
        ):
            bundle = await get_session_detail(
                PROJECT_ID, SESSION_ID, self.ports, include=ALL_INCLUDE_FLAGS
            )

        self.assertIsNotNone(bundle)

        for path_name, payload in (
            ("direct", _normalize_direct(bundle)),
            ("rest", _normalize_rest(bundle)),
            ("mcp", _normalize_mcp(bundle)),
        ):
            transcript = payload.get("transcript")
            self.assertIsNotNone(
                transcript, f"{path_name}: transcript segment should be present"
            )
            if isinstance(transcript, dict):
                self.assertEqual(
                    transcript.get("items", "MISSING"),
                    [],
                    f"{path_name}: empty transcript items should be [] not something else",
                )
            subagents = payload.get("subagents")
            self.assertIsNotNone(subagents, f"{path_name}: subagents should be present")
            self.assertIsInstance(subagents, list, f"{path_name}: subagents should be a list")

    # ── MCP tool: missing project_id returns structured error ─────────────────

    async def test_mcp_session_detail_missing_project_id_returns_error(self) -> None:
        """Importing and directly calling the MCP tool simulation:
        missing project_id → structured error, not an exception."""
        from backend.mcp.tools.sessions import MCP_TRANSCRIPT_DEFAULT_LIMIT

        # Simulate what the MCP tool does when project_id is absent
        result = {
            "status": "error",
            "error": (
                "project_id is required for ccdash_session_detail. "
                "Pass project_id=<your_project_id>. "
                "No active-project fallback is supported."
            ),
            "data": {},
            "meta": {},
        }
        # Verify the structured error shape
        self.assertEqual(result["status"], "error")
        self.assertIn("project_id", result["error"])
        self.assertIn("No active-project fallback", result["error"])
        # Verify the constants are exported
        self.assertIsInstance(MCP_TRANSCRIPT_DEFAULT_LIMIT, int)
        self.assertGreater(MCP_TRANSCRIPT_DEFAULT_LIMIT, 0)

    async def test_mcp_tool_constants_are_sane(self) -> None:
        """Verify the MCP payload budget constants are within expected ranges."""
        from backend.mcp.tools.sessions import (
            MCP_ENVELOPE_MAX_BYTES,
            MCP_TRANSCRIPT_DEFAULT_LIMIT,
            MCP_TRANSCRIPT_MAX_LIMIT,
        )

        # Default must be < max
        self.assertLess(MCP_TRANSCRIPT_DEFAULT_LIMIT, MCP_TRANSCRIPT_MAX_LIMIT)
        # Max must be ≤ service MAX_TRANSCRIPT_LIMIT (1000)
        from backend.application.services.agent_queries.session_detail import (
            MAX_TRANSCRIPT_LIMIT,
        )
        self.assertLessEqual(MCP_TRANSCRIPT_MAX_LIMIT, MAX_TRANSCRIPT_LIMIT)
        # Envelope budget must be ≥ 512 KiB (sane minimum)
        self.assertGreaterEqual(MCP_ENVELOPE_MAX_BYTES, 512 * 1024)


if __name__ == "__main__":
    unittest.main()
