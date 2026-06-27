"""P6-008 (FU-4) — SSE wire-boundary end-to-end smoke test.

Closes the gap left by existing unit tests that cover individual layers in
isolation:
  - test_postgres_live_fanout.py → bus encode/decode + listener republish
  - test_live_router.py          → SSE endpoint via direct function call

This file wires the *full* NOTIFY → listener → broker → SSE path in a single
test, using the same ``_FakeAsyncpgConnection.fire_notification()`` technique
from test_postgres_live_fanout.py and the async response-body iterator
technique from test_live_router.py.

The single end-to-end scenario:
  1. Build a ``_FakeAsyncpgConnection`` + ``_FakeAsyncpgPool``.
  2. Attach a real ``PostgresLiveNotificationListener`` to the pool, publishing
     into a real ``InMemoryLiveEventBroker``.
  3. Subscribe the live SSE endpoint (``stream_live_updates``) to the relevant
     topic via ``_FakeRequest`` + the broker.
  4. Fire a NOTIFY through the fake connection for a session-invalidate event.
  5. Assert the SSE stream delivers a frame whose topic and kind match the
     expected session invalidate event.

Why this matters (FU-4 audit)
------------------------------
Each existing test proves one layer works.  No test proved the layers
compose correctly end-to-end before this one.  A serialisation mismatch or
topic-normalisation difference between the Postgres channel payload and the
SSE frame format would be invisible without this wire test.
"""
from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any

import aiosqlite

from backend.adapters.auth.local import LocalIdentityProvider, PermitAllAuthorizationPolicy
from backend.adapters.integrations.local import NoopIntegrationClient
from backend.adapters.jobs.local import InProcessJobScheduler
from backend.adapters.live_updates import InMemoryLiveEventBroker
from backend.adapters.live_updates.postgres_listener import PostgresLiveNotificationListener
from backend.adapters.storage.local import LocalStorageUnitOfWork
from backend.adapters.workspaces.local import ProjectManagerWorkspaceRegistry
from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext, WorkspaceScope
from backend.application.live_updates import (
    BrokerLiveEventPublisher,
    DEFAULT_BUS_RECOVERY_HINT,
    LiveDeliveryHint,
    LiveEventMessage,
)
from backend.application.live_updates.bus import (
    LiveEventBusEnvelope,
    encode_live_event_bus_envelope,
    live_event_bus_envelope_from_message,
)
from backend.application.live_updates.topics import session_topic
from backend.application.ports import CorePorts
from backend.project_manager import ProjectManager
from backend.routers.live import stream_live_updates


# ---------------------------------------------------------------------------
# Shared fake asyncpg helpers (mirrors test_postgres_live_fanout.py)
# ---------------------------------------------------------------------------


class _FakeAsyncpgConnection:
    """Minimal asyncpg connection stub with synchronous notification dispatch."""

    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[Any, ...]]] = []
        self.listeners: list[tuple[str, Callable[[Any, int, str, str], None]]] = []

    async def execute(self, query: str, *args: Any) -> str:
        self.executed.append((query, args))
        return "SELECT 1"

    async def add_listener(self, channel: str, callback: Callable[[Any, int, str, str], None]) -> None:
        self.listeners.append((channel, callback))

    async def remove_listener(self, channel: str, callback: Callable[[Any, int, str, str], None]) -> None:
        self.listeners = [
            (ch, cb) for ch, cb in self.listeners if not (ch == channel and cb == callback)
        ]

    def fire_notification(self, channel: str, payload: str, *, pid: int = 1234) -> None:
        """Synchronously invoke all listeners registered for *channel*.

        Mirrors ``_FakeAsyncpgConnection.fire_notification`` in
        test_postgres_live_fanout.py exactly so test authors can cross-reference.
        """
        for ch, callback in tuple(self.listeners):
            if ch == channel:
                callback(self, pid, channel, payload)


class _FakeAsyncpgPool:
    """Minimal asyncpg pool stub that hands out a single shared connection."""

    def __init__(self, connection: _FakeAsyncpgConnection) -> None:
        self.connection = connection

    async def acquire(self) -> _FakeAsyncpgConnection:
        return self.connection

    async def release(self, connection: _FakeAsyncpgConnection) -> None:
        pass  # no-op; connection is not actually pooled in this stub


# ---------------------------------------------------------------------------
# SSE frame decoder (mirrors _decode_frame in test_live_router.py)
# ---------------------------------------------------------------------------


def _decode_sse_frame(chunk: bytes) -> dict[str, object]:
    """Parse a raw SSE chunk (bytes) into a dict with 'event', 'id', and payload fields."""
    text = chunk.decode("utf-8").strip()
    fields: dict[str, str] = {}
    for line in text.splitlines():
        if ": " in line:
            key, value = line.split(": ", 1)
            fields[key] = value
    payload_dict = json.loads(fields["data"])
    payload_dict["event"] = fields.get("event")
    payload_dict["_id"] = fields.get("id")
    return payload_dict


# ---------------------------------------------------------------------------
# Fake HTTP request (mirrors _FakeRequest in test_live_router.py)
# ---------------------------------------------------------------------------


class _FakeRequest:
    """Fake FastAPI Request that disconnects after a configurable number of is_disconnected checks."""

    def __init__(self, disconnect_after_checks: int = 999) -> None:
        self._disconnect_after = disconnect_after_checks
        self._checks = 0

    async def is_disconnected(self) -> bool:
        self._checks += 1
        return self._checks > self._disconnect_after


# ---------------------------------------------------------------------------
# Helper: wait until a condition is true (with timeout)
# ---------------------------------------------------------------------------


