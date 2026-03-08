"""SkillMeat definition sync orchestration."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.db.factory import get_agentic_intelligence_repository
from backend.services.integrations.skillmeat_client import SkillMeatClient, SkillMeatClientError
from backend.services.integrations.skillmeat_contracts import annotate_effective_workflows


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _store_definitions(
    repo: Any,
    *,
    source_id: Any,
    project_id: str,
    definition_type: str,
    items: list[dict[str, Any]],
    fetched_at: str,
) -> None:
    for item in items:
        await repo.upsert_external_definition(
            {
                "project_id": project_id,
                "source_id": source_id,
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


async def sync_skillmeat_definitions(db: Any, project: Any) -> dict[str, Any]:
    repo = get_agentic_intelligence_repository(db)
    config = getattr(project, "skillMeat", None)
    project_id = str(getattr(project, "id", "") or "")
    if config is None:
        config = type(
            "SkillMeatConfig",
            (),
            {
                "enabled": False,
                "baseUrl": "",
                "projectId": "",
                "collectionId": "",
                "aaaEnabled": False,
                "apiKey": "",
                "requestTimeoutSeconds": 5.0,
            },
        )()

    source = await repo.upsert_definition_source(
        {
            "project_id": project_id,
            "source_kind": "skillmeat",
            "enabled": bool(getattr(config, "enabled", False)),
            "base_url": str(getattr(config, "baseUrl", "") or ""),
            "project_mapping": {
                "projectId": str(getattr(config, "projectId", "") or ""),
                "collectionId": str(getattr(config, "collectionId", "") or ""),
            },
            "feature_flags": getattr(getattr(config, "featureFlags", {}), "model_dump", lambda: getattr(config, "featureFlags", {}))(),
        }
    )

    warnings: list[dict[str, Any]] = []
    fetched_at = _now_iso()
    counts_by_type = {"artifact": 0, "workflow": 0, "context_module": 0, "bundle": 0}

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
        aaa_enabled=bool(getattr(config, "aaaEnabled", False)),
        api_key=str(getattr(config, "apiKey", "") or ""),
    )

    configured_project_id = str(getattr(config, "projectId", "") or "")
    configured_collection_id = str(getattr(config, "collectionId", "") or "")

    try:
        artifact_items = await client.fetch_definitions(
            definition_type="artifact",
            collection_id=configured_collection_id,
        )
        counts_by_type["artifact"] = len(artifact_items)
        await _store_definitions(
            repo,
            source_id=source.get("id"),
            project_id=project_id,
            definition_type="artifact",
            items=artifact_items,
            fetched_at=fetched_at,
        )
    except SkillMeatClientError as exc:
        warnings.append(
            {
                "section": "artifact",
                "message": str(exc),
                "recoverable": True,
            }
        )

    try:
        global_workflow_items = await client.fetch_definitions(definition_type="workflow")
        project_workflow_items = await client.fetch_definitions(
            definition_type="workflow",
            project_id=configured_project_id,
        )
        workflow_items = annotate_effective_workflows(
            [
                *global_workflow_items,
                *project_workflow_items,
            ]
        )
        counts_by_type["workflow"] = len(workflow_items)
        await _store_definitions(
            repo,
            source_id=source.get("id"),
            project_id=project_id,
            definition_type="workflow",
            items=workflow_items,
            fetched_at=fetched_at,
        )
    except SkillMeatClientError as exc:
        warnings.append(
            {
                "section": "workflow",
                "message": str(exc),
                "recoverable": True,
            }
        )

    try:
        context_module_items = await client.fetch_definitions(
            definition_type="context_module",
            project_id=configured_project_id,
        )
        counts_by_type["context_module"] = len(context_module_items)
        await _store_definitions(
            repo,
            source_id=source.get("id"),
            project_id=project_id,
            definition_type="context_module",
            items=context_module_items,
            fetched_at=fetched_at,
        )
    except SkillMeatClientError as exc:
        warnings.append(
            {
                "section": "context_module",
                "message": str(exc),
                "recoverable": True,
            }
        )

    try:
        bundle_items = await client.fetch_definitions(definition_type="bundle")
        detailed_bundles: list[dict[str, Any]] = []
        for item in bundle_items:
            bundle_id = str(item.get("external_id") or "").strip()
            if not bundle_id:
                detailed_bundles.append(item)
                continue
            try:
                detail = await client.get_bundle(bundle_id)
                enriched = dict(item)
                raw_snapshot = detail if detail else item.get("raw_snapshot", {})
                enriched["raw_snapshot"] = raw_snapshot
                metadata = dict(item.get("resolution_metadata", {}))
                metadata["artifactCount"] = len(raw_snapshot.get("artifacts", [])) if isinstance(raw_snapshot, dict) else metadata.get("artifactCount", 0)
                enriched["resolution_metadata"] = metadata
                detailed_bundles.append(enriched)
            except SkillMeatClientError as exc:
                warnings.append(
                    {
                        "section": "bundle_detail",
                        "message": str(exc),
                        "recoverable": True,
                    }
                )
                detailed_bundles.append(item)
        counts_by_type["bundle"] = len(detailed_bundles)
        await _store_definitions(
            repo,
            source_id=source.get("id"),
            project_id=project_id,
            definition_type="bundle",
            items=detailed_bundles,
            fetched_at=fetched_at,
        )
    except SkillMeatClientError as exc:
        warnings.append(
            {
                "section": "bundle",
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
