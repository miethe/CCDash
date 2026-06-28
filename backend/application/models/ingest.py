"""Pydantic request/response models for the NDJSON session ingest endpoint.

ADR-006: POST /api/v1/ingest/sessions — chunked NDJSON transport.
Schema is intentionally stable: the daemon reads these field names directly.
"""
from __future__ import annotations

from typing import Any

from pydantic import ConfigDict, BaseModel


class IngestSessionEvent(BaseModel):
    """A single session event submitted by the daemon in an NDJSON batch.

    ``extra="allow"`` enables forward-compat per ADR-006 F-6: unknown
    top-level fields from a newer daemon are silently accepted so that a
    schema-version N daemon can talk to an N-1 server without rejection.
    """

    model_config = ConfigDict(extra="allow")

    event_id: str          # UUID (v4 in tests, v7 from daemon)
    batch_id: str          # UUID grouping events in the same POST
    schema_version: str = "1.0"
    occurred_at: str       # ISO-8601 timestamp from the originating workstation
    payload: dict[str, Any]
    source_ref: str | None = None  # optional override; normally computed server-side


class RejectedEvent(BaseModel):
    """Describes a single event that could not be processed."""

    event_id: str | None
    reason: str
    code: str


class IngestBatchResponse(BaseModel):
    """Aggregated result of one NDJSON batch POST."""

    accepted: int
    rejected: list[RejectedEvent]
    dead_lettered: list[RejectedEvent]
    cursor_advanced_to: str | None


__all__ = [
    "IngestSessionEvent",
    "RejectedEvent",
    "IngestBatchResponse",
]
