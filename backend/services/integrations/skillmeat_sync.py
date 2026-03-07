"""SkillMeat definition sync orchestration."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.db.factory import get_agentic_intelligence_repository
from backend.services.integrations.skillmeat_client import SkillMeatClient, SkillMeatClientError


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def sync_skillmeat_definitions(db: Any, project: Any) -> dict[str, Any]:
    repo = get_agentic_intelligence_repository(db)
    config = getattr(project, "skillMeat", None)
    project_id = str(getattr(project, "id", "") or "")
    if config is None:
        config = type("SkillMeatConfig", (), {"enabled": False, "baseUrl": "", "projectId": "", "workspaceId": "", "requestTimeoutSeconds": 5.0})()

    source = await repo.upsert_definition_source(
        {
            "project_id": project_id,
            "source_kind": "skillmeat",
            "enabled": bool(getattr(config, "enabled", False)),
            "base_url": str(getattr(config, "baseUrl", "") or ""),
            "project_mapping": {
                "projectId": str(getattr(config, "projectId", "") or ""),
                "workspaceId": str(getattr(config, "workspaceId", "") or ""),
            },
            "feature_flags": {},
        }
    )

    warnings: list[dict[str, Any]] = []
    fetched_at = _now_iso()
    counts_by_type = {"artifact": 0, "workflow": 0, "context_module": 0}

    if not bool(getattr(config, "enabled", False)):
        warnings.append(
            {
                "section": "config",
                "message": "SkillMeat integration is disabled for this project.",
                "recoverable": True,
            }
        )
        updated_source = await repo.update_definition_source_status(
            project_id,
            "skillmeat",
            last_synced_at=fetched_at,
            last_sync_status="skipped",
            last_sync_error="",
        )
        return {
            "projectId": project_id,
            "source": updated_source or source,
            "totalDefinitions": 0,
            "countsByType": counts_by_type,
            "fetchedAt": fetched_at,
            "warnings": warnings,
        }

    base_url = str(getattr(config, "baseUrl", "") or "").strip()
    if not base_url:
        warnings.append(
            {
                "section": "config",
                "message": "SkillMeat base URL is missing.",
                "recoverable": True,
            }
        )
        updated_source = await repo.update_definition_source_status(
            project_id,
            "skillmeat",
            last_synced_at=fetched_at,
            last_sync_status="skipped",
            last_sync_error="base_url_missing",
        )
        return {
            "projectId": project_id,
            "source": updated_source or source,
            "totalDefinitions": 0,
            "countsByType": counts_by_type,
            "fetchedAt": fetched_at,
            "warnings": warnings,
        }

    client = SkillMeatClient(
        base_url=base_url,
        timeout_seconds=float(getattr(config, "requestTimeoutSeconds", 5.0) or 5.0),
    )

    for definition_type in ("artifact", "workflow", "context_module"):
        try:
            items = await client.fetch_definitions(
                definition_type=definition_type,
                project_id=str(getattr(config, "projectId", "") or ""),
                workspace_id=str(getattr(config, "workspaceId", "") or ""),
            )
            counts_by_type[definition_type] = len(items)
            for item in items:
                await repo.upsert_external_definition(
                    {
                        "project_id": project_id,
                        "source_id": source.get("id"),
                        "definition_type": definition_type,
                        "external_id": item.get("external_id", ""),
                        "display_name": item.get("display_name", ""),
                        "version": item.get("version", ""),
                        "source_url": item.get("source_url", ""),
                        "resolution_metadata": item.get("resolution_metadata", {}),
                        "raw_snapshot": item.get("raw_snapshot", {}),
                        "fetched_at": fetched_at,
                    }
                )
        except SkillMeatClientError as exc:
            warnings.append(
                {
                    "section": definition_type,
                    "message": str(exc),
                    "recoverable": True,
                }
            )

    status = "ok" if not warnings else "degraded"
    error_text = "" if not warnings else "; ".join(str(item.get("message") or "") for item in warnings[:5])
    updated_source = await repo.update_definition_source_status(
        project_id,
        "skillmeat",
        last_synced_at=fetched_at,
        last_sync_status=status,
        last_sync_error=error_text,
    )

    return {
        "projectId": project_id,
        "source": updated_source or source,
        "totalDefinitions": sum(counts_by_type.values()),
        "countsByType": counts_by_type,
        "fetchedAt": fetched_at,
        "warnings": warnings,
    }
