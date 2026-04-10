"""Shared filter and scope resolution helpers for agent query services."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.application.context import ProjectScope, RequestContext
from backend.application.ports import CorePorts


def resolve_project_scope(
    context: RequestContext,
    ports: CorePorts,
    project_id_override: str | None = None,
) -> ProjectScope:
    """Resolve the effective project scope for an agent query request.

    Resolution order is:
    1. Explicit ``project_id_override`` when provided.
    2. The request-scoped project on ``context``.
    3. The active project from the workspace registry.

    Raises:
        ValueError: If no project can be resolved.
    """
    project_id = (project_id_override or "").strip()
    if project_id:
        _, project_scope = ports.workspace_registry.resolve_scope(project_id)
        if project_scope is None:
            raise ValueError(f"Project '{project_id}' could not be resolved")
        return project_scope

    if context.project is not None:
        return context.project

    active_project = ports.workspace_registry.get_active_project()
    if active_project is None:
        raise ValueError("No active project available for query scope")

    _, project_scope = ports.workspace_registry.resolve_scope(active_project.id)
    if project_scope is None:
        raise ValueError(f"Active project '{active_project.id}' has no resolvable scope")
    return project_scope


def resolve_time_window(
    since: datetime | str | None,
    until: datetime | str | None,
    default_days: int,
) -> tuple[datetime, datetime]:
    """Resolve a UTC-normalized inclusive query window.

    If ``since`` is omitted, it defaults to ``until - default_days``.
    If ``until`` is omitted, the current UTC timestamp is used.
    Naive datetimes are assumed to already be UTC.
    """
    if default_days < 0:
        raise ValueError("default_days must be non-negative")

    resolved_until = _coerce_datetime(until) or datetime.now(timezone.utc)
    resolved_since = _coerce_datetime(since) or (resolved_until - timedelta(days=default_days))

    if resolved_since > resolved_until:
        raise ValueError("since must be less than or equal to until")

    return resolved_since, resolved_until


def normalize_entity_ids(*entity_groups: Any) -> list[str]:
    """Normalize one or more entity-id inputs into a stable deduplicated list.

    Accepts strings, iterables of strings, ``None``, and nested iterables.
    Empty values are removed. Output order preserves first appearance.
    """
    normalized: list[str] = []
    seen: set[str] = set()

    for group in entity_groups:
        for entity_id in _flatten_entity_group(group):
            if entity_id in seen:
                continue
            seen.add(entity_id)
            normalized.append(entity_id)

    return normalized


def _coerce_datetime(value: datetime | str | None) -> datetime | None:
    """Convert an input datetime or ISO string into an aware UTC datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _flatten_entity_group(value: Any) -> list[str]:
    """Flatten nested entity-id inputs into normalized string identifiers."""
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, Iterable):
        flattened: list[str] = []
        for item in value:
            flattened.extend(_flatten_entity_group(item))
        return flattened
    text = str(value).strip()
    return [text] if text else []


__all__ = [
    "normalize_entity_ids",
    "resolve_project_scope",
    "resolve_time_window",
]

# Made with Bob
