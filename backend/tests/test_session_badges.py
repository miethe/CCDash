import unittest

from backend.session_badges import derive_session_badges


class SessionBadgesTests(unittest.TestCase):
    def test_derives_models_agents_skills_and_tools(self) -> None:
        logs = [
            {
                "type": "message",
                "agent_name": "Planner",
                "metadata_json": '{"model":"claude-3-7-sonnet-20260201"}',
            },
            {
                "type": "command",
                "content": "/model",
                "metadata_json": '{"args":"gpt-5"}',
            },
            {
                "type": "tool",
                "tool_name": "Skill",
                "tool_args": '{"skill":"frontend-design"}',
                "metadata_json": "{}",
            },
            {
                "type": "tool",
                "tool_name": "Bash",
                "metadata_json": '{"subagentAgentId":"worker-1"}',
            },
            {
                "type": "tool",
                "tool_name": "Bash",
                "metadata_json": "{}",
            },
        ]

        badges = derive_session_badges(
            logs,
            primary_model="claude-opus-4-5-20251101",
            session_agent_id="root-agent",
        )

        model_raws = [entry["raw"] for entry in badges["modelsUsed"]]
        self.assertEqual(
            model_raws,
            ["claude-opus-4-5-20251101", "claude-3-7-sonnet-20260201", "gpt-5"],
        )
        self.assertEqual(badges["agentsUsed"], ["root-agent", "Planner", "worker-1"])
        self.assertEqual(badges["skillsUsed"], ["frontend-design"])
        self.assertEqual(badges["toolSummary"], ["Bash x2", "Skill x1"])

    def test_ignores_model_command_stopwords(self) -> None:
        logs = [
            {
                "type": "command",
                "content": "/model",
                "metadata_json": '{"args":"set to default"}',
            }
        ]

        badges = derive_session_badges(logs, primary_model="")
        self.assertEqual(badges["modelsUsed"], [])


if __name__ == "__main__":
    unittest.main()
