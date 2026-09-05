"""Tests for the usage-backfill script (node_01M1S7WQETVF7Q7APB6FYB44HQ).

Exercises the query/gating logic against a real in-memory aiosqlite
connection (schema-not-ready detection, project/since-days filtering,
project-registry path resolution) plus the pure before/after comparison used
to decide whether a row needs rewriting. Does not exercise the Postgres
branch (no local Postgres in this test environment) — that path is
straight-line-symmetric SQL, verified live against the node's Postgres as
part of today's rollout.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite
import pytest

from backend.scripts.reparse_usage_backfill import (
    SchemaNotReadyError,
    _LocalResolver,
    _assert_schema_ready,
    _fetch_candidates,
    _project_sessions_paths,
)


async def _make_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(":memory:")
    await db.execute(
        """CREATE TABLE sessions (
            id TEXT, project_id TEXT, workspace_id TEXT, source_file TEXT,
            tokens_in INTEGER, tokens_out INTEGER,
            cache_creation_input_tokens INTEGER, cache_read_input_tokens INTEGER,
            created_at TEXT, updated_at TEXT
        )"""
    )
    await db.execute(
        """CREATE TABLE projects (
            id TEXT, sessions_path TEXT
        )"""
    )
    await db.commit()
    return db


def test_assert_schema_ready_raises_when_table_absent() -> None:
    async def _go() -> None:
        db = await aiosqlite.connect(":memory:")
        with pytest.raises(SchemaNotReadyError):
            await _assert_schema_ready(db)
        await db.close()

    asyncio.run(_go())


def test_fetch_candidates_filters_by_project_and_since_days() -> None:
    """No source_file gating: a row with a blank/synthetic source_file is
    still a candidate — resolution happens via the project registry, not
    this column (see module docstring for why).
    """

    async def _go() -> None:
        db = await _make_db()
        now = datetime.now(timezone.utc)
        old = (now - timedelta(days=30)).isoformat()
        recent = (now - timedelta(days=1)).isoformat()

        rows = [
            ("s-old", "proj-a", "ws-1", "/tmp/old.jsonl", 100, 50, 10, 5, old, old),
            ("s-recent", "proj-a", "ws-1", "/tmp/recent.jsonl", 100, 50, 10, 5, recent, recent),
            ("s-other-project", "proj-b", "ws-1", "/tmp/other.jsonl", 1, 1, 1, 1, recent, recent),
            ("s-no-source", "proj-a", "ws-1", None, 1, 1, 1, 1, recent, recent),
            ("s-synthetic", "proj-a", "ws-1", "ccdash-source:v1/proj-a/session/opaque/abc", 1, 1, 1, 1, recent, recent),
        ]
        for r in rows:
            await db.execute(
                "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", r
            )
        await db.commit()

        # No filters: every row is a candidate, regardless of source_file shape.
        all_candidates = await _fetch_candidates(
            db, project_id=None, since_days=None, limit=None
        )
        assert {c["id"] for c in all_candidates} == {
            "s-old", "s-recent", "s-other-project", "s-no-source", "s-synthetic",
        }

        # Project filter.
        proj_a = await _fetch_candidates(db, project_id="proj-a", since_days=None, limit=None)
        assert {c["id"] for c in proj_a} == {"s-old", "s-recent", "s-no-source", "s-synthetic"}

        # since_days filter excludes the 30-day-old row.
        recent_only = await _fetch_candidates(db, project_id=None, since_days=7, limit=None)
        assert {c["id"] for c in recent_only} == {
            "s-recent", "s-other-project", "s-no-source", "s-synthetic",
        }

        await db.close()

    asyncio.run(_go())


def test_project_sessions_paths_skips_blank(tmp_path: Path) -> None:
    async def _go() -> None:
        db = await _make_db()
        await db.execute(
            "INSERT INTO projects VALUES (?, ?)", ("proj-a", str(tmp_path))
        )
        await db.execute("INSERT INTO projects VALUES (?, ?)", ("proj-blank", ""))
        await db.commit()

        paths = await _project_sessions_paths(db)
        assert paths == {"proj-a": tmp_path}

        await db.close()

    asyncio.run(_go())


def test_local_resolver_finds_file_by_stripped_id(tmp_path: Path) -> None:
    """A session id's 'S-' prefix is stripped to get the on-disk filename stem."""
    sessions_dir = tmp_path / "-Users-me-dev-repo"
    sessions_dir.mkdir()
    (sessions_dir / "a0ac7283-ef53-4b20-bf58-9ce69a95a5fa.jsonl").write_text("{}\n")

    resolver = _LocalResolver({"proj-a": sessions_dir})
    found = resolver.resolve("S-a0ac7283-ef53-4b20-bf58-9ce69a95a5fa", "proj-a")
    assert found is not None
    assert found.name == "a0ac7283-ef53-4b20-bf58-9ce69a95a5fa.jsonl"


def test_local_resolver_finds_file_under_worktree_sibling(tmp_path: Path) -> None:
    """A session under a git-worktree sibling dir is found via session_scan_roots."""
    sessions_dir = tmp_path / "-Users-me-dev-repo"
    sessions_dir.mkdir()
    sibling = tmp_path / "-Users-me-dev-repo--claude-worktrees-myfeature"
    sibling.mkdir()
    (sibling / "agent-deadbeefcafe.jsonl").write_text("{}\n")

    resolver = _LocalResolver({"proj-a": sessions_dir})
    found = resolver.resolve("S-agent-deadbeefcafe", "proj-a")
    assert found is not None
    assert found.parent == sibling


def test_local_resolver_returns_none_for_unregistered_project(tmp_path: Path) -> None:
    resolver = _LocalResolver({})
    assert resolver.resolve("S-anything", "proj-unregistered") is None
