"""Response envelope types for CCDash client API v1."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ClientV1Meta(BaseModel):
    generated_at: datetime | None = None
    instance_id: str = ""
    request_id: str = ""


class ClientV1Envelope(BaseModel, Generic[T]):
    status: Literal["ok", "partial", "error"] = "ok"
    data: T
    meta: ClientV1Meta = Field(default_factory=ClientV1Meta)


class ClientV1PaginatedMeta(ClientV1Meta):
    cursor: str | None = None
    has_more: bool = False
    total: int = 0
    limit: int = 50
    offset: int = 0
    truncated: bool = False


class ClientV1PaginatedEnvelope(BaseModel, Generic[T]):
    status: Literal["ok", "partial", "error"] = "ok"
    data: list[T]
    meta: ClientV1PaginatedMeta = Field(default_factory=ClientV1PaginatedMeta)


class ClientV1ErrorDetail(BaseModel):
    code: str = ""
    message: str = ""
    detail: dict[str, Any] = Field(default_factory=dict)


class ClientV1ErrorEnvelope(BaseModel):
    status: Literal["error"] = "error"
    error: ClientV1ErrorDetail
    meta: ClientV1Meta = Field(default_factory=ClientV1Meta)
