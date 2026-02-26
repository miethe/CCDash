#!/usr/bin/env python3
"""Backfill telemetry fact events from persisted session tables.

Usage:
  python backend/scripts/telemetry_backfill.py
  python backend/scripts/telemetry_backfill.py --project default-skillmeat
  python backend/scripts/telemetry_backfill.py --all-projects
"""
from __future__ import annotations

import argparse
import asyncio

from backend.db import connection, migrations, sync_engine
from backend.project_manager import project_manager


async def _run(project_id: str | None, all_projects: bool) -> int:
    db = await connection.get_connection()
    await migrations.run_migrations(db)
    engine = sync_engine.SyncEngine(db)

    if all_projects:
        targets = project_manager.list_projects()
    elif project_id:
        project = project_manager.get_project(project_id)
        if not project:
            print(f"Project not found: {project_id}")
            await connection.close_connection()
            return 1
        targets = [project]
    else:
        active = project_manager.get_active_project()
        targets = [active] if active else []

    if not targets:
        print("No projects available to backfill.")
        await connection.close_connection()
        return 0

    for project in targets:
        stats = await engine._backfill_telemetry_events_for_project(project.id)  # noqa: SLF001
        print(
            f"{project.id}: sessions_backfilled={stats.get('sessions', 0)} "
            f"events_written={stats.get('events', 0)}"
        )

    await connection.close_connection()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default="", help="Project ID to backfill (default: active project)")
    parser.add_argument("--all-projects", action="store_true", help="Backfill all configured projects")
    args = parser.parse_args()
    return asyncio.run(_run(args.project or None, args.all_projects))


if __name__ == "__main__":
    raise SystemExit(main())
