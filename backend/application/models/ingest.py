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


class RfEventPayload(BaseModel):
    """A single Research Foundry ``ccdash_event`` record.

    Phase 1 (research-foundry-run-telemetry-v1), T1-003.
    Mirrors ``research-foundry/schemas/ccdash_event.schema.yaml``, which
    declares ``additionalProperties: true`` at every level — RF is free to add
    new fields without a CCDash-side schema bump. ``extra="allow"`` here means
    a forward-compat field is accepted and preserved on the model (visible via
    ``model_dump()``/``model_extra``) even though it has no dedicated column;
    the raw payload is always persisted verbatim to ``rf_events.raw_payload_json``
    (T1-001) as the forward-compat safety net.

    Only ``event_id``/``timestamp``/``project`` are required, matching the
    schema's ``required`` block. Every other field is nullable and never
    defaulted — unknown == null, never a fabricated default.

    The nested groups (``metrics``/``governance``/``reuse``/``human_review``)
    are intentionally typed as ``dict[str, Any]`` rather than nested models:
    the schema declares ``additionalProperties: true`` on each of them too, so
    a strict nested model would either reject or silently drop RF-side fields
    that CCdash has not yet mapped to a dedicated column. The ingest service
    extracts known keys by name and leaves the rest to ``raw_payload_json``.
    """

    model_config = ConfigDict(extra="allow")

    event_id: str
    timestamp: str
    project: str

    run_id: str | None = None
    intent_id: str | None = None
    task_node_id: str | None = None

    agent_postures: list[str] | None = None
    skillbom_ids: list[str] | None = None
    tools: list[str] | None = None
    input_artifacts: list[str] | None = None
    output_artifacts: list[str] | None = None

    metrics: dict[str, Any] | None = None
    governance: dict[str, Any] | None = None
    reuse: dict[str, Any] | None = None
    human_review: dict[str, Any] | None = None


__all__ = [
    "IngestSessionEvent",
    "RejectedEvent",
    "IngestBatchResponse",
    "RfEventPayload",
]
