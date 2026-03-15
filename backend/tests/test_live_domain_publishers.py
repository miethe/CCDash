import unittest

from backend.application.live_updates import set_live_event_publisher
from backend.application.live_updates.domain_events import (
    publish_execution_run_events,
    publish_execution_run_snapshot,
    publish_session_snapshot,
)


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
