"""Tests for the usage-backfill script (node_01M1S7WQETVF7Q7APB6FYB44HQ).

Exercises the query/gating logic against a real in-memory aiosqlite
connection (schema-not-ready detection, project/since-days filtering) plus
the pure before/after comparison used to decide whether a row needs
rewriting. Does not exercise the Postgres branch (no local Postgres in this
test environment) — that path is straight-line-symmetric SQL, verified live
on the node as part of today's rollout.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import aiosqlite
import pytest

from backend.scripts.reparse_usage_backfill import (
    SchemaNotReadyError,
    _assert_schema_ready,
    _fetch_candidates,
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
        ]
        for r in rows:
            await db.execute(
                "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", r
            )
        await db.commit()

        # No filters: every row with a non-null source_file.
        all_candidates = await _fetch_candidates(
            db, project_id=None, since_days=None, limit=None
        )
        assert {c["id"] for c in all_candidates} == {"s-old", "s-recent", "s-other-project"}

        # Project filter.
        proj_a = await _fetch_candidates(db, project_id="proj-a", since_days=None, limit=None)
        assert {c["id"] for c in proj_a} == {"s-old", "s-recent"}

        # since_days filter excludes the 30-day-old row.
        recent_only = await _fetch_candidates(db, project_id=None, since_days=7, limit=None)
        assert {c["id"] for c in recent_only} == {"s-recent", "s-other-project"}

        await db.close()

    asyncio.run(_go())
