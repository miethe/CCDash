import unittest

from backend.services.integrations.skillmeat_routes import build_definition_source_url


class SkillMeatRoutesTests(unittest.TestCase):
    def test_artifact_urls_use_collection_route(self) -> None:
        self.assertEqual(
            build_definition_source_url(
                "artifact",
                "skill:artifact-tracking",
                web_base_url="http://localhost:3000",
                collection_id="default",
            ),
            "http://localhost:3000/collection?collection=default&artifact=skill%3Aartifact-tracking",
        )

    def test_bundle_urls_preserve_collection_selection(self) -> None:
        self.assertEqual(
            build_definition_source_url(
                "bundle",
                "bundle_python",
                web_base_url="http://localhost:3000",
                collection_id="default",
            ),
            "http://localhost:3000/collection?collection=default",
        )

    def test_missing_web_base_url_disables_links(self) -> None:
        self.assertEqual(
            build_definition_source_url(
                "workflow",
                "phase-execution",
                web_base_url="",
            ),
            "",
        )


if __name__ == "__main__":
    unittest.main()
