"""Regression test for node_01M2GV5XJ63HYV282W02N7DF2R.

CCDash's fleet-wide session-ingest pipeline went silent for ~5 days (measured
2026-09-14: every window from 2026-09-09T00:00Z onward returned sessions=0
across all 107 registered projects) with zero operator-visible signal —
``systemctl status`` stayed ``active`` and ``ccdash-cli daemon status`` stayed
clean the whole time.

Root cause class: ``_tail_coroutine`` (``ccdash_cli/daemon/runner.py``) caught
``ImportError`` on the lazy ``backend.parsers.sessions`` import and returned
silently. ``run_daemon``'s ``asyncio.gather(tail_task, flush_task)`` never
completes when the tail task merely *returns* early, because ``flush_task``
runs forever regardless — so the daemon process never exits, never crashes,
and never trips ``Restart=on-failure``. It just stops ingesting anything,
forever, looking perfectly healthy. This exact trap is documented as a known
hazard in ``infra/agentic-node/CCDASH-NODE-INGEST.md`` §(b); this outage is
that hazard recurring.

The fix makes the import failure fatal: ``_tail_coroutine`` re-raises instead
of swallowing, so ``asyncio.gather`` propagates the exception out of
``run_daemon()`` and the process crashes loudly (visible in journalctl,
retried by ``Restart=on-failure``) instead of idling as an undetectable
zombie.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from ccdash_cli.daemon import runner as _runner
from ccdash_cli.daemon.config import DaemonConfig


def _make_config(tmp_path: Path) -> DaemonConfig:
    return DaemonConfig(
        server_url="http://testserver",
        token="test-token",
        project_id="proj-1",
        sessions_dir=tmp_path / "sessions",
        flush_interval_seconds=0.05,
        max_batch_events=100,
        buffer_root=tmp_path / "buffer",
        deadletter_root=tmp_path / "deadletter",
        status_path=tmp_path / "daemon.status",
        max_retries=1,
    )


def test_tail_coroutine_reraises_import_error_instead_of_returning(tmp_path: Path) -> None:
    """The tail coroutine must not swallow a broken cross-package import.

    Before the fix this coroutine logged one ERROR line and returned — asyncio
    treats an early ``return`` as the coroutine completing successfully, which
    is indistinguishable, from ``run_daemon``'s perspective, from "nothing to
    watch right now".
    """
    config = _make_config(tmp_path)
    config.sessions_dir.mkdir(parents=True)
    wal = _runner.WalBuffer(config.buffer_root)
    queue: list[dict] = []

    with patch.object(
        _runner, "_import_parse_session_file", side_effect=ImportError("no backend")
    ):
        with pytest.raises(ImportError):
            asyncio.run(
                asyncio.wait_for(
                    _runner._tail_coroutine(config, wal, queue), timeout=2.0
                )
            )


def test_run_daemon_crashes_instead_of_hanging_when_tail_import_fails(
    tmp_path: Path,
) -> None:
    """End-to-end: a broken tail import must crash ``run_daemon``, not hang it.

    This is the actual production shape: ``flush_task`` is healthy and would
    run forever on its own. Before the fix, ``asyncio.gather`` never
    completed (tail returned, flush never does), so this test would time out
    rather than raise — that timeout IS the zombie. ``pytest.raises`` here
    means the fix turned an infinite hang into an immediate, visible failure.
    """
    config = _make_config(tmp_path)
    config.sessions_dir.mkdir(parents=True)

    async def _handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        return httpx.Response(200, json={"accepted": 0, "rejected": []})

    transport = httpx.MockTransport(_handler)
    http_client = httpx.AsyncClient(transport=transport, base_url=config.server_url)

    with patch.object(
        _runner, "_import_parse_session_file", side_effect=ImportError("no backend")
    ):
        with pytest.raises(ImportError):
            asyncio.run(
                asyncio.wait_for(
                    _runner.run_daemon(config, http_client=http_client), timeout=3.0
                )
            )
