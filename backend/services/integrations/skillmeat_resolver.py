"""Deterministic resolution of observed components against cached SkillMeat definitions."""
from __future__ import annotations

from typing import Any


def resolve_stack_components(
    *,
    components: list[dict[str, Any]],
    definitions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_external_id: dict[tuple[str, str], dict[str, Any]] = {}
    by_display_name: dict[tuple[str, str], dict[str, Any]] = {}
    for definition in definitions:
        definition_type = str(definition.get("definition_type") or "")
        external_id = _normalize_token(definition.get("external_id"))
        display_name = _normalize_token(definition.get("display_name"))
        if definition_type and external_id:
            by_external_id[(definition_type, external_id)] = definition
        if definition_type and display_name:
            by_display_name[(definition_type, display_name)] = definition

    resolved: list[dict[str, Any]] = []
    for component in components:
        updated = dict(component)
        definition_type = _target_definition_type(component)
        candidate_tokens = _candidate_tokens(component)
        matched: dict[str, Any] | None = None
        matched_via = ""
        if definition_type:
            for token in candidate_tokens:
                normalized = _normalize_token(token)
                if not normalized:
                    continue
                matched = by_external_id.get((definition_type, normalized))
                if matched:
                    matched_via = "external_id_exact"
                    break
            if matched is None:
                for token in candidate_tokens:
                    normalized = _normalize_token(token)
                    if not normalized:
                        continue
                    matched = by_display_name.get((definition_type, normalized))
                    if matched:
                        matched_via = "display_name_exact"
                        break

        if matched:
            updated["status"] = "resolved"
            updated["confidence"] = max(float(updated.get("confidence") or 0.0), 0.95 if matched_via == "external_id_exact" else 0.85)
            updated["external_definition_id"] = matched.get("id")
            updated["external_definition_type"] = matched.get("definition_type", "")
            updated["external_definition_external_id"] = matched.get("external_id", "")
            updated["source_attribution"] = matched_via
        else:
            updated["status"] = "unresolved" if definition_type else str(updated.get("status") or "explicit")
            updated["source_attribution"] = str(updated.get("source_attribution") or ("local_only" if not definition_type else "no_match"))
        resolved.append(updated)
    return resolved


def _target_definition_type(component: dict[str, Any]) -> str:
    component_type = str(component.get("component_type") or component.get("componentType") or "")
    if component_type in {"artifact", "skill"}:
        return "artifact"
    if component_type == "workflow":
        return "workflow"
    if component_type == "context_module":
        return "context_module"
    return ""


def _candidate_tokens(component: dict[str, Any]) -> list[str]:
    payload = component.get("payload")
    if not isinstance(payload, dict):
        payload = component.get("component_payload_json")
    if not isinstance(payload, dict):
        payload = {}
    values = [
        component.get("component_key"),
        payload.get("externalId"),
        payload.get("external_id"),
        payload.get("name"),
        payload.get("title"),
        payload.get("workflowRef"),
        payload.get("contextRef"),
        payload.get("artifactId"),
        payload.get("skill"),
    ]
    return [str(value).strip() for value in values if isinstance(value, str) and value.strip()]


def _normalize_token(value: object) -> str:
    if not isinstance(value, str):
        return ""
    normalized = "".join(ch.lower() if ch.isalnum() or ch in {":", "-", "_"} else " " for ch in value.strip())
    return " ".join(normalized.split())
