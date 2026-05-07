import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import aiosqlite

from backend.config import TelemetryExporterConfig
from backend.db.repositories.sessions import SqliteSessionRepository
from backend.db.repositories.telemetry_queue import SqliteTelemetryQueueRepository
from backend.db.sqlite_migrations import run_migrations
from backend.models import ArtifactOutcomePayload, ArtifactUsageRollup
from backend.services.integrations.skillmeat_client import SkillMeatClientError
from backend.services.integrations.telemetry_exporter import TelemetryExportCoordinator
from backend.services.integrations.telemetry_settings_store import TelemetrySettingsStore
from backend.services.telemetry_transformer import PrivacyViolationError


def _rollup() -> ArtifactUsageRollup:
    return ArtifactUsageRollup.model_validate(
        {
            "schemaVersion": "ccdash-artifact-usage-rollup-v1",
            "projectSlug": "project-1",
            "skillmeatProjectId": "sm-project",
            "collectionId": "default",
            "period": "30d",
            "artifact": {"definitionType": "skill", "externalId": "skill:frontend-design", "artifactUuid": "uuid-1"},
            "usage": {"exclusiveTokens": 10, "supportingTokens": 5, "sessionCount": 1},
        }
    )


class _Builder:
    def __init__(self, rollups):
        self.rollups = rollups
        self.calls = []

    async def build_rollups(self, db, **kwargs):  # noqa: ANN001
        self.calls.append((db, kwargs))
        return self.rollups


class _SkillMeatClient:
    def __init__(self, *, error: Exception | None = None):
        self.error = error
        self.calls = []

    async def post_artifact_usage_rollup(self, rollup):
        self.calls.append(rollup)
        if self.error is not None:
            raise self.error
        return {"accepted": True}


class _ArtifactOutcomeClient:
    def __init__(self):
        self.artifact_calls = []

    async def push_batch(self, events):  # noqa: ANN001
        return True, None

    async def push_artifact_batch(self, events, sam_base_url):  # noqa: ANN001
        self.artifact_calls.append((events, sam_base_url))
        return True, None

    async def push_artifact_version_batch(self, events, sam_base_url):  # noqa: ANN001
        return True, None


class ArtifactRollupExporterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.queue = SqliteTelemetryQueueRepository(self.db)
        self.settings = TelemetrySettingsStore(Path(self.tmp.name) / "integrations.json")
        self.settings.save(type("Req", (), {"enabled": True})())
        self.runtime_config = TelemetryExporterConfig(
            enabled=True,
            sam_endpoint="https://sam.example/api/v1/analytics/execution-outcomes",
            sam_api_key="secret",
            timeout_seconds=30,
            interval_seconds=60,
            artifact_telemetry_enabled=True,
        )

    async def asyncTearDown(self) -> None:
        await self.db.close()
        self.tmp.cleanup()

    def _coordinator(self, builder) -> TelemetryExportCoordinator:  # noqa: ANN001
        return TelemetryExportCoordinator(
            repository=self.queue,
            settings_store=self.settings,
            runtime_config=self.runtime_config,
            db=self.db,
            rollup_payload_builder=builder,
        )

    async def test_export_artifact_usage_rollups_verifies_and_posts_each_payload(self) -> None:
        builder = _Builder([_rollup()])
        coordinator = self._coordinator(builder)
        client = _SkillMeatClient()

        with patch("backend.services.integrations.telemetry_exporter.config.CCDASH_ARTIFACT_INTELLIGENCE_ENABLED", True):
            outcome = await coordinator.export_artifact_usage_rollups(
                project_id="project-1",
                period="30d",
                skillmeat_project_id="sm-project",
                collection_id="default",
                skillmeat_client=client,
            )

        self.assertTrue(outcome.success)
        self.assertEqual(outcome.success_count, 1)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(builder.calls[0][1]["skillmeat_project_id"], "sm-project")

    async def test_export_skips_privacy_failures_without_posting(self) -> None:
        builder = _Builder([_rollup()])
        coordinator = self._coordinator(builder)
        client = _SkillMeatClient()

        with (
            patch("backend.services.integrations.telemetry_exporter.config.CCDASH_ARTIFACT_INTELLIGENCE_ENABLED", True),
            patch(
                "backend.services.integrations.telemetry_exporter.AnonymizationVerifier.verify_rollup_payload",
                side_effect=PrivacyViolationError("privacy"),
            ),
        ):
            outcome = await coordinator.export_artifact_usage_rollups(
                project_id="project-1",
                period="30d",
                skillmeat_client=client,
            )

        self.assertTrue(outcome.success)
        self.assertEqual(outcome.skipped_count, 1)
        self.assertEqual(client.calls, [])
    async def test_export_handles_skillmeat_network_failures_without_crashing(self) -> None:
        builder = _Builder([_rollup()])
        coordinator = self._coordinator(builder)
        client = _SkillMeatClient(error=SkillMeatClientError("unavailable", detail="connection refused"))

        with patch("backend.services.integrations.telemetry_exporter.config.CCDASH_ARTIFACT_INTELLIGENCE_ENABLED", True):
            outcome = await coordinator.export_artifact_usage_rollups(
                project_id="project-1",
                period="30d",
                skillmeat_client=client,
            )

        self.assertFalse(outcome.success)
        self.assertEqual(outcome.failed_count, 1)
        self.assertEqual(outcome.error, "connection refused")

    async def test_export_job_skips_when_feature_flag_disabled(self) -> None:
        builder = _Builder([_rollup()])
        coordinator = self._coordinator(builder)
        client = _SkillMeatClient()

        with patch("backend.services.integrations.telemetry_exporter.config.CCDASH_ARTIFACT_INTELLIGENCE_ENABLED", False):
            outcome = await coordinator.export_artifact_usage_rollups(
                project_id="project-1",
                period="30d",
                skillmeat_client=client,
            )

        self.assertTrue(outcome.success)
        self.assertEqual(outcome.outcome, "disabled")
        self.assertEqual(builder.calls, [])
        self.assertEqual(client.calls, [])

    async def test_existing_artifact_outcome_export_still_marks_rows_synced(self) -> None:
        session_repo = SqliteSessionRepository(self.db)
        await session_repo.upsert(
            {
                "id": "session-1",
                "taskId": "",
                "status": "completed",
                "model": "claude-sonnet-4-5-20260101",
                "platformType": "Claude Code",
                "durationSeconds": 60,
                "tokensIn": 100,
                "tokensOut": 50,
                "totalCost": 0.0,
                "startedAt": "2026-05-07T12:00:00Z",
                "endedAt": "2026-05-07T12:01:00Z",
                "sourceFile": "/tmp/session-1.jsonl",
            },
            "project-1",
        )
        payload = ArtifactOutcomePayload(
            event_id="5b56afba-9ccb-4d2b-b334-f921d4460209",
            definition_type="skill",
            external_id="skill:frontend-design",
            period_label="30d",
            period_start=datetime(2026, 4, 7, tzinfo=timezone.utc),
            period_end=datetime(2026, 5, 7, tzinfo=timezone.utc),
            execution_count=1,
            success_count=1,
            failure_count=0,
            token_input=10,
            token_output=5,
            cost_usd=0.01,
            duration_ms=1000,
            timestamp=datetime(2026, 5, 7, tzinfo=timezone.utc),
        )
        await self.queue.enqueue(
            "session-1",
            "project-1",
            payload.event_dict(),
            queue_id=str(payload.event_id),
            event_type="artifact_outcome",
        )
        coordinator = self._coordinator(_Builder([]))
        client = _ArtifactOutcomeClient()
        coordinator._client = client

        outcome = await coordinator.execute(trigger="manual", raise_on_busy=True)
        stats = await self.queue.get_queue_stats()

        self.assertTrue(outcome.success)
        self.assertEqual(stats["synced"], 1)
        self.assertEqual(len(client.artifact_calls), 1)


class ArtifactRollupJobWiringTests(unittest.IsolatedAsyncioTestCase):
    async def test_runtime_scheduler_registers_artifact_rollup_export_task(self) -> None:
        from backend.adapters.jobs.artifact_rollup_export_job import ArtifactRollupExportJob
        from backend.adapters.jobs.runtime import RuntimeJobAdapter
        from backend.runtime.profiles import get_runtime_profile

        class _Scheduler:
            def __init__(self):
                self.calls = []

            def schedule(self, job, *, name=None):  # noqa: ANN001
                self.calls.append((job, name))
                job.close()
                return SimpleNamespace(done=lambda: False)

        scheduler = _Scheduler()
        ports = SimpleNamespace(job_scheduler=scheduler, workspace_registry=SimpleNamespace())
        adapter = RuntimeJobAdapter(
            profile=get_runtime_profile("worker"),
            ports=ports,
            sync_engine=None,
            artifact_rollup_export_job=ArtifactRollupExportJob(
                SimpleNamespace(export_artifact_usage_rollups=AsyncMock()),
                project=SimpleNamespace(id="project-1", skillMeat=SimpleNamespace(baseUrl="http://skillmeat.local")),
            ),
        )

        with patch("backend.adapters.jobs.runtime.config.CCDASH_ARTIFACT_ROLLUP_EXPORT_INTERVAL_SECONDS", 3600):
            task = adapter._start_artifact_rollup_export_task()  # noqa: SLF001

        self.assertIsNotNone(task)
        self.assertEqual(adapter.state.job_observations["artifactRollupExports"].interval_seconds, 3600)
        self.assertEqual(scheduler.calls[0][1], "ccdash:worker:artifact-rollup-export")


if __name__ == "__main__":
    unittest.main()