async def _wait_until(predicate: Callable[[], bool], *, timeout_seconds: float = 1.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while not predicate():
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError(
                f"Timed out waiting for condition after {timeout_seconds}s"
            )
        await asyncio.sleep(0.01)


# ---------------------------------------------------------------------------
# The end-to-end wire test
# ---------------------------------------------------------------------------


class TestSSEWireBoundaryEndToEnd(unittest.IsolatedAsyncioTestCase):
    """FU-4: full NOTIFY → listener → broker → SSE wire path in one test.

    This is intentionally a single, focused end-to-end smoke test.
    It does NOT replace the unit tests for individual layers; it verifies that
    the composed path delivers events correctly.
    """

    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        manager = ProjectManager(Path(self._tmp.name) / "projects.json")
        self._db = await aiosqlite.connect(":memory:")

        # Build CorePorts with local (test-safe) adapters.
        self._core_ports = CorePorts(
            identity_provider=LocalIdentityProvider(),
            authorization_policy=PermitAllAuthorizationPolicy(),
            workspace_registry=ProjectManagerWorkspaceRegistry(manager),
            storage=LocalStorageUnitOfWork(self._db),
            job_scheduler=InProcessJobScheduler(),
            integration_client=NoopIntegrationClient(),
        )
        self._request_context = RequestContext(
            principal=Principal(subject="test:operator", display_name="Operator", auth_mode="local"),
            workspace=WorkspaceScope(workspace_id="wire-project", root_path=Path(self._tmp.name)),
            project=ProjectScope(
                project_id="wire-project",
                project_name="Wire Project",
                root_path=Path(self._tmp.name),
                sessions_dir=Path(self._tmp.name) / "sessions",
                docs_dir=Path(self._tmp.name) / "docs",
                progress_dir=Path(self._tmp.name) / "progress",
            ),
            runtime_profile="test",
            trace=TraceContext(request_id="req-wire-1"),
        )

        # Build the full notification pipeline.
        self._fake_conn = _FakeAsyncpgConnection()
        self._fake_pool = _FakeAsyncpgPool(self._fake_conn)
        self._broker = InMemoryLiveEventBroker(replay_buffer_size=10)
        api_publisher = BrokerLiveEventPublisher(self._broker)
        self._listener = PostgresLiveNotificationListener(
            db=self._fake_pool,
            publisher=api_publisher,
            startup_timeout_seconds=0.5,
        )
        await self._listener.start()

    async def asyncTearDown(self) -> None:
        await self._listener.stop()
        await self._broker.close()
        await self._db.close()
        self._tmp.cleanup()

    async def test_notify_delivers_session_invalidate_frame_through_sse(self) -> None:
        """FU-4: firing a NOTIFY reaches the SSE subscriber as an invalidate frame.

        Wire path exercised:
          _FakeAsyncpgConnection.fire_notification
            → PostgresLiveNotificationListener._handle_notification
              → _republish_notification (decode bus envelope)
                → BrokerLiveEventPublisher.publish_invalidation
                  → InMemoryLiveEventBroker (subscription queue)
                    → stream_live_updates (SSE endpoint body iterator)
                      → assert frame topic/kind
        """
        session_id = "session-wire-001"
        topic = session_topic(session_id)  # e.g. "session.session-wire-001"

        # Build a compact bus envelope (as the worker would emit via PostgresNotifyLiveEventBus).
        message = LiveEventMessage(
            topic=topic,
            kind="invalidate",
            payload={"sessionId": session_id, "reason": "sync"},
            occurred_at="2026-06-01T10:00:00+00:00",
            delivery=LiveDeliveryHint(replayable=False),
        )
        envelope = live_event_bus_envelope_from_message(message)
        raw_payload = encode_live_event_bus_envelope(envelope)

        # Open the SSE stream subscribed to the session topic.
        response = await stream_live_updates(
            request=_FakeRequest(disconnect_after_checks=5),
            topic=[topic],
            cursor=[],
            request_context=self._request_context,
            core_ports=self._core_ports,
            live_broker=self._broker,
        )

        self.assertEqual(
            response.media_type,
            "text/event-stream",
            "SSE endpoint must return text/event-stream",
        )

        # Fire the NOTIFY on the fake connection — this triggers the listener callback.
        self._fake_conn.fire_notification(
            self._listener.channel,
            raw_payload,
            pid=9_001,
        )

        # Wait until the listener has republished the event to the broker.
        await _wait_until(
            lambda: self._listener.status_snapshot()["republished"] >= 1,
            timeout_seconds=2.0,
        )

        # Read one frame from the SSE body iterator.
        frame_chunk = await asyncio.wait_for(
            anext(response.body_iterator),
            timeout=2.0,
        )
        await response.body_iterator.aclose()

        frame = _decode_sse_frame(frame_chunk)

        # Assertions: topic and kind delivered correctly through the full wire path.
        self.assertEqual(
            frame.get("event"),
            "invalidate",
            f"Expected SSE event='invalidate', got event='{frame.get('event')}'. "
            f"Full frame: {frame}",
        )
        self.assertEqual(
            frame.get("topic"),
            topic,
            f"Expected SSE topic='{topic}', got topic='{frame.get('topic')}'. "
            f"Full frame: {frame}",
        )

        # Verify listener counters show a clean republish (no errors).
        snapshot = self._listener.status_snapshot()
        self.assertEqual(snapshot["received"], 1, "Listener must have received exactly 1 notification")
        self.assertEqual(snapshot["republished"], 1, "Listener must have republished exactly 1 notification")
        self.assertEqual(snapshot["malformed"], 0, "No malformed notifications expected")
        self.assertEqual(snapshot["publishErrors"], 0, "No publish errors expected")
        self.assertEqual(self._broker.stats().active_subscribers, 0, "Subscriber must have closed cleanly")
