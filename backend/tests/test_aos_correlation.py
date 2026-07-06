from __future__ import annotations

import json
from pathlib import Path

from backend.services.aos_correlation import derive_aos_correlation


TURN_UUID = "11111111-1111-4111-8111-111111111111"
RUN_UUID = "22222222-2222-4222-8222-222222222222"
FEATURE_UUID = "33333333-3333-4333-8333-333333333333"


def _write_events(home: Path, lines: list[object | str]) -> None:
    home.mkdir(parents=True, exist_ok=True)
    payload_lines = [
        line if isinstance(line, str) else json.dumps(line, separators=(",", ":"))
        for line in lines
    ]
    (home / "events.jsonl").write_text("\n".join(payload_lines), encoding="utf-8")


def test_footer_extraction_surfaces_copyable_leaf_id(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AOS_ID_HOME", str(tmp_path))
    logs = [
        {"id": "log-1", "content": "work finished\nAOS-ID: urn:aos:turn:11111111-1111-4111-8111-111111111111"},
    ]

    result = derive_aos_correlation(
        session_id="sess-1",
        project_id="proj-1",
        logs=logs,
    )

    assert result["status"] == "resolved"
    assert result["footer"] == f"AOS-ID: urn:aos:turn:{TURN_UUID}"
    assert result["turnUrn"] == f"urn:aos:turn:{TURN_UUID}"
    assert result["turnUuid"] == TURN_UUID
    assert result["sessionIds"] == ["sess-1"]


def test_sidecar_events_are_sanitized_deduped_and_diagnostic(monkeypatch, tmp_path: Path) -> None:
    event = {
        "urn": f"urn:aos:turn:{TURN_UUID}",
        "target": f"urn:aos:run:{RUN_UUID}",
        "relation": "belongs_to",
        "aliases": {
            "ccdash_session_id": "sess-1",
            "feature_id": "FEAT-AOS",
            "prompt": "private prompt must not survive",
        },
        "native": {
            "op_run_id": "op_run_20260706_120000_aos",
            "response": "private response must not survive",
        },
        "content": "private content must not survive",
    }
    _write_events(
        tmp_path,
        [
            event,
            event,
            "{not json",
            {"aliases": {"ccdash_session_id": "sess-1"}},
            {"urn": f"urn:aos:feature:{FEATURE_UUID}", "source": f"urn:aos:run:{RUN_UUID}"},
        ],
    )
    monkeypatch.setenv("AOS_ID_HOME", str(tmp_path))

    result = derive_aos_correlation(session_id="sess-1", project_id="proj-1", logs=[])
    rendered = json.dumps(result, sort_keys=True)

    assert result["status"] == "partial"
    assert result["footer"] == f"AOS-ID: urn:aos:turn:{TURN_UUID}"
    assert result["parentRun"]["urn"] == f"urn:aos:run:{RUN_UUID}"
    assert result["parentFeature"]["urn"] == f"urn:aos:feature:{FEATURE_UUID}"
    assert result["aliases"]["ccdash_session_id"] == ["sess-1"]
    assert result["native"]["op_run_id"] == ["op_run_20260706_120000_aos"]
    assert {item["code"] for item in result["diagnostics"]} >= {
        "duplicate_sidecar_row",
        "malformed_sidecar_line",
        "unresolved_sidecar_row",
    }
    assert "private prompt" not in rendered
    assert "private response" not in rendered
    assert "private content" not in rendered


def test_unrelated_sidecar_event_does_not_attach_to_session(monkeypatch, tmp_path: Path) -> None:
    _write_events(
        tmp_path,
        [
            {
                "urn": f"urn:aos:turn:{TURN_UUID}",
                "aliases": {"ccdash_session_id": "other-session"},
            }
        ],
    )
    monkeypatch.setenv("AOS_ID_HOME", str(tmp_path))

    assert derive_aos_correlation(session_id="sess-1", project_id="proj-1", logs=[]) == {}
