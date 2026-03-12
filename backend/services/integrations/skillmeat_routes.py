"""Helpers for stable SkillMeat UI routes derived from API-backed definitions."""
from __future__ import annotations

from typing import Any
from urllib.parse import quote, urlencode


def build_definition_source_url(
    definition_type: str,
    external_id: str,
    *,
    base_url: str,
    project_id: str = "",
) -> str:
    normalized_base = _normalize_base_url(base_url)
    if not normalized_base:
        return ""

    if definition_type == "artifact" and external_id:
        return f"{normalized_base}/artifacts/{quote(external_id, safe=':')}"
    if definition_type == "workflow" and external_id:
        return f"{normalized_base}/workflows/{quote(external_id, safe='')}"
    if definition_type == "context_module" and project_id:
        return f"{normalized_base}/projects/{quote(project_id, safe='')}/memory"
    if definition_type == "bundle":
        return f"{normalized_base}/collection"
    return ""


def build_execution_source_url(
    *,
    base_url: str,
    workflow_id: str,
) -> str:
    normalized_base = _normalize_base_url(base_url)
    if not normalized_base:
        return ""
    query = urlencode({"workflow_id": workflow_id}) if workflow_id else ""
    return f"{normalized_base}/workflows/executions{f'?{query}' if query else ''}"


def attach_stable_definition_source(
    definition: dict[str, Any],
    *,
    base_url: str,
    project_id: str = "",
) -> dict[str, Any]:
    updated = dict(definition)
    metadata = updated.get("resolution_metadata")
    metadata = dict(metadata) if isinstance(metadata, dict) else {}

    raw_source_url = str(updated.get("source_url") or metadata.get("rawSourceUrl") or "").strip()
    stable_source_url = build_definition_source_url(
        str(updated.get("definition_type") or ""),
        str(updated.get("external_id") or ""),
        base_url=base_url,
        project_id=project_id,
    )

    if raw_source_url:
        metadata["rawSourceUrl"] = raw_source_url
    if stable_source_url:
        metadata["stableSourceUrl"] = stable_source_url
        updated["source_url"] = stable_source_url

    if str(updated.get("definition_type") or "") == "workflow":
        execution_url = build_execution_source_url(
            base_url=base_url,
            workflow_id=str(updated.get("external_id") or ""),
        )
        if execution_url:
            execution_summary = metadata.get("executionSummary")
            if isinstance(execution_summary, dict):
                metadata["executionSummary"] = {**execution_summary, "sourceUrl": execution_url}

            recent_executions = metadata.get("recentExecutions")
            if isinstance(recent_executions, list):
                normalized_executions: list[dict[str, Any]] = []
                for item in recent_executions:
                    if isinstance(item, dict):
                        normalized_executions.append({**item, "sourceUrl": execution_url})
                metadata["recentExecutions"] = normalized_executions

            resolved_contexts = metadata.get("resolvedContextModules")
            context_source_url = build_definition_source_url(
                "context_module",
                "",
                base_url=base_url,
                project_id=project_id,
            )
            if context_source_url and isinstance(resolved_contexts, list):
                normalized_contexts: list[dict[str, Any]] = []
                for item in resolved_contexts:
                    if isinstance(item, dict):
                        raw_context_source = str(item.get("sourceUrl") or "").strip()
                        normalized_contexts.append(
                            {
                                **item,
                                "rawSourceUrl": raw_context_source,
                                "sourceUrl": context_source_url,
                            }
                        )
                metadata["resolvedContextModules"] = normalized_contexts

    updated["resolution_metadata"] = metadata
    return updated


def _normalize_base_url(base_url: str) -> str:
    normalized = str(base_url or "").strip().rstrip("/")
    for suffix in ("/api/v1", "/api"):
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
            break
    return normalized.rstrip("/")
