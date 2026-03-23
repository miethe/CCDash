import unittest

from backend.application.live_updates import set_live_event_publisher
from backend.application.live_updates.domain_events import (
    publish_feature_invalidation,
    publish_ops_invalidation,
    publish_execution_run_events,
    publish_execution_run_snapshot,
    publish_session_transcript_append,
    publish_session_snapshot,
    publish_test_invalidation,
    SessionTranscriptAppendPayload,
)
from backend.application.live_updates.topics import session_transcript_topic


class _RecordingPublisher:
    def __init__(self) -> None:
        self.append_calls: list[dict] = []
        self.invalidate_calls: list[dict] = []

    async def publish_append(self, **kwargs):  # type: ignore[no-untyped-def]
        self.append_calls.append(kwargs)
        return None

    async def publish_invalidation(self, **kwargs):  # type: ignore[no-untyped-def]
        self.invalidate_calls.append(kwargs)
        return None


class LiveDomainPublisherTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.publisher = _RecordingPublisher()
        set_live_event_publisher(self.publisher)

    async def asyncTearDown(self) -> None:
        set_live_event_publisher(None)

    async def test_publish_execution_run_snapshot_emits_invalidation(self) -> None:
        await publish_execution_run_snapshot(
            {
                "id": "run-1",
                "feature_id": "feat-1",
                "status": "running",
                "updated_at": "2026-03-15T14:00:00Z",
                "started_at": "2026-03-15T13:59:00Z",
                "ended_at": "",
                "exit_code": None,
                "requires_approval": False,
            }
        )

        self.assertEqual(len(self.publisher.invalidate_calls), 1)
        call = self.publisher.invalidate_calls[0]
        self.assertEqual(call["topic"], "execution.run.run-1")
        self.assertEqual(call["payload"]["status"], "running")

    async def test_publish_execution_run_events_emits_append_payloads(self) -> None:
        await publish_execution_run_events(
          "run-2",
          [
            {
                "sequence_no": 7,
                "stream": "stdout",
                "event_type": "output",
                "payload_text": "hello",
                "payload_json": {"line": 1},
                "occurred_at": "2026-03-15T14:01:00Z",
            }
          ],
        )

        self.assertEqual(len(self.publisher.append_calls), 1)
        call = self.publisher.append_calls[0]
        self.assertEqual(call["topic"], "execution.run.run-2")
        self.assertEqual(call["payload"]["sequenceNo"], 7)
        self.assertEqual(call["payload"]["payload"]["line"], 1)

    async def test_publish_session_snapshot_emits_recovery_invalidation(self) -> None:
        await publish_session_snapshot(
            {
                "id": "session-1",
                "status": "active",
                "updatedAt": "2026-03-15T14:02:00Z",
            },
            log_count=42,
            source="sync",
        )

        self.assertEqual(len(self.publisher.invalidate_calls), 1)
        call = self.publisher.invalidate_calls[0]
        self.assertEqual(call["topic"], "session.session-1")
        self.assertEqual(call["payload"]["logCount"], 42)
        self.assertEqual(call["payload"]["source"], "sync")

    async def test_publish_feature_invalidation_emits_feature_and_project_topics(self) -> None:
        await publish_feature_invalidation(
            "project-1",
            feature_id="feature-1",
            reason="feature_status_updated",
            source="features_api",
            payload={"status": "in-progress"},
        )

        self.assertEqual(len(self.publisher.invalidate_calls), 2)
        topics = {call["topic"] for call in self.publisher.invalidate_calls}
        self.assertEqual(topics, {"feature.feature-1", "project.project-1.features"})

    async def test_publish_test_and_ops_invalidations_emit_project_topics(self) -> None:
        await publish_test_invalidation(
            "project-1",
            reason="ingest_run",
            source="tests_api",
            payload={"runId": "run-1"},
        )
        await publish_ops_invalidation(
            "project-1",
            reason="operation_finished",
            source="sync_engine",
            payload={"operationId": "OP-1"},
        )

        self.assertEqual(len(self.publisher.invalidate_calls), 2)
        self.assertEqual(self.publisher.invalidate_calls[0]["topic"], "project.project-1.tests")
        self.assertEqual(self.publisher.invalidate_calls[0]["payload"]["runId"], "run-1")
        self.assertEqual(self.publisher.invalidate_calls[1]["topic"], "project.project-1.ops")
        self.assertEqual(self.publisher.invalidate_calls[1]["payload"]["operationId"], "OP-1")

    async def test_session_transcript_topic_helper_and_append_payload(self) -> None:
        self.assertEqual(session_transcript_topic("session-1"), "session.session-1.transcript")

        payload = SessionTranscriptAppendPayload(
            session_id="session-1",
            entry_id="log-1",
            sequence_no=12,
            kind="assistant_message",
            created_at="2026-03-15T14:03:00Z",
            payload={
                "id": "log-1",
                "timestamp": "2026-03-15T14:03:00Z",
                "speaker": "agent",
                "type": "message",
                "content": "hello",
                "agentName": "Claude",
                "linkedSessionId": "session-child",
                "relatedToolCallId": "tool-1",
                "metadata": {"foo": "bar"},
                "toolCall": {"name": "write_file", "status": "success"},
            },
        )

        await publish_session_transcript_append(payload)

        self.assertEqual(len(self.publisher.append_calls), 1)
        call = self.publisher.append_calls[0]
        self.assertEqual(call["topic"], "session.session-1.transcript")
        self.assertEqual(call["payload"]["sessionId"], "session-1")
        self.assertEqual(call["payload"]["entryId"], "log-1")
        self.assertEqual(call["payload"]["sequenceNo"], 12)
        self.assertEqual(call["payload"]["kind"], "assistant_message")
        self.assertEqual(call["payload"]["payload"]["metadata"]["foo"], "bar")
        self.assertEqual(call["payload"]["payload"]["toolCall"]["name"], "write_file")
