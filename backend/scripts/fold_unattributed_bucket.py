"""Fold the 3 residual catch-all project rows into one frozen unattributed bucket.

Follow-up to ``scripts/fold_junk_projects.py`` (node_01KZ495B2QXDVB091H9WMKB191,
merged 2026-08-03): everything with ``cwd`` evidence was already re-pointed to
its real project. What is left in the 3 catch-all rows has NO independent
evidence -- ``source_file`` is self-referential
(``ccdash-source:v1/<project_id>/...``), so it only echoes the bucket the row
is already in. Nick's decision (2026-09-10, AskUserQuestion): collapse the 3
rows into ONE frozen ``unattributed`` bucket, excluded from per-project
metrics; raw sessions stay directly queryable by project_id.

The 3 catch-all rows (identified from the IntentTree node's residue table,
node_01KZ4RB7TPACS44WJMMXTJZ6BT):
    ccp-3f61311bd972  "development"  -- the dev parent dir, not a repo
    ccp-61d5a4bb0de5  "miethe"       -- $HOME catch-all
    ccp-89da067a7379  "agentic-meta-dev-infra-ica-codex-shim" -- decoder artifact

Deliberately idempotent and non-destructive:
  - The bucket project row is created with ``INSERT ... ON CONFLICT DO NOTHING``.
  - Each catch-all row's sessions are re-pointed with
    ``sessions.prior_project_id`` recording where they came from (reversibility
    -- see this module's docstring "Undo" section below).
  - A session id that would collide with one the bucket already owns (same
    composite PK component) is left in place rather than orphaned or
    overwritten -- surfaced via ``sessions_collision_skipped``.
  - The 3 catch-all rows are marked ``bucket_role = 'retired_catchall'``
    (never deleted), so ``projects.bucket_role IS NOT NULL`` is a stable,
    single, later-verifiable fact about them.
  - Re-running produces zero further moves and zero further retirements --
    the UPDATEs' own WHERE clauses are the idempotency guard, not an
    external check.

Undo (one paragraph): every moved session still carries
``prior_project_id`` = its pre-fold ``project_id`` (one of the 3 catch-all
ids above), and the 3 catch-all rows are still present (never deleted, just
``bucket_role = 'retired_catchall'``). To reverse: for each session with
``project_id = '<bucket id>' AND prior_project_id IS NOT NULL``, run
``UPDATE sessions SET project_id = prior_project_id, prior_project_id = NULL``,
then clear ``bucket_role`` on the 3 catch-all rows (and optionally delete the
now-empty bucket row).

Usage (against the LIVE Postgres store -- NOT run by this leg; the front
decides that after merge):
    python -m backend.scripts.fold_unattributed_bucket \\
        --database-url "$CCDASH_DATABASE_URL" --apply
Omit ``--apply`` for a dry run (the transaction is rolled back; the printed
counts are what WOULD happen).
"""
from __future__ import annotations

import argparse
import asyncio
import os
from typing import Any

import aiosqlite

UNATTRIBUTED_BUCKET_ID = "ccp-unattributed"
UNATTRIBUTED_BUCKET_NAME = "Unattributed"
UNATTRIBUTED_BUCKET_DESCRIPTION = (
    "Frozen home for sessions with no independent attribution evidence "
    "(ccdash-unattributed-0910). Excluded from per-project metrics; its own "
    "sessions remain directly queryable by project_id."
)

# The 3 residual catch-all rows named in node_01KZ4RB7TPACS44WJMMXTJZ6BT's
# residue table. Not auto-discovered -- these are the specific ids Nick's
# decision named; a script that "found more junk buckets" on its own would
# be making a second policy call this leg was not asked to make.
CATCHALL_PROJECT_IDS: tuple[str, ...] = (
    "ccp-3f61311bd972",  # "development" -- the dev parent dir, not a repo
    "ccp-61d5a4bb0de5",  # "miethe" -- $HOME catch-all
    "ccp-89da067a7379",  # "agentic-meta-dev-infra-ica-codex-shim" -- decoder artifact
)


