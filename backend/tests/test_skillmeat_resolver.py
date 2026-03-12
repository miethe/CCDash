import unittest

from backend.services.integrations.skillmeat_resolver import resolve_stack_components


class SkillMeatResolverTests(unittest.TestCase):
    def test_resolve_stack_components_prefers_effective_project_workflow_alias(self) -> None:
        definitions = [
            {
                "id": 1,
                "definition_type": "workflow",
                "external_id": "wf_global",
                "display_name": "Phase Execution",
                "resolution_metadata_json": {
                    "aliases": ["phase-execution", "Phase Execution"],
                    "workflowScope": "global",
                    "isEffective": False,
                },
            },
            {
                "id": 2,
                "definition_type": "workflow",
                "external_id": "wf_project",
                "display_name": "Phase Execution",
                "resolution_metadata_json": {
                    "aliases": ["phase-execution", "Phase Execution"],
                    "workflowScope": "project",
                    "isEffective": True,
                },
            },
        ]
        components = [
            {
                "component_type": "workflow",
                "component_key": "phase-execution",
                "status": "inferred",
                "confidence": 0.7,
                "payload": {"workflowRef": "phase-execution"},
            }
        ]

        resolved = resolve_stack_components(components=components, definitions=definitions)

        self.assertEqual(resolved[0]["status"], "resolved")
        self.assertEqual(resolved[0]["external_definition_id"], 2)
        self.assertEqual(resolved[0]["external_definition_external_id"], "wf_project")
        self.assertEqual(resolved[0]["source_attribution"], "alias_exact")


if __name__ == "__main__":
    unittest.main()
