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

from backend.application.services.session_intelligence import (
    HistoricalSessionIntelligenceBackfillService,
    SESSION_INTELLIGENCE_BACKFILL_CHECKPOINT_KEY,
)
from backend.db import connection, migrations
from backend.db.factory import get_agentic_intelligence_repository
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


def _format_counts(counts_by_type: dict[str, Any]) -> str:
    ordered_keys = ("artifact", "workflow", "context_module", "bundle")
    parts = [f"{key}={int(counts_by_type.get(key) or 0)}" for key in ordered_keys]
    return " ".join(parts)


def _format_warning(warning: Any) -> str:
    if not isinstance(warning, dict):
        return str(warning)
    section = str(warning.get("section") or "general")
    message = str(warning.get("message") or "").strip()
    if not message:
        return section
    return f"[{section}] {message}"


def _definition_metadata(definition: dict[str, Any]) -> dict[str, Any]:
    metadata = definition.get("resolution_metadata")
    return metadata if isinstance(metadata, dict) else {}


async def _build_enrichment_summary(repo: Any, project_id: str) -> dict[str, int]:
    definitions = await repo.list_external_definitions(project_id, limit=1000)
    workflows = [item for item in definitions if str(item.get("definition_type") or "") == "workflow"]
    context_modules = [item for item in definitions if str(item.get("definition_type") or "") == "context_module"]

    return {
        "effectiveWorkflows": sum(1 for item in workflows if bool(_definition_metadata(item).get("isEffective"))),
        "plannedWorkflows": sum(1 for item in workflows if bool(_definition_metadata(item).get("planSummary"))),
        "executionEnrichedWorkflows": sum(
            1
            for item in workflows
            if int(_definition_metadata(item).get("executionSummary", {}).get("count") or 0) > 0
        ),
        "contextPreviewModules": sum(1 for item in context_modules if bool(_definition_metadata(item).get("previewSummary"))),
    }


