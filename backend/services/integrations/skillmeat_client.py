"""Read-only SkillMeat client and payload normalization."""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request


class SkillMeatClientError(RuntimeError):
    """Raised when SkillMeat cannot be queried successfully."""


@dataclass(slots=True)
class SkillMeatClient:
    base_url: str
    timeout_seconds: float = 5.0

    async def fetch_definitions(
        self,
        *,
        definition_type: str,
        project_id: str = "",
        workspace_id: str = "",
    ) -> list[dict[str, Any]]:
        endpoint = _endpoint_for(definition_type)
        query: dict[str, str] = {}
        if project_id:
            query["project_id"] = project_id
        if workspace_id:
            query["workspace_id"] = workspace_id
        payload = await asyncio.to_thread(self._request_json, endpoint, query)
        items = _extract_items(payload, definition_type)
        return [_normalize_definition_item(item, definition_type) for item in items]

    def _request_json(self, endpoint: str, query: dict[str, str]) -> Any:
        base = self.base_url.rstrip("/")
        suffix = f"?{parse.urlencode(query)}" if query else ""
        url = f"{base}{endpoint}{suffix}"
        req = request.Request(url, headers={"Accept": "application/json"})
        try:
            with request.urlopen(req, timeout=max(0.1, float(self.timeout_seconds))) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            raise SkillMeatClientError(f"{endpoint} returned HTTP {exc.code}") from exc
        except error.URLError as exc:
            raise SkillMeatClientError(f"{endpoint} unavailable: {exc.reason}") from exc
        except TimeoutError as exc:
            raise SkillMeatClientError(f"{endpoint} timed out") from exc
        try:
            return json.loads(raw) if raw else []
        except json.JSONDecodeError as exc:
            raise SkillMeatClientError(f"{endpoint} returned invalid JSON") from exc


def _endpoint_for(definition_type: str) -> str:
    mapping = {
        "artifact": "/api/artifacts",
        "workflow": "/api/workflows",
        "context_module": "/api/context-modules",
    }
    if definition_type not in mapping:
        raise SkillMeatClientError(f"Unsupported definition type '{definition_type}'")
    return mapping[definition_type]


def _extract_items(payload: Any, definition_type: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    candidate_keys = [
        "items",
        f"{definition_type}s",
        f"{definition_type}_items",
        definition_type,
    ]
    if definition_type == "context_module":
        candidate_keys.extend(["contextModules", "context_modules"])

    for key in candidate_keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _normalize_definition_item(item: dict[str, Any], definition_type: str) -> dict[str, Any]:
    display_name = _first_text(
        item.get("displayName"),
        item.get("name"),
        item.get("title"),
        item.get("label"),
        item.get("slug"),
        item.get("id"),
    )
    external_id = _first_text(
        item.get("externalId"),
        item.get("external_id"),
        item.get("id"),
    )
    if not external_id and definition_type == "artifact":
        artifact_type = _first_text(item.get("type"), item.get("artifactType"))
        artifact_name = _first_text(item.get("name"), item.get("title"))
        if artifact_type and artifact_name:
            external_id = f"{artifact_type}:{artifact_name}"
    if not external_id and definition_type == "context_module":
        external_id = _first_text(item.get("slug"), item.get("name"), item.get("title"))
        if external_id and not external_id.startswith("ctx:"):
            external_id = f"ctx:{external_id}"
    if not external_id:
        external_id = _slugify(display_name or definition_type)

    return {
        "definition_type": definition_type,
        "external_id": external_id,
        "display_name": display_name or external_id,
        "version": _first_text(item.get("version"), item.get("revision"), item.get("etag")),
        "source_url": _first_text(item.get("url"), item.get("href"), item.get("permalink")),
        "resolution_metadata": {
            "normalizedFrom": list(sorted(item.keys()))[:24],
        },
        "raw_snapshot": item,
    }


def _first_text(*values: object) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _slugify(value: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    parts = [part for part in normalized.split("-") if part]
    return "-".join(parts) or "unknown"
