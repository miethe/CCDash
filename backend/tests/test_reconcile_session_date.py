"""Date reconciliation uses registered roots and stays read-only in dry-run."""
from __future__ import annotations

from datetime import date
import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "reconcile_session_date.py"
SPEC = importlib.util.spec_from_file_location("reconcile_session_date", SCRIPT)
assert SPEC and SPEC.loader
reconcile = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reconcile)


def test_report_scoped_candidates_include_git_proven_worktree(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    gitdir = repo / ".git" / "worktrees" / "run"
    gitdir.mkdir(parents=True)
    checkout = repo / ".wt" / "run"
    checkout.mkdir(parents=True)
    (checkout / ".git").write_text(f"gitdir: {gitdir}\n")
    slug = lambda path: str(path).replace("/", "-").replace("_", "-").replace(".", "-")
    root = tmp_path / "projects" / slug(repo)
    sibling = root.parent / slug(checkout)
    root.mkdir(parents=True)
    sibling.mkdir()
    target = sibling / "missing-id.jsonl"
    target.write_text(json.dumps({"cwd": str(checkout), "timestamp": "2026-09-26T01:00:00Z"}) + "\n")
    (sibling / "other-id.jsonl").write_text('{"timestamp":"2026-09-26T01:00:00Z"}\n')
    projects = [{"id": "project-1", "pathConfig": {"sessions": {"filesystemPath": str(root)}}}]

    assert reconcile.candidates(projects, date(2026, 9, 26), {"missing-id"}) == [("project-1", target)]


def test_report_date_mismatch_is_rejected(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"window": {"since": "2026-09-25T00:00:00Z"}}))

    with pytest.raises(ValueError, match="does not start"):
        reconcile.report_ids(report, date(2026, 9, 26))


def test_first_record_date_uses_utc(tmp_path: Path) -> None:
    transcript = tmp_path / "session.jsonl"
    transcript.write_text('{"timestamp":"2026-09-25T23:30:00-04:00"}\n')

    assert reconcile.first_record_date(transcript) == date(2026, 9, 26)
