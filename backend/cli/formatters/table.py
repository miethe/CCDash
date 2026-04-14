"""Rich-backed human-readable formatter."""
from __future__ import annotations

import json
from typing import Any

from rich.console import Console
from rich.table import Table

from backend.cli.formatters._utils import to_serializable
from backend.cli.formatters.base import OutputFormatter


class TableFormatter(OutputFormatter):
    def render(self, data: Any, *, title: str = "") -> str:
        payload = to_serializable(data)
        console = Console(record=True, force_terminal=False, width=120)
        self._render_payload(console, payload, title=title)
        return console.export_text().rstrip()

    def _render_payload(self, console: Console, payload: Any, *, title: str) -> None:
        if isinstance(payload, dict):
            table = Table(title=title or None, show_header=True, header_style="bold")
            table.add_column("Field", style="bold")
            table.add_column("Value", overflow="fold")
            for key, value in payload.items():
                table.add_row(str(key), self._stringify(value))
            console.print(table)
            return

        if isinstance(payload, list):
            if payload and all(isinstance(item, dict) for item in payload):
                columns = self._collect_columns(payload)
                table = Table(title=title or None, show_header=True, header_style="bold")
                for column in columns:
                    table.add_column(column, overflow="fold")
                for row in payload:
                    table.add_row(*[self._stringify(row.get(column, "")) for column in columns])
                console.print(table)
                return

            table = Table(title=title or None, show_header=True, header_style="bold")
            table.add_column("Value", overflow="fold")
            for item in payload:
                table.add_row(self._stringify(item))
            console.print(table)
            return

        if title:
            console.print(f"{title}: {self._stringify(payload)}")
        else:
            console.print(self._stringify(payload))

    def _collect_columns(self, rows: list[dict[str, Any]]) -> list[str]:
        seen: list[str] = []
        for row in rows:
            for key in row.keys():
                token = str(key)
                if token not in seen:
                    seen.append(token)
        return seen

    def _stringify(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            return json.dumps(value, indent=2, default=str)
        return str(value)

