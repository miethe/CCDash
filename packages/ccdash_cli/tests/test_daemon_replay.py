"""Tests for 'ccdash daemon replay' — dead-letter replay command.

Uses Typer's CliRunner for CLI-layer tests and httpx.MockTransport for the
HTTP layer (mirrors the stubbing pattern in test_daemon_retry.py).
"""
from __future__ import annotations

import asyncio
import json
import unittest.mock as mock
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from ccdash_cli.daemon import runner as _runner
from ccdash_cli.daemon.config import DaemonConfig
from ccdash_cli.daemon.wal import WalBuffer
from ccdash_cli.main import app

cli_runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers shared with test_daemon_retry.py pattern
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
        "event_id": f"replay-evt-{idx:04d}",
        "batch_id": "batch-replay-0001",
        "schema_version": "1.0",
        "occurred_at": "2026-06-28T00:00:00+00:00",
        "payload": {"n": idx},
    }


def _ok_response(accepted: int = 1) -> dict:
    return {
        "accepted": accepted,
        "rejected": [],
        "dead_lettered": [],
        "cursor_advanced_to": None,
    }


class _MockTransport(httpx.MockTransport):
    """Sequence-based mock transport returning responses from a queue."""

    def __init__(self, responses: list[httpx.Response]) -> None:
        self._responses = list(responses)
        self._index = 0
        self.calls: int = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if self._index >= len(self._responses):
            raise AssertionError(
                f"MockTransport exhausted after {self._index} call(s); "
                f"unexpected request to {request.url}"
            )
        resp = self._responses[self._index]
        self._index += 1
        self.calls += 1
        return resp

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return self.handle_request(request)


def _build_response(
    status_code: int,
    body: dict | None = None,
    headers: dict | None = None,
) -> httpx.Response:
    content = json.dumps(body or {}).encode() if body is not None else b"{}"
    return httpx.Response(
        status_code=status_code,
        content=content,
        headers={"Content-Type": "application/json", **(headers or {})},
    )


def _write_deadletter_file(deadletter_dir: Path, events: list[dict], name: str) -> Path:
    """Write a fixture dead-letter NDJSON file and return its path."""
    deadletter_dir.mkdir(parents=True, exist_ok=True)
    path = deadletter_dir / name
    with path.open("w", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps(ev) + "\n")
    return path


# ---------------------------------------------------------------------------
# _post_batch-level replay integration (unit tests)
# ---------------------------------------------------------------------------


class TestReplayPostBatch:
    """Verify that replaying dead-letter batches reuses _post_batch correctly."""

    def test_replay_successful_batch_removes_wal_segment(self, tmp_path: Path) -> None:
        """After a 200 response, the temp WAL segment must be acked (no pending segs)."""
        events = [_event(0), _event(1)]
        config = _make_config(tmp_path)
        config.deadletter_root.mkdir(parents=True, exist_ok=True)

        wal_dir = tmp_path / "replay-wal"
        wal = WalBuffer(wal_dir)
        for ev in events:
            wal.append(ev)
        seg = wal.pending_segments()[0]
        counters = _runner._Counters()

        transport = _MockTransport(
            [_build_response(200, _ok_response(accepted=2))]
        )

        async def _run() -> None:
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

        asyncio.run(_run())

        assert wal.pending_segments() == [], "WAL must be empty after successful replay"
        assert counters.accepted_total == 2

    def test_replay_failed_batch_leaves_wal_segment(self, tmp_path: Path) -> None:
        """After exhausted retries, the WAL segment must remain (file not moved)."""
        events = [_event(0)]
        config = _make_config(tmp_path)
        config.deadletter_root.mkdir(parents=True, exist_ok=True)
        # max_retries=3 → 4 total responses
        config = DaemonConfig(
            server_url="http://testserver",
            token="tok",
            project_id="p1",
            sessions_dir=tmp_path / "s",
            buffer_root=tmp_path / "b",
            deadletter_root=tmp_path / "dl",
            status_path=tmp_path / "st",
            max_retries=2,
        )

        wal_dir = tmp_path / "replay-wal2"
        wal = WalBuffer(wal_dir)
        wal.append(events[0])
        seg = wal.pending_segments()[0]
        counters = _runner._Counters()

        transport = _MockTransport([_build_response(503)] * 3)

        async def fast_sleep(_: float) -> None:
            pass

        async def _run() -> None:
            async with httpx.AsyncClient(
                base_url="http://testserver", transport=transport
            ) as client:
                with mock.patch(
                    "ccdash_cli.daemon.runner.asyncio.sleep", side_effect=fast_sleep
                ):
                    await _runner._post_batch(
                        events=events,
                        segment_path=seg,
                        wal=wal,
                        config=config,
                        http_client=client,
                        counters=counters,
                    )

        asyncio.run(_run())

        assert wal.pending_segments(), "WAL segment must remain on failure"
        assert counters.abandoned_total == 1


