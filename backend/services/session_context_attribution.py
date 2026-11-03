"""Read metadata-only context receipts through exact session/project/native joins.

Never opens a transcript, walks a home directory, writes the producer or converts
characters/bytes to tokens. Missing or ambiguous joins are explicit contract states.
"""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from backend import config
from backend.models import SessionContextAttribution, SessionContextStage

MAX_BYTES = 16 * 1024 * 1024
MAX_STAGES = 200
MAX_LAYERS = 64
UNITS = {"characters", "bytes", "tokens", "unknown"}


def _text(value: Any, fallback: str = "unrecorded", limit: int = 256) -> str:
    return value[:limit] if isinstance(value, str) and value else fallback


def _amount(value: Any) -> int | float | None:
    try:
        return (
            value
            if isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            and value >= 0
            else None
        )
    except OverflowError:
        return None


def _unit(value: Any) -> str:
    return value if isinstance(value, str) and value in UNITS else "unknown"


def _stage_time(stage: SessionContextStage) -> float:
    try:
        parsed = datetime.fromisoformat((stage.observedAt or "").replace("Z", "+00:00"))
        return parsed.timestamp() if parsed.tzinfo is not None else float("inf")
    except (ValueError, OverflowError):
        return float("inf")


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@lru_cache(maxsize=2)
def _read(path: str, mtime: int, size: int) -> dict:
    del mtime
    if size > MAX_BYTES:
        raise ValueError("source exceeds bounded size")
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("source exceeds bounded size")
    data = json.loads(raw)
    if (
        not isinstance(data, dict)
        or type(data.get("schemaVersion")) is not int
        or data["schemaVersion"] != 1
        or not isinstance(data.get("sessions"), list)
    ):
        raise ValueError("unsupported context receipt schema")
    return data


def _empty(
    join: str, reason: str, generated: str | None = None
) -> SessionContextAttribution:
    return SessionContextAttribution(
        generatedAt=generated,
        coverage={
            "joinStatus": join,
            "stageCount": 0,
            "source": "session-context-attribution",
            "sourceVersion": "1",
        },
        unknowns=[reason],
    )


def load_session_context_attribution(
    row: dict, *, source_path: Path | None = None
) -> SessionContextAttribution:
    path = (
        source_path or Path(config.CCDASH_SESSION_CONTEXT_ATTRIBUTION_PATH).expanduser()
    )
    try:
        stat = path.stat()
        data = _read(str(path), stat.st_mtime_ns, stat.st_size)
    except (OSError, ValueError):
        return _empty(
            "source_unavailable",
            "Metadata-only context receipts are unavailable for this session.",
        )
    generated = (
        data.get("generatedAt") if isinstance(data.get("generatedAt"), str) else None
    )
    session_id, cwd = row.get("id"), row.get("cwd")
    if (
        not isinstance(session_id, str)
        or not session_id
        or not isinstance(cwd, str)
        or not os.path.isabs(cwd)
    ):
        return _empty(
            "unmatched",
            "Exact cached session identity or original project directory is unrecorded.",
            generated,
        )
    scope = os.path.normcase(os.path.normpath(cwd))
    matches = [
        item
        for item in data["sessions"]
        if isinstance(item, dict)
        and item.get("ccdashSessionKey") == _hash(session_id)
        and item.get("projectPathKey") == _hash(scope)
    ]
    if not matches:
        return _empty(
            "unmatched",
            "No exact session and project-scope receipt match was recorded.",
            generated,
        )
    if len(matches) != 1:
        return _empty(
            "ambiguous",
            "Multiple exact receipt candidates were recorded; no association was chosen.",
            generated,
        )
    record = matches[0]
    forensics = row.get("session_forensics_json") or {}
    if isinstance(forensics, str):
        try:
            forensics = json.loads(forensics)
        except ValueError:
            forensics = {}
    forensics = forensics if isinstance(forensics, dict) else {}
    raw_id = forensics.get("rawSessionId")
    platform = row.get("platform_type") or forensics.get("platform")
    if (
        not isinstance(raw_id, str)
        or not raw_id
        or record.get("nativeSessionKey") != _hash(raw_id)
        or not platform
        or record.get("platform") != platform
    ):
        return _empty(
            "unmatched",
            "Native source alias or platform could not be verified against the cached session.",
            generated,
        )
    unknowns = (
        [
            _text(v, limit=512)
            for v in (record.get("unknowns") or [])[:20]
            if isinstance(v, str)
        ]
        if isinstance(record.get("unknowns", []), list)
        else []
    )
    raw_stages = record.get("stages")
    if not isinstance(raw_stages, list):
        raw_stages = []
    if len(raw_stages) > MAX_STAGES:
        unknowns.append("Additional stages exceed the bounded response limit.")
    stages = []
    for index, original in enumerate(raw_stages[:MAX_STAGES]):
        if not isinstance(original, dict):
            unknowns.append("A malformed metadata stage was not returned.")
            continue
        stage_unit = _unit(original.get("unit"))
        layer_rows = (
            original.get("layers") if isinstance(original.get("layers"), list) else []
        )
        if len(layer_rows) > MAX_LAYERS:
            unknowns.append("Additional layers exceed the bounded response limit.")
        layers = []
        for layer in layer_rows[:MAX_LAYERS]:
            if not isinstance(layer, dict):
                unknowns.append("A malformed metadata layer was not returned.")
                continue
            layer_unit = _unit(layer.get("unit"))
            attribution = layer.get("attribution")
            layers.append(
                {
                    "name": _text(layer.get("name")),
                    "amount": _amount(layer.get("amount"))
                    if layer_unit != "unknown"
                    else None,
                    "unit": layer_unit,
                    "source": _text(layer.get("source")),
                    "sourceVersion": _text(layer.get("sourceVersion"), "", 80) or None,
                    "attribution": attribution
                    if isinstance(attribution, str)
                    and attribution
                    in {"attributed", "measured", "unattributed", "missing"}
                    else "missing",
                }
            )
        try:
            stages.append(
                SessionContextStage(
                    id=_text(original.get("id"), f"stage-{index}", 120),
                    phase=_text(original.get("phase"), "unknown", 120),
                    observedAt=original.get("observedAt")
                    if isinstance(original.get("observedAt"), str)
                    else None,
                    source=_text(original.get("source")),
                    sourceVersion=_text(original.get("sourceVersion"), "", 80) or None,
                    unit=stage_unit,
                    amount=_amount(original.get("amount"))
                    if stage_unit != "unknown"
                    else None,
                    method=_text(original.get("method")),
                    provenance=_text(original.get("provenance"), limit=512),
                    layers=layers,
                )
            )
        except ValidationError:
            unknowns.append("A malformed metadata stage was not returned.")
    stages.sort(key=_stage_time)
    measured = any(
        stage.amount is not None
        or any(layer.amount is not None for layer in stage.layers)
        for stage in stages
    )
    incomplete = bool(unknowns) or any(
        stage.amount is None
        or any(
            layer.amount is None or layer.attribution in {"unattributed", "missing"}
            for layer in stage.layers
        )
        for stage in stages
    )
    return SessionContextAttribution(
        status="partial"
        if measured and incomplete
        else "measured"
        if measured
        else "unmeasured",
        generatedAt=generated,
        coverage={
            "joinStatus": "matched",
            "stageCount": len(stages),
            "source": "session-context-attribution",
            "sourceVersion": "1",
        },
        stages=stages,
        unknowns=list(dict.fromkeys(unknowns)),
    )
