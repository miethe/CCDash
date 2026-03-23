import unittest
from unittest.mock import AsyncMock, patch

from backend.application.live_updates.domain_events import SessionTranscriptAppendPayload
from backend.db.sync_engine import _publish_session_transcript_appends


class SyncEngineTranscriptLiveUpdateTests(unittest.IsolatedAsyncioTestCase):
    async def test_publish_session_transcript_appends_emits_only_strict_prefix_growth(self) -> None:
        session_dict = {"id": "session-1", "updatedAt": "2026-03-23T12:00:00Z"}
        previous_logs = [
            {
                "source_log_id": "log-1",
                "timestamp": "2026-03-23T11:58:00Z",
                "speaker": "user",
                "type": "message",
                "content": "start",
            },
            {
                "source_log_id": "log-2",
                "timestamp": "2026-03-23T11:59:00Z",
                "speaker": "agent",
                "type": "message",
                "content": "reply",
            },
        ]
        current_logs = [
            {
                "id": "log-1",
                "timestamp": "2026-03-23T11:58:00Z",
                "speaker": "user",
                "type": "message",
                "content": "start",
            },
            {
                "id": "log-2",
                "timestamp": "2026-03-23T11:59:00Z",
                "speaker": "agent",
                "type": "message",
                "content": "reply",
            },
            {
                "id": "log-3",
                "timestamp": "2026-03-23T12:00:00Z",
                "speaker": "agent",
                "type": "tool",
                "content": "next",
                "metadata": {"eventType": "tool_result"},
            },
        ]

        with patch("backend.db.sync_engine.publish_session_transcript_append", new_callable=AsyncMock) as publish_mock:
            published = await _publish_session_transcript_appends(
                session_dict,
                previous_logs=previous_logs,
                current_logs=current_logs,
            )

        self.assertTrue(published)
        publish_mock.assert_awaited_once()
        payload = publish_mock.await_args.args[0]
        self.assertIsInstance(payload, SessionTranscriptAppendPayload)
        self.assertEqual(payload.session_id, "session-1")
        self.assertEqual(payload.entry_id, "log-3")
        self.assertEqual(payload.sequence_no, 3)
        self.assertEqual(payload.payload["metadata"]["eventType"], "tool_result")

    async def test_publish_session_transcript_appends_rejects_rewrite_like_updates(self) -> None:
        session_dict = {"id": "session-1", "updatedAt": "2026-03-23T12:00:00Z"}
        previous_logs = [
            {"source_log_id": "log-1", "timestamp": "2026-03-23T11:58:00Z", "type": "message"},
            {"source_log_id": "log-2", "timestamp": "2026-03-23T11:59:00Z", "type": "message"},
        ]
        current_logs = [
            {"id": "log-1", "timestamp": "2026-03-23T11:58:00Z", "type": "message"},
            {"id": "log-9", "timestamp": "2026-03-23T12:00:00Z", "type": "message"},
        ]

        with patch("backend.db.sync_engine.publish_session_transcript_append", new_callable=AsyncMock) as publish_mock:
            published = await _publish_session_transcript_appends(
                session_dict,
                previous_logs=previous_logs,
                current_logs=current_logs,
            )

        self.assertFalse(published)
        publish_mock.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
