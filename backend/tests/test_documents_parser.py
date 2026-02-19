import tempfile
import unittest
from pathlib import Path

from backend.parsers.documents import parse_document_file


class DocumentParserTests(unittest.TestCase):
    def test_parse_progress_document_extracts_typed_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            progress_dir = root / ".claude" / "progress" / "feature-a"
            progress_dir.mkdir(parents=True, exist_ok=True)
            path = progress_dir / "phase-1-progress.md"
            path.write_text(
                """---
title: Feature A Phase 1
status: in-progress
phase: 1
progress: 40
total_tasks: 5
completed_tasks: 2
in_progress_tasks: 2
blocked_tasks: 1
linked_features:
  - feature-a-v1
request_log_id: REQ-20260101-feature-a-1
---
Body
""",
                encoding="utf-8",
            )

            doc = parse_document_file(path, root / ".claude" / "progress", project_root=root)
            self.assertIsNotNone(doc)
            assert doc is not None
            self.assertEqual(doc.rootKind, "progress")
            self.assertEqual(doc.docSubtype, "progress_phase")
            self.assertEqual(doc.phaseToken, "1")
            self.assertEqual(doc.totalTasks, 5)
            self.assertEqual(doc.completedTasks, 2)
            self.assertEqual(doc.inProgressTasks, 2)
            self.assertEqual(doc.blockedTasks, 1)
            self.assertIn("feature-a-v1", doc.featureCandidates)
            self.assertIn("REQ-20260101-feature-a-1", doc.metadata.requestLogIds)


if __name__ == "__main__":
    unittest.main()
