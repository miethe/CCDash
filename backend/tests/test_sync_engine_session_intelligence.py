import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiosqlite

from backend.db.factory import get_document_repository, get_session_intelligence_repository
from backend.db.sqlite_migrations import run_migrations
from backend.db.sync_engine import SyncEngine


class _ParsedSession:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def model_dump(self) -> dict:
        return dict(self._payload)


class SyncEngineSessionIntelligenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.engine = SyncEngine(self.db)
        self.engine._replace_session_usage_attribution = AsyncMock(return_value={"events": 0, "attributions": 0})  # type: ignore[attr-defined]
        self.engine._replace_session_telemetry_events = AsyncMock(return_value=0)  # type: ignore[attr-defined]
        self.engine._replace_session_commit_correlations = AsyncMock(return_value=0)  # type: ignore[attr-defined]
        self.engine._maybe_enqueue_telemetry_export = AsyncMock(return_value=None)  # type: ignore[attr-defined]
        self.engine._derive_session_observability_fields = AsyncMock(return_value={})  # type: ignore[attr-defined]

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_sync_single_session_writes_session_intelligence_facts(self) -> None:
        document_repo = get_document_repository(self.db)
        await document_repo.upsert(
            {
                "id": "doc-1",
                "title": "Plan",
                "filePath": "docs/project_plans/implementation_plans/features/feature-1.md",
                "canonicalPath": "docs/project_plans/implementation_plans/features/feature-1.md",
                "docType": "implementation_plan",
                "frontmatter": {
                    "linkedFeatures": ["feature-1"],
                    "context_files": ["backend/services"],
                },
                "content": "plan",
                "createdAt": "2026-04-02T00:00:00Z",
                "updatedAt": "2026-04-02T00:00:00Z",
            },
            "project-1",
        )

        session_payload = {
            "id": "S-INT-1",
            "taskId": "feature-1",
            "status": "completed",
            "model": "gpt-5",
            "startedAt": "2026-04-02T10:00:00Z",
            "endedAt": "2026-04-02T10:05:00Z",
            "logs": [
                {
                    "id": "log-1",
                    "timestamp": "2026-04-02T10:00:01Z",
                    "speaker": "user",
                    "type": "message",
                    "content": "this is blocked and failing",
                }
            ],
            "toolsUsed": [],
            "updatedFiles": [
                {
                    "filePath": "backend/services/session_scope_drift.py",
                    "action": "update",
                    "timestamp": "2026-04-02T10:00:02Z",
                    "additions": 4,
                    "deletions": 1,
                    "sourceLogId": "log-1",
                }
            ],
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

        repo = get_session_intelligence_repository(self.db)
        sentiment = await repo.list_session_sentiment_facts("S-INT-1")
        churn = await repo.list_session_code_churn_facts("S-INT-1")
        scope = await repo.list_session_scope_drift_facts("S-INT-1")

        self.assertEqual(len(sentiment), 1)
        self.assertEqual(sentiment[0]["sentiment_label"], "negative")
        self.assertEqual(len(churn), 1)
        self.assertEqual(churn[0]["file_path"], "backend/services/session_scope_drift.py")
        self.assertEqual(len(scope), 1)
        self.assertEqual(scope[0]["matched_path_count"], 1)


if __name__ == "__main__":
    unittest.main()
