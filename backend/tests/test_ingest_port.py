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


# ---------------------------------------------------------------------------
# _StubRemoteIngestSource — contract probe (NOT production code)
# ---------------------------------------------------------------------------
# This stub lives here to prove the SessionIngestSource Protocol holds for any
# non-filesystem implementation.  It is never imported by production modules.
# Cursor values use ISO-8601 timestamps with explicit microsecond offsets so
# lexicographic ordering is deterministic regardless of test execution time.


class _StubRemoteIngestSource:
    """Minimal remote-style ingest source for Protocol contract tests."""

    source_id: str = "remote_ingest"

    def __init__(self, events: list[IngestEvent]) -> None:
        self._events = events
        self.acked_cursors: list[str] = []

    async def stream(self, *, since: IngestCursor) -> AsyncIterator[IngestEvent]:  # type: ignore[override]
        start_cursor = since.last_cursor or ""
        for ev in self._events:
            if ev.cursor_value > start_cursor:  # lexicographic; fine for ISO timestamps
                yield ev

    async def ack(self, event: IngestEvent) -> None:
        self.acked_cursors.append(event.cursor_value)


# ---------------------------------------------------------------------------
# Helpers shared by the contract tests below
# ---------------------------------------------------------------------------

import unittest

import aiosqlite

from backend.db.repositories.ingest_cursors import SqliteIngestCursorRepository
from backend.db.sqlite_migrations import run_migrations


def _make_remote_event(cursor_value: str, seq: int = 0) -> IngestEvent:
    return IngestEvent(
        source_ref=f"remote:default:ev-{seq:03d}",
        project_id="proj-remote",
        workspace_id="default",
        payload={"seq": seq},
        schema_version="1.0",
        cursor_value=cursor_value,
        occurred_at=cursor_value,
    )


# Three events with explicit microsecond spacing so ordering is unambiguous.
_EV_A = _make_remote_event("2026-05-12T10:00:00.000000Z", seq=1)
_EV_B = _make_remote_event("2026-05-12T10:00:00.001000Z", seq=2)
_EV_C = _make_remote_event("2026-05-12T10:00:00.002000Z", seq=3)


# ---------------------------------------------------------------------------
# Contract tests
# ---------------------------------------------------------------------------


