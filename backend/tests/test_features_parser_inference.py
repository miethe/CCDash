import tempfile
import unittest
import warnings
from pathlib import Path

import yaml

from backend.models import EntityDates, TimelineEvent
from backend.parsers.features import scan_features


def _frontmatter_status(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return ""
    _, fm_text, _ = text.split("---", 2)
    fm = yaml.safe_load(fm_text) or {}
    return str(fm.get("status") or "")


class FeatureParserInferenceTests(unittest.TestCase):
    def test_scan_features_emits_typed_dates_and_timeline_without_serializer_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            docs_dir = root / "docs" / "project_plans"
            progress_dir = root / ".claude" / "progress"
            (docs_dir / "implementation_plans" / "features").mkdir(parents=True, exist_ok=True)
            (docs_dir / "PRDs" / "features").mkdir(parents=True, exist_ok=True)
            (progress_dir / "feature-z-v1").mkdir(parents=True, exist_ok=True)

            plan_file = docs_dir / "implementation_plans" / "features" / "feature-z-v1.md"
            plan_file.write_text(
                """---
title: "Implementation Plan: Feature Z"
status: in-progress
---
Plan body
""",
                encoding="utf-8",
            )
            progress_file = progress_dir / "feature-z-v1" / "phase-1-progress.md"
            progress_file.write_text(
                """---
title: Feature Z Phase 1
status: in-progress
phase: 1
total_tasks: 2
completed_tasks: 1
---
Progress body
""",
                encoding="utf-8",
            )

            features = scan_features(docs_dir, progress_dir)
            self.assertEqual(len(features), 1)
            feature = features[0]
            self.assertIsInstance(feature.dates, EntityDates)
            self.assertTrue(all(isinstance(event, TimelineEvent) for event in feature.timeline))

            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                feature.model_dump()

            unexpected = [
                warning for warning in caught
                if "PydanticSerializationUnexpectedValue" in str(warning.message)
            ]
            self.assertEqual(unexpected, [])

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

    def test_invalid_prd_frontmatter_skips_inferred_write_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            docs_dir = root / "docs" / "project_plans"
            progress_dir = root / ".claude" / "progress"
            (docs_dir / "implementation_plans" / "features").mkdir(parents=True, exist_ok=True)
            (docs_dir / "PRDs" / "features").mkdir(parents=True, exist_ok=True)
            progress_dir.mkdir(parents=True, exist_ok=True)

            plan_file = docs_dir / "implementation_plans" / "features" / "feature-c-v1.md"
            plan_file.write_text(
                """---
title: "Implementation Plan: Feature C"
status: completed
---
Plan body
""",
                encoding="utf-8",
            )

            prd_file = docs_dir / "PRDs" / "features" / "feature-c-v1.md"
            prd_file.write_text(
                """---
<<<<<<< ours
schema_version: '1.1'
=======
schema_version: "1.1"
>>>>>>> theirs
status: draft
---
PRD body
""",
                encoding="utf-8",
            )

            with self.assertLogs("ccdash", level="WARNING") as captured:
                features = scan_features(docs_dir, progress_dir)

            self.assertEqual(len(features), 1)
            self.assertEqual(features[0].status, "done")
            self.assertTrue(any("Skipping inferred status write for" in line for line in captured.output))
            self.assertTrue(any("Invalid YAML frontmatter" in line for line in captured.output))
            self.assertIn("<<<<<<< ours", prd_file.read_text(encoding="utf-8"))

    def test_related_refs_do_not_cause_cross_feature_inferred_completion(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            docs_dir = root / "docs" / "project_plans"
            progress_dir = root / ".claude" / "progress"
            (docs_dir / "implementation_plans" / "features").mkdir(parents=True, exist_ok=True)
            (docs_dir / "PRDs" / "features").mkdir(parents=True, exist_ok=True)
            progress_dir.mkdir(parents=True, exist_ok=True)

            infra_plan = docs_dir / "implementation_plans" / "features" / "composite-artifact-infrastructure-v1.md"
            infra_plan.write_text(
                """---
title: "Implementation Plan: Composite Artifact Infrastructure"
status: completed
---
Plan body
""",
                encoding="utf-8",
            )
            infra_prd = docs_dir / "PRDs" / "features" / "composite-artifact-infrastructure-v1.md"
            infra_prd.write_text(
                """---
title: "PRD: Composite Artifact Infrastructure"
status: draft
---
PRD body
""",
                encoding="utf-8",
            )

            ux_plan = docs_dir / "implementation_plans" / "features" / "composite-artifact-ux-v2.md"
            ux_plan.write_text(
                """---
title: "Implementation Plan: Composite Artifact UX v2"
status: draft
related:
  - /docs/project_plans/implementation_plans/features/composite-artifact-infrastructure-v1.md
---
Plan body
""",
                encoding="utf-8",
            )
            ux_prd = docs_dir / "PRDs" / "features" / "composite-artifact-ux-v2.md"
            ux_prd.write_text(
                """---
title: "PRD: Composite Artifact UX v2"
status: draft
related:
  - /docs/project_plans/PRDs/features/composite-artifact-infrastructure-v1.md
---
PRD body
""",
                encoding="utf-8",
            )

            features = scan_features(docs_dir, progress_dir)
            by_id = {feature.id: feature for feature in features}

            self.assertEqual(by_id["composite-artifact-infrastructure-v1"].status, "done")
            self.assertEqual(by_id["composite-artifact-ux-v2"].status, "backlog")
            self.assertEqual(_frontmatter_status(infra_prd), "inferred_complete")
            self.assertEqual(_frontmatter_status(ux_plan), "draft")
            self.assertEqual(_frontmatter_status(ux_prd), "draft")

    def test_versioned_features_do_not_inherit_owned_docs_or_progress_from_base_slug(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            docs_dir = root / "docs" / "project_plans"
            progress_dir = root / ".claude" / "progress"
            (docs_dir / "implementation_plans" / "features" / "agent-context-entities-v1").mkdir(parents=True, exist_ok=True)
            (docs_dir / "PRDs" / "features").mkdir(parents=True, exist_ok=True)
            (progress_dir / "agent-context-entities").mkdir(parents=True, exist_ok=True)

            plan_v1 = docs_dir / "implementation_plans" / "features" / "agent-context-entities-v1.md"
            plan_v1.write_text(
                """---
title: "Implementation Plan: Agent Context Entities v1"
status: in-progress
---
Plan body
""",
                encoding="utf-8",
            )
            plan_v2 = docs_dir / "implementation_plans" / "features" / "agent-context-entities-v2.md"
            plan_v2.write_text(
                """---
title: "Implementation Plan: Agent Context Entities v2"
status: draft
---
Plan body
""",
                encoding="utf-8",
            )
            phase_plan_v1 = docs_dir / "implementation_plans" / "features" / "agent-context-entities-v1" / "phase-1-core.md"
            phase_plan_v1.write_text(
                """---
title: "Phase 1: Core"
status: in-progress
---
Phase body
""",
                encoding="utf-8",
            )
            prd_v1 = docs_dir / "PRDs" / "features" / "agent-context-entities-v1.md"
            prd_v1.write_text(
                """---
title: "PRD: Agent Context Entities v1"
status: in-progress
---
PRD body
""",
                encoding="utf-8",
            )
            progress_v1 = progress_dir / "agent-context-entities" / "phase-1-progress.md"
            progress_v1.write_text(
                """---
title: "Phase 1 Progress"
status: in-progress
phase: 1
total_tasks: 1
completed_tasks: 0
tasks:
  - id: TASK-1
    title: "Implement route"
    status: in-progress
---
Progress body
""",
                encoding="utf-8",
            )

            features = scan_features(docs_dir, progress_dir)
            by_id = {feature.id: feature for feature in features}
            self.assertIn("agent-context-entities-v1", by_id)
            self.assertIn("agent-context-entities-v2", by_id)

            v1 = by_id["agent-context-entities-v1"]
            v2 = by_id["agent-context-entities-v2"]

            self.assertGreaterEqual(len(v1.phases), 1)
            self.assertEqual(len(v2.phases), 0)

            v2_impl_paths = {doc.filePath for doc in v2.linkedDocs if doc.docType == "implementation_plan"}
            self.assertEqual(
                v2_impl_paths,
                {"docs/project_plans/implementation_plans/features/agent-context-entities-v2.md"},
            )
            self.assertFalse(any(doc.docType == "phase_plan" for doc in v2.linkedDocs))
            self.assertFalse(any(doc.docType == "progress" for doc in v2.linkedDocs))
            self.assertFalse(any(doc.docType == "prd" for doc in v2.linkedDocs))

    def test_lineage_parent_builds_related_feature_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            docs_dir = root / "docs" / "project_plans"
            progress_dir = root / ".claude" / "progress"
            (docs_dir / "implementation_plans" / "features").mkdir(parents=True, exist_ok=True)
            (docs_dir / "PRDs" / "features").mkdir(parents=True, exist_ok=True)
            progress_dir.mkdir(parents=True, exist_ok=True)

            infra_plan = docs_dir / "implementation_plans" / "features" / "composite-artifact-infrastructure-v1.md"
            infra_plan.write_text(
                """---
title: "Implementation Plan: Composite Artifact Infrastructure"
status: draft
feature_slug: composite-artifact-infrastructure-v1
---
Plan body
""",
                encoding="utf-8",
            )
            infra_prd = docs_dir / "PRDs" / "features" / "composite-artifact-infrastructure-v1.md"
            infra_prd.write_text(
                """---
title: "PRD: Composite Artifact Infrastructure"
status: draft
feature_slug: composite-artifact-infrastructure-v1
---
PRD body
""",
                encoding="utf-8",
            )

            ux_plan = docs_dir / "implementation_plans" / "features" / "composite-artifact-ux-v2.md"
            ux_plan.write_text(
                """---
title: "Implementation Plan: Composite Artifact UX v2"
status: draft
feature_slug: composite-artifact-ux-v2
lineage_parent: composite-artifact-infrastructure-v1
lineage_family: composite-artifact
lineage_type: expansion
---
Plan body
""",
                encoding="utf-8",
            )
            ux_prd = docs_dir / "PRDs" / "features" / "composite-artifact-ux-v2.md"
            ux_prd.write_text(
                """---
title: "PRD: Composite Artifact UX v2"
status: draft
feature_slug: composite-artifact-ux-v2
lineage_parent: composite-artifact-infrastructure-v1
lineage_family: composite-artifact
lineage_type: expansion
---
PRD body
""",
                encoding="utf-8",
            )

            features = scan_features(docs_dir, progress_dir)
            by_id = {feature.id: feature for feature in features}

            self.assertIn("composite-artifact-infrastructure-v1", by_id["composite-artifact-ux-v2"].relatedFeatures)
            self.assertIn("composite-artifact-ux-v2", by_id["composite-artifact-infrastructure-v1"].relatedFeatures)

    def test_feature_rollups_include_primary_docs_coverage_and_quality_signals(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            docs_dir = root / "docs" / "project_plans"
            progress_dir = root / ".claude" / "progress"
            (docs_dir / "implementation_plans" / "features").mkdir(parents=True, exist_ok=True)
            (docs_dir / "PRDs" / "features").mkdir(parents=True, exist_ok=True)
            (docs_dir / "reports").mkdir(parents=True, exist_ok=True)
            (progress_dir / "feature-rollup-v1").mkdir(parents=True, exist_ok=True)

            (docs_dir / "implementation_plans" / "features" / "feature-rollup-v1.md").write_text(
                """---
title: "Implementation Plan: Rollup Feature"
status: in-progress
description: "Plan description"
complexity: high
track: migration
timeline_estimate: "2 weeks"
owners: [plan-owner]
contributors: [plan-contributor]
request_log_ids: [REQ-PLAN-1]
commit_refs: [plan-commit]
pr_refs: [plan-pr]
execution_readiness: ready
---
Plan body
""",
                encoding="utf-8",
            )
            (docs_dir / "PRDs" / "features" / "feature-rollup-v1.md").write_text(
                """---
title: "PRD: Rollup Feature"
status: in-progress
description: "PRD description"
summary: "PRD summary"
priority: high
risk_level: medium
target_release: "2026-Q2"
milestone: "Milestone A"
owners: [prd-owner]
contributors: [prd-contributor]
test_impact: high
---
PRD body
""",
                encoding="utf-8",
            )
            (docs_dir / "reports" / "feature-rollup-audit.md").write_text(
                """---
title: "Report: Rollup Audit"
doc_type: report
feature_slug: feature-rollup-v1
integrity_signal_refs: [SIG-1]
findings:
  - severity: high
    description: "High severity issue"
---
Report body
""",
                encoding="utf-8",
            )
            (progress_dir / "feature-rollup-v1" / "phase-1-progress.md").write_text(
                """---
title: "Phase 1 Progress"
status: in-progress
phase: 1
owners: [progress-owner]
blockers:
  - "Waiting on dependency"
tasks:
  - id: TASK-1
    title: "Blocked task"
    status: blocked
    git_commit: abc1234
---
Progress body
""",
                encoding="utf-8",
            )

            features = scan_features(docs_dir, progress_dir)
            self.assertEqual(len(features), 1)
            feature = features[0]

            self.assertEqual(feature.description, "PRD description")
            self.assertEqual(feature.summary, "PRD summary")
            self.assertEqual(feature.priority, "high")
            self.assertEqual(feature.complexity, "high")
            self.assertEqual(feature.track, "migration")
            self.assertEqual(feature.timelineEstimate, "2 weeks")
            self.assertEqual(feature.targetRelease, "2026-Q2")
            self.assertEqual(feature.milestone, "Milestone A")
            self.assertEqual(feature.executionReadiness, "blocked")
            self.assertEqual(feature.testImpact, "high")
            self.assertIn("plan-owner", feature.owners)
            self.assertIn("prd-owner", feature.owners)
            self.assertIn("progress-owner", feature.owners)
            self.assertIn("plan-contributor", feature.contributors)
            self.assertIn("prd-contributor", feature.contributors)
            self.assertIn("REQ-PLAN-1", feature.requestLogIds)
            self.assertIn("plan-commit", feature.commitRefs)
            self.assertIn("abc1234", feature.commitRefs)
            self.assertIn("plan-pr", feature.prRefs)

            self.assertIsNotNone(feature.primaryDocuments.prd)
            self.assertIsNotNone(feature.primaryDocuments.implementationPlan)
            self.assertGreaterEqual(len(feature.primaryDocuments.progressDocs), 1)

            self.assertIn("prd", feature.documentCoverage.present)
            self.assertIn("implementation_plan", feature.documentCoverage.present)
            self.assertIn("progress", feature.documentCoverage.present)
            self.assertIn("spec", feature.documentCoverage.missing)

            self.assertGreaterEqual(feature.qualitySignals.blockerCount, 1)
            self.assertGreaterEqual(feature.qualitySignals.atRiskTaskCount, 1)
            self.assertTrue(feature.qualitySignals.hasBlockingSignals)
            self.assertIn("SIG-1", feature.qualitySignals.integritySignalRefs)
            self.assertEqual(feature.qualitySignals.reportFindingsBySeverity.get("high"), 1)

    def test_linked_feature_refs_include_lineage_and_inferred_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            docs_dir = root / "docs" / "project_plans"
            progress_dir = root / ".claude" / "progress"
            (docs_dir / "implementation_plans" / "features").mkdir(parents=True, exist_ok=True)
            (docs_dir / "PRDs" / "features").mkdir(parents=True, exist_ok=True)
            progress_dir.mkdir(parents=True, exist_ok=True)

            shared_ref = "docs/project_plans/specs/shared-delivery-spec.md"

            (docs_dir / "implementation_plans" / "features" / "feature-a-v1.md").write_text(
                f"""---
title: "Implementation Plan: Feature A"
status: in-progress
related_documents:
  - {shared_ref}
---
Plan body
""",
                encoding="utf-8",
            )
            (docs_dir / "PRDs" / "features" / "feature-a-v1.md").write_text(
                """---
title: "PRD: Feature A"
status: in-progress
---
PRD body
""",
                encoding="utf-8",
            )
            (docs_dir / "implementation_plans" / "features" / "feature-b-v1.md").write_text(
                f"""---
title: "Implementation Plan: Feature B"
status: in-progress
lineage_parent: feature-a-v1
related_documents:
  - {shared_ref}
---
Plan body
""",
                encoding="utf-8",
            )
            (docs_dir / "PRDs" / "features" / "feature-b-v1.md").write_text(
                """---
title: "PRD: Feature B"
status: in-progress
lineage_parent: feature-a-v1
---
PRD body
""",
                encoding="utf-8",
            )

            features = scan_features(docs_dir, progress_dir)
            by_id = {feature.id: feature for feature in features}
            refs_b = by_id["feature-b-v1"].linkedFeatures
            refs_a = by_id["feature-a-v1"].linkedFeatures

            self.assertTrue(
                any(
                    ref.feature == "feature-a-v1"
                    and ref.source == "derived_lineage"
                    and ref.type == "lineage_parent"
                    for ref in refs_b
                )
            )
            self.assertTrue(
                any(
                    ref.feature == "feature-b-v1"
                    and ref.source == "derived_lineage"
                    and ref.type == "lineage_child"
                    for ref in refs_a
                )
            )
            self.assertTrue(
                any(
                    ref.feature == "feature-a-v1"
                    and ref.source == "inferred"
                    and ref.type == "shared_document_context"
                    for ref in refs_b
                )
            )

    def test_feature_rollups_apply_precedence_rules_for_bubbled_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            docs_dir = root / "docs" / "project_plans"
            progress_dir = root / ".claude" / "progress"
            (docs_dir / "implementation_plans" / "features").mkdir(parents=True, exist_ok=True)
            (docs_dir / "PRDs" / "features").mkdir(parents=True, exist_ok=True)
            progress_dir.mkdir(parents=True, exist_ok=True)

            (docs_dir / "implementation_plans" / "features" / "feature-precedence-v1.md").write_text(
                """---
title: "Implementation Plan: Precedence"
status: in-progress
description: "Plan description"
summary: "Plan summary"
priority: critical
risk_level: high
complexity: high
track: migration
timeline_estimate: "3 weeks"
target_release: "2026-Q4"
milestone: "Plan Milestone"
execution_readiness: ready
test_impact: low
---
Plan body
""",
                encoding="utf-8",
            )
            (docs_dir / "PRDs" / "features" / "feature-precedence-v1.md").write_text(
                """---
title: "PRD: Precedence"
status: in-progress
description: "PRD description"
summary: "PRD summary"
priority: low
risk_level: medium
target_release: "2026-Q3"
milestone: "PRD Milestone"
execution_readiness: review
test_impact: high
---
PRD body
""",
                encoding="utf-8",
            )

            features = scan_features(docs_dir, progress_dir)
            self.assertEqual(len(features), 1)
            feature = features[0]

            self.assertEqual(feature.description, "PRD description")
            self.assertEqual(feature.summary, "PRD summary")
            self.assertEqual(feature.priority, "low")
            self.assertEqual(feature.riskLevel, "medium")
            self.assertEqual(feature.complexity, "high")
            self.assertEqual(feature.track, "migration")
            self.assertEqual(feature.timelineEstimate, "3 weeks")
            self.assertEqual(feature.targetRelease, "2026-Q3")
            self.assertEqual(feature.milestone, "PRD Milestone")
            self.assertEqual(feature.testImpact, "high")
            self.assertEqual(feature.executionReadiness, "review")

    def test_linked_feature_refs_preserve_manual_plus_derived_relationships(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            docs_dir = root / "docs" / "project_plans"
            progress_dir = root / ".claude" / "progress"
            (docs_dir / "implementation_plans" / "features").mkdir(parents=True, exist_ok=True)
            (docs_dir / "PRDs" / "features").mkdir(parents=True, exist_ok=True)
            progress_dir.mkdir(parents=True, exist_ok=True)

            shared_ref = "docs/project_plans/specs/shared-contract.md"

            (docs_dir / "implementation_plans" / "features" / "feature-a-v1.md").write_text(
                f"""---
title: "Implementation Plan: Feature A"
status: in-progress
related_documents:
  - {shared_ref}
---
Plan body
""",
                encoding="utf-8",
            )
            (docs_dir / "PRDs" / "features" / "feature-a-v1.md").write_text(
                """---
title: "PRD: Feature A"
status: in-progress
---
PRD body
""",
                encoding="utf-8",
            )

            (docs_dir / "implementation_plans" / "features" / "feature-b-v1.md").write_text(
                f"""---
title: "Implementation Plan: Feature B"
status: in-progress
lineage_parent: feature-a-v1
related_documents:
  - {shared_ref}
linked_features:
  - feature: feature-a-v1
    type: dependency
    source: manual
    confidence: 0.88
---
Plan body
""",
                encoding="utf-8",
            )
            (docs_dir / "PRDs" / "features" / "feature-b-v1.md").write_text(
                """---
title: "PRD: Feature B"
status: in-progress
lineage_parent: feature-a-v1
---
PRD body
""",
                encoding="utf-8",
            )

            features = scan_features(docs_dir, progress_dir)
            by_id = {feature.id: feature for feature in features}
            refs_b = by_id["feature-b-v1"].linkedFeatures

            self.assertTrue(
                any(
                    ref.feature == "feature-a-v1"
                    and ref.source == "manual"
                    and ref.type == "dependency"
                    for ref in refs_b
                )
            )
            self.assertTrue(
                any(
                    ref.feature == "feature-a-v1"
                    and ref.source == "derived_lineage"
                    and ref.type == "lineage_parent"
                    for ref in refs_b
                )
            )
            self.assertTrue(
                any(
                    ref.feature == "feature-a-v1"
                    and ref.source == "inferred"
                    and ref.type == "shared_document_context"
                    for ref in refs_b
                )
            )


if __name__ == "__main__":
    unittest.main()
