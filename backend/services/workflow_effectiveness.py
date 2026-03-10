"""Effectiveness scoring and failure-pattern analytics for agentic workflows."""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from statistics import median
from typing import Any

from backend.db.factory import (
    get_agentic_intelligence_repository,
    get_session_repository,
    get_test_integrity_repository,
    get_test_run_repository,
)
from backend.services.session_usage_analytics import get_session_scope_attribution_metrics


_FINAL_SESSION_STATUSES = {"completed", "done", "succeeded"}
_RISKY_DEBUG_TOKENS = ("debug", "fix", "investigate", "triage")
_SEVERITY_WEIGHTS = {"low": 1.0, "medium": 2.0, "high": 3.0}
_MAX_SESSION_SCAN = 5000
_MAX_REPRESENTATIVE_SESSIONS = 5

METRIC_DEFINITIONS: list[dict[str, Any]] = [
    {
        "id": "successScore",
        "label": "Success",
        "description": "How often this scope reaches a clean outcome without immediate follow-on rework.",
        "formula": "0.45*outcome + 0.35*test_pass_ratio + 0.20*resolution_score - retry_penalty",
        "inputs": ["session.status", "test_runs", "stack_resolution", "later_feature_sessions"],
    },
    {
        "id": "efficiencyScore",
        "label": "Efficiency",
        "description": "Relative runtime efficiency against the project's observed median cost, token, duration, and coordination pressure.",
        "formula": "0.25*duration_eff + 0.25*token_eff + 0.20*cost_eff + 0.15*queue_eff + 0.15*subagent_eff",
        "inputs": ["session.duration_seconds", "session.tokens", "session.total_cost", "forensics.queuePressure", "forensics.subagentTopology"],
    },
    {
        "id": "qualityScore",
        "label": "Quality",
        "description": "Evidence-backed implementation quality from tests, integrity signals, observed stack resolution, and explicit quality ratings.",
        "formula": "0.30*quality_rating + 0.35*test_pass_ratio + 0.20*integrity_score + 0.15*resolution_score",
        "inputs": ["session.quality_rating", "test_runs", "test_integrity_signals", "stack_resolution"],
    },
    {
        "id": "riskScore",
        "label": "Risk",
        "description": "Probability that the scope will require rework based on retries, debug loops, missing validation, integrity issues, and queue pressure.",
        "formula": "0.25*retry_risk + 0.20*debug_risk + 0.20*validation_risk + 0.20*integrity_risk + 0.15*queue_risk",
        "inputs": ["later_feature_sessions", "command_history", "test_runs", "test_integrity_signals", "forensics.queuePressure"],
    },
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


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


def _definition_metadata(definition: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(definition, dict):
        return {}
    metadata = definition.get("resolution_metadata_json")
    if isinstance(metadata, dict):
        return metadata
    metadata = definition.get("resolution_metadata")
    return metadata if isinstance(metadata, dict) else {}


def _normalize_ref_token(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _definition_for_component(
    component: dict[str, Any],
    definition_by_id: dict[int, dict[str, Any]],
    definition_by_key: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any] | None:
    definition_id = _safe_int(component.get("external_definition_id"), 0)
    if definition_id and definition_id in definition_by_id:
        return definition_by_id[definition_id]
    definition_type = str(component.get("external_definition_type") or "").strip()
    external_id = str(component.get("external_definition_external_id") or "").strip()
    if definition_type and external_id:
        return definition_by_key.get((definition_type, external_id))
    return None


def _artifact_refs_from_definition(definition: dict[str, Any] | None) -> set[str]:
    if not isinstance(definition, dict):
        return set()
    metadata = _definition_metadata(definition)
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
    observation: dict[str, Any],
    definition_by_id: dict[int, dict[str, Any]],
    definition_by_key: dict[tuple[str, str], dict[str, Any]],
) -> tuple[set[str], dict[str, Any] | None]:
    workflow_definition: dict[str, Any] | None = None
    refs: set[str] = set()
    for component in _safe_list(observation.get("components")):
        component_type = str(component.get("component_type") or "").strip()
        definition = _definition_for_component(component, definition_by_id, definition_by_key)
        if component_type == "workflow" and definition and workflow_definition is None:
            workflow_definition = definition
        if component_type in {"artifact", "skill"}:
            refs.update(_artifact_refs_from_definition(definition))
            component_key = str(component.get("component_key") or "").strip()
            if definition is None and component_type == "skill" and component_key:
                refs.add(_normalize_ref_token(f"skill:{component_key}"))
    workflow_metadata = _definition_metadata(workflow_definition)
    swdl_summary = workflow_metadata.get("swdlSummary")
    if isinstance(swdl_summary, dict):
        refs.update(_normalize_ref_token(str(value)) for value in _safe_list(swdl_summary.get("artifactRefs")) if str(value).strip())
    return ({ref for ref in refs if ref}, workflow_definition)


def _best_bundle_scope(
    observation: dict[str, Any],
    definitions: list[dict[str, Any]],
    definition_by_id: dict[int, dict[str, Any]],
    definition_by_key: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    stack_refs, workflow_definition = _stack_artifact_refs(observation, definition_by_id, definition_by_key)
    best_bundle_id = ""
    best_bundle_label = ""
    best_score = 0.0
    if not stack_refs:
        return {"bundleId": "", "bundleLabel": "", "effectiveWorkflowId": "", "effectiveWorkflowLabel": ""}

    for definition in definitions:
        if str(definition.get("definition_type") or "") != "bundle":
            continue
        metadata = _definition_metadata(definition)
        bundle_summary = metadata.get("bundleSummary")
        bundle_refs = _safe_list(bundle_summary.get("artifactRefs")) if isinstance(bundle_summary, dict) else []
        normalized_bundle_refs = {_normalize_ref_token(str(value)) for value in bundle_refs if str(value).strip()}
        if not normalized_bundle_refs:
            continue
        matched = stack_refs & normalized_bundle_refs
        if not matched:
            continue
        score = 0.65 * (len(matched) / max(1, len(normalized_bundle_refs))) + 0.35 * (len(matched) / max(1, len(stack_refs)))
        if score > best_score:
            best_score = score
            best_bundle_id = str(definition.get("external_id") or "")
            best_bundle_label = str(definition.get("display_name") or best_bundle_id)

    workflow_metadata = _definition_metadata(workflow_definition)
    effective_workflow = _safe_dict(workflow_metadata.get("effectiveWorkflow"))
    effective_workflow_id = str(workflow_metadata.get("effectiveWorkflowId") or effective_workflow.get("id") or "")
    effective_workflow_label = str(workflow_metadata.get("effectiveWorkflowName") or effective_workflow.get("name") or effective_workflow_id)
    if not effective_workflow_id and workflow_definition is not None:
        effective_workflow_id = str(workflow_definition.get("external_id") or "")
        effective_workflow_label = str(workflow_definition.get("display_name") or effective_workflow_id)

    return {
        "bundleId": best_bundle_id if best_score >= 0.34 else "",
        "bundleLabel": best_bundle_label if best_score >= 0.34 else "",
        "effectiveWorkflowId": effective_workflow_id,
        "effectiveWorkflowLabel": effective_workflow_label,
    }


def _median_or_zero(values: list[float]) -> float:
    usable = [value for value in values if value > 0]
    return float(median(usable)) if usable else 0.0


def _relative_efficiency(value: float, baseline: float) -> float:
    if value <= 0:
        return 1.0
    if baseline <= 0:
        return 0.75
    if value <= baseline:
        return 1.0
    return _clamp(baseline / value)


def _severity_points(signals: list[dict[str, Any]]) -> float:
    total = 0.0
    for signal in signals:
        total += _SEVERITY_WEIGHTS.get(str(signal.get("severity") or "medium").lower(), 2.0)
    return total


def _queue_operation_count(forensics: dict[str, Any]) -> int:
    queue_pressure = _safe_dict(forensics.get("queuePressure"))
    operation_counts = _safe_dict(queue_pressure.get("operationCounts"))
    if operation_counts:
        return sum(_safe_int(value, 0) for value in operation_counts.values())
    return max(
        _safe_int(queue_pressure.get("queueOperationCount"), 0),
        _safe_int(queue_pressure.get("waitingForTaskCount"), 0),
    )


def _subagent_start_count(forensics: dict[str, Any]) -> int:
    topology = _safe_dict(forensics.get("subagentTopology"))
    return _safe_int(topology.get("subagentStartCount"), 0)


def _session_workload_tokens(row: dict[str, Any]) -> float:
    observed_tokens = _safe_float(row.get("observed_tokens"), 0.0)
    if observed_tokens > 0:
        return observed_tokens
    return _safe_float(row.get("tokens_in"), 0.0) + _safe_float(row.get("tokens_out"), 0.0)


def _quality_rating_score(row: dict[str, Any]) -> float:
    rating = _safe_int(row.get("quality_rating"), 0)
    if rating <= 0:
        return 0.5
    return _clamp(rating / 5.0)


def _resolution_score(observation: dict[str, Any]) -> float:
    components = _safe_list(observation.get("components"))
    if not components:
        return _clamp(_safe_float(observation.get("confidence"), 0.0))
    resolved = 0
    for component in components:
        status = str(component.get("status") or "").lower()
        if status == "resolved":
            resolved += 1
    return _clamp(resolved / max(1, len(components)))


def _period_bucket(ts: datetime | None, period: str) -> str:
    if period == "all":
        return "all"
    if ts is None:
        return f"{period}:unknown"
    if period == "daily":
        return f"daily:{ts.date().isoformat()}"
    week_start = (ts - timedelta(days=ts.weekday())).date().isoformat()
    return f"weekly:{week_start}"


def _looks_like_debug(commands: list[str], workflow_ref: str) -> bool:
    joined = " ".join(commands).lower()
    workflow = workflow_ref.lower()
    return any(token in joined or token in workflow for token in _RISKY_DEBUG_TOKENS)


def _derive_test_ratio(test_runs: list[dict[str, Any]], forensics: dict[str, Any]) -> tuple[int, float]:
    total_tests = sum(_safe_int(row.get("total_tests"), 0) for row in test_runs)
    passed_tests = sum(_safe_int(row.get("passed_tests"), 0) for row in test_runs)
    if total_tests > 0:
        return len(test_runs), _clamp(passed_tests / total_tests)

    test_execution = _safe_dict(forensics.get("testExecution"))
    result_counts = _safe_dict(test_execution.get("resultCounts"))
    if result_counts:
        total = sum(_safe_int(value, 0) for value in result_counts.values())
        passed = _safe_int(result_counts.get("passed"), 0)
        if total > 0:
            run_count = max(len(test_runs), _safe_int(test_execution.get("runCount"), 0))
            return run_count, _clamp(passed / total)

    status_counts = _safe_dict(_safe_dict(forensics.get("testExecution")).get("statusCounts"))
    if status_counts:
        total = sum(_safe_int(value, 0) for value in status_counts.values())
        passed = _safe_int(status_counts.get("passed"), 0)
        if total > 0:
            run_count = max(len(test_runs), _safe_int(_safe_dict(forensics.get("testExecution")).get("runCount"), 0))
            return run_count, _clamp(passed / total)

    return max(len(test_runs), _safe_int(_safe_dict(forensics.get("testExecution")).get("runCount"), 0)), 0.0


def _scope_label(scope_type: str, scope_id: str) -> str:
    if scope_type == "stack":
        return scope_id.replace("|", " / ")
    return scope_id


def _stack_scope_id(observation: dict[str, Any]) -> str:
    workflow_ref = str(observation.get("workflow_ref") or "unassigned").strip() or "unassigned"
    components = _safe_list(observation.get("components"))
    agents = sorted({
        str(component.get("component_key") or "")
        for component in components
        if str(component.get("component_type") or "") == "agent" and str(component.get("component_key") or "").strip()
    })
    skills = sorted({
        str(component.get("component_key") or "")
        for component in components
        if str(component.get("component_type") or "") == "skill" and str(component.get("component_key") or "").strip()
    })
    contexts = sorted({
        str(component.get("component_key") or "")
        for component in components
        if (
            str(component.get("component_type") or "") == "context_module"
            or str(component.get("external_definition_type") or "") == "context_module"
        )
        and str(component.get("component_key") or "").strip()
    })
    return "|".join(
        [
            workflow_ref,
            f"agents:{','.join(agents[:3]) or 'none'}",
            f"skills:{','.join(skills[:3]) or 'none'}",
            f"contexts:{','.join(contexts[:3]) or 'none'}",
        ]
    )


def _scope_keys(
    observation: dict[str, Any],
    *,
    extra_scopes: list[tuple[str, str]] | None = None,
) -> list[tuple[str, str]]:
    keys: list[tuple[str, str]] = []
    workflow_ref = str(observation.get("workflow_ref") or "").strip()
    if workflow_ref:
        keys.append(("workflow", workflow_ref))

    components = _safe_list(observation.get("components"))
    for component in components:
        component_type = str(component.get("component_type") or "")
        component_key = str(component.get("component_key") or "").strip()
        if component_type in {"agent", "skill"} and component_key:
            keys.append((component_type, component_key))
        if (
            component_key
            and (
                component_type == "context_module"
                or str(component.get("external_definition_type") or "") == "context_module"
            )
        ):
            keys.append(("context_module", component_key))

    keys.append(("stack", _stack_scope_id(observation)))
    for scope_type, scope_id in extra_scopes or []:
        if scope_type and scope_id:
            keys.append((scope_type, scope_id))
    deduped: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in keys:
        if item in seen:
            continue
        deduped.append(item)
        seen.add(item)
    return deduped


def _session_outcome_score(row: dict[str, Any]) -> float:
    status = str(row.get("status") or "").strip().lower()
    if status in _FINAL_SESSION_STATUSES:
        return 1.0
    if status in {"review", "running"}:
        return 0.55
    if status in {"failed", "blocked", "canceled"}:
        return 0.15
    return 0.35


def _hydrate_rollup(row: dict[str, Any]) -> dict[str, Any]:
    metrics = _safe_dict(row.get("metrics_json"))
    evidence = _safe_dict(row.get("evidence_summary_json"))
    return {
        "id": row.get("id"),
        "projectId": str(row.get("project_id") or ""),
        "scopeType": str(row.get("scope_type") or ""),
        "scopeId": str(row.get("scope_id") or ""),
        "scopeLabel": str(metrics.get("scopeLabel") or _scope_label(str(row.get("scope_type") or ""), str(row.get("scope_id") or ""))),
        "period": str(row.get("period") or "all"),
        "sampleSize": _safe_int(metrics.get("sampleSize"), 0),
        "successScore": round(_safe_float(metrics.get("successScore"), 0.0), 4),
        "efficiencyScore": round(_safe_float(metrics.get("efficiencyScore"), 0.0), 4),
        "qualityScore": round(_safe_float(metrics.get("qualityScore"), 0.0), 4),
        "riskScore": round(_safe_float(metrics.get("riskScore"), 0.0), 4),
        "attributedTokens": _safe_int(metrics.get("attributedTokens"), 0),
        "supportingAttributionTokens": _safe_int(metrics.get("supportingAttributionTokens"), 0),
        "attributedCostUsdModelIO": round(_safe_float(metrics.get("attributedCostUsdModelIO"), 0.0), 6),
        "averageAttributionConfidence": round(_safe_float(metrics.get("averageAttributionConfidence"), 0.0), 4),
        "attributionCoverage": round(_safe_float(metrics.get("attributionCoverage"), 0.0), 4),
        "attributionCacheShare": round(_safe_float(metrics.get("attributionCacheShare"), 0.0), 4),
        "evidenceSummary": evidence,
        "generatedAt": str(metrics.get("generatedAt") or ""),
        "createdAt": str(row.get("created_at") or ""),
        "updatedAt": str(row.get("updated_at") or ""),
    }


async def _load_hydrated_observations(repo: Any, project_id: str, feature_id: str | None) -> list[dict[str, Any]]:
    observations = await repo.list_stack_observations(
        project_id,
        feature_id=feature_id,
        limit=_MAX_SESSION_SCAN,
        offset=0,
    )
    hydrated: list[dict[str, Any]] = []
    for observation in observations:
        session_id = str(observation.get("session_id") or "")
        if not session_id:
            continue
        full_observation = await repo.get_stack_observation(project_id, session_id)
        if full_observation:
            hydrated.append(full_observation)
    return hydrated


async def _collect_effectiveness_dataset(
    db: Any,
    project: Any,
    *,
    feature_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> list[dict[str, Any]]:
    project_id = str(getattr(project, "id", "") or "")
    intelligence_repo = get_agentic_intelligence_repository(db)
    session_repo = get_session_repository(db)
    test_run_repo = get_test_run_repository(db)
    integrity_repo = get_test_integrity_repository(db)
    definitions = await intelligence_repo.list_external_definitions(project_id, limit=5000, offset=0)
    definition_by_id: dict[int, dict[str, Any]] = {}
    definition_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for definition in definitions:
        definition_id = _safe_int(definition.get("id"), 0)
        if definition_id:
            definition_by_id[definition_id] = definition
        definition_type = str(definition.get("definition_type") or "").strip()
        external_id = str(definition.get("external_id") or "").strip()
        if definition_type and external_id:
            definition_by_key[(definition_type, external_id)] = definition

    session_filters: dict[str, Any] = {"include_subagents": True}
    if start:
        session_filters["start_date"] = start
    if end:
        session_filters["end_date"] = end

    session_rows = await session_repo.list_paginated(
        0,
        _MAX_SESSION_SCAN,
        project_id,
        "started_at",
        "desc",
        session_filters,
    )
    observations = await _load_hydrated_observations(intelligence_repo, project_id, feature_id)
    observation_by_session = {
        str(observation.get("session_id") or ""): observation
        for observation in observations
        if str(observation.get("session_id") or "").strip()
    }

    filtered_sessions: list[dict[str, Any]] = []
    for row in session_rows:
        session_id = str(row.get("id") or "")
        if not session_id or session_id not in observation_by_session:
            continue
        if feature_id and str(row.get("task_id") or observation_by_session[session_id].get("feature_id") or "") != feature_id:
            continue
        filtered_sessions.append(row)

    filtered_session_ids = {str(row.get("id") or "") for row in filtered_sessions}
    test_runs = await test_run_repo.list_by_project(project_id, limit=_MAX_SESSION_SCAN, offset=0)
    test_runs_by_session: dict[str, list[dict[str, Any]]] = {}
    for test_run in test_runs:
        session_id = str(test_run.get("agent_session_id") or "")
        if session_id and session_id in filtered_session_ids:
            test_runs_by_session.setdefault(session_id, []).append(test_run)

    integrity_signals, _ = await integrity_repo.list_filtered(
        project_id=project_id,
        since=start,
        limit=_MAX_SESSION_SCAN,
        offset=0,
    )
    integrity_by_session: dict[str, list[dict[str, Any]]] = {}
    for signal in integrity_signals:
        session_id = str(signal.get("agent_session_id") or "")
        if session_id and session_id in filtered_session_ids:
            integrity_by_session.setdefault(session_id, []).append(signal)

    feature_timeline: dict[str, list[dict[str, Any]]] = {}
    for row in filtered_sessions:
        feature_key = str(row.get("task_id") or observation_by_session[str(row.get("id") or "")].get("feature_id") or "").strip()
        if not feature_key:
            continue
        feature_timeline.setdefault(feature_key, []).append(row)
    for rows in feature_timeline.values():
        rows.sort(key=lambda item: _parse_iso(str(item.get("started_at") or item.get("created_at") or "")) or datetime.min.replace(tzinfo=timezone.utc))

    baseline_durations = [_safe_float(row.get("duration_seconds"), 0.0) for row in filtered_sessions]
    baseline_tokens = [_session_workload_tokens(row) for row in filtered_sessions]
    baseline_costs = [_safe_float(row.get("total_cost"), 0.0) for row in filtered_sessions]
    baseline_queue = [
        _queue_operation_count(_safe_dict(row.get("session_forensics_json")))
        for row in filtered_sessions
    ]
    baseline_subagents = [
        _subagent_start_count(_safe_dict(row.get("session_forensics_json")))
        for row in filtered_sessions
    ]

    duration_baseline = _median_or_zero(baseline_durations)
    token_baseline = _median_or_zero(baseline_tokens)
    cost_baseline = _median_or_zero(baseline_costs)
    queue_baseline = _median_or_zero([float(value) for value in baseline_queue])
    subagent_baseline = _median_or_zero([float(value) for value in baseline_subagents])

    dataset: list[dict[str, Any]] = []
    for row in filtered_sessions:
        session_id = str(row.get("id") or "")
        observation = observation_by_session.get(session_id)
        if not observation:
            continue

        forensics = _safe_dict(row.get("session_forensics_json"))
        commands = [str(command) for command in _safe_list(_safe_dict(observation.get("evidence_json")).get("commands")) if str(command).strip()]
        workflow_ref = str(observation.get("workflow_ref") or "")
        feature_key = str(row.get("task_id") or observation.get("feature_id") or "").strip()
        session_list = feature_timeline.get(feature_key, [])
        session_index = next((idx for idx, item in enumerate(session_list) if str(item.get("id") or "") == session_id), -1)
        later_sessions = session_list[session_index + 1 :] if session_index >= 0 else []
        later_debug_count = 0
        for later_row in later_sessions:
            later_observation = observation_by_session.get(str(later_row.get("id") or ""))
            if not later_observation:
                continue
            later_commands = [
                str(command)
                for command in _safe_list(_safe_dict(later_observation.get("evidence_json")).get("commands"))
                if str(command).strip()
            ]
            if _looks_like_debug(later_commands, str(later_observation.get("workflow_ref") or "")):
                later_debug_count += 1

        test_run_rows = test_runs_by_session.get(session_id, [])
        test_run_count, test_pass_ratio = _derive_test_ratio(test_run_rows, forensics)
        integrity_rows = integrity_by_session.get(session_id, [])
        severity_points = _severity_points(integrity_rows)
        resolution_score = _resolution_score(observation)
        scope_alignment = _best_bundle_scope(
            observation,
            definitions,
            definition_by_id,
            definition_by_key,
        )
        queue_ops = _queue_operation_count(forensics)
        subagent_starts = _subagent_start_count(forensics)
        total_tokens = _session_workload_tokens(row)
        retry_penalty = min(0.35, len(later_sessions) * 0.08 + later_debug_count * 0.12)

        success_score = _clamp(
            0.45 * _session_outcome_score(row)
            + 0.35 * test_pass_ratio
            + 0.20 * resolution_score
            - retry_penalty
        )
        efficiency_score = _clamp(
            0.25 * _relative_efficiency(_safe_float(row.get("duration_seconds"), 0.0), duration_baseline)
            + 0.25 * _relative_efficiency(total_tokens, token_baseline)
            + 0.20 * _relative_efficiency(_safe_float(row.get("total_cost"), 0.0), cost_baseline)
            + 0.15 * (1.0 - _clamp(queue_ops / max(1.0, queue_baseline * 2 or 1.0)))
            + 0.15 * (1.0 - _clamp(subagent_starts / max(1.0, subagent_baseline * 2 + 1.0)))
        )
        quality_score = _clamp(
            0.30 * _quality_rating_score(row)
            + 0.35 * test_pass_ratio
            + 0.20 * (1.0 - _clamp(severity_points / 6.0))
            + 0.15 * resolution_score
        )
        risk_score = _clamp(
            0.25 * _clamp(len(later_sessions) / 4.0)
            + 0.20 * _clamp(later_debug_count / 3.0)
            + 0.20 * (1.0 if test_run_count == 0 else 1.0 - test_pass_ratio)
            + 0.20 * _clamp(severity_points / 6.0)
            + 0.15 * _clamp(queue_ops / max(1.0, queue_baseline * 2 or 1.0))
        )

        dataset.append(
            {
                "sessionId": session_id,
                "featureId": feature_key,
                "startedAt": str(row.get("started_at") or row.get("created_at") or ""),
                "workflowRef": workflow_ref,
                "commands": commands,
                "isDebugLike": _looks_like_debug(commands, workflow_ref),
                "queueOps": queue_ops,
                "subagentStarts": subagent_starts,
                "testRunCount": test_run_count,
                "testPassRatio": round(test_pass_ratio, 4),
                "laterSessionCount": len(later_sessions),
                "laterDebugCount": later_debug_count,
                "resolutionScore": round(resolution_score, 4),
                "integritySignalCount": len(integrity_rows),
                "integritySeverityPoints": round(severity_points, 4),
                "successScore": round(success_score, 4),
                "efficiencyScore": round(efficiency_score, 4),
                "qualityScore": round(quality_score, 4),
                "riskScore": round(risk_score, 4),
                "observation": observation,
                "effectiveWorkflowScopeId": str(scope_alignment.get("effectiveWorkflowId") or ""),
                "bundleScopeId": str(scope_alignment.get("bundleId") or ""),
                "scopeLabels": {
                    "effective_workflow": str(scope_alignment.get("effectiveWorkflowLabel") or ""),
                    "bundle": str(scope_alignment.get("bundleLabel") or ""),
                },
            }
        )
    return dataset


def _aggregate_rollups(
    dataset: list[dict[str, Any]],
    scope_metrics: dict[tuple[str, str, str], dict[str, Any]],
    *,
    period: str,
    scope_type: str | None = None,
    scope_id: str | None = None,
) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str, str], dict[str, Any]] = {}
    generated_at = _now_iso()
    for item in dataset:
        observation = _safe_dict(item.get("observation"))
        period_key = _period_bucket(_parse_iso(str(item.get("startedAt") or "")), period)
        extra_scopes = [
            ("effective_workflow", str(item.get("effectiveWorkflowScopeId") or "")),
            ("bundle", str(item.get("bundleScopeId") or "")),
        ]
        scope_labels = _safe_dict(item.get("scopeLabels"))
        for candidate_scope_type, candidate_scope_id in _scope_keys(observation, extra_scopes=extra_scopes):
            if scope_type and candidate_scope_type != scope_type:
                continue
            if scope_id and candidate_scope_id != scope_id:
                continue
            bucket_key = (candidate_scope_type, candidate_scope_id, period_key)
            bucket = buckets.setdefault(
                bucket_key,
                {
                    "projectId": str(observation.get("project_id") or ""),
                    "scopeType": candidate_scope_type,
                    "scopeId": candidate_scope_id,
                    "scopeLabel": str(scope_labels.get(candidate_scope_type) or _scope_label(candidate_scope_type, candidate_scope_id)),
                    "period": period_key,
                    "sampleSize": 0,
                    "successTotal": 0.0,
                    "efficiencyTotal": 0.0,
                    "qualityTotal": 0.0,
                    "riskTotal": 0.0,
                    "attributedTokens": 0,
                    "supportingAttributionTokens": 0,
                    "attributedCostUsdModelIO": 0.0,
                    "attributionConfidenceTotal": 0.0,
                    "attributionConfidenceCount": 0,
                    "attributionCoverageTotal": 0.0,
                    "attributionCacheShareTotal": 0.0,
                    "sessionIds": [],
                    "featureIds": set(),
                    "queueOpsTotal": 0,
                    "laterDebugTotal": 0,
                    "avgTestPassTotal": 0.0,
                    "generatedAt": generated_at,
                },
            )
            bucket["sampleSize"] += 1
            bucket["successTotal"] += _safe_float(item.get("successScore"), 0.0)
            bucket["efficiencyTotal"] += _safe_float(item.get("efficiencyScore"), 0.0)
            bucket["qualityTotal"] += _safe_float(item.get("qualityScore"), 0.0)
            bucket["riskTotal"] += _safe_float(item.get("riskScore"), 0.0)
            bucket["queueOpsTotal"] += _safe_int(item.get("queueOps"), 0)
            bucket["laterDebugTotal"] += _safe_int(item.get("laterDebugCount"), 0)
            bucket["avgTestPassTotal"] += _safe_float(item.get("testPassRatio"), 0.0)
            bucket["sessionIds"].append(str(item.get("sessionId") or ""))
            if str(item.get("featureId") or "").strip():
                bucket["featureIds"].add(str(item.get("featureId") or ""))
            attribution_metrics = scope_metrics.get((str(item.get("sessionId") or ""), candidate_scope_type, candidate_scope_id), {})
            if attribution_metrics:
                bucket["attributedTokens"] += _safe_int(attribution_metrics.get("exclusiveTokens"), 0)
                bucket["supportingAttributionTokens"] += _safe_int(attribution_metrics.get("supportingTokens"), 0)
                bucket["attributedCostUsdModelIO"] += _safe_float(attribution_metrics.get("exclusiveCostUsdModelIO"), 0.0)
                bucket["attributionCoverageTotal"] += _safe_float(attribution_metrics.get("attributionCoverage"), 0.0)
                bucket["attributionCacheShareTotal"] += _safe_float(attribution_metrics.get("attributionCacheShare"), 0.0)
                bucket["attributionConfidenceTotal"] += _safe_float(attribution_metrics.get("averageConfidence"), 0.0)
                bucket["attributionConfidenceCount"] += 1

    items: list[dict[str, Any]] = []
    for bucket in buckets.values():
        sample_size = max(1, int(bucket["sampleSize"]))
        items.append(
            {
                "projectId": bucket["projectId"],
                "scopeType": bucket["scopeType"],
                "scopeId": bucket["scopeId"],
                "scopeLabel": bucket["scopeLabel"],
                "period": bucket["period"],
                "sampleSize": sample_size,
                "successScore": round(bucket["successTotal"] / sample_size, 4),
                "efficiencyScore": round(bucket["efficiencyTotal"] / sample_size, 4),
                "qualityScore": round(bucket["qualityTotal"] / sample_size, 4),
                "riskScore": round(bucket["riskTotal"] / sample_size, 4),
                "attributedTokens": bucket["attributedTokens"],
                "supportingAttributionTokens": bucket["supportingAttributionTokens"],
                "attributedCostUsdModelIO": round(bucket["attributedCostUsdModelIO"], 6),
                "averageAttributionConfidence": round(
                    bucket["attributionConfidenceTotal"] / max(1, bucket["attributionConfidenceCount"]),
                    4,
                ),
                "attributionCoverage": round(bucket["attributionCoverageTotal"] / sample_size, 4),
                "attributionCacheShare": round(bucket["attributionCacheShareTotal"] / sample_size, 4),
                "evidenceSummary": {
                    "featureIds": sorted(bucket["featureIds"]),
                    "representativeSessionIds": bucket["sessionIds"][:_MAX_REPRESENTATIVE_SESSIONS],
                    "averageQueueOperations": round(bucket["queueOpsTotal"] / sample_size, 2),
                    "averageLaterDebugSessions": round(bucket["laterDebugTotal"] / sample_size, 2),
                    "averageTestPassRatio": round(bucket["avgTestPassTotal"] / sample_size, 4),
                },
                "generatedAt": bucket["generatedAt"],
            }
        )

    items.sort(key=lambda row: (-_safe_int(row.get("sampleSize"), 0), -_safe_float(row.get("successScore"), 0.0), str(row.get("scopeType") or ""), str(row.get("scopeId") or ""), str(row.get("period") or "")))
    return items


async def get_workflow_effectiveness(
    db: Any,
    project: Any,
    *,
    period: str = "all",
    scope_type: str | None = None,
    scope_id: str | None = None,
    feature_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
    limit: int = 100,
    offset: int = 0,
    recompute: bool = False,
) -> dict[str, Any]:
    project_id = str(getattr(project, "id", "") or "")
    intelligence_repo = get_agentic_intelligence_repository(db)

    use_cache = not recompute and not feature_id and not start and not end
    if use_cache:
        cached_rows = await intelligence_repo.list_effectiveness_rollups(
            project_id,
            scope_type=scope_type,
            scope_id=scope_id,
            period=period,
            limit=max(limit, 500),
            offset=0,
        )
        if cached_rows:
            hydrated = [_hydrate_rollup(row) for row in cached_rows]
            total = len(hydrated)
            return {
                "projectId": project_id,
                "period": period,
                "metricDefinitions": METRIC_DEFINITIONS,
                "items": hydrated[offset : offset + limit],
                "total": total,
                "offset": offset,
                "limit": limit,
                "generatedAt": _now_iso(),
            }

    dataset = await _collect_effectiveness_dataset(
        db,
        project,
        feature_id=feature_id,
        start=start,
        end=end,
    )
    scope_metrics = await get_session_scope_attribution_metrics(
        db,
        project_id=project_id,
        session_ids=[str(item.get("sessionId") or "") for item in dataset if str(item.get("sessionId") or "").strip()],
    )
    items = _aggregate_rollups(
        dataset,
        scope_metrics,
        period=period,
        scope_type=scope_type,
        scope_id=scope_id,
    )

    if not feature_id and not start and not end:
        await intelligence_repo.purge_effectiveness_rollups(project_id, period=period)
        for item in items:
            await intelligence_repo.upsert_effectiveness_rollup(
                {
                    "project_id": project_id,
                    "scope_type": item["scopeType"],
                    "scope_id": item["scopeId"],
                    "period": item["period"],
                    "metrics": {
                        "scopeLabel": item["scopeLabel"],
                        "sampleSize": item["sampleSize"],
                        "successScore": item["successScore"],
                        "efficiencyScore": item["efficiencyScore"],
                        "qualityScore": item["qualityScore"],
                        "riskScore": item["riskScore"],
                        "attributedTokens": item["attributedTokens"],
                        "supportingAttributionTokens": item["supportingAttributionTokens"],
                        "attributedCostUsdModelIO": item["attributedCostUsdModelIO"],
                        "averageAttributionConfidence": item["averageAttributionConfidence"],
                        "attributionCoverage": item["attributionCoverage"],
                        "attributionCacheShare": item["attributionCacheShare"],
                        "generatedAt": item["generatedAt"],
                    },
                    "evidence_summary": item["evidenceSummary"],
                },
                project_id=project_id,
            )

    total = len(items)
    return {
        "projectId": project_id,
        "period": period,
        "metricDefinitions": METRIC_DEFINITIONS,
        "items": items[offset : offset + limit],
        "total": total,
        "offset": offset,
        "limit": limit,
        "generatedAt": _now_iso(),
    }


async def detect_failure_patterns(
    db: Any,
    project: Any,
    *,
    scope_type: str | None = None,
    scope_id: str | None = None,
    feature_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    dataset = await _collect_effectiveness_dataset(
        db,
        project,
        feature_id=feature_id,
        start=start,
        end=end,
    )
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in dataset:
        observation = _safe_dict(item.get("observation"))
        scopes = _scope_keys(
            observation,
            extra_scopes=[
                ("effective_workflow", str(item.get("effectiveWorkflowScopeId") or "")),
                ("bundle", str(item.get("bundleScopeId") or "")),
            ],
        )
        scoped_candidates = [
            (candidate_scope_type, candidate_scope_id)
            for candidate_scope_type, candidate_scope_id in scopes
            if (not scope_type or candidate_scope_type == scope_type)
            and (not scope_id or candidate_scope_id == scope_id)
        ]
        primary_scope_type, primary_scope_id = scoped_candidates[0] if scoped_candidates else ("workflow", str(item.get("workflowRef") or "project"))

        if _safe_int(item.get("queueOps"), 0) >= 4 and _safe_float(item.get("efficiencyScore"), 0.0) <= 0.55:
            key = ("queue_waste", primary_scope_type, primary_scope_id)
            grouped.setdefault(key, {"rows": [], "title": "Queue waste", "severity": "medium"})["rows"].append(item)
        if (_safe_int(item.get("laterDebugCount"), 0) > 0 or bool(item.get("isDebugLike"))) and _safe_float(item.get("successScore"), 0.0) <= 0.55:
            key = ("debug_loop", primary_scope_type, primary_scope_id)
            grouped.setdefault(key, {"rows": [], "title": "Repeated debug loop", "severity": "high"})["rows"].append(item)
        if _safe_int(item.get("testRunCount"), 0) == 0 and _safe_float(item.get("qualityScore"), 0.0) <= 0.55:
            key = ("weak_validation", primary_scope_type, primary_scope_id)
            grouped.setdefault(key, {"rows": [], "title": "Weak validation path", "severity": "high"})["rows"].append(item)

    items: list[dict[str, Any]] = []
    for (pattern_type, candidate_scope_type, candidate_scope_id), payload in grouped.items():
        rows = payload["rows"]
        occurrence_count = len(rows)
        avg_success = round(sum(_safe_float(row.get("successScore"), 0.0) for row in rows) / occurrence_count, 4)
        avg_risk = round(sum(_safe_float(row.get("riskScore"), 0.0) for row in rows) / occurrence_count, 4)
        avg_queue = round(sum(_safe_int(row.get("queueOps"), 0) for row in rows) / occurrence_count, 2)
        avg_debug = round(sum(_safe_int(row.get("laterDebugCount"), 0) for row in rows) / occurrence_count, 2)
        confidence = _clamp(0.45 + occurrence_count * 0.1 + avg_risk * 0.2)
        items.append(
            {
                "id": f"{pattern_type}:{candidate_scope_type}:{candidate_scope_id}",
                "patternType": pattern_type,
                "title": payload["title"],
                "scopeType": candidate_scope_type,
                "scopeId": candidate_scope_id,
                "severity": payload["severity"],
                "confidence": round(confidence, 4),
                "occurrenceCount": occurrence_count,
                "averageSuccessScore": avg_success,
                "averageRiskScore": avg_risk,
                "evidenceSummary": {
                    "representativeSessionIds": [str(row.get("sessionId") or "") for row in rows[:_MAX_REPRESENTATIVE_SESSIONS]],
                    "featureIds": sorted({str(row.get("featureId") or "") for row in rows if str(row.get("featureId") or "").strip()}),
                    "averageQueueOperations": avg_queue,
                    "averageLaterDebugSessions": avg_debug,
                    "missingValidationSessions": sum(1 for row in rows if _safe_int(row.get("testRunCount"), 0) == 0),
                },
                "sessionIds": [str(row.get("sessionId") or "") for row in rows[:_MAX_REPRESENTATIVE_SESSIONS]],
            }
        )

    items.sort(key=lambda row: (-_safe_int(row.get("occurrenceCount"), 0), -_safe_float(row.get("averageRiskScore"), 0.0), str(row.get("patternType") or ""), str(row.get("scopeId") or "")))
    project_id = str(getattr(project, "id", "") or "")
    total = len(items)
    return {
        "projectId": project_id,
        "items": items[offset : offset + limit],
        "total": total,
        "offset": offset,
        "limit": limit,
        "generatedAt": _now_iso(),
    }
