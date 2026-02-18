import unittest

from backend.document_linking import (
    alias_tokens_from_path,
    classify_doc_type,
    extract_frontmatter_references,
    is_generic_phase_progress_slug,
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

    def test_classify_doc_type_detects_progress(self) -> None:
        self.assertEqual(classify_doc_type("progress/collection-data-consistency/phase-1-progress.md"), "progress")


if __name__ == "__main__":
    unittest.main()
