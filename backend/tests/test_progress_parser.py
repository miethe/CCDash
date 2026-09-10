import tempfile
import unittest
from pathlib import Path

from backend.parsers.progress import parse_progress_file


class ProgressParserTests(unittest.TestCase):
    def _write_progress_file(self, tmpdir: Path, body: str) -> Path:
        progress_dir = tmpdir / ".claude" / "progress" / "feature-a"
        progress_dir.mkdir(parents=True, exist_ok=True)
        path = progress_dir / "phase-1-progress.md"
        path.write_text(body, encoding="utf-8")
        return path

    def test_reads_assigned_model_field_not_model(self) -> None:
        """AC: progress.py reads `assigned_model`, not the nonexistent `model` key."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            path = self._write_progress_file(
                root,
                """---
prd: feature-a
phase: 1
tasks:
  - id: T1-001
    name: Do the thing
    status: in_progress
    assigned_model: opus
---
Body
""",
            )
            tasks = parse_progress_file(path, root / ".claude" / "progress")
            self.assertEqual(len(tasks), 1)
            self.assertEqual(tasks[0].lastAgent, "Claude 3 Opus")

    def test_dependencies_persist_fully_and_not_truncated_into_tags(self) -> None:
        """AC: dependencies persist as a real structured field, not [:3]-truncated tags."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            deps = ["T1-001", "T1-002", "T1-003", "T1-004", "T1-005"]
            path = self._write_progress_file(
                root,
                f"""---
prd: feature-a
phase: 1
tasks:
  - id: T1-006
    name: Depends on everything
    status: pending
    dependencies: {deps}
---
Body
""",
            )
            tasks = parse_progress_file(path, root / ".claude" / "progress")
            self.assertEqual(len(tasks), 1)
            task = tasks[0]
            self.assertEqual(task.dependencies, deps)
            for dep in deps:
                self.assertNotIn(dep, task.tags)

    def test_multi_assignee_not_dropped_to_single_value(self) -> None:
        """AC: multi-assignee assigned_to is preserved, not collapsed to one owner."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            assignees = ["alice", "bob", "carol"]
            path = self._write_progress_file(
                root,
                f"""---
prd: feature-a
phase: 1
tasks:
  - id: T1-007
    name: Shared task
    status: pending
    assigned_to: {assignees}
---
Body
""",
            )
            tasks = parse_progress_file(path, root / ".claude" / "progress")
            self.assertEqual(len(tasks), 1)
            task = tasks[0]
            self.assertEqual(task.owner, "alice")
            self.assertEqual(task.assignees, assignees)


if __name__ == "__main__":
    unittest.main()