async def fold_unattributed_bucket(db: Any) -> dict[str, int]:
    """Idempotently fold ``CATCHALL_PROJECT_IDS`` into ``UNATTRIBUTED_BUCKET_ID``.

    Dual-path for SQLite (aiosqlite) and PostgreSQL (asyncpg), mirroring the
    ``isinstance(db, aiosqlite.Connection)`` convention established in
    ``system_metrics.py``. Returns per-run counts; a second call against
    unchanged state returns all-zero move/retire counts (idempotent).
    """
    is_sqlite = isinstance(db, aiosqlite.Connection)

    if is_sqlite:
        await db.execute(
            "INSERT INTO projects (id, name, description, bucket_role)"
            " VALUES (?, ?, ?, 'unattributed_bucket')"
            " ON CONFLICT(id) DO NOTHING",
            (UNATTRIBUTED_BUCKET_ID, UNATTRIBUTED_BUCKET_NAME, UNATTRIBUTED_BUCKET_DESCRIPTION),
        )
    else:
        await db.execute(
            "INSERT INTO projects (id, name, description, bucket_role)"
            " VALUES ($1, $2, $3, 'unattributed_bucket')"
            " ON CONFLICT(id) DO NOTHING",
            UNATTRIBUTED_BUCKET_ID,
            UNATTRIBUTED_BUCKET_NAME,
            UNATTRIBUTED_BUCKET_DESCRIPTION,
        )

    sessions_moved = 0
    catchall_rows_retired = 0
    for catchall_id in CATCHALL_PROJECT_IDS:
        if catchall_id == UNATTRIBUTED_BUCKET_ID:
            continue  # pragma: no cover -- defensive; the two ids never collide

        if is_sqlite:
            cursor = await db.execute(
                """
                UPDATE sessions
                SET prior_project_id = project_id, project_id = ?
                WHERE project_id = ?
                  AND NOT EXISTS (
                      SELECT 1 FROM sessions b
                      WHERE b.project_id = ? AND b.id = sessions.id
                  )
                """,
                (UNATTRIBUTED_BUCKET_ID, catchall_id, UNATTRIBUTED_BUCKET_ID),
            )
            sessions_moved += cursor.rowcount or 0
        else:
            result = await db.execute(
                """
                UPDATE sessions
                SET prior_project_id = project_id, project_id = $1
                WHERE project_id = $2
                  AND NOT EXISTS (
                      SELECT 1 FROM sessions b
                      WHERE b.project_id = $1 AND b.id = sessions.id
                  )
                """,
                UNATTRIBUTED_BUCKET_ID,
                catchall_id,
            )
            sessions_moved += int(result.rsplit(" ", 1)[-1])

        if is_sqlite:
            retire_cursor = await db.execute(
                "UPDATE projects SET bucket_role = 'retired_catchall'"
                " WHERE id = ? AND bucket_role IS NULL",
                (catchall_id,),
            )
            catchall_rows_retired += retire_cursor.rowcount or 0
        else:
            retire_result = await db.execute(
                "UPDATE projects SET bucket_role = 'retired_catchall'"
                " WHERE id = $1 AND bucket_role IS NULL",
                catchall_id,
            )
            catchall_rows_retired += int(retire_result.rsplit(" ", 1)[-1])

    if is_sqlite:
        await db.commit()

    return {
        "sessions_moved": sessions_moved,
        "catchall_rows_retired": catchall_rows_retired,
    }


async def _main(database_url: str, apply: bool) -> None:
    import asyncpg

    connection = await asyncpg.connect(database_url)
    try:
        tx = connection.transaction()
        await tx.start()
        stats = await fold_unattributed_bucket(connection)
        if apply:
            await tx.commit()
        else:
            await tx.rollback()
    finally:
        await connection.close()
    print(
        f"sessions_moved={stats['sessions_moved']} "
        f"catchall_rows_retired={stats['catchall_rows_retired']} "
        f"(dry_run={not apply})"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("CCDASH_DATABASE_URL", ""))
    parser.add_argument("--apply", action="store_true", help="Commit. Default is dry-run.")
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or CCDASH_DATABASE_URL is required")
    asyncio.run(_main(args.database_url, args.apply))


if __name__ == "__main__":
    main()
