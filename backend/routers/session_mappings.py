"""Session mapping configuration API."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.db import connection
from backend.project_manager import project_manager
from backend.session_mappings import load_session_mappings, save_session_mappings

session_mappings_router = APIRouter(prefix="/api/session-mappings", tags=["session-mappings"])


class SessionMappingRule(BaseModel):
    id: str
    mappingType: str = "bash"
    label: str
    category: str = "bash"
    pattern: str
    transcriptLabel: str
    sessionTypeLabel: str = ""
    matchScope: str = "command"
    fieldMappings: list[dict[str, Any]] = Field(default_factory=list)
    enabled: bool = True
    priority: int = 10


class SessionMappingsPayload(BaseModel):
    mappings: list[SessionMappingRule]


@session_mappings_router.get("", response_model=list[SessionMappingRule])
async def list_session_mappings():
    project = project_manager.get_active_project()
    if not project:
        return []
    db = await connection.get_connection()
    mappings = await load_session_mappings(db, project.id)
    return [SessionMappingRule(**m) for m in mappings]


@session_mappings_router.put("", response_model=list[SessionMappingRule])
async def update_session_mappings(payload: SessionMappingsPayload):
    project = project_manager.get_active_project()
    if not project:
        raise HTTPException(status_code=400, detail="No active project")
    db = await connection.get_connection()
    mapping_dicts: list[dict[str, Any]] = [m.model_dump() for m in payload.mappings]
    saved = await save_session_mappings(db, project.id, mapping_dicts)
    return [SessionMappingRule(**m) for m in saved]
