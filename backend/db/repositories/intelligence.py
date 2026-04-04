"""SQLite repository for SkillMeat definition caches and stack observations."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import aiosqlite


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bool_to_int(value: object) -> int:
    return 1 if bool(value) else 0


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


class SqliteAgenticIntelligenceRepository:
    """SQLite-backed storage for external definitions and stack observations."""

    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def upsert_definition_source(self, source_data: dict, project_id: str | None = None) -> dict:
        now = _now_iso()
        resolved_project_id = str(project_id or source_data.get("project_id") or source_data.get("projectId") or "")
        source_kind = str(source_data.get("source_kind") or source_data.get("sourceKind") or "skillmeat")
        await self.db.execute(
            """
            INSERT INTO external_definition_sources (
                project_id, source_kind, enabled, base_url, project_mapping_json, feature_flags_json,
                last_synced_at, last_sync_status, last_sync_error, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, source_kind) DO UPDATE SET
                enabled=excluded.enabled,
                base_url=excluded.base_url,
                project_mapping_json=excluded.project_mapping_json,
                feature_flags_json=excluded.feature_flags_json,
                updated_at=excluded.updated_at
            """,
            (
                resolved_project_id,
                source_kind,
                _bool_to_int(source_data.get("enabled", False)),
                str(source_data.get("base_url") or source_data.get("baseUrl") or ""),
                json.dumps(
                    _parse_json_dict(
                        source_data.get("project_mapping", source_data.get("projectMapping", {}))
                    )
                ),
                json.dumps(
                    _parse_json_dict(
                        source_data.get("feature_flags", source_data.get("featureFlags", {}))
                    )
                ),
                str(source_data.get("last_synced_at") or source_data.get("lastSyncedAt") or ""),
                str(source_data.get("last_sync_status") or source_data.get("lastSyncStatus") or "never"),
                str(source_data.get("last_sync_error") or source_data.get("lastSyncError") or ""),
                str(source_data.get("created_at") or source_data.get("createdAt") or now),
                str(source_data.get("updated_at") or source_data.get("updatedAt") or now),
            ),
        )
        await self.db.commit()
        row = await self.get_definition_source(resolved_project_id, source_kind)
        return row or {}

    async def get_definition_source(self, project_id: str, source_kind: str = "skillmeat") -> dict | None:
        async with self.db.execute(
            """
            SELECT *
            FROM external_definition_sources
            WHERE project_id = ? AND source_kind = ?
            LIMIT 1
            """,
            (project_id, source_kind),
        ) as cur:
            row = await cur.fetchone()
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
        now = _now_iso()
        await self.db.execute(
            """
            UPDATE external_definition_sources
            SET last_synced_at = ?, last_sync_status = ?, last_sync_error = ?, updated_at = ?
            WHERE project_id = ? AND source_kind = ?
            """,
            (last_synced_at, last_sync_status, last_sync_error, now, project_id, source_kind),
        )
        await self.db.commit()
        return await self.get_definition_source(project_id, source_kind)

    async def upsert_external_definition(self, definition_data: dict, project_id: str | None = None) -> dict:
        now = _now_iso()
        resolved_project_id = str(project_id or definition_data.get("project_id") or definition_data.get("projectId") or "")
        await self.db.execute(
            """
            INSERT INTO external_definitions (
                project_id, source_id, definition_type, external_id, display_name, version, source_url,
                resolution_metadata_json, raw_snapshot_json, fetched_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, definition_type, external_id) DO UPDATE SET
                source_id=excluded.source_id,
                display_name=excluded.display_name,
                version=excluded.version,
                source_url=excluded.source_url,
                resolution_metadata_json=excluded.resolution_metadata_json,
                raw_snapshot_json=excluded.raw_snapshot_json,
                fetched_at=excluded.fetched_at,
                updated_at=excluded.updated_at
            """,
            (
                resolved_project_id,
                definition_data.get("source_id") or definition_data.get("sourceId"),
                str(definition_data.get("definition_type") or definition_data.get("definitionType") or ""),
                str(definition_data.get("external_id") or definition_data.get("externalId") or ""),
                str(definition_data.get("display_name") or definition_data.get("displayName") or ""),
                str(definition_data.get("version") or ""),
                str(definition_data.get("source_url") or definition_data.get("sourceUrl") or ""),
                json.dumps(
                    _parse_json_dict(
                        definition_data.get("resolution_metadata", definition_data.get("resolutionMetadata", {}))
                    )
                ),
                json.dumps(_parse_json_dict(definition_data.get("raw_snapshot", definition_data.get("rawSnapshot", {})))),
                str(definition_data.get("fetched_at") or definition_data.get("fetchedAt") or now),
                str(definition_data.get("created_at") or definition_data.get("createdAt") or now),
                str(definition_data.get("updated_at") or definition_data.get("updatedAt") or now),
            ),
        )
        await self.db.commit()
        return (
            await self.get_external_definition(
                resolved_project_id,
                str(definition_data.get("definition_type") or definition_data.get("definitionType") or ""),
                str(definition_data.get("external_id") or definition_data.get("externalId") or ""),
            )
            or {}
        )

    async def list_external_definitions(
        self,
        project_id: str,
        *,
        definition_type: str | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[dict]:
        if definition_type:
            query = """
                SELECT *
                FROM external_definitions
                WHERE project_id = ? AND definition_type = ?
                ORDER BY definition_type ASC, display_name ASC, id DESC
                LIMIT ? OFFSET ?
            """
            params: tuple[object, ...] = (project_id, definition_type, limit, offset)
        else:
            query = """
                SELECT *
                FROM external_definitions
                WHERE project_id = ?
                ORDER BY definition_type ASC, display_name ASC, id DESC
                LIMIT ? OFFSET ?
            """
            params = (project_id, limit, offset)
        async with self.db.execute(query, params) as cur:
            rows = await cur.fetchall()
        return [self._definition_row_to_dict(row) for row in rows]

    async def get_external_definition(self, project_id: str, definition_type: str, external_id: str) -> dict | None:
        async with self.db.execute(
            """
            SELECT *
            FROM external_definitions
            WHERE project_id = ? AND definition_type = ? AND external_id = ?
            LIMIT 1
            """,
            (project_id, definition_type, external_id),
        ) as cur:
            row = await cur.fetchone()
        return self._definition_row_to_dict(row) if row else None

    async def upsert_stack_observation(
        self,
        observation_data: dict,
        components: list[dict] | None = None,
        project_id: str | None = None,
    ) -> dict:
        now = _now_iso()
        resolved_project_id = str(project_id or observation_data.get("project_id") or observation_data.get("projectId") or "")
        session_id = str(observation_data.get("session_id") or observation_data.get("sessionId") or "")
        await self.db.execute(
            """
            INSERT INTO session_stack_observations (
                project_id, session_id, feature_id, workflow_ref, confidence, observation_source,
                evidence_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, session_id) DO UPDATE SET
                feature_id=excluded.feature_id,
                workflow_ref=excluded.workflow_ref,
                confidence=excluded.confidence,
                observation_source=excluded.observation_source,
                evidence_json=excluded.evidence_json,
                updated_at=excluded.updated_at
            """,
            (
                resolved_project_id,
                session_id,
                str(observation_data.get("feature_id") or observation_data.get("featureId") or ""),
                str(observation_data.get("workflow_ref") or observation_data.get("workflowRef") or ""),
                float(observation_data.get("confidence") or 0.0),
                str(observation_data.get("source") or observation_data.get("observation_source") or "backfill"),
                json.dumps(_parse_json_dict(observation_data.get("evidence", observation_data.get("evidence_json", {})))),
                str(observation_data.get("created_at") or observation_data.get("createdAt") or now),
                str(observation_data.get("updated_at") or observation_data.get("updatedAt") or now),
            ),
        )
        async with self.db.execute(
            """
            SELECT *
            FROM session_stack_observations
            WHERE project_id = ? AND session_id = ?
            LIMIT 1
            """,
            (resolved_project_id, session_id),
        ) as cur:
            row = await cur.fetchone()
        observation = self._observation_row_to_dict(row) if row else {}
        observation_id = int(observation.get("id") or 0)

        if components is not None and observation_id:
            await self.db.execute(
                "DELETE FROM session_stack_components WHERE observation_id = ?",
                (observation_id,),
            )
            for component in components:
                await self.db.execute(
                    """
                    INSERT INTO session_stack_components (
                        project_id, observation_id, component_type, component_key, status, confidence,
                        external_definition_id, external_definition_type, external_definition_external_id,
                        source_attribution, component_payload_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
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
                    ),
                )
        await self.db.commit()
        observation["components"] = await self.list_stack_components(observation_id) if observation_id else []
        return observation

    async def get_stack_observation(self, project_id: str, session_id: str) -> dict | None:
        async with self.db.execute(
            """
            SELECT *
            FROM session_stack_observations
            WHERE project_id = ? AND session_id = ?
            LIMIT 1
            """,
            (project_id, session_id),
        ) as cur:
            row = await cur.fetchone()
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
            query = """
                SELECT *
                FROM session_stack_observations
                WHERE project_id = ? AND feature_id = ?
                ORDER BY updated_at DESC, id DESC
                LIMIT ? OFFSET ?
            """
            params: tuple[object, ...] = (project_id, feature_id, limit, offset)
        else:
            query = """
                SELECT *
                FROM session_stack_observations
                WHERE project_id = ?
                ORDER BY updated_at DESC, id DESC
                LIMIT ? OFFSET ?
            """
            params = (project_id, limit, offset)
        async with self.db.execute(query, params) as cur:
            rows = await cur.fetchall()
        return [self._observation_row_to_dict(row) for row in rows]

    async def list_stack_components(self, observation_id: int) -> list[dict]:
        async with self.db.execute(
            """
            SELECT *
            FROM session_stack_components
            WHERE observation_id = ?
            ORDER BY component_type ASC, id ASC
            """,
            (observation_id,),
        ) as cur:
            rows = await cur.fetchall()
        return [self._component_row_to_dict(row) for row in rows]

    async def upsert_effectiveness_rollup(
        self,
        rollup_data: dict,
        project_id: str | None = None,
    ) -> dict:
        now = _now_iso()
        resolved_project_id = str(project_id or rollup_data.get("project_id") or rollup_data.get("projectId") or "")
        scope_type = str(rollup_data.get("scope_type") or rollup_data.get("scopeType") or "")
        scope_id = str(rollup_data.get("scope_id") or rollup_data.get("scopeId") or "")
        period = str(rollup_data.get("period") or "all")
        await self.db.execute(
            """
            INSERT INTO effectiveness_rollups (
                project_id, scope_type, scope_id, period, metrics_json, evidence_summary_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, scope_type, scope_id, period) DO UPDATE SET
                metrics_json=excluded.metrics_json,
                evidence_summary_json=excluded.evidence_summary_json,
                updated_at=excluded.updated_at
            """,
            (
                resolved_project_id,
                scope_type,
                scope_id,
                period,
                json.dumps(_parse_json_dict(rollup_data.get("metrics", rollup_data.get("metrics_json", {})))),
                json.dumps(
                    _parse_json_dict(
                        rollup_data.get("evidence_summary", rollup_data.get("evidenceSummary", rollup_data.get("evidence_summary_json", {})))
                    )
                ),
                str(rollup_data.get("created_at") or rollup_data.get("createdAt") or now),
                str(rollup_data.get("updated_at") or rollup_data.get("updatedAt") or now),
            ),
        )
        await self.db.commit()
        rows = await self.list_effectiveness_rollups(
            resolved_project_id,
            scope_type=scope_type,
            scope_id=scope_id,
            period=period,
            limit=1,
            offset=0,
        )
        return rows[0] if rows else {}

    async def list_effectiveness_rollups(
        self,
        project_id: str,
        *,
        scope_type: str | None = None,
        scope_id: str | None = None,
        period: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict]:
        where_clauses = ["project_id = ?"]
        params: list[object] = [project_id]
        if scope_type:
            where_clauses.append("scope_type = ?")
            params.append(scope_type)
        if scope_id:
            where_clauses.append("scope_id = ?")
            params.append(scope_id)
        if period:
            if period == "all":
                where_clauses.append("period = ?")
                params.append("all")
            else:
                where_clauses.append("period LIKE ?")
                params.append(f"{period}:%")

        query = (
            "SELECT * "
            "FROM effectiveness_rollups "
            f"WHERE {' AND '.join(where_clauses)} "
            "ORDER BY updated_at DESC, scope_type ASC, scope_id ASC "
            "LIMIT ? OFFSET ?"
        )
        params.extend([limit, offset])
        async with self.db.execute(query, tuple(params)) as cur:
            rows = await cur.fetchall()
        return [self._rollup_row_to_dict(row) for row in rows]

    async def purge_effectiveness_rollups(
        self,
        project_id: str,
        *,
        period: str | None = None,
    ) -> None:
        if period:
            if period == "all":
                query = "DELETE FROM effectiveness_rollups WHERE project_id = ? AND period = ?"
                params: tuple[object, ...] = (project_id, "all")
            else:
                query = "DELETE FROM effectiveness_rollups WHERE project_id = ? AND period LIKE ?"
                params = (project_id, f"{period}:%")
        else:
            query = "DELETE FROM effectiveness_rollups WHERE project_id = ?"
            params = (project_id,)
        await self.db.execute(query, params)
        await self.db.commit()

    async def upsert_session_memory_draft(
        self,
        draft_data: dict[str, Any],
        project_id: str | None = None,
    ) -> dict[str, Any]:
        now = _now_iso()
        resolved_project_id = str(project_id or draft_data.get("project_id") or draft_data.get("projectId") or "")
        content_hash = str(draft_data.get("content_hash") or draft_data.get("contentHash") or "").strip()
        if not resolved_project_id or not content_hash:
            raise ValueError("project_id and content_hash are required for session memory drafts")
        await self.db.execute(
            """
            INSERT INTO session_memory_drafts (
                project_id, session_id, feature_id, root_session_id, thread_session_id, workflow_ref,
                title, memory_type, status, module_name, module_description, content, confidence,
                source_message_id, source_log_id, source_message_index, content_hash, evidence_json,
                publish_attempts, published_module_id, published_memory_id, reviewed_by, review_notes,
                reviewed_at, published_at, last_publish_error, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, content_hash) DO UPDATE SET
                session_id=excluded.session_id,
                feature_id=excluded.feature_id,
                root_session_id=excluded.root_session_id,
                thread_session_id=excluded.thread_session_id,
                workflow_ref=excluded.workflow_ref,
                title=excluded.title,
                memory_type=excluded.memory_type,
                status=excluded.status,
                module_name=excluded.module_name,
                module_description=excluded.module_description,
                content=excluded.content,
                confidence=excluded.confidence,
                source_message_id=excluded.source_message_id,
                source_log_id=excluded.source_log_id,
                source_message_index=excluded.source_message_index,
                evidence_json=excluded.evidence_json,
                publish_attempts=excluded.publish_attempts,
                published_module_id=excluded.published_module_id,
                published_memory_id=excluded.published_memory_id,
                reviewed_by=excluded.reviewed_by,
                review_notes=excluded.review_notes,
                reviewed_at=excluded.reviewed_at,
                published_at=excluded.published_at,
                last_publish_error=excluded.last_publish_error,
                updated_at=excluded.updated_at
            """,
            (
                resolved_project_id,
                str(draft_data.get("session_id") or draft_data.get("sessionId") or ""),
                str(draft_data.get("feature_id") or draft_data.get("featureId") or ""),
                str(draft_data.get("root_session_id") or draft_data.get("rootSessionId") or ""),
                str(draft_data.get("thread_session_id") or draft_data.get("threadSessionId") or ""),
                str(draft_data.get("workflow_ref") or draft_data.get("workflowRef") or ""),
                str(draft_data.get("title") or ""),
                str(draft_data.get("memory_type") or draft_data.get("memoryType") or "learning"),
                str(draft_data.get("status") or "draft"),
                str(draft_data.get("module_name") or draft_data.get("moduleName") or ""),
                str(draft_data.get("module_description") or draft_data.get("moduleDescription") or ""),
                str(draft_data.get("content") or ""),
                float(draft_data.get("confidence") or 0.0),
                str(draft_data.get("source_message_id") or draft_data.get("sourceMessageId") or ""),
                str(draft_data.get("source_log_id") or draft_data.get("sourceLogId") or ""),
                int(draft_data.get("source_message_index") or draft_data.get("sourceMessageIndex") or 0),
                content_hash,
                json.dumps(_parse_json_dict(draft_data.get("evidence", draft_data.get("evidence_json", {})))),
                int(draft_data.get("publish_attempts") or draft_data.get("publishAttempts") or 0),
                str(draft_data.get("published_module_id") or draft_data.get("publishedModuleId") or ""),
                str(draft_data.get("published_memory_id") or draft_data.get("publishedMemoryId") or ""),
                str(draft_data.get("reviewed_by") or draft_data.get("reviewedBy") or ""),
                str(draft_data.get("review_notes") or draft_data.get("reviewNotes") or ""),
                str(draft_data.get("reviewed_at") or draft_data.get("reviewedAt") or ""),
                str(draft_data.get("published_at") or draft_data.get("publishedAt") or ""),
                str(draft_data.get("last_publish_error") or draft_data.get("lastPublishError") or ""),
                str(draft_data.get("created_at") or draft_data.get("createdAt") or now),
                str(draft_data.get("updated_at") or draft_data.get("updatedAt") or now),
            ),
        )
        await self.db.commit()
        async with self.db.execute(
            """
            SELECT *
            FROM session_memory_drafts
            WHERE project_id = ? AND content_hash = ?
            LIMIT 1
            """,
            (resolved_project_id, content_hash),
        ) as cur:
            row = await cur.fetchone()
        return self._memory_draft_row_to_dict(row) if row else {}

    async def get_session_memory_draft(self, project_id: str, draft_id: int) -> dict[str, Any] | None:
        async with self.db.execute(
            """
            SELECT *
            FROM session_memory_drafts
            WHERE project_id = ? AND id = ?
            LIMIT 1
            """,
            (project_id, draft_id),
        ) as cur:
            row = await cur.fetchone()
        return self._memory_draft_row_to_dict(row) if row else None

    async def count_session_memory_drafts(
        self,
        project_id: str,
        *,
        session_id: str | None = None,
        status: str | None = None,
    ) -> int:
        where = ["project_id = ?"]
        params: list[object] = [project_id]
        if session_id:
            where.append("session_id = ?")
            params.append(session_id)
        if status:
            where.append("status = ?")
            params.append(status)
        async with self.db.execute(
            f"SELECT COUNT(*) AS count FROM session_memory_drafts WHERE {' AND '.join(where)}",
            tuple(params),
        ) as cur:
            row = await cur.fetchone()
        return int(row["count"] or 0) if row else 0

    async def list_session_memory_drafts(
        self,
        project_id: str,
        *,
        session_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        where = ["project_id = ?"]
        params: list[object] = [project_id]
        if session_id:
            where.append("session_id = ?")
            params.append(session_id)
        if status:
            where.append("status = ?")
            params.append(status)
        params.extend([limit, offset])
        async with self.db.execute(
            (
                "SELECT * FROM session_memory_drafts "
                f"WHERE {' AND '.join(where)} "
                "ORDER BY updated_at DESC, id DESC LIMIT ? OFFSET ?"
            ),
            tuple(params),
        ) as cur:
            rows = await cur.fetchall()
        return [self._memory_draft_row_to_dict(row) for row in rows]

    async def review_session_memory_draft(
        self,
        project_id: str,
        draft_id: int,
        *,
        decision: str,
        actor: str = "",
        notes: str = "",
    ) -> dict[str, Any] | None:
        now = _now_iso()
        await self.db.execute(
            """
            UPDATE session_memory_drafts
            SET status = ?, reviewed_by = ?, review_notes = ?, reviewed_at = ?, updated_at = ?
            WHERE project_id = ? AND id = ?
            """,
            (decision, actor, notes, now, now, project_id, draft_id),
        )
        await self.db.commit()
        return await self.get_session_memory_draft(project_id, draft_id)

    async def record_session_memory_draft_publish_attempt(
        self,
        project_id: str,
        draft_id: int,
        *,
        actor: str = "",
        notes: str = "",
        module_id: str = "",
        memory_id: str = "",
        source_url: str = "",
        error: str = "",
    ) -> dict[str, Any] | None:
        existing = await self.get_session_memory_draft(project_id, draft_id)
        if existing is None:
            return None
        now = _now_iso()
        publish_attempts = int(existing.get("publish_attempts") or 0) + 1
        next_status = "published" if not error else str(existing.get("status") or "approved")
        review_notes = str(existing.get("review_notes") or "")
        combined_notes = review_notes
        if notes.strip():
            combined_notes = notes.strip() if not review_notes else f"{review_notes}\n\nPublish: {notes.strip()}"
        await self.db.execute(
            """
            UPDATE session_memory_drafts
            SET status = ?, publish_attempts = ?, published_module_id = ?, published_memory_id = ?,
                review_notes = ?, published_at = ?, last_publish_error = ?, updated_at = ?
            WHERE project_id = ? AND id = ?
            """,
            (
                next_status,
                publish_attempts,
                module_id,
                memory_id or source_url,
                combined_notes,
                now if not error else str(existing.get("published_at") or ""),
                error,
                now,
                project_id,
                draft_id,
            ),
        )
        await self.db.commit()
        return await self.get_session_memory_draft(project_id, draft_id)


    def _source_row_to_dict(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        data["enabled"] = bool(data.get("enabled"))
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

    def _rollup_row_to_dict(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        data["metrics_json"] = _parse_json_dict(data.get("metrics_json"))
        data["evidence_summary_json"] = _parse_json_dict(data.get("evidence_summary_json"))
        return data


    def _memory_draft_row_to_dict(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        data["evidence_json"] = _parse_json_dict(data.get("evidence_json"))
        return data
