import asyncio
import json
import tempfile
import unittest
from pathlib import Path

import aiosqlite
from fastapi import HTTPException

import backend.routers.live as live_router_module
from backend.adapters.auth.local import LocalIdentityProvider, PermitAllAuthorizationPolicy
from backend.adapters.integrations.local import NoopIntegrationClient
from backend.adapters.jobs.local import InProcessJobScheduler
from backend.adapters.live_updates import InMemoryLiveEventBroker
from backend.adapters.storage.local import FactoryStorageUnitOfWork
from backend.adapters.workspaces.local import ProjectManagerWorkspaceRegistry
from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext, WorkspaceScope
from backend.application.live_updates import BrokerLiveEventPublisher, LiveTopicCursor
from backend.application.ports import CorePorts
from backend.application.live_updates.topics import encode_cursor, session_transcript_topic
from backend.project_manager import ProjectManager
from backend.routers.live import stream_live_updates


class _FakeRequest:
    def __init__(self, disconnect_after_checks: int = 999) -> None:
        self._disconnect_after_checks = disconnect_after_checks
        self._checks = 0

    async def is_disconnected(self) -> bool:
        self._checks += 1
        return self._checks > self._disconnect_after_checks


def _decode_frame(chunk: bytes) -> dict[str, object]:
    text = chunk.decode("utf-8").strip()
    fields: dict[str, str] = {}
    for line in text.splitlines():
        key, value = line.split(": ", 1)
        fields[key] = value
    payload = json.loads(fields["data"])
    payload["event"] = fields["event"]
    payload["id"] = fields.get("id")
    return payload


class LiveRouterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        manager = ProjectManager(Path(self._tmp.name) / "projects.json")
        self.db = await aiosqlite.connect(":memory:")
        self.core_ports = CorePorts(
            identity_provider=LocalIdentityProvider(),
            authorization_policy=PermitAllAuthorizationPolicy(),
            workspace_registry=ProjectManagerWorkspaceRegistry(manager),
            storage=FactoryStorageUnitOfWork(self.db),
            job_scheduler=InProcessJobScheduler(),
            integration_client=NoopIntegrationClient(),
        )
        self.request_context = RequestContext(
            principal=Principal(subject="test:operator", display_name="Operator", auth_mode="local"),
            workspace=WorkspaceScope(workspace_id="project-1", root_path=Path(self._tmp.name)),
            project=ProjectScope(
                project_id="project-1",
                project_name="Project 1",
                root_path=Path(self._tmp.name),
                sessions_dir=Path(self._tmp.name) / "sessions",
                docs_dir=Path(self._tmp.name) / "docs",
                progress_dir=Path(self._tmp.name) / "progress",
            ),
            runtime_profile="test",
            trace=TraceContext(request_id="req-live-1"),
        )
        self.broker = InMemoryLiveEventBroker(replay_buffer_size=2)
        self.publisher = BrokerLiveEventPublisher(self.broker)

    async def asyncTearDown(self) -> None:
        await self.broker.close()
        await self.db.close()
        self._tmp.cleanup()

    async def test_stream_endpoint_emits_replay_and_live_frames(self) -> None:
        topic = "execution.run.run-123"
        first = await self.publisher.publish_append(topic=topic, payload={"step": 1}, occurred_at="2026-03-14T10:00:00+00:00")
        await self.publisher.publish_append(topic=topic, payload={"step": 2}, occurred_at="2026-03-14T10:00:01+00:00")

        response = await stream_live_updates(
            request=_FakeRequest(),
            topic=[topic],
            cursor=[first.cursor],
            request_context=self.request_context,
            core_ports=self.core_ports,
            live_broker=self.broker,
        )

        self.assertEqual(response.media_type, "text/event-stream")
        replay_chunk = await anext(response.body_iterator)
        replay_payload = _decode_frame(replay_chunk)
        self.assertEqual(replay_payload["event"], "append")
        self.assertEqual(replay_payload["payload"]["step"], 2)

        await self.publisher.publish_append(topic=topic, payload={"step": 3}, occurred_at="2026-03-14T10:00:02+00:00")
        live_chunk = await asyncio.wait_for(anext(response.body_iterator), timeout=0.2)
        live_payload = _decode_frame(live_chunk)
        self.assertEqual(live_payload["payload"]["step"], 3)

        await response.body_iterator.aclose()
        self.assertEqual(self.broker.stats().active_subscribers, 0)

    async def test_stream_endpoint_emits_snapshot_required_when_cursor_is_out_of_buffer(self) -> None:
        topic = "execution.run.run-gap"
        await self.publisher.publish_append(topic=topic, payload={"step": 1}, occurred_at="2026-03-14T10:00:00+00:00")
        await self.publisher.publish_append(topic=topic, payload={"step": 2}, occurred_at="2026-03-14T10:00:01+00:00")
        await self.publisher.publish_append(topic=topic, payload={"step": 3}, occurred_at="2026-03-14T10:00:02+00:00")

        response = await stream_live_updates(
            request=_FakeRequest(disconnect_after_checks=4),
            topic=[topic],
            cursor=[encode_cursor(LiveTopicCursor(topic=topic, sequence=0))],
            request_context=self.request_context,
            core_ports=self.core_ports,
            live_broker=self.broker,
        )

        gap_chunk = await anext(response.body_iterator)
        gap_payload = _decode_frame(gap_chunk)
        self.assertEqual(gap_payload["event"], "snapshot_required")
        self.assertEqual(gap_payload["payload"]["latestSequence"], 3)
        await response.body_iterator.aclose()

    async def test_stream_endpoint_emits_heartbeat_when_idle(self) -> None:
        topic = "execution.run.run-idle"
        response = None
        previous = live_router_module.config.CCDASH_LIVE_HEARTBEAT_SECONDS
        live_router_module.config.CCDASH_LIVE_HEARTBEAT_SECONDS = 1
        try:
            response = await stream_live_updates(
                request=_FakeRequest(disconnect_after_checks=3),
                topic=[topic],
                cursor=[],
                request_context=self.request_context,
                core_ports=self.core_ports,
                live_broker=self.broker,
            )
            heartbeat_chunk = await asyncio.wait_for(anext(response.body_iterator), timeout=1.2)
        finally:
            live_router_module.config.CCDASH_LIVE_HEARTBEAT_SECONDS = previous
            if response is not None:
                await response.body_iterator.aclose()

        heartbeat_payload = _decode_frame(heartbeat_chunk)
        self.assertEqual(heartbeat_payload["event"], "heartbeat")
        self.assertEqual(heartbeat_payload["topic"], "system.heartbeat")

    async def test_stream_endpoint_rejects_cursor_for_unsubscribed_topic(self) -> None:
        with self.assertRaises(HTTPException) as exc_info:
            await stream_live_updates(
                request=_FakeRequest(),
                topic=["execution.run.run-1"],
                cursor=[encode_cursor(LiveTopicCursor(topic="execution.run.run-2", sequence=1))],
                request_context=self.request_context,
                core_ports=self.core_ports,
                live_broker=self.broker,
            )
        self.assertEqual(exc_info.exception.status_code, 400)
        self.assertIn("Cursor topics must be part of the subscription", str(exc_info.exception.detail))

    async def test_transcript_topic_replay_and_gap_snapshot_required(self) -> None:
        topic = session_transcript_topic("session-123")
        first = await self.publisher.publish_append(
            topic=topic,
            payload={
                "sessionId": "session-123",
                "entryId": "log-1",
                "sequenceNo": 1,
                "kind": "message",
                "createdAt": "2026-03-14T10:00:00+00:00",
                "payload": {"id": "log-1", "content": "hello"},
            },
            occurred_at="2026-03-14T10:00:00+00:00",
        )
        await self.publisher.publish_append(
            topic=topic,
            payload={
                "sessionId": "session-123",
                "entryId": "log-2",
                "sequenceNo": 2,
                "kind": "message",
                "createdAt": "2026-03-14T10:00:01+00:00",
                "payload": {"id": "log-2", "content": "world"},
            },
            occurred_at="2026-03-14T10:00:01+00:00",
        )
        await self.publisher.publish_append(
            topic=topic,
            payload={
                "sessionId": "session-123",
                "entryId": "log-3",
                "sequenceNo": 3,
                "kind": "message",
                "createdAt": "2026-03-14T10:00:02+00:00",
                "payload": {"id": "log-3", "content": "buffer overflow"},
            },
            occurred_at="2026-03-14T10:00:02+00:00",
        )

        response = await stream_live_updates(
            request=_FakeRequest(),
            topic=[topic],
            cursor=[first.cursor],
            request_context=self.request_context,
            core_ports=self.core_ports,
            live_broker=self.broker,
        )

        replay_chunk = await anext(response.body_iterator)
        replay_payload = _decode_frame(replay_chunk)
        self.assertEqual(replay_payload["event"], "append")
        self.assertEqual(replay_payload["payload"]["entryId"], "log-2")

        await response.body_iterator.aclose()

        gap_response = await stream_live_updates(
            request=_FakeRequest(disconnect_after_checks=4),
            topic=[topic],
            cursor=[encode_cursor(LiveTopicCursor(topic=topic, sequence=0))],
            request_context=self.request_context,
            core_ports=self.core_ports,
            live_broker=self.broker,
        )
        gap_chunk = await anext(gap_response.body_iterator)
        gap_payload = _decode_frame(gap_chunk)
        self.assertEqual(gap_payload["event"], "snapshot_required")
        self.assertEqual(gap_payload["topic"], topic)
        await gap_response.body_iterator.aclose()
