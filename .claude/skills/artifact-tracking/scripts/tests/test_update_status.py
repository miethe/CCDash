"""Tests for `update-status.py` — id resolution beyond `tasks:` and metric containment.

Three defects, all of which silently corrupted the record rather than failing loudly:

1. `--task` only ever searched `tasks:`, so every other id-bearing collection was
   unreachable. `.claude/progress/enterprise-r0-validation-pass/milestone-M4-progress.md`
   carries `SC-1`…`SC-5` under `success_criteria:` that could not be updated at all — the
   CLI answered `Task 'SC-1' not found`, which reads as "no such id" rather than "this
   tool cannot see that collection".

2. Had a non-task update landed, it would have run `recalculate_metrics()`, which
   OVERWRITES the file-level `status` from task progress — re-deriving milestone status
   from an unrelated collection. This repo has already been bitten by the tracker
   auto-flipping `completed`.

3. `recalculate_metrics()` wrote `progress` but never `overall_progress`, the
   schema-REQUIRED completion field (`schemas/VALIDATION-REFERENCE.md`). They diverged
   silently; M4 read `progress: 100` beside `overall_progress: 85`.

The load-bearing guard is `test_non_task_update_does_not_touch_status_or_totals`: making
ids reachable must not hand an unrelated collection the power to rewrite milestone status.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

SCRIPTS = Path(__file__).resolve().parents[1]
SCRIPT = SCRIPTS / "update-status.py"


def _load_module():
    """Import a hyphenated script by path (it is a CLI, not an importable module)."""
    spec = importlib.util.spec_from_file_location("update_status", SCRIPT)
    assert spec is not None and spec.loader is not None, f"cannot load {SCRIPT}"
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


us = _load_module()


# A milestone-shaped progress file: two tasks (one already completed), plus the three
# non-task id-bearing collections. `status`, `total_tasks` and `overall_progress` are
# deliberately STALE relative to the tasks so that any accidental recalculation is visible.
MILESTONE = """\
---
type: progress
schema_version: 2
prd: enterprise-r0-validation-pass
milestone: M4
title: Runtime claims discharged
status: in_progress
started: null
completed: null
overall_progress: 85
total_tasks: 99
completed_tasks: 1
in_progress_tasks: 0
blocked_tasks: 0
tasks:
- id: TASK-M4.B1
  description: First task.
  status: completed
- id: TASK-M4.B2
  description: Second task.
  status: pending
success_criteria:
- id: SC-1
  description: A finding that does not reproduce moves to refuted.
  status: pending
- id: SC-2
  description: No runtime verdict is asserted without a pasted observation.
  status: pending
risks:
- id: RISK-1
  description: A risk that needs its own status.
  status: pending
open_questions:
- id: OQ-1
  description: An open question that needs its own status.
  status: pending
---