class TestStubRemoteIngestSourceProtocol(unittest.IsolatedAsyncioTestCase):
    """T2-007: ADR-009 §Hard Gates row 2 — stub satisfies the Protocol."""

    def test_stub_remote_satisfies_protocol(self) -> None:
        stub = _StubRemoteIngestSource([])
        assert isinstance(stub, SessionIngestSource)

    async def test_cursor_advances_after_upsert_via_repo(self) -> None:
        """Simulate the SyncEngine loop: get_or_create → stream → advance + ack.

        After the loop the ingest_cursors row must reflect the last cursor_value
        and error_count must be 0.
        """
        db = await aiosqlite.connect(":memory:")
        db.row_factory = aiosqlite.Row
        await run_migrations(db)
        repo = SqliteIngestCursorRepository(db)

        source = _StubRemoteIngestSource([_EV_A, _EV_B, _EV_C])

        cursor = await repo.get_or_create(
            source_id=source.source_id,
            project_id="proj-remote",
            workspace_id="default",
        )

        processed: list[str] = []
        async for event in source.stream(since=cursor):
            # Simulate a successful session upsert then advance.
            await repo.advance(
                source_id=source.source_id,
                project_id="proj-remote",
                workspace_id="default",
                cursor_value=event.cursor_value,
                occurred_at=event.occurred_at,
            )
            await source.ack(event)
            processed.append(event.cursor_value)

        assert processed == [_EV_A.cursor_value, _EV_B.cursor_value, _EV_C.cursor_value]
        assert source.acked_cursors == processed

        final_cursor = await repo.get_or_create(
            source_id=source.source_id,
            project_id="proj-remote",
            workspace_id="default",
        )
        assert final_cursor.last_cursor == _EV_C.cursor_value
        assert final_cursor.error_count == 0

        await db.close()

    async def test_crash_between_upsert_and_advance_is_idempotent(self) -> None:
        """Simulate a crash after upsert but before repo.advance().

        The cursor does not move.  On the next run, stream() re-yields the
        missed event because its cursor_value exceeds the unchanged watermark.
        ADR-009 §Risks row 1: "Cursor advances after upsert in the same DB
        transaction; integration test forces a crash between upsert and advance
        and asserts re-ingest is idempotent."
        """
        db = await aiosqlite.connect(":memory:")
        db.row_factory = aiosqlite.Row
        await run_migrations(db)
        repo = SqliteIngestCursorRepository(db)

        source = _StubRemoteIngestSource([_EV_A, _EV_B])

        # --- First run: advance _EV_A, crash before advancing _EV_B ---
        cursor = await repo.get_or_create(
            source_id=source.source_id,
            project_id="proj-remote",
            workspace_id="default",
        )
        events_first_run: list[str] = []
        async for event in source.stream(since=cursor):
            if event.cursor_value == _EV_A.cursor_value:
                # Normal path: upsert succeeded, advance cursor.
                await repo.advance(
                    source_id=source.source_id,
                    project_id="proj-remote",
                    workspace_id="default",
                    cursor_value=event.cursor_value,
                    occurred_at=event.occurred_at,
                )
                await source.ack(event)
            # _EV_B: simulate crash — skip advance entirely.
            events_first_run.append(event.cursor_value)

        # Cursor is at _EV_A; _EV_B was received but not advanced.
        mid_cursor = await repo.get_or_create(
            source_id=source.source_id,
            project_id="proj-remote",
            workspace_id="default",
        )
        assert mid_cursor.last_cursor == _EV_A.cursor_value

        # --- Second run: resume from the unchanged cursor ---
        replayed: list[str] = []
        async for event in source.stream(since=mid_cursor):
            # This time advance succeeds for _EV_B.
            await repo.advance(
                source_id=source.source_id,
                project_id="proj-remote",
                workspace_id="default",
                cursor_value=event.cursor_value,
                occurred_at=event.occurred_at,
            )
            await source.ack(event)
            replayed.append(event.cursor_value)

        # _EV_B must be re-yielded exactly once.
        assert replayed == [_EV_B.cursor_value]

        final_cursor = await repo.get_or_create(
            source_id=source.source_id,
            project_id="proj-remote",
            workspace_id="default",
        )
        assert final_cursor.last_cursor == _EV_B.cursor_value

        await db.close()

    async def test_record_error_does_not_advance_cursor(self) -> None:
        """Calling repo.record_error() must increment error_count without
        moving last_cursor.  Confirms the contract: errors never advance the
        watermark (ADR-009 §Decision — "cursor advances on successful upsert").
        """
        db = await aiosqlite.connect(":memory:")
        db.row_factory = aiosqlite.Row
        await run_migrations(db)
        repo = SqliteIngestCursorRepository(db)

        source = _StubRemoteIngestSource([_EV_A])

        cursor = await repo.get_or_create(
            source_id=source.source_id,
            project_id="proj-remote",
            workspace_id="default",
        )
        assert cursor.last_cursor is None

        # Simulate a failed upsert: record error instead of advancing.
        async for event in source.stream(since=cursor):
            await repo.record_error(
                source_id=source.source_id,
                project_id="proj-remote",
                workspace_id="default",
                error_message="simulated upsert failure",
            )
            # Do NOT call repo.advance() or source.ack().

        after_error = await repo.get_or_create(
            source_id=source.source_id,
            project_id="proj-remote",
            workspace_id="default",
        )
        # Cursor must not have moved.
        assert after_error.last_cursor is None
        # Error count must have incremented.
        assert after_error.error_count == 1
        assert after_error.last_error == "simulated upsert failure"

        await db.close()
