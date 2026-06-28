"""Retry behavior tests for the CCDash daemon using httpx MockTransport.

Tests exercise the _post_batch helper in runner.py directly, injecting
pre-configured MockTransport instances so no real HTTP server is needed.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

# Import internal helpers directly for unit testing.
from ccdash_cli.daemon import runner as _runner
from ccdash_cli.daemon.config import DaemonConfig
from ccdash_cli.daemon.wal import WalBuffer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(tmp_path: Path) -> DaemonConfig:
    return DaemonConfig(
        server_url="http://testserver",
        token="test-token",
        project_id="proj-1",
        sessions_dir=tmp_path / "sessions",
        flush_interval_seconds=5.0,
        max_batch_events=100,
        buffer_root=tmp_path / "buffer",
        deadletter_root=tmp_path / "deadletter",
        status_path=tmp_path / "daemon.status",
        max_retries=3,
    )


def _event(idx: int) -> dict:
    return {
        "event_id": f"evt-{idx:04d}",
        "batch_id": "batch-0001",
        "schema_version": "1.0",
        "occurred_at": "2026-05-19T00:00:00+00:00",
        "payload": {"n": idx},
    }


def _ok_response(accepted: int = 1, rejected: list | None = None) -> dict:
    return {
        "accepted": accepted,
        "rejected": rejected or [],
        "dead_lettered": [],
        "cursor_advanced_to": None,
    }


class _MockTransport(httpx.MockTransport):
    """Sequence-based mock transport: returns responses from a queue."""

    def __init__(self, responses: list[httpx.Response]) -> None:
        self._responses = list(responses)
        self._index = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if self._index >= len(self._responses):
            raise AssertionError(
                f"MockTransport exhausted after {self._index} calls; "
                f"got unexpected request to {request.url}"
            )
        response = self._responses[self._index]
        self._index += 1
        return response

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return self.handle_request(request)


def _build_response(
    status_code: int,
    body: dict | None = None,
    headers: dict | None = None,
) -> httpx.Response:
    content = json.dumps(body or {}).encode("utf-8") if body is not None else b"{}"
    return httpx.Response(
        status_code=status_code,
        content=content,
        headers={"Content-Type": "application/json", **(headers or {})},
    )


def _make_wal(tmp_path: Path) -> WalBuffer:
    buf = tmp_path / "buffer"
    buf.mkdir(parents=True, exist_ok=True)
    return WalBuffer(buf, max_segment_lines=500)


async def _run_post_batch(
    events: list[dict],
    responses: list[httpx.Response],
    tmp_path: Path,
) -> tuple[WalBuffer, DaemonConfig, _runner._Counters]:
    """Helper that creates a WAL, writes events, calls _post_batch, returns state."""
    config = _make_config(tmp_path)
    config.buffer_root.mkdir(parents=True, exist_ok=True)
    config.deadletter_root.mkdir(parents=True, exist_ok=True)
    config.status_path.parent.mkdir(parents=True, exist_ok=True)

    wal = _make_wal(tmp_path)
    for ev in events:
        wal.append(ev)

    seg = wal.pending_segments()[0]
    counters = _runner._Counters()

    transport = _MockTransport(responses)
    async with httpx.AsyncClient(
        base_url="http://testserver",
        transport=transport,
    ) as client:
        await _runner._post_batch(
            events=events,
            segment_path=seg,
            wal=wal,
            config=config,
            http_client=client,
            counters=counters,
        )

    return wal, config, counters


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_200_acks_segment(self, tmp_path: Path) -> None:
        events = [_event(0)]
        responses = [_build_response(200, _ok_response(accepted=1))]

        wal, config, counters = asyncio.run(
            _run_post_batch(events, responses, tmp_path)
        )

        assert wal.pending_segments() == [], "Segment should be acked on success"
        assert counters.accepted_total == 1
        assert counters.rejected_total == 0

    def test_200_increments_accepted_total(self, tmp_path: Path) -> None:
        events = [_event(i) for i in range(5)]
        responses = [_build_response(200, _ok_response(accepted=5))]

        _, _, counters = asyncio.run(
            _run_post_batch(events, responses, tmp_path)
        )

        assert counters.accepted_total == 5


class TestPartialSuccess:
    def test_200_partial_moves_rejected_to_deadletter(self, tmp_path: Path) -> None:
        events = [_event(0), _event(1), _event(2)]
        # Reject event 1
        partial_body = {
            "accepted": 2,
            "rejected": [{"event_id": "evt-0001", "reason": "invalid", "code": "X"}],
            "dead_lettered": [],
            "cursor_advanced_to": None,
        }
        responses = [_build_response(200, partial_body)]

        wal, config, counters = asyncio.run(
            _run_post_batch(events, responses, tmp_path)
        )

        # Dead-letter files should exist.
        dl_files = list(config.deadletter_root.glob("deadletter-*.ndjson"))
        assert dl_files, "Expected dead-letter file for rejected event"
        assert counters.rejected_total == 1


class TestRetryOn503:
    def test_503_triggers_backoff_and_eventually_succeeds(self, tmp_path: Path) -> None:
        events = [_event(0)]
        # First two attempts fail with 503, third succeeds.
        responses = [
            _build_response(503),
            _build_response(503),
            _build_response(200, _ok_response(accepted=1)),
        ]

        # Patch asyncio.sleep to avoid waiting in tests.
        sleep_calls: list[float] = []

        async def fast_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        import unittest.mock as mock

        with mock.patch("ccdash_cli.daemon.runner.asyncio.sleep", side_effect=fast_sleep):
            wal, config, counters = asyncio.run(
                _run_post_batch(events, responses, tmp_path)
            )

        assert counters.accepted_total == 1
        assert wal.pending_segments() == []
        assert len(sleep_calls) == 2, f"Expected 2 backoff sleeps, got {sleep_calls}"
        # Exponential backoff: 0.1 * 2^0 = 0.1, 0.1 * 2^1 = 0.2
        assert sleep_calls[0] == pytest.approx(0.1, rel=0.01)
        assert sleep_calls[1] == pytest.approx(0.2, rel=0.01)


class TestRetryExhausted:
    def test_exhausted_retries_leave_wal_intact(self, tmp_path: Path) -> None:
        """When all retries are exhausted, the WAL segment must remain."""
        events = [_event(0)]
        config = _make_config(tmp_path)
        config.buffer_root.mkdir(parents=True, exist_ok=True)
        config.deadletter_root.mkdir(parents=True, exist_ok=True)
        config.status_path.parent.mkdir(parents=True, exist_ok=True)
        # max_retries=3 → 4 total attempts (1 + 3 retries)
        responses = [_build_response(503)] * 4

        wal = _make_wal(tmp_path)
        for ev in events:
            wal.append(ev)
        seg = wal.pending_segments()[0]
        counters = _runner._Counters()

        import unittest.mock as mock

        async def fast_sleep(_: float) -> None:
            pass

        async def _run() -> None:
            transport = _MockTransport(responses)
            async with httpx.AsyncClient(
                base_url="http://testserver", transport=transport
            ) as client:
                await _runner._post_batch(
                    events=events,
                    segment_path=seg,
                    wal=wal,
                    config=config,
                    http_client=client,
                    counters=counters,
                )

        with mock.patch("ccdash_cli.daemon.runner.asyncio.sleep", side_effect=fast_sleep):
            asyncio.run(_run())

        assert wal.pending_segments(), "WAL segment must remain when retries exhausted"
        assert counters.accepted_total == 0
        assert counters.last_error is not None


class TestRateLimiting:
    def test_429_honors_retry_after(self, tmp_path: Path) -> None:
        events = [_event(0)]
        responses = [
            _build_response(429, headers={"Retry-After": "2"}),
            _build_response(200, _ok_response(accepted=1)),
        ]

        sleep_calls: list[float] = []

        async def fast_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        import unittest.mock as mock

        with mock.patch("ccdash_cli.daemon.runner.asyncio.sleep", side_effect=fast_sleep):
            wal, config, counters = asyncio.run(
                _run_post_batch(events, responses, tmp_path)
            )

        assert counters.accepted_total == 1
        assert sleep_calls[0] == pytest.approx(2.0, rel=0.01), (
            f"Expected Retry-After=2s sleep, got {sleep_calls[0]}"
        )


class TestBatchSplit:
    def test_413_splits_batch_in_half(self, tmp_path: Path) -> None:
        """413 must cause the batch to be split and re-posted as two halves."""
        events = [_event(0), _event(1)]
        # 413 on first call, then 200 for each half.
        responses = [
            _build_response(413),
            _build_response(200, _ok_response(accepted=1)),
            _build_response(200, _ok_response(accepted=1)),
        ]

        wal, config, counters = asyncio.run(
            _run_post_batch(events, responses, tmp_path)
        )

        assert counters.accepted_total == 2

    def test_413_single_event_goes_to_deadletter(self, tmp_path: Path) -> None:
        """A single-event batch that gets 413 cannot be split — it must be dead-lettered."""
        events = [_event(0)]
        responses = [_build_response(413)]

        wal, config, counters = asyncio.run(
            _run_post_batch(events, responses, tmp_path)
        )

        dl_files = list(config.deadletter_root.glob("deadletter-*.ndjson"))
        assert dl_files, "Expected dead-letter file for unsplittable 413 event"
        assert counters.deadlettered_total == 1
