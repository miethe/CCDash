"""Tests for PCP-203: planning live-update topics and publisher fan-out.

Covers:
- Topic helper format (exact strings).
- topic_authorization returns planning-scoped resource.
- publish_planning_invalidation fan-out: project, feature, and phase topics.
- Phase-level granularity is absent when phase_number is not provided.
- Fan-out from publish_feature_invalidation is NOT affected (planning is additive).
"""
from __future__ import annotations

import unittest

from backend.application.live_updates import set_live_event_publisher
from backend.application.live_updates.domain_events import (
    publish_feature_invalidation,
    publish_planning_invalidation,
)
from backend.application.live_updates.topics import (
    feature_phase_topic,
    feature_planning_topic,
    project_planning_topic,
    topic_authorization,
)


class _RecordingPublisher:
    """Minimal stub that captures publish_invalidation calls."""

    def __init__(self) -> None:
        self.invalidate_calls: list[dict] = []

    async def publish_invalidation(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self.invalidate_calls.append(kwargs)

    async def publish_append(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        pass

    @property
    def topics(self) -> list[str]:
        return [c["topic"] for c in self.invalidate_calls]


# ── Topic helper format assertions ──────────────────────────────────────────


class TopicHelperFormatTests(unittest.TestCase):
    def test_project_planning_topic_format(self) -> None:
        self.assertEqual(project_planning_topic("proj-1"), "project.proj-1.planning")

    def test_feature_planning_topic_format(self) -> None:
        self.assertEqual(feature_planning_topic("feat-abc"), "feature.feat-abc.planning")

    def test_feature_phase_topic_integer_phase(self) -> None:
        self.assertEqual(feature_phase_topic("feat-abc", 2), "feature.feat-abc.phase.2")

    def test_feature_phase_topic_string_phase(self) -> None:
        # phase_id from the router is a string slug (e.g. "phase-2")
        self.assertEqual(feature_phase_topic("feat-abc", "phase-2"), "feature.feat-abc.phase.phase-2")

    def test_project_planning_topic_normalises_case(self) -> None:
        # join_topic lower-cases; verify robustness
        self.assertEqual(project_planning_topic("PROJ-1"), "project.proj-1.planning")


# ── Authorization resource assertions ───────────────────────────────────────


class TopicAuthorizationTests(unittest.TestCase):
    def test_project_planning_topic_authorization_resource(self) -> None:
        auth = topic_authorization("project.proj-1.planning", project_id="proj-1")
        # resource is first two segments — matches existing pattern
        self.assertEqual(auth.resource, "project.proj-1")
        self.assertEqual(auth.topic, "project.proj-1.planning")
        self.assertEqual(auth.project_id, "proj-1")

    def test_feature_planning_topic_authorization_resource(self) -> None:
        auth = topic_authorization("feature.feat-abc.planning", project_id=None)
        self.assertEqual(auth.resource, "feature.feat-abc")
        self.assertEqual(auth.topic, "feature.feat-abc.planning")

    def test_feature_phase_topic_authorization_resource(self) -> None:
        auth = topic_authorization("feature.feat-abc.phase.2", project_id=None)
        # resource is still the first two segments
        self.assertEqual(auth.resource, "feature.feat-abc")
        self.assertEqual(auth.topic, "feature.feat-abc.phase.2")

    def test_authorization_action_is_subscribe(self) -> None:
        auth = topic_authorization("project.proj-1.planning", project_id="proj-1")
        self.assertEqual(auth.action, "live_updates:subscribe")


# ── Publisher fan-out assertions ─────────────────────────────────────────────


class PlanningPublisherFanOutTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.publisher = _RecordingPublisher()
        set_live_event_publisher(self.publisher)

    async def asyncTearDown(self) -> None:
        set_live_event_publisher(None)

    async def test_project_only_emits_project_planning_topic(self) -> None:
        await publish_planning_invalidation(
            "proj-1",
            reason="sync_project_completed",
            source="sync_engine",
        )

        self.assertEqual(self.publisher.topics, ["project.proj-1.planning"])

    async def test_feature_and_project_emits_both_planning_topics(self) -> None:
        await publish_planning_invalidation(
            "proj-1",
            feature_id="feat-abc",
            reason="feature_status_updated",
            source="features_api",
        )

        self.assertIn("project.proj-1.planning", self.publisher.topics)
        self.assertIn("feature.feat-abc.planning", self.publisher.topics)
        # No phase topic when phase_number is absent
        self.assertFalse(
            any("phase" in t for t in self.publisher.topics),
            "phase topic must not be emitted without phase_number",
        )

    async def test_phase_number_emits_three_planning_topics(self) -> None:
        await publish_planning_invalidation(
            "proj-1",
            feature_id="feat-abc",
            phase_number=2,
            reason="feature_phase_status_updated",
            source="features_api",
        )

        expected = {
            "project.proj-1.planning",
            "feature.feat-abc.planning",
            "feature.feat-abc.phase.2",
        }
        self.assertEqual(set(self.publisher.topics), expected)

    async def test_phase_topic_payload_includes_phase_number(self) -> None:
        await publish_planning_invalidation(
            "proj-1",
            feature_id="feat-abc",
            phase_number="phase-2",
            reason="feature_phase_status_updated",
            source="features_api",
            payload={"status": "completed"},
        )

        phase_call = next(c for c in self.publisher.invalidate_calls if "phase" in c["topic"])
        self.assertEqual(phase_call["payload"]["phaseNumber"], "phase-2")
        self.assertEqual(phase_call["payload"]["status"], "completed")
        self.assertEqual(phase_call["payload"]["resource"], "planning")

    async def test_empty_project_id_emits_nothing(self) -> None:
        await publish_planning_invalidation(
            "",
            reason="noop",
            source="test",
        )
        self.assertEqual(self.publisher.invalidate_calls, [])

    async def test_planning_fan_out_is_additive_to_feature_invalidation(self) -> None:
        """publish_feature_invalidation should still emit its own topics unchanged."""
        await publish_feature_invalidation(
            "proj-1",
            feature_id="feat-abc",
            reason="feature_status_updated",
            source="features_api",
        )
        feature_topics = set(self.publisher.topics)
        self.assertIn("feature.feat-abc", feature_topics)
        self.assertIn("project.proj-1.features", feature_topics)
        # Planning topics are NOT emitted by publish_feature_invalidation itself
        self.assertNotIn("project.proj-1.planning", feature_topics)
        self.assertNotIn("feature.feat-abc.planning", feature_topics)

    async def test_planning_payload_contains_required_fields(self) -> None:
        await publish_planning_invalidation(
            "proj-1",
            feature_id="feat-abc",
            reason="test_reason",
            source="test_source",
            payload={"extra": "value"},
        )

        for call in self.publisher.invalidate_calls:
            p = call["payload"]
            self.assertEqual(p["resource"], "planning")
            self.assertEqual(p["projectId"], "proj-1")
            self.assertEqual(p["featureId"], "feat-abc")
            self.assertEqual(p["reason"], "test_reason")
            self.assertEqual(p["source"], "test_source")
            self.assertEqual(p["extra"], "value")
