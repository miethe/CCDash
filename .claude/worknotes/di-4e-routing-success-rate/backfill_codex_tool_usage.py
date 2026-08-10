#!/usr/bin/env python3
"""Backfill stale ``session_tool_usage`` rows for Codex sessions.

Codex sessions written before commit b51de27 (``backend/parsers/platforms/
codex/tool_outcome.py``) went through a broken tool-error detector that
recorded ~0 errors for every GPT/Codex tool call. The parser fix does not
retroactively rewrite rows already in the DB — see the validated
re-measurement method this script follows:

    docs/project_plans/exploration/routing-feedback-success-signal/spikes/
    tool-failures/di-4d-remeasurement.md  (§0)

This script re-parses each in-window Codex session's local JSONL through the
CURRENT parser (``backend.parsers.sessions.parse_session_file``) and
overwrites its ``session_tool_usage`` rows via the SAME repository write path
the live sync pipeline uses (``PostgresSessionRepository.upsert_tool_usage``,
reached in production via ``SessionIngestService.persist_envelope`` from
``backend/db/sync_engine.py``). No hand-rolled INSERT/UPDATE SQL.

Session-id <-> local-file mapping is ``'S-' + path.stem``, the exact rule
``backend.parsers.platforms.codex.parser._make_id`` implements (imported
directly here, not reimplemented, so the two can never drift).

"Codex session" is identified the way the codebase already filters for it —
an exact-match on ``sessions.platform_type = 'Codex'`` (see
``backend/db/repositories/postgres/sessions.py`` around the `platform_type`
comparisons, and ``backend/parsers/platforms/codex/parser.py``'s
``platformType="Codex"`` on every parsed Codex session). This is NOT a model-
name heuristic.

Usage:

    export CCDASH_DSN=postgres://ccdash:...@10.42.10.76:5440/ccdash
    python .claude/worknotes/di-4e-routing-success-rate/backfill_codex_tool_usage.py
        [--apply]                 # default: dry-run, prints a plan + coverage
        [--window-days 30]        # rolling window matching the routing rollup
        [--codex-sessions-root ~/.codex/sessions]
        [--limit N]               # cap candidate sessions (testing)

Safety:
  * Defaults to dry-run. Writing requires the explicit ``--apply`` flag.
  * Never connects anywhere except the DSN in ``$CCDASH_DSN`` — never
    hardcoded, never printed.
  * A session with no local JSONL is left completely untouched and reported
    under the ``no_local_file`` skip reason — never zeroed.
  * Idempotent: ``PostgresSessionRepository.upsert_tool_usage`` deletes then
    re-inserts a session's tool rows inside one transaction, so re-running
    this script against an unchanged local JSONL corpus reproduces the exact
    same end state.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

# Allow ``python .../backfill_codex_tool_usage.py`` to import ``backend.*``
# without requiring a package install (mirrors scripts/backfill_worktree_attribution.py).
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.parsers.platforms.codex.parser import _make_id as codex_make_id  # noqa: E402
from backend.parsers.sessions import parse_session_file  # noqa: E402

CODEX_PLATFORM_TYPE = "Codex"
DEFAULT_WINDOW_DAYS = 30
DEFAULT_CODEX_SESSIONS_ROOT = Path.home() / ".codex" / "sessions"

# Closed skip-reason vocabulary. Every skipped candidate MUST carry one of
# these — a session is never silently dropped from the report.
SKIP_NO_LOCAL_FILE = "no_local_file"
SKIP_PARSE_RETURNED_NONE = "parse_returned_none"


# ---------------------------------------------------------------------------
# Pure planning logic — no DB, no network. Unit-tested without a live DB.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlanRow:
    """One candidate session's backfill outcome."""

    session_id: str
    project_id: str
    jsonl_path: Path | None
    before_tools: list[dict[str, Any]] = field(default_factory=list)
    after_tools: list[dict[str, Any]] = field(default_factory=list)
    skip_reason: str | None = None


def build_jsonl_index(root: Path) -> dict[str, Path]:
    """Map ``session_id -> local jsonl path`` for every file under *root*.

    Session id uses the exact same rule the codex parser uses internally
    (``_make_id``), imported rather than reimplemented so this index can never
    silently diverge from what ``parse_session_file`` itself would compute.

    Sorted traversal makes any (extremely unlikely) stem collision
    deterministic rather than glob-order-dependent.
    """
    index: dict[str, Path] = {}
    if not root.exists():
        return index
    for path in sorted(root.rglob("*.jsonl")):
        index[codex_make_id(path)] = path
    return index


