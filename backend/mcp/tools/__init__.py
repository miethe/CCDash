"""MCP tool registration and shared response helpers."""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from pydantic import BaseModel


META_FIELDS = {"status", "generated_at", "data_freshness", "source_refs"}
IDENTIFIER_FIELDS = (
    "project_id",
    "feature_id",
    "feature_slug",
)


def _serialize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    if isinstance(value, tuple):
        return [_serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize_value(item) for key, item in value.items()}
    return value


def build_envelope(result: BaseModel, *, identifiers: Iterable[str] = IDENTIFIER_FIELDS) -> dict[str, Any]:
    payload = result.model_dump(mode="json")
    data = {key: value for key, value in payload.items() if key not in META_FIELDS}
    meta = {
        "generated_at": _serialize_value(getattr(result, "generated_at", None)),
        "data_freshness": _serialize_value(getattr(result, "data_freshness", None)),
        "source_refs": _serialize_value(getattr(result, "source_refs", [])),
    }
    for field in identifiers:
        value = payload.get(field)
        if value is not None:
            meta[field] = _serialize_value(value)
    return {
        "status": payload.get("status", "error"),
        "data": data,
        "meta": meta,
    }


def register_tools(mcp: Any) -> None:
    from backend.mcp.tools.features import register_feature_tools
    from backend.mcp.tools.project import register_project_tools
    from backend.mcp.tools.reports import register_report_tools
    from backend.mcp.tools.workflows import register_workflow_tools

    register_project_tools(mcp)
    register_feature_tools(mcp)
    register_workflow_tools(mcp)
    register_report_tools(mcp)


__all__ = ["build_envelope", "register_tools"]
