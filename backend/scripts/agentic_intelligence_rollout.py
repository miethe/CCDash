#!/usr/bin/env python3
"""Sync SkillMeat definitions, backfill observations, and recompute workflow rollups.

Usage:
  python backend/scripts/agentic_intelligence_rollout.py
  python backend/scripts/agentic_intelligence_rollout.py --project default-skillmeat
  python backend/scripts/agentic_intelligence_rollout.py --all-projects
  python backend/scripts/agentic_intelligence_rollout.py --skip-sync --skip-backfill
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.db import connection, migrations
from backend.project_manager import project_manager
from backend.services.agentic_intelligence_flags import (
    require_skillmeat_integration_enabled,
    workflow_analytics_enabled,
)
from backend.services.integrations.skillmeat_sync import sync_skillmeat_definitions
from backend.services.stack_observations import backfill_session_stack_observations
from backend.services.workflow_effectiveness import detect_failure_patterns, get_workflow_effectiveness


def _iter_projects(project_id: str | None, all_projects: bool) -> list[Any]:
    if all_projects:
        return project_manager.list_projects()
    if project_id:
        project = project_manager.get_project(project_id)
        return [project] if project else []
    active = project_manager.get_active_project()
    return [active] if active else []


async def _run(
    project_id: str | None,
    *,
    all_projects: bool,
    skip_sync: bool,
    skip_backfill: bool,
    skip_recompute: bool,
    limit: int,
    force_recompute: bool,
) -> int:
    require_skillmeat_integration_enabled()
    targets = [project for project in _iter_projects(project_id, all_projects) if project is not None]
    if not targets:
        print("No projects available for agentic intelligence rollout.")
        return 0

    db = await connection.get_connection()
    await migrations.run_migrations(db)

    try:
        for project in targets:
            print(f"[{project.id}]")
            if not skip_sync:
                sync_payload = await sync_skillmeat_definitions(db, project)
                print(
                    "  sync:"
                    f" total_definitions={int(sync_payload.get('totalDefinitions') or 0)}"
                    f" warnings={len(sync_payload.get('warnings') or [])}"
                )

            if not skip_backfill:
                backfill_payload = await backfill_session_stack_observations(
                    db,
                    project,
                    limit=limit,
                    force_recompute=force_recompute,
                )
                print(
                    "  observations:"
                    f" processed={int(backfill_payload.get('sessionsProcessed') or 0)}"
                    f" stored={int(backfill_payload.get('observationsStored') or 0)}"
                    f" skipped={int(backfill_payload.get('skippedSessions') or 0)}"
                )

            if not skip_recompute:
                if workflow_analytics_enabled(project):
                    rollup_payload = await get_workflow_effectiveness(
                        db,
                        project,
                        period="all",
                        limit=500,
                        offset=0,
                        recompute=True,
                    )
                    failure_payload = await detect_failure_patterns(
                        db,
                        project,
                        limit=100,
                        offset=0,
                    )
                    print(
                        "  analytics:"
                        f" rollups={int(rollup_payload.get('total') or 0)}"
                        f" failure_patterns={int(failure_payload.get('total') or 0)}"
                    )
                else:
                    print("  analytics: skipped (workflow analytics disabled for this project)")
    finally:
        await connection.close_connection()

    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default="", help="Project ID to process (default: active project)")
    parser.add_argument("--all-projects", action="store_true", help="Process all configured projects")
    parser.add_argument("--skip-sync", action="store_true", help="Skip SkillMeat definition sync")
    parser.add_argument("--skip-backfill", action="store_true", help="Skip stack observation backfill")
    parser.add_argument("--skip-recompute", action="store_true", help="Skip workflow analytics recompute")
    parser.add_argument("--limit", type=int, default=5000, help="Max sessions to process during backfill")
    parser.add_argument("--force-recompute", action="store_true", help="Recompute stack observations even when cached rows exist")
    args = parser.parse_args()
    return asyncio.run(
        _run(
            args.project or None,
            all_projects=args.all_projects,
            skip_sync=args.skip_sync,
            skip_backfill=args.skip_backfill,
            skip_recompute=args.skip_recompute,
            limit=max(1, args.limit),
            force_recompute=args.force_recompute,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
