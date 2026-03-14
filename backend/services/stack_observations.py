"""Observed stack extraction and project backfill helpers."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from backend.db.factory import get_agentic_intelligence_repository, get_session_repository
from backend.services.integrations.skillmeat_resolver import resolve_stack_components
from backend.session_badges import derive_session_badges
from backend.session_mappings import classify_session_key_metadata, default_session_mappings, workflow_command_exemptions

_GENERATED_AGENT_ID_RE = re.compile(r"^(?:[a-f0-9]{12,}|a[a-f0-9]{8,})$", re.IGNORECASE)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_json(raw: object) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _normalize_command(command: str) -> str:
    return " ".join((command or "").strip().split())


def _command_token(command: str) -> str:
    normalized = _normalize_command(command)
    if not normalized:
        return ""
    return normalized.split()[0]


def _looks_like_generated_agent_id(value: str) -> bool:
    return bool(_GENERATED_AGENT_ID_RE.fullmatch(str(value or "").strip()))


def _preferred_agent_names(agents: list[str]) -> list[str]:
    normalized = [str(agent or "").strip() for agent in agents if str(agent or "").strip()]
    friendly = [agent for agent in normalized if not _looks_like_generated_agent_id(agent)]
    if not friendly:
        return normalized
    friendly_keys = {agent.lower() for agent in friendly}
    return [agent for agent in normalized if agent.lower() in friendly_keys]


def _canonical_workflow_ref(session_metadata: dict[str, Any] | None, commands: list[str]) -> str:
    metadata = session_metadata if isinstance(session_metadata, dict) else {}
    related_command = _command_token(str(metadata.get("relatedCommand") or ""))
    if related_command:
        return related_command
    for command in commands:
        token = _command_token(command)
        if token.startswith("/"):
            return token
    return ""


def canonicalize_stack_observation(observation: dict[str, Any]) -> dict[str, Any]:
    updated = dict(observation)
    evidence = _safe_json(updated.get("evidence_json") or updated.get("evidence"))
    commands = [str(command).strip() for command in evidence.get("commands", []) if str(command).strip()]
    workflow_metadata = _safe_json(evidence.get("workflowMetadata"))
    workflow_ref = _canonical_workflow_ref(workflow_metadata, commands)
    if not workflow_ref:
        workflow_ref = _command_token(str(updated.get("workflow_ref") or updated.get("workflowRef") or ""))

    components_raw = updated.get("components")
    components = [dict(component) for component in components_raw] if isinstance(components_raw, list) else []
    preferred_agents = {
        str(component.get("component_key") or "").strip().lower()
        for component in components
        if str(component.get("component_type") or "").strip() == "agent"
        and str(component.get("component_key") or "").strip()
        and not _looks_like_generated_agent_id(str(component.get("component_key") or ""))
    }

    normalized_components: list[dict[str, Any]] = []
    for component in components:
        updated_component = dict(component)
        component_type = str(updated_component.get("component_type") or "").strip()
        component_key = str(updated_component.get("component_key") or "").strip()
        if component_type == "agent" and preferred_agents and _looks_like_generated_agent_id(component_key):
            continue
        if component_type == "workflow":
            payload = _safe_json(updated_component.get("payload") or updated_component.get("component_payload_json"))
            component_workflow_ref = _canonical_workflow_ref(payload, commands) or workflow_ref or component_key
            updated_component["component_key"] = component_workflow_ref
            payload["workflowRef"] = component_workflow_ref
            if workflow_metadata.get("mappingId"):
                payload["mappingId"] = str(workflow_metadata.get("mappingId") or "")
            if workflow_metadata.get("sessionTypeLabel"):
                payload["sessionTypeLabel"] = str(workflow_metadata.get("sessionTypeLabel") or "")
            updated_component["payload"] = payload
            updated_component["component_payload_json"] = payload
        normalized_components.append(updated_component)

    if workflow_ref:
        updated["workflow_ref"] = workflow_ref
    if normalized_components:
        updated["components"] = _dedupe_components(normalized_components)
    return updated


def build_session_stack_observation(
    *,
    project_id: str,
    session_row: dict[str, Any],
    logs: list[dict[str, Any]],
    artifacts: list[dict[str, Any]],
    file_updates: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    badge_data = derive_session_badges(
        logs,
        primary_model=str(session_row.get("model") or ""),
        session_agent_id=session_row.get("agent_id"),
    )

    command_events: list[dict[str, Any]] = []
    commands: list[str] = []
    for log in logs:
        if str(log.get("type") or "") != "command":
            continue
        metadata = _safe_json(log.get("metadata_json"))
        command = _normalize_command(str(log.get("content") or ""))
        if command:
            commands.append(command)
        command_events.append(
            {
                "name": command,
                "args": str(metadata.get("args") or ""),
                "parsedCommand": metadata.get("parsedCommand") if isinstance(metadata.get("parsedCommand"), dict) else {},
            }
        )
    commands = _dedupe_commands(commands)

    session_metadata = classify_session_key_metadata(
        command_events,
        default_session_mappings(),
        platform_type=str(session_row.get("platform_type") or ""),
    )
    workflow_ref = _canonical_workflow_ref(session_metadata, commands)

    session_forensics = _safe_json(session_row.get("session_forensics_json"))
    thinking = _safe_json(session_forensics.get("thinking"))
    models_used = [
        str(item.get("raw") or "")
        for item in badge_data.get("modelsUsed", [])
        if isinstance(item, dict) and str(item.get("raw") or "").strip()
    ]

    components: list[dict[str, Any]] = []

    for agent in _preferred_agent_names(list(badge_data.get("agentsUsed", []))):
        components.append(
            {
                "project_id": project_id,
                "component_type": "agent",
                "component_key": str(agent),
                "status": "explicit",
                "confidence": 0.95,
                "payload": {"name": str(agent), "source": "session_badges"},
            }
        )

    for skill in badge_data.get("skillsUsed", []):
        components.append(
            {
                "project_id": project_id,
                "component_type": "skill",
                "component_key": str(skill),
                "status": "explicit",
                "confidence": 0.9,
                "payload": {"skill": str(skill), "source": "session_badges"},
            }
        )

    for artifact in artifacts:
        external_id = _artifact_external_id(artifact)
        component_type = _artifact_component_type(artifact, external_id)
        if not external_id:
            continue
        components.append(
            {
                "project_id": project_id,
                "component_type": component_type,
                "component_key": external_id,
                "status": "explicit",
                "confidence": 0.85,
                "payload": {
                    "externalId": external_id,
                    "title": str(artifact.get("title") or ""),
                    "source": str(artifact.get("source") or ""),
                    "url": str(artifact.get("url") or ""),
                },
            }
        )

    for command in commands:
        components.append(
            {
                "project_id": project_id,
                "component_type": "command",
                "component_key": command,
                "status": "explicit",
                "confidence": 0.75,
                "payload": {"command": command},
            }
        )

    if workflow_ref:
        components.append(
            {
                "project_id": project_id,
                "component_type": "workflow",
                "component_key": workflow_ref,
                "status": "inferred",
                "confidence": 0.7,
                "payload": {
                    "workflowRef": workflow_ref,
                    "relatedCommand": str(session_metadata.get("relatedCommand") or "") if session_metadata else "",
                    "mappingId": str(session_metadata.get("mappingId") or "") if session_metadata else "",
                    "sessionTypeLabel": str(session_metadata.get("sessionTypeLabel") or "") if session_metadata else "",
                },
            }
        )

    if thinking or models_used:
        components.append(
            {
                "project_id": project_id,
                "component_type": "model_policy",
                "component_key": str(thinking.get("level") or session_row.get("thinking_level") or "model-policy"),
                "status": "inferred",
                "confidence": 0.65,
                "payload": {
                    "thinkingLevel": str(thinking.get("level") or session_row.get("thinking_level") or ""),
                    "models": models_used,
                },
            }
        )

    confidence = _overall_confidence(components, workflow_ref=workflow_ref)
    evidence = {
        "commands": commands[:20],
        "artifactCount": len(artifacts),
        "fileUpdateCount": len(file_updates),
        "agentsUsed": list(badge_data.get("agentsUsed", [])),
        "skillsUsed": list(badge_data.get("skillsUsed", [])),
        "workflowMetadata": session_metadata or {},
        "queuePressure": _safe_json(session_forensics.get("queuePressure")),
        "subagentTopology": _safe_json(session_forensics.get("subagentTopology")),
        "testExecution": _safe_json(session_forensics.get("testExecution")),
    }

    observation = {
        "project_id": project_id,
        "session_id": str(session_row.get("id") or ""),
        "feature_id": str(session_row.get("task_id") or ""),
        "workflow_ref": workflow_ref,
        "confidence": confidence,
        "source": "backfill",
        "evidence": evidence,
    }
    normalized_components = _dedupe_components(components)
    normalized_observation = canonicalize_stack_observation({**observation, "components": normalized_components})
    return (
        {
            **observation,
            "workflow_ref": str(normalized_observation.get("workflow_ref") or workflow_ref),
        },
        _dedupe_components(list(normalized_observation.get("components") or normalized_components)),
    )


async def backfill_session_stack_observations(
    db: Any,
    project: Any,
    *,
    limit: int = 200,
    force_recompute: bool = False,
) -> dict[str, Any]:
    intelligence_repo = get_agentic_intelligence_repository(db)
    session_repo = get_session_repository(db)
    project_id = str(getattr(project, "id", "") or "")
    warnings: list[dict[str, Any]] = []
    sessions_processed = 0
    observations_stored = 0
    skipped_sessions = 0
    resolved_components = 0
    unresolved_components = 0

    definitions = await intelligence_repo.list_external_definitions(project_id, limit=5000, offset=0)
    session_rows = await session_repo.list_paginated(
        0,
        limit,
        project_id,
        "started_at",
        "desc",
        {"include_subagents": True},
    )

    for session_row in session_rows:
        session_id = str(session_row.get("id") or "")
        try:
            existing = await intelligence_repo.get_stack_observation(project_id, session_id)
            if existing and not force_recompute:
                skipped_sessions += 1
                continue

            logs = await session_repo.get_logs(session_id)
            artifacts = await session_repo.get_artifacts(session_id)
            file_updates = await session_repo.get_file_updates(session_id)
            observation, components = build_session_stack_observation(
                project_id=project_id,
                session_row=session_row,
                logs=logs,
                artifacts=artifacts,
                file_updates=file_updates,
            )
            resolved = resolve_stack_components(components=components, definitions=definitions)
            stored = await intelligence_repo.upsert_stack_observation(
                canonicalize_stack_observation({**observation, "components": resolved}),
                resolved,
                project_id,
            )
            sessions_processed += 1
            observations_stored += 1
            for component in stored.get("components", []):
                if str(component.get("status") or "") == "resolved":
                    resolved_components += 1
                elif str(component.get("status") or "") == "unresolved":
                    unresolved_components += 1
        except Exception as exc:
            warnings.append(
                {
                    "section": session_id,
                    "message": f"Failed to backfill session '{session_id}': {exc}",
                    "recoverable": True,
                }
            )

    return {
        "projectId": project_id,
        "sessionsProcessed": sessions_processed,
        "observationsStored": observations_stored,
        "skippedSessions": skipped_sessions,
        "resolvedComponents": resolved_components,
        "unresolvedComponents": unresolved_components,
        "generatedAt": _now_iso(),
        "warnings": warnings,
    }


def _artifact_external_id(artifact: dict[str, Any]) -> str:
    candidates = [
        artifact.get("id"),
        artifact.get("title"),
        artifact.get("url"),
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            value = candidate.strip()
            if value.startswith("ctx:") or ":" in value:
                return value
    return ""


def _artifact_component_type(artifact: dict[str, Any], external_id: str) -> str:
    if external_id.startswith("ctx:"):
        return "context_module"
    artifact_type = str(artifact.get("type") or "").strip().lower()
    if "workflow" in artifact_type:
        return "workflow"
    return "artifact"


def _overall_confidence(components: list[dict[str, Any]], *, workflow_ref: str) -> float:
    score = 0.35
    if workflow_ref:
        score += 0.2
    explicit_count = sum(1 for item in components if str(item.get("status") or "") == "explicit")
    inferred_count = sum(1 for item in components if str(item.get("status") or "") == "inferred")
    score += min(0.3, explicit_count * 0.05)
    score += min(0.1, inferred_count * 0.03)
    return min(0.95, round(score, 2))


def _dedupe_commands(commands: list[str]) -> list[str]:
    exclusions = workflow_command_exemptions()
    seen: set[str] = set()
    deduped: list[str] = []
    for command in commands:
        normalized = _normalize_command(command)
        if not normalized:
            continue
        token = normalized.split()[0].lower()
        if token in exclusions:
            continue
        lowered = normalized.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(normalized)
    return deduped


def _dedupe_components(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for component in components:
        component_type = str(component.get("component_type") or "")
        component_key = str(component.get("component_key") or "")
        key = (component_type, component_key.lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(component)
    return deduped
