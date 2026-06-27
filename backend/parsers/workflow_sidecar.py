"""Parser for ``workflow.json`` sidecar files (T5-002).

A ``workflow.json`` sidecar sits next to (or near) a session log and carries
run/task correlation ids plus orchestration metadata — notably a context-window
marker that lets us attribute 1M-context sessions without a transcript heuristic.

This module is intentionally **standalone and pure**: it has no DB / sync-engine
dependencies. ``sync_engine`` (T5-003) joins the parsed records to session rows
on ``run_id``/``task_id`` within a ±1 min window.

Resilience contract (AC-5.1 / T5-002): every parse path tolerates malformed JSON,
partial/missing fields, and a missing file by returning ``None`` (or a record with
``None`` attributes) and logging at DEBUG — it never raises.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("ccdash.parsers.workflow_sidecar")

# Keys we accept for each concept (camelCase + snake_case variants).
_RUN_ID_KEYS = ("runId", "run_id", "runID")
_TASK_ID_KEYS = ("taskId", "task_id", "taskID")
_WORKFLOW_ID_KEYS = ("workflowId", "workflow_id", "workflowID")
_CONTEXT_WINDOW_KEYS = (
    "contextWindow",
    "context_window",
    "contextWindowLabel",
    "context_window_label",
    "modelVariant",
    "model_variant",
)
_TIMESTAMP_KEYS = (
    "timestamp",
    "createdAt",
    "created_at",
    "startedAt",
    "started_at",
    "updatedAt",
    "updated_at",
)


@dataclass
class WorkflowSidecar:
    """Structured view over a parsed ``workflow.json`` sidecar.

    All correlation/metadata attributes are ``Optional`` — a missing field is a
    contract state, not an error. ``mtime`` is the file modification time (epoch
    seconds) used as the fallback timestamp for the ±1 min sidecar join.
    """

    path: Optional[Path] = None
    run_id: Optional[str] = None
    task_id: Optional[str] = None
    workflow_id: Optional[str] = None
    context_window: Optional[str] = None
    timestamp: Optional[str] = None
    mtime: Optional[float] = None
    raw: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.raw is None:
            self.raw = {}


def _first_str(payload: dict[str, Any], keys: tuple[str, ...]) -> Optional[str]:
    for key in keys:
        if key not in payload:
            continue
        value = payload.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _normalize_context_window(raw_value: Optional[str], payload: dict[str, Any]) -> Optional[str]:
    """Normalize a 1M-context marker to the canonical string ``"1M"``.

    Recognizes an explicit context-window value (e.g. ``"1m"``, ``"1M"``,
    ``"1000000"``) as well as a ``[1m]`` variant suffix embedded in a model id.
    Returns ``None`` when no 1M marker is derivable.
    """
    candidates: list[str] = []
    if raw_value:
        candidates.append(raw_value)
    # Also inspect a model id for a bracketed variant suffix like ``[1m]``.
    model_id = _first_str(payload, ("model", "modelId", "model_id"))
    if model_id:
        candidates.append(model_id)

    for candidate in candidates:
        lowered = candidate.strip().lower()
        if not lowered:
            continue
        if "1m" in lowered or "[1m]" in lowered:
            return "1M"
        # Numeric 1,000,000-token windows.
        digits = lowered.replace(",", "").replace("_", "")
        if digits.isdigit() and int(digits) >= 1_000_000:
            return "1M"
    # Preserve a non-1M explicit label verbatim (still a valid context state).
    if raw_value:
        return raw_value.strip() or None
    return None


def parse_workflow_sidecar(path: Path) -> Optional[WorkflowSidecar]:
    """Parse a single ``workflow.json`` sidecar.

    Returns a :class:`WorkflowSidecar` on success, or ``None`` when the file is
    missing or its JSON is malformed (logged at DEBUG, never raised).
    """
    try:
        if not path.exists() or not path.is_file():
            logger.debug("workflow sidecar missing: %s", path)
            return None
    except OSError as exc:  # pragma: no cover - defensive
        logger.debug("workflow sidecar stat failed for %s: %s", path, exc)
        return None

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.debug("workflow sidecar read failed for %s: %s", path, exc)
        return None

    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.debug("workflow sidecar malformed JSON in %s: %s", path, exc)
        return None

    if not isinstance(payload, dict):
        logger.debug("workflow sidecar root is not an object: %s", path)
        return None

    try:
        mtime: Optional[float] = path.stat().st_mtime
    except OSError:
        mtime = None

    raw_context_window = _first_str(payload, _CONTEXT_WINDOW_KEYS)
    return WorkflowSidecar(
        path=path,
        run_id=_first_str(payload, _RUN_ID_KEYS),
        task_id=_first_str(payload, _TASK_ID_KEYS),
        workflow_id=_first_str(payload, _WORKFLOW_ID_KEYS),
        context_window=_normalize_context_window(raw_context_window, payload),
        timestamp=_first_str(payload, _TIMESTAMP_KEYS),
        mtime=mtime,
        raw=payload,
    )


def scan_workflow_sidecars(directory: Path) -> list[WorkflowSidecar]:
    """Scan a directory tree for ``workflow.json`` sidecars.

    Tolerant of a missing directory (returns ``[]``); individual malformed
    sidecars are skipped (logged at DEBUG), never raised.
    """
    records: list[WorkflowSidecar] = []
    try:
        if not directory.exists() or not directory.is_dir():
            return records
        candidates = sorted(directory.rglob("workflow.json"))
    except OSError as exc:  # pragma: no cover - defensive
        logger.debug("workflow sidecar scan failed for %s: %s", directory, exc)
        return records

    for candidate in candidates:
        record = parse_workflow_sidecar(candidate)
        if record is not None:
            records.append(record)
    return records
