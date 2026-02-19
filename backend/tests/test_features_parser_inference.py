import tempfile
import unittest
from pathlib import Path

import yaml

from backend.parsers.features import scan_features


def _frontmatter_status(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return ""
    _, fm_text, _ = text.split("---", 2)
    fm = yaml.safe_load(fm_text) or {}
    return str(fm.get("status") or "")


class FeatureParserInferenceTests(unittest.TestCase):
    def test_progress_completion_marks_feature_done_and_writes_through_top_level_docs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            docs_dir = root / "docs" / "project_plans"
            progress_dir = root / ".claude" / "progress"
            (docs_dir / "implementation_plans" / "features").mkdir(parents=True, exist_ok=True)
            (docs_dir / "PRDs" / "features").mkdir(parents=True, exist_ok=True)
            (progress_dir / "feature-a-v1").mkdir(parents=True, exist_ok=True)

            plan_file = docs_dir / "implementation_plans" / "features" / "feature-a-v1.md"
            plan_file.write_text(
                """---
title: "Implementation Plan: Feature A"
status: draft
---
Plan body
""",
                encoding="utf-8",
            )

            prd_file = docs_dir / "PRDs" / "features" / "feature-a-v1.md"
            prd_file.write_text(
                """---
title: "PRD: Feature A"
status: draft
---
PRD body
""",
                encoding="utf-8",
            )

            progress_file = progress_dir / "feature-a-v1" / "phase-1-progress.md"
            progress_file.write_text(
                """---
title: Feature A Phase 1
status: completed
phase: 1
total_tasks: 2
completed_tasks: 2
---
Progress body
""",
                encoding="utf-8",
            )

            features = scan_features(docs_dir, progress_dir)
            self.assertEqual(len(features), 1)
            self.assertEqual(features[0].status, "done")
            self.assertEqual(_frontmatter_status(plan_file), "inferred_complete")
            self.assertEqual(_frontmatter_status(prd_file), "inferred_complete")

    def test_completed_plan_marks_feature_done_and_writes_through_prd(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            docs_dir = root / "docs" / "project_plans"
            progress_dir = root / ".claude" / "progress"
            (docs_dir / "implementation_plans" / "features").mkdir(parents=True, exist_ok=True)
            (docs_dir / "PRDs" / "features").mkdir(parents=True, exist_ok=True)
            progress_dir.mkdir(parents=True, exist_ok=True)

            plan_file = docs_dir / "implementation_plans" / "features" / "feature-b-v1.md"
            plan_file.write_text(
                """---
title: "Implementation Plan: Feature B"
status: completed
---
Plan body
""",
                encoding="utf-8",
            )

            prd_file = docs_dir / "PRDs" / "features" / "feature-b-v1.md"
            prd_file.write_text(
                """---
title: "PRD: Feature B"
status: draft
---
PRD body
""",
                encoding="utf-8",
            )

            features = scan_features(docs_dir, progress_dir)
            self.assertEqual(len(features), 1)
            self.assertEqual(features[0].status, "done")
            self.assertEqual(_frontmatter_status(plan_file), "completed")
            self.assertEqual(_frontmatter_status(prd_file), "inferred_complete")


if __name__ == "__main__":
    unittest.main()
