"""Tests for compute_source_ref helper and source_ref write path in sessions repository."""
from __future__ import annotations

import re
import unittest

import aiosqlite

from backend.db.repositories.sessions import SqliteSessionRepository, compute_source_ref


# ---------------------------------------------------------------------------
# compute_source_ref unit tests
# ---------------------------------------------------------------------------

class TestComputeSourceRef(unittest.TestCase):
    def test_filesystem_returns_fs_uri(self) -> None:
        result = compute_source_ref("filesystem", source_file="projects/foo/session.jsonl")
        self.assertEqual(result, "fs:projects/foo/session.jsonl")

    def test_filesystem_missing_source_file_raises(self) -> None:
        with self.assertRaisesRegex(ValueError, "source_file is required"):
            compute_source_ref("filesystem")

    def test_filesystem_none_source_file_raises(self) -> None:
        with self.assertRaisesRegex(ValueError, "source_file is required"):
            compute_source_ref("filesystem", source_file=None)

    def test_remote_ingest_returns_remote_uri(self) -> None:
        result = compute_source_ref("remote_ingest", event_id="evt-abc123")
        self.assertEqual(result, "remote:evt-abc123")

    def test_remote_ingest_missing_event_id_raises(self) -> None:
        with self.assertRaisesRegex(ValueError, "event_id is required"):
            compute_source_ref("remote_ingest")

    def test_remote_ingest_none_event_id_raises(self) -> None:
        with self.assertRaisesRegex(ValueError, "event_id is required"):
            compute_source_ref("remote_ingest", event_id=None)

    def test_entire_returns_entire_uri(self) -> None:
        result = compute_source_ref("entire", checkpoint_id="deadbeef")
        self.assertEqual(result, "entire:deadbeef")

    def test_entire_missing_checkpoint_id_raises(self) -> None:
        with self.assertRaisesRegex(ValueError, "checkpoint_id is required"):
            compute_source_ref("entire")

    def test_entire_none_checkpoint_id_raises(self) -> None:
        with self.assertRaisesRegex(ValueError, "checkpoint_id is required"):
            compute_source_ref("entire", checkpoint_id=None)

    def test_unknown_source_id_raises(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown source_id"):
            compute_source_ref("s3_bucket", source_file="whatever")

    def test_unknown_source_id_empty_string_raises(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown source_id"):
            compute_source_ref("")


# ---------------------------------------------------------------------------
# Helpers for repository tests
# ---------------------------------------------------------------------------

def _minimal_session(session_id: str = "sess-001") -> dict:
    """Return the minimum valid session_data dict for upsert."""
    return {
        "id": session_id,
        "taskId": "task-1",
        "status": "completed",
        "model": "claude-opus-4",
        "platformType": "Claude Code",
        "platformVersion": "1.0",
        "durationSeconds": 10,
        "tokensIn": 100,
        "tokensOut": 200,
        "modelIOTokens": 300,
        "totalCost": 0.001,
        "sourceFile": "projects/my-proj/session.jsonl",
    }


_CREATE_SESSIONS_TABLE = """
    CREATE TABLE sessions (
        id TEXT PRIMARY KEY,
        project_id TEXT,
        task_id TEXT,
        status TEXT,
        model TEXT,
        platform_type TEXT,
        platform_version TEXT,
        platform_versions_json TEXT,
        platform_version_transitions_json TEXT,
        duration_seconds REAL,
        tokens_in INTEGER,
        tokens_out INTEGER,
        model_io_tokens INTEGER,
        cache_creation_input_tokens INTEGER,
        cache_read_input_tokens INTEGER,
        cache_input_tokens INTEGER,
        observed_tokens INTEGER,
        tool_reported_tokens INTEGER,
        tool_result_input_tokens INTEGER,
        tool_result_output_tokens INTEGER,
        tool_result_cache_creation_input_tokens INTEGER,
        tool_result_cache_read_input_tokens INTEGER,
        total_cost REAL,
        quality_rating INTEGER,
        friction_rating INTEGER,
        git_commit_hash TEXT,
        git_commit_hashes_json TEXT,
        git_author TEXT,
        git_branch TEXT,
        session_type TEXT,
        parent_session_id TEXT,
        root_session_id TEXT,
        agent_id TEXT,
        thread_kind TEXT,
        conversation_family_id TEXT,
        context_inheritance TEXT,
        fork_parent_session_id TEXT,
        fork_point_log_id TEXT,
        fork_point_entry_uuid TEXT,
        fork_point_parent_entry_uuid TEXT,
        fork_depth INTEGER,
        fork_count INTEGER,
        started_at TEXT,
        ended_at TEXT,
        created_at TEXT,
        updated_at TEXT,
        source_file TEXT,
        dates_json TEXT,
        timeline_json TEXT,
        impact_history_json TEXT,
        thinking_level TEXT,
        session_forensics_json TEXT,
        source_ref TEXT
    )
"""


# ---------------------------------------------------------------------------
# Repository write-path tests
# ---------------------------------------------------------------------------

class SessionsSourceRefRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await self.db.execute(_CREATE_SESSIONS_TABLE)
        await self.db.commit()
        self.repo = SqliteSessionRepository(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def _source_ref(self, session_id: str) -> str | None:
        async with self.db.execute(
            "SELECT source_ref FROM sessions WHERE id = ?", (session_id,)
        ) as cur:
            row = await cur.fetchone()
        self.assertIsNotNone(row)
        return row["source_ref"]

    async def test_upsert_with_source_ref_persists_value(self) -> None:
        data = _minimal_session("sess-001")
        await self.repo.upsert(data, "proj-1", workspace_id="default-local", source_ref="fs:projects/my-proj/session.jsonl")
        self.assertEqual(await self._source_ref("sess-001"), "fs:projects/my-proj/session.jsonl")

    async def test_upsert_without_source_ref_leaves_column_null_on_insert(self) -> None:
        data = _minimal_session("sess-002")
        await self.repo.upsert(data, "proj-1", workspace_id="default-local")  # no source_ref kwarg
        self.assertIsNone(await self._source_ref("sess-002"))

    async def test_upsert_source_ref_updates_on_conflict_preserves_other_fields(self) -> None:
        """Re-upserting with source_ref should update source_ref; other fields preserved."""
        data = _minimal_session("sess-003")
        await self.repo.upsert(data, "proj-1", workspace_id="default-local")

        async with self.db.execute(
            "SELECT model, source_ref FROM sessions WHERE id = 'sess-003'"
        ) as cur:
            row_before = await cur.fetchone()
        self.assertEqual(row_before["model"], "claude-opus-4")
        self.assertIsNone(row_before["source_ref"])

        await self.repo.upsert(data, "proj-1", workspace_id="default-local", source_ref="fs:projects/my-proj/session.jsonl")

        async with self.db.execute(
            "SELECT model, source_ref FROM sessions WHERE id = 'sess-003'"
        ) as cur:
            row_after = await cur.fetchone()
        self.assertEqual(row_after["model"], "claude-opus-4")  # existing fields preserved
        self.assertEqual(row_after["source_ref"], "fs:projects/my-proj/session.jsonl")

    async def test_upsert_without_source_ref_does_not_clear_existing_source_ref(self) -> None:
        """Backwards-compat: upserting without source_ref must not NULL out an existing value."""
        data = _minimal_session("sess-004")
        await self.repo.upsert(data, "proj-1", workspace_id="default-local", source_ref="fs:projects/my-proj/session.jsonl")
        # Second upsert — legacy caller, no source_ref kwarg
        await self.repo.upsert(data, "proj-1", workspace_id="default-local")
        # COALESCE(excluded.source_ref, sessions.source_ref) must preserve original value
        self.assertEqual(
            await self._source_ref("sess-004"),
            "fs:projects/my-proj/session.jsonl",
        )

    async def test_upsert_source_ref_can_be_overwritten_when_new_value_provided(self) -> None:
        """A second upsert with a different non-None source_ref overwrites the old one."""
        data = _minimal_session("sess-005")
        await self.repo.upsert(data, "proj-1", workspace_id="default-local", source_ref="remote:evt-old")
        await self.repo.upsert(data, "proj-1", workspace_id="default-local", source_ref="remote:evt-new")
        self.assertEqual(await self._source_ref("sess-005"), "remote:evt-new")


if __name__ == "__main__":
    unittest.main()
