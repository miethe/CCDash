"""Read-only SkillMeat client and payload normalization."""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request


_ARTIFACT_PAGE_LIMIT = 200
_CONTEXT_MODULE_PAGE_LIMIT = 100
_WORKFLOW_PAGE_LIMIT = 100
_BUNDLE_PAGE_LIMIT = 100
_MAX_CURSOR_PAGES = 25
_MAX_OFFSET_PAGES = 25


class SkillMeatClientError(RuntimeError):
    """Raised when SkillMeat cannot be queried successfully."""

    def __init__(
        self,
        message: str,
        *,
        endpoint: str = "",
        status_code: int | None = None,
        detail: str = "",
        payload: Any = None,
    ) -> None:
        super().__init__(message)
        self.endpoint = endpoint
        self.status_code = status_code
        self.detail = detail or message
        self.payload = payload


@dataclass(slots=True)
class SkillMeatClient:
    base_url: str
    timeout_seconds: float = 5.0
    aaa_enabled: bool = False
    api_key: str = ""

    async def fetch_definitions(
        self,
        *,
        definition_type: str,
        project_id: str = "",
        workspace_id: str = "",
        collection_id: str = "",
    ) -> list[dict[str, Any]]:
        effective_collection_id = str(collection_id or workspace_id or "").strip()
        if definition_type == "artifact":
            items = await self.list_artifacts(collection_id=effective_collection_id)
            return [_normalize_artifact_item(item) for item in items]
        if definition_type == "workflow":
            items = await self.list_workflows(project_id=project_id)
            return [_normalize_workflow_item(item) for item in items]
        if definition_type == "context_module":
            items = await self.list_context_modules(project_id=project_id)
            return [_normalize_context_module_item(item) for item in items]
        if definition_type == "bundle":
            items = await self.list_bundles()
            return [_normalize_bundle_item(item) for item in items]
        raise SkillMeatClientError(f"Unsupported definition type '{definition_type}'")

    async def validate_base_url(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._request_json, "/api/v1/projects", {"limit": 1})

    async def get_project(self, project_id: str) -> dict[str, Any]:
        encoded_project_id = parse.quote(str(project_id or "").strip(), safe="")
        payload = await asyncio.to_thread(self._request_json, f"/api/v1/projects/{encoded_project_id}", None)
        if isinstance(payload, dict):
            return payload
        return {}

    async def list_artifacts(self, *, collection_id: str = "") -> list[dict[str, Any]]:
        query: dict[str, Any] = {"limit": _ARTIFACT_PAGE_LIMIT}
        if collection_id:
            query["collection"] = collection_id
        return await asyncio.to_thread(
            self._paginate_cursor_resource,
            "/api/v1/artifacts",
            query,
            "items",
            page_info_key="page_info",
            cursor_param="after",
            end_cursor_key="end_cursor",
            has_more_key="has_next_page",
        )

    async def list_workflows(self, *, project_id: str = "") -> list[dict[str, Any]]:
        query: dict[str, Any] = {"limit": _WORKFLOW_PAGE_LIMIT}
        if project_id:
            query["project_id"] = project_id
        return await asyncio.to_thread(self._paginate_offset_resource, "/api/v1/workflows", query)

    async def get_workflow(self, workflow_id: str) -> dict[str, Any]:
        payload = await asyncio.to_thread(self._request_json, f"/api/v1/workflows/{parse.quote(workflow_id, safe='')}", None)
        return payload if isinstance(payload, dict) else {}

    async def plan_workflow(self, workflow_id: str, *, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
        body = {"parameters": parameters} if parameters else None
        payload = await asyncio.to_thread(
            self._request_json,
            f"/api/v1/workflows/{parse.quote(workflow_id, safe='')}/plan",
            None,
            method="POST",
            body=body,
        )
        return payload if isinstance(payload, dict) else {}

    async def list_context_modules(self, *, project_id: str) -> list[dict[str, Any]]:
        if not str(project_id or "").strip():
            return []
        query: dict[str, Any] = {
            "project_id": project_id,
            "limit": _CONTEXT_MODULE_PAGE_LIMIT,
        }
        return await asyncio.to_thread(
            self._paginate_cursor_resource,
            "/api/v1/context-modules",
            query,
            "items",
            cursor_param="cursor",
            end_cursor_key="next_cursor",
            has_more_key="has_more",
            page_info_key=None,
        )

    async def get_context_module(self, module_id: str) -> dict[str, Any]:
        payload = await asyncio.to_thread(
            self._request_json,
            f"/api/v1/context-modules/{parse.quote(module_id, safe='')}",
            None,
        )
        return payload if isinstance(payload, dict) else {}

    async def list_bundles(self) -> list[dict[str, Any]]:
        payload = await asyncio.to_thread(self._request_json, "/api/v1/bundles", {"limit": _BUNDLE_PAGE_LIMIT})
        if isinstance(payload, dict):
            bundles = payload.get("bundles")
            if isinstance(bundles, list):
                return [item for item in bundles if isinstance(item, dict)]
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    async def get_bundle(self, bundle_id: str) -> dict[str, Any]:
        payload = await asyncio.to_thread(self._request_json, f"/api/v1/bundles/{parse.quote(bundle_id, safe='')}", None)
        return payload if isinstance(payload, dict) else {}

    def _request_json(
        self,
        endpoint: str,
        query: dict[str, Any] | None,
        *,
        method: str = "GET",
        body: dict[str, Any] | None = None,
    ) -> Any:
        base = self.base_url.rstrip("/")
        encoded_query = parse.urlencode(
            {
                key: value
                for key, value in (query or {}).items()
                if value is not None and str(value) != ""
            },
            doseq=True,
        )
        suffix = f"?{encoded_query}" if encoded_query else ""
        url = f"{base}{endpoint}{suffix}"

        headers = {"Accept": "application/json"}
        token = str(self.api_key or "").strip()
        if self.aaa_enabled and token:
            headers["Authorization"] = f"Bearer {token}"

        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")

        req = request.Request(url, data=data, headers=headers, method=method.upper())
        try:
            with request.urlopen(req, timeout=max(0.1, float(self.timeout_seconds))) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            payload = _decode_json_payload(exc.read().decode("utf-8", errors="replace"))
            detail = _extract_error_detail(payload) or f"HTTP {exc.code}"
            raise SkillMeatClientError(
                f"{endpoint} returned HTTP {exc.code}: {detail}",
                endpoint=endpoint,
                status_code=exc.code,
                detail=detail,
                payload=payload,
            ) from exc
        except error.URLError as exc:
            detail = str(exc.reason)
            raise SkillMeatClientError(
                f"{endpoint} unavailable: {detail}",
                endpoint=endpoint,
                detail=detail,
            ) from exc
        except TimeoutError as exc:
            raise SkillMeatClientError(
                f"{endpoint} timed out",
                endpoint=endpoint,
                detail="request timed out",
            ) from exc

        try:
            return _decode_json_payload(raw)
        except json.JSONDecodeError as exc:
            raise SkillMeatClientError(
                f"{endpoint} returned invalid JSON",
                endpoint=endpoint,
                detail="invalid JSON response",
            ) from exc

    def _paginate_cursor_resource(
        self,
        endpoint: str,
        query: dict[str, Any],
        items_key: str,
        *,
        page_info_key: str | None = "page_info",
        cursor_param: str = "after",
        end_cursor_key: str = "end_cursor",
        has_more_key: str = "has_next_page",
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        next_cursor = str(query.get(cursor_param) or "").strip()
        base_query = dict(query)

        for _ in range(_MAX_CURSOR_PAGES):
            page_query = dict(base_query)
            if next_cursor:
                page_query[cursor_param] = next_cursor
            payload = self._request_json(endpoint, page_query)
            batch = _extract_dict_items(payload, items_key)
            items.extend(batch)

            if not isinstance(payload, dict):
                break
            if page_info_key:
                page_info = payload.get(page_info_key)
                if not isinstance(page_info, dict):
                    break
                has_more = bool(page_info.get(has_more_key))
                next_cursor = str(page_info.get(end_cursor_key) or "").strip()
            else:
                has_more = bool(payload.get(has_more_key))
                next_cursor = str(payload.get(end_cursor_key) or "").strip()

            if not has_more or not next_cursor:
                break
        return items

    def _paginate_offset_resource(self, endpoint: str, query: dict[str, Any]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        limit = int(query.get("limit") or _WORKFLOW_PAGE_LIMIT)
        skip = int(query.get("skip") or 0)
        base_query = {key: value for key, value in query.items() if key != "skip"}

        for _ in range(_MAX_OFFSET_PAGES):
            page_query = dict(base_query)
            page_query["skip"] = skip
            payload = self._request_json(endpoint, page_query)
            batch = [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else _extract_dict_items(payload, "items")
            items.extend(batch)
            if len(batch) < limit:
                break
            skip += limit
        return items


def _decode_json_payload(raw: str) -> Any:
    return json.loads(raw) if raw else []


def _extract_error_detail(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("detail", "message", "error"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _extract_dict_items(payload: Any, items_key: str) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        items = payload.get(items_key)
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _first_text(*values: object) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _slug_token(value: object) -> str:
    if not isinstance(value, str):
        return ""
    normalized = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    return "-".join(part for part in normalized.split("-") if part)


def _normalize_artifact_item(item: dict[str, Any]) -> dict[str, Any]:
    artifact_type = _first_text(item.get("type"), item.get("artifact_type"))
    artifact_name = _first_text(item.get("name"), item.get("title"))
    external_id = _first_text(item.get("id"), item.get("external_id"), item.get("externalId"))
    if not external_id and artifact_type and artifact_name:
        external_id = f"{artifact_type}:{artifact_name}"
    display_name = _first_text(
        _safe_dict(item.get("metadata")).get("title"),
        artifact_name,
        external_id,
    )
    return {
        "definition_type": "artifact",
        "external_id": external_id or "artifact:unknown",
        "display_name": display_name or external_id or "artifact",
        "version": _first_text(item.get("version"), _safe_dict(item.get("metadata")).get("version")),
        "source_url": _first_text(item.get("url"), item.get("href"), item.get("source_url")),
        "resolution_metadata": {
            "artifactUuid": _first_text(item.get("uuid")),
            "artifactType": artifact_type,
            "artifactName": artifact_name,
            "collectionId": _extract_collection_id(item),
            "aliases": _compact_unique([external_id, f"{artifact_type}:{artifact_name}" if artifact_type and artifact_name else ""]),
            "normalizedFrom": list(sorted(item.keys()))[:32],
        },
        "raw_snapshot": item,
    }


def _normalize_workflow_item(item: dict[str, Any]) -> dict[str, Any]:
    workflow_id = _first_text(item.get("id"), item.get("workflow_id"))
    workflow_name = _first_text(item.get("name"), item.get("title"), workflow_id)
    project_id = _first_text(item.get("project_id"))
    aliases = _compact_unique(
        [
            workflow_id,
            workflow_name,
            _slug_token(workflow_name),
        ]
    )
    return {
        "definition_type": "workflow",
        "external_id": workflow_id or _slug_token(workflow_name) or "workflow",
        "display_name": workflow_name or workflow_id or "workflow",
        "version": _first_text(item.get("version")),
        "source_url": _first_text(item.get("url"), item.get("href"), item.get("source_url")),
        "resolution_metadata": {
            "workflowName": workflow_name,
            "workflowScope": "project" if project_id else "global",
            "scopeProjectId": project_id,
            "aliases": aliases,
            "normalizedFrom": list(sorted(item.keys()))[:32],
        },
        "raw_snapshot": item,
    }


def _normalize_context_module_item(item: dict[str, Any]) -> dict[str, Any]:
    module_id = _first_text(item.get("id"))
    module_name = _first_text(item.get("name"), item.get("title"), module_id)
    return {
        "definition_type": "context_module",
        "external_id": module_id or _slug_token(module_name) or "context-module",
        "display_name": module_name or module_id or "context module",
        "version": _first_text(item.get("content_hash")),
        "source_url": _first_text(item.get("url"), item.get("href"), item.get("source_url")),
        "resolution_metadata": {
            "moduleName": module_name,
            "scopeProjectId": _first_text(item.get("project_id")),
            "aliases": _compact_unique([module_id, module_name, _slug_token(module_name), f"ctx:{_slug_token(module_name)}" if module_name else ""]),
            "normalizedFrom": list(sorted(item.keys()))[:32],
        },
        "raw_snapshot": item,
    }


def _normalize_bundle_item(item: dict[str, Any]) -> dict[str, Any]:
    bundle_id = _first_text(item.get("bundle_id"), item.get("id"))
    bundle_name = _first_text(item.get("name"), _safe_dict(item.get("metadata")).get("name"), bundle_id)
    return {
        "definition_type": "bundle",
        "external_id": bundle_id or _slug_token(bundle_name) or "bundle",
        "display_name": bundle_name or bundle_id or "bundle",
        "version": _first_text(_safe_dict(item.get("metadata")).get("version")),
        "source_url": _first_text(item.get("bundle_path"), item.get("source_url")),
        "resolution_metadata": {
            "bundleName": bundle_name,
            "bundleSource": _first_text(item.get("source")),
            "artifactCount": _safe_int(item.get("artifact_count") or len(_safe_list(item.get("artifacts"))), 0),
            "aliases": _compact_unique([bundle_id, bundle_name, _slug_token(bundle_name)]),
            "normalizedFrom": list(sorted(item.keys()))[:32],
        },
        "raw_snapshot": item,
    }


def _extract_collection_id(item: dict[str, Any]) -> str:
    collections = item.get("collections")
    if isinstance(collections, list):
        for entry in collections:
            if isinstance(entry, dict):
                collection_id = _first_text(entry.get("collection_id"), entry.get("collectionId"))
                if collection_id:
                    return collection_id
    return ""


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


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
