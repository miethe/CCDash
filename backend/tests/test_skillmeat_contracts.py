import unittest

from backend.services.integrations.skillmeat_contracts import (
    attach_workflow_detail,
    extract_workflow_swdl_summary,
    summarize_workflow_plan,
)


class SkillMeatContractsTests(unittest.TestCase):
    def test_extract_workflow_swdl_summary_collects_artifacts_contexts_and_stage_graph(self) -> None:
        summary = extract_workflow_swdl_summary(
            {
                "definition": (
                    "name: Feature Pipeline\n"
                    "stages:\n"
                    "  - id: planning\n"
                    "    type: agent\n"
                    "    agent: agent:planner\n"
                    "  - id: implementation\n"
                    "    type: fan_out\n"
                    "    depends_on: [planning]\n"
                    "    stages:\n"
                    "      - id: backend\n"
                    "        type: agent\n"
                    "        agent: skill:symbols\n"
                    "      - id: context\n"
                    "        type: agent\n"
                    "        memory: ctx:planning\n"
                )
            }
        )

        self.assertIn("agent:planner", summary.artifactRefs)
        self.assertIn("skill:symbols", summary.artifactRefs)
        self.assertIn("ctx:planning", summary.contextRefs)
        self.assertEqual(summary.fanOutCount, 1)
        self.assertEqual(summary.stageOrder[:2], ["planning", "implementation"])

    def test_summarize_workflow_plan_tracks_batches_dependencies_and_gates(self) -> None:
        summary = summarize_workflow_plan(
            {
                "estimated_batches": 3,
                "estimated_stages": 4,
                "has_gates": True,
                "validation_errors": [],
                "execution_order": [
                    {"batch_index": 0, "stages": [{"stage_id": "planning", "stage_type": "agent", "depends_on": []}]},
                    {"batch_index": 1, "stages": [{"stage_id": "backend", "stage_type": "agent", "depends_on": ["planning"]}]},
                    {"batch_index": 2, "stages": [{"stage_id": "approval", "stage_type": "gate", "depends_on": ["backend"]}]},
                ],
            }
        )

        self.assertEqual(summary.batchCount, 3)
        self.assertEqual(summary.stageCount, 4)
        self.assertTrue(summary.hasGates)
        self.assertEqual(summary.stageOrder, ["planning", "backend", "approval"])
        self.assertEqual(summary.stageDependencies[-1]["stageType"], "gate")

    def test_attach_workflow_detail_keeps_raw_and_effective_metadata_distinct(self) -> None:
        definition = {
            "external_id": "wf_project",
            "display_name": "Phase Execution",
            "resolution_metadata": {
                "workflowScope": "project",
                "effectiveWorkflowKey": "phase-execution",
                "effectiveWorkflowId": "wf_project",
                "effectiveWorkflowName": "Phase Execution",
                "isEffective": True,
            },
            "raw_snapshot": {"id": "wf_project"},
        }

        enriched = attach_workflow_detail(
            definition,
            workflow_detail={
                "id": "wf_project",
                "name": "Phase Execution",
                "project_id": "sm-project",
                "definition": "name: Phase Execution\nstages:\n  - id: planning\n    type: agent\n    agent: agent:planner\n",
            },
            workflow_plan={
                "estimated_batches": 1,
                "estimated_stages": 1,
                "has_gates": False,
                "execution_order": [{"batch_index": 0, "stages": [{"stage_id": "planning", "stage_type": "agent", "depends_on": []}]}],
            },
        )

        self.assertEqual(enriched["resolution_metadata"]["rawWorkflow"]["id"], "wf_project")
        self.assertEqual(enriched["resolution_metadata"]["effectiveWorkflow"]["id"], "wf_project")
        self.assertEqual(enriched["resolution_metadata"]["planSummary"]["batchCount"], 1)
        self.assertIn("agent:planner", enriched["resolution_metadata"]["swdlSummary"]["artifactRefs"])


if __name__ == "__main__":
    unittest.main()
