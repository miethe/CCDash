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

    def test_parse_lineage_frontmatter_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            docs_dir = root / "docs" / "project_plans" / "implementation_plans" / "features"
            docs_dir.mkdir(parents=True, exist_ok=True)
            path = docs_dir / "composite-artifact-ux-v2.md"
            path.write_text(
                """---
title: Composite Artifact UX v2
status: draft
feature_slug: composite-artifact-ux-v2
lineage_family: composite-artifact
lineage_parent: /docs/project_plans/implementation_plans/features/composite-artifact-infrastructure-v1.md
lineage_children:
  - composite-artifact-ux-v3
lineage_type: expansion
---
Body
""",
                encoding="utf-8",
            )

            doc = parse_document_file(path, root / "docs" / "project_plans", project_root=root)
            self.assertIsNotNone(doc)
            assert doc is not None
            self.assertEqual(doc.frontmatter.lineageFamily, "composite-artifact")
            self.assertEqual(doc.frontmatter.lineageParent, "composite-artifact-infrastructure-v1")
            self.assertEqual(doc.frontmatter.lineageChildren, ["composite-artifact-ux-v3"])
            self.assertEqual(doc.frontmatter.lineageType, "expansion")
            self.assertIn("composite-artifact-infrastructure-v1", doc.frontmatter.linkedFeatures)

    def test_parse_canonical_fields_and_typed_linked_features(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            docs_dir = root / "docs" / "project_plans" / "design-specs" / "features"
            docs_dir.mkdir(parents=True, exist_ok=True)
            path = docs_dir / "feature-alpha-v2.md"
            path.write_text(
                """---
title: Feature Alpha UX
doc_type: design_spec
description: Detailed design scope.
summary: Design summary.
priority: high
risk_level: medium
complexity: high
track: design
timeline_estimate: 2 weeks
target_release: R2
milestone: M2
decision_status: approved
execution_readiness: ready
test_impact: medium
primary_doc_role: supporting_design
feature_slug: feature-alpha-v2
feature_family: feature-alpha
feature_version: v2
plan_ref: docs/project_plans/implementation_plans/features/feature-alpha-v2.md
implementation_plan_ref: docs/project_plans/implementation_plans/features/feature-alpha-v2.md
linked_features:
  - feature-beta-v1
  - feature: feature-gamma-v1
    type: dependency
    source: manual
    confidence: 0.9
linked_tasks:
  - TASK-2.1
request_log_ids:
  - REQ-20260301-feature-alpha-2
commit_refs:
  - abc1234
pr_refs:
  - "321"
---
Body
""",
                encoding="utf-8",
            )

            doc = parse_document_file(path, root / "docs" / "project_plans", project_root=root)
            self.assertIsNotNone(doc)
            assert doc is not None
            self.assertEqual(doc.docType, "design_doc")
            self.assertEqual(doc.docSubtype, "design_spec")
            self.assertEqual(doc.priority, "high")
            self.assertEqual(doc.riskLevel, "medium")
            self.assertEqual(doc.metadata.executionReadiness, "ready")
            self.assertEqual(doc.metadata.testImpact, "medium")
            self.assertEqual(doc.metadata.primaryDocRole, "supporting_design")
            self.assertEqual(doc.featureSlug, "feature-alpha-v2")
            self.assertEqual(doc.featureFamily, "feature-alpha")
            self.assertEqual(doc.featureVersion, "v2")
            self.assertIn("feature-gamma-v1", doc.frontmatter.linkedFeatures)
            self.assertTrue(any(ref.feature == "feature-gamma-v1" for ref in doc.frontmatter.linkedFeatureRefs))
            self.assertIn("TASK-2.1", doc.frontmatter.linkedTasks)
            self.assertIn("REQ-20260301-feature-alpha-2", doc.frontmatter.requestLogIds)
            self.assertIn("abc1234", doc.frontmatter.commitRefs)
            self.assertIn("321", doc.frontmatter.prRefs)


if __name__ == "__main__":
    unittest.main()
