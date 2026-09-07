#!/usr/bin/env python3
"""Read-only enumeration of journal-bearing rows already in ``session_messages``.

**This script counts. It never deletes, updates, or prints row content.** Removal of the
already-indexed rows is Mode-D — Nick's decision, deliberately not this script's
(``node_01M1YV12EH7AQSXSMSFSKQJXM8``). There is no ``--delete`` flag and adding one here would
be the wrong place for it.

Baseline, measured 2026-09-07 before CCDash adopted the exclusion predicate:
**208 rows across 59 sessions**. Re-run this after the fix is deployed to confirm the number has
stopped growing. It is expected to stay at or near the baseline until Nick decides on removal —
a *falling* number without a decision means something deleted rows, which is itself a finding.

Usage
-----
    # Against a DSN (asyncpg):
    python scripts/journal_egress_enumerate.py --dsn postgresql://user@host:5440/ccdash

    # Or emit the SQL to pipe anywhere psql can reach, which is how the baseline was taken:
    python scripts/journal_egress_enumerate.py --print-sql \\
      | ssh agentic-nuc 'podman exec -i ccdash_postgres_1 psql -U ccdash -d ccdash'

The DSN may also come from ``CCDASH_ENUMERATE_DSN`` or ``CCDASH_DATABASE_URL``.

⚠️ **The instrument trap.** The haystack is ``content || metadata_json``, never ``content``
alone. A first pass that scanned ``content`` returned 10 and was a false clean:
``session_messages.content`` averages 11 characters on Bash tool rows (421,313 of them, zero
carrying a recognizable shell command) while the tool input lives in ``metadata_json``
(avg 3,979 chars). The corrected haystack found 20x as much. Do not "simplify" the query.

⚠️ **``metis_cwd = 0`` here is UNMEASURED, not clean.** This query resolves that rule through
``sessions.cwd``, which is populated on only ~15% of CCDash sessions. The *live* predicate does
not depend on that column — it reads each record's own ``cwd`` field at parse time — but a
retrospective count over stored rows has no such field to read. See
``docs/guides/journal-transcript-egress.md``.

The query takes roughly 3m20s against ~1.5M rows.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

SQL_PATH = Path(__file__).resolve().parent / "sql" / "journal-egress-enumerate.sql"

#: The count measured before the predicate was adopted. Reported alongside the live number so a
#: reader never has to go find it.
BASELINE_ROWS = 208
BASELINE_SESSIONS = 59
BASELINE_DATE = "2026-09-07"


def load_sql() -> str:
    return SQL_PATH.read_text(encoding="utf-8")


def _sql_for_driver(raw: str) -> str:
    """Strip psql meta-commands (``\\pset`` etc.) so asyncpg can run the same file."""
    return "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("\\"))


async def _run(dsn: str) -> int:
    try:
        import asyncpg  # noqa: PLC0415 — optional dependency; --print-sql works without it
    except ImportError:
        print(
            "asyncpg is not installed. Use --print-sql and pipe to psql instead.",
            file=sys.stderr,
        )
        return 2

    conn = await asyncpg.connect(dsn)
    try:
        # Belt-and-braces: the query is a pure SELECT, and the session is read-only anyway.
        await conn.execute("SET default_transaction_read_only = on")
        rows = await conn.fetch(_sql_for_driver(load_sql()))
    finally:
        await conn.close()

    total_rows = 0
    total_sessions = 0
    print(f"{'reason':<28}{'matched_rows':>14}{'distinct_sessions':>20}")
    print("-" * 62)
    for row in rows:
        reason = row["reason"]
        print(f"{reason:<28}{row['matched_rows']:>14}{row['distinct_sessions']:>20}")
        if reason == "TOTAL_MATCHED":
            total_rows = int(row["matched_rows"])
            total_sessions = int(row["distinct_sessions"])
    print("-" * 62)
    print(
        f"baseline {BASELINE_DATE} (pre-predicate): {BASELINE_ROWS} rows / "
        f"{BASELINE_SESSIONS} sessions   |   now: {total_rows} rows / {total_sessions} sessions"
        f"   delta: {total_rows - BASELINE_ROWS:+d} rows"
    )
    print("metis_cwd is UNMEASURED here (sessions.cwd populated on ~15% of rows), never 'clean'.")
    print("Nothing was modified. Removal of these rows is Mode-D — Nick's decision.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dsn", default="", help="postgres DSN; else CCDASH_ENUMERATE_DSN / CCDASH_DATABASE_URL")
    parser.add_argument("--print-sql", action="store_true", help="print the SQL and exit (pipe to psql)")
    args = parser.parse_args(argv)

    if args.print_sql:
        print(load_sql())
        return 0

    dsn = args.dsn or os.environ.get("CCDASH_ENUMERATE_DSN") or os.environ.get("CCDASH_DATABASE_URL") or ""
    if not dsn:
        parser.error("no DSN given; pass --dsn, set CCDASH_ENUMERATE_DSN, or use --print-sql")
    return asyncio.run(_run(dsn))


if __name__ == "__main__":
    raise SystemExit(main())