def build_plan(
    candidates: Sequence[Mapping[str, Any]],
    jsonl_index: Mapping[str, Path],
    before_tool_usage: Mapping[str, Sequence[Mapping[str, Any]]],
) -> list[PlanRow]:
    """Turn candidate session rows into a change plan. Pure except for the
    one JSONL read-and-parse per matched candidate (deterministic given
    unchanged file content — no DB, no network).
    """
    rows: list[PlanRow] = []
    for candidate in candidates:
        session_id = str(candidate["id"])
        project_id = str(candidate.get("project_id") or "")
        before = [dict(r) for r in before_tool_usage.get(session_id, [])]

        path = jsonl_index.get(session_id)
        if path is None:
            rows.append(PlanRow(session_id, project_id, None, before, [], SKIP_NO_LOCAL_FILE))
            continue

        session = parse_session_file(path)
        if session is None:
            rows.append(PlanRow(session_id, project_id, path, before, [], SKIP_PARSE_RETURNED_NONE))
            continue

        after = [tool.model_dump() for tool in session.toolsUsed]
        rows.append(PlanRow(session_id, project_id, path, before, after, None))
    return rows


def _truncated_success_count(count: Any, success_rate: Any) -> int:
    """Mirror ``PostgresSessionRepository.upsert_tool_usage``'s exact math
    (``int(count * successRate)`` — truncation, not round) so the printed
    "after" figures match what a real ``--apply`` run would persist.
    """
    try:
        return int(float(count or 0) * float(success_rate or 0.0))
    except (TypeError, ValueError):
        return 0


def summarize_plan(rows: Sequence[PlanRow]) -> dict[str, Any]:
    """Aggregate a plan into a report-ready summary. Pure."""
    total = len(rows)
    matched_rows = [r for r in rows if r.skip_reason is None]
    matched = len(matched_rows)

    skip_counts: dict[str, int] = {}
    for row in rows:
        if row.skip_reason is not None:
            skip_counts[row.skip_reason] = skip_counts.get(row.skip_reason, 0) + 1

    tool_delta: dict[str, dict[str, int]] = {}

    def _entry(name: str) -> dict[str, int]:
        return tool_delta.setdefault(
            name,
            {"before_calls": 0, "before_success": 0, "after_calls": 0, "after_success": 0},
        )

    for row in matched_rows:
        for before in row.before_tools:
            entry = _entry(str(before.get("tool_name") or ""))
            entry["before_calls"] += int(before.get("call_count") or 0)
            entry["before_success"] += int(before.get("success_count") or 0)
        for after in row.after_tools:
            entry = _entry(str(after.get("name") or ""))
            count = int(after.get("count") or 0)
            entry["after_calls"] += count
            entry["after_success"] += _truncated_success_count(count, after.get("successRate"))

    return {
        "total_candidates": total,
        "matched": matched,
        "skip_counts": skip_counts,
        "tool_delta": tool_delta,
    }


