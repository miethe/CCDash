"""Deterministic resolution of observed components against cached SkillMeat definitions."""
from __future__ import annotations

from typing import Any


def build_definition_indexes(
    definitions: list[dict[str, Any]],
) -> tuple[
    dict[tuple[str, str], dict[str, Any]],
    dict[tuple[str, str], dict[str, Any]],
    dict[tuple[str, str], dict[str, Any]],
]:
    by_external_id: dict[tuple[str, str], dict[str, Any]] = {}
    by_display_name: dict[tuple[str, str], dict[str, Any]] = {}
    by_alias: dict[tuple[str, str], dict[str, Any]] = {}
    for definition in definitions:
        definition_type = str(definition.get("definition_type") or "")
        external_id = _normalize_token(definition.get("external_id"))
        display_name = _normalize_token(definition.get("display_name"))
        if definition_type and external_id:
            by_external_id[(definition_type, external_id)] = definition
        if definition_type and display_name:
            by_display_name[(definition_type, display_name)] = definition
        for alias in _definition_aliases(definition):
            key = (definition_type, alias)
            existing = by_alias.get(key)
            if existing is None or _definition_priority(definition) >= _definition_priority(existing):
                by_alias[key] = definition
    return by_external_id, by_display_name, by_alias


def resolve_component_definition(
    component: dict[str, Any],
    definition_indexes: tuple[
        dict[tuple[str, str], dict[str, Any]],
        dict[tuple[str, str], dict[str, Any]],
        dict[tuple[str, str], dict[str, Any]],
    ],
) -> tuple[dict[str, Any] | None, str, str]:
    by_external_id, by_display_name, by_alias = definition_indexes
    definition_types = _target_definition_types(component)
    candidate_tokens = _candidate_tokens(component)
    for definition_type in definition_types:
        for token in candidate_tokens:
            normalized = _normalize_token(token)
            if not normalized:
                continue
            matched = by_external_id.get((definition_type, normalized))
            if matched:
                return matched, "external_id_exact", "resolved"
        for token in candidate_tokens:
            normalized = _normalize_token(token)
            if not normalized:
                continue
            matched = by_alias.get((definition_type, normalized))
            if matched:
                return matched, "alias_exact", "resolved"
        for token in candidate_tokens:
            normalized = _normalize_token(token)
            if not normalized:
                continue
            matched = by_display_name.get((definition_type, normalized))
            if matched:
                return matched, "display_name_exact", "resolved"
    return None, "", "unresolved" if definition_types else str(component.get("status") or "explicit")


def resolve_stack_components(
    *,
    components: list[dict[str, Any]],
    definitions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    definition_indexes = build_definition_indexes(definitions)
    resolved: list[dict[str, Any]] = []
    for component in components:
        updated = dict(component)
        matched, matched_via, fallback_status = resolve_component_definition(component, definition_indexes)

        if matched:
            updated["status"] = "resolved"
            updated["confidence"] = max(
                float(updated.get("confidence") or 0.0),
                0.95 if matched_via == "external_id_exact" else 0.9 if matched_via == "alias_exact" else 0.85,
            )
            updated["external_definition_id"] = matched.get("id")
            updated["external_definition_type"] = matched.get("definition_type", "")
            updated["external_definition_external_id"] = matched.get("external_id", "")
            updated["source_attribution"] = matched_via
        else:
            definition_types = _target_definition_types(component)
            updated["status"] = fallback_status
            updated["source_attribution"] = str(updated.get("source_attribution") or ("local_only" if not definition_types else "no_match"))
        resolved.append(updated)
    return resolved


def _target_definition_types(component: dict[str, Any]) -> list[str]:
    component_type = str(component.get("component_type") or component.get("componentType") or "")
    if component_type in {"artifact", "skill", "agent", "command"}:
        return ["artifact"]
    if component_type == "workflow":
        return ["workflow", "artifact"]
    if component_type == "context_module":
        return ["context_module"]
    return []


def _candidate_tokens(component: dict[str, Any]) -> list[str]:
    payload = component.get("payload")
    if not isinstance(payload, dict):
        payload = component.get("component_payload_json")
    if not isinstance(payload, dict):
        payload = {}
    component_type = str(component.get("component_type") or component.get("componentType") or "")
    component_key = str(component.get("component_key") or component.get("componentKey") or "").strip()
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
    tokens = [str(value).strip() for value in values if isinstance(value, str) and value.strip()]
    if component_type == "skill" and component_key:
        tokens.append(f"skill:{component_key}")
    if component_type == "agent" and component_key:
        tokens.append(f"agent:{component_key}")
    if component_type in {"command", "workflow"}:
        for candidate in [component_key, str(payload.get("relatedCommand") or "").strip(), str(payload.get("command") or "").strip()]:
            normalized = _normalize_token(candidate)
            if not normalized:
                continue
            tokens.append(normalized)
            if normalized.startswith("command:"):
                continue
            if ":" in normalized:
                tokens.append(f"command:{normalized.split(':', 1)[1]}")
            else:
                tokens.append(f"command:{normalized}")
    return [token for token in tokens if token]


def _normalize_token(value: object) -> str:
    if not isinstance(value, str):
        return ""
    normalized = "".join(ch.lower() if ch.isalnum() or ch in {":", "-", "_"} else " " for ch in value.strip())
    return " ".join(normalized.split())


def _definition_aliases(definition: dict[str, Any]) -> list[str]:
    metadata = definition.get("resolution_metadata_json")
    if not isinstance(metadata, dict):
        metadata = definition.get("resolution_metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    aliases: list[str] = []
    for candidate in metadata.get("aliases", []):
        normalized = _normalize_token(candidate)
        if normalized:
            aliases.append(normalized)
    return aliases


def _definition_priority(definition: dict[str, Any]) -> int:
    metadata = definition.get("resolution_metadata_json")
    if not isinstance(metadata, dict):
        metadata = definition.get("resolution_metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    score = 0
    if bool(metadata.get("isEffective")):
        score += 2
    if str(metadata.get("workflowScope") or "") == "project":
        score += 1
    return score
