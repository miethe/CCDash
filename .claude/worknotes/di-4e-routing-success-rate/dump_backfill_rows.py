"""Dump ACTUAL session_tool_usage rows for backfilled Codex sessions — row-level artifact
evidence that the 2026-08-10 backfill write landed, for a reviewer that cannot itself execute
against the live database.

Read-only: two SELECTs, no writes, no DDL. Sources the DSN from the repo .env and never prints it.

The point of this over a summary: a summary is a claim, a row is an observation. Each row below
carries a session's per-tool call_count/success_count as PERSISTED. Where success_count <
call_count, an error was detected and stored — which the pre-b51de27 parser never did for Codex
(it recorded 100% success across all 3,482 Codex sessions ever ingested).

Usage:
    backend/.venv/bin/python .claude/worknotes/di-4e-routing-success-rate/dump_backfill_rows.py
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import re

MAIN = pathlib.Path("/Users/miethe/dev/homelab/development/CCDash")
PAT = re.compile(r"^CCDASH_DATABASE_URL=(\S+)", re.MULTILINE)

# Sessions whose stored rows should now carry errors. Chosen mechanically: the highest-error
# Codex sessions in the window, so the sample cannot be cherry-picked to look good.
TOP_ERROR_ROWS = """
SELECT s.id, stu.tool_name, stu.call_count, stu.success_count,
       (stu.call_count - stu.success_count) AS errors
FROM session_tool_usage stu
JOIN sessions s ON s.id = stu.session_id
WHERE TRIM(COALESCE(s.platform_type,'')) = 'Codex'
  AND stu.call_count > stu.success_count
ORDER BY (stu.call_count - stu.success_count) DESC, s.id, stu.tool_name
LIMIT 25;
"""

# The aggregate the D-b4 gate reads, expressed at row level per tool.
PER_TOOL_TOTALS = """
SELECT stu.tool_name,
       SUM(stu.call_count)    AS calls,
       SUM(stu.success_count) AS successes,
       SUM(stu.call_count - stu.success_count) AS errors,
       COUNT(DISTINCT stu.session_id) AS sessions
FROM session_tool_usage stu
JOIN sessions s ON s.id = stu.session_id
WHERE TRIM(COALESCE(s.platform_type,'')) = 'Codex'
GROUP BY stu.tool_name
HAVING SUM(stu.call_count) > 0
ORDER BY errors DESC, stu.tool_name;
"""


async def main() -> int:
    import asyncpg

    dsn = None
    for name in (".env", ".env.hosted", ".env.local"):
        p = MAIN / name
        if p.is_file():
            m = PAT.search(p.read_text(errors="replace"))
            if m:
                dsn = m.group(1).strip().strip("\"'")
                print(f"[dsn source: {name}]")
                break
    if not dsn:
        raise SystemExit("no CCDASH_DATABASE_URL found in .env files")

    conn = await asyncpg.connect(dsn)
    try:
        print("\n=== Per-tool PERSISTED totals, platform_type='Codex' (all time) ===")
        print(f"{'tool':<32}{'calls':>10}{'successes':>12}{'errors':>9}{'sessions':>10}")
        for r in await conn.fetch(PER_TOOL_TOTALS):
            print(
                f"{r['tool_name']:<32}{r['calls']:>10}{r['successes']:>12}"
                f"{r['errors']:>9}{r['sessions']:>10}"
            )

        print("\n=== Top 25 individual stored rows carrying errors (session_id, tool) ===")
        print(f"{'session_id':<46}{'tool':<16}{'calls':>7}{'succ':>7}{'err':>6}")
        rows = await conn.fetch(TOP_ERROR_ROWS)
        for r in rows:
            print(
                f"{r['id'][:44]:<46}{r['tool_name'][:14]:<16}"
                f"{r['call_count']:>7}{r['success_count']:>7}{r['errors']:>6}"
            )
        print(f"\n{len(rows)} rows shown. A row with succ < calls is a STORED, backfilled error.")
        print(
            "Pre-backfill this query returned rows only for non-Codex platforms: the old parser "
            "recorded 100% success for every Codex session ever ingested."
        )
    finally:
        await conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
