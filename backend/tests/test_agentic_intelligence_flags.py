import types
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from backend.services import agentic_intelligence_flags


class AgenticIntelligenceFlagsTests(unittest.TestCase):
    def test_project_flags_default_to_enabled(self) -> None:
        project = types.SimpleNamespace(skillMeat=types.SimpleNamespace(featureFlags=None))

        self.assertTrue(agentic_intelligence_flags.stack_recommendations_enabled(project))
        self.assertTrue(agentic_intelligence_flags.workflow_analytics_enabled(project))

    def test_project_flags_respect_overrides(self) -> None:
        project = types.SimpleNamespace(
            skillMeat=types.SimpleNamespace(
                featureFlags={
                    "stackRecommendationsEnabled": False,
                    "workflowAnalyticsEnabled": False,
                }
            )
        )

        self.assertFalse(agentic_intelligence_flags.stack_recommendations_enabled(project))
        self.assertFalse(agentic_intelligence_flags.workflow_analytics_enabled(project))

    def test_require_skillmeat_integration_enabled_raises_when_env_disabled(self) -> None:
        with patch.object(agentic_intelligence_flags.config, "CCDASH_SKILLMEAT_INTEGRATION_ENABLED", False):
            with self.assertRaises(HTTPException) as ctx:
                agentic_intelligence_flags.require_skillmeat_integration_enabled()

        self.assertEqual(ctx.exception.status_code, 503)

    def test_workflow_analytics_respects_global_flag(self) -> None:
        project = types.SimpleNamespace(skillMeat=types.SimpleNamespace(featureFlags={}))

        with patch.object(agentic_intelligence_flags.config, "CCDASH_AGENTIC_WORKFLOW_ANALYTICS_ENABLED", False):
            self.assertFalse(agentic_intelligence_flags.workflow_analytics_enabled(project))
