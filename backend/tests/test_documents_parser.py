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

    def test_parse_progress_document_retains_parallelization_and_source_document_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            progress_dir = root / ".claude" / "progress" / "feature-b"
            progress_dir.mkdir(parents=True, exist_ok=True)
            path = progress_dir / "phase-2-progress.md"
            path.write_text(
                """---
title: Feature B Phase 2
status: completed
phase: 2
source_documents:
  - docs/project_plans/implementation_plans/features/feature-b-v1.md
parallelization:
  batch_1: [B-201]
  batch_2: [B-202, B-203]
tasks:
  - id: B-201
    description: "Batch one"
    status: completed
  - id: B-202
    description: "Batch two"
    status: pending
---
Body
""",
                encoding="utf-8",
            )

            doc = parse_document_file(path, root / ".claude" / "progress", project_root=root)
            self.assertIsNotNone(doc)
            assert doc is not None
            self.assertIn(
                "docs/project_plans/implementation_plans/features/feature-b-v1.md",
                doc.frontmatter.relatedRefs,
            )
            self.assertIn(
                "parallelization",
                doc.metadata.docTypeFields,
            )
            self.assertEqual(
                doc.metadata.docTypeFields["parallelization"],
                {
                    "batch_1": ["B-201"],
                    "batch_2": ["B-202", "B-203"],
                },
            )
            self.assertEqual(doc.statusNormalized, "completed")

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

    def test_parse_blocked_by_and_sequence_order_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            docs_dir = root / "docs" / "project_plans" / "implementation_plans" / "features"
            docs_dir.mkdir(parents=True, exist_ok=True)
            path = docs_dir / "feature-delta-v2.md"
            path.write_text(
                """---
title: Feature Delta Plan
status: blocked
feature_slug: feature-delta-v2
feature_family: feature-delta
blocked_by:
  - feature-alpha-v1
  - docs/project_plans/implementation_plans/features/feature-beta-v2.md
sequence_order: 2
---
Body
""",
                encoding="utf-8",
            )

            doc = parse_document_file(path, root / "docs" / "project_plans", project_root=root)
            self.assertIsNotNone(doc)
            assert doc is not None
            self.assertEqual(doc.featureFamily, "feature-delta")
            self.assertEqual(doc.sequenceOrder, 2)
            self.assertEqual(doc.metadata.sequenceOrder, 2)
            self.assertEqual(doc.frontmatter.sequenceOrder, 2)
            self.assertEqual(doc.blockedBy, ["feature-alpha-v1", "feature-beta-v2"])
            self.assertEqual(doc.metadata.blockedBy, ["feature-alpha-v1", "feature-beta-v2"])
            self.assertEqual(doc.frontmatter.blockedBy, ["feature-alpha-v1", "feature-beta-v2"])
            self.assertTrue(
                any(
                    ref.feature == "feature-alpha-v1"
                    and ref.type == "blocked_by"
                    and ref.source == "blocked_by"
                    for ref in doc.frontmatter.linkedFeatureRefs
                )
            )

    def test_parse_legacy_alias_fields_for_backfill_compatibility(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            docs_dir = root / "docs"
            docs_dir.mkdir(parents=True, exist_ok=True)

            legacy_spec = docs_dir / "document-entity-spec.md"
            legacy_spec.write_text(
                """---
title: Document Entity Spec
status: review
duration: 3 days
api_contracts:
  - endpoint: /api/documents
compatibility_notes:
  - Keep legacy keys ingestible
breaking_changes:
  - Drop deprecated aliases after migration
---
Spec body
""",
                encoding="utf-8",
            )

            plan_dir = root / "docs" / "project_plans" / "implementation_plans" / "features"
            plan_dir.mkdir(parents=True, exist_ok=True)
            legacy_plan = plan_dir / "feature-legacy-v1.md"
            legacy_plan.write_text(
                """---
title: "Implementation Plan: Legacy Feature"
status: in-progress
effort_estimate:
  engineering_weeks: 2
  story_points: 13
release_target: 2026-Q3
test_strategy:
  - Validate parser migration logic
readiness: ready
testing_impact: high
---
Plan body
""",
                encoding="utf-8",
            )

            spec_doc = parse_document_file(legacy_spec, root / "docs", project_root=root)
            self.assertIsNotNone(spec_doc)
            assert spec_doc is not None
            self.assertEqual(spec_doc.docType, "spec")
            self.assertEqual(spec_doc.docSubtype, "spec")
            self.assertEqual(spec_doc.category, "specs")
            self.assertEqual(spec_doc.timelineEstimate, "3 days")
            self.assertIn("interfaces", spec_doc.metadata.docTypeFields)
            self.assertIn("migration_notes", spec_doc.metadata.docTypeFields)

            plan_doc = parse_document_file(legacy_plan, root / "docs" / "project_plans", project_root=root)
            self.assertIsNotNone(plan_doc)
            assert plan_doc is not None
            self.assertEqual(plan_doc.docType, "implementation_plan")
            self.assertEqual(plan_doc.timelineEstimate, "2 weeks, 13 points")
            self.assertEqual(plan_doc.targetRelease, "2026-Q3")
            self.assertEqual(plan_doc.executionReadiness, "ready")
            self.assertEqual(plan_doc.testImpact, "high")
            self.assertIn("testing_strategy", plan_doc.metadata.docTypeFields)

    def test_parse_each_canonical_doc_type_schema_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            docs_root = root / "docs" / "project_plans"
            progress_root = root / ".claude" / "progress"

            fixtures = [
                {
                    "path": docs_root / "PRDs" / "features" / "feature-canonical-v1.md",
                    "base_dir": docs_root,
                    "contents": """---
title: "PRD: Canonical"
status: in_progress
problem_statement: "Problem"
---
Body
""",
                    "expected_type": "prd",
                    "expected_field": "problem_statement",
                },
                {
                    "path": docs_root / "implementation_plans" / "features" / "feature-canonical-v1.md",
                    "base_dir": docs_root,
                    "contents": """---
title: "Plan: Canonical"
status: in_progress
objective: "Ship this"
---
Body
""",
                    "expected_type": "implementation_plan",
                    "expected_field": "objective",
                },
                {
                    "path": docs_root / "implementation_plans" / "features" / "feature-canonical-v1" / "phase-1-core.md",
                    "base_dir": docs_root,
                    "contents": """---
title: "Phase 1"
status: pending
phase_title: "Core"
---
Body
""",
                    "expected_type": "phase_plan",
                    "expected_field": "phase_title",
                },
                {
                    "path": progress_root / "feature-canonical-v1" / "phase-1-progress.md",
                    "base_dir": progress_root,
                    "contents": """---
title: "Progress 1"
status: in_progress
completion_estimate: "Tomorrow"
---
Body
""",
                    "expected_type": "progress",
                    "expected_field": "completion_estimate",
                },
                {
                    "path": docs_root / "reports" / "feature-canonical-audit.md",
                    "base_dir": docs_root,
                    "contents": """---
title: "Report: Canonical"
status: completed
report_kind: audit
---
Body
""",
                    "expected_type": "report",
                    "expected_field": "report_kind",
                },
                {
                    "path": docs_root / "design-specs" / "features" / "feature-canonical-v1.md",
                    "base_dir": docs_root,
                    "contents": """---
title: "Design: Canonical"
status: review
surfaces:
  - dashboard
---
Body
""",
                    "expected_type": "design_doc",
                    "expected_field": "surfaces",
                },
                {
                    "path": docs_root / "specs" / "feature-canonical-api.md",
                    "base_dir": docs_root,
                    "contents": """---
title: "Spec: Canonical"
status: review
interfaces:
  - name: DocumentsAPI
---
Body
""",
                    "expected_type": "spec",
                    "expected_field": "interfaces",
                },
                {
                    "path": root / "docs" / "notes" / "feature-canonical-notes.md",
                    "base_dir": root / "docs",
                    "contents": """---
title: "General Document"
status: pending
---
Body
""",
                    "expected_type": "document",
                    "expected_field": "",
                },
            ]

            for fixture in fixtures:
                fixture_path = fixture["path"]
                fixture_path.parent.mkdir(parents=True, exist_ok=True)
                fixture_path.write_text(str(fixture["contents"]), encoding="utf-8")

            for fixture in fixtures:
                with self.subTest(path=str(fixture["path"])):
                    doc = parse_document_file(
                        fixture["path"],
                        fixture["base_dir"],
                        project_root=root,
                    )
                    self.assertIsNotNone(doc)
                    assert doc is not None
                    self.assertEqual(doc.docType, fixture["expected_type"])
                    expected_field = str(fixture["expected_field"])
                    if expected_field:
                        self.assertIn(expected_field, doc.metadata.docTypeFields)


if __name__ == "__main__":
    unittest.main()
