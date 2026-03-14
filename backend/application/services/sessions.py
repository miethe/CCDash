"""Application services for session read paths."""
from __future__ import annotations

from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.model_identity import derive_model_identity

from backend.application.services.common import resolve_project


class SessionFacetService:
    async def get_model_facets(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        include_subagents: bool = True,
    ) -> list[dict[str, str | int]]:
        project = resolve_project(context, ports)
        if project is None:
            return []

        rows = await ports.storage.sessions().get_model_facets(
            project.id,
            include_subagents=include_subagents,
        )
        items: list[dict[str, str | int]] = []
        for row in rows:
            raw_model = str(row.get("model") or "")
            identity = derive_model_identity(raw_model)
            items.append(
                {
                    "raw": raw_model,
                    "modelDisplayName": identity["modelDisplayName"],
                    "modelProvider": identity["modelProvider"],
                    "modelFamily": identity["modelFamily"],
                    "modelVersion": identity["modelVersion"],
                    "count": int(row.get("count") or 0),
                }
            )
        return items

    async def get_platform_facets(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        include_subagents: bool = True,
    ) -> list[dict[str, str | int]]:
        project = resolve_project(context, ports)
        if project is None:
            return []

        rows = await ports.storage.sessions().get_platform_facets(
            project.id,
            include_subagents=include_subagents,
        )
        return [
            {
                "platformType": str(row.get("platform_type") or "Claude Code").strip() or "Claude Code",
                "platformVersion": str(row.get("platform_version") or "").strip(),
                "count": int(row.get("count") or 0),
            }
            for row in rows
        ]
