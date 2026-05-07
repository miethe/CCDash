import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import aiosqlite

from backend.db.factory import get_artifact_snapshot_repository
from backend.db.repositories.artifact_snapshot_repository import SqliteArtifactSnapshotRepository
from backend.db.repositories.postgres.artifact_snapshot_repository import PostgresArtifactSnapshotRepository
from backend.db.sqlite_migrations import run_migrations
from backend.models import SKILLMEAT_ARTIFACT_SNAPSHOT_SCHEMA_VERSION, SkillMeatArtifactSnapshot


def _snapshot_payload(
    *,
    project_id: str = "project-1",
    collection_id: str | None = "collection-a",
    generated_at: str = "2026-05-07T10:00:00Z",
    fetched_at: str = "2026-05-07T10:01:00Z",
    display_name: str = "frontend-design",
) -> dict:
    payload = {
        "schemaVersion": SKILLMEAT_ARTIFACT_SNAPSHOT_SCHEMA_VERSION,
        "generatedAt": generated_at,
        "projectId": project_id,
        "artifacts": [
            {
                "definitionType": "skill",
                "externalId": f"skill:{display_name}",
                "artifactUuid": f"uuid-{display_name}",
                "displayName": display_name,
                "versionId": "version-1",
                "contentHash": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "collectionIds": [collection_id] if collection_id else [],
                "deploymentProfileIds": ["profile-1"],
                "defaultLoadMode": "workflow_scoped",
                "workflowRefs": ["workflow-1"],
                "tags": ["frontend"],
                "status": "active",
            }
        ],
        "freshness": {
            "snapshotSource": "skillmeat",
            "sourceGeneratedAt": generated_at,
            "fetchedAt": fetched_at,
        },
    }
    if collection_id:
        payload["collectionId"] = collection_id
    return payload


def _snapshot(**kwargs) -> SkillMeatArtifactSnapshot:
    return SkillMeatArtifactSnapshot.model_validate(_snapshot_payload(**kwargs))


class ArtifactSnapshotRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.repo = SqliteArtifactSnapshotRepository(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_factory_returns_sqlite_artifact_snapshot_repository(self) -> None:
        repo = get_artifact_snapshot_repository(self.db)

        self.assertIsInstance(repo, SqliteArtifactSnapshotRepository)

    async def test_save_snapshot_stores_raw_json_and_latest_snapshot_uses_fetched_at(self) -> None:
        await self.repo.save_snapshot(
            _snapshot(
                generated_at="2026-05-07T09:00:00Z",
                fetched_at="2026-05-07T09:01:00Z",
                display_name="older-skill",
            )
        )
        await self.repo.save_snapshot(
            _snapshot(
                collection_id="collection-b",
                generated_at="2026-05-07T10:00:00Z",
                fetched_at="2026-05-07T10:01:00Z",
                display_name="newer-skill",
            )
        )

        latest = await self.repo.get_latest_snapshot("project-1")

        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertEqual(latest.project_id, "project-1")
        self.assertEqual(latest.collection_id, "collection-b")
        self.assertEqual(latest.artifacts[0].display_name, "newer-skill")
        self.assertEqual(latest.freshness.fetched_at.isoformat(), "2026-05-07T10:01:00+00:00")

        async with self.db.execute(
            """
            SELECT raw_json, artifact_count, collection_id
            FROM artifact_snapshot_cache
            WHERE project_id = ?
            ORDER BY fetched_at DESC
            LIMIT 1
            """,
            ("project-1",),
        ) as cur:
            row = await cur.fetchone()
        stored = json.loads(row["raw_json"])
        self.assertEqual(row["artifact_count"], 1)
        self.assertEqual(row["collection_id"], "collection-b")
        self.assertEqual(stored["projectId"], "project-1")
        self.assertEqual(stored["freshness"]["fetchedAt"], "2026-05-07T10:01:00Z")

    async def test_get_snapshot_freshness_returns_latest_generated_and_fetched_times(self) -> None:
        await self.repo.save_snapshot(
            _snapshot(
                generated_at="2026-05-07T08:00:00Z",
                fetched_at="2026-05-07T08:05:00Z",
            )
        )
        await self.repo.save_snapshot(
            _snapshot(
                generated_at="2026-05-07T11:00:00Z",
                fetched_at="2026-05-07T11:05:00Z",
            )
        )

        freshness = await self.repo.get_snapshot_freshness("project-1")

        self.assertEqual(freshness.source_generated_at.isoformat(), "2026-05-07T11:00:00+00:00")
        self.assertEqual(freshness.fetched_at.isoformat(), "2026-05-07T11:05:00+00:00")
        self.assertEqual(freshness.snapshot_source, "skillmeat")

    async def test_get_snapshot_freshness_for_missing_project_returns_warning_meta(self) -> None:
        freshness = await self.repo.get_snapshot_freshness("missing-project")

        self.assertIsNone(freshness.source_generated_at)
        self.assertIsNone(freshness.fetched_at)
        self.assertEqual(freshness.warnings, ["snapshot_not_found"])

    async def test_get_unresolved_identity_count_counts_project_unresolved_rows(self) -> None:
        await self.db.executemany(
            """
            INSERT INTO artifact_identity_map (
                project_id, ccdash_name, ccdash_type, match_tier, unresolved_reason
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("project-1", "frontend-design", "skill", "unresolved", "not_in_snapshot"),
                ("project-1", "symbols", "skill", "unresolved", "not_in_snapshot"),
                ("project-1", "planning", "skill", "uuid", ""),
                ("project-2", "frontend-design", "skill", "unresolved", "not_in_snapshot"),
            ],
        )
        await self.db.commit()

        self.assertEqual(await self.repo.get_unresolved_identity_count("project-1"), 2)
        self.assertEqual(await self.repo.get_unresolved_identity_count("project-2"), 1)
        self.assertEqual(await self.repo.get_unresolved_identity_count("missing-project"), 0)

    async def test_save_identity_mapping_replaces_existing_mapping_and_lists_rows(self) -> None:
        await self.repo.save_identity_mapping(
            {
                "project_id": "project-1",
                "ccdash_name": "frontend-design",
                "ccdash_type": "skill",
                "skillmeat_uuid": "old-uuid",
                "content_hash": "",
                "match_tier": "unresolved",
                "confidence": None,
                "resolved_at": "",
                "unresolved_reason": "not_in_snapshot",
            }
        )
        await self.repo.save_identity_mapping(
            {
                "project_id": "project-1",
                "ccdash_name": "frontend-design",
                "ccdash_type": "skill",
                "skillmeat_uuid": "new-uuid",
                "content_hash": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                "match_tier": "tier-1",
                "confidence": 1.0,
                "resolved_at": "2026-05-07T10:00:00Z",
                "unresolved_reason": "",
            }
        )

        mappings = await self.repo.list_identity_mappings("project-1")

        self.assertEqual(len(mappings), 1)
        self.assertEqual(mappings[0]["skillmeat_uuid"], "new-uuid")
        self.assertEqual(mappings[0]["match_tier"], "tier-1")
        self.assertEqual(mappings[0]["confidence"], 1.0)

    async def test_get_snapshot_diagnostics_returns_latest_counts_and_staleness(self) -> None:
        await self.repo.save_snapshot(
            _snapshot(
                generated_at="2026-05-07T10:00:00Z",
                fetched_at="2026-05-07T10:01:00Z",
            )
        )
        await self.db.executemany(
            """
            INSERT INTO artifact_identity_map (
                project_id, ccdash_name, ccdash_type, match_tier, unresolved_reason
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("project-1", "frontend-design", "skill", "uuid", ""),
                ("project-1", "symbols", "skill", "hash", ""),
                ("project-1", "planning", "skill", "unresolved", "not_in_snapshot"),
                ("project-2", "frontend-design", "skill", "unresolved", "not_in_snapshot"),
            ],
        )
        await self.db.commit()

        with patch(
            "backend.db.repositories.artifact_snapshot_repository._utc_now",
            return_value=datetime(2026, 5, 7, 10, 31, tzinfo=timezone.utc),
        ), patch(
            "backend.db.repositories.artifact_snapshot_repository.config.CCDASH_SNAPSHOT_FRESHNESS_MAX_AGE_SECONDS",
            3600,
        ):
            diagnostics = await self.repo.get_snapshot_diagnostics("project-1")

        self.assertEqual(diagnostics.project_id, "project-1")
        self.assertEqual(diagnostics.snapshot_age_seconds, 1800)
        self.assertEqual(diagnostics.artifact_count, 1)
        self.assertEqual(diagnostics.resolved_count, 2)
        self.assertEqual(diagnostics.unresolved_count, 1)
        self.assertFalse(diagnostics.is_stale)

        with patch(
            "backend.db.repositories.artifact_snapshot_repository._utc_now",
            return_value=datetime(2026, 5, 7, 12, 0, tzinfo=timezone.utc),
        ), patch(
            "backend.db.repositories.artifact_snapshot_repository.config.CCDASH_SNAPSHOT_FRESHNESS_MAX_AGE_SECONDS",
            3600,
        ):
            stale = await self.repo.get_snapshot_diagnostics("project-1")

        self.assertTrue(stale.is_stale)

    async def test_get_snapshot_diagnostics_for_missing_project_is_stale_empty_payload(self) -> None:
        diagnostics = await self.repo.get_snapshot_diagnostics("missing-project")

        self.assertEqual(diagnostics.project_id, "missing-project")
        self.assertIsNone(diagnostics.snapshot_age_seconds)
        self.assertEqual(diagnostics.artifact_count, 0)
        self.assertEqual(diagnostics.resolved_count, 0)
        self.assertEqual(diagnostics.unresolved_count, 0)
        self.assertTrue(diagnostics.is_stale)


class _FakePostgresConnection:
    def __init__(self):
        self.execute_calls: list[tuple[str, tuple[object, ...]]] = []
        self.fetchrow_results: list[dict | None] = []
        self.fetchval_results: list[object] = []
        self.fetch_results: list[list[dict]] = []

    async def execute(self, query: str, *args):
        self.execute_calls.append((query, args))

    async def fetchrow(self, query: str, *args):
        self.execute_calls.append((query, args))
        return self.fetchrow_results.pop(0)

    async def fetchval(self, query: str, *args):
        self.execute_calls.append((query, args))
        return self.fetchval_results.pop(0)

    async def fetch(self, query: str, *args):
        self.execute_calls.append((query, args))
        return self.fetch_results.pop(0)


class PostgresArtifactSnapshotRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_postgres_repository_uses_jsonb_insert_and_round_trips_rows(self) -> None:
        conn = _FakePostgresConnection()
        repo = PostgresArtifactSnapshotRepository(conn)  # type: ignore[arg-type]
        snapshot = _snapshot()

        await repo.save_snapshot(snapshot)

        insert_query, params = conn.execute_calls[0]
        self.assertIn("$8::jsonb", insert_query)
        self.assertEqual(params[0], "project-1")
        self.assertEqual(params[1], "collection-a")
        raw_payload = json.loads(params[7])
        self.assertEqual(raw_payload["projectId"], "project-1")
        self.assertEqual(raw_payload["freshness"]["fetchedAt"], "2026-05-07T10:01:00Z")

        conn.fetchrow_results.append(
            {
                "id": 1,
                "project_id": "project-1",
                "collection_id": "collection-a",
                "schema_version": SKILLMEAT_ARTIFACT_SNAPSHOT_SCHEMA_VERSION,
                "generated_at": "2026-05-07T10:00:00Z",
                "fetched_at": "2026-05-07T10:01:00Z",
                "artifact_count": 1,
                "status": "fetched",
                "raw_json": raw_payload,
            }
        )

        latest = await repo.get_latest_snapshot("project-1")

        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertEqual(latest.project_id, "project-1")
        self.assertEqual(latest.collection_id, "collection-a")

    async def test_postgres_freshness_and_unresolved_count_queries(self) -> None:
        conn = _FakePostgresConnection()
        conn.fetchrow_results.append({"generated_at": "2026-05-07T10:00:00Z", "fetched_at": "2026-05-07T10:01:00Z"})
        conn.fetchval_results.append(3)
        repo = PostgresArtifactSnapshotRepository(conn)  # type: ignore[arg-type]

        freshness = await repo.get_snapshot_freshness("project-1")
        count = await repo.get_unresolved_identity_count("project-1")

        self.assertEqual(freshness.source_generated_at.isoformat(), "2026-05-07T10:00:00+00:00")
        self.assertEqual(freshness.fetched_at.isoformat(), "2026-05-07T10:01:00+00:00")
        self.assertEqual(count, 3)
        self.assertEqual(conn.execute_calls[-1][1], ("project-1",))

    async def test_postgres_snapshot_diagnostics_queries_latest_snapshot_and_identity_counts(self) -> None:
        conn = _FakePostgresConnection()
        conn.fetchrow_results.extend(
            [
                {"artifact_count": 4, "fetched_at": "2026-05-07T10:00:00Z"},
                {"resolved_count": 3, "unresolved_count": 1},
            ]
        )
        repo = PostgresArtifactSnapshotRepository(conn)  # type: ignore[arg-type]

        with patch(
            "backend.db.repositories.artifact_snapshot_repository._utc_now",
            return_value=datetime(2026, 5, 7, 10, 10, tzinfo=timezone.utc),
        ), patch(
            "backend.db.repositories.artifact_snapshot_repository.config.CCDASH_SNAPSHOT_FRESHNESS_MAX_AGE_SECONDS",
            1200,
        ):
            diagnostics = await repo.get_snapshot_diagnostics("project-1")

        self.assertEqual(diagnostics.snapshot_age_seconds, 600)
        self.assertEqual(diagnostics.artifact_count, 4)
        self.assertEqual(diagnostics.resolved_count, 3)
        self.assertEqual(diagnostics.unresolved_count, 1)
        self.assertFalse(diagnostics.is_stale)
        self.assertIn("artifact_snapshot_cache", conn.execute_calls[0][0])
        self.assertIn("artifact_identity_map", conn.execute_calls[1][0])
        self.assertEqual(conn.execute_calls[0][1], ("project-1",))
        self.assertEqual(conn.execute_calls[1][1], ("project-1",))

    async def test_postgres_identity_mapping_write_and_list_queries(self) -> None:
        conn = _FakePostgresConnection()
        conn.fetch_results.append(
            [
                {
                    "project_id": "project-1",
                    "ccdash_name": "frontend-design",
                    "ccdash_type": "skill",
                    "skillmeat_uuid": "uuid-1",
                    "content_hash": "",
                    "match_tier": "tier-2",
                    "confidence": 0.91,
                    "resolved_at": "2026-05-07T10:00:00Z",
                    "unresolved_reason": "",
                }
            ]
        )
        repo = PostgresArtifactSnapshotRepository(conn)  # type: ignore[arg-type]

        await repo.save_identity_mapping(
            {
                "project_id": "project-1",
                "ccdash_name": "frontend-design",
                "ccdash_type": "skill",
                "skillmeat_uuid": "uuid-1",
                "content_hash": "",
                "match_tier": "tier-2",
                "confidence": 0.91,
                "resolved_at": "2026-05-07T10:00:00Z",
                "unresolved_reason": "",
            }
        )
        mappings = await repo.list_identity_mappings("project-1")

        self.assertIn("DELETE FROM artifact_identity_map", conn.execute_calls[0][0])
        self.assertIn("INSERT INTO artifact_identity_map", conn.execute_calls[1][0])
        self.assertEqual(conn.execute_calls[0][1], ("project-1", "frontend-design", "skill"))
        self.assertEqual(mappings[0]["match_tier"], "tier-2")
