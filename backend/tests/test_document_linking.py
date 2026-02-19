import unittest
from pathlib import Path

from backend.document_linking import (
    alias_tokens_from_path,
    canonical_project_path,
    classify_doc_type,
    classify_doc_subtype,
    extract_frontmatter_references,
    feature_slug_from_path,
    infer_project_root,
    is_generic_phase_progress_slug,
    normalize_doc_status,
    normalize_doc_subtype,
)


class DocumentLinkingTests(unittest.TestCase):
    def test_alias_tokens_from_progress_path_uses_parent_feature_slug(self) -> None:
        aliases = alias_tokens_from_path("progress/collection-data-consistency/phase-1-progress.md")

        self.assertIn("collection-data-consistency", aliases)
        self.assertNotIn("phase-1-progress", aliases)

    def test_generic_phase_progress_slug_detection(self) -> None:
        self.assertTrue(is_generic_phase_progress_slug("phase-1-progress"))
        self.assertTrue(is_generic_phase_progress_slug("phase-all-progress"))
        self.assertFalse(is_generic_phase_progress_slug("collection-data-consistency-v1"))

    def test_extract_frontmatter_references_collects_related_and_prd(self) -> None:
        refs = extract_frontmatter_references(
            {
                "related": [
                    "docs/project_plans/implementation_plans/refactors/collection-data-consistency-v1.md",
                    "collection-data-consistency-v1",
                ],
                "prd": "collection-data-consistency-v1",
            }
        )

        feature_refs = refs.get("featureRefs", [])
        assert isinstance(feature_refs, list)
        self.assertIn("collection-data-consistency-v1", feature_refs)
        self.assertIn("collection-data-consistency", feature_refs)

    def test_extract_frontmatter_references_ignores_free_text_with_slash(self) -> None:
        refs = extract_frontmatter_references(
            {
                "notes": "Completed validation/persistence flows and paths/types handling",
                "related": ["progress/collection-data-consistency/phase-1-progress.md"],
            }
        )

        feature_refs = refs.get("featureRefs", [])
        assert isinstance(feature_refs, list)
        self.assertIn("collection-data-consistency", feature_refs)
        self.assertNotIn("persistence flows", feature_refs)
        self.assertNotIn("types handling", feature_refs)

    def test_feature_slug_from_path_supports_nested_feature_phase_docs(self) -> None:
        feature_slug = feature_slug_from_path(
            "docs/project_plans/implementation_plans/features/marketplace-source-detection-improvements-v1/phase-1-backend.md"
        )
        self.assertEqual(feature_slug, "marketplace-source-detection-improvements-v1")

    def test_feature_slug_from_path_supports_progress_layout(self) -> None:
        feature_slug = feature_slug_from_path("progress/marketplace-source-detection-improvements/phase-3-progress.md")
        self.assertEqual(feature_slug, "marketplace-source-detection-improvements")

    def test_classify_doc_type_detects_progress(self) -> None:
        self.assertEqual(classify_doc_type("progress/collection-data-consistency/phase-1-progress.md"), "progress")

    def test_infer_project_root_supports_docs_and_dot_claude_progress(self) -> None:
        docs_dir = Path("/tmp/workspace/docs/project_plans")
        progress_dir = Path("/tmp/workspace/.claude/progress")
        root = infer_project_root(docs_dir, progress_dir)
        self.assertTrue(str(root).endswith("/tmp/workspace"))

    def test_canonical_project_path_returns_project_relative_path(self) -> None:
        project_root = Path("/tmp/workspace")
        full_path = Path("/tmp/workspace/.claude/progress/feature-a/phase-1-progress.md")
        self.assertEqual(
            canonical_project_path(full_path, project_root),
            ".claude/progress/feature-a/phase-1-progress.md",
        )

    def test_classify_doc_subtype_detects_progress_phase(self) -> None:
        self.assertEqual(
            classify_doc_subtype(".claude/progress/feature-a/phase-2-progress.md"),
            "progress_phase",
        )

    def test_normalize_doc_status_maps_variants_to_canonical_values(self) -> None:
        self.assertEqual(normalize_doc_status("Done"), "completed")
        self.assertEqual(normalize_doc_status("inferred complete"), "inferred_complete")
        self.assertEqual(normalize_doc_status("WIP"), "in_progress")
        self.assertEqual(normalize_doc_status("unknown-status"), "pending")

    def test_normalize_doc_subtype_maps_variants_to_canonical_values(self) -> None:
        self.assertEqual(normalize_doc_subtype("implementation-report"), "report")
        self.assertEqual(normalize_doc_subtype("quick feature progress", root_kind="progress"), "progress_quick_feature")
        self.assertEqual(normalize_doc_subtype("phase progress", root_kind="progress"), "progress_phase")

    def test_extract_frontmatter_references_supports_additional_keys(self) -> None:
        refs = extract_frontmatter_references(
            {
                "plan_ref": "docs/project_plans/implementation_plans/features/alpha-v1.md",
                "prd_link": "alpha-v1",
                "related_documents": ["docs/project_plans/reports/alpha-v1-report.md"],
                "request_log_id": "REQ-20260101-alpha-1",
                "git_commit_hashes": [{"hash": "abc1234"}],
            }
        )
        feature_refs = refs.get("featureRefs", [])
        request_refs = refs.get("requestRefs", [])
        commit_refs = refs.get("commitRefs", [])
        assert isinstance(feature_refs, list)
        assert isinstance(request_refs, list)
        assert isinstance(commit_refs, list)
        self.assertIn("alpha-v1", feature_refs)
        self.assertIn("REQ-20260101-alpha-1", request_refs)
        self.assertIn("abc1234", commit_refs)


if __name__ == "__main__":
    unittest.main()
