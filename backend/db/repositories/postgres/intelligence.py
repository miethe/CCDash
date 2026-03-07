"""PostgreSQL repository for SkillMeat definition caches and stack observations."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import asyncpg


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_json_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


class PostgresAgenticIntelligenceRepository:
    """PostgreSQL-backed storage for external definitions and stack observations."""

    def __init__(self, db: asyncpg.Connection):
        self.db = db

    async def upsert_definition_source(self, source_data: dict, project_id: str | None = None) -> dict:
        now = _now_iso()
        resolved_project_id = str(project_id or source_data.get("project_id") or source_data.get("projectId") or "")
        source_kind = str(source_data.get("source_kind") or source_data.get("sourceKind") or "skillmeat")
        row = await self.db.fetchrow(
            """
            INSERT INTO external_definition_sources (
                project_id, source_kind, enabled, base_url, project_mapping_json, feature_flags_json,
                last_synced_at, last_sync_status, last_sync_error, created_at, updated_at
            ) VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7, $8, $9, $10, $11)
            ON CONFLICT(project_id, source_kind) DO UPDATE SET
                enabled=EXCLUDED.enabled,
                base_url=EXCLUDED.base_url,
                project_mapping_json=EXCLUDED.project_mapping_json,
                feature_flags_json=EXCLUDED.feature_flags_json,
                updated_at=EXCLUDED.updated_at
            RETURNING *
            """,
            resolved_project_id,
            source_kind,
            bool(source_data.get("enabled", False)),
            str(source_data.get("base_url") or source_data.get("baseUrl") or ""),
            json.dumps(_parse_json_dict(source_data.get("project_mapping", source_data.get("projectMapping", {})))),
            json.dumps(_parse_json_dict(source_data.get("feature_flags", source_data.get("featureFlags", {})))),
            str(source_data.get("last_synced_at") or source_data.get("lastSyncedAt") or ""),
            str(source_data.get("last_sync_status") or source_data.get("lastSyncStatus") or "never"),
            str(source_data.get("last_sync_error") or source_data.get("lastSyncError") or ""),
            str(source_data.get("created_at") or source_data.get("createdAt") or now),
            str(source_data.get("updated_at") or source_data.get("updatedAt") or now),
        )
        return self._source_row_to_dict(row) if row else {}

    async def get_definition_source(self, project_id: str, source_kind: str = "skillmeat") -> dict | None:
        row = await self.db.fetchrow(
            """
            SELECT *
            FROM external_definition_sources
            WHERE project_id = $1 AND source_kind = $2
            LIMIT 1
            """,
            project_id,
            source_kind,
        )
        return self._source_row_to_dict(row) if row else None

    async def update_definition_source_status(
        self,
        project_id: str,
        source_kind: str,
        *,
        last_synced_at: str = "",
        last_sync_status: str = "",
        last_sync_error: str = "",
    ) -> dict | None:
        row = await self.db.fetchrow(
            """
            UPDATE external_definition_sources
            SET last_synced_at = $1, last_sync_status = $2, last_sync_error = $3, updated_at = $4
            WHERE project_id = $5 AND source_kind = $6
            RETURNING *
            """,
            last_synced_at,
            last_sync_status,
            last_sync_error,
            _now_iso(),
            project_id,
            source_kind,
        )
        return self._source_row_to_dict(row) if row else None

    async def upsert_external_definition(self, definition_data: dict, project_id: str | None = None) -> dict:
        now = _now_iso()
        resolved_project_id = str(project_id or definition_data.get("project_id") or definition_data.get("projectId") or "")
        row = await self.db.fetchrow(
            """
            INSERT INTO external_definitions (
                project_id, source_id, definition_type, external_id, display_name, version, source_url,
                resolution_metadata_json, raw_snapshot_json, fetched_at, created_at, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb, $10, $11, $12)
            ON CONFLICT(project_id, definition_type, external_id) DO UPDATE SET
                source_id=EXCLUDED.source_id,
                display_name=EXCLUDED.display_name,
                version=EXCLUDED.version,
                source_url=EXCLUDED.source_url,
                resolution_metadata_json=EXCLUDED.resolution_metadata_json,
                raw_snapshot_json=EXCLUDED.raw_snapshot_json,
                fetched_at=EXCLUDED.fetched_at,
                updated_at=EXCLUDED.updated_at
            RETURNING *
            """,
            resolved_project_id,
            definition_data.get("source_id") or definition_data.get("sourceId"),
            str(definition_data.get("definition_type") or definition_data.get("definitionType") or ""),
            str(definition_data.get("external_id") or definition_data.get("externalId") or ""),
            str(definition_data.get("display_name") or definition_data.get("displayName") or ""),
            str(definition_data.get("version") or ""),
            str(definition_data.get("source_url") or definition_data.get("sourceUrl") or ""),
            json.dumps(_parse_json_dict(definition_data.get("resolution_metadata", definition_data.get("resolutionMetadata", {})))),
            json.dumps(_parse_json_dict(definition_data.get("raw_snapshot", definition_data.get("rawSnapshot", {})))),
            str(definition_data.get("fetched_at") or definition_data.get("fetchedAt") or now),
            str(definition_data.get("created_at") or definition_data.get("createdAt") or now),
            str(definition_data.get("updated_at") or definition_data.get("updatedAt") or now),
        )
        return self._definition_row_to_dict(row) if row else {}

    async def list_external_definitions(
        self,
        project_id: str,
        *,
        definition_type: str | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[dict]:
        if definition_type:
            rows = await self.db.fetch(
                """
                SELECT *
                FROM external_definitions
                WHERE project_id = $1 AND definition_type = $2
                ORDER BY definition_type ASC, display_name ASC, id DESC
                LIMIT $3 OFFSET $4
                """,
                project_id,
                definition_type,
                limit,
                offset,
            )
        else:
            rows = await self.db.fetch(
                """
                SELECT *
                FROM external_definitions
                WHERE project_id = $1
                ORDER BY definition_type ASC, display_name ASC, id DESC
                LIMIT $2 OFFSET $3
                """,
                project_id,
                limit,
                offset,
            )
        return [self._definition_row_to_dict(row) for row in rows]

    async def get_external_definition(self, project_id: str, definition_type: str, external_id: str) -> dict | None:
        row = await self.db.fetchrow(
            """
            SELECT *
            FROM external_definitions
            WHERE project_id = $1 AND definition_type = $2 AND external_id = $3
            LIMIT 1
            """,
            project_id,
            definition_type,
            external_id,
        )
        return self._definition_row_to_dict(row) if row else None

    async def upsert_stack_observation(
        self,
        observation_data: dict,
        components: list[dict] | None = None,
        project_id: str | None = None,
    ) -> dict:
        now = _now_iso()
        resolved_project_id = str(project_id or observation_data.get("project_id") or observation_data.get("projectId") or "")
        row = await self.db.fetchrow(
            """
            INSERT INTO session_stack_observations (
                project_id, session_id, feature_id, workflow_ref, confidence, observation_source,
                evidence_json, created_at, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9)
            ON CONFLICT(project_id, session_id) DO UPDATE SET
                feature_id=EXCLUDED.feature_id,
                workflow_ref=EXCLUDED.workflow_ref,
                confidence=EXCLUDED.confidence,
                observation_source=EXCLUDED.observation_source,
                evidence_json=EXCLUDED.evidence_json,
                updated_at=EXCLUDED.updated_at
            RETURNING *
            """,
            resolved_project_id,
            str(observation_data.get("session_id") or observation_data.get("sessionId") or ""),
            str(observation_data.get("feature_id") or observation_data.get("featureId") or ""),
            str(observation_data.get("workflow_ref") or observation_data.get("workflowRef") or ""),
            float(observation_data.get("confidence") or 0.0),
            str(observation_data.get("source") or observation_data.get("observation_source") or "backfill"),
            json.dumps(_parse_json_dict(observation_data.get("evidence", observation_data.get("evidence_json", {})))),
            str(observation_data.get("created_at") or observation_data.get("createdAt") or now),
            str(observation_data.get("updated_at") or observation_data.get("updatedAt") or now),
        )
        observation = self._observation_row_to_dict(row) if row else {}
        observation_id = int(observation.get("id") or 0)

        if components is not None and observation_id:
            await self.db.execute(
                "DELETE FROM session_stack_components WHERE observation_id = $1",
                observation_id,
            )
            for component in components:
                await self.db.execute(
                    """
                    INSERT INTO session_stack_components (
                        project_id, observation_id, component_type, component_key, status, confidence,
                        external_definition_id, external_definition_type, external_definition_external_id,
                        source_attribution, component_payload_json, created_at, updated_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb, $12, $13)
                    """,
                    resolved_project_id,
                    observation_id,
                    str(component.get("component_type") or component.get("componentType") or ""),
                    str(component.get("component_key") or component.get("componentKey") or ""),
                    str(component.get("status") or "explicit"),
                    float(component.get("confidence") or 0.0),
                    component.get("external_definition_id") or component.get("externalDefinitionId"),
                    str(component.get("external_definition_type") or component.get("externalDefinitionType") or ""),
                    str(component.get("external_definition_external_id") or component.get("externalDefinitionExternalId") or ""),
                    str(component.get("source_attribution") or component.get("sourceAttribution") or ""),
                    json.dumps(_parse_json_dict(component.get("payload", component.get("component_payload_json", {})))),
                    str(component.get("created_at") or component.get("createdAt") or now),
                    str(component.get("updated_at") or component.get("updatedAt") or now),
                )
        observation["components"] = await self.list_stack_components(observation_id) if observation_id else []
        return observation

    async def get_stack_observation(self, project_id: str, session_id: str) -> dict | None:
        row = await self.db.fetchrow(
            """
            SELECT *
            FROM session_stack_observations
            WHERE project_id = $1 AND session_id = $2
            LIMIT 1
            """,
            project_id,
            session_id,
        )
        if not row:
            return None
        observation = self._observation_row_to_dict(row)
        observation["components"] = await self.list_stack_components(int(observation.get("id") or 0))
        return observation

    async def list_stack_observations(
        self,
        project_id: str,
        *,
        limit: int = 200,
        offset: int = 0,
        feature_id: str | None = None,
    ) -> list[dict]:
        if feature_id:
            rows = await self.db.fetch(
                """
                SELECT *
                FROM session_stack_observations
                WHERE project_id = $1 AND feature_id = $2
                ORDER BY updated_at DESC, id DESC
                LIMIT $3 OFFSET $4
                """,
                project_id,
                feature_id,
                limit,
                offset,
            )
        else:
            rows = await self.db.fetch(
                """
                SELECT *
                FROM session_stack_observations
                WHERE project_id = $1
                ORDER BY updated_at DESC, id DESC
                LIMIT $2 OFFSET $3
                """,
                project_id,
                limit,
                offset,
            )
        return [self._observation_row_to_dict(row) for row in rows]

    async def list_stack_components(self, observation_id: int) -> list[dict]:
        rows = await self.db.fetch(
            """
            SELECT *
            FROM session_stack_components
            WHERE observation_id = $1
            ORDER BY component_type ASC, id ASC
            """,
            observation_id,
        )
        return [self._component_row_to_dict(row) for row in rows]

    def _source_row_to_dict(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        data["project_mapping_json"] = _parse_json_dict(data.get("project_mapping_json"))
        data["feature_flags_json"] = _parse_json_dict(data.get("feature_flags_json"))
        return data

    def _definition_row_to_dict(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        data["resolution_metadata_json"] = _parse_json_dict(data.get("resolution_metadata_json"))
        data["raw_snapshot_json"] = _parse_json_dict(data.get("raw_snapshot_json"))
        return data

    def _observation_row_to_dict(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        data["evidence_json"] = _parse_json_dict(data.get("evidence_json"))
        return data

    def _component_row_to_dict(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        data["component_payload_json"] = _parse_json_dict(data.get("component_payload_json"))
        return data