# ---------------------------------------------------------------------------
# CLI-layer replay tests (via Typer CliRunner)
# ---------------------------------------------------------------------------


class TestDaemonReplayCLI:
    """End-to-end CLI tests for 'ccdash daemon replay'.

    Patch targets:
      - ``ccdash_cli.daemon.config.load_config`` (imported dynamically inside daemon_replay)
      - ``ccdash_cli.daemon.runner._build_http_client`` (imported dynamically inside _run_replay)
    """

    def _patch_load_config(self, cfg: DaemonConfig) -> mock.MagicMock:
        return mock.patch("ccdash_cli.daemon.config.load_config", return_value=cfg)

    def _patch_http_client(self, transport: _MockTransport) -> mock.MagicMock:
        def _fake(config: DaemonConfig) -> httpx.AsyncClient:
            return httpx.AsyncClient(base_url="http://testserver", transport=transport)

        return mock.patch(
            "ccdash_cli.daemon.runner._build_http_client", side_effect=_fake
        )

    def test_replay_help(self) -> None:
        result = cli_runner.invoke(app, ["daemon", "replay", "--help"])
        assert result.exit_code == 0
        assert "replay" in result.output.lower()

    def test_replay_missing_dir_exits_ok(self, tmp_path: Path) -> None:
        """Non-existent dead-letter dir must exit 0 with friendly message."""
        ghost_dir = tmp_path / "nonexistent-dl"
        cfg = _make_config(tmp_path)
        with self._patch_load_config(cfg):
            result = cli_runner.invoke(
                app, ["daemon", "replay", "--dir", str(ghost_dir)]
            )
        assert result.exit_code == 0
        assert "nothing to replay" in result.output.lower()

    def test_replay_empty_dir_exits_ok(self, tmp_path: Path) -> None:
        """An empty dead-letter dir must exit 0 with friendly message."""
        dl_dir = tmp_path / "deadletter"
        dl_dir.mkdir()
        cfg = _make_config(tmp_path)
        with self._patch_load_config(cfg):
            result = cli_runner.invoke(
                app, ["daemon", "replay", "--dir", str(dl_dir)]
            )
        assert result.exit_code == 0
        assert "nothing to replay" in result.output.lower()

    def test_dry_run_lists_files_no_post(self, tmp_path: Path) -> None:
        """--dry-run must list files and not make any HTTP calls."""
        dl_dir = tmp_path / "deadletter"
        _write_deadletter_file(dl_dir, [_event(0)], "deadletter-0000000001.ndjson")
        _write_deadletter_file(dl_dir, [_event(1)], "deadletter-0000000002.ndjson")
        cfg = _make_config(tmp_path)

        with self._patch_load_config(cfg):
            with mock.patch("ccdash_cli.daemon.runner._build_http_client") as mock_client:
                result = cli_runner.invoke(
                    app,
                    ["daemon", "replay", "--dir", str(dl_dir), "--dry-run"],
                )

        assert result.exit_code == 0
        mock_client.assert_not_called()
        assert "dry-run" in result.output.lower()
        assert "deadletter-0000000001.ndjson" in result.output
        assert "deadletter-0000000002.ndjson" in result.output

    def test_replay_success_moves_to_replayed_subdir(self, tmp_path: Path) -> None:
        """On 200, files must be moved to replayed/ subdir."""
        dl_dir = tmp_path / "deadletter"
        events_a = [_event(0), _event(1)]
        events_b = [_event(2)]
        file_a = _write_deadletter_file(
            dl_dir, events_a, "deadletter-0000000001.ndjson"
        )
        file_b = _write_deadletter_file(
            dl_dir, events_b, "deadletter-0000000002.ndjson"
        )

        transport = _MockTransport(
            [
                _build_response(200, _ok_response(accepted=2)),
                _build_response(200, _ok_response(accepted=1)),
            ]
        )
        cfg = _make_config(tmp_path)

        async def fast_sleep(_: float) -> None:
            pass

        with self._patch_load_config(cfg):
            with self._patch_http_client(transport):
                with mock.patch(
                    "ccdash_cli.daemon.runner.asyncio.sleep",
                    side_effect=fast_sleep,
                ):
                    result = cli_runner.invoke(
                        app,
                        ["daemon", "replay", "--dir", str(dl_dir)],
                    )

        assert result.exit_code == 0, f"Expected exit 0:\n{result.output}"
        assert not file_a.exists(), "Replayed file must be moved"
        assert not file_b.exists(), "Replayed file must be moved"
        assert (dl_dir / "replayed" / "deadletter-0000000001.ndjson").exists()
        assert (dl_dir / "replayed" / "deadletter-0000000002.ndjson").exists()
        assert "2 accepted" in result.output

    def test_replay_success_purge_deletes_files(self, tmp_path: Path) -> None:
        """--purge must delete replayed files instead of moving them."""
        dl_dir = tmp_path / "deadletter"
        file_a = _write_deadletter_file(
            dl_dir, [_event(0)], "deadletter-0000000010.ndjson"
        )
        transport = _MockTransport([_build_response(200, _ok_response(accepted=1))])
        cfg = _make_config(tmp_path)

        with self._patch_load_config(cfg):
            with self._patch_http_client(transport):
                result = cli_runner.invoke(
                    app,
                    ["daemon", "replay", "--dir", str(dl_dir), "--purge"],
                )

        assert result.exit_code == 0, f"Expected exit 0:\n{result.output}"
        assert not file_a.exists(), "--purge must delete replayed files"
        replayed_dir = dl_dir / "replayed"
        if replayed_dir.exists():
            assert not list(replayed_dir.glob("*.ndjson")), "replayed/ must be empty"

    def test_replay_permanent_failure_exits_1(self, tmp_path: Path) -> None:
        """When a file permanently fails (exhausted retries), exit code must be 1."""
        dl_dir = tmp_path / "deadletter"
        file_a = _write_deadletter_file(
            dl_dir, [_event(0)], "deadletter-0000000020.ndjson"
        )

        cfg = DaemonConfig(
            server_url="http://testserver",
            token="tok",
            project_id="p1",
            sessions_dir=tmp_path / "s",
            buffer_root=tmp_path / "b",
            deadletter_root=dl_dir,
            status_path=tmp_path / "st",
            max_retries=1,
        )
        # 2 responses (1 initial + 1 retry) all 503 → exhausted
        transport = _MockTransport([_build_response(503)] * 2)

        async def fast_sleep(_: float) -> None:
            pass

        with self._patch_load_config(cfg):
            with self._patch_http_client(transport):
                with mock.patch(
                    "ccdash_cli.daemon.runner.asyncio.sleep",
                    side_effect=fast_sleep,
                ):
                    result = cli_runner.invoke(
                        app,
                        ["daemon", "replay", "--dir", str(dl_dir)],
                    )

        assert result.exit_code == 1, f"Expected exit 1 on failure:\n{result.output}"
        assert file_a.exists(), "Failed file must remain in place"
        assert "still-failed" in result.output.lower()


