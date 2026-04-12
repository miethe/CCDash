"""Shared formatter utilities."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel


def to_serializable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): to_serializable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_serializable(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value