def render_report(summary: Mapping[str, Any]) -> str:
    """Human-readable dry-run / pre-apply report. Pure string formatting."""
    total = int(summary["total_candidates"])
    matched = int(summary["matched"])
    pct = (matched / total * 100.0) if total else 0.0

    lines = [
        f"coverage: {matched}/{total} in-window Codex sessions matched a local "
        f"JSONL file ({pct:.1f}%)",
    ]

    skip_counts: Mapping[str, int] = summary["skip_counts"]
    if skip_counts:
        lines.append("skips by reason (never zeroed, left untouched):")
        for reason in sorted(skip_counts):
            lines.append(f"  {reason}: {skip_counts[reason]}")
    else:
        lines.append("skips by reason: none")

    tool_delta: Mapping[str, Mapping[str, int]] = summary["tool_delta"]
    lines.append("per-tool before -> after (call_count / success_count):")
    if not tool_delta:
        lines.append("  (no matched sessions to summarize)")
    for name in sorted(tool_delta):
        d = tool_delta[name]
        lines.append(
            f"  {name}: {d['before_calls']}/{d['before_success']} -> "
            f"{d['after_calls']}/{d['after_success']}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Write path — reuses PostgresSessionRepository.upsert_tool_usage verbatim.
# ---------------------------------------------------------------------------


async def apply_plan(repo: Any, rows: Sequence[PlanRow]) -> int:
    """Write ``after_tools`` for every matched row via *repo*'s own
    ``upsert_tool_usage``. Skipped rows (no local file / parse failure) are
    never touched. Returns the number of sessions written.

    *repo* is duck-typed on ``upsert_tool_usage(session_id, tools, project_id)``
    — in production this is ``PostgresSessionRepository``; tests exercise the
    identical contract against ``SqliteSessionRepository`` for a real (non-
    mocked) idempotency check without touching Postgres.
    """
    written = 0
    for row in rows:
        if row.skip_reason is not None:
            continue
        await repo.upsert_tool_usage(row.session_id, row.after_tools, row.project_id)
        written += 1
    return written


# ---------------------------------------------------------------------------
# DB access — isolated behind small async functions so tests can monkeypatch
# them without a live Postgres connection.
# ---------------------------------------------------------------------------


async def _open_pool(dsn: str) -> Any:
    import asyncpg  # local import: keep asyncpg optional for pure-logic tests

    return await asyncpg.create_pool(dsn)


async def fetch_codex_candidates(
    pool: Any, window_days: int, limit: int | None = None
) -> list[dict[str, Any]]:
    """Every in-window Codex session. ``platform_type = 'Codex'`` exact match,
    same identification the codebase's own Postgres queries use.
    """
    safe_window = max(1, int(window_days))
    # ``sessions.updated_at`` is TEXT in this schema, not a timestamp, so it must be
    # compared against a formatted string — `>= NOW() - INTERVAL` raises
    # `operator does not exist: text >= timestamp with time zone`. This mirrors the
    # D-b4 verification query in di-4d-remeasurement.md §1 verbatim so the backfill
    # and the gate that judges it select the same window.
    sql = (
        "SELECT id, project_id FROM sessions "
        "WHERE TRIM(COALESCE(platform_type, '')) = $1 "
        "AND updated_at >= to_char("
        f"NOW() - INTERVAL '{safe_window} days', 'YYYY-MM-DD\"T\"HH24:MI:SS') "
        "ORDER BY id"
    )
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = await pool.fetch(sql, CODEX_PLATFORM_TYPE)
    return [{"id": r["id"], "project_id": r["project_id"]} for r in rows]


async def fetch_existing_tool_usage(
    pool: Any, session_ids: Sequence[str]
) -> dict[str, list[dict[str, Any]]]:
    """Current (stale) ``session_tool_usage`` rows for *session_ids* — the
    "before" side of the report.
    """
    if not session_ids:
        return {}
    rows = await pool.fetch(
        "SELECT session_id, tool_name, call_count, success_count "
        "FROM session_tool_usage WHERE session_id = ANY($1::text[])",
        list(session_ids),
    )
    out: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        out.setdefault(r["session_id"], []).append(
            {
                "tool_name": r["tool_name"],
                "call_count": r["call_count"],
                "success_count": r["success_count"],
            }
        )
    return out


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


async def _async_main(args: argparse.Namespace) -> int:
    dsn = os.environ.get("CCDASH_DSN")
    if not dsn:
        print("ERROR: CCDASH_DSN is not set. Refusing to guess a connection target.", file=sys.stderr)
        return 2

    pool = await _open_pool(dsn)
    try:
        candidates = await fetch_codex_candidates(pool, args.window_days, args.limit)
        session_ids = [c["id"] for c in candidates]
        before = await fetch_existing_tool_usage(pool, session_ids)
        jsonl_index = build_jsonl_index(args.codex_sessions_root)
        rows = build_plan(candidates, jsonl_index, before)
        summary = summarize_plan(rows)

        print(render_report(summary))

        if not args.apply:
            print("\nDRY RUN: zero writes performed. Re-run with --apply to commit.")
            return 0

        from backend.db.repositories.postgres.sessions import PostgresSessionRepository

        repo = PostgresSessionRepository(pool)
        written = await apply_plan(repo, rows)
        print(f"\nAPPLIED: wrote session_tool_usage for {written} session(s).")
        return 0
    finally:
        await pool.close()


def _build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Commit changes. Default is dry-run (prints the plan and coverage).",
    )
    ap.add_argument(
        "--window-days",
        type=int,
        default=DEFAULT_WINDOW_DAYS,
        help=f"Rolling window in days, matching the routing rollup (default {DEFAULT_WINDOW_DAYS}).",
    )
    ap.add_argument(
        "--codex-sessions-root",
        type=Path,
        default=DEFAULT_CODEX_SESSIONS_ROOT,
        help="Root directory to glob for local Codex JSONL files.",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap candidate sessions fetched from the DB (testing).",
    )
    return ap


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    sys.exit(main())
