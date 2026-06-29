"""Tests for Phase 2 of codex-session-ingestion-v1: Codex sync attribution.

Tests:
  1. Codex fixture whose cwd matches a registered project's repo_path →
     session is attributed to that project_id (merged bucket).
  2. Codex fixture whose cwd matches nothing → session is stored with
     project_id='' (D2-b NULL bucket) and the summary log fires.
  3. Idempotent re-sync → no duplicate session or session_message rows.
  4. Flag off (CCDASH_CODEX_INGEST_ENABLED=False) → sync_codex_sessions is
     a no-op; no sessions are written.

Hard constraints tested:
  - ADR-007: direct-count assertions on all write paths.
  - AC6: flag-off leaves the DB empty.
  - cwd column is stored on the session row.

Run with:
    backend/.venv/bin/python -m pytest backend/tests/test_codex_sync_attribution.py -v

NEVER run unscoped `pytest backend/tests` — test_runtime_bootstrap hangs.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

import aiosqlite

# Modules under test
from backend.db.sync_engine import SyncEngine, _extract_codex_cwd
from backend.db.sqlite_migrations import run_migrations


# ── Helpers ──────────────────────────────────────────────────────────────────

_FIXTURE = Path(__file__).parent / "fixtures" / "codex_rollout_sample.jsonl"

# The cwd baked into the fixture file.
_FIXTURE_CWD = "/Users/testuser/dev/myproject"


def _run(coro: Any) -> Any:
    """Run a coroutine synchronously (test helper)."""
    return asyncio.get_event_loop().run_until_complete(coro)


async def _bootstrap_db(db_path: str) -> None:
    """Create a DB with full migrations so sync_engine can operate."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA busy_timeout = 30000")
        await run_migrations(db)
        await db.commit()


def _insert_project(db_path: str, project_id: str, repo_path: str) -> None:
    """Insert a minimal project row into the projects table."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute(
        """INSERT OR REPLACE INTO projects
           (id, name, path, repo_path, is_active, created_at, updated_at)
           VALUES (?, ?, ?, ?, 1, datetime('now'), datetime('now'))""",
        (project_id, "Test Project", repo_path, repo_path),
    )
    conn.commit()
    conn.close()


def _build_rollout_dir(base: Path, cwd: str) -> tuple[Path, Path]:
    """Create a minimal YYYY/MM/DD/rollout-*.jsonl tree under *base*.

    Returns (date_dir, file_path).
    """
    date_dir = base / "2026" / "06" / "28"
    date_dir.mkdir(parents=True, exist_ok=True)
    file_path = date_dir / "rollout-test-session.jsonl"
    # Write a rollout file with the given cwd.
    lines = [
        json.dumps({
            "type": "turn_context",
            "timestamp": "2026-06-28T10:00:00Z",
            "payload": {
                "type": "turn_context",
                "cwd": cwd,
                "model": "gpt-4-codex",
                "cli_version": "0.64.3",
            },
        }),
        json.dumps({
            "type": "response_item",
            "timestamp": "2026-06-28T10:00:01Z",
            "payload": {
                "type": "user_message",
                "role": "user",
                "content": "implement the feature",
            },
        }),
        json.dumps({
            "type": "response_item",
            "timestamp": "2026-06-28T10:00:02Z",
            "payload": {
                "type": "agent_message",
                "role": "assistant",
                "content": "I will implement it.",
            },
        }),
        json.dumps({
            "type": "event_msg",
            "timestamp": "2026-06-28T10:00:03Z",
            "payload": {
                "type": "task_complete",
                "summary": "Done.",
            },
        }),
    ]
    file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return date_dir, file_path


# ── Test cases ───────────────────────────────────────────────────────────────


class TestCodexCwdExtractor(unittest.TestCase):
    """Unit tests for the lightweight _extract_codex_cwd helper."""

    def test_extracts_cwd_from_turn_context(self) -> None:
        """_extract_codex_cwd reads the cwd from the fixture file."""
        cwd = _extract_codex_cwd(_FIXTURE)
        self.assertEqual(cwd, _FIXTURE_CWD)

    def test_returns_empty_for_missing_cwd(self) -> None:
        """A file without a cwd field returns an empty string."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({"type": "event_msg", "payload": {"type": "task_complete"}}) + "\n")
            tmp = f.name
        try:
            self.assertEqual(_extract_codex_cwd(Path(tmp)), "")
        finally:
            os.unlink(tmp)