body text that must survive untouched
"""


def write_progress(tmp_path: Path, text: str = MILESTONE) -> Path:
    path = tmp_path / "milestone-M4-progress.md"
    path.write_text(text, encoding="utf-8")
    return path


def run_cli(path: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), "-f", str(path), *args],
                          capture_output=True, text=True)


def frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    _, _, rest = text.partition("---\n")
    block, _, _ = rest.partition("\n---")
    return yaml.safe_load(block)


def item(data: dict, collection: str, item_id: str) -> dict:
    for entry in data[collection]:
        if entry["id"] == item_id:
            return entry
    raise AssertionError(f"{item_id} missing from {collection}")


# --------------------------------------------------------------------------- #
# find_item — resolution order across the id-bearing collections
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("item_id,expected_collection", [
    ("TASK-M4.B1", "tasks"),
    ("SC-2", "success_criteria"),
    ("RISK-1", "risks"),
    ("OQ-1", "open_questions"),
])
def test_find_item_resolves_every_id_bearing_collection(item_id, expected_collection):
    data = yaml.safe_load(MILESTONE.partition("---\n")[2].partition("\n---")[0])
    found, collection = us.find_item(data, item_id)
    assert collection == expected_collection
    assert found["id"] == item_id


def test_find_item_returns_none_for_an_unknown_id():
    data = yaml.safe_load(MILESTONE.partition("---\n")[2].partition("\n---")[0])
    assert us.find_item(data, "NOPE-1") == (None, None)


def test_find_item_tolerates_a_null_collection():
    """A file with `risks:` present but empty must not explode the search."""
    assert us.find_item({"risks": None, "success_criteria": [{"id": "SC-1"}]},
                        "SC-1")[1] == "success_criteria"


# --------------------------------------------------------------------------- #
# the papercut: a success-criterion id must be updatable at all
# --------------------------------------------------------------------------- #

def test_success_criterion_id_is_updatable(tmp_path):
    """The AC. Before the fix this exited 1 with `Task 'SC-1' not found`."""
    path = write_progress(tmp_path)

    result = run_cli(path, "-t", "SC-1", "-s", "partial", "--note", "gated on F-M3-1")

    assert result.returncode == 0, result.stderr
    data = frontmatter(path)
    assert item(data, "success_criteria", "SC-1")["status"] == "partial"
    assert item(data, "success_criteria", "SC-1")["note"] == "gated on F-M3-1"
    # untargeted siblings are untouched
    assert item(data, "success_criteria", "SC-2")["status"] == "pending"


@pytest.mark.parametrize("item_id,collection", [
    ("RISK-1", "risks"),
    ("OQ-1", "open_questions"),
])
def test_risk_and_open_question_ids_are_updatable(tmp_path, item_id, collection):
    path = write_progress(tmp_path)

    result = run_cli(path, "-t", item_id, "-s", "deferred")

    assert result.returncode == 0, result.stderr
    assert item(frontmatter(path), collection, item_id)["status"] == "deferred"


def test_a_task_id_shadows_an_identically_named_non_task_id(tmp_path):
    """Precedence: `tasks:` is searched first, so a colliding id resolves there.

    The `overall_progress` assertion is what makes this fail pre-fix — the shadowing
    itself was already correct because `tasks:` was the ONLY collection searched.
    """
    collided = MILESTONE.replace("- id: TASK-M4.B2", "- id: SC-1", 1)
    path = write_progress(tmp_path, collided)

    result = run_cli(path, "-t", "SC-1", "-s", "completed", "--evidence", "commit:abc123")

    assert result.returncode == 0, result.stderr
    data = frontmatter(path)
    assert item(data, "tasks", "SC-1")["status"] == "completed"
    assert item(data, "success_criteria", "SC-1")["status"] == "pending", \
        "the success_criteria entry must not have been touched"
    # a tasks-collection update DOES recalculate, and must keep the two fields in step
    assert data["progress"] == data["overall_progress"] == 100


# --------------------------------------------------------------------------- #
# containment: a non-task update must not re-derive task metrics
# --------------------------------------------------------------------------- #

def test_non_task_update_does_not_touch_status_or_totals(tmp_path):
    """The load-bearing guard.

    `status`, `total_tasks` and `overall_progress` in the fixture are all stale relative
    to `tasks:`. A recalculation triggered by an SC update would rewrite every one of
    them — `status` would flip `in_progress` → `at_risk`/`pending` and `total_tasks`
    99 → 2 — silently re-deriving milestone state from an unrelated collection.
    """
    path = write_progress(tmp_path)

    result = run_cli(path, "-t", "SC-1", "-s", "partial")

    assert result.returncode == 0, result.stderr
    data = frontmatter(path)
    assert data["status"] == "in_progress"
    assert data["total_tasks"] == 99
    assert data["completed_tasks"] == 1
    assert data["overall_progress"] == 85
    assert "progress" not in data, "a non-task update must not invent a task-progress key"


def test_non_task_update_bumps_updated_and_reports_unchanged_progress(tmp_path):
    path = write_progress(tmp_path)

    result = run_cli(path, "-t", "OQ-1", "-s", "blocked")

    assert result.returncode == 0, result.stderr
    assert frontmatter(path)["updated"], "`updated` must still move"
    # truthful, not a fabricated drop to 0%
    assert "Progress: 85% → 85%" in result.stdout


def test_non_task_update_preserves_the_body(tmp_path):
    path = write_progress(tmp_path)
    result = run_cli(path, "-t", "SC-2", "-s", "partial")
    assert result.returncode == 0, result.stderr
    assert "body text that must survive untouched" in path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# overall_progress must track progress
# --------------------------------------------------------------------------- #

def test_task_update_syncs_overall_progress_with_progress(tmp_path):
    """Pre-fix this left `overall_progress: 85` beside `progress: 100`."""
    path = write_progress(tmp_path)

    result = run_cli(path, "-t", "TASK-M4.B2", "-s", "completed",
                     "--evidence", "commit:abc123")

    assert result.returncode == 0, result.stderr
    data = frontmatter(path)
    assert data["progress"] == 100
    assert data["overall_progress"] == 100
    assert data["status"] == "completed"


def test_partial_task_completion_syncs_both_fields(tmp_path):
    """Not just the 100% case — the two fields agree at every value."""
    path = write_progress(tmp_path)

    result = run_cli(path, "-t", "TASK-M4.B1", "-s", "pending")

    assert result.returncode == 0, result.stderr
    data = frontmatter(path)
    assert data["progress"] == 0
    assert data["overall_progress"] == 0


def test_completed_and_started_timestamps_are_not_fabricated(tmp_path):
    """Syncing progress must not invent file-level completion timestamps."""
    path = write_progress(tmp_path)

    run_cli(path, "-t", "TASK-M4.B2", "-s", "completed", "--evidence", "commit:abc123")

    data = frontmatter(path)
    assert data["completed"] is None
    assert data["started"] is None


# --------------------------------------------------------------------------- #
# unresolved ids and the preserved completion gate
# --------------------------------------------------------------------------- #

def test_unknown_id_still_errors_and_names_the_searched_collections(tmp_path):
    path = write_progress(tmp_path)
    before = path.read_text(encoding="utf-8")

    result = run_cli(path, "-t", "TASK-NOPE", "-s", "completed", "--force")

    assert result.returncode == 1
    assert "not found" in result.stderr
    for collection in ("tasks", "success_criteria", "risks", "open_questions"):
        assert collection in result.stderr
    assert path.read_text(encoding="utf-8") == before


def test_completion_gate_still_applies_to_a_success_criterion(tmp_path):
    """Reaching a new collection must not smuggle in an evidence-free completion."""
    path = write_progress(tmp_path)
    before = path.read_text(encoding="utf-8")

    result = run_cli(path, "-t", "SC-1", "-s", "completed")

    assert result.returncode == 1
    assert "without timing signals" in result.stderr
    assert path.read_text(encoding="utf-8") == before


def test_force_still_overrides_the_gate_for_a_success_criterion(tmp_path):
    path = write_progress(tmp_path)

    result = run_cli(path, "-t", "SC-1", "-s", "completed", "--force")

    assert result.returncode == 0, result.stderr
    assert "WARNING" in result.stderr
    assert item(frontmatter(path), "success_criteria", "SC-1")["status"] == "completed"


def test_evidence_and_verified_by_still_land_on_a_non_task_item(tmp_path):
    path = write_progress(tmp_path)

    result = run_cli(path, "-t", "SC-2", "-s", "completed",
                     "--evidence", "commit:abc123", "--evidence", "plain observation",
                     "--verified-by", "M4-B2")

    assert result.returncode == 0, result.stderr
    sc2 = item(frontmatter(path), "success_criteria", "SC-2")
    assert sc2["evidence"] == [{"commit": "abc123"}, {"note": "plain observation"}]
    assert sc2["verified_by"] == ["M4-B2"]
