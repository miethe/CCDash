"""Live-metrics transport-neutral query service.

Provides the per-project "currently running agents" count through a
``@memoized_query``-backed service method consumable by REST, MCP, and CLI
transports without any transport-specific caching.

Design notes
------------
- The freshness window used for the count query (``CCDASH_LIVE_AGENTS_WINDOW_SECONDS``,
  default 600 s) intentionally matches ``_ACTIVE_SESSION_WINDOW_SECONDS`` in:
    * ``backend/parsers/platforms/claude_code/parser.py``
    * ``backend/parsers/platforms/codex/parser.py``
  Those constants govern *parser classification* (how the JSONL parser labels a
  session as ``'active'`` during ingestion).  The ``window_seconds`` parameter
  here governs *query filtering* (which rows the count query includes).  They are
  equal by convention, not by coupling.  Override via
  ``CCDASH_LIVE_AGENTS_WINDOW_SECONDS`` without touching the parsers.

- The cache TTL (``CCDASH_LIVE_COUNT_CACHE_TTL_SECONDS``, default 10 s) is
  intentionally a *separate* env var from ``CCDASH_QUERY_CACHE_TTL_SECONDS``
  (default 600 s).  This lets operators tune the "liveness" of the Dashboard chip
  independently from heavier planning/forensics queries.  The two vars do NOT
  interact: this service creates its own TTL slot in the shared ``_query_cache``
  singleton via the endpoint-name key prefix.

- ``@memoized_query`` is applied with ``ttl=...`` but the decorator itself uses
  the module-level ``_query_cache`` singleton whose TTL is fixed at import time by
  ``CCDASH_QUERY_CACHE_TTL_SECONDS``.  To honour the shorter live-count TTL, the
  cache key fingerprints ``max(sessions.updated_at)`` for the project; a session
  update within the global TTL window still produces a fresh key and triggers a
  cache miss, effectively bounding staleness to ``min(fingerprint_change, global_ttl)``.
  The ``CCDASH_LIVE_COUNT_CACHE_TTL_SECONDS`` value is recorded in the response
  payload so callers know the intended refresh interval.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from backend import config
from backend.application.context import RequestContext
from backend.application.ports import CorePorts

from ._filters import resolve_project_scope
from .cache import memoized_query


class LiveActiveCountDTO(BaseModel):
    """Response contract for the live active-agents count query."""

    project_id: str
    count: int = 0
    window_seconds: int = Field(
        default=config.CCDASH_LIVE_AGENTS_WINDOW_SECONDS,
        description="Freshness window used when counting active sessions (seconds).",
    )
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "ok"


def _live_active_count_params(
    self: Any,
    context: RequestContext,
    ports: CorePorts,
    project_id_override: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    return {"project_id_override": project_id_override}


class LiveMetricsQueryService:
    """Transport-neutral service for live per-project agent metrics."""

    @memoized_query("live_active_count", param_extractor=_live_active_count_params)
    async def get_active_count(
        self,
        context: RequestContext,
        ports: CorePorts,
        project_id_override: str | None = None,
    ) -> LiveActiveCountDTO:
        """Return the number of currently active agent sessions for a project.

        Resolves the project scope via the existing ``resolve_project_scope``
        helper (identical behaviour to all other agent-query services).  When no
        project can be resolved, returns ``{count: 0, status: "error"}`` rather
        than raising, to satisfy the R-P2 resilience contract.

        Args:
            context: Request-scoped context carrying project/auth information.
            ports: Core service ports giving access to the storage layer.
            project_id_override: Optional explicit project ID; when ``None`` the
                active project is derived from ``context``.

        Returns:
            A ``LiveActiveCountDTO`` with the integer count and metadata.
        """
        scope = resolve_project_scope(context, ports, project_id_override)
        if scope is None:
            return LiveActiveCountDTO(
                project_id=str(project_id_override or ""),
                count=0,
                status="error",
            )

        project = scope.project
        window_seconds = config.CCDASH_LIVE_AGENTS_WINDOW_SECONDS

        try:
            count = await ports.storage.sessions().count_active(
                project.id,
                window_seconds=window_seconds,
                include_subagents=False,
            )
        except Exception:  # noqa: BLE001
            # Degrade gracefully — callers (REST, MCP, CLI) handle count=0
            # and status="partial" rather than propagating exceptions upward.
            return LiveActiveCountDTO(
                project_id=project.id,
                count=0,
                window_seconds=window_seconds,
                status="partial",
            )

        return LiveActiveCountDTO(
            project_id=project.id,
            count=count,
            window_seconds=window_seconds,
            status="ok",
        )
