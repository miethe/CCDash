"""DTOs and envelope models for the versioned CCDash client API (v1)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field

from backend.application.services.agent_queries.models import DocumentRef, SessionRef

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Core envelope types
# ---------------------------------------------------------------------------


class ClientV1Meta(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    instance_id: str = ""
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class ClientV1Envelope(BaseModel, Generic[T]):
    status: Literal["ok", "partial", "error"] = "ok"
    data: T
    meta: ClientV1Meta = Field(default_factory=ClientV1Meta)


# ---------------------------------------------------------------------------
# Paginated envelope
# ---------------------------------------------------------------------------


class ClientV1PaginatedMeta(ClientV1Meta):
    cursor: str | None = None
    has_more: bool = False
    total: int = 0
    limit: int = 50
    offset: int = 0


class ClientV1PaginatedEnvelope(BaseModel, Generic[T]):
    status: Literal["ok", "partial", "error"] = "ok"
    data: list[T]
    meta: ClientV1PaginatedMeta = Field(default_factory=ClientV1PaginatedMeta)


# ---------------------------------------------------------------------------
# Error envelope
# ---------------------------------------------------------------------------


class ClientV1ErrorDetail(BaseModel):
    code: Literal["NOT_FOUND", "INVALID_PARAM", "SERVER_ERROR", "UNAUTHORIZED", "UNAVAILABLE"]
    message: str = ""
    detail: dict[str, Any] = Field(default_factory=dict)


class ClientV1ErrorEnvelope(BaseModel):
    status: Literal["error"] = "error"
    error: ClientV1ErrorDetail
    meta: ClientV1Meta = Field(default_factory=ClientV1Meta)


# ---------------------------------------------------------------------------
# Instance metadata DTO
# ---------------------------------------------------------------------------


class InstanceMetaDTO(BaseModel):
    instance_id: str
    version: str
    environment: str
    db_backend: str
    capabilities: list[str]
    server_time: datetime


# ---------------------------------------------------------------------------
# Feature DTOs
# ---------------------------------------------------------------------------


class FeatureSummaryDTO(BaseModel):
    id: str
    name: str = ""
    status: str = ""
    category: str = ""
    priority: str = ""
    total_tasks: int = 0
    completed_tasks: int = 0
    updated_at: str = ""


class FeatureSessionsDTO(BaseModel):
    feature_id: str
    feature_slug: str = ""
    sessions: list[SessionRef] = Field(default_factory=list)
    total: int = 0


class FeatureDocumentsDTO(BaseModel):
    feature_id: str
    feature_slug: str = ""
    documents: list[DocumentRef] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Session family DTO
# ---------------------------------------------------------------------------


class SessionFamilyDTO(BaseModel):
    root_session_id: str
    session_count: int = 0
    members: list[SessionRef] = Field(default_factory=list)
