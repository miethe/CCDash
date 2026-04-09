import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiosqlite

from backend import config
from backend.config import StorageProfileConfig
from backend.db.sqlite_migrations import run_migrations
from backend.db.sync_engine import SyncEngine


class _ParsedSession:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def model_dump(self) -> dict:
        return dict(self._payload)


def _enterprise_storage_profile() -> StorageProfileConfig:
    return StorageProfileConfig(
        profile="enterprise",
        db_backend="postgres",
        database_url="postgresql://example/test",
        filesystem_source_of_truth=False,
        shared_postgres_enabled=False,
        isolation_mode="dedicated",
        schema_name="ccdash",
    )


class SyncEngineEnterpriseCanonicalTranscriptTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.engine = SyncEngine(self.db)

        # Keep this suite focused on transcript persistence behavior.
        self.engine._replace_session_usage_attribution = AsyncMock(return_value=0)  # type: ignore[attr-defined]
        self.engine._replace_session_telemetry_events = AsyncMock(return_value=0)  # type: ignore[attr-defined]
        self.engine._replace_session_commit_correlations = AsyncMock(return_value=0)  # type: ignore[attr-defined]
        self.engine._maybe_enqueue_telemetry_export = AsyncMock(return_value=None)  # type: ignore[attr-defined]
        self.engine._derive_session_observability_fields = AsyncMock(return_value={})  # type: ignore[attr-defined]

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_enterprise_mode_writes_canonical_transcript_and_clears_legacy_logs(self) -> None:
        session_payload = {
            "id": "S-ENT-1",
            "status": "completed",
            "model": "claude-sonnet-4-5",
            "startedAt": "2026-04-02T10:00:00Z",
            "endedAt": "2026-04-02T10:05:00Z",
            "logs": [
                {
                    "id": "log-1",
                    "timestamp": "2026-04-02T10:00:01Z",
                    "speaker": "user",
                    "type": "message",
                    "content": "hello",
                }
            ],
            "toolsUsed": [],
            "updatedFiles": [],
            "linkedArtifacts": [],
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            session_path = Path(tmp_dir) / "session.jsonl"
            session_path.write_text("{}\n", encoding="utf-8")
            with (
                patch.object(config, "STORAGE_PROFILE", _enterprise_storage_profile()),
                patch("backend.db.sync_engine.parse_session_file", return_value=_ParsedSession(session_payload)),
                patch("backend.db.sync_engine._publish_session_transcript_appends", AsyncMock(return_value=False)),
                patch("backend.db.sync_engine.publish_session_snapshot", AsyncMock(return_value=None)),
            ):
                synced = await self.engine._sync_single_session("project-1", session_path, force=True)

        self.assertTrue(synced)

        async with self.db.execute(
            "SELECT COUNT(*) FROM session_messages WHERE session_id = ?",
            ("S-ENT-1",),
        ) as cur:
            canonical_count = (await cur.fetchone())[0]
        self.assertEqual(canonical_count, 1)

        async with self.db.execute(
            "SELECT COUNT(*) FROM session_logs WHERE session_id = ?",
            ("S-ENT-1",),
        ) as cur:
            legacy_count = (await cur.fetchone())[0]
        self.assertEqual(legacy_count, 0)

    async def test_enterprise_mode_preserves_legacy_logs_when_canonical_projection_is_unavailable(self) -> None:
        session_payload = {
            "id": "S-ENT-2",
            "status": "completed",
            "model": "claude-sonnet-4-5",
            "startedAt": "2026-04-02T11:00:00Z",
            "endedAt": "2026-04-02T11:05:00Z",
            "logs": [
                {
                    "id": "log-legacy-1",
                    "timestamp": "2026-04-02T11:00:01Z",
                    "speaker": "assistant",
                    "type": "message",
                    "content": "fallback transcript",
                }
            ],
            "toolsUsed": [],
            "updatedFiles": [],
            "linkedArtifacts": [],
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            session_path = Path(tmp_dir) / "session.jsonl"
            session_path.write_text("{}\n", encoding="utf-8")
            with (
                patch.object(config, "STORAGE_PROFILE", _enterprise_storage_profile()),
                patch("backend.db.sync_engine.parse_session_file", return_value=_ParsedSession(session_payload)),
                patch("backend.db.sync_engine.project_session_messages", return_value=[]),
                patch("backend.db.sync_engine._publish_session_transcript_appends", AsyncMock(return_value=False)),
                patch("backend.db.sync_engine.publish_session_snapshot", AsyncMock(return_value=None)),
            ):
                synced = await self.engine._sync_single_session("project-1", session_path, force=True)

        self.assertTrue(synced)

        async with self.db.execute(
            "SELECT COUNT(*) FROM session_logs WHERE session_id = ?",
            ("S-ENT-2",),
        ) as cur:
            legacy_count = (await cur.fetchone())[0]
        self.assertEqual(legacy_count, 1)

        async with self.db.execute(
            "SELECT COUNT(*) FROM session_messages WHERE session_id = ?",
            ("S-ENT-2",),
        ) as cur:
            canonical_count = (await cur.fetchone())[0]
        self.assertEqual(canonical_count, 0)

    async def test_local_mode_keeps_legacy_logs_alongside_canonical_rows(self) -> None:
        session_payload = {
            "id": "S-LOC-1",
            "status": "completed",
            "model": "claude-sonnet-4-5",
            "startedAt": "2026-04-02T12:00:00Z",
            "endedAt": "2026-04-02T12:05:00Z",
            "logs": [
                {
                    "id": "log-local-1",
                    "timestamp": "2026-04-02T12:00:01Z",
                    "speaker": "user",
                    "type": "message",
                    "content": "local mode transcript",
                }
            ],
            "toolsUsed": [],
            "updatedFiles": [],
            "linkedArtifacts": [],
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            session_path = Path(tmp_dir) / "session.jsonl"
            session_path.write_text("{}\n", encoding="utf-8")
            with (
                patch("backend.db.sync_engine.parse_session_file", return_value=_ParsedSession(session_payload)),
                patch("backend.db.sync_engine._publish_session_transcript_appends", AsyncMock(return_value=False)),
                patch("backend.db.sync_engine.publish_session_snapshot", AsyncMock(return_value=None)),
            ):
                synced = await self.engine._sync_single_session("project-1", session_path, force=True)

        self.assertTrue(synced)

        async with self.db.execute(
            "SELECT COUNT(*) FROM session_messages WHERE session_id = ?",
            ("S-LOC-1",),
        ) as cur:
            canonical_count = (await cur.fetchone())[0]
        self.assertEqual(canonical_count, 1)

        async with self.db.execute(
            "SELECT COUNT(*) FROM session_logs WHERE session_id = ?",
            ("S-LOC-1",),
        ) as cur:
            legacy_count = (await cur.fetchone())[0]
        self.assertEqual(legacy_count, 1)
