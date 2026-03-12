"""Global AI platform pricing catalog API."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend.db import connection
from backend.db.factory import get_pricing_catalog_repository, get_session_repository
from backend.models import PricingCatalogEntry, PricingCatalogSyncResponse, PricingCatalogUpsertRequest
from backend.project_manager import project_manager
from backend.services.pricing_catalog import PricingCatalogService

pricing_router = APIRouter(prefix="/api/pricing", tags=["pricing"])


def _active_project() -> Any:
    project = project_manager.get_active_project()
    if not project:
        raise HTTPException(status_code=400, detail="No active project")
    return project


def _service_for_db(db: Any) -> PricingCatalogService:
    return PricingCatalogService(get_pricing_catalog_repository(db), get_session_repository(db))


@pricing_router.get("/catalog", response_model=list[PricingCatalogEntry])
async def get_pricing_catalog(
    platformType: str | None = Query(default=None),
):
    db = await connection.get_connection()
    service = _service_for_db(db)
    return await service.list_catalog_entries(platformType)


@pricing_router.put("/catalog", response_model=PricingCatalogEntry)
async def upsert_pricing_catalog_entry(payload: PricingCatalogUpsertRequest):
    db = await connection.get_connection()
    service = _service_for_db(db)
    return await service.upsert_catalog_entry(payload.model_dump())


@pricing_router.post("/catalog/sync", response_model=PricingCatalogSyncResponse)
async def sync_pricing_catalog(
    platformType: str = Query(default="Claude Code"),
):
    db = await connection.get_connection()
    service = _service_for_db(db)
    return await service.sync_catalog_entries(platformType)


@pricing_router.post("/catalog/reset")
async def reset_pricing_catalog_entry(
    platformType: str = Query(...),
    modelId: str = Query(default=""),
):
    db = await connection.get_connection()
    service = _service_for_db(db)
    entry = await service.reset_catalog_entry(platformType, modelId)
    return {"status": "ok", "entry": entry}


@pricing_router.delete("/catalog/entry")
async def delete_pricing_catalog_entry(
    platformType: str = Query(...),
    modelId: str = Query(...),
):
    db = await connection.get_connection()
    service = _service_for_db(db)
    try:
        await service.delete_catalog_entry(platformType, modelId)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok"}
