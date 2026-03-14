"""Helpers for stable SkillMeat UI routes derived from API-backed definitions."""
from __future__ import annotations

from typing import Any
from urllib.parse import quote, urlencode


def build_definition_source_url(
    definition_type: str,
    external_id: str,
    *,
    web_base_url: str,
    project_id: str = "",
    collection_id: str = "",
) -> str:
    normalized_base = _normalize_base_url(web_base_url)
    if not normalized_base:
        return ""

    if definition_type == "artifact" and external_id:
        query = urlencode(
            {
                "collection": collection_id or "default",
                "artifact": external_id,
            }
        )
        return f"{normalized_base}/collection?{query}"
    if definition_type == "workflow" and external_id:
        return f"{normalized_base}/workflows/{quote(external_id, safe='')}"
    if definition_type == "context_module" and project_id:
        return f"{normalized_base}/projects/{quote(project_id, safe='')}/memory"
    if definition_type == "bundle":
        query = urlencode({"collection": collection_id or "default"})
        return f"{normalized_base}/collection?{query}"
    return ""


def build_execution_source_url(
    *,
    web_base_url: str,
    workflow_id: str,
) -> str:
    normalized_base = _normalize_base_url(web_base_url)
    if not normalized_base:
        return ""
    query = urlencode({"workflow_id": workflow_id}) if workflow_id else ""
    return f"{normalized_base}/workflows/executions{f'?{query}' if query else ''}"


def attach_stable_definition_source(
    definition: dict[str, Any],
    *,
    web_base_url: str,
    project_id: str = "",
    collection_id: str = "",
) -> dict[str, Any]:
    updated = dict(definition)
    metadata = updated.get("resolution_metadata")
    if not isinstance(metadata, dict):
        metadata = updated.get("resolution_metadata_json")
    metadata = dict(metadata) if isinstance(metadata, dict) else {}

    raw_source_url = str(updated.get("source_url") or metadata.get("rawSourceUrl") or "").strip()
    stable_source_url = build_definition_source_url(
        str(updated.get("definition_type") or ""),
        str(updated.get("external_id") or ""),
        web_base_url=web_base_url,
        project_id=project_id,
        collection_id=collection_id,
    )

    if raw_source_url:
        metadata["rawSourceUrl"] = raw_source_url
    updated["source_url"] = stable_source_url
    if stable_source_url:
        metadata["stableSourceUrl"] = stable_source_url
    else:
        metadata.pop("stableSourceUrl", None)

    if str(updated.get("definition_type") or "") == "workflow":
        execution_url = build_execution_source_url(
            web_base_url=web_base_url,
            workflow_id=str(updated.get("external_id") or ""),
        )
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
            web_base_url=web_base_url,
            project_id=project_id,
            collection_id=collection_id,
        )
        if isinstance(resolved_contexts, list):
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
    updated["resolution_metadata_json"] = metadata
    return updated


def _normalize_base_url(base_url: str) -> str:
    return str(base_url or "").strip().rstrip("/")


def normalize_definition_for_project(definition: dict[str, Any], project: Any) -> dict[str, Any]:
    config = getattr(project, "skillMeat", None)
    return attach_stable_definition_source(
        definition,
        web_base_url=str(getattr(config, "webBaseUrl", "") or ""),
        project_id=str(getattr(config, "projectId", "") or ""),
        collection_id=str(getattr(config, "collectionId", "") or ""),
    )


def normalize_definitions_for_project(definitions: list[dict[str, Any]], project: Any) -> list[dict[str, Any]]:
    return [normalize_definition_for_project(definition, project) for definition in definitions]
