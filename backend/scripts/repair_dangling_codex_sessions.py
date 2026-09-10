"""Repair imported opaque sessions that were incorrectly labelled as Codex.

This is deliberately a one-way, idempotent data repair rather than a
destructive migration.  The opaque source scheme denotes imported data, not a
filesystem Codex rollout.  Registering its supplied project identity preserves
the original attribution key; reclassifying the rows removes them from Codex
metrics without deleting transcripts or changing session ids.
"""
from __future__ import annotations

import argparse
import asyncio
import os
from typing import Any

import asyncpg


OPAQUE_SOURCE_PREFIX = "ccdash-source:v1/"
UNATTRIBUTED_PLATFORM_TYPE = "Unattributed"


async def repair(connection: Any) -> tuple[int, int]:
    """Register missing imported projects and reclassify their opaque sessions.

    Returns ``(projects_registered, sessions_reclassified)``.  Both SQL
    statements are idempotent, and no session row is deleted.
    """
    project_rows = await connection.fetch(
        """
        SELECT DISTINCT s.project_id
        FROM sessions AS s
        WHERE s.platform_type = 'Codex'
          AND s.source_file LIKE $1
          AND s.project_id <> ''
          AND NOT EXISTS (SELECT 1 FROM projects AS p WHERE p.id = s.project_id)
        """,
        f"{OPAQUE_SOURCE_PREFIX}%",
    )
    for row in project_rows:
        project_id = str(row["project_id"])
        await connection.execute(
            """
            INSERT INTO projects (id, name, description, agent_platforms_json)
            VALUES ($1, $2, $3, $4::jsonb)
            ON CONFLICT (id) DO NOTHING
            """,
            project_id,
            f"Unattributed imported sessions ({project_id})",
            "Registered by repair_dangling_codex_sessions; opaque imported session source.",
            '["Unattributed"]',
        )

    result = await connection.execute(
        """
        UPDATE sessions AS s
        SET platform_type = $1
        WHERE s.platform_type = 'Codex'
          AND s.source_file LIKE $2
          AND s.project_id <> ''
          AND EXISTS (SELECT 1 FROM projects AS p WHERE p.id = s.project_id)
        """,
        UNATTRIBUTED_PLATFORM_TYPE,
        f"{OPAQUE_SOURCE_PREFIX}%",
    )
    return len(project_rows), int(result.rsplit(" ", 1)[-1])


async def _main(database_url: str) -> None:
    connection = await asyncpg.connect(database_url)
    try:
        async with connection.transaction():
            projects, sessions = await repair(connection)
    finally:
        await connection.close()
    print(f"projects_registered={projects} sessions_reclassified={sessions}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("CCDASH_DATABASE_URL", ""))
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or CCDASH_DATABASE_URL is required")
    asyncio.run(_main(args.database_url))


if __name__ == "__main__":
    main()
