"""Recommended stack ranking for the feature execution workbench."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.db.factory import get_agentic_intelligence_repository, get_session_repository
from backend.models import (
    ExecutionArtifactReference,
    ExecutionRecommendation,
    Feature,
    FeatureExecutionWarning,
    RecommendedStack,
    RecommendedStackComponent,
    RecommendedStackDefinitionRef,
    SimilarWorkExample,
    StackRecommendationEvidence,
)
from backend.services.integrations.skillmeat_routes import normalize_definitions_for_project
from backend.services.integrations.skillmeat_resolver import build_definition_indexes, resolve_component_definition
from backend.services.stack_observations import canonicalize_stack_observation
from backend.services.workflow_effectiveness import get_workflow_effectiveness

_MAX_STACK_ITEMS = 250
_MAX_OBSERVATIONS = 400
_MAX_ALTERNATIVES = 2
_MAX_SIMILAR_WORK = 3
_RESOLVABLE_COMPONENT_TYPES = {"workflow", "skill", "context_module", "artifact", "agent", "command"}

_RULE_WORKFLOW_HINTS = {
    "R1_PLAN_FROM_PRD_OR_REPORT": "planning",
    "R2_START_PHASE_1": "phase-execution",
    "R3_ADVANCE_TO_NEXT_PHASE": "phase-execution",
    "R4_RESUME_ACTIVE_PHASE": "phase-execution",
    "R5_COMPLETE_STORY": "story-execution",
    "R6_FALLBACK_QUICK_FEATURE": "quick-execution",
}

_COMMAND_WORKFLOW_HINTS = {
    "/plan:plan-feature": "planning",
    "/dev:execute-phase": "phase-execution",
    "/dev:complete-user-story": "story-execution",
    "/dev:quick-feature": "quick-execution",
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _normalize_token(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _command_token(command: str) -> str:
    normalized = _normalize_token(command)
    if not normalized:
        return ""
    return normalized.split()[0]


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    items: list[str] = []
    for value in values:
        normalized = _normalize_token(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        items.append(value)
    return items


def _overlap_ratio(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    overlap = len(left & right)
    baseline = max(len(left), len(right), 1)
    return overlap / baseline


def _parse_stack_scope_id(scope_id: str) -> dict[str, Any]:
    parts = [part.strip() for part in (scope_id or "").split("|") if part.strip()]
    workflow_ref = parts[0] if parts else ""
    agents: list[str] = []
    skills: list[str] = []
    contexts: list[str] = []
    for part in parts[1:]:
        if ":" not in part:
            continue
        key, raw_values = part.split(":", 1)
        values = [value for value in raw_values.split(",") if value and value != "none"]
        if key == "agents":
            agents = values
        elif key == "skills":
            skills = values
        elif key == "contexts":
            contexts = values
    return {
        "workflowRef": workflow_ref,
        "agents": agents,
        "skills": skills,
        "contexts": contexts,
    }


def _stack_scope_id(observation: dict[str, Any]) -> str:
    workflow_ref = str(observation.get("workflow_ref") or observation.get("workflowRef") or "unassigned").strip() or "unassigned"
    components = _safe_list(observation.get("components"))
    agents = sorted({
        str(component.get("component_key") or component.get("componentKey") or "").strip()
        for component in components
        if str(component.get("component_type") or component.get("componentType") or "") == "agent"
        and str(component.get("component_key") or component.get("componentKey") or "").strip()
    })
    skills = sorted({
        str(component.get("component_key") or component.get("componentKey") or "").strip()
        for component in components
        if str(component.get("component_type") or component.get("componentType") or "") == "skill"
        and str(component.get("component_key") or component.get("componentKey") or "").strip()
    })
    contexts = sorted({
        str(component.get("component_key") or component.get("componentKey") or "").strip()
        for component in components
        if (
            str(component.get("component_type") or component.get("componentType") or "") == "context_module"
            or str(component.get("external_definition_type") or component.get("externalDefinitionType") or "") == "context_module"
        )
        and str(component.get("component_key") or component.get("componentKey") or "").strip()
    })
    return "|".join(
        [
            workflow_ref,
            f"agents:{','.join(agents[:3]) or 'none'}",
            f"skills:{','.join(skills[:3]) or 'none'}",
            f"contexts:{','.join(contexts[:3]) or 'none'}",
        ]
    )


def _component_label(component: dict[str, Any], definition: dict[str, Any] | None) -> str:
    if definition and str(definition.get("display_name") or "").strip():
        return str(definition.get("display_name") or "")
    payload = _safe_dict(component.get("payload") or component.get("component_payload_json"))
    for key in ("displayName", "name", "title", "workflowRef", "skill", "command", "externalId"):
        if str(payload.get(key) or "").strip():
            return str(payload.get(key) or "")
    return str(component.get("component_key") or component.get("componentKey") or "")


def _stack_label(workflow_ref: str, components: list[RecommendedStackComponent]) -> str:
    readable_workflow = workflow_ref if workflow_ref.startswith("/") else workflow_ref.replace("-", " ").strip().title() or "Local stack"
    agents = [component.label for component in components if component.componentType == "agent"][:2]
    skills = [component.label for component in components if component.componentType == "skill"][:2]
    suffix_parts: list[str] = []
    if agents:
        suffix_parts.append(", ".join(agents))
    if skills:
        suffix_parts.append(", ".join(skills))
    if not suffix_parts:
        return readable_workflow
    return f"{readable_workflow} ({' + '.join(suffix_parts)})"


def _is_placeholder_workflow_ref(workflow_ref: str) -> bool:
    normalized = str(workflow_ref or "").strip().lower()
    return not normalized or normalized == "unassigned" or normalized.startswith("key-")


def _definition_map(definitions: list[dict[str, Any]]) -> tuple[dict[int, dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
    by_id: dict[int, dict[str, Any]] = {}
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for definition in definitions:
        definition_id = _safe_int(definition.get("id"), 0)
        if definition_id:
            by_id[definition_id] = definition
        definition_type = str(definition.get("definition_type") or "").strip()
        external_id = str(definition.get("external_id") or "").strip()
        if definition_type and external_id:
            by_key[(definition_type, external_id)] = definition
    return by_id, by_key


def _definition_for_component(
    component: dict[str, Any],
    definition_by_id: dict[int, dict[str, Any]],
    definition_by_key: dict[tuple[str, str], dict[str, Any]],
) -> tuple[dict[str, Any] | None, str]:
    definition_id = _safe_int(component.get("external_definition_id") or component.get("externalDefinitionId"), 0)
    if definition_id and definition_id in definition_by_id:
        return definition_by_id[definition_id], "resolved"
    definition_type = str(component.get("external_definition_type") or component.get("externalDefinitionType") or "").strip()
    external_id = str(component.get("external_definition_external_id") or component.get("externalDefinitionExternalId") or "").strip()
    if definition_type and external_id:
        return definition_by_key.get((definition_type, external_id)), "cached"
    return None, "unresolved"


def _build_stack_components(
    observation: dict[str, Any],
    definition_by_id: dict[int, dict[str, Any]],
    definition_by_key: dict[tuple[str, str], dict[str, Any]],
    definition_indexes: tuple[
        dict[tuple[str, str], dict[str, Any]],
        dict[tuple[str, str], dict[str, Any]],
        dict[tuple[str, str], dict[str, Any]],
    ],
) -> list[RecommendedStackComponent]:
    items: list[RecommendedStackComponent] = []
    for component in _safe_list(observation.get("components")):
        definition_row, fallback_status = _definition_for_component(component, definition_by_id, definition_by_key)
        matched_via = str(component.get("source_attribution") or component.get("sourceAttribution") or "")
        if definition_row is None:
            definition_row, matched_via, fallback_status = resolve_component_definition(component, definition_indexes)
        definition_ref = None
        if definition_row:
            definition_ref = RecommendedStackDefinitionRef(
                definitionType=str(definition_row.get("definition_type") or ""),
                externalId=str(definition_row.get("external_id") or ""),
                displayName=str(definition_row.get("display_name") or ""),
                version=str(definition_row.get("version") or ""),
                sourceUrl=str(definition_row.get("source_url") or ""),
                status="resolved" if str(component.get("status") or "") == "resolved" else fallback_status,
            )
        label = _component_label(component, definition_row)
        payload = _safe_dict(component.get("payload") or component.get("component_payload_json"))
        component_status = str(component.get("status") or fallback_status)
        if definition_ref and definition_ref.status in {"resolved", "cached"}:
            component_status = str(definition_ref.status)
        items.append(
            RecommendedStackComponent(
                componentType=str(component.get("component_type") or component.get("componentType") or "artifact"),
                componentKey=str(component.get("component_key") or component.get("componentKey") or ""),
                label=label,
                status=component_status,
                confidence=round(_safe_float(component.get("confidence"), 0.0), 4),
                sourceAttribution=str(component.get("source_attribution") or component.get("sourceAttribution") or ""),
                payload=payload,
                definition=definition_ref,
                artifactRef=ExecutionArtifactReference(
                    key=str((definition_row or {}).get("external_id") or component.get("component_key") or component.get("componentKey") or ""),
                    label=label or str(component.get("component_key") or component.get("componentKey") or ""),
                    kind=str(component.get("component_type") or component.get("componentType") or "artifact"),
                    status=str(definition_ref.status if definition_ref else fallback_status),
                    definitionType=str((definition_row or {}).get("definition_type") or ""),
                    externalId=str((definition_row or {}).get("external_id") or ""),
                    sourceUrl=str((definition_row or {}).get("source_url") or ""),
                    sourceAttribution=matched_via or str(component.get("source_attribution") or component.get("sourceAttribution") or ""),
                    description=str(payload.get("title") or payload.get("name") or payload.get("workflowRef") or payload.get("command") or ""),
                    metadata=payload,
                ),
            )
        )
    items.sort(key=lambda component: (component.componentType, component.label.lower(), component.componentKey.lower()))
    return items


def _workflow_candidates(
    recommendation: ExecutionRecommendation,
    sessions: list[Any],
) -> list[str]:
    items: list[str] = []
    primary_command = _command_token(recommendation.primary.command)
    if primary_command:
        items.append(primary_command)
    rule_hint = _RULE_WORKFLOW_HINTS.get(str(recommendation.ruleId or ""))
    if rule_hint:
        items.append(rule_hint)

    command_hint = _COMMAND_WORKFLOW_HINTS.get(primary_command)
    if command_hint:
        items.append(command_hint)

    workflow_counts: dict[str, int] = {}
    for session in sessions:
        workflow_type = str(getattr(session, "workflowType", "") or _safe_dict(session).get("workflowType") or "").strip()
        if workflow_type:
            workflow_counts[workflow_type] = workflow_counts.get(workflow_type, 0) + 1
    items.extend(
        workflow
        for workflow, _ in sorted(workflow_counts.items(), key=lambda item: (-item[1], item[0]))
    )
    return _dedupe_strings(items)


def _current_context(
    feature: Feature,
    sessions: list[Any],
    recommendation: ExecutionRecommendation,
) -> dict[str, Any]:
    agent_counts: dict[str, int] = {}
    skill_counts: dict[str, int] = {}
    current_session_ids: set[str] = set()

    for raw_session in sessions:
        session = raw_session if isinstance(raw_session, dict) else raw_session.model_dump() if hasattr(raw_session, "model_dump") else {}
        session_id = str(session.get("sessionId") or session.get("id") or "")
        if session_id:
            current_session_ids.add(session_id)
        for agent in _safe_list(session.get("agentsUsed")):
            token = str(agent).strip()
            if token:
                agent_counts[token] = agent_counts.get(token, 0) + 1
        for skill in _safe_list(session.get("skillsUsed")):
            token = str(skill).strip()
            if token:
                skill_counts[token] = skill_counts.get(token, 0) + 1

    top_agents = [
        key
        for key, _ in sorted(agent_counts.items(), key=lambda item: (-item[1], item[0]))
    ][:5]
    top_skills = [
        key
        for key, _ in sorted(skill_counts.items(), key=lambda item: (-item[1], item[0]))
    ][:5]

    return {
        "featureId": feature.id,
        "workflowCandidates": _workflow_candidates(recommendation, sessions),
        "agents": set(top_agents),
        "skills": set(top_skills),
        "contexts": set(),
        "sessionIds": current_session_ids,
    }


def _parse_iso(value: str | None) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _definition_metadata_row(definition: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(definition, dict):
        return {}
    metadata = definition.get("resolution_metadata")
    if isinstance(metadata, dict):
        return metadata
    metadata = definition.get("resolution_metadata_json")
    return metadata if isinstance(metadata, dict) else {}


def _normalize_ref_token(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _tokenize_text(value: str) -> set[str]:
    token = "".join(ch.lower() if ch.isalnum() else " " for ch in str(value or ""))
    return {part for part in token.split() if len(part) >= 3}


def _feature_tokens(feature: Feature) -> set[str]:
    return _tokenize_text(feature.id) | _tokenize_text(feature.name)


def _workflow_definition_for_observation(
    observation: dict[str, Any] | None,
    definition_by_id: dict[int, dict[str, Any]],
    definition_by_key: dict[tuple[str, str], dict[str, Any]],
    definition_indexes: tuple[
        dict[tuple[str, str], dict[str, Any]],
        dict[tuple[str, str], dict[str, Any]],
        dict[tuple[str, str], dict[str, Any]],
    ],
) -> dict[str, Any] | None:
    if not isinstance(observation, dict):
        return None
    for component in _safe_list(observation.get("components")):
        component_type = str(component.get("component_type") or component.get("componentType") or "")
        if component_type != "workflow":
            continue
        definition_row, _ = _definition_for_component(component, definition_by_id, definition_by_key)
        if definition_row:
            return definition_row
        definition_row, _, _ = resolve_component_definition(component, definition_indexes)
        if definition_row:
            return definition_row
    return None


def _workflow_ref_from_component(component: RecommendedStackComponent) -> str:
    payload = component.payload if isinstance(component.payload, dict) else {}
    candidates = [
        str(payload.get("relatedCommand") or ""),
        str(payload.get("command") or ""),
        str(payload.get("workflowRef") or ""),
        str(component.componentKey or ""),
        str((component.artifactRef.externalId if component.artifactRef else "") or ""),
        str(component.label or ""),
    ]
    for candidate in candidates:
        token = _command_token(candidate)
        if token and not _is_placeholder_workflow_ref(token):
            return token
        raw = str(candidate or "").strip()
        if raw and not _is_placeholder_workflow_ref(raw):
            return raw
    return ""


def _preferred_stack_workflow_ref(
    workflow_ref: str,
    observation: dict[str, Any] | None,
    components: list[RecommendedStackComponent],
) -> str:
    if not _is_placeholder_workflow_ref(workflow_ref):
        return workflow_ref

    if isinstance(observation, dict):
        observed_workflow_ref = _command_token(str(observation.get("workflow_ref") or observation.get("workflowRef") or ""))
        if observed_workflow_ref and not _is_placeholder_workflow_ref(observed_workflow_ref):
            return observed_workflow_ref

    workflow_component = next((component for component in components if component.componentType == "workflow"), None)
    if workflow_component is not None:
        component_workflow_ref = _workflow_ref_from_component(workflow_component)
        if component_workflow_ref and not _is_placeholder_workflow_ref(component_workflow_ref):
            return component_workflow_ref

    return workflow_ref


def _stack_items_need_refresh(stack_items: list[dict[str, Any]]) -> bool:
    for item in stack_items:
        scope_id = str(item.get("scopeId") or "").strip()
        parsed_scope = _parse_stack_scope_id(scope_id)
        workflow_ref = str(parsed_scope.get("workflowRef") or scope_id or "").strip()
        if _is_placeholder_workflow_ref(workflow_ref):
            return True
    return False


def _artifact_refs_from_definition(definition: dict[str, Any] | None) -> set[str]:
    if not isinstance(definition, dict):
        return set()
    metadata = _definition_metadata_row(definition)
    refs: set[str] = set()
    artifact_type = str(metadata.get("artifactType") or "").strip()
    artifact_name = str(metadata.get("artifactName") or "").strip()
    if artifact_type and artifact_name:
        refs.add(_normalize_ref_token(f"{artifact_type}:{artifact_name}"))
    external_id = str(definition.get("external_id") or "").strip()
    if ":" in external_id:
        refs.add(_normalize_ref_token(external_id))
    for alias in _safe_list(metadata.get("aliases")):
        token = str(alias).strip()
        if ":" in token and not token.startswith("ctx:"):
            refs.add(_normalize_ref_token(token))
    return {ref for ref in refs if ref}


def _stack_artifact_refs(
    observation: dict[str, Any] | None,
    workflow_definition: dict[str, Any] | None,
    definition_by_id: dict[int, dict[str, Any]],
    definition_by_key: dict[tuple[str, str], dict[str, Any]],
) -> set[str]:
    refs: set[str] = set()
    if isinstance(observation, dict):
        for component in _safe_list(observation.get("components")):
            component_type = str(component.get("component_type") or component.get("componentType") or "")
            if component_type not in {"artifact", "skill"}:
                continue
            definition_row, _ = _definition_for_component(component, definition_by_id, definition_by_key)
            refs.update(_artifact_refs_from_definition(definition_row))
            if definition_row is None:
                component_key = str(component.get("component_key") or component.get("componentKey") or "").strip()
                if component_type == "skill" and component_key:
                    refs.add(_normalize_ref_token(f"skill:{component_key}"))
                elif component_key and ":" in component_key:
                    refs.add(_normalize_ref_token(component_key))

    workflow_metadata = _definition_metadata_row(workflow_definition)
    swdl_summary = workflow_metadata.get("swdlSummary")
    if isinstance(swdl_summary, dict):
        refs.update(_normalize_ref_token(str(value)) for value in _safe_list(swdl_summary.get("artifactRefs")) if str(value).strip())
    return {ref for ref in refs if ref}


def _best_bundle_alignment(
    *,
    observation: dict[str, Any] | None,
    workflow_definition: dict[str, Any] | None,
    definitions: list[dict[str, Any]],
    definition_by_id: dict[int, dict[str, Any]],
    definition_by_key: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any] | None:
    stack_refs = _stack_artifact_refs(observation, workflow_definition, definition_by_id, definition_by_key)
    if not stack_refs:
        return None

    best: dict[str, Any] | None = None
    for definition in definitions:
        if str(definition.get("definition_type") or "") != "bundle":
            continue
        metadata = _definition_metadata_row(definition)
        bundle_summary = metadata.get("bundleSummary")
        bundle_refs = _safe_list(bundle_summary.get("artifactRefs")) if isinstance(bundle_summary, dict) else []
        normalized_bundle_refs = {_normalize_ref_token(str(value)) for value in bundle_refs if str(value).strip()}
        if not normalized_bundle_refs:
            continue
        matched = sorted(stack_refs & normalized_bundle_refs)
        if not matched:
            continue
        score = round(
            0.65 * (len(matched) / max(1, len(normalized_bundle_refs)))
            + 0.35 * (len(matched) / max(1, len(stack_refs))),
            4,
        )
        candidate = {
            "bundleId": str(definition.get("external_id") or ""),
            "bundleName": str(definition.get("display_name") or ""),
            "matchScore": score,
            "matchedRefs": matched,
            "sourceUrl": str(definition.get("source_url") or ""),
        }
        if best is None or score > _safe_float(best.get("matchScore"), 0.0):
            best = candidate
    return best if best and _safe_float(best.get("matchScore"), 0.0) >= 0.34 else None


def _context_alignment_signal(workflow_definition: dict[str, Any] | None) -> dict[str, Any]:
    metadata = _definition_metadata_row(workflow_definition)
    context_summary = metadata.get("contextSummary")
    if not isinstance(context_summary, dict):
        return {"bonus": 0.0, "evidence": None}

    referenced = _safe_int(context_summary.get("referenced"), 0)
    resolved = _safe_int(context_summary.get("resolved"), 0)
    previewed = _safe_int(context_summary.get("previewed"), 0)
    token_footprint = _safe_int(context_summary.get("previewTokenFootprint"), 0)
    if referenced <= 0:
        return {"bonus": 0.0, "evidence": None}

    resolved_contexts_raw = _safe_list(metadata.get("resolvedContextModules"))
    resolved_contexts: list[dict[str, Any]] = []
    for item in resolved_contexts_raw:
        if not isinstance(item, dict):
            continue
        preview_summary = _safe_dict(item.get("previewSummary"))
        resolved_contexts.append(
            {
                "contextRef": str(item.get("contextRef") or ""),
                "moduleId": str(item.get("moduleId") or ""),
                "moduleName": str(item.get("moduleName") or ""),
                "status": str(item.get("status") or ""),
                "sourceUrl": str(item.get("sourceUrl") or ""),
                "previewTokens": _safe_int(preview_summary.get("totalTokens"), 0),
            }
        )

    bonus = 0.04 * (resolved / max(1, referenced)) + 0.03 * (previewed / max(1, referenced))
    summary = f"Resolved {resolved} of {referenced} workflow context references"
    if previewed > 0:
        summary += f"; previewed {previewed} module pack(s) for ~{token_footprint} tokens."
    else:
        summary += "."
    return {
        "bonus": round(bonus, 4),
        "evidence": {
            "label": "Context availability",
            "summary": summary,
            "sourceType": "context_preview",
            "confidence": round((resolved + previewed) / max(1, referenced * 2), 4),
            "metrics": {
                "referenced": referenced,
                "resolved": resolved,
                "previewed": previewed,
                "previewTokenFootprint": token_footprint,
                "resolvedContexts": resolved_contexts,
            },
        },
    }


def _execution_alignment_signal(feature: Feature, workflow_definition: dict[str, Any] | None) -> dict[str, Any]:
    metadata = _definition_metadata_row(workflow_definition)
    executions = metadata.get("recentExecutions")
    execution_summary = metadata.get("executionSummary")
    if not isinstance(executions, list) or not executions:
        return {"bonus": 0.0, "evidence": None}

    feature_tokens = _feature_tokens(feature)
    completed = 0
    active = 0
    feature_correlated = 0
    recent = 0
    latest_started_at = ""
    valid_execution_count = 0
    for execution in executions:
        if not isinstance(execution, dict):
            continue
        valid_execution_count += 1
        status = str(execution.get("status") or "").lower()
        if status == "completed":
            completed += 1
        if status in {"running", "pending", "paused"}:
            active += 1
        parameter_tokens: set[str] = set()
        parameters = execution.get("parameters")
        if isinstance(parameters, dict):
            for value in parameters.values():
                if isinstance(value, str):
                    parameter_tokens |= _tokenize_text(value)
        if feature_tokens and parameter_tokens and feature_tokens & parameter_tokens:
            feature_correlated += 1
        started_at = str(execution.get("startedAt") or "").strip()
        latest_started_at = latest_started_at or started_at
        started_dt = _parse_iso(started_at)
        if started_dt is not None:
            age = datetime.now(timezone.utc) - started_dt.astimezone(timezone.utc)
            if age.days <= 14:
                recent += 1

    count = max(1, valid_execution_count)
    bonus = (
        0.06 * (completed / count)
        + 0.04 * (feature_correlated / count)
        + 0.02 * (recent / count)
        + (0.02 if active > 0 else 0.0)
    )
    latest_label = latest_started_at or (str(execution_summary.get("latestStartedAt") or "") if isinstance(execution_summary, dict) else "")
    summary = f"{count} recent SkillMeat execution(s); {completed} completed"
    if active > 0:
        summary += f", {active} active"
    if feature_correlated > 0:
        summary += f", {feature_correlated} matched current feature metadata"
    if latest_label:
        summary += f". Latest start: {latest_label}."
    else:
        summary += "."
    return {
        "bonus": round(bonus, 4),
        "evidence": {
            "label": "Workflow execution history",
            "summary": summary,
            "sourceType": "workflow_execution",
            "confidence": round((completed + feature_correlated + recent) / max(1, count * 3), 4),
            "metrics": {
                "count": count,
                "completed": completed,
                "active": active,
                "featureCorrelated": feature_correlated,
                "recent": recent,
                "sourceUrl": str(execution_summary.get("sourceUrl") or "") if isinstance(execution_summary, dict) else "",
                "liveUpdateHint": str(execution_summary.get("liveUpdateHint") or "") if isinstance(execution_summary, dict) else "",
            },
        },
    }


def _candidate_enrichment(
    *,
    feature: Feature,
    observation: dict[str, Any] | None,
    definitions: list[dict[str, Any]],
    definition_by_id: dict[int, dict[str, Any]],
    definition_by_key: dict[tuple[str, str], dict[str, Any]],
    definition_indexes: tuple[
        dict[tuple[str, str], dict[str, Any]],
        dict[tuple[str, str], dict[str, Any]],
        dict[tuple[str, str], dict[str, Any]],
    ],
) -> dict[str, Any]:
    workflow_definition = _workflow_definition_for_observation(observation, definition_by_id, definition_by_key, definition_indexes)
    workflow_metadata = _definition_metadata_row(workflow_definition)

    bonus = 0.0
    evidence: list[dict[str, Any]] = []
    notes: list[str] = []

    is_effective = bool(workflow_metadata.get("isEffective")) or bool(_safe_dict(workflow_metadata.get("effectiveWorkflow")).get("isEffective"))
    if is_effective:
        bonus += 0.08
        notes.append("uses effective SkillMeat workflow precedence")
        evidence.append(
            {
                "label": "Effective workflow precedence",
                "summary": "Project-scoped effective workflow metadata outranks same-name global definitions for this stack.",
                "sourceType": "effective_workflow",
                "confidence": 0.92,
                "metrics": {
                    "effectiveWorkflowId": str(workflow_metadata.get("effectiveWorkflowId") or _safe_dict(workflow_metadata.get("effectiveWorkflow")).get("id") or ""),
                    "effectiveWorkflowName": str(workflow_metadata.get("effectiveWorkflowName") or _safe_dict(workflow_metadata.get("effectiveWorkflow")).get("name") or ""),
                    "workflowScope": str(workflow_metadata.get("workflowScope") or _safe_dict(workflow_metadata.get("effectiveWorkflow")).get("scope") or ""),
                    "sourceUrl": str(workflow_definition.get("source_url") or "") if isinstance(workflow_definition, dict) else "",
                },
            }
        )

    context_signal = _context_alignment_signal(workflow_definition)
    bonus += _safe_float(context_signal.get("bonus"), 0.0)
    if context_signal.get("evidence"):
        evidence.append(context_signal["evidence"])
        notes.append("has resolved workflow context coverage")

    bundle_alignment = _best_bundle_alignment(
        observation=observation,
        workflow_definition=workflow_definition,
        definitions=definitions,
        definition_by_id=definition_by_id,
        definition_by_key=definition_by_key,
    )
    if bundle_alignment:
        match_score = _safe_float(bundle_alignment.get("matchScore"), 0.0)
        bonus += 0.08 * match_score
        notes.append(f"aligns to curated bundle {bundle_alignment.get('bundleName') or bundle_alignment.get('bundleId')}")
        evidence.append(
            {
                "label": "Curated bundle alignment",
                "summary": (
                    f"Matches curated bundle `{bundle_alignment.get('bundleName') or bundle_alignment.get('bundleId')}` "
                    f"with {round(match_score * 100)}% fit across {len(_safe_list(bundle_alignment.get('matchedRefs')))} artifact refs."
                ),
                "sourceType": "bundle_alignment",
                "confidence": round(match_score, 4),
                "metrics": bundle_alignment,
            }
        )

    execution_signal = _execution_alignment_signal(feature, workflow_definition)
    bonus += _safe_float(execution_signal.get("bonus"), 0.0)
    if execution_signal.get("evidence"):
        evidence.append(execution_signal["evidence"])
        notes.append("has relevant execution history")

    return {
        "workflowDefinition": workflow_definition,
        "bonus": round(bonus, 4),
        "evidence": evidence,
        "notes": notes,
    }


def _stack_rank(item: dict[str, Any], context: dict[str, Any]) -> float:
    scope = _parse_stack_scope_id(str(item.get("scopeId") or ""))
    workflow_ref = str(scope.get("workflowRef") or "")
    workflow_candidates = set(context.get("workflowCandidates") or [])
    workflow_match = 1.0 if workflow_ref and workflow_ref in workflow_candidates else (0.5 if not workflow_candidates else 0.0)
    agent_overlap = _overlap_ratio(set(scope.get("agents") or []), set(context.get("agents") or []))
    skill_overlap = _overlap_ratio(set(scope.get("skills") or []), set(context.get("skills") or []))
    context_overlap = _overlap_ratio(set(scope.get("contexts") or []), set(context.get("contexts") or []))
    sample_bonus = min(_safe_int(item.get("sampleSize"), 0), 6) / 6.0
    return (
        0.32 * _safe_float(item.get("successScore"), 0.0)
        + 0.18 * _safe_float(item.get("efficiencyScore"), 0.0)
        + 0.18 * _safe_float(item.get("qualityScore"), 0.0)
        + 0.14 * (1.0 - _safe_float(item.get("riskScore"), 0.0))
        + 0.10 * workflow_match
        + 0.04 * agent_overlap
        + 0.03 * skill_overlap
        + 0.01 * context_overlap
        + 0.04 * sample_bonus
    )


def _stack_confidence(rank_score: float, stack: dict[str, Any], components: list[RecommendedStackComponent]) -> float:
    resolvable = [component for component in components if component.componentType in _RESOLVABLE_COMPONENT_TYPES]
    resolved = [
        component
        for component in resolvable
        if component.status == "resolved" or (component.definition and component.definition.status == "resolved")
    ]
    resolution_ratio = len(resolved) / len(resolvable) if resolvable else 0.8
    sample_bonus = min(_safe_int(stack.get("sampleSize"), 0), 5) / 5.0
    return round(_clamp(0.3 + 0.35 * rank_score + 0.2 * resolution_ratio + 0.15 * sample_bonus), 4)


def _definition_warnings(
    stack: RecommendedStack | None,
    definitions_available: bool,
) -> list[FeatureExecutionWarning]:
    if stack is None:
        if definitions_available:
            return []
        return [
            FeatureExecutionWarning(
                section="stack",
                message="No cached SkillMeat definitions are available yet, so stack recommendations cannot be resolved beyond local evidence.",
            )
        ]

    unresolved = [
        component.label or component.componentKey
        for component in stack.components
        if component.componentType in _RESOLVABLE_COMPONENT_TYPES
        and component.status != "resolved"
    ]
    if not unresolved and definitions_available:
        return []

    if not definitions_available:
        return [
            FeatureExecutionWarning(
                section="stack",
                message="Stack recommendations are based on local CCDash observations because no SkillMeat definition cache is available for this project.",
            )
        ]

    preview = ", ".join(unresolved[:3])
    suffix = "" if len(unresolved) <= 3 else f", and {len(unresolved) - 3} more"
    return [
        FeatureExecutionWarning(
            section="stack",
            message=f"Some stack components could not be resolved to SkillMeat definitions: {preview}{suffix}.",
        )
    ]


def _matched_component_sets(observation: dict[str, Any]) -> dict[str, set[str]]:
    groups: dict[str, set[str]] = {"agent": set(), "skill": set(), "context_module": set()}
    for component in _safe_list(observation.get("components")):
        component_type = str(component.get("component_type") or component.get("componentType") or "")
        component_key = str(component.get("component_key") or component.get("componentKey") or "").strip()
        if component_type in groups and component_key:
            groups[component_type].add(component_key)
    return groups


def _score_similar_work(
    *,
    observation: dict[str, Any],
    target_stack: RecommendedStack,
    context: dict[str, Any],
) -> tuple[float, list[str], list[str]]:
    reasons: list[str] = []
    matched_components: list[str] = []
    workflow_ref = str(observation.get("workflow_ref") or observation.get("workflowRef") or "").strip()
    score = 0.0

    if target_stack.workflowRef and workflow_ref == target_stack.workflowRef:
        score += 0.45
        reasons.append(f"Shares workflow `{workflow_ref}`.")

    observation_components = _matched_component_sets(observation)
    target_agents = {component.componentKey for component in target_stack.components if component.componentType == "agent" and component.componentKey}
    target_skills = {component.componentKey for component in target_stack.components if component.componentType == "skill" and component.componentKey}
    target_contexts = {component.componentKey for component in target_stack.components if component.componentType == "context_module" and component.componentKey}

    shared_agents = sorted(target_agents & observation_components["agent"])
    if shared_agents:
        score += min(0.18, len(shared_agents) * 0.09)
        matched_components.extend(shared_agents[:2])
        reasons.append(f"Reuses agent stack: {', '.join(shared_agents[:2])}.")

    shared_skills = sorted(target_skills & observation_components["skill"])
    if shared_skills:
        score += min(0.15, len(shared_skills) * 0.075)
        matched_components.extend(shared_skills[:2])
        reasons.append(f"Reuses skills: {', '.join(shared_skills[:2])}.")

    shared_contexts = sorted(target_contexts & observation_components["context_module"])
    if shared_contexts:
        score += min(0.1, len(shared_contexts) * 0.05)
        matched_components.extend(shared_contexts[:2])
        reasons.append(f"Shares context modules: {', '.join(shared_contexts[:2])}.")

    observation_feature_id = str(observation.get("feature_id") or observation.get("featureId") or "").strip()
    if observation_feature_id and observation_feature_id == str(context.get("featureId") or ""):
        score += 0.12
        reasons.append("Comes from the same feature lineage.")

    return _clamp(score), reasons[:3], _dedupe_strings(matched_components)[:6]


async def _load_observations(repo: Any, project_id: str) -> list[dict[str, Any]]:
    rows = await repo.list_stack_observations(project_id, limit=_MAX_OBSERVATIONS, offset=0)
    hydrated: list[dict[str, Any]] = []
    for row in rows:
        session_id = str(row.get("session_id") or row.get("sessionId") or "").strip()
        if not session_id:
            continue
        observation = await repo.get_stack_observation(project_id, session_id)
        if observation:
            hydrated.append(canonicalize_stack_observation(observation))
    return hydrated


def _build_stack_record(
    *,
    stack_item: dict[str, Any],
    observation: dict[str, Any] | None,
    recommendation: ExecutionRecommendation,
    definition_by_id: dict[int, dict[str, Any]],
    definition_by_key: dict[tuple[str, str], dict[str, Any]],
    definition_indexes: tuple[
        dict[tuple[str, str], dict[str, Any]],
        dict[tuple[str, str], dict[str, Any]],
        dict[tuple[str, str], dict[str, Any]],
    ],
    rank_score: float,
) -> RecommendedStack:
    components = _build_stack_components(observation or {}, definition_by_id, definition_by_key, definition_indexes) if observation else []
    workflow_scope = str(stack_item.get("scopeId") or "")
    parsed_scope = _parse_stack_scope_id(workflow_scope)
    workflow_ref = _preferred_stack_workflow_ref(
        str(parsed_scope.get("workflowRef") or workflow_scope),
        observation,
        components,
    )
    if not components and parsed_scope.get("workflowRef"):
        components = [
            RecommendedStackComponent(
                componentType="workflow",
                componentKey=str(parsed_scope.get("workflowRef") or ""),
                label=str(parsed_scope.get("workflowRef") or ""),
                status="inferred",
                confidence=0.7,
                sourceAttribution="rollup_scope",
                artifactRef=ExecutionArtifactReference(
                    key=str(parsed_scope.get("workflowRef") or ""),
                    label=str(parsed_scope.get("workflowRef") or ""),
                    kind="workflow",
                    status="unresolved",
                    definitionType="",
                    externalId="",
                    sourceUrl="",
                    sourceAttribution="rollup_scope",
                    metadata={"workflowRef": str(parsed_scope.get("workflowRef") or "")},
                ),
            )
        ]
        workflow_ref = _preferred_stack_workflow_ref(workflow_ref, observation, components)

    return RecommendedStack(
        id=str(stack_item.get("scopeId") or workflow_ref or "local-stack"),
        label=_stack_label(workflow_ref, components),
        workflowRef=workflow_ref,
        commandAlignment=f"Aligned with {recommendation.ruleId} and `{recommendation.primary.command}`.",
        confidence=_stack_confidence(rank_score, stack_item, components),
        sampleSize=_safe_int(stack_item.get("sampleSize"), 0),
        successScore=round(_safe_float(stack_item.get("successScore"), 0.0), 4),
        efficiencyScore=round(_safe_float(stack_item.get("efficiencyScore"), 0.0), 4),
        qualityScore=round(_safe_float(stack_item.get("qualityScore"), 0.0), 4),
        riskScore=round(_safe_float(stack_item.get("riskScore"), 0.0), 4),
        sourceSessionId=str(observation.get("session_id") or observation.get("sessionId") or "") if observation else "",
        sourceFeatureId=str(observation.get("feature_id") or observation.get("featureId") or "") if observation else "",
        explanation=(
            f"Ranked from {max(1, _safe_int(stack_item.get('sampleSize'), 0))} observed runs with historical "
            f"success {round(_safe_float(stack_item.get('successScore'), 0.0) * 100)}% and risk "
            f"{round(_safe_float(stack_item.get('riskScore'), 0.0) * 100)}%."
        ),
        components=components,
    )


async def build_stack_recommendations(
    db: Any,
    project: Any,
    *,
    feature: Feature,
    sessions: list[Any],
    recommendation: ExecutionRecommendation,
) -> dict[str, Any]:
    project_id = str(getattr(project, "id", "") or "")
    intelligence_repo = get_agentic_intelligence_repository(db)
    session_repo = get_session_repository(db)

    definitions = normalize_definitions_for_project(
        await intelligence_repo.list_external_definitions(project_id, limit=5000, offset=0),
        project,
    )
    definition_by_id, definition_by_key = _definition_map(definitions)
    definition_indexes = build_definition_indexes(definitions)
    observations = await _load_observations(intelligence_repo, project_id)
    stack_payload = await get_workflow_effectiveness(
        db,
        project,
        period="all",
        scope_type="stack",
        limit=_MAX_STACK_ITEMS,
        offset=0,
        recompute=False,
    )
    stack_items = _safe_list(stack_payload.get("items"))
    if not stack_items and observations:
        stack_payload = await get_workflow_effectiveness(
            db,
            project,
            period="all",
            scope_type="stack",
            limit=_MAX_STACK_ITEMS,
            offset=0,
            recompute=True,
        )
        stack_items = _safe_list(stack_payload.get("items"))
    elif stack_items and observations and _stack_items_need_refresh(stack_items):
        stack_payload = await get_workflow_effectiveness(
            db,
            project,
            period="all",
            scope_type="stack",
            limit=_MAX_STACK_ITEMS,
            offset=0,
            recompute=True,
        )
        stack_items = _safe_list(stack_payload.get("items"))

    if not stack_items:
        return {
            "recommendedStack": None,
            "stackAlternatives": [],
            "stackEvidence": [],
            "definitionResolutionWarnings": _definition_warnings(None, bool(definitions)),
        }

    context = _current_context(feature, sessions, recommendation)
    stack_by_scope = {str(item.get("scopeId") or ""): item for item in stack_items if str(item.get("scopeId") or "").strip()}
    observations_by_scope: dict[str, list[dict[str, Any]]] = {}
    observation_by_session_id: dict[str, dict[str, Any]] = {}
    for observation in observations:
        scope_id = _stack_scope_id(observation)
        observations_by_scope.setdefault(scope_id, []).append(observation)
        session_id = str(observation.get("session_id") or observation.get("sessionId") or "")
        if session_id:
            observation_by_session_id[session_id] = observation

    ranked_candidates: list[dict[str, Any]] = []
    for item in stack_items:
        rank_score = _stack_rank(item, context)
        scope_id = str(item.get("scopeId") or "")
        evidence_summary = _safe_dict(item.get("evidenceSummary"))
        representative_session_ids = [str(value) for value in _safe_list(evidence_summary.get("representativeSessionIds")) if str(value).strip()]
        representative_observation = None
        for session_id in representative_session_ids:
            representative_observation = observation_by_session_id.get(session_id)
            if representative_observation:
                break
        if representative_observation is None:
            scoped_observations = observations_by_scope.get(scope_id, [])
            if scoped_observations:
                representative_observation = scoped_observations[0]

        stack_record = _build_stack_record(
            stack_item=item,
            observation=representative_observation,
            recommendation=recommendation,
            definition_by_id=definition_by_id,
            definition_by_key=definition_by_key,
            definition_indexes=definition_indexes,
            rank_score=rank_score,
        )
        enrichment = _candidate_enrichment(
            feature=feature,
            observation=representative_observation,
            definitions=definitions,
            definition_by_id=definition_by_id,
            definition_by_key=definition_by_key,
            definition_indexes=definition_indexes,
        )
        if enrichment["notes"]:
            note_preview = ", ".join(str(note) for note in enrichment["notes"][:3])
            stack_record.commandAlignment = f"{stack_record.commandAlignment} Ranked higher because it {note_preview}."
            stack_record.explanation = f"{stack_record.explanation} It {note_preview}."
        ranked_candidates.append(
            {
                "rankScore": rank_score,
                "adjustedRank": rank_score + _safe_float(enrichment.get("bonus"), 0.0),
                "stackItem": item,
                "record": stack_record,
                "observation": representative_observation,
                "enrichment": enrichment,
            }
        )

    ranked_candidates.sort(
        key=lambda item: (
            -_safe_float(item.get("adjustedRank"), 0.0),
            -_safe_int(_safe_dict(item.get("stackItem")).get("sampleSize"), 0),
            -_safe_float(_safe_dict(item.get("stackItem")).get("successScore"), 0.0),
            str(_safe_dict(item.get("stackItem")).get("scopeId") or ""),
        )
    )

    primary_candidate = ranked_candidates[0] if ranked_candidates else None
    primary = primary_candidate["record"] if primary_candidate else None
    alternatives = [item["record"] for item in ranked_candidates[1 : 1 + _MAX_ALTERNATIVES]]

    session_cache: dict[str, dict[str, Any] | None] = {}

    async def load_session(session_id: str) -> dict[str, Any] | None:
        if session_id not in session_cache:
            session_cache[session_id] = await session_repo.get_by_id(session_id)
        return session_cache[session_id]

    similar_work: list[SimilarWorkExample] = []
    if primary is not None:
        candidates: list[SimilarWorkExample] = []
        for observation in observations:
            session_id = str(observation.get("session_id") or observation.get("sessionId") or "").strip()
            if not session_id or session_id == primary.sourceSessionId:
                continue
            similarity_score, reasons, matched_components = _score_similar_work(
                observation=observation,
                target_stack=primary,
                context=context,
            )
            if similarity_score < 0.35:
                continue

            session_row = await load_session(session_id)
            stack_scope = _stack_scope_id(observation)
            metrics = stack_by_scope.get(stack_scope) or {}
            candidates.append(
                SimilarWorkExample(
                    sessionId=session_id,
                    featureId=str(observation.get("feature_id") or observation.get("featureId") or ""),
                    title=str(session_id),
                    workflowRef=str(observation.get("workflow_ref") or observation.get("workflowRef") or ""),
                    similarityScore=round(similarity_score, 4),
                    reasons=reasons,
                    matchedComponents=matched_components,
                    startedAt=str((session_row or {}).get("started_at") or ""),
                    endedAt=str((session_row or {}).get("ended_at") or ""),
                    totalCost=round(_safe_float((session_row or {}).get("total_cost"), 0.0), 4),
                    durationSeconds=_safe_int((session_row or {}).get("duration_seconds"), 0),
                    successScore=round(_safe_float(metrics.get("successScore"), 0.0), 4),
                    efficiencyScore=round(_safe_float(metrics.get("efficiencyScore"), 0.0), 4),
                    qualityScore=round(_safe_float(metrics.get("qualityScore"), 0.0), 4),
                    riskScore=round(_safe_float(metrics.get("riskScore"), 0.0), 4),
                )
            )

        candidates.sort(
            key=lambda item: (
                -item.similarityScore,
                -item.successScore,
                item.sessionId,
            )
        )
        similar_work = candidates[:_MAX_SIMILAR_WORK]

    source_path = next(
        (
            ref
            for ref in recommendation.evidenceRefs
            if isinstance(ref, str) and ref.endswith(".md")
        ),
        "",
    )
    stack_evidence: list[StackRecommendationEvidence] = []
    if primary is not None:
        stack_evidence.append(
            StackRecommendationEvidence(
                id="STK-EV-1",
                label="Execution rule alignment",
                summary=primary.commandAlignment,
                sourceType="command_rule",
                sourceId=recommendation.ruleId,
                sourcePath=source_path,
                confidence=round(recommendation.confidence, 4),
                metrics={
                    "ruleConfidence": round(recommendation.confidence, 4),
                    "ruleId": recommendation.ruleId,
                },
            )
        )
        stack_evidence.append(
            StackRecommendationEvidence(
                id="STK-EV-2",
                label="Historical effectiveness",
                summary=(
                    f"{primary.sampleSize} matching runs with success {round(primary.successScore * 100)}%, "
                    f"quality {round(primary.qualityScore * 100)}%, and risk {round(primary.riskScore * 100)}%."
                ),
                sourceType="stack_rollup",
                sourceId=primary.id,
                confidence=primary.confidence,
                metrics={
                    "sampleSize": primary.sampleSize,
                    "successScore": primary.successScore,
                    "efficiencyScore": primary.efficiencyScore,
                    "qualityScore": primary.qualityScore,
                    "riskScore": primary.riskScore,
                },
            )
        )
        if similar_work:
            stack_evidence.append(
                StackRecommendationEvidence(
                    id="STK-EV-3",
                    label="Similar work",
                    summary=f"Found {len(similar_work)} similar historical sessions that share the same workflow or stack components.",
                    sourceType="similar_work",
                    sourceId=primary.id,
                    confidence=round(
                        sum(item.similarityScore for item in similar_work) / max(1, len(similar_work)),
                        4,
                    ),
                    metrics={"count": len(similar_work)},
                    similarWork=similar_work,
                )
            )

        resolvable_count = sum(1 for component in primary.components if component.componentType in _RESOLVABLE_COMPONENT_TYPES)
        resolved_count = sum(1 for component in primary.components if component.componentType in _RESOLVABLE_COMPONENT_TYPES and component.status == "resolved")
        stack_evidence.append(
            StackRecommendationEvidence(
                id="STK-EV-4",
                label="Definition coverage",
                summary=(
                    f"{resolved_count} of {resolvable_count} stack components resolved to cached SkillMeat definitions."
                    if resolvable_count
                    else "This stack is driven by local CCDash evidence only."
                ),
                sourceType="definition_resolution",
                sourceId=primary.id,
                confidence=round(resolved_count / resolvable_count, 4) if resolvable_count else 0.0,
                metrics={
                    "resolvedComponents": resolved_count,
                    "resolvableComponents": resolvable_count,
                },
            )
        )
        enrichment_evidence = _safe_list(_safe_dict(primary_candidate).get("enrichment", {}).get("evidence")) if primary_candidate else []
        for index, evidence_item in enumerate(enrichment_evidence, start=5):
            metrics = _safe_dict(evidence_item.get("metrics"))
            stack_evidence.append(
                StackRecommendationEvidence(
                    id=f"STK-EV-{index}",
                    label=str(evidence_item.get("label") or "SkillMeat evidence"),
                    summary=str(evidence_item.get("summary") or ""),
                    sourceType=str(evidence_item.get("sourceType") or "skillmeat"),
                    sourceId=primary.id,
                    confidence=round(_safe_float(evidence_item.get("confidence"), 0.0), 4),
                    metrics=metrics,
                )
            )

    return {
        "recommendedStack": primary,
        "stackAlternatives": alternatives,
        "stackEvidence": stack_evidence,
        "definitionResolutionWarnings": _definition_warnings(primary, bool(definitions)),
    }
