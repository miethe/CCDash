"""Workflow registry aggregation over cached SkillMeat definitions and CCDash observations."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.db.factory import get_agentic_intelligence_repository, get_session_repository
from backend.services.integrations.skillmeat_routes import normalize_definitions_for_project
from backend.services.stack_observations import canonicalize_stack_observation

_MAX_REGISTRY_SCAN = 5000
_MAX_REPRESENTATIVE_COMMANDS = 5
_MAX_REPRESENTATIVE_SESSIONS = 3
_MAX_RECENT_EXECUTIONS = 5
_STALE_THRESHOLD_DAYS = 14


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


def _parse_iso(value: str | None) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        raw = str(value or "").strip()
        key = _normalize_token(raw)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(raw)
    return deduped


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
    external_id = str(definition.get("external_id") or "").strip()
    if external_id.startswith("command:"):
        suffix = external_id.split(":", 1)[1]
        aliases.extend([suffix, f"/{suffix}", f"dev:{suffix}", f"/dev:{suffix}"])
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


def _definition_priority(definition: dict[str, Any]) -> tuple[int, int]:
    metadata = _definition_metadata(definition)
    score = 0
    if bool(metadata.get("isEffective")):
        score += 4
    if str(metadata.get("workflowScope") or "").strip().lower() == "project":
        score += 2
    if str(definition.get("source_url") or "").strip():
        score += 1
    fetched_at = _parse_iso(str(definition.get("fetched_at") or definition.get("updated_at") or ""))
    freshness = int(fetched_at.timestamp()) if fetched_at is not None else 0
    return (score, freshness)


def _build_definition_indexes(
    definitions: list[dict[str, Any]],
) -> tuple[
    dict[tuple[str, str], dict[str, Any]],
    dict[str, list[dict[str, Any]]],
    dict[str, list[dict[str, Any]]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    workflow_by_token: dict[str, list[dict[str, Any]]] = {}
    command_by_token: dict[str, list[dict[str, Any]]] = {}
    workflows: list[dict[str, Any]] = []
    command_artifacts: list[dict[str, Any]] = []
    bundles: list[dict[str, Any]] = []

    for definition in definitions:
        definition_type = str(definition.get("definition_type") or "").strip()
        external_id = str(definition.get("external_id") or "").strip()
        if definition_type and external_id:
            by_key[(definition_type, external_id)] = definition
        if definition_type == "workflow":
            workflows.append(definition)
            for alias in _definition_aliases(definition):
                token = _normalize_token(alias)
                if token:
                    workflow_by_token.setdefault(token, []).append(definition)
        elif _is_command_artifact(definition):
            command_artifacts.append(definition)
            for alias in _definition_aliases(definition):
                token = _normalize_token(alias)
                if token:
                    command_by_token.setdefault(token, []).append(definition)
        elif definition_type == "bundle":
            bundles.append(definition)

    return by_key, workflow_by_token, command_by_token, workflows, command_artifacts, bundles


def _match_definition(tokens: list[str], index: dict[str, list[dict[str, Any]]]) -> dict[str, Any] | None:
    for token in _dedupe_strings(tokens):
        matches = index.get(_normalize_token(token), [])
        if matches:
            return sorted(matches, key=_definition_priority, reverse=True)[0]
    return None


def _component_definition(
    component: dict[str, Any],
    definitions_by_key: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any] | None:
    definition_type = str(component.get("external_definition_type") or component.get("externalDefinitionType") or "").strip()
    external_id = str(
        component.get("external_definition_external_id")
        or component.get("externalDefinitionExternalId")
        or ""
    ).strip()
    if definition_type and external_id:
        return definitions_by_key.get((definition_type, external_id))
    return None


def _observation_tokens(observation: dict[str, Any]) -> list[str]:
    workflow_ref = str(observation.get("workflow_ref") or observation.get("workflowRef") or "").strip()
    evidence = _safe_dict(observation.get("evidence_json") or observation.get("evidence"))
    commands = [str(command).strip() for command in _safe_list(evidence.get("commands")) if str(command).strip()]
    tokens: list[str] = []
    if workflow_ref:
        tokens.extend([workflow_ref, _command_token(workflow_ref), workflow_ref.lstrip("/")])
        if ":" in workflow_ref:
            tokens.append(workflow_ref.split(":")[-1])
    for command in commands:
        token = _command_token(command)
        if token:
            tokens.extend([token, token.lstrip("/")])
            if ":" in token:
                tokens.append(token.split(":")[-1])
    return _dedupe_strings(tokens)


def _workflow_definition_for_observation(
    observation: dict[str, Any],
    *,
    definitions_by_key: dict[tuple[str, str], dict[str, Any]],
    workflow_index: dict[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    for component in _safe_list(observation.get("components")):
        if str(component.get("component_type") or component.get("componentType") or "") != "workflow":
            continue
        definition = _component_definition(component, definitions_by_key)
        if definition and str(definition.get("definition_type") or "") == "workflow":
            return definition
    return _match_definition(_observation_tokens(observation), workflow_index)


def _command_definition_for_observation(
    observation: dict[str, Any],
    *,
    definitions_by_key: dict[tuple[str, str], dict[str, Any]],
    command_index: dict[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    for component in _safe_list(observation.get("components")):
        definition = _component_definition(component, definitions_by_key)
        if definition and _is_command_artifact(definition):
            return definition
    return _match_definition(_observation_tokens(observation), command_index)


def _merge_entities(target: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    if target.get("workflowDefinition") is None and source.get("workflowDefinition") is not None:
        target["workflowDefinition"] = source["workflowDefinition"]
    if target.get("commandArtifactDefinition") is None and source.get("commandArtifactDefinition") is not None:
        target["commandArtifactDefinition"] = source["commandArtifactDefinition"]
    target["observedRefs"] = _dedupe_strings(list(target.get("observedRefs", [])) + list(source.get("observedRefs", [])))
    target["commands"] = _dedupe_strings(list(target.get("commands", [])) + list(source.get("commands", [])))
    target["observations"] = list(target.get("observations", [])) + list(source.get("observations", []))
    return target


def _primary_observed_ref(entity: dict[str, Any]) -> str:
    if entity.get("observations"):
        sorted_observations = sorted(
            entity["observations"],
            key=lambda item: _parse_iso(str(item.get("updated_at") or item.get("started_at") or "")) or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        for observation in sorted_observations:
            workflow_ref = str(observation.get("workflow_ref") or observation.get("workflowRef") or "").strip()
            if workflow_ref:
                return workflow_ref
    refs = _dedupe_strings(list(entity.get("observedRefs", [])))
    return refs[0] if refs else ""


def _effective_workflow_id(workflow_definition: dict[str, Any] | None) -> str:
    metadata = _definition_metadata(workflow_definition)
    effective = _safe_dict(metadata.get("effectiveWorkflow"))
    return str(metadata.get("effectiveWorkflowId") or effective.get("id") or "")


def _effective_workflow_label(workflow_definition: dict[str, Any] | None) -> str:
    metadata = _definition_metadata(workflow_definition)
    effective = _safe_dict(metadata.get("effectiveWorkflow"))
    return str(metadata.get("effectiveWorkflowName") or effective.get("name") or "")


def _correlation_state(entity: dict[str, Any]) -> str:
    workflow_definition = entity.get("workflowDefinition")
    command_definition = entity.get("commandArtifactDefinition")
    if workflow_definition and command_definition:
        return "hybrid"
    if workflow_definition:
        return "strong"
    if command_definition:
        return "weak"
    return "unresolved"


def _resolution_kind(entity: dict[str, Any]) -> str:
    workflow_definition = entity.get("workflowDefinition")
    command_definition = entity.get("commandArtifactDefinition")
    if workflow_definition and command_definition:
        return "dual_backed"
    if workflow_definition:
        return "workflow_definition"
    if command_definition:
        return "command_artifact"
    return "none"


def _display_label(entity: dict[str, Any]) -> str:
    workflow_definition = entity.get("workflowDefinition")
    command_definition = entity.get("commandArtifactDefinition")
    if workflow_definition:
        return (
            _effective_workflow_label(workflow_definition)
            or str(workflow_definition.get("display_name") or "").strip()
            or str(workflow_definition.get("external_id") or "").strip()
        )
    if command_definition:
        return (
            str(command_definition.get("display_name") or "").strip()
            or str(command_definition.get("external_id") or "").strip()
            or _humanize_workflow_label(_primary_observed_ref(entity))
        )
    return _humanize_workflow_label(_primary_observed_ref(entity))


def _rollup_summary(rollup: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(rollup, dict):
        return None
    metrics = _safe_dict(rollup.get("metrics_json"))
    evidence = _safe_dict(rollup.get("evidence_summary_json"))
    return {
        "scopeType": str(rollup.get("scope_type") or ""),
        "scopeId": str(rollup.get("scope_id") or ""),
        "scopeLabel": str(metrics.get("scopeLabel") or ""),
        "sampleSize": _safe_int(metrics.get("sampleSize"), 0),
        "successScore": _safe_float(metrics.get("successScore"), 0.0),
        "efficiencyScore": _safe_float(metrics.get("efficiencyScore"), 0.0),
        "qualityScore": _safe_float(metrics.get("qualityScore"), 0.0),
        "riskScore": _safe_float(metrics.get("riskScore"), 0.0),
        "attributionCoverage": _safe_float(metrics.get("attributionCoverage"), 0.0),
        "averageAttributionConfidence": _safe_float(metrics.get("averageAttributionConfidence"), 0.0),
        "evidenceSummary": evidence,
    }


def _best_effectiveness_summary(
    entity: dict[str, Any],
    rollups_by_scope: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any] | None:
    workflow_definition = entity.get("workflowDefinition")
    candidates: list[tuple[str, str]] = []
    effective_workflow_id = _effective_workflow_id(workflow_definition)
    if effective_workflow_id:
        candidates.append(("effective_workflow", effective_workflow_id))
    if workflow_definition:
        workflow_external_id = str(workflow_definition.get("external_id") or "").strip()
        if workflow_external_id:
            candidates.append(("workflow", workflow_external_id))
    for observed_ref in _dedupe_strings(list(entity.get("observedRefs", []))):
        candidates.append(("workflow", observed_ref))
    command_definition = entity.get("commandArtifactDefinition")
    if command_definition:
        command_external_id = str(command_definition.get("external_id") or "").strip()
        if command_external_id:
            candidates.append(("workflow", command_external_id))
    for scope_type, scope_id in candidates:
        rollup = rollups_by_scope.get((scope_type, scope_id))
        summary = _rollup_summary(rollup)
        if summary is not None:
            if not summary.get("scopeLabel"):
                summary["scopeLabel"] = _display_label(entity)
            return summary
    return None


def _stack_artifact_refs(observation: dict[str, Any], workflow_definition: dict[str, Any] | None) -> set[str]:
    refs: set[str] = set()
    metadata = _definition_metadata(workflow_definition)
    swdl_summary = _safe_dict(metadata.get("swdlSummary"))
    refs.update(
        _normalize_token(str(value))
        for value in _safe_list(swdl_summary.get("artifactRefs"))
        if str(value).strip()
    )
    for component in _safe_list(observation.get("components")):
        component_type = str(component.get("component_type") or component.get("componentType") or "").strip()
        component_key = str(component.get("component_key") or component.get("componentKey") or "").strip()
        if component_type == "skill" and component_key:
            refs.add(_normalize_token(f"skill:{component_key}"))
        elif component_type in {"artifact", "agent", "command"} and ":" in component_key:
            refs.add(_normalize_token(component_key))
    return {ref for ref in refs if ref}


def _bundle_alignment(
    entity: dict[str, Any],
    bundles: list[dict[str, Any]],
) -> dict[str, Any] | None:
    observations = list(entity.get("observations", []))
    workflow_definition = entity.get("workflowDefinition")
    if not observations:
        return None
    best: dict[str, Any] | None = None
    for observation in observations:
        stack_refs = _stack_artifact_refs(observation, workflow_definition)
        if not stack_refs:
            continue
        for definition in bundles:
            metadata = _definition_metadata(definition)
            bundle_summary = _safe_dict(metadata.get("bundleSummary"))
            bundle_refs = {
                _normalize_token(str(value))
                for value in _safe_list(bundle_summary.get("artifactRefs"))
                if str(value).strip()
            }
            if not bundle_refs:
                continue
            matched = sorted(stack_refs & bundle_refs)
            if not matched:
                continue
            score = round(
                0.65 * (len(matched) / max(1, len(bundle_refs)))
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
            if best is None or _safe_float(candidate.get("matchScore"), 0.0) > _safe_float(best.get("matchScore"), 0.0):
                best = candidate
    if best and _safe_float(best.get("matchScore"), 0.0) >= 0.34:
        return best
    return None


def _composition_summary(entity: dict[str, Any], bundles: list[dict[str, Any]]) -> dict[str, Any]:
    workflow_definition = entity.get("workflowDefinition")
    metadata = _definition_metadata(workflow_definition)
    swdl_summary = _safe_dict(metadata.get("swdlSummary"))
    context_modules: list[dict[str, Any]] = []
    for item in _safe_list(metadata.get("resolvedContextModules")):
        if not isinstance(item, dict):
            continue
        preview_summary = _safe_dict(item.get("previewSummary"))
        context_modules.append(
            {
                "contextRef": str(item.get("contextRef") or ""),
                "moduleId": str(item.get("moduleId") or ""),
                "moduleName": str(item.get("moduleName") or ""),
                "status": str(item.get("status") or ""),
                "sourceUrl": str(item.get("sourceUrl") or ""),
                "previewTokens": _safe_int(preview_summary.get("totalTokens"), 0),
            }
        )
    return {
        "artifactRefs": _dedupe_strings([str(value) for value in _safe_list(swdl_summary.get("artifactRefs")) if str(value).strip()]),
        "contextRefs": _dedupe_strings([str(value) for value in _safe_list(swdl_summary.get("contextRefs")) if str(value).strip()]),
        "resolvedContextModules": context_modules,
        "planSummary": _safe_dict(metadata.get("planSummary")),
        "stageOrder": _dedupe_strings([str(value) for value in _safe_list(swdl_summary.get("stageOrder")) if str(value).strip()]),
        "gateCount": _safe_int(swdl_summary.get("gateCount"), 0),
        "fanOutCount": _safe_int(swdl_summary.get("fanOutCount"), 0),
        "bundleAlignment": _bundle_alignment(entity, bundles),
    }


def _representative_sessions(entity: dict[str, Any], sessions_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    observations = sorted(
        list(entity.get("observations", [])),
        key=lambda item: _parse_iso(str(item.get("updated_at") or item.get("started_at") or "")) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    items: list[dict[str, Any]] = []
    for observation in observations[:_MAX_REPRESENTATIVE_SESSIONS]:
        session_id = str(observation.get("session_id") or observation.get("sessionId") or "")
        session_row = sessions_by_id.get(session_id, {})
        items.append(
            {
                "sessionId": session_id,
                "featureId": str(observation.get("feature_id") or observation.get("featureId") or session_row.get("task_id") or ""),
                "title": str(session_row.get("title") or session_id or "Session"),
                "status": str(session_row.get("status") or ""),
                "workflowRef": str(observation.get("workflow_ref") or observation.get("workflowRef") or ""),
                "startedAt": str(session_row.get("started_at") or session_row.get("created_at") or ""),
                "endedAt": str(session_row.get("ended_at") or session_row.get("updated_at") or ""),
                "href": f"/sessions?session={session_id}",
            }
        )
    return items


def _recent_executions(entity: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = _definition_metadata(entity.get("workflowDefinition"))
    items: list[dict[str, Any]] = []
    for execution in _safe_list(metadata.get("recentExecutions"))[:_MAX_RECENT_EXECUTIONS]:
        if not isinstance(execution, dict):
            continue
        items.append(
            {
                "executionId": str(execution.get("executionId") or execution.get("id") or ""),
                "status": str(execution.get("status") or ""),
                "startedAt": str(execution.get("startedAt") or ""),
                "sourceUrl": str(execution.get("sourceUrl") or ""),
                "parameters": _safe_dict(execution.get("parameters")),
            }
        )
    return items


def _actions(entity: dict[str, Any], composition: dict[str, Any], representative_sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    workflow_definition = entity.get("workflowDefinition")
    command_definition = entity.get("commandArtifactDefinition")
    if workflow_definition:
        source_url = str(workflow_definition.get("source_url") or "").strip()
        actions.append(
            {
                "id": "open-workflow",
                "label": "Open SkillMeat workflow",
                "target": "external",
                "href": source_url,
                "disabled": not bool(source_url),
                "reason": "" if source_url else "No stable workflow URL is cached yet.",
                "metadata": {"definitionId": str(workflow_definition.get("external_id") or "")},
            }
        )
    if command_definition:
        source_url = str(command_definition.get("source_url") or "").strip()
        actions.append(
            {
                "id": "open-command-artifact",
                "label": "Open command artifact",
                "target": "external",
                "href": source_url,
                "disabled": not bool(source_url),
                "reason": "" if source_url else "No stable command artifact URL is cached yet.",
                "metadata": {"definitionId": str(command_definition.get("external_id") or "")},
            }
        )
    execution_summary = _safe_dict(_definition_metadata(workflow_definition).get("executionSummary"))
    execution_url = str(execution_summary.get("sourceUrl") or "").strip()
    actions.append(
        {
            "id": "open-executions",
            "label": "Open workflow executions",
            "target": "external",
            "href": execution_url,
            "disabled": not bool(execution_url),
            "reason": "" if execution_url else "No recent SkillMeat execution link is cached yet.",
            "metadata": {"liveUpdateHint": str(execution_summary.get("liveUpdateHint") or "")},
        }
    )
    bundle_alignment = composition.get("bundleAlignment")
    if isinstance(bundle_alignment, dict):
        bundle_url = str(bundle_alignment.get("sourceUrl") or "").strip()
        actions.append(
            {
                "id": "open-bundle",
                "label": "Open aligned bundle",
                "target": "external",
                "href": bundle_url,
                "disabled": not bool(bundle_url),
                "reason": "" if bundle_url else "No stable bundle URL is cached yet.",
                "metadata": {"bundleId": str(bundle_alignment.get("bundleId") or "")},
            }
        )
    context_urls = _dedupe_strings([
        str(item.get("sourceUrl") or "")
        for item in _safe_list(composition.get("resolvedContextModules"))
        if isinstance(item, dict) and str(item.get("sourceUrl") or "").strip()
    ])
    if context_urls:
        actions.append(
            {
                "id": "open-context-memory",
                "label": "Open context memory",
                "target": "external",
                "href": context_urls[0],
                "disabled": False,
                "reason": "",
                "metadata": {"contextCount": len(context_urls)},
            }
        )
    if representative_sessions:
        actions.append(
            {
                "id": "open-session",
                "label": "Open representative session",
                "target": "internal",
                "href": str(representative_sessions[0].get("href") or ""),
                "disabled": False,
                "reason": "",
                "metadata": {"sessionId": str(representative_sessions[0].get("sessionId") or "")},
            }
        )
    return actions


def _cache_issue(definition: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(definition, dict):
        return None
    updated_at = _parse_iso(str(definition.get("fetched_at") or definition.get("updated_at") or ""))
    if updated_at is None:
        return None
    age = datetime.now(timezone.utc) - updated_at.astimezone(timezone.utc)
    if age <= timedelta(days=_STALE_THRESHOLD_DAYS):
        return None
    return {
        "code": "stale_cache",
        "severity": "warning",
        "title": "Cached definition may be stale",
        "message": (
            f"Cached definition metadata is {age.days} day(s) old, so workflow correlation may lag behind SkillMeat."
        ),
        "metadata": {
            "updatedAt": updated_at.isoformat(),
            "thresholdDays": _STALE_THRESHOLD_DAYS,
        },
    }


def _issues(
    entity: dict[str, Any],
    composition: dict[str, Any],
    effectiveness: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    workflow_definition = entity.get("workflowDefinition")
    command_definition = entity.get("commandArtifactDefinition")
    observed_refs = _dedupe_strings(list(entity.get("observedRefs", [])))

    if workflow_definition is None and command_definition is None and observed_refs:
        issues.append(
            {
                "code": "unresolved_workflow",
                "severity": "error",
                "title": "Observed workflow is unresolved",
                "message": "CCDash observed a workflow family but could not correlate it to cached SkillMeat workflow or command definitions.",
                "metadata": {"observedRefs": observed_refs},
            }
        )
    elif workflow_definition is None and command_definition is not None:
        issues.append(
            {
                "code": "weak_resolution",
                "severity": "warning",
                "title": "Workflow is only command-backed",
                "message": "This workflow currently resolves to a command artifact without a stronger SkillMeat workflow definition match.",
                "metadata": {"commandArtifactId": str(command_definition.get("external_id") or "")},
            }
        )

    cache_issue = _cache_issue(workflow_definition or command_definition)
    if cache_issue is not None:
        issues.append(cache_issue)

    artifact_refs = list(composition.get("artifactRefs", []))
    context_refs = list(composition.get("contextRefs", []))
    stage_order = list(composition.get("stageOrder", []))
    plan_summary = _safe_dict(composition.get("planSummary"))
    if workflow_definition and not artifact_refs and not context_refs and not stage_order and not plan_summary:
        issues.append(
            {
                "code": "missing_composition",
                "severity": "warning",
                "title": "Workflow composition is missing",
                "message": "The cached workflow definition has no extracted artifact, context, stage, or plan summary metadata yet.",
                "metadata": {"workflowId": str(workflow_definition.get("external_id") or "")},
            }
        )

    resolved_contexts = [
        item for item in _safe_list(composition.get("resolvedContextModules")) if isinstance(item, dict)
    ]
    if context_refs and len(resolved_contexts) < len(context_refs):
        issues.append(
            {
                "code": "missing_context_coverage",
                "severity": "warning",
                "title": "Workflow context coverage is incomplete",
                "message": (
                    f"Resolved {len(resolved_contexts)} of {len(context_refs)} referenced context module(s) from the workflow definition."
                ),
                "metadata": {
                    "referenced": len(context_refs),
                    "resolved": len(resolved_contexts),
                },
            }
        )

    if effectiveness is None or _safe_int(effectiveness.get("sampleSize"), 0) <= 0:
        issues.append(
            {
                "code": "missing_effectiveness",
                "severity": "warning",
                "title": "No effectiveness evidence yet",
                "message": "Workflow effectiveness rollups have not been cached for this workflow entity yet.",
                "metadata": {},
            }
        )

    if workflow_definition and not observed_refs:
        issues.append(
            {
                "code": "no_recent_observations",
                "severity": "info",
                "title": "No CCDash observations yet",
                "message": "This SkillMeat workflow is cached, but CCDash has not yet correlated any observed session workflow family to it.",
                "metadata": {"workflowId": str(workflow_definition.get("external_id") or "")},
            }
        )

    return issues


def _last_observed_at(entity: dict[str, Any], sessions_by_id: dict[str, dict[str, Any]]) -> str:
    values: list[str] = []
    for observation in _safe_list(entity.get("observations")):
        session_id = str(observation.get("session_id") or observation.get("sessionId") or "")
        session_row = sessions_by_id.get(session_id, {})
        values.extend(
            [
                str(observation.get("updated_at") or ""),
                str(session_row.get("started_at") or ""),
                str(session_row.get("created_at") or ""),
            ]
        )
    parsed = [_parse_iso(value) for value in values if str(value).strip()]
    parsed = [value for value in parsed if value is not None]
    return max(parsed).isoformat() if parsed else ""


def _registry_detail(
    entity: dict[str, Any],
    *,
    bundles: list[dict[str, Any]],
    rollups_by_scope: dict[tuple[str, str], dict[str, Any]],
    sessions_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    workflow_definition = entity.get("workflowDefinition")
    command_definition = entity.get("commandArtifactDefinition")
    correlation_state = _correlation_state(entity)
    composition = _composition_summary(entity, bundles)
    effectiveness = _best_effectiveness_summary(entity, rollups_by_scope)
    representative_sessions = _representative_sessions(entity, sessions_by_id)
    recent_executions = _recent_executions(entity)
    issues = _issues(entity, composition, effectiveness)
    display_label = _display_label(entity)
    observed_aliases = _dedupe_strings(list(entity.get("observedRefs", [])))
    representative_commands = _dedupe_strings(list(entity.get("commands", [])))[:_MAX_REPRESENTATIVE_COMMANDS]
    detail = {
        "id": str(entity.get("id") or ""),
        "identity": {
            "registryId": str(entity.get("id") or ""),
            "observedWorkflowFamilyRef": _primary_observed_ref(entity),
            "observedAliases": observed_aliases,
            "displayLabel": display_label,
            "resolvedWorkflowId": str(_effective_workflow_id(workflow_definition) or (workflow_definition or {}).get("external_id") or ""),
            "resolvedWorkflowLabel": _effective_workflow_label(workflow_definition) or str((workflow_definition or {}).get("display_name") or ""),
            "resolvedWorkflowSourceUrl": str((workflow_definition or {}).get("source_url") or ""),
            "resolvedCommandArtifactId": str((command_definition or {}).get("external_id") or ""),
            "resolvedCommandArtifactLabel": str((command_definition or {}).get("display_name") or ""),
            "resolvedCommandArtifactSourceUrl": str((command_definition or {}).get("source_url") or ""),
            "resolutionKind": _resolution_kind(entity),
            "correlationState": correlation_state,
        },
        "correlationState": correlation_state,
        "issueCount": len(issues),
        "issues": issues,
        "effectiveness": effectiveness,
        "observedCommandCount": len(_dedupe_strings(list(entity.get("commands", [])))),
        "representativeCommands": representative_commands,
        "sampleSize": _safe_int((effectiveness or {}).get("sampleSize"), len(_safe_list(entity.get("observations")))),
        "lastObservedAt": _last_observed_at(entity, sessions_by_id),
        "composition": composition,
        "representativeSessions": representative_sessions,
        "recentExecutions": recent_executions,
        "actions": _actions(entity, composition, representative_sessions),
    }
    return detail


def _registry_item(detail: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(detail.get("id") or ""),
        "identity": detail.get("identity") or {},
        "correlationState": str(detail.get("correlationState") or "unresolved"),
        "issueCount": _safe_int(detail.get("issueCount"), 0),
        "issues": list(detail.get("issues", [])),
        "effectiveness": detail.get("effectiveness"),
        "observedCommandCount": _safe_int(detail.get("observedCommandCount"), 0),
        "representativeCommands": list(detail.get("representativeCommands", [])),
        "sampleSize": _safe_int(detail.get("sampleSize"), 0),
        "lastObservedAt": str(detail.get("lastObservedAt") or ""),
    }


def _matches_search(detail: dict[str, Any], search: str) -> bool:
    token = _normalize_token(search)
    if not token:
        return True
    haystacks = [
        str(_safe_dict(detail.get("identity")).get("displayLabel") or ""),
        str(_safe_dict(detail.get("identity")).get("resolvedWorkflowLabel") or ""),
        str(_safe_dict(detail.get("identity")).get("resolvedCommandArtifactLabel") or ""),
    ]
    haystacks.extend(str(value) for value in _safe_list(_safe_dict(detail.get("identity")).get("observedAliases")))
    haystacks.extend(str(value) for value in _safe_list(detail.get("representativeCommands")))
    return any(token in _normalize_token(value) for value in haystacks if str(value).strip())


async def _load_registry_details(db: Any, project: Any) -> list[dict[str, Any]]:
    project_id = str(getattr(project, "id", "") or "")
    intelligence_repo = get_agentic_intelligence_repository(db)
    session_repo = get_session_repository(db)

    definitions = normalize_definitions_for_project(
        await intelligence_repo.list_external_definitions(project_id, limit=_MAX_REGISTRY_SCAN, offset=0),
        project,
    )
    definitions_by_key, workflow_index, command_index, workflows, command_artifacts, bundles = _build_definition_indexes(definitions)

    observations = await intelligence_repo.list_stack_observations(project_id, limit=_MAX_REGISTRY_SCAN, offset=0)
    hydrated_observations: list[dict[str, Any]] = []
    for observation in observations:
        hydrated = canonicalize_stack_observation(dict(observation))
        observation_id = _safe_int(hydrated.get("id"), 0)
        hydrated["components"] = await intelligence_repo.list_stack_components(observation_id) if observation_id else []
        hydrated_observations.append(hydrated)

    session_rows = await session_repo.list_paginated(
        0,
        _MAX_REGISTRY_SCAN,
        project_id,
        "started_at",
        "desc",
        {"include_subagents": True},
    )
    sessions_by_id = {str(row.get("id") or ""): row for row in session_rows}

    rollup_rows = await intelligence_repo.list_effectiveness_rollups(
        project_id,
        period="all",
        limit=_MAX_REGISTRY_SCAN,
        offset=0,
    )
    rollups_by_scope: dict[tuple[str, str], dict[str, Any]] = {}
    for rollup in rollup_rows:
        key = (str(rollup.get("scope_type") or ""), str(rollup.get("scope_id") or ""))
        current = rollups_by_scope.get(key)
        if current is None:
            rollups_by_scope[key] = rollup
            continue
        current_metrics = _safe_dict(current.get("metrics_json"))
        next_metrics = _safe_dict(rollup.get("metrics_json"))
        if _safe_int(next_metrics.get("sampleSize"), 0) > _safe_int(current_metrics.get("sampleSize"), 0):
            rollups_by_scope[key] = rollup

    entities: dict[str, dict[str, Any]] = {}
    attached_workflow_ids: set[str] = set()
    attached_command_ids: set[str] = set()

    for observation in hydrated_observations:
        workflow_definition = _workflow_definition_for_observation(
            observation,
            definitions_by_key=definitions_by_key,
            workflow_index=workflow_index,
        )
        command_definition = _command_definition_for_observation(
            observation,
            definitions_by_key=definitions_by_key,
            command_index=command_index,
        )

        workflow_key = _registry_id(workflow_definition=workflow_definition)
        command_key = _registry_id(command_definition=command_definition) if command_definition else ""
        observed_ref = str(observation.get("workflow_ref") or observation.get("workflowRef") or "").strip()
        primary_key = workflow_key if workflow_definition else command_key or _registry_id(observed_ref=observed_ref)
        entity = entities.get(primary_key)
        if entity is None:
            entity = _empty_entity(primary_key)
            entities[primary_key] = entity

        entity["workflowDefinition"] = entity.get("workflowDefinition") or workflow_definition
        entity["commandArtifactDefinition"] = entity.get("commandArtifactDefinition") or command_definition
        entity["observations"].append(observation)
        if observed_ref:
            entity["observedRefs"].append(observed_ref)
        evidence = _safe_dict(observation.get("evidence_json") or observation.get("evidence"))
        entity["commands"] = _dedupe_strings(
            list(entity.get("commands", []))
            + [str(command) for command in _safe_list(evidence.get("commands")) if str(command).strip()]
        )
        if workflow_definition:
            attached_workflow_ids.add(str(workflow_definition.get("external_id") or ""))
        if command_definition:
            attached_command_ids.add(str(command_definition.get("external_id") or ""))

        if workflow_definition and command_key and command_key in entities and command_key != primary_key:
            entity = _merge_entities(entity, entities.pop(command_key))
            entities[primary_key] = entity

    for definition in workflows:
        external_id = str(definition.get("external_id") or "")
        if external_id in attached_workflow_ids:
            continue
        key = _registry_id(workflow_definition=definition)
        entity = entities.setdefault(key, _empty_entity(key))
        entity["workflowDefinition"] = definition

    for definition in command_artifacts:
        external_id = str(definition.get("external_id") or "")
        if external_id in attached_command_ids:
            continue
        key = _registry_id(command_definition=definition)
        entity = entities.setdefault(key, _empty_entity(key))
        entity["commandArtifactDefinition"] = definition

    details = [
        _registry_detail(
            entity,
            bundles=bundles,
            rollups_by_scope=rollups_by_scope,
            sessions_by_id=sessions_by_id,
        )
        for entity in entities.values()
    ]
    details.sort(
        key=lambda item: (
            -_safe_int(item.get("sampleSize"), 0),
            -(_parse_iso(str(item.get("lastObservedAt") or "")) or datetime.min.replace(tzinfo=timezone.utc)).timestamp(),
            _normalize_token(str(_safe_dict(item.get("identity")).get("displayLabel") or "")),
        )
    )
    return details


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
    details = await _load_registry_details(db, project)
    if search:
        details = [detail for detail in details if _matches_search(detail, search)]
    correlation_counts = {
        "strong": 0,
        "hybrid": 0,
        "weak": 0,
        "unresolved": 0,
    }
    for detail in details:
        state = str(detail.get("correlationState") or "unresolved")
        if state in correlation_counts:
            correlation_counts[state] += 1
    if correlation_state:
        details = [
            detail for detail in details
            if str(detail.get("correlationState") or "") == str(correlation_state)
        ]
    items = [_registry_item(detail) for detail in details]
    total = len(items)
    return {
        "projectId": project_id,
        "items": items[offset : offset + limit],
        "correlationCounts": correlation_counts,
        "total": total,
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
    details = await _load_registry_details(db, project)
    for detail in details:
        if str(detail.get("id") or "") == registry_id:
            return detail
    return None
