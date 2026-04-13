"""Direct formatter coverage for ccdash_cli output renderers."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

from pydantic import BaseModel

from ccdash_cli.formatters._utils import to_serializable
from ccdash_cli.formatters.json import JsonFormatter
from ccdash_cli.formatters.markdown import MarkdownFormatter
from ccdash_cli.formatters.table import TableFormatter


class _Payload(BaseModel):
    id: str
    created_at: datetime


def test_to_serializable_handles_models_and_dates():
    payload = {
        "model": _Payload(
            id="FEAT-1",
            created_at=datetime(2026, 4, 13, 12, 0, tzinfo=timezone.utc),
        ),
        "dates": (date(2026, 4, 13),),
    }

    serialized = to_serializable(payload)

    assert serialized == {
        "model": {
            "id": "FEAT-1",
            "created_at": "2026-04-13T12:00:00Z",
        },
        "dates": ["2026-04-13"],
    }


def test_json_formatter_renders_valid_json():
    output = JsonFormatter().render(
        {"created_at": datetime(2026, 4, 13, 12, 0, tzinfo=timezone.utc)}
    )

    parsed = json.loads(output)

    assert parsed["created_at"] == "2026-04-13T12:00:00+00:00"


def test_markdown_formatter_renders_headings_and_empty_lists():
    output = MarkdownFormatter().render(
        {"status": "ok", "items": []},
        title="Feature Report",
    )

    assert "# Feature Report" in output
    assert "## status" in output
    assert "## items" in output
    assert "- _none_" in output


def test_table_formatter_renders_tabular_rows():
    output = TableFormatter().render(
        [{"id": "FEAT-1", "status": "active"}],
        title="Features",
    )

    assert "Features" in output
    assert "FEAT-1" in output
    assert "active" in output
