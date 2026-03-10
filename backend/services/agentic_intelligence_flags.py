"""Feature-flag helpers for the agentic SDLC intelligence surface."""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from backend import config


DEFAULT_PROJECT_FEATURE_FLAGS = {
    "stackRecommendationsEnabled": True,
    "workflowAnalyticsEnabled": True,
    "usageAttributionEnabled": True,
}


def _project_feature_flags(project: Any) -> dict[str, bool]:
    skillmeat = getattr(project, "skillMeat", None)
    raw_flags = getattr(skillmeat, "featureFlags", None)
    if hasattr(raw_flags, "model_dump"):
        raw_flags = raw_flags.model_dump()
    if hasattr(raw_flags, "dict"):
        raw_flags = raw_flags.dict()
    if not isinstance(raw_flags, dict):
        raw_flags = {}
    return {
        key: bool(raw_flags.get(key, default))
        for key, default in DEFAULT_PROJECT_FEATURE_FLAGS.items()
    }


def skillmeat_integration_enabled() -> bool:
    return bool(config.CCDASH_SKILLMEAT_INTEGRATION_ENABLED)


def stack_recommendations_enabled(project: Any | None) -> bool:
    if not config.CCDASH_AGENTIC_RECOMMENDATIONS_ENABLED:
        return False
    if project is None:
        return True
    return _project_feature_flags(project)["stackRecommendationsEnabled"]


def workflow_analytics_enabled(project: Any | None) -> bool:
    if not config.CCDASH_AGENTIC_WORKFLOW_ANALYTICS_ENABLED:
        return False
    if project is None:
        return True
    return _project_feature_flags(project)["workflowAnalyticsEnabled"]


def usage_attribution_enabled(project: Any | None) -> bool:
    if not config.CCDASH_SESSION_USAGE_ATTRIBUTION_ENABLED:
        return False
    if project is None:
        return True
    return _project_feature_flags(project)["usageAttributionEnabled"]


def require_skillmeat_integration_enabled() -> None:
    if skillmeat_integration_enabled():
        return
    raise HTTPException(
        status_code=503,
        detail={
            "error": "feature_disabled",
            "message": "SkillMeat integration is not enabled.",
            "hint": "Set CCDASH_SKILLMEAT_INTEGRATION_ENABLED=true in environment.",
        },
    )


def require_workflow_analytics_enabled(project: Any | None) -> None:
    if workflow_analytics_enabled(project):
        return

    if not config.CCDASH_AGENTIC_WORKFLOW_ANALYTICS_ENABLED:
        hint = "Set CCDASH_AGENTIC_WORKFLOW_ANALYTICS_ENABLED=true in environment."
    else:
        hint = "Enable Workflow Effectiveness in Project Settings > SkillMeat Integration."

    raise HTTPException(
        status_code=503,
        detail={
            "error": "feature_disabled",
            "message": "Workflow effectiveness analytics are disabled for this project.",
            "hint": hint,
        },
    )


def require_usage_attribution_enabled(project: Any | None) -> None:
    if usage_attribution_enabled(project):
        return

    if not config.CCDASH_SESSION_USAGE_ATTRIBUTION_ENABLED:
        hint = "Set CCDASH_SESSION_USAGE_ATTRIBUTION_ENABLED=true in environment."
    else:
        hint = "Enable Usage Attribution in Project Settings > SkillMeat Integration."

    raise HTTPException(
        status_code=503,
        detail={
            "error": "feature_disabled",
            "message": "Session usage attribution is disabled for this project.",
            "hint": hint,
        },
    )
