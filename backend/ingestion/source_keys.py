"""Deterministic source keys for normalized ingestion idempotency."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from pathlib import PurePath
from typing import Any, Mapping, NewType


IngestSourceKey = NewType("IngestSourceKey", str)

SOURCE_KEY_SCHEME = "ccdash-ingest-source"
SOURCE_KEY_VERSION = "v1"
DIGEST_ALGORITHM = "sha256"
DIGEST_LENGTH = 32
UNRESOLVED_AGGREGATE_SCOPE = "unresolved"


@dataclass(frozen=True, slots=True)
class SourceKeyDigest:
    """Stable digest metadata for a canonical ingestion payload."""

    algorithm: str
    value: str
    canonical_json: str


def session_event_source_key(
    *,
    platform_type: str,
    source: str | Enum,
    session_id: str,
    event_kind: str,
    event: Mapping[str, Any],
) -> IngestSourceKey:
    """Return an idempotency key for a session-scoped metric or log event.

    Session-scoped events must carry a concrete ``session_id``. Aggregate OTel
    payloads that cannot resolve a session should use ``aggregate_source_key``
    so they remain explicit instead of being assigned to a synthetic session.
    """

    session = _required_component("session_id", session_id)
    digest = canonical_digest(event).value
    return _format_source_key(
        platform_type=platform_type,
        source=source,
        scope="session",
        scope_id=session,
        event_kind=event_kind,
        digest=digest,
    )


def aggregate_source_key(
    *,
    platform_type: str,
    source: str | Enum,
    aggregate_kind: str,
    aggregate_id: str | None,
    event: Mapping[str, Any],
) -> IngestSourceKey:
    """Return an idempotency key for a non-session aggregate payload.

    Blank or missing aggregate ids are represented with the explicit
    ``unresolved`` aggregate scope. They are not folded into a placeholder
    session id.
    """

    aggregate = _optional_component(aggregate_id) or UNRESOLVED_AGGREGATE_SCOPE
    digest = canonical_digest(event).value
    return _format_source_key(
        platform_type=platform_type,
        source=source,
        scope="aggregate",
        scope_id=aggregate,
        event_kind=aggregate_kind,
        digest=digest,
    )


def canonical_digest(payload: Mapping[str, Any]) -> SourceKeyDigest:
    """Hash canonical JSON with sorted keys for replay-stable idempotency."""

    canonical_json = canonical_json_dumps(payload)
    value = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()[:DIGEST_LENGTH]
    return SourceKeyDigest(
        algorithm=DIGEST_ALGORITHM,
        value=value,
        canonical_json=canonical_json,
    )


def canonical_json_dumps(payload: Mapping[str, Any]) -> str:
    """Serialize a mapping into deterministic, compact JSON."""

    normalized = _canonicalize(payload)
    if not isinstance(normalized, dict):
        raise TypeError("source key payload must be a mapping")
    return json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def _format_source_key(
    *,
    platform_type: str,
    source: str | Enum,
    scope: str,
    scope_id: str,
    event_kind: str,
    digest: str,
) -> IngestSourceKey:
    platform = _required_component("platform_type", platform_type)
    source_value = _required_component("source", _enum_value(source))
    scope_value = _required_component("scope", scope)
    scope_identity = _required_component("scope_id", scope_id)
    kind = _required_component("event_kind", event_kind)
    digest_value = _required_component("digest", digest)
    return IngestSourceKey(
        f"{SOURCE_KEY_SCHEME}:{SOURCE_KEY_VERSION}/"
        f"{platform}/{source_value}/{scope_value}/{scope_identity}/{kind}/{digest_value}"
    )


def _canonicalize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _canonicalize(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, tuple | list):
        return [_canonicalize(item) for item in value]
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.isoformat()
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, PurePath):
        return value.as_posix()
    if value is None or isinstance(value, str | int | float | bool):
        return value
    raise TypeError(f"unsupported source key payload value: {type(value).__name__}")


def _enum_value(value: str | Enum) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def _required_component(name: str, value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} cannot be blank")
    if "/" in normalized:
        raise ValueError(f"{name} cannot contain '/'")
    return normalized


def _optional_component(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None
