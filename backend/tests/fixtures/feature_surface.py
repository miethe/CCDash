"""Shared fixture helpers for feature-surface parity tests.

Seed helpers mirror the schema used by test_feature_rollup_query.py so that
parity tests can build identical data without duplicating boilerplate.

All helpers accept an open aiosqlite.Connection and return the IDs they
inserted so callers can reference them in assertions.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone


def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def seed_feature(
    db,
    fid: str,
    *,
    project_id: str,
    name: str = "",
    status: str = "in-progress",
) -> str:
    now = _now()
    await db.execute(
        """INSERT INTO features (id, project_id, name, status, created_at, updated_at, data_json)
           VALUES (?, ?, ?, ?, ?, ?, '{}')
           ON CONFLICT(id) DO NOTHING""",
        (fid, project_id, name or fid, status, now, now),
    )
    return fid


async def seed_session(
    db,
    session_id: str | None = None,
    *,
    project_id: str,
    parent_session_id: str | None = None,
    total_cost: float = 1.0,
    display_cost_usd: float | None = None,
    observed_tokens: int = 100,
    model_io_tokens: int = 80,
    cache_input_tokens: int = 20,
    model: str = "claude-sonnet-4-5",
    started_at: str | None = None,
    updated_at: str | None = None,
) -> str:
    sid = session_id or _uid()
    now = _now()
    started = started_at or now
    updated = updated_at or now
    root = sid if not parent_session_id else parent_session_id
    await db.execute(
        """INSERT INTO sessions (
            id, project_id, task_id, status, model,
            platform_type, total_cost, display_cost_usd,
            observed_tokens, model_io_tokens, cache_input_tokens,
            parent_session_id, started_at, ended_at, created_at, updated_at, source_file,
            thread_kind, root_session_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO NOTHING""",
        (
            sid, project_id, "", "completed", model,
            "Claude Code", total_cost, display_cost_usd,
            observed_tokens, model_io_tokens, cache_input_tokens,
            parent_session_id, started, started, now, updated, f"{sid}.jsonl",
            "", root,
        ),
    )
    return sid


async def link_feature_session(db, feature_id: str, session_id: str) -> None:
    now = _now()
    await db.execute(
        """INSERT INTO entity_links (
            source_type, source_id, target_type, target_id, link_type,
            origin, confidence, depth, sort_order, created_at
        ) VALUES ('feature', ?, 'session', ?, 'related', 'auto', 1.0, 0, 0, ?)
        ON CONFLICT(source_type, source_id, target_type, target_id, link_type) DO NOTHING""",
        (feature_id, session_id, now),
    )
