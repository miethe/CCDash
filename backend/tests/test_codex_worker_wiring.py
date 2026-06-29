"""Tests for Phase 4 of codex-session-ingestion-v1: worker wiring + D3-b backfill window.

Tests:
  1. Backfill window (backfill_only=True): rollout older than N days is excluded.
  2. Live mode (backfill_only=False): no date window, old file is ingested normally.
  3. CCDASH_CODEX_BACKFILL_DAYS=0: disables window entirely, all files included.
  4. Worker flag on (CCDASH_CODEX_INGEST_ENABLED=True):
     RuntimeJobAdapter.start() creates codex_backfill_task (worker registered).
  5. Worker flag off (CCDASH_CODEX_INGEST_ENABLED=False, AC6):
     RuntimeJobAdapter.start() leaves codex_backfill_task=None; sync never called.
  6. Reconcile re-scan idempotency: two passes over unchanged file → 1 session row.
  7. Unit: _codex_file_date extracts date from YYYY/MM/DD path tree correctly.

Hard constraints:
  - AC6: CCDASH_CODEX_INGEST_ENABLED=False → zero codex work, zero DB rows.
  - ADR-007: direct-count assertions on all write paths.
  - No unscoped `pytest backend/tests` invocation.

Run with:
    backend/.venv/bin/python -m pytest backend/tests/test_codex_worker_wiring.py -v
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sqlite3
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite

import aiosqlite as _aiosqlite_mod

from backend.db.sync_engine import SyncEngine, _codex_file_date
from backend.db.sqlite_migrations import run_migrations


# ── Shared helpers ─────────────────────────────────────────────────────────────

async def _bootstrap_db(db_path: str) -> None:
    """Create a DB with full migrations so SyncEngine can operate."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA busy_timeout = 30000")
        await run_migrations(db)
        await db.commit()


def _build_rollout_at_date(
    codex_root: Path,
    *,
    year: int,
    month: int,
    day: int,
    cwd: str = "/tmp/testproject",
    filename: str = "rollout-test.jsonl",
) -> Path:
    """Create a minimal rollout file at the YYYY/MM/DD tree path inside *codex_root*.

    Returns the created file path.
    """
    date_dir = codex_root / str(year) / f"{month:02d}" / f"{day:02d}"
    date_dir.mkdir(parents=True, exist_ok=True)
    file_path = date_dir / filename
    ts = f"{year:04d}-{month:02d}-{day:02d}T10:00:00Z"
    lines = [
        json.dumps({
            "type": "turn_context",
            "timestamp": ts,
            "payload": {"type": "turn_context", "cwd": cwd, "model": "gpt-4-codex", "cli_version": "0.64.3"},
        }),
        json.dumps({
            "type": "response_item",
            "timestamp": ts,
            "payload": {"type": "user_message", "role": "user", "content": "run test"},
        }),
        json.dumps({
            "type": "response_item",
            "timestamp": ts,
            "payload": {"type": "agent_message", "role": "assistant", "content": "done"},
        }),
        json.dumps({
            "type": "event_msg",
            "timestamp": ts,
            "payload": {"type": "task_complete", "summary": "Done."},
        }),
    ]
    file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return file_path


