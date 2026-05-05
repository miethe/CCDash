"""SkillMeat definition sync orchestration."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.db.factory import get_agentic_intelligence_repository
from backend.services.integrations.skillmeat_client import SkillMeatClient, SkillMeatClientError
from backend.services.integrations.skillmeat_contracts import (
    annotate_effective_workflows,
    attach_bundle_detail,
    attach_context_module_preview,
    attach_workflow_detail,
    attach_workflow_executions,
    resolve_workflow_context_modules,
)
from backend.services.integrations.skillmeat_routes import attach_stable_definition_source
from backend.services.integrations.skillmeat_trust import build_skillmeat_trust_metadata


_MAX_WORKFLOW_DETAIL_CALLS = 50
_MAX_WORKFLOW_PLAN_CALLS = 20
_MAX_CONTEXT_PREVIEW_CALLS = 5
_MAX_WORKFLOW_EXECUTION_WORKFLOWS = 10
_MAX_WORKFLOW_EXECUTION_DETAIL_CALLS = 15


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
    web_base_url: str,
    source_project_id: str,
    collection_id: str,
) -> None:
    for item in items:
        stored_item = attach_stable_definition_source(
            item,
            web_base_url=web_base_url,
            project_id=source_project_id,
            collection_id=collection_id,
        )
        await repo.upsert_external_definition(
            {
                "project_id": project_id,
                "source_id": source_id,
                "definition_type": definition_type,
                "external_id": stored_item.get("external_id", ""),
                "display_name": stored_item.get("display_name", ""),
                "version": stored_item.get("version", ""),
                "source_url": stored_item.get("source_url", ""),
                "resolution_metadata": stored_item.get("resolution_metadata", {}),
                "raw_snapshot": stored_item.get("raw_snapshot", {}),
                "fetched_at": fetched_at,
            }
        )


async def sync_skillmeat_definitions(
    db: Any,
    project: Any,
    *,
    context: Any | None = None,
) -> dict[str, Any]:
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
        trust_metadata=build_skillmeat_trust_metadata(
            context,
            delegation_reason="skillmeat.definition.sync",
        ),
    )

    configured_project_id = str(getattr(config, "projectId", "") or "")
    configured_collection_id = str(getattr(config, "collectionId", "") or "")
    configured_web_base_url = str(getattr(config, "webBaseUrl", "") or "").strip()
    context_module_items: list[dict[str, Any]] = []
    workflow_items: list[dict[str, Any]] = []

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
            web_base_url=configured_web_base_url,
            source_project_id=configured_project_id,
            collection_id=configured_collection_id,
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
        context_module_items = await client.fetch_definitions(
            definition_type="context_module",
            project_id=configured_project_id,
        )
        counts_by_type["context_module"] = len(context_module_items)
    except SkillMeatClientError as exc:
        warnings.append(
            {
                "section": "context_module",
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
        plan_calls = 0
        execution_workflow_calls = 0
        execution_detail_calls = 0
        for index, item in enumerate(workflow_items):
            if index >= _MAX_WORKFLOW_DETAIL_CALLS:
                break
            workflow_id = str(item.get("external_id") or "").strip()
            if not workflow_id:
                continue
            workflow_detail: dict[str, Any] | None = None
            workflow_plan: dict[str, Any] | None = None
            workflow_executions: list[dict[str, Any]] = []
            try:
                workflow_detail = await client.get_workflow(workflow_id)
            except SkillMeatClientError as exc:
                warnings.append(
                    {
                        "section": "workflow_detail",
                        "message": str(exc),
                        "recoverable": True,
                    }
                )
            if bool(item.get("resolution_metadata", {}).get("isEffective")) and plan_calls < _MAX_WORKFLOW_PLAN_CALLS:
                try:
                    workflow_plan = await client.plan_workflow(workflow_id)
                    plan_calls += 1
                except SkillMeatClientError as exc:
                    warnings.append(
                        {
                            "section": "workflow_plan",
                            "message": str(exc),
                            "recoverable": True,
                        }
                    )
            if (
                bool(item.get("resolution_metadata", {}).get("isEffective"))
                and execution_workflow_calls < _MAX_WORKFLOW_EXECUTION_WORKFLOWS
            ):
                try:
                    execution_list = await client.list_workflow_executions(
                        workflow_id=workflow_id,
                        limit=3,
                    )
                    execution_workflow_calls += 1
                    for execution_item in execution_list:
                        execution_id = str(execution_item.get("id") or "").strip()
                        if not execution_id:
                            workflow_executions.append(execution_item)
                            continue
                        if execution_detail_calls >= _MAX_WORKFLOW_EXECUTION_DETAIL_CALLS:
                            workflow_executions.append(execution_item)
                            continue
                        try:
                            execution_detail = await client.get_workflow_execution(execution_id)
                            execution_detail_calls += 1
                            workflow_executions.append(execution_detail or execution_item)
                        except SkillMeatClientError as exc:
                            warnings.append(
                                {
                                    "section": "workflow_execution_detail",
                                    "message": str(exc),
                                    "recoverable": True,
                                }
                            )
                            workflow_executions.append(execution_item)
                except SkillMeatClientError as exc:
                    warnings.append(
                        {
                            "section": "workflow_execution",
                            "message": str(exc),
                            "recoverable": True,
                        }
                    )
            workflow_items[index] = attach_workflow_detail(
                item,
                workflow_detail=workflow_detail,
                workflow_plan=workflow_plan,
            )
            if workflow_executions:
                workflow_items[index] = attach_workflow_executions(workflow_items[index], workflow_executions)
        if context_module_items:
            workflow_items = [
                resolve_workflow_context_modules(
                    item,
                    context_modules=context_module_items,
                    preview_summaries={},
                )
                for item in workflow_items
            ]
            preview_targets: list[str] = []
            seen_preview_targets: set[str] = set()
            for item in workflow_items:
                if not bool(item.get("resolution_metadata", {}).get("isEffective")):
                    continue
                resolved = item.get("resolution_metadata", {}).get("resolvedContextModules", [])
                if not isinstance(resolved, list):
                    continue
                for ref in resolved:
                    if not isinstance(ref, dict):
                        continue
                    module_id = str(ref.get("moduleId") or "").strip()
                    if not module_id or module_id in seen_preview_targets:
                        continue
                    preview_targets.append(module_id)
                    seen_preview_targets.add(module_id)
                    if len(preview_targets) >= _MAX_CONTEXT_PREVIEW_CALLS:
                        break
                if len(preview_targets) >= _MAX_CONTEXT_PREVIEW_CALLS:
                    break

            preview_summaries: dict[str, dict[str, Any]] = {}
            if configured_project_id:
                for module_id in preview_targets:
                    try:
                        preview_payload = await client.preview_context_pack(
                            project_id=configured_project_id,
                            module_id=module_id,
                        )
                        preview_summaries[module_id] = preview_payload
                    except SkillMeatClientError as exc:
                        warnings.append(
                            {
                                "section": "context_preview",
                                "message": str(exc),
                                "recoverable": True,
                            }
                        )
                if preview_summaries:
                    for index, item in enumerate(context_module_items):
                        module_id = str(item.get("external_id") or "").strip()
                        if module_id in preview_summaries:
                            context_module_items[index] = attach_context_module_preview(item, preview_summaries[module_id])
                    preview_summaries = {
                        str(item.get("external_id") or "").strip(): dict(item.get("resolution_metadata", {})).get("previewSummary")
                        for item in context_module_items
                        if isinstance(dict(item.get("resolution_metadata", {})).get("previewSummary"), dict)
                    }

            workflow_items = [
                resolve_workflow_context_modules(
                    item,
                    context_modules=context_module_items,
                    preview_summaries=preview_summaries,
                )
                for item in workflow_items
            ]
        counts_by_type["workflow"] = len(workflow_items)
        await _store_definitions(
            repo,
            source_id=source.get("id"),
            project_id=project_id,
            definition_type="workflow",
            items=workflow_items,
            fetched_at=fetched_at,
            web_base_url=configured_web_base_url,
            source_project_id=configured_project_id,
            collection_id=configured_collection_id,
        )
    except SkillMeatClientError as exc:
        warnings.append(
            {
                "section": "workflow",
                "message": str(exc),
                "recoverable": True,
            }
        )

    if context_module_items:
        await _store_definitions(
            repo,
            source_id=source.get("id"),
            project_id=project_id,
            definition_type="context_module",
            items=context_module_items,
            fetched_at=fetched_at,
            web_base_url=configured_web_base_url,
            source_project_id=configured_project_id,
            collection_id=configured_collection_id,
        )

    try:
        bundle_items = await client.fetch_definitions(definition_type="bundle")
        detailed_bundles: list[dict[str, Any]] = []
        for item in bundle_items:
            bundle_id = str(item.get("external_id") or "").strip()
            if not bundle_id:
                detailed_bundles.append(attach_bundle_detail(item))
                continue
            try:
                detail = await client.get_bundle(bundle_id)
                enriched = dict(item)
                raw_snapshot = detail if detail else item.get("raw_snapshot", {})
                enriched["raw_snapshot"] = raw_snapshot
                metadata = dict(item.get("resolution_metadata", {}))
                metadata["artifactCount"] = len(raw_snapshot.get("artifacts", [])) if isinstance(raw_snapshot, dict) else metadata.get("artifactCount", 0)
                enriched["resolution_metadata"] = metadata
                detailed_bundles.append(attach_bundle_detail(enriched))
            except SkillMeatClientError as exc:
                warnings.append(
                    {
                        "section": "bundle_detail",
                        "message": str(exc),
                        "recoverable": True,
                    }
                )
                detailed_bundles.append(attach_bundle_detail(item))
        counts_by_type["bundle"] = len(detailed_bundles)
        await _store_definitions(
            repo,
            source_id=source.get("id"),
            project_id=project_id,
            definition_type="bundle",
            items=detailed_bundles,
            fetched_at=fetched_at,
            web_base_url=configured_web_base_url,
            source_project_id=configured_project_id,
            collection_id=configured_collection_id,
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
