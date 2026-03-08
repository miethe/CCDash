"""Helpers for contract-aligned SkillMeat definition metadata."""
from __future__ import annotations

from typing import Any


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
