"""CCDash contracts — shared Pydantic DTOs for server and CLI."""
from __future__ import annotations

from ccdash_contracts.envelopes import (
    ClientV1Envelope,
    ClientV1ErrorDetail,
    ClientV1ErrorEnvelope,
    ClientV1Meta,
    ClientV1PaginatedEnvelope,
    ClientV1PaginatedMeta,
)
from ccdash_contracts.models import (
    DocumentRef,
    FeatureDocumentsDTO,
    FeatureSessionsDTO,
    FeatureSummaryDTO,
    InstanceMetaDTO,
    SessionFamilyDTO,
    SessionRef,
)

__all__ = [
    # envelopes
    "ClientV1Envelope",
    "ClientV1ErrorDetail",
    "ClientV1ErrorEnvelope",
    "ClientV1Meta",
    "ClientV1PaginatedEnvelope",
    "ClientV1PaginatedMeta",
    # models
    "DocumentRef",
    "FeatureDocumentsDTO",
    "FeatureSessionsDTO",
    "FeatureSummaryDTO",
    "InstanceMetaDTO",
    "SessionFamilyDTO",
    "SessionRef",
]
