"""Unit tests for backend.application.ports.ingest."""
from __future__ import annotations

import dataclasses
from collections.abc import AsyncIterator

import pytest

from backend.application.ports.ingest import (
    IngestCursor,
    IngestEvent,
    SessionIngestSource,
)


# ---------------------------------------------------------------------------
# Frozen dataclass assertions
# ---------------------------------------------------------------------------


def _make_event() -> IngestEvent:
    return IngestEvent(
        source_ref="fs:sessions/abc.jsonl",
        project_id="proj-1",
        workspace_id="default",
        payload={"id": "s1"},
        schema_version="1.0",
        cursor_value="2026-05-12T00:00:00Z",
        occurred_at="2026-05-12T00:00:00Z",
    )


def _make_cursor() -> IngestCursor:
    return IngestCursor(
        source_id="filesystem",
        project_id="proj-1",
        workspace_id="default",
        last_cursor=None,
        last_ingest_at=None,
        error_count=0,
    )


class TestIngestEventFrozen:
    def test_is_dataclass(self) -> None:
        assert dataclasses.is_dataclass(IngestEvent)

    def test_mutation_raises(self) -> None:
        event = _make_event()
        with pytest.raises(dataclasses.FrozenInstanceError):
            event.project_id = "other"  # type: ignore[misc]

    def test_fields_present(self) -> None:
        event = _make_event()
        assert event.source_ref == "fs:sessions/abc.jsonl"
        assert event.schema_version == "1.0"
        assert event.workspace_id == "default"


class TestIngestCursorFrozen:
    def test_is_dataclass(self) -> None:
        assert dataclasses.is_dataclass(IngestCursor)

    def test_mutation_raises(self) -> None:
        cursor = _make_cursor()
        with pytest.raises(dataclasses.FrozenInstanceError):
            cursor.error_count = 99  # type: ignore[misc]

    def test_optional_fields_default_none(self) -> None:
        cursor = _make_cursor()
        assert cursor.last_error is None
        assert cursor.last_error_at is None

    def test_optional_fields_settable(self) -> None:
        cursor = IngestCursor(
            source_id="remote_ingest",
            project_id="proj-2",
            workspace_id="ws-a",
            last_cursor="uuid-v7-xyz",
            last_ingest_at="2026-05-12T01:00:00Z",
            error_count=1,
            last_error="connection reset",
            last_error_at="2026-05-12T00:59:00Z",
        )
        assert cursor.last_error == "connection reset"


# ---------------------------------------------------------------------------
# SessionIngestSource Protocol — runtime_checkable isinstance check
# ---------------------------------------------------------------------------


class _StubSource:
    """Minimal stub that satisfies the SessionIngestSource structural protocol."""

    source_id: str = "stub"

    async def stream(self, *, since: IngestCursor) -> AsyncIterator[IngestEvent]:  # type: ignore[override]
        return
        yield  # make it an async generator

    async def ack(self, event: IngestEvent) -> None:
        pass


class TestSessionIngestSourceProtocol:
    def test_stub_isinstance(self) -> None:
        stub = _StubSource()
        assert isinstance(stub, SessionIngestSource)

    def test_missing_source_id_not_instance(self) -> None:
        class _Bad:
            async def stream(self, *, since: IngestCursor) -> AsyncIterator[IngestEvent]:  # type: ignore[override]
                return
                yield

            async def ack(self, event: IngestEvent) -> None:
                pass

        # Python 3.12+ runtime_checkable checks non-callable Protocol members too,
        # so a class missing source_id fails the isinstance check.
        bad = _Bad()
        assert not isinstance(bad, SessionIngestSource)

    def test_missing_ack_not_instance(self) -> None:
        class _NoAck:
            source_id: str = "no_ack"

            async def stream(self, *, since: IngestCursor) -> AsyncIterator[IngestEvent]:  # type: ignore[override]
                return
                yield

        no_ack = _NoAck()
        assert not isinstance(no_ack, SessionIngestSource)

    def test_missing_stream_not_instance(self) -> None:
        class _NoStream:
            source_id: str = "no_stream"

            async def ack(self, event: IngestEvent) -> None:
                pass

        no_stream = _NoStream()
        assert not isinstance(no_stream, SessionIngestSource)
