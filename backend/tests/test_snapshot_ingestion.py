import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import aiosqlite

from backend.db.repositories.artifact_snapshot_repository import SqliteArtifactSnapshotRepository
from backend.db.sqlite_migrations import run_migrations
from backend.models import SKILLMEAT_ARTIFACT_SNAPSHOT_SCHEMA_VERSION
from backend.services.identity_resolver import ArtifactIdentityMapper
from backend.services.integrations.skillmeat_client import SkillMeatClient


def _artifact(
    name: str,
    *,
    artifact_uuid: str,
    content_hash_suffix: str,
    tags: list[str] | None = None,
    status: str = "active",
) -> dict[str, object]:
    return {
        "definitionType": "skill",
        "externalId": f"skill:{name}",
        "artifactUuid": artifact_uuid,
        "displayName": name,
        "versionId": f"version-{name}",
        "contentHash": f"sha256:{content_hash_suffix * 64}",
        "collectionIds": ["collection-a"],
        "deploymentProfileIds": ["claude-code"],
        "defaultLoadMode": "disabled" if status == "disabled" else "workflow_scoped",
        "workflowRefs": ["workflow-1"],
        "tags": tags or [name],
        "status": status,
    }


def _snapshot_payload() -> dict[str, object]:
    return {
        "schemaVersion": SKILLMEAT_ARTIFACT_SNAPSHOT_SCHEMA_VERSION,
        "generatedAt": "2026-05-07T10:00:00Z",
        "projectId": "project-1",
        "collectionId": "collection-a",
        "artifacts": [
            _artifact("code-review", artifact_uuid="uuid-code-review", content_hash_suffix="a"),
            _artifact("test-runner", artifact_uuid="uuid-test-runner", content_hash_suffix="b"),
            _artifact("planning", artifact_uuid="uuid-planning", content_hash_suffix="c"),
            _artifact(
                "frontend-design-skill",
                artifact_uuid="uuid-frontend-design",
                content_hash_suffix="d",
                tags=["frontend-design"],
            ),
            _artifact(
                "legacy-auditor-skill",
                artifact_uuid="uuid-legacy-auditor",
                content_hash_suffix="e",
                tags=["legacy-auditor"],
                status="disabled",
            ),
            _artifact("release-notes-skill", artifact_uuid="uuid-release-notes", content_hash_suffix="f"),
            _artifact("security-review-skill", artifact_uuid="uuid-security-review", content_hash_suffix="0"),
        ],
        "freshness": {
            "snapshotSource": "skillmeat",
            "sourceGeneratedAt": "2026-05-07T10:00:00Z",
            "fetchedAt": "2026-05-07T10:01:00Z",
            "warnings": [],
        },
    }


def _observed_usage_fixture() -> list[dict[str, str | None]]:
    return [
        {
            "observed_name": "ccdash-code-review",
            "ccdash_type": "skill",
            "observed_uuid": "uuid-code-review",
            "content_hash": None,
        },
        {
            "observed_name": "local-test-runner",
            "ccdash_type": "skill",
            "observed_uuid": "uuid-test-runner",
            "content_hash": None,
        },
        {
            "observed_name": "planning",
            "ccdash_type": "skill",
            "observed_uuid": "uuid-planning",
            "content_hash": None,
        },
        {
            "observed_name": "frontend-design",
            "ccdash_type": "skill",
            "observed_uuid": None,
            "content_hash": None,
        },
        {
            "observed_name": "legacy-auditor",
            "ccdash_type": "skill",
            "observed_uuid": None,
            "content_hash": None,
        },
        {
            "observed_name": "zzzzzzzz",
            "ccdash_type": "skill",
            "observed_uuid": None,
            "content_hash": None,
        },
        {
            "observed_name": "untracked-context-loader",
            "ccdash_type": "skill",
            "observed_uuid": None,
            "content_hash": None,
        },
    ]


class SnapshotIngestionIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.repo = SqliteArtifactSnapshotRepository(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_fetch_store_resolve_and_query_snapshot_diagnostics(self) -> None:
        client = SkillMeatClient(base_url="http://skillmeat.local", timeout_seconds=2.0)
        mapper = ArtifactIdentityMapper(self.repo, fuzzy_threshold=0.85)
        observed_usage = _observed_usage_fixture()

        with (
            patch(
                "backend.services.integrations.skillmeat_client.agentic_intelligence_flags.artifact_intelligence_enabled",
                return_value=True,
            ),
            patch.object(SkillMeatClient, "_request_json", return_value=_snapshot_payload()) as request_mock,
        ):
            snapshot = await client.fetch_project_artifact_snapshot("project-1", "collection-a")

        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(len(snapshot.artifacts), 7)
        self.assertEqual(len(observed_usage), 7)
        request_mock.assert_called_once_with(
            "/api/v1/projects/project-1/artifact-snapshot",
            {"collection_id": "collection-a"},
        )

        await self.repo.save_snapshot(snapshot)
        latest = await self.repo.get_latest_snapshot("project-1")

        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertEqual(latest.project_id, "project-1")
        self.assertEqual(latest.collection_id, "collection-a")
        self.assertEqual(len(latest.artifacts), 7)

        results = await mapper.resolve_many(
            project_id="project-1",
            observed_artifacts=observed_usage,
            snapshot_artifacts=latest.artifacts,
        )
        by_name = {result.ccdash_name: result for result in results}

        self.assertEqual(
            [result.match_tier for result in results].count("tier-1"),
            3,
        )
        self.assertEqual(
            [result.match_tier for result in results].count("tier-2"),
            2,
        )
        self.assertEqual(
            [result.match_tier for result in results].count("unresolved"),
            2,
        )
        self.assertEqual(by_name["frontend-design"].skillmeat_uuid, "uuid-frontend-design")
        self.assertEqual(by_name["legacy-auditor"].skillmeat_uuid, "uuid-legacy-auditor")
        self.assertEqual(by_name["legacy-auditor"].metadata["artifact_status"], "disabled")
        self.assertEqual(by_name["legacy-auditor"].metadata["ranking_status"], "disabled")
        self.assertTrue(by_name["zzzzzzzz"].metadata["identity_reconciliation"]["recommended"])  # type: ignore[index]
        self.assertTrue(by_name["untracked-context-loader"].metadata["identity_reconciliation"]["recommended"])  # type: ignore[index]

        mappings = await self.repo.list_identity_mappings("project-1")
        self.assertEqual(len(mappings), 7)
        self.assertEqual(await self.repo.get_unresolved_identity_count("project-1"), 2)

        freshness = await self.repo.get_snapshot_freshness("project-1")
        self.assertEqual(freshness.source_generated_at.isoformat(), "2026-05-07T10:00:00+00:00")
        self.assertEqual(freshness.fetched_at.isoformat(), "2026-05-07T10:01:00+00:00")

        with patch(
            "backend.db.repositories.artifact_snapshot_repository._utc_now",
            return_value=datetime(2026, 5, 7, 10, 31, tzinfo=timezone.utc),
        ), patch(
            "backend.db.repositories.artifact_snapshot_repository.config.CCDASH_SNAPSHOT_FRESHNESS_MAX_AGE_SECONDS",
            3600,
        ):
            diagnostics = await self.repo.get_snapshot_diagnostics("project-1")

        self.assertEqual(diagnostics.snapshot_age_seconds, 1800)
        self.assertEqual(diagnostics.artifact_count, 7)
        self.assertEqual(diagnostics.resolved_count, 5)
        self.assertEqual(diagnostics.unresolved_count, 2)
        self.assertFalse(diagnostics.is_stale)