# ---------------------------------------------------------------------------
# Counter tests — retry_total / abandoned_total exposed in status
# ---------------------------------------------------------------------------


class TestCounters:
    """Verify new retry_total and abandoned_total counters are tracked."""

    def test_retry_total_incremented_on_503(self, tmp_path: Path) -> None:
        from ccdash_cli.daemon.wal import WalBuffer

        config = _make_config(tmp_path)
        config.buffer_root.mkdir(parents=True, exist_ok=True)
        config.deadletter_root.mkdir(parents=True, exist_ok=True)
        config.status_path.parent.mkdir(parents=True, exist_ok=True)

        wal = WalBuffer(config.buffer_root)
        events = [_event(0)]
        wal.append(events[0])
        seg = wal.pending_segments()[0]
        counters = _runner._Counters()

        # 503 twice then 200
        transport = _MockTransport(
            [
                _build_response(503),
                _build_response(503),
                _build_response(200, _ok_response(accepted=1)),
            ]
        )

        async def fast_sleep(_: float) -> None:
            pass

        async def _run() -> None:
            async with httpx.AsyncClient(
                base_url="http://testserver", transport=transport
            ) as client:
                with mock.patch(
                    "ccdash_cli.daemon.runner.asyncio.sleep",
                    side_effect=fast_sleep,
                ):
                    await _runner._post_batch(
                        events=events,
                        segment_path=seg,
                        wal=wal,
                        config=config,
                        http_client=client,
                        counters=counters,
                    )

        asyncio.run(_run())

        assert counters.retry_total == 2, (
            f"Expected 2 retries (2x 503), got {counters.retry_total}"
        )
        assert counters.abandoned_total == 0

    def test_abandoned_total_incremented_on_exhaustion(self, tmp_path: Path) -> None:
        config = DaemonConfig(
            server_url="http://testserver",
            token="tok",
            project_id="p1",
            sessions_dir=tmp_path / "s",
            buffer_root=tmp_path / "b",
            deadletter_root=tmp_path / "dl",
            status_path=tmp_path / "st",
            max_retries=1,
        )
        config.buffer_root.mkdir(parents=True, exist_ok=True)
        config.deadletter_root.mkdir(parents=True, exist_ok=True)
        config.status_path.parent.mkdir(parents=True, exist_ok=True)

        wal = WalBuffer(config.buffer_root)
        ev = _event(0)
        wal.append(ev)
        seg = wal.pending_segments()[0]
        counters = _runner._Counters()

        # max_retries=1 → 2 total attempts (both 503)
        transport = _MockTransport([_build_response(503)] * 2)

        async def fast_sleep(_: float) -> None:
            pass

        async def _run() -> None:
            async with httpx.AsyncClient(
                base_url="http://testserver", transport=transport
            ) as client:
                with mock.patch(
                    "ccdash_cli.daemon.runner.asyncio.sleep",
                    side_effect=fast_sleep,
                ):
                    await _runner._post_batch(
                        events=[ev],
                        segment_path=seg,
                        wal=wal,
                        config=config,
                        http_client=client,
                        counters=counters,
                    )

        asyncio.run(_run())

        assert counters.abandoned_total == 1
        assert counters.retry_total >= 1

    def test_status_file_includes_new_counters(self, tmp_path: Path) -> None:
        """_write_status must include retry_total and abandoned_total keys."""
        config = _make_config(tmp_path)
        config.status_path.parent.mkdir(parents=True, exist_ok=True)
        config.buffer_root.mkdir(parents=True, exist_ok=True)

        wal = WalBuffer(config.buffer_root)
        counters = _runner._Counters()
        counters.retry_total = 5
        counters.abandoned_total = 2

        asyncio.run(_runner._write_status(config, wal, counters, last_error=None))

        raw = config.status_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        assert "retry_total" in data, "retry_total must appear in status JSON"
        assert "abandoned_total" in data, "abandoned_total must appear in status JSON"
        assert data["retry_total"] == 5
        assert data["abandoned_total"] == 2
