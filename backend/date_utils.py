"""Shared date normalization and confidence helpers."""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CONFIDENCE_ORDER = {"high": 3, "medium": 2, "low": 1}


def normalize_confidence(value: str | None) -> str:
    token = (value or "").strip().lower()
    if token in _CONFIDENCE_ORDER:
        return token
    return "low"


def _format_datetime_utc(value: datetime) -> str:
    dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc).replace(microsecond=0)
    return dt.isoformat().replace("+00:00", "Z")


def _parse_datetime_token(token: str) -> datetime | None:
    cleaned = token.strip()
    if not cleaned:
        return None
    try:
        return datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except Exception:
        pass
    for fmt in ("%Y/%m/%d", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(cleaned, fmt).replace(tzinfo=timezone.utc)
        except Exception:
            continue
    return None


def normalize_iso_date(value: Any) -> str:
    """Convert mixed date inputs into comparable ISO strings."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return _format_datetime_utc(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        token = value.strip()
        if not token:
            return ""
        if _DATE_ONLY_RE.match(token):
            try:
                return date.fromisoformat(token).isoformat()
            except Exception:
                return ""
        parsed_dt = _parse_datetime_token(token)
        if parsed_dt:
            return _format_datetime_utc(parsed_dt)
        return ""
    return ""


def iso_to_epoch(value: str) -> float:
    token = normalize_iso_date(value)
    if not token:
        return 0.0
    if _DATE_ONLY_RE.match(token):
        try:
            return datetime.fromisoformat(token).replace(tzinfo=timezone.utc).timestamp()
        except Exception:
            return 0.0
    parsed_dt = _parse_datetime_token(token)
    if not parsed_dt:
        return 0.0
    dt = parsed_dt if parsed_dt.tzinfo else parsed_dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).timestamp()


def _file_created_datetime(stats: Any) -> datetime | None:
    for attr in ("st_birthtime",):
        value = getattr(stats, attr, None)
        if isinstance(value, (int, float)) and value > 0:
            return datetime.fromtimestamp(float(value), timezone.utc)
    ctime = getattr(stats, "st_ctime", None)
    if isinstance(ctime, (int, float)) and ctime > 0:
        return datetime.fromtimestamp(float(ctime), timezone.utc)
    return None


def file_metadata_dates(path: Path) -> dict[str, str]:
    """Return normalized filesystem creation/modified timestamps."""
    try:
        stats = path.stat()
    except Exception:
        return {"createdAt": "", "updatedAt": ""}

    created_dt = _file_created_datetime(stats)
    modified_dt = datetime.fromtimestamp(float(stats.st_mtime), timezone.utc)
    return {
        "createdAt": _format_datetime_utc(created_dt) if created_dt else "",
        "updatedAt": _format_datetime_utc(modified_dt),
    }


def make_date_value(
    value: str,
    confidence: str,
    source: str,
    reason: str = "",
) -> dict[str, str]:
    normalized = normalize_iso_date(value)
    if not normalized:
        return {}
    return {
        "value": normalized,
        "confidence": normalize_confidence(confidence),
        "source": (source or "").strip(),
        "reason": (reason or "").strip(),
    }


def _confidence_score(value: str) -> int:
    return _CONFIDENCE_ORDER.get(normalize_confidence(value), 0)


def choose_first(candidates: list[dict[str, str]]) -> dict[str, str]:
    for candidate in candidates:
        value = normalize_iso_date(candidate.get("value"))
        if not value:
            continue
        return {
            **candidate,
            "value": value,
            "confidence": normalize_confidence(candidate.get("confidence")),
        }
    return {}


def choose_earliest(candidates: list[dict[str, str]]) -> dict[str, str]:
    best: dict[str, str] = {}
    best_epoch = float("inf")
    best_conf = -1
    for candidate in candidates:
        value = normalize_iso_date(candidate.get("value"))
        if not value:
            continue
        epoch = iso_to_epoch(value)
        conf = _confidence_score(candidate.get("confidence", ""))
        if epoch < best_epoch or (epoch == best_epoch and conf > best_conf):
            best = {
                **candidate,
                "value": value,
                "confidence": normalize_confidence(candidate.get("confidence")),
            }
            best_epoch = epoch
            best_conf = conf
    return best


def choose_latest(candidates: list[dict[str, str]]) -> dict[str, str]:
    best: dict[str, str] = {}
    best_epoch = 0.0
    best_conf = -1
    for candidate in candidates:
        value = normalize_iso_date(candidate.get("value"))
        if not value:
            continue
        epoch = iso_to_epoch(value)
        conf = _confidence_score(candidate.get("confidence", ""))
        if epoch > best_epoch or (epoch == best_epoch and conf > best_conf):
            best = {
                **candidate,
                "value": value,
                "confidence": normalize_confidence(candidate.get("confidence")),
            }
            best_epoch = epoch
            best_conf = conf
    return best
