"""Markdown output formatter."""
from __future__ import annotations

from typing import Any

from ccdash_cli.formatters._utils import to_serializable
from ccdash_cli.formatters.base import OutputFormatter


class MarkdownFormatter(OutputFormatter):
    def render(self, data: Any, *, title: str = "") -> str:
        payload = to_serializable(data)
        lines: list[str] = []
        if title:
            lines.append(f"# {title}")
            lines.append("")
        lines.extend(self._render_block(payload, level=2))
        return "\n".join(lines).strip()

    def _render_block(self, value: Any, *, level: int) -> list[str]:
        if isinstance(value, dict):
            lines: list[str] = []
            for key, item in value.items():
                label = str(key).replace("_", " ").strip() or "Value"
                lines.append(f"{'#' * level} {label}")
                lines.append("")
                lines.extend(self._render_block(item, level=min(level + 1, 6)))
                lines.append("")
            return lines
        if isinstance(value, list):
            if not value:
                return ["- _none_"]
            lines: list[str] = []
            for item in value:
                if isinstance(item, (dict, list)):
                    nested = self._render_block(item, level=min(level + 1, 6))
                    first = nested[0] if nested else ""
                    lines.append(f"- {first}" if first else "-")
                    lines.extend(nested[1:])
                else:
                    lines.append(f"- {self._render_scalar(item)}")
            return lines
        return [self._render_scalar(value)]

    def _render_scalar(self, value: Any) -> str:
        if value is None:
            return "_none_"
        token = str(value).strip()
        return token or "_empty_"