def _session_count(db_path: str) -> int:
    """Return the total number of Codex-platform session rows in the DB."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA busy_timeout = 30000")
    row = conn.execute(
        "SELECT COUNT(*) FROM sessions WHERE platform_type = 'Codex'"
    ).fetchone()
    conn.close()
    return row[0]


def _patch_config_for_engine(mock_cfg: Any, codex_root: str) -> None:
    """Apply the minimum config values needed by SyncEngine.sync_codex_sessions."""
    import backend.db.sync_engine as _se_mod

    real_cfg = _se_mod.config
    mock_cfg.CCDASH_CODEX_INGEST_ENABLED = True
    mock_cfg.CCDASH_CODEX_SESSIONS_PATH = codex_root
    mock_cfg.SYNC_COALESCING_ENABLED = getattr(real_cfg, "SYNC_COALESCING_ENABLED", True)
    mock_cfg.SIDECAR_CONTEXT_JOIN_ENABLED = getattr(real_cfg, "SIDECAR_CONTEXT_JOIN_ENABLED", True)
    mock_cfg.STARTUP_SYNC_LIGHT_MODE = False
    mock_cfg.SYNC_RECENT_FIRST_ENABLED = True
    mock_cfg.SYNC_RECENT_FIRST_N = 200
    mock_cfg.STORAGE_PROFILE = None


# ── Test Class 1: Backfill Window ─────────────────────────────────────────────


class TestCodexBackfillWindow(unittest.IsolatedAsyncioTestCase):
    """D3-b backfill window: verify date filtering in sync_codex_sessions."""

    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._db_path = os.path.join(self._tmpdir, "test.db")
        self._codex_root = Path(self._tmpdir) / "codex_sessions"
        self._codex_root.mkdir()
        await _bootstrap_db(self._db_path)

    async def asyncTearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    async def _engine(self) -> tuple[SyncEngine, aiosqlite.Connection]:
        db = await aiosqlite.connect(self._db_path)
        await db.execute("PRAGMA busy_timeout = 30000")
        db.row_factory = aiosqlite.Row
        return SyncEngine(db), db

    async def test_old_file_excluded_by_backfill_window(self) -> None:
        """A rollout file dated 30 days ago is excluded from a 7-day backfill
        window (backfill_only=True, CCDASH_CODEX_BACKFILL_DAYS=7).
        """
        old_date = datetime.now(timezone.utc) - timedelta(days=30)
        _build_rollout_at_date(
            self._codex_root,
            year=old_date.year,
            month=old_date.month,
            day=old_date.day,
        )

        engine, db = await self._engine()
        try:
            with patch("backend.db.sync_engine.config") as mock_cfg:
                _patch_config_for_engine(mock_cfg, str(self._codex_root))
                mock_cfg.CCDASH_CODEX_BACKFILL_DAYS = 7

                stats = await engine.sync_codex_sessions(force=False, backfill_only=True)
        finally:
            await db.close()

        self.assertEqual(
            stats["synced"], 0,
            "30-day-old file must be excluded from a 7-day backfill window",
        )
        self.assertEqual(
            stats["skipped"], 0,
            "excluded file must not appear as 'skipped' — it is pre-filtered",
        )
        # ADR-007: direct-count assertion.
        self.assertEqual(
            _session_count(self._db_path), 0,
            "no session rows expected after excluding the old file",
        )

    async def test_old_file_included_in_live_mode(self) -> None:
        """The same 30-day-old file is ingested when backfill_only=False (live /
        reconcile pass).  No date window is applied; mtime idempotency handles dedup.
        """
        old_date = datetime.now(timezone.utc) - timedelta(days=30)
        _build_rollout_at_date(
            self._codex_root,
            year=old_date.year,
            month=old_date.month,
            day=old_date.day,
        )

        engine, db = await self._engine()
        try:
            with patch("backend.db.sync_engine.config") as mock_cfg:
                _patch_config_for_engine(mock_cfg, str(self._codex_root))
                mock_cfg.CCDASH_CODEX_BACKFILL_DAYS = 7

                stats = await engine.sync_codex_sessions(force=False, backfill_only=False)
        finally:
            await db.close()

        self.assertGreater(
            stats["synced"], 0,
            "30-day-old file must be ingested when backfill_only=False (live mode)",
        )
        self.assertGreater(
            _session_count(self._db_path), 0,
            "session row must exist after live-mode ingest",
        )

    async def test_backfill_days_zero_disables_window(self) -> None:
        """CCDASH_CODEX_BACKFILL_DAYS=0 disables the date window: a 30-day-old
        file is included in the backfill pass (full historical backfill).
        """
        old_date = datetime.now(timezone.utc) - timedelta(days=30)
        _build_rollout_at_date(
            self._codex_root,
            year=old_date.year,
            month=old_date.month,
            day=old_date.day,
        )

        engine, db = await self._engine()
        try:
            with patch("backend.db.sync_engine.config") as mock_cfg:
                _patch_config_for_engine(mock_cfg, str(self._codex_root))
                mock_cfg.CCDASH_CODEX_BACKFILL_DAYS = 0  # no day bound

                stats = await engine.sync_codex_sessions(force=False, backfill_only=True)
        finally:
            await db.close()

        self.assertGreater(
            stats["synced"], 0,
            "old file must be included when CCDASH_CODEX_BACKFILL_DAYS=0",
        )


# ── Test Class 2: Worker Flag Gating (AC6) ────────────────────────────────────


class TestCodexWorkerFlagGating(unittest.IsolatedAsyncioTestCase):
    """AC6 enforcement at the worker level.

    When CCDASH_CODEX_INGEST_ENABLED=False (the default), start() must register
    NO codex scan target and must NOT call sync_codex_sessions.
    When the flag is True, start() must create a codex_backfill_task.
    """

    def _make_adapter(self, mock_sync: Any) -> Any:
        """Build a minimal RuntimeJobAdapter with the "test" profile.

        The "test" profile has capabilities.sync/watch/jobs=False, so all
        the heavy startup blocks are skipped — only the Codex block (which
        depends on config, not capabilities) is exercised.
        """
        from backend.adapters.jobs.runtime import RuntimeJobAdapter
        from backend.runtime.profiles import get_runtime_profile

        profile = get_runtime_profile("test")

        mock_registry = MagicMock()
        mock_registry.list_projects.return_value = []
        mock_registry.resolve_project_binding.return_value = None

        mock_ports = types.SimpleNamespace(
            workspace_registry=mock_registry,
            # None → codex block uses asyncio.create_task (no scheduler needed).
            job_scheduler=None,
            storage=MagicMock(),
        )

        return RuntimeJobAdapter(
            profile=profile,
            ports=mock_ports,
            sync_engine=mock_sync,
            project_binding=None,
        )

    def _base_runtime_config(self, mock_cfg: Any) -> None:
        """Patch the minimum config attributes that start() reads."""
        from backend import config as _real_cfg
        from pathlib import Path

        mock_cfg.STARTUP_SYNC_ENABLED = True
        mock_cfg.SYNC_ALL_PROJECTS = False
        mock_cfg.ANALYTICS_SNAPSHOT_INTERVAL_SECONDS = 0
        mock_cfg.CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS = 0
        mock_cfg.RETENTION_PRUNE_ENABLED = False
        mock_cfg.RECONCILE_INTERVAL_SECONDS = 0
        mock_cfg.WATCHER_RECONCILE_INTERVAL_SECONDS = 0
        # Paths used when active_bundle is None.
        mock_cfg.SESSIONS_DIR = Path("/tmp/ccdash-test/sessions")
        mock_cfg.DOCUMENTS_DIR = Path("/tmp/ccdash-test/docs")
        mock_cfg.PROGRESS_DIR = Path("/tmp/ccdash-test/progress")

    async def test_flag_on_creates_codex_backfill_task(self) -> None:
        """CCDASH_CODEX_INGEST_ENABLED=True → start() creates codex_backfill_task.

        The task is the worker's codex scan registration (D3-b backfill job).
        """
        mock_sync = AsyncMock()
        mock_sync.sync_codex_sessions = AsyncMock(return_value={
            "synced": 0, "skipped": 0, "parse_errors": 0,
            "unattributed": 0, "unattributed_cwds": [],
        })

        adapter = self._make_adapter(mock_sync)

        with patch("backend.adapters.jobs.runtime.config") as mock_cfg:
            self._base_runtime_config(mock_cfg)
            mock_cfg.CCDASH_CODEX_INGEST_ENABLED = True

            await adapter.start()
            # Yield to let the asyncio task begin executing.
            await asyncio.sleep(0)

        try:
            self.assertIsNotNone(
                adapter.state.codex_backfill_task,
                "codex_backfill_task must be created when CCDASH_CODEX_INGEST_ENABLED=True",
            )
        finally:
            await adapter.stop()

    async def test_flag_off_no_codex_task_ac6(self) -> None:
        """CCDASH_CODEX_INGEST_ENABLED=False (default) → start() leaves
        codex_backfill_task=None and never calls sync_codex_sessions (AC6).
        """
        mock_sync = AsyncMock()
        mock_sync.sync_codex_sessions = AsyncMock(return_value={
            "synced": 0, "skipped": 0, "parse_errors": 0,
            "unattributed": 0, "unattributed_cwds": [],
        })

        adapter = self._make_adapter(mock_sync)

        with patch("backend.adapters.jobs.runtime.config") as mock_cfg:
            self._base_runtime_config(mock_cfg)
            mock_cfg.CCDASH_CODEX_INGEST_ENABLED = False

            await adapter.start()

        try:
            self.assertIsNone(
                adapter.state.codex_backfill_task,
                "codex_backfill_task must be None when CCDASH_CODEX_INGEST_ENABLED=False (AC6)",
            )
            mock_sync.sync_codex_sessions.assert_not_called()
        finally:
            await adapter.stop()


# ── Test Class 3: Reconcile Idempotency ───────────────────────────────────────


class TestCodexReconcileIdempotency(unittest.IsolatedAsyncioTestCase):
    """Two sync passes over the same unchanged file produce exactly one session row."""

    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._db_path = os.path.join(self._tmpdir, "test.db")
        self._codex_root = Path(self._tmpdir) / "codex_sessions"
        self._codex_root.mkdir()
        await _bootstrap_db(self._db_path)

    async def asyncTearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    async def test_reconcile_idempotent_no_dup_rows(self) -> None:
        """Two sync_codex_sessions calls over an unchanged file → 1 session row.

        First call: force=True to guarantee an initial ingest.
        Second call: force=False — mtime unchanged → file is skipped → no dup.

        ADR-007: direct-count assertion enforces exactly-once storage.
        """
        today = datetime.now(timezone.utc)
        _build_rollout_at_date(
            self._codex_root,
            year=today.year,
            month=today.month,
            day=today.day,
        )

        db = await aiosqlite.connect(self._db_path)
        await db.execute("PRAGMA busy_timeout = 30000")
        # row_factory must be set so dict(row) works in SqliteSyncStateRepository.
        db.row_factory = aiosqlite.Row
        engine = SyncEngine(db)
        try:
            with patch("backend.db.sync_engine.config") as mock_cfg:
                _patch_config_for_engine(mock_cfg, str(self._codex_root))
                mock_cfg.CCDASH_CODEX_BACKFILL_DAYS = 7

                # First pass: force ingest.
                stats1 = await engine.sync_codex_sessions(force=True, backfill_only=False)
                # Second pass: reconcile (no file changes → mtime match → skip).
                stats2 = await engine.sync_codex_sessions(force=False, backfill_only=False)
        finally:
            await db.close()

        self.assertGreater(stats1["synced"], 0, "first pass must ingest the session")
        self.assertEqual(
            stats2["synced"], 0,
            "second pass must skip the unchanged file (idempotency)",
        )
        self.assertGreater(
            stats2["skipped"], 0,
            "second pass must report the file as skipped",
        )
        # ADR-007: direct-count assertion.
        self.assertEqual(
            _session_count(self._db_path), 1,
            "exactly one session row must exist after two passes over the same unchanged file",
        )


# ── Unit tests: _codex_file_date helper ───────────────────────────────────────


class TestCodexFileDateHelper(unittest.TestCase):
    """Unit tests for the _codex_file_date path-extraction helper."""

    def test_extracts_date_from_yyyy_mm_dd_path(self) -> None:
        """Date is extracted from the last three directory components."""
        p = Path("/home/user/.codex/sessions/2026/06/15/rollout-abc.jsonl")
        result = _codex_file_date(p)
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2026)
        self.assertEqual(result.month, 6)
        self.assertEqual(result.day, 15)

    def test_old_path_returns_correct_old_date(self) -> None:
        p = Path("/home/user/.codex/sessions/2020/01/01/rollout-old.jsonl")
        result = _codex_file_date(p)
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2020)
        self.assertEqual(result.month, 1)
        self.assertEqual(result.day, 1)

    def test_non_date_path_falls_back_to_mtime(self) -> None:
        """A path without YYYY/MM/DD structure falls back to the file mtime."""
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            p = Path(f.name)
        try:
            result = _codex_file_date(p)
            # Falls back to mtime — result should be a recent datetime, not None.
            self.assertIsNotNone(result)
        finally:
            os.unlink(p)

    def test_old_date_falls_outside_7day_cutoff(self) -> None:
        """A file from 30 days ago is correctly identified as outside a 7-day window."""
        old = datetime.now(timezone.utc) - timedelta(days=30)
        p = Path(f"/root/{old.year}/{old.month:02d}/{old.day:02d}/rollout-old.jsonl")
        result = _codex_file_date(p)
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        self.assertIsNotNone(result)
        self.assertLess(
            result, cutoff,
            "30-day-old date must fall before the 7-day cutoff",
        )

    def test_recent_date_falls_inside_7day_cutoff(self) -> None:
        """A file from yesterday is inside a 7-day backfill window."""
        recent = datetime.now(timezone.utc) - timedelta(days=1)
        p = Path(f"/root/{recent.year}/{recent.month:02d}/{recent.day:02d}/rollout-new.jsonl")
        result = _codex_file_date(p)
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        self.assertIsNotNone(result)
        self.assertGreaterEqual(
            result, cutoff,
            "yesterday's date must fall within the 7-day cutoff",
        )


if __name__ == "__main__":
    unittest.main()
