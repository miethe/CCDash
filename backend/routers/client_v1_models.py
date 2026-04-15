"""Shared and compatibility DTOs for the versioned CCDash client API (v1)."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field

from ccdash_contracts import (
    ClientV1Envelope,
    ClientV1ErrorDetail,
    ClientV1ErrorEnvelope,
    ClientV1Meta,
    ClientV1PaginatedEnvelope,
    ClientV1PaginatedMeta,
    FeatureSummaryDTO,
    InstanceMetaDTO,
)

from backend.application.services.agent_queries.models import DocumentRef, SessionRef


def build_client_v1_meta(*, instance_id: str = "") -> ClientV1Meta:
    """Populate the shared metadata model with the server-side defaults."""
    return ClientV1Meta(
        generated_at=datetime.now(timezone.utc),
        instance_id=instance_id,
        request_id=str(uuid4()),
    )


def build_client_v1_paginated_meta(
    *,
    instance_id: str = "",
    cursor: str | None = None,
    has_more: bool = False,
    total: int = 0,
    limit: int = 50,
    offset: int = 0,
    truncated: bool = False,
) -> ClientV1PaginatedMeta:
    """Populate paginated metadata using the shared contract type."""
    return ClientV1PaginatedMeta(
        generated_at=datetime.now(timezone.utc),
        instance_id=instance_id,
        request_id=str(uuid4()),
        cursor=cursor,
        has_more=has_more,
        total=total,
        limit=limit,
        offset=offset,
        truncated=truncated,
    )


# NOTE:
# The shared package is now the source of truth for public envelope/meta models
# plus the DTOs whose field shapes already match the live API surface.
#
# The feature/session document refs below still depend on richer backend-owned
# query-service DTOs. Keeping these as thin router-local compatibility models
# avoids widening this remediation into a service-layer/public-contract rewrite.


class FeatureSessionsDTO(BaseModel):
    feature_id: str
    feature_slug: str = ""
    sessions: list[SessionRef] = Field(default_factory=list)
    total: int = 0


class FeatureDocumentsDTO(BaseModel):
    feature_id: str
    feature_slug: str = ""
    documents: list[DocumentRef] = Field(default_factory=list)


class SessionFamilyDTO(BaseModel):
    root_session_id: str
    session_count: int = 0
    members: list[SessionRef] = Field(default_factory=list)


__all__ = [
    "ClientV1Envelope",
    "ClientV1ErrorDetail",
    "ClientV1ErrorEnvelope",
    "ClientV1Meta",
    "ClientV1PaginatedEnvelope",
    "ClientV1PaginatedMeta",
    "FeatureDocumentsDTO",
    "FeatureSessionsDTO",
    "FeatureSummaryDTO",
    "InstanceMetaDTO",
    "SessionFamilyDTO",
    "build_client_v1_meta",
    "build_client_v1_paginated_meta",
]
