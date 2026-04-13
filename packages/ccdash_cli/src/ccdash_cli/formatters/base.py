"""Formatter protocol shared by CLI output adapters."""
from __future__ import annotations

from typing import Any, Protocol


class OutputFormatter(Protocol):
    def render(self, data: Any, *, title: str = "") -> str: ...
