"""JSON output formatter."""
from __future__ import annotations

import json
from typing import Any

from backend.cli.formatters._utils import to_serializable
from backend.cli.formatters.base import OutputFormatter


class JsonFormatter(OutputFormatter):
    def render(self, data: Any, *, title: str = "") -> str:
        _ = title
        return json.dumps(to_serializable(data), indent=2, default=str)

