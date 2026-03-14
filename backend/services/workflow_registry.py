"""Workflow registry aggregation over cached SkillMeat definitions and CCDash observations."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from backend.db.factory import get_agentic_intelligence_repository
from backend.services.integrations.skillmeat_routes import normalize_definitions_for_project
from backend.services.stack_observations import canonicalize_stack_observation


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _normalize_token(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _command_token(command: str) -> str:
    normalized = _normalize_token(command)
    if not normalized:
        return ""
    return normalized.split()[0]


def _humanize_workflow_label(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "Unresolved workflow"
    if raw.startswith("/"):
        return raw
    return raw.replace("-", " ").replace("_", " ").strip().title() or raw


def _definition_metadata(definition: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(definition, dict):
        return {}
    metadata = definition.get("resolution_metadata")
    if isinstance(metadata, dict):
        return metadata
    metadata = definition.get("resolution_metadata_json")
    return metadata if isinstance(metadata, dict) else {}


def _definition_aliases(definition: dict[str, Any]) -> list[str]:
    metadata = _definition_metadata(definition)
    aliases = [
        str(definition.get("external_id") or ""),
        str(definition.get("display_name") or ""),
        str(metadata.get("effectiveWorkflowId") or ""),
        str(metadata.get("effectiveWorkflowName") or ""),
    ]
    aliases.extend(str(alias) for alias in _safe_list(metadata.get("aliases")))
    return [alias.strip() for alias in aliases if str(alias).strip()]


def _is_command_artifact(definition: dict[str, Any]) -> bool:
    if str(definition.get("definition_type") or "") != "artifact":
        return False
    metadata = _definition_metadata(definition)
    artifact_type = str(metadata.get("artifactType") or "").strip().lower()
    external_id = str(definition.get("external_id") or "").strip().lower()
    return artifact_type == "command" or external_id.startswith("command:")


def _registry_id(
    *,
    workflow_definition: dict[str, Any] | None = None,
    command_definition: dict[str, Any] | None = None,
    observed_ref: str = "",
) -> str:
    if isinstance(workflow_definition, dict):
        return f"workflow:{workflow_definition.get('external_id') or ''}"
    if isinstance(command_definition, dict):
        return f"command:{command_definition.get('external_id') or ''}"
    return f"observed:{observed_ref or 'unresolved'}"


def _empty_entity(registry_id: str) -> dict[str, Any]:
    return {
        "id": registry_id,
        "workflowDefinition": None,
        "commandArtifactDefinition": None,
        "observedRefs": [],
        "commands": [],
        "observations": [],
        "issues": [],
    }


async def list_workflow_registry(
    db: Any,
    project: Any,
    *,
    search: str | None = None,
    correlation_state: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    project_id = str(getattr(project, "id", "") or "")
    intelligence_repo = get_agentic_intelligence_repository(db)
    definitions = normalize_definitions_for_project(
        await intelligence_repo.list_external_definitions(project_id, limit=5000, offset=0),
        project,
    )
    observations = await intelligence_repo.list_stack_observations(project_id, limit=5000, offset=0)
    hydrated_observations: list[dict[str, Any]] = []
    for observation in observations:
        hydrated = canonicalize_stack_observation(dict(observation))
        observation_id = _safe_int(hydrated.get("id"), 0)
        hydrated["components"] = await intelligence_repo.list_stack_components(observation_id) if observation_id else []
        hydrated_observations.append(hydrated)

    # Phase 1 foundation: return an empty registry payload until aggregation logic is added.
    # Call sites can integrate against the contract immediately without overloading workflowRef.
    return {
        "projectId": project_id,
        "items": [],
        "total": 0,
        "offset": offset,
        "limit": limit,
        "generatedAt": _now_iso(),
    }


async def get_workflow_registry_detail(
    db: Any,
    project: Any,
    *,
    registry_id: str,
) -> dict[str, Any] | None:
    payload = await list_workflow_registry(db, project, limit=5000, offset=0)
    for item in payload.get("items", []):
        if str(item.get("id") or "") == registry_id:
            return item
    return None