async def _run(
    project_id: str | None,
    *,
    all_projects: bool,
    skip_sync: bool,
    skip_backfill: bool,
    session_intelligence_backfill: bool,
    session_intelligence_limit: int,
    session_intelligence_checkpoint_key: str,
    reset_session_intelligence_checkpoint: bool,
    skip_recompute: bool,
    limit: int,
    force_recompute: bool,
    fail_on_warning: bool,
) -> int:
    require_skillmeat_integration_enabled()
    targets = [project for project in _iter_projects(project_id, all_projects) if project is not None]
    if not targets:
        print("No projects available for agentic intelligence rollout.")
        return 0

    db = await connection.get_connection()
    await migrations.run_migrations(db)
    intelligence_repo = get_agentic_intelligence_repository(db)
    had_warnings = False

    try:
        for project in targets:
            print(f"[{project.id}]")
            if not skip_sync:
                sync_payload = await sync_skillmeat_definitions(db, project)
                counts_by_type = sync_payload.get("countsByType", {}) if isinstance(sync_payload.get("countsByType"), dict) else {}
                warnings = sync_payload.get("warnings", []) if isinstance(sync_payload.get("warnings"), list) else []
                print(
                    "  sync:"
                    f" total_definitions={int(sync_payload.get('totalDefinitions') or 0)}"
                    f" {_format_counts(counts_by_type)}"
                    f" warnings={len(warnings)}"
                )
                enrichment_summary = await _build_enrichment_summary(intelligence_repo, project.id)
                print(
                    "  enrichment:"
                    f" effective_workflows={enrichment_summary['effectiveWorkflows']}"
                    f" planned_workflows={enrichment_summary['plannedWorkflows']}"
                    f" execution_enriched_workflows={enrichment_summary['executionEnrichedWorkflows']}"
                    f" context_preview_modules={enrichment_summary['contextPreviewModules']}"
                )
                if warnings:
                    had_warnings = True
                    for warning in warnings:
                        print(f"  warning: {_format_warning(warning)}")

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

            if session_intelligence_backfill:
                payload = await HistoricalSessionIntelligenceBackfillService().backfill(
                    db,
                    project_id=project.id,
                    limit=session_intelligence_limit,
                    checkpoint_key=session_intelligence_checkpoint_key,
                    reset_checkpoint=reset_session_intelligence_checkpoint,
                )
                checkpoint = payload.get("checkpoint", {}) if isinstance(payload.get("checkpoint"), dict) else {}
                print(
                    "  session_intelligence:"
                    f" processed={int(payload.get('sessionsProcessed') or 0)}"
                    f" transcript_sessions={int(payload.get('transcriptSessionsBackfilled') or 0)}"
                    f" fact_sessions={int(payload.get('derivedFactSessionsBackfilled') or 0)}"
                    f" embedding_sessions={int(payload.get('embeddingSessionsBackfilled') or 0)}"
                    f" embedding_blocks={int(payload.get('embeddingBlocksBackfilled') or 0)}"
                    f" completed={bool(payload.get('completed'))}"
                )
                print(
                    "  session_intelligence_checkpoint:"
                    f" last_started_at={str(checkpoint.get('lastStartedAt') or '-')}"
                    f" last_session_id={str(checkpoint.get('lastSessionId') or '-')}"
                    f" total_processed={int(payload.get('sessionsProcessedTotal') or 0)}"
                )
                for line in payload.get("operatorGuidance", []):
                    print(f"  guidance: {line}")

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

    return 1 if fail_on_warning and had_warnings else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default="", help="Project ID to process (default: active project)")
    parser.add_argument("--all-projects", action="store_true", help="Process all configured projects")
    parser.add_argument("--skip-sync", action="store_true", help="Skip SkillMeat definition sync")
    parser.add_argument("--skip-backfill", action="store_true", help="Skip stack observation backfill")
    parser.add_argument(
        "--session-intelligence-backfill",
        action="store_true",
        help="Backfill canonical session transcripts, embedding blocks, and derived intelligence facts with checkpoints",
    )
    parser.add_argument(
        "--session-intelligence-limit",
        type=int,
        default=200,
        help="Max enterprise sessions to process in one session-intelligence backfill batch",
    )
    parser.add_argument(
        "--session-intelligence-checkpoint-key",
        default=SESSION_INTELLIGENCE_BACKFILL_CHECKPOINT_KEY,
        help="Checkpoint key stored in app_metadata for restart-safe session-intelligence backfill",
    )
    parser.add_argument(
        "--reset-session-intelligence-checkpoint",
        action="store_true",
        help="Delete the stored session-intelligence checkpoint before processing the next batch",
    )
    parser.add_argument("--skip-recompute", action="store_true", help="Skip workflow analytics recompute")
    parser.add_argument("--limit", type=int, default=5000, help="Max sessions to process during backfill")
    parser.add_argument("--force-recompute", action="store_true", help="Recompute stack observations even when cached rows exist")
    parser.add_argument("--fail-on-warning", action="store_true", help="Exit non-zero when sync emits recoverable warnings")
    args = parser.parse_args()
    return asyncio.run(
        _run(
            args.project or None,
            all_projects=args.all_projects,
            skip_sync=args.skip_sync,
            skip_backfill=args.skip_backfill,
            session_intelligence_backfill=args.session_intelligence_backfill,
            session_intelligence_limit=max(1, args.session_intelligence_limit),
            session_intelligence_checkpoint_key=str(args.session_intelligence_checkpoint_key or SESSION_INTELLIGENCE_BACKFILL_CHECKPOINT_KEY),
            reset_session_intelligence_checkpoint=args.reset_session_intelligence_checkpoint,
            skip_recompute=args.skip_recompute,
            limit=max(1, args.limit),
            force_recompute=args.force_recompute,
            fail_on_warning=args.fail_on_warning,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
