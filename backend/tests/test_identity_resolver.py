import unittest

import aiosqlite

from backend.db.repositories.artifact_snapshot_repository import SqliteArtifactSnapshotRepository
from backend.db.sqlite_migrations import run_migrations
from backend.models import SnapshotArtifact
from backend.services.identity_resolver import ArtifactIdentityMapper


def _artifact(
    name: str,
    *,
    artifact_uuid: str | None = None,
    content_hash: str | None = None,
    status: str = "active",
) -> SnapshotArtifact:
    slug = name.replace("_", "-")
    return SnapshotArtifact.model_validate(
        {
            "definitionType": "skill",
            "externalId": f"skill:{slug}",
            "artifactUuid": artifact_uuid or f"uuid-{slug}",
            "displayName": name,
            "versionId": f"version-{slug}",
            "contentHash": content_hash
            or "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "defaultLoadMode": "workflow_scoped",
            "status": status,
            "tags": [slug],
        }
    )


class ArtifactIdentityMapperTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.repo = SqliteArtifactSnapshotRepository(self.db)
        self.mapper = ArtifactIdentityMapper(self.repo, fuzzy_threshold=0.85)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_exact_uuid_match_resolves_as_tier_1_with_full_confidence(self) -> None:
        artifact = _artifact("frontend-design", artifact_uuid="skill-uuid-1")

        result = await self.mapper.resolve_identity(
            project_id="project-1",
            observed_name="frontend-design",
            ccdash_type="skill",
            observed_uuid="skill-uuid-1",
            snapshot_artifacts=[artifact],
        )

        self.assertEqual(result.match_tier, "tier-1")
        self.assertEqual(result.confidence, 1.0)
        self.assertEqual(result.skillmeat_uuid, "skill-uuid-1")
        self.assertFalse(result.metadata["identity_reconciliation"]["recommended"])  # type: ignore[index]

    async def test_exact_content_hash_match_resolves_as_tier_1_with_full_confidence(self) -> None:
        content_hash = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        artifact = _artifact("symbols", content_hash=content_hash)

        result = await self.mapper.resolve_identity(
            project_id="project-1",
            observed_name="renamed-symbols",
            ccdash_type="skill",
            content_hash=content_hash,
            snapshot_artifacts=[artifact],
        )

        self.assertEqual(result.match_tier, "tier-1")
        self.assertEqual(result.confidence, 1.0)
        self.assertEqual(result.content_hash, content_hash)

    async def test_alias_fuzzy_match_above_threshold_resolves_as_tier_2(self) -> None:
        artifact = _artifact("frontend-design-skill")

        result = await self.mapper.resolve_identity(
            project_id="project-1",
            observed_name="frontend-design",
            ccdash_type="skill",
            snapshot_artifacts=[artifact],
        )

        self.assertEqual(result.match_tier, "tier-2")
        self.assertGreaterEqual(result.confidence or 0.0, 0.85)
        self.assertEqual(result.metadata["matched_alias"], "frontend-design-skill")

    async def test_alias_fuzzy_match_below_threshold_is_quarantined(self) -> None:
        artifact = _artifact("frontend-design-skill")

        result = await self.mapper.resolve_identity(
            project_id="project-1",
            observed_name="frontend-data",
            ccdash_type="skill",
            snapshot_artifacts=[artifact],
        )

        self.assertEqual(result.match_tier, "unresolved")
        self.assertEqual(result.unresolved_reason, "below_threshold")
        self.assertTrue(result.metadata["identity_reconciliation"]["recommended"])  # type: ignore[index]
        mappings = await self.repo.list_identity_mappings("project-1")
        self.assertEqual(mappings[0]["match_tier"], "unresolved")
        self.assertEqual(mappings[0]["unresolved_reason"], "below_threshold")

    async def test_snapshot_artifact_without_ccdash_usage_is_not_quarantined(self) -> None:
        observed = _artifact("frontend-design")
        unused = _artifact("unused-skill")

        await self.mapper.resolve_identity(
            project_id="project-1",
            observed_name="frontend-design",
            ccdash_type="skill",
            snapshot_artifacts=[observed, unused],
        )

        mappings = await self.repo.list_identity_mappings("project-1")
        self.assertEqual(len(mappings), 1)
        self.assertEqual(await self.repo.get_unresolved_identity_count("project-1"), 0)

    async def test_observed_name_not_in_snapshot_is_quarantined_as_not_in_snapshot(self) -> None:
        result = await self.mapper.resolve_identity(
            project_id="project-1",
            observed_name="zzzzzzzz",
            ccdash_type="skill",
            snapshot_artifacts=[_artifact("frontend-design")],
        )

        self.assertEqual(result.match_tier, "unresolved")
        self.assertEqual(result.unresolved_reason, "not_in_snapshot")
        self.assertTrue(result.metadata["identity_reconciliation"]["recommended"])  # type: ignore[index]

    async def test_disabled_snapshot_artifact_is_mapped_and_flagged_for_ranking(self) -> None:
        artifact = _artifact("legacy-skill", status="disabled")

        result = await self.mapper.resolve_identity(
            project_id="project-1",
            observed_name="legacy-skill",
            ccdash_type="skill",
            snapshot_artifacts=[artifact],
        )

        self.assertEqual(result.match_tier, "tier-2")
        self.assertEqual(result.metadata["artifact_status"], "disabled")
        self.assertEqual(result.metadata["ranking_status"], "disabled")
