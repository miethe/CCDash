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
