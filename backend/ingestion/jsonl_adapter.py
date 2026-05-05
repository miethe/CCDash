"""JSONL parser bridge for normalized session ingestion."""
from __future__ import annotations

from typing import Any

from backend.ingestion.models import (
    IngestSource,
    MergePolicy,
    NormalizedSessionEnvelope,
    SourceProvenance,
)


def _normalize_platform_type(value: Any) -> str:
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if raw in {"claude", "claude_code"}:
        return "claude_code"
    return raw


def jsonl_session_to_envelope(
    session: Any,
    *,
    source_identity: str,
    source_uri: str = "",
) -> NormalizedSessionEnvelope:
    """Wrap an existing parsed JSONL session in the shared ingest contract."""
    payload = session.model_dump() if hasattr(session, "model_dump") else dict(session)
    session_id = str(payload.get("id") or "").strip()
    platform_type = _normalize_platform_type(payload.get("platformType") or payload.get("platform_type"))
    provenance = SourceProvenance(
        source=IngestSource.JSONL,
        platform_type=platform_type,
        source_identity=source_identity,
        confidence=1.0,
        source_uri=source_uri,
        attributes={"ingest_adapter": "jsonl"},
    )
    return NormalizedSessionEnvelope(
        session_id=session_id,
        source=IngestSource.JSONL,
        merge_policy=MergePolicy.UPSERT_COMPLETE,
        platform_type=platform_type,
        source_identity=source_identity,
        confidence=1.0,
        provenance=provenance,
        session=payload,
        logs=payload.get("logs") if isinstance(payload.get("logs"), list) else [],
        tool_calls=payload.get("toolsUsed") if isinstance(payload.get("toolsUsed"), list) else [],
        file_updates=payload.get("updatedFiles") if isinstance(payload.get("updatedFiles"), list) else [],
        artifacts=payload.get("linkedArtifacts") if isinstance(payload.get("linkedArtifacts"), list) else [],
        relationships=payload.get("sessionRelationships") if isinstance(payload.get("sessionRelationships"), list) else [],
        raw_refs=[source_identity],
    )
