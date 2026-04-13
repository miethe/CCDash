"""Shared domain DTOs for CCDash client API v1."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class InstanceMetaDTO(BaseModel):
    instance_id: str = ""
    version: str = ""
    environment: str = ""
    db_backend: str = ""
    capabilities: list[str] = Field(default_factory=list)
    server_time: datetime | None = None


class SessionRef(BaseModel):
    session_id: str = ""
    title: str = ""
    model: str = ""
    total_cost: float = 0.0
    total_turns: int = 0
    started_at: str = ""


class DocumentRef(BaseModel):
    path: str = ""
    title: str = ""
    doc_type: str = ""


class FeatureSummaryDTO(BaseModel):
    id: str = ""
    name: str = ""
    status: str = ""
    category: str = ""
    priority: str = ""
    total_tasks: int = 0
    completed_tasks: int = 0
    updated_at: str = ""


class FeatureSessionsDTO(BaseModel):
    feature_id: str = ""
    feature_slug: str = ""
    sessions: list[SessionRef] = Field(default_factory=list)
    total: int = 0


class FeatureDocumentsDTO(BaseModel):
    feature_id: str = ""
    feature_slug: str = ""
    documents: list[DocumentRef] = Field(default_factory=list)


class SessionFamilyDTO(BaseModel):
    root_session_id: str = ""
    session_count: int = 0
    members: list[SessionRef] = Field(default_factory=list)
