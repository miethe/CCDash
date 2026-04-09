import json
import unittest

from backend.services.session_scope_drift import build_session_scope_drift_facts


class SessionScopeDriftFactsTests(unittest.TestCase):
    def test_in_scope_edits_are_classified_as_matched(self) -> None:
        session = {
            "id": "session-1",
            "featureId": "feature-scope",
            "rootSessionId": "root-1",
            "threadSessionId": "thread-1",
        }
        docs = [
            {
                "id": "DOC-PLAN",
                "frontmatter_json": json.dumps(
                    {
                        "context_files": [
                            "backend/services",
                            "docs/project_plans/implementation_plans/enhancements/session-intelligence-canonical-storage-v1.md",
                        ],
                        "relatedRefs": ["docs/project_plans/specs/shared-contract.md"],
                    }
                ),
            }
        ]
        file_updates = [
            {"file_path": "backend/services/session_scope_drift.py"},
            {
                "file_path": "/Users/test/work/CCDash/docs/project_plans/implementation_plans/enhancements/session-intelligence-canonical-storage-v1.md"
            },
        ]

        facts = build_session_scope_drift_facts(session, docs, file_updates)

        self.assertEqual(len(facts), 1)
        fact = facts[0]
        self.assertEqual(fact["session_id"], "session-1")
        self.assertEqual(fact["feature_id"], "feature-scope")
        self.assertEqual(fact["root_session_id"], "root-1")
        self.assertEqual(fact["thread_session_id"], "thread-1")
        self.assertEqual(fact["actual_path_count"], 2)
        self.assertEqual(fact["matched_path_count"], 2)
        self.assertEqual(fact["out_of_scope_path_count"], 0)
        self.assertEqual(fact["drift_ratio"], 0.0)
        self.assertEqual(fact["adherence_score"], 1.0)
        self.assertEqual(fact["heuristic_version"], "scope_drift_v1")
        self.assertEqual(fact["evidence_json"]["matchingMode"], "prefix-aware")

    def test_out_of_scope_edits_are_flagged(self) -> None:
        session = {"id": "session-2", "featureId": "feature-scope"}
        docs = [
            {
                "id": "DOC-PLAN",
                "frontmatter": {"context_files": ["backend/services"]},
            }
        ]
        file_updates = [{"file_path": "components/SessionInspector.tsx"}]

        facts = build_session_scope_drift_facts(session, docs, file_updates)

        fact = facts[0]
        self.assertEqual(fact["planned_path_count"], 1)
        self.assertEqual(fact["actual_path_count"], 1)
        self.assertEqual(fact["matched_path_count"], 0)
        self.assertEqual(fact["out_of_scope_path_count"], 1)
        self.assertEqual(fact["drift_ratio"], 1.0)
        self.assertEqual(fact["adherence_score"], 0.0)
        self.assertIn("components/SessionInspector.tsx", fact["evidence_json"]["outOfScopePaths"])

    def test_mixed_prefix_and_exact_file_matching(self) -> None:
        session = {
            "id": "session-3",
            "taskId": "feature-from-task",
            "root_session_id": "root-3",
            "thread_session_id": "thread-3",
        }
        docs = [
            {
                "id": "DOC-PRD",
                "frontmatter_json": json.dumps(
                    {
                        "pathRefs": ["backend/services"],
                        "prd": "docs/project_plans/PRDs/enhancements/session-intelligence-canonical-storage-v1.md",
                    }
                ),
            }
        ]
        file_updates = [
            {"file_path": "backend/services/session_scope_drift.py"},
            {
                "file_path": "/Users/me/dev/homelab/development/CCDash/docs/project_plans/PRDs/enhancements/session-intelligence-canonical-storage-v1.md"
            },
            {"file_path": "backend/db/sync_engine.py"},
        ]

        facts = build_session_scope_drift_facts(session, docs, file_updates)

        fact = facts[0]
        self.assertEqual(fact["feature_id"], "feature-from-task")
        self.assertEqual(fact["planned_path_count"], 2)
        self.assertEqual(fact["actual_path_count"], 3)
        self.assertEqual(fact["matched_path_count"], 2)
        self.assertEqual(fact["out_of_scope_path_count"], 1)
        self.assertEqual(fact["drift_ratio"], 0.3333)
        self.assertEqual(fact["adherence_score"], 0.6667)
        self.assertIn("backend/services/session_scope_drift.py", fact["evidence_json"]["matchedPaths"])
        self.assertIn("backend/db/sync_engine.py", fact["evidence_json"]["outOfScopePaths"])

    def test_missing_plan_behavior_uses_actual_paths_as_out_of_scope(self) -> None:
        session = {"id": "session-4", "featureId": "feature-plan-missing"}
        docs: list[dict[str, object]] = []
        file_updates = [{"file_path": "backend/services/session_scope_drift.py"}]

        facts = build_session_scope_drift_facts(session, docs, file_updates)

        fact = facts[0]
        self.assertEqual(fact["planned_path_count"], 0)
        self.assertEqual(fact["actual_path_count"], 1)
        self.assertEqual(fact["matched_path_count"], 0)
        self.assertEqual(fact["out_of_scope_path_count"], 1)
        self.assertEqual(fact["drift_ratio"], 1.0)
        self.assertEqual(fact["adherence_score"], 0.0)
        self.assertEqual(fact["confidence"], 0.45)
        self.assertEqual(fact["evidence_json"]["plannedPaths"], [])

    def test_sparse_evidence_behavior_remains_deterministic(self) -> None:
        session = {"id": "session-5", "featureId": "feature-sparse"}
        docs = [
            {
                "id": "DOC-SPARSE",
                "frontmatter": {
                    "relatedRefs": ["feature-scope-v1"],
                    "plan_ref": "",
                },
            }
        ]
        file_updates: list[dict[str, object]] = []

        facts_first = build_session_scope_drift_facts(session, docs, file_updates)
        facts_second = build_session_scope_drift_facts(session, docs, file_updates)

        self.assertEqual(facts_first, facts_second)
        fact = facts_first[0]
        self.assertEqual(fact["planned_path_count"], 0)
        self.assertEqual(fact["actual_path_count"], 0)
        self.assertEqual(fact["matched_path_count"], 0)
        self.assertEqual(fact["out_of_scope_path_count"], 0)
        self.assertEqual(fact["drift_ratio"], 0.0)
        self.assertEqual(fact["adherence_score"], 1.0)
        self.assertEqual(fact["confidence"], 0.35)


if __name__ == "__main__":
    unittest.main()
