"""CLI output mode selection and formatter dispatch."""
from __future__ import annotations

from enum import Enum

from backend.cli.formatters.base import OutputFormatter
from backend.cli.formatters.json import JsonFormatter
from backend.cli.formatters.markdown import MarkdownFormatter
from backend.cli.formatters.table import TableFormatter


class OutputMode(str, Enum):
    human = "human"
    json = "json"
    markdown = "markdown"


def resolve_output_mode(
    *,
    output: OutputMode | None = None,
    json_output: bool = False,
    markdown_output: bool = False,
    default: OutputMode = OutputMode.human,
) -> OutputMode:
    if json_output and markdown_output:
        raise ValueError("Choose only one of --json or --md.")
    if json_output:
        return OutputMode.json
    if markdown_output:
        return OutputMode.markdown
    if output is not None:
        return output
    return default


def get_formatter(mode: OutputMode) -> OutputFormatter:
    if mode == OutputMode.json:
        return JsonFormatter()
    if mode == OutputMode.markdown:
        return MarkdownFormatter()
    return TableFormatter()

