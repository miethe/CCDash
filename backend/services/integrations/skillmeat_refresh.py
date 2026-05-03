"""Helpers for refreshing SkillMeat-backed caches after config changes."""
from __future__ import annotations

from typing import Any

from backend.db.factory import get_agentic_intelligence_repository
from backend.services.integrations.skillmeat_sync import sync_skillmeat_definitions
from backend.services.stack_observations import backfill_session_stack_observations


DEFAULT_OBSERVATION_BACKFILL_LIMIT = 200


def skillmeat_refresh_configured(project: Any | None) -> bool:
    if project is None:
        return False
    config = getattr(project, "skillMeat", None)
    if config is None:
        return False
    if not bool(getattr(config, "enabled", False)):
        return False
    return bool(str(getattr(config, "baseUrl", "") or "").strip())


async def refresh_skillmeat_cache(
    db: Any,
    project: Any,
    *,
    context: Any | None = None,
    observation_limit: int = DEFAULT_OBSERVATION_BACKFILL_LIMIT,
    force_observation_recompute: bool = False,
) -> dict[str, Any]:
    """Refresh definition cache first, then rebuild stack observations from current definitions."""
    sync_payload = await sync_skillmeat_definitions(db, project, context=context)
    project_id = str(getattr(project, "id", "") or "")
    repo = get_agentic_intelligence_repository(db)
    cached_definitions = await repo.list_external_definitions(project_id, limit=1, offset=0)

    should_backfill = bool(cached_definitions) or skillmeat_refresh_configured(project)
    if not should_backfill:
        return {
            "sync": sync_payload,
            "backfill": None,
        }

    backfill_payload = await backfill_session_stack_observations(
        db,
        project,
        limit=observation_limit,
        force_recompute=force_observation_recompute,
    )
    return {
        "sync": sync_payload,
        "backfill": backfill_payload,
    }
