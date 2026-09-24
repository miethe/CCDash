#!/usr/bin/env python3
"""Tests for intenttree_capture.py discovery (DI-107).

Invariants under test:
1. A catch-all dir (quick-features/quick-wins, or >2 distinct feature_slugs) captures each FILE
   as its own feature — generic task ids (QF-1) reused across files never collide because each
   file has a distinct artifact_path → distinct source_artifact_id.
2. A normal feature dir still aggregates its phase files into ONE feature.
3. Fully-complete catch-all files are excluded (not in-flight).
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from intenttree_capture import discover_features, discover_flat_plans  # noqa: E402

_CUTOFF = datetime.date(2026, 1, 1)

_ALPHA = """\
---
doc_type: progress
updated: 2026-06-20
tasks:
  - id: QF-1
    description: Alpha quick feature task one.
    status: todo
  - id: QF-2
    description: Alpha quick feature task two.
    status: in_progress
---

# Alpha
"""

_BETA = """\
---
doc_type: progress
updated: 2026-06-20
tasks:
  - id: QF-1
    description: Beta quick feature task one (same generic id as alpha's).
    status: todo
---

# Beta
"""

_DONE = """\
---
doc_type: progress
updated: 2026-06-20
tasks:
  - id: QF-1
    description: A finished quick win.
    status: completed
---

# Done
"""

_PHASE1 = """\
---
doc_type: progress
feature_slug: my-feature
phase: 1
updated: 2026-06-20
tasks:
  - id: TASK-1.1
    description: Phase one task.
    status: todo
---

# Phase 1
"""

_PHASE2 = """\
---
doc_type: progress
feature_slug: my-feature
phase: 2
updated: 2026-06-20
tasks:
  - id: TASK-2.1
    description: Phase two task.
    status: todo
---

# Phase 2
"""


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_catch_all_dir_captures_per_file(tmp_path: Path) -> None:
    _write(tmp_path / ".claude/progress/quick-features/alpha.md", _ALPHA)
    _write(tmp_path / ".claude/progress/quick-features/beta.md", _BETA)

    feats = discover_features(tmp_path, _CUTOFF)
    qf = [f for f in feats if "quick-features" in f["artifact_path"]]
    # One feature per file (NOT one collapsed feature for the whole dir).
    assert len(qf) == 2
    by_stem = {Path(f["artifact_path"]).stem: f for f in qf}
    assert set(by_stem) == {"alpha", "beta"}
    assert len(by_stem["alpha"]["tasks"]) == 2
    assert len(by_stem["beta"]["tasks"]) == 1
    # The generic id QF-1 appears in BOTH files but in different features → distinct artifacts,
    # so (source_artifact_id, source_task_id) cannot collide on apply.
    assert {t["id"] for t in by_stem["alpha"]["tasks"]} >= {"QF-1"}
    assert {t["id"] for t in by_stem["beta"]["tasks"]} >= {"QF-1"}
    assert by_stem["alpha"]["artifact_path"] != by_stem["beta"]["artifact_path"]


def test_normal_dir_still_aggregates_phase_files(tmp_path: Path) -> None:
    _write(tmp_path / ".claude/progress/my-feature/phase-1-progress.md", _PHASE1)
    _write(tmp_path / ".claude/progress/my-feature/phase-2-progress.md", _PHASE2)

    feats = discover_features(tmp_path, _CUTOFF)
    mine = [f for f in feats if f["slug"] == "my-feature"]
    assert len(mine) == 1, "a normal feature dir must aggregate into ONE feature"
    assert len(mine[0]["tasks"]) == 2  # TASK-1.1 + TASK-2.1 across phases


def test_catch_all_skips_fully_complete_files(tmp_path: Path) -> None:
    _write(tmp_path / ".claude/progress/quick-wins/done.md", _DONE)
    _write(tmp_path / ".claude/progress/quick-wins/active.md", _ALPHA)

    feats = discover_features(tmp_path, _CUTOFF)
    qw = [f for f in feats if "quick-wins" in f["artifact_path"]]
    assert len(qw) == 1
    assert Path(qw[0]["artifact_path"]).stem == "active"


# ----------------------------------------------------------------- DI-144 tests

_FLAT_PLAN = """\
---
it_schema: 1
feature_slug: flat-one
title: Flat One
doc_type: implementation_plan
status: in_progress
---

# Flat One

A flat plan with no progress dir and no tasks[].
"""

_FLAT_PLAN_NO_SCHEMA = """\
---
feature_slug: no-schema-plan
title: No Schema Plan
doc_type: implementation_plan
status: in_progress
---

# No Schema Plan
"""

_FLAT_PLAN_NO_SLUG = """\
---
it_schema: 1
title: No Slug Plan
doc_type: implementation_plan
status: in_progress
---

# No Slug Plan
"""


def test_discover_flat_plans_finds_plan_with_schema_and_slug(tmp_path: Path) -> None:
    """AC-1: a plan under docs/project_plans/ with it_schema + feature_slug is discovered."""
    _write(tmp_path / "docs/project_plans/features/flat-one.md", _FLAT_PLAN)

    feats = discover_flat_plans(tmp_path, set())
    slugs = [f["slug"] for f in feats]
    assert "flat-one" in slugs, f"expected 'flat-one' in {slugs}"
    flat_one = next(f for f in feats if f["slug"] == "flat-one")
    assert flat_one["title"] == "Flat One"


def test_discover_flat_plans_excludes_already_captured_slug(tmp_path: Path) -> None:
    """AC-2a: passing captured_slugs={"flat-one"} suppresses flat-one from results."""
    _write(tmp_path / "docs/project_plans/features/flat-one.md", _FLAT_PLAN)

    feats = discover_flat_plans(tmp_path, {"flat-one"})
    slugs = [f["slug"] for f in feats]
    assert "flat-one" not in slugs, f"flat-one should be excluded; got {slugs}"


def test_discover_flat_plans_skips_plan_without_it_schema(tmp_path: Path) -> None:
    """AC-2b: a plan with feature_slug but no it_schema is skipped."""
    _write(tmp_path / "docs/project_plans/features/no-schema-plan.md", _FLAT_PLAN_NO_SCHEMA)

    feats = discover_flat_plans(tmp_path, set())
    slugs = [f["slug"] for f in feats]
    assert "no-schema-plan" not in slugs, f"no-schema-plan should be skipped; got {slugs}"


def test_discover_flat_plans_skips_plan_without_feature_slug(tmp_path: Path) -> None:
    """AC-3: a plan with it_schema but no feature_slug is skipped."""
    _write(tmp_path / "docs/project_plans/features/no-slug-plan.md", _FLAT_PLAN_NO_SLUG)

    feats = discover_flat_plans(tmp_path, set())
    # no slug → feature_from_file uses stem as slug BUT discover_flat_plans gates on
    # fm.get("feature_slug") being truthy before calling feature_from_file, so this is skipped.
    assert all(f.get("slug") != "no-slug-plan" for f in feats)


def test_discover_flat_plans_empty_when_no_docs_dir(tmp_path: Path) -> None:
    """discover_flat_plans returns [] when docs/project_plans/ does not exist."""
    feats = discover_flat_plans(tmp_path, set())
    assert feats == []


def test_discover_flat_plans_no_double_capture_with_progress_dir(tmp_path: Path) -> None:
    """AC-2 integration: a slug that has a .claude/progress/<slug>/ dir is excluded via captured_slugs."""
    _write(tmp_path / "docs/project_plans/features/flat-one.md", _FLAT_PLAN)
    # simulate discover_features already capturing this slug
    captured = {"flat-one"}
    feats = discover_flat_plans(tmp_path, captured)
    assert all(f["slug"] != "flat-one" for f in feats)
