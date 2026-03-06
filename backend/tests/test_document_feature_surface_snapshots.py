import json
import unittest

from backend.routers.api import _map_document_row_to_model
from backend.routers.features import (
    _normalize_document_coverage,
    _normalize_primary_documents,
    _normalize_quality_signals,
)


class DocumentFeatureSurfaceSnapshotTests(unittest.TestCase):
    def test_document_surface_snapshot_contains_schema_alignment_fields(self) -> None:
        row = {
            "id": "DOC-123",
            "title": "Implementation Plan: Snapshot",
            "file_path": "docs/project_plans/implementation_plans/features/snapshot-v1.md",
            "canonical_path": "docs/project_plans/implementation_plans/features/snapshot-v1.md",
            "status": "in-progress",
            "status_normalized": "in_progress",
            "created_at": "2026-03-01T09:00:00Z",
            "updated_at": "2026-03-01T10:30:00Z",
            "last_modified": "2026-03-01T10:30:00Z",
            "author": "codex",
            "doc_type": "implementation_plan",
            "doc_subtype": "implementation_plan",
            "root_kind": "project_plans",
            "category": "features",
            "has_frontmatter": 1,
            "frontmatter_type": "implementation_plan",
            "feature_slug_hint": "snapshot-v1",
            "feature_slug_canonical": "snapshot",
            "prd_ref": "snapshot-v1",
            "phase_token": "1",
            "phase_number": 1,
            "overall_progress": 45.0,
            "total_tasks": 10,
            "completed_tasks": 4,
            "in_progress_tasks": 3,
            "blocked_tasks": 1,
            "frontmatter_json": json.dumps(
                {
                    "linkedFeatures": ["feature-alpha-v1"],
                    "linkedFeatureRefs": [
                        {
                            "feature": "feature-beta-v1",
                            "type": "dependency",
                            "source": "manual",
                            "confidence": 0.9,
                        }
                    ],
                    "relatedRefs": ["docs/project_plans/specs/shared-contract.md"],
                }
            ),
            "metadata_json": json.dumps(
                {
                    "description": "Document description",
                    "summary": "Document summary",
                    "priority": "high",
                    "riskLevel": "medium",
                    "complexity": "high",
                    "track": "migration",
                    "timelineEstimate": "2 weeks",
                    "targetRelease": "2026-Q2",
                    "milestone": "Milestone A",
                    "executionReadiness": "ready",
                    "testImpact": "high",
                    "requestLogIds": ["REQ-20260301-snapshot-1"],
                    "commitRefs": ["abc1234"],
                    "prRefs": ["451"],
                    "docTypeFields": {"objective": "Ship aligned schema views"},
                    "timeline": [
                        {
                            "id": "doc-created",
                            "timestamp": "2026-03-01T09:00:00Z",
                            "label": "Document Created",
                            "kind": "created",
                            "confidence": "high",
                            "source": "frontmatter",
                            "description": "created",
                        }
                    ],
                }
            ),
        }
        doc = _map_document_row_to_model(
            row,
            include_content=False,
            link_counts={"features": 2, "tasks": 1, "sessions": 0, "documents": 3},
        )

        snapshot = {
            "summary": {
                "docType": doc.docType,
                "docSubtype": doc.docSubtype,
                "status": doc.statusNormalized,
                "description": doc.description,
                "summary": doc.summary,
                "priority": doc.priority,
                "riskLevel": doc.riskLevel,
                "complexity": doc.complexity,
                "track": doc.track,
            },
            "delivery": {
                "timelineEstimate": doc.timelineEstimate,
                "executionReadiness": doc.executionReadiness,
                "testImpact": doc.testImpact,
                "targetRelease": doc.targetRelease,
                "milestone": doc.milestone,
                "docTypeFieldKeys": sorted(doc.metadata.docTypeFields.keys()),
            },
            "relationships": {
                "linkedFeatures": doc.frontmatter.linkedFeatures,
                "linkedFeatureRefs": [
                    ref.model_dump(mode="json")
                    for ref in doc.frontmatter.linkedFeatureRefs
                ],
                "relatedRefs": doc.frontmatter.relatedRefs,
                "requestLogIds": doc.metadata.requestLogIds,
                "commitRefs": doc.metadata.commitRefs,
                "prRefs": doc.metadata.prRefs,
            },
            "timelineKinds": [event.kind for event in doc.timeline],
            "linkCounts": doc.linkCounts.model_dump(mode="json"),
        }

        self.assertEqual(
            snapshot,
            {
                "summary": {
                    "docType": "implementation_plan",
                    "docSubtype": "implementation_plan",
                    "status": "in_progress",
                    "description": "Document description",
                    "summary": "Document summary",
                    "priority": "high",
                    "riskLevel": "medium",
                    "complexity": "high",
                    "track": "migration",
                },
                "delivery": {
                    "timelineEstimate": "2 weeks",
                    "executionReadiness": "ready",
                    "testImpact": "high",
                    "targetRelease": "2026-Q2",
                    "milestone": "Milestone A",
                    "docTypeFieldKeys": ["objective"],
                },
                "relationships": {
                    "linkedFeatures": ["feature-alpha-v1"],
                    "linkedFeatureRefs": [
                        {
                            "feature": "feature-beta-v1",
                            "type": "dependency",
                            "source": "manual",
                            "confidence": 0.9,
                            "notes": "",
                            "evidence": [],
                        }
                    ],
                    "relatedRefs": ["docs/project_plans/specs/shared-contract.md"],
                    "requestLogIds": ["REQ-20260301-snapshot-1"],
                    "commitRefs": ["abc1234"],
                    "prRefs": ["451"],
                },
                "timelineKinds": ["created"],
                "linkCounts": {"features": 2, "tasks": 1, "sessions": 0, "documents": 3},
            },
        )

    def test_feature_surface_snapshot_normalizes_primary_docs_coverage_and_quality(self) -> None:
        primary = _normalize_primary_documents(
            {
                "prd": {
                    "id": "DOC-PRD",
                    "title": "PRD Snapshot",
                    "filePath": "docs/project_plans/PRDs/features/snapshot-v1.md",
                    "docType": "prd",
                },
                "implementationPlan": {
                    "id": "DOC-PLAN",
                    "title": "Plan Snapshot",
                    "filePath": "docs/project_plans/implementation_plans/features/snapshot-v1.md",
                    "docType": "implementation_plan",
                },
                "phasePlans": [
                    {
                        "id": "DOC-PHASE-1",
                        "title": "Phase 1",
                        "filePath": "docs/project_plans/implementation_plans/features/snapshot-v1/phase-1-core.md",
                        "docType": "phase_plan",
                    }
                ],
                "progressDocs": [
                    {
                        "id": "DOC-PROG-1",
                        "title": "Progress 1",
                        "filePath": ".claude/progress/snapshot-v1/phase-1-progress.md",
                        "docType": "progress",
                    }
                ],
                "supportingDocs": [
                    {
                        "id": "DOC-REPORT",
                        "title": "Audit Report",
                        "filePath": "docs/project_plans/reports/snapshot-audit.md",
                        "docType": "report",
                    },
                    {
                        "id": "DOC-SPEC",
                        "title": "API Spec",
                        "filePath": "docs/project_plans/specs/snapshot-api.md",
                        "docType": "spec",
                    },
                ],
            }
        )
        coverage = _normalize_document_coverage(
            {
                "present": ["prd", "implementation_plan", "progress"],
                "missing": ["report", "design_doc", "spec"],
                "countsByType": {"prd": 1, "implementation_plan": 1, "progress": 1},
                "coverageScore": 0.5,
            }
        )
        quality = _normalize_quality_signals(
            {
                "blockerCount": 2,
                "atRiskTaskCount": 1,
                "integritySignalRefs": ["SIG-1"],
                "reportFindingsBySeverity": {"high": 1, "critical": 0},
                "testImpact": "high",
                "hasBlockingSignals": True,
            }
        )

        snapshot = {
            "primary": {
                "prdType": primary["prd"].docType if primary["prd"] else "",
                "implementationPlanType": (
                    primary["implementationPlan"].docType
                    if primary["implementationPlan"]
                    else ""
                ),
                "phasePlanCount": len(primary["phasePlans"]),
                "progressDocCount": len(primary["progressDocs"]),
                "supportingDocTypes": [doc.docType for doc in primary["supportingDocs"]],
            },
            "coverage": coverage,
            "quality": quality,
        }

        self.assertEqual(
            snapshot,
            {
                "primary": {
                    "prdType": "prd",
                    "implementationPlanType": "implementation_plan",
                    "phasePlanCount": 1,
                    "progressDocCount": 1,
                    "supportingDocTypes": ["report", "spec"],
                },
                "coverage": {
                    "present": ["prd", "implementation_plan", "progress"],
                    "missing": ["report", "design_doc", "spec"],
                    "countsByType": {"prd": 1, "implementation_plan": 1, "progress": 1},
                    "coverageScore": 0.5,
                },
                "quality": {
                    "blockerCount": 2,
                    "atRiskTaskCount": 1,
                    "integritySignalRefs": ["SIG-1"],
                    "reportFindingsBySeverity": {"high": 1, "critical": 0},
                    "testImpact": "high",
                    "hasBlockingSignals": True,
                },
            },
        )


if __name__ == "__main__":
    unittest.main()
