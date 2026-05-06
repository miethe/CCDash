"""Source-neutral models for normalized session ingestion."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any

from pydantic import BaseModel, Field, StringConstraints, model_validator


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class IngestSource(str, Enum):
    """Supported upstream source families for normalized session ingest."""

    JSONL = "jsonl"
    OTEL = "otel"


class MergePolicy(str, Enum):
    """How persistence should apply an envelope to the canonical session rows."""

    UPSERT_COMPLETE = "upsert_complete"
    PATCH_METRICS = "patch_metrics"
    APPEND_EVENTS = "append_events"


class SourceProvenance(BaseModel):
    """Metadata that identifies where an envelope came from and how complete it is."""

    source: IngestSource
    platform_type: str = ""
    source_identity: Annotated[str, StringConstraints(min_length=1)]
    confidence: float = Field(1.0, ge=0.0, le=1.0)
    observed_at: datetime | None = None
    emitted_at: datetime | None = None
    received_at: datetime = Field(default_factory=_utc_now)
    source_started_at: datetime | None = None
    source_ended_at: datetime | None = None
    source_updated_at: datetime | None = None
    source_uri: str = ""
    attributes: dict[str, Any] = Field(default_factory=dict)


class NormalizedSessionEnvelope(BaseModel):
    """Normalized session payload accepted by future JSONL and OTel adapters.

    JSONL sources can provide complete session/message/tool payloads with
    ``UPSERT_COMPLETE``. OTel sources can provide partial metrics or structural
    events with additive merge policies.
    """

    session_id: Annotated[str, StringConstraints(min_length=1)]
    source: IngestSource
    merge_policy: MergePolicy = MergePolicy.UPSERT_COMPLETE
    platform_type: str = ""
    source_identity: Annotated[str, StringConstraints(min_length=1)]
    confidence: float = Field(1.0, ge=0.0, le=1.0)
    provenance: SourceProvenance
    source_started_at: datetime | None = None
    source_ended_at: datetime | None = None
    source_updated_at: datetime | None = None
    session: dict[str, Any] = Field(default_factory=dict)
    messages: list[dict[str, Any]] = Field(default_factory=list)
    logs: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    file_updates: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    usage: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    forensics: dict[str, Any] = Field(default_factory=dict)
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    raw_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _align_source_metadata(self) -> "NormalizedSessionEnvelope":
        if self.provenance.source != self.source:
            raise ValueError("provenance.source must match envelope source")
        if self.provenance.source_identity != self.source_identity:
            raise ValueError("provenance.source_identity must match envelope source_identity")
        if self.provenance.confidence != self.confidence:
            raise ValueError("provenance.confidence must match envelope confidence")
        if self.provenance.platform_type and self.platform_type:
            if self.provenance.platform_type != self.platform_type:
                raise ValueError("provenance.platform_type must match envelope platform_type")
        return self


class SessionIngestResult(BaseModel):
    """Transport-neutral result from persisting normalized session envelopes."""

    source: IngestSource
    merge_policy: MergePolicy
    accepted: bool = True
    session_ids: list[str] = Field(default_factory=list)
    inserted_session_ids: list[str] = Field(default_factory=list)
    updated_session_ids: list[str] = Field(default_factory=list)
    message_count: int = Field(0, ge=0)
    log_count: int = Field(0, ge=0)
    metric_count: int = Field(0, ge=0)
    relationship_count: int = Field(0, ge=0)
    warning_count: int = Field(0, ge=0)
    warnings: list[str] = Field(default_factory=list)
    processed_at: datetime = Field(default_factory=_utc_now)
