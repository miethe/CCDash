"""Helpers for contract-aligned SkillMeat definition metadata."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

import yaml


_ARTIFACT_REF_RE = re.compile(r"^(?:agent|artifact|command|skill):[A-Za-z0-9._/\-]+$")
_CTX_REF_RE = re.compile(r"^ctx:[A-Za-z0-9._/\-]+$")


@dataclass(slots=True)
class WorkflowSwdlSummary:
    artifactRefs: list[str] = field(default_factory=list)
    contextRefs: list[str] = field(default_factory=list)
    stageOrder: list[str] = field(default_factory=list)
    stageGraph: list[dict[str, Any]] = field(default_factory=list)
    gateCount: int = 0
    fanOutCount: int = 0
    parseError: str = ""


@dataclass(slots=True)
class WorkflowPlanSummary:
    batchCount: int = 0
    stageCount: int = 0
    hasGates: bool = False
    stageOrder: list[str] = field(default_factory=list)
    stageDependencies: list[dict[str, Any]] = field(default_factory=list)
    validationErrors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ContextPackPreviewSummary:
    moduleId: str = ""
    moduleName: str = ""
    itemsIncluded: int = 0
    itemsAvailable: int = 0
    totalTokens: int = 0
    budgetTokens: int = 0
    utilization: float = 0.0
    memoryTypes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class WorkflowExecutionSummary:
    executionId: str = ""
    workflowId: str = ""
    status: str = ""
    startedAt: str = ""
    completedAt: str = ""
    errorMessage: str = ""
    stepCount: int = 0
    completedStepCount: int = 0
    failedStepCount: int = 0
    runningStepCount: int = 0
    gateStepCount: int = 0


def annotate_effective_workflows(definitions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for definition in definitions:
        metadata = _definition_metadata(definition)
        workflow_name = str(metadata.get("workflowName") or definition.get("display_name") or "").strip()
        workflow_key = _slug_token(workflow_name) or str(definition.get("external_id") or "").strip()
        if not workflow_key:
            continue
        grouped.setdefault(workflow_key, []).append(definition)

    for workflow_key, candidates in grouped.items():
        effective = _effective_workflow_candidate(candidates)
        effective_id = str(effective.get("external_id") or "").strip()
        effective_name = str(_definition_metadata(effective).get("workflowName") or effective.get("display_name") or "").strip()
        for definition in candidates:
            metadata = _definition_metadata(definition)
            metadata["aliases"] = _compact_unique(
                [
                    *[str(alias) for alias in metadata.get("aliases", []) if isinstance(alias, str)],
                    workflow_key,
                    str(metadata.get("workflowName") or ""),
                    _slug_token(str(metadata.get("workflowName") or "")),
                    str(definition.get("external_id") or ""),
                ]
            )
            metadata["effectiveWorkflowKey"] = workflow_key
            metadata["effectiveWorkflowId"] = effective_id
            metadata["effectiveWorkflowName"] = effective_name
            metadata["isEffective"] = str(definition.get("external_id") or "").strip() == effective_id
            definition["resolution_metadata"] = metadata
    return definitions


def attach_workflow_detail(
    definition: dict[str, Any],
    *,
    workflow_detail: dict[str, Any] | None = None,
    workflow_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = _definition_metadata(definition)
    raw_snapshot = dict(definition.get("raw_snapshot") or {}) if isinstance(definition.get("raw_snapshot"), dict) else {}
    if workflow_detail:
        raw_snapshot = {**raw_snapshot, **workflow_detail}

    swdl_summary = extract_workflow_swdl_summary(raw_snapshot)
    plan_summary = summarize_workflow_plan(workflow_plan or {})

    metadata["rawWorkflow"] = {
        "id": str(raw_snapshot.get("id") or definition.get("external_id") or ""),
        "name": str(raw_snapshot.get("name") or definition.get("display_name") or ""),
        "scope": str(metadata.get("workflowScope") or ""),
        "projectId": str(raw_snapshot.get("project_id") or metadata.get("scopeProjectId") or ""),
    }
    metadata["effectiveWorkflow"] = {
        "key": str(metadata.get("effectiveWorkflowKey") or ""),
        "id": str(metadata.get("effectiveWorkflowId") or definition.get("external_id") or ""),
        "name": str(metadata.get("effectiveWorkflowName") or definition.get("display_name") or ""),
        "scope": str(metadata.get("workflowScope") or ""),
        "isEffective": bool(metadata.get("isEffective")),
    }
    metadata["swdlSummary"] = asdict(swdl_summary)
    metadata["planSummary"] = asdict(plan_summary)

    definition["resolution_metadata"] = metadata
    definition["raw_snapshot"] = raw_snapshot
    return definition


def attach_context_module_preview(
    definition: dict[str, Any],
    preview_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    summary = summarize_context_pack_preview(preview_payload or {}, definition=definition)
    if not summary:
        return definition
    metadata = _definition_metadata(definition)
    metadata["previewSummary"] = summary
    definition["resolution_metadata"] = metadata
    return definition


def resolve_workflow_context_modules(
    definition: dict[str, Any],
    *,
    context_modules: list[dict[str, Any]],
    preview_summaries: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    metadata = _definition_metadata(definition)
    swdl_summary = metadata.get("swdlSummary")
    context_refs = swdl_summary.get("contextRefs") if isinstance(swdl_summary, dict) else []
    if not isinstance(context_refs, list) or not context_refs:
        metadata["resolvedContextModules"] = []
        metadata["contextSummary"] = {
            "referenced": 0,
            "resolved": 0,
            "previewed": 0,
        }
        definition["resolution_metadata"] = metadata
        return definition

    preview_summaries = preview_summaries or {}
    by_alias: dict[str, dict[str, Any]] = {}
    for item in context_modules:
        item_metadata = _definition_metadata(item)
        aliases = [
            *[str(alias) for alias in item_metadata.get("aliases", []) if isinstance(alias, str)],
            str(item.get("external_id") or ""),
            str(item.get("display_name") or ""),
        ]
        for alias in aliases:
            normalized = _normalize_lookup_token(alias)
            if not normalized:
                continue
            existing = by_alias.get(normalized)
            if existing is None or _context_module_priority(item) >= _context_module_priority(existing):
                by_alias[normalized] = item

    resolved_contexts: list[dict[str, Any]] = []
    previewed = 0
    total_tokens = 0
    for raw_ref in context_refs:
        context_ref = str(raw_ref or "").strip()
        lookup_key = _normalize_lookup_token(context_ref)
        matched = by_alias.get(lookup_key)
        entry = {
            "contextRef": context_ref,
            "moduleId": "",
            "moduleName": "",
            "projectId": "",
            "status": "unresolved",
            "sourceAttribution": "no_match",
            "confidence": 0.0,
        }
        if matched:
            matched_metadata = _definition_metadata(matched)
            preview_summary = preview_summaries.get(str(matched.get("external_id") or "").strip()) or matched_metadata.get("previewSummary")
            if not isinstance(preview_summary, dict):
                preview_summary = {}
            if preview_summary:
                previewed += 1
                total_tokens += _safe_int(preview_summary.get("totalTokens"), 0)
            entry = {
                **entry,
                "moduleId": str(matched.get("external_id") or ""),
                "moduleName": str(matched.get("display_name") or ""),
                "projectId": str(matched_metadata.get("scopeProjectId") or ""),
                "status": "resolved",
                "sourceAttribution": "ctx_name_alias",
                "confidence": 0.92,
                "previewSummary": preview_summary,
                "sourceUrl": str(matched.get("source_url") or ""),
            }
        resolved_contexts.append(entry)

    metadata["resolvedContextModules"] = resolved_contexts
    metadata["contextSummary"] = {
        "referenced": len(context_refs),
        "resolved": sum(1 for item in resolved_contexts if str(item.get("status") or "") == "resolved"),
        "previewed": previewed,
        "previewTokenFootprint": total_tokens,
    }
    definition["resolution_metadata"] = metadata
    return definition


def attach_bundle_detail(definition: dict[str, Any]) -> dict[str, Any]:
    metadata = _definition_metadata(definition)
    raw_snapshot = definition.get("raw_snapshot")
    raw_snapshot = raw_snapshot if isinstance(raw_snapshot, dict) else {}
    artifact_refs = _extract_bundle_artifact_refs(raw_snapshot)
    metadata["bundleSummary"] = {
        "artifactRefs": artifact_refs,
        "dependencyCount": len([item for item in raw_snapshot.get("dependencies", []) if isinstance(item, str)]),
        "artifactCount": len(artifact_refs),
    }
    definition["resolution_metadata"] = metadata
    return definition


def attach_workflow_executions(
    definition: dict[str, Any],
    executions: list[dict[str, Any]],
) -> dict[str, Any]:
    metadata = _definition_metadata(definition)
    summaries = [asdict(summarize_workflow_execution(item)) for item in executions if isinstance(item, dict)]
    completed = sum(1 for item in summaries if str(item.get("status") or "").lower() == "completed")
    running = sum(1 for item in summaries if str(item.get("status") or "").lower() in {"running", "pending", "paused"})
    failed = sum(1 for item in summaries if str(item.get("status") or "").lower() in {"failed", "cancelled"})
    metadata["recentExecutions"] = summaries
    metadata["executionSummary"] = {
        "count": len(summaries),
        "completed": completed,
        "running": running,
        "failed": failed,
        "latestStartedAt": next((str(item.get("startedAt") or "") for item in summaries if str(item.get("startedAt") or "").strip()), ""),
    }
    definition["resolution_metadata"] = metadata
    return definition


def extract_workflow_swdl_summary(payload: dict[str, Any]) -> WorkflowSwdlSummary:
    yaml_content = str(payload.get("definition") or payload.get("yaml_content") or "").strip()
    if not yaml_content:
        return WorkflowSwdlSummary()

    try:
        parsed = yaml.safe_load(yaml_content) or {}
    except Exception as exc:
        return WorkflowSwdlSummary(parseError=str(exc))

    summary = WorkflowSwdlSummary()
    stages = parsed.get("stages")
    if isinstance(stages, list):
        _walk_stages(stages, summary)
    return _dedupe_swdl_summary(summary)


def summarize_workflow_plan(plan_payload: dict[str, Any]) -> WorkflowPlanSummary:
    if not isinstance(plan_payload, dict):
        return WorkflowPlanSummary()

    execution_order = plan_payload.get("execution_order")
    if not isinstance(execution_order, list):
        execution_order = []

    stage_order: list[str] = []
    stage_dependencies: list[dict[str, Any]] = []
    has_gates = False

    for batch in execution_order:
        if not isinstance(batch, dict):
            continue
        for stage in batch.get("stages", []):
            if not isinstance(stage, dict):
                continue
            stage_id = str(stage.get("stage_id") or "")
            stage_type = str(stage.get("stage_type") or "")
            depends_on = [str(item) for item in stage.get("depends_on", []) if isinstance(item, str)]
            if stage_id:
                stage_order.append(stage_id)
            if stage_type == "gate":
                has_gates = True
            stage_dependencies.append(
                {
                    "stageId": stage_id,
                    "stageType": stage_type,
                    "dependsOn": depends_on,
                    "batchIndex": int(batch.get("batch_index") or 0),
                }
            )

    return WorkflowPlanSummary(
        batchCount=int(plan_payload.get("estimated_batches") or len(execution_order) or 0),
        stageCount=int(plan_payload.get("estimated_stages") or len(stage_dependencies) or 0),
        hasGates=bool(plan_payload.get("has_gates")) or has_gates,
        stageOrder=_compact_unique(stage_order),
        stageDependencies=stage_dependencies,
        validationErrors=[str(item) for item in plan_payload.get("validation_errors", []) if isinstance(item, str)],
    )


def summarize_context_pack_preview(
    preview_payload: dict[str, Any],
    *,
    definition: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(preview_payload, dict) or not preview_payload:
        return {}

    items = preview_payload.get("items")
    if not isinstance(items, list):
        items = []

    total_tokens = _safe_int(
        preview_payload.get("total_tokens", preview_payload.get("total_estimated_tokens")),
        0,
    )
    budget_tokens = _safe_int(preview_payload.get("budget_tokens"), 0)
    items_available = _safe_int(preview_payload.get("items_available", preview_payload.get("total_items", len(items))), len(items))
    items_included = _safe_int(preview_payload.get("items_included", preview_payload.get("total_items", len(items))), len(items))
    utilization = _safe_float(preview_payload.get("utilization"), 0.0)
    if utilization <= 0.0 and budget_tokens > 0:
        utilization = min(1.0, total_tokens / max(1, budget_tokens))

    metadata = _definition_metadata(definition or {})
    return asdict(
        ContextPackPreviewSummary(
            moduleId=str((definition or {}).get("external_id") or ""),
            moduleName=str((definition or {}).get("display_name") or metadata.get("moduleName") or ""),
            itemsIncluded=items_included,
            itemsAvailable=items_available,
            totalTokens=total_tokens,
            budgetTokens=budget_tokens,
            utilization=round(utilization, 4),
            memoryTypes=_compact_unique([str(item.get("type") or "") for item in items if isinstance(item, dict)]),
        )
    )


def summarize_workflow_execution(payload: dict[str, Any]) -> WorkflowExecutionSummary:
    if not isinstance(payload, dict):
        return WorkflowExecutionSummary()

    steps = payload.get("steps")
    if not isinstance(steps, list):
        steps = []

    completed_steps = 0
    failed_steps = 0
    running_steps = 0
    gate_steps = 0
    for step in steps:
        if not isinstance(step, dict):
            continue
        status = str(step.get("status") or "").lower()
        if status == "completed":
            completed_steps += 1
        elif status == "failed":
            failed_steps += 1
        elif status in {"running", "pending"}:
            running_steps += 1
        if str(step.get("stage_type") or "").lower() == "gate":
            gate_steps += 1

    return WorkflowExecutionSummary(
        executionId=str(payload.get("id") or ""),
        workflowId=str(payload.get("workflow_id") or ""),
        status=str(payload.get("status") or ""),
        startedAt=str(payload.get("started_at") or ""),
        completedAt=str(payload.get("completed_at") or ""),
        errorMessage=str(payload.get("error_message") or ""),
        stepCount=len([step for step in steps if isinstance(step, dict)]),
        completedStepCount=completed_steps,
        failedStepCount=failed_steps,
        runningStepCount=running_steps,
        gateStepCount=gate_steps,
    )


def _effective_workflow_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    ranked = sorted(
        candidates,
        key=lambda item: (
            0 if str(_definition_metadata(item).get("workflowScope") or "") == "project" else 1,
            str(item.get("display_name") or ""),
            str(item.get("external_id") or ""),
        ),
    )
    return ranked[0]


def _definition_metadata(definition: dict[str, Any]) -> dict[str, Any]:
    metadata = definition.get("resolution_metadata")
    if isinstance(metadata, dict):
        return dict(metadata)
    return {}


def _slug_token(value: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    return "-".join(part for part in normalized.split("-") if part)


def _normalize_lookup_token(value: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() or ch in {":", "-", "_", "/"} else " " for ch in value.strip())
    return " ".join(normalized.split())


def _context_module_priority(definition: dict[str, Any]) -> int:
    metadata = _definition_metadata(definition)
    return 1 if str(metadata.get("scopeProjectId") or "").strip() else 0


def _compact_unique(values: list[str]) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for value in values:
        token = str(value or "").strip()
        if not token or token in seen:
            continue
        items.append(token)
        seen.add(token)
    return items


def _walk_stages(stages: list[Any], summary: WorkflowSwdlSummary) -> None:
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        stage_id = str(stage.get("id") or "")
        stage_type = str(stage.get("type") or "")
        depends_on = [str(item) for item in stage.get("depends_on", []) if isinstance(item, str)]
        if stage_id:
            summary.stageOrder.append(stage_id)
        if stage_type == "gate":
            summary.gateCount += 1
        if stage_type == "fan_out":
            summary.fanOutCount += 1

        summary.stageGraph.append(
            {
                "stageId": stage_id,
                "stageType": stage_type,
                "dependsOn": depends_on,
                "artifactRefs": [],
                "contextRefs": [],
            }
        )
        stage_entry = summary.stageGraph[-1]

        for value in _iter_scalar_tokens(stage):
            if _ARTIFACT_REF_RE.match(value):
                summary.artifactRefs.append(value)
                stage_entry["artifactRefs"].append(value)
            elif _CTX_REF_RE.match(value):
                summary.contextRefs.append(value)
                stage_entry["contextRefs"].append(value)

        nested_stages = stage.get("stages")
        if isinstance(nested_stages, list):
            _walk_stages(nested_stages, summary)


def _iter_scalar_tokens(payload: Any) -> list[str]:
    tokens: list[str] = []
    if isinstance(payload, dict):
        for value in payload.values():
            tokens.extend(_iter_scalar_tokens(value))
    elif isinstance(payload, list):
        for value in payload:
            tokens.extend(_iter_scalar_tokens(value))
    elif isinstance(payload, str):
        tokens.append(payload.strip())
    return tokens


def _dedupe_swdl_summary(summary: WorkflowSwdlSummary) -> WorkflowSwdlSummary:
    summary.artifactRefs = _compact_unique(summary.artifactRefs)
    summary.contextRefs = _compact_unique(summary.contextRefs)
    summary.stageOrder = _compact_unique(summary.stageOrder)
    for entry in summary.stageGraph:
        entry["artifactRefs"] = _compact_unique([str(item) for item in entry.get("artifactRefs", []) if isinstance(item, str)])
        entry["contextRefs"] = _compact_unique([str(item) for item in entry.get("contextRefs", []) if isinstance(item, str)])
    return summary


def _extract_bundle_artifact_refs(payload: dict[str, Any]) -> list[str]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    refs: list[str] = []
    for item in artifacts:
        if not isinstance(item, dict):
            continue
        artifact_type = str(item.get("type") or "").strip()
        artifact_name = str(item.get("name") or item.get("id") or "").strip()
        if artifact_type and artifact_name:
            refs.append(f"{artifact_type}:{artifact_name}")
        elif artifact_name:
            refs.append(artifact_name)
    return _compact_unique(refs)


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