class TestCodexSyncAttribution(unittest.IsolatedAsyncioTestCase):
    """Integration tests for sync_codex_sessions attribution and storage."""

    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._db_path = os.path.join(self._tmpdir, "test.db")
        self._codex_root = Path(self._tmpdir) / "codex_sessions"
        self._codex_root.mkdir()
        await _bootstrap_db(self._db_path)

    async def asyncTearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    async def _engine(self) -> SyncEngine:
        db = await aiosqlite.connect(self._db_path)
        await db.execute("PRAGMA busy_timeout = 30000")
        return SyncEngine(db), db

    # ── Test 1: attributed session ────────────────────────────────────────

    async def test_codex_session_attributed_to_matching_project(self) -> None:
        """A Codex session whose cwd matches a registered project's repo_path
        is stored with that project_id (D1-a merged bucket).

        ADR-007 direct-count assertion: exactly one row in sessions with the
        expected project_id and cwd.
        """
        project_id = "proj-skillmeat"
        project_repo_path = "/Users/testuser/dev/myproject"
        _insert_project(self._db_path, project_id, project_repo_path)

        # Build a rollout file with cwd matching the registered project.
        build_rollout_dir(self._codex_root, cwd=project_repo_path)

        engine, db = await self._engine()
        try:
            with patch("backend.db.sync_engine.config") as mock_cfg:
                mock_cfg.CCDASH_CODEX_INGEST_ENABLED = True
                mock_cfg.CCDASH_CODEX_SESSIONS_PATH = str(self._codex_root)
                import backend.db.sync_engine as _se_mod
                real_config = _se_mod.config
                mock_cfg.SYNC_COALESCING_ENABLED = getattr(real_config, "SYNC_COALESCING_ENABLED", True)
                mock_cfg.SIDECAR_CONTEXT_JOIN_ENABLED = getattr(real_config, "SIDECAR_CONTEXT_JOIN_ENABLED", True)
                mock_cfg.STARTUP_SYNC_LIGHT_MODE = False
                mock_cfg.SYNC_RECENT_FIRST_ENABLED = True
                mock_cfg.SYNC_RECENT_FIRST_N = 200
                mock_cfg.STORAGE_PROFILE = None

                stats = await engine.sync_codex_sessions(force=True)
        finally:
            await db.close()

        self.assertGreater(stats["synced"], 0, "at least one Codex session should be synced")
        self.assertEqual(stats["unattributed"], 0, "no unattributed sessions expected")

        # ADR-007: direct-count assertion.
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA busy_timeout = 30000")
        row = conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE project_id = ? AND cwd = ?",
            (project_id, project_repo_path),
        ).fetchone()
        conn.close()
        self.assertEqual(row[0], 1, "exactly one session must be attributed to the project with the correct cwd")

    # ── Test 2: D2-b unattributed bucket ─────────────────────────────────

    async def test_codex_session_unattributed_when_cwd_unmatched(self) -> None:
        """A Codex session whose cwd matches no registered project is stored
        with project_id='' (D2-b NULL bucket).  The unmatched summary log fires.

        ADR-007: direct-count assertion that the session row exists.
        """
        # No project registered → every cwd will be unmatched.
        unmatched_cwd = "/Users/testuser/dev/unknown-repo"
        build_rollout_dir(self._codex_root, cwd=unmatched_cwd)

        engine, db = await self._engine()
        try:
            with (
                patch("backend.db.sync_engine.config") as mock_cfg,
            ):
                mock_cfg.CCDASH_CODEX_INGEST_ENABLED = True
                mock_cfg.CCDASH_CODEX_SESSIONS_PATH = str(self._codex_root)
                import backend.db.sync_engine as _se_mod
                real_config = _se_mod.config
                mock_cfg.SYNC_COALESCING_ENABLED = getattr(real_config, "SYNC_COALESCING_ENABLED", True)
                mock_cfg.SIDECAR_CONTEXT_JOIN_ENABLED = getattr(real_config, "SIDECAR_CONTEXT_JOIN_ENABLED", True)
                mock_cfg.STARTUP_SYNC_LIGHT_MODE = False
                mock_cfg.SYNC_RECENT_FIRST_ENABLED = True
                mock_cfg.SYNC_RECENT_FIRST_N = 200
                mock_cfg.STORAGE_PROFILE = None

                with self.assertLogs("ccdash.sync", level="INFO") as log_ctx:
                    stats = await engine.sync_codex_sessions(force=True)
        finally:
            await db.close()

        # D2-b: unattributed sessions counted.
        self.assertGreater(stats["unattributed"], 0, "unattributed count should be > 0")
        self.assertIn(unmatched_cwd, stats["unattributed_cwds"])

        # Summary log fired: contains the unmatched cwd.
        summary_log = " ".join(log_ctx.output)
        self.assertIn("unmatched_cwds", summary_log, "summary log line must be emitted")
        self.assertIn(unmatched_cwd, summary_log)

        # ADR-007: direct-count assertion — session stored with project_id=''.
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA busy_timeout = 30000")
        row = conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE project_id = '' AND cwd = ?",
            (unmatched_cwd,),
        ).fetchone()
        conn.close()
        self.assertEqual(row[0], 1, "one unattributed session must exist with the correct cwd")

    # ── Test 3: idempotent re-sync ────────────────────────────────────────

    async def test_idempotent_resync_no_duplicate_rows(self) -> None:
        """Running sync_codex_sessions twice on the same file produces no
        duplicate session rows (idempotency via upsert + delete-by-source).
        """
        project_id = "proj-idempotent"
        project_repo_path = "/Users/testuser/dev/myproject"
        _insert_project(self._db_path, project_id, project_repo_path)
        build_rollout_dir(self._codex_root, cwd=project_repo_path)

        engine, db = await self._engine()
        try:
            with patch("backend.db.sync_engine.config") as mock_cfg:
                mock_cfg.CCDASH_CODEX_INGEST_ENABLED = True
                mock_cfg.CCDASH_CODEX_SESSIONS_PATH = str(self._codex_root)
                import backend.db.sync_engine as _se_mod
                real_config = _se_mod.config
                mock_cfg.SYNC_COALESCING_ENABLED = getattr(real_config, "SYNC_COALESCING_ENABLED", True)
                mock_cfg.SIDECAR_CONTEXT_JOIN_ENABLED = getattr(real_config, "SIDECAR_CONTEXT_JOIN_ENABLED", True)
                mock_cfg.STARTUP_SYNC_LIGHT_MODE = False
                mock_cfg.SYNC_RECENT_FIRST_ENABLED = True
                mock_cfg.SYNC_RECENT_FIRST_N = 200
                mock_cfg.STORAGE_PROFILE = None

                # First pass.
                await engine.sync_codex_sessions(force=True)
                # Second pass (force=True to bypass mtime cache).
                await engine.sync_codex_sessions(force=True)
        finally:
            await db.close()

        # ADR-007: exactly one session row, no duplicates.
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA busy_timeout = 30000")
        session_count = conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE project_id = ?",
            (project_id,),
        ).fetchone()[0]
        conn.close()
        self.assertEqual(session_count, 1, "idempotent re-sync must not produce duplicate session rows")

    # ── Test 4: flag-off no-op ────────────────────────────────────────────

    async def test_flag_off_codex_ingest_is_noop(self) -> None:
        """When CCDASH_CODEX_INGEST_ENABLED=False, sync_codex_sessions returns
        empty stats and writes nothing to the DB (AC6).
        """
        project_id = "proj-flagoff"
        project_repo_path = "/Users/testuser/dev/myproject"
        _insert_project(self._db_path, project_id, project_repo_path)
        build_rollout_dir(self._codex_root, cwd=project_repo_path)

        engine, db = await self._engine()
        try:
            with patch("backend.db.sync_engine.config") as mock_cfg:
                # Flag is OFF — all other config is irrelevant.
                mock_cfg.CCDASH_CODEX_INGEST_ENABLED = False
                mock_cfg.CCDASH_CODEX_SESSIONS_PATH = str(self._codex_root)
                import backend.db.sync_engine as _se_mod
                real_config = _se_mod.config
                mock_cfg.SYNC_COALESCING_ENABLED = getattr(real_config, "SYNC_COALESCING_ENABLED", True)

                stats = await engine.sync_codex_sessions(force=True)
        finally:
            await db.close()

        # Stats should be all-zero.
        self.assertEqual(stats["synced"], 0)
        self.assertEqual(stats["skipped"], 0)
        self.assertEqual(stats["unattributed"], 0)

        # No sessions written.
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA busy_timeout = 30000")
        session_count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        conn.close()
        self.assertEqual(session_count, 0, "flag-off must write zero sessions (AC6)")


# ── Module-level helper (used by tests above) ─────────────────────────────────

def build_rollout_dir(codex_root: Path, *, cwd: str) -> Path:
    """Create a ``2026/06/28/rollout-test-session.jsonl`` under *codex_root*.

    Returns the created file path.
    """
    date_dir = codex_root / "2026" / "06" / "28"
    date_dir.mkdir(parents=True, exist_ok=True)
    file_path = date_dir / "rollout-test-session.jsonl"
    lines = [
        json.dumps({
            "type": "turn_context",
            "timestamp": "2026-06-28T10:00:00Z",
            "payload": {"type": "turn_context", "cwd": cwd, "model": "gpt-4-codex", "cli_version": "0.64.3"},
        }),
        json.dumps({
            "type": "response_item",
            "timestamp": "2026-06-28T10:00:01Z",
            "payload": {"type": "user_message", "role": "user", "content": "implement the feature"},
        }),
        json.dumps({
            "type": "response_item",
            "timestamp": "2026-06-28T10:00:02Z",
            "payload": {"type": "agent_message", "role": "assistant", "content": "I will implement it."},
        }),
        json.dumps({
            "type": "event_msg",
            "timestamp": "2026-06-28T10:00:03Z",
            "payload": {"type": "task_complete", "summary": "Done."},
        }),
    ]
    file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return file_path


if __name__ == "__main__":
    unittest.main()
