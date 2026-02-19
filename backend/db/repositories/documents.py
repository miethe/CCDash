"""SQLite implementation of DocumentRepository."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from backend.document_linking import canonical_slug, normalize_ref_path


class SqliteDocumentRepository:
    """SQLite-backed document storage with typed metadata and refs."""

    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    def _extract_document_refs(self, doc_data: dict, project_id: str) -> list[tuple[str, str, str, str]]:
        refs: list[tuple[str, str, str, str]] = []
        frontmatter = doc_data.get("frontmatter", {}) if isinstance(doc_data.get("frontmatter"), dict) else {}
        metadata = doc_data.get("metadata", {}) if isinstance(doc_data.get("metadata"), dict) else {}

        def add(kind: str, value: str, source_field: str) -> None:
            raw = (value or "").strip()
            if not raw:
                return
            norm = normalize_ref_path(raw).lower() if "/" in raw or raw.lower().endswith(".md") else raw.lower()
            if kind in {"feature", "feature_ref", "feature_slug"}:
                norm = canonical_slug(norm)
            refs.append((kind, raw, norm, source_field))

        for value in frontmatter.get("linkedFeatures", []) or []:
            if isinstance(value, str):
                add("feature", value, "linkedFeatures")
        for value in frontmatter.get("linkedSessions", []) or []:
            if isinstance(value, str):
                add("session", value, "linkedSessions")
        for value in frontmatter.get("relatedRefs", []) or []:
            if isinstance(value, str):
                add("related", value, "relatedRefs")
        for value in frontmatter.get("pathRefs", []) or []:
            if isinstance(value, str):
                add("path", value, "pathRefs")
        for value in frontmatter.get("slugRefs", []) or []:
            if isinstance(value, str):
                add("slug", value, "slugRefs")
        for value in frontmatter.get("prdRefs", []) or []:
            if isinstance(value, str):
                add("prd", value, "prdRefs")
        prd_primary = frontmatter.get("prd")
        if isinstance(prd_primary, str):
            add("prd", prd_primary, "prd")
        for value in frontmatter.get("commits", []) or []:
            if isinstance(value, str):
                add("commit", value, "commits")
        for value in metadata.get("requestLogIds", []) or []:
            if isinstance(value, str):
                add("request_log", value, "requestLogIds")
        for value in metadata.get("owners", []) or []:
            if isinstance(value, str):
                add("owner", value, "owners")
        for value in metadata.get("contributors", []) or []:
            if isinstance(value, str):
                add("contributor", value, "contributors")
        for value in metadata.get("commitRefs", []) or []:
            if isinstance(value, str):
                add("commit", value, "commitRefs")

        unique: dict[tuple[str, str, str], tuple[str, str, str, str]] = {}
        for kind, raw, norm, source_field in refs:
            unique[(kind, norm, source_field)] = (kind, raw, norm, source_field)
        return list(unique.values())

    def _build_where_clause(self, project_id: str, filters: dict | None = None) -> tuple[str, list[Any]]:
        filters = filters or {}
        clauses = ["project_id = ?"]
        params: list[Any] = [project_id]

        include_progress = filters.get("include_progress")
        if include_progress is False:
            clauses.append("root_kind != 'progress'")

        if filters.get("root_kind"):
            clauses.append("root_kind = ?")
            params.append(str(filters["root_kind"]))
        if filters.get("doc_subtype"):
            clauses.append("doc_subtype = ?")
            params.append(str(filters["doc_subtype"]))
        if filters.get("doc_type"):
            clauses.append("doc_type = ?")
            params.append(str(filters["doc_type"]))
        if filters.get("category"):
            clauses.append("category = ?")
            params.append(str(filters["category"]))
        if filters.get("status"):
            clauses.append("(status_normalized = ? OR status = ?)")
            status = str(filters["status"])
            params.extend([status, status])
        if filters.get("feature"):
            token = canonical_slug(str(filters["feature"]).strip().lower())
            clauses.append(
                """
                (
                    feature_slug_canonical = ?
                    OR feature_slug_hint = ?
                    OR EXISTS (
                        SELECT 1 FROM document_refs dr
                        WHERE dr.document_id = documents.id
                          AND dr.ref_kind IN ('feature', 'feature_ref', 'feature_slug', 'prd')
                          AND dr.ref_value_norm = ?
                    )
                )
                """
            )
            params.extend([token, token, token])
        if filters.get("prd"):
            token = str(filters["prd"]).strip().lower()
            clauses.append(
                """
                (
                    lower(prd_ref) = ?
                    OR EXISTS (
                        SELECT 1 FROM document_refs dr
                        WHERE dr.document_id = documents.id
                          AND dr.ref_kind = 'prd'
                          AND dr.ref_value_norm = ?
                    )
                )
                """
            )
            params.extend([token, token])
        if filters.get("phase"):
            phase_token = str(filters["phase"]).strip()
            clauses.append("(phase_token = ? OR CAST(phase_number AS TEXT) = ?)")
            params.extend([phase_token, phase_token])
        if filters.get("has_frontmatter") is not None:
            clauses.append("has_frontmatter = ?")
            params.append(1 if filters["has_frontmatter"] else 0)
        if filters.get("q"):
            needle = f"%{str(filters['q']).strip().lower()}%"
            clauses.append(
                """
                (
                    lower(title) LIKE ?
                    OR lower(file_path) LIKE ?
                    OR lower(canonical_path) LIKE ?
                    OR lower(author) LIKE ?
                    OR lower(status_normalized) LIKE ?
                    OR lower(feature_slug_hint) LIKE ?
                    OR lower(feature_slug_canonical) LIKE ?
                    OR lower(prd_ref) LIKE ?
                    OR lower(frontmatter_json) LIKE ?
                    OR lower(metadata_json) LIKE ?
                    OR EXISTS (
                        SELECT 1 FROM document_refs dr
                        WHERE dr.document_id = documents.id
                          AND (lower(dr.ref_value) LIKE ? OR lower(dr.ref_value_norm) LIKE ?)
                    )
                )
                """
            )
            params.extend([needle] * 12)

        return " AND ".join(clauses), params

    async def upsert(self, doc_data: dict, project_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        frontmatter = doc_data.get("frontmatter", {})
        metadata = doc_data.get("metadata", {})
        fm_json = json.dumps(frontmatter if isinstance(frontmatter, dict) else {})
        metadata_json = json.dumps(metadata if isinstance(metadata, dict) else {})

        canonical_path = str(doc_data.get("canonicalPath") or doc_data.get("filePath") or "")
        normalized_path = normalize_ref_path(canonical_path)
        if normalized_path:
            canonical_path = normalized_path
        file_path = str(doc_data.get("filePath") or canonical_path)
        file_name = Path(canonical_path).name if canonical_path else Path(file_path).name
        file_stem = Path(canonical_path).stem if canonical_path else Path(file_path).stem
        file_dir = str(Path(canonical_path).parent).replace("\\", "/") if canonical_path else ""
        if file_dir == ".":
            file_dir = ""

        await self.db.execute(
            """INSERT INTO documents (
                id, project_id, title, file_path, canonical_path, root_kind, doc_subtype,
                file_name, file_stem, file_dir, has_frontmatter, frontmatter_type,
                status, status_normalized, author, content, doc_type, category,
                feature_slug_hint, feature_slug_canonical, prd_ref,
                phase_token, phase_number, overall_progress,
                total_tasks, completed_tasks, in_progress_tasks, blocked_tasks,
                metadata_json, parent_doc_id, created_at, updated_at, last_modified,
                frontmatter_json, source_file
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title,
                file_path=excluded.file_path,
                canonical_path=excluded.canonical_path,
                root_kind=excluded.root_kind,
                doc_subtype=excluded.doc_subtype,
                file_name=excluded.file_name,
                file_stem=excluded.file_stem,
                file_dir=excluded.file_dir,
                has_frontmatter=excluded.has_frontmatter,
                frontmatter_type=excluded.frontmatter_type,
                status=excluded.status,
                status_normalized=excluded.status_normalized,
                author=excluded.author,
                content=excluded.content,
                doc_type=excluded.doc_type,
                category=excluded.category,
                feature_slug_hint=excluded.feature_slug_hint,
                feature_slug_canonical=excluded.feature_slug_canonical,
                prd_ref=excluded.prd_ref,
                phase_token=excluded.phase_token,
                phase_number=excluded.phase_number,
                overall_progress=excluded.overall_progress,
                total_tasks=excluded.total_tasks,
                completed_tasks=excluded.completed_tasks,
                in_progress_tasks=excluded.in_progress_tasks,
                blocked_tasks=excluded.blocked_tasks,
                metadata_json=excluded.metadata_json,
                parent_doc_id=excluded.parent_doc_id,
                updated_at=excluded.updated_at,
                last_modified=excluded.last_modified,
                frontmatter_json=excluded.frontmatter_json,
                source_file=excluded.source_file
            """,
            (
                doc_data["id"],
                project_id,
                doc_data.get("title", ""),
                file_path,
                canonical_path,
                doc_data.get("rootKind", "project_plans"),
                doc_data.get("docSubtype", ""),
                file_name,
                file_stem,
                file_dir,
                1 if doc_data.get("hasFrontmatter") else 0,
                doc_data.get("frontmatterType", ""),
                doc_data.get("status", "active"),
                doc_data.get("statusNormalized", ""),
                doc_data.get("author", ""),
                doc_data.get("content"),
                doc_data.get("docType", ""),
                doc_data.get("category", ""),
                doc_data.get("featureSlugHint", ""),
                doc_data.get("featureSlugCanonical", ""),
                doc_data.get("prdRef", ""),
                doc_data.get("phaseToken", ""),
                doc_data.get("phaseNumber"),
                doc_data.get("overallProgress"),
                doc_data.get("totalTasks", 0),
                doc_data.get("completedTasks", 0),
                doc_data.get("inProgressTasks", 0),
                doc_data.get("blockedTasks", 0),
                metadata_json,
                doc_data.get("parentDocId"),
                doc_data.get("createdAt", now),
                now,
                doc_data.get("lastModified", ""),
                fm_json,
                doc_data.get("sourceFile", file_path),
            ),
        )

        await self.db.execute("DELETE FROM document_refs WHERE document_id = ?", (doc_data["id"],))
        rows = self._extract_document_refs(doc_data, project_id)
        for kind, raw, norm, source_field in rows:
            await self.db.execute(
                """
                INSERT INTO document_refs (document_id, project_id, ref_kind, ref_value, ref_value_norm, source_field)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_id, ref_kind, ref_value_norm, source_field) DO NOTHING
                """,
                (doc_data["id"], project_id, kind, raw, norm, source_field),
            )
        await self.db.commit()

    async def get_by_id(self, doc_id: str) -> dict | None:
        async with self.db.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def get_by_path(self, project_id: str, canonical_path: str) -> dict | None:
        async with self.db.execute(
            "SELECT * FROM documents WHERE project_id = ? AND canonical_path = ? LIMIT 1",
            (project_id, normalize_ref_path(canonical_path)),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def list_paginated(self, project_id: str, offset: int, limit: int, filters: dict | None = None) -> list[dict]:
        where_sql, params = self._build_where_clause(project_id, filters)
        query = f"""
            SELECT * FROM documents
            WHERE {where_sql}
            ORDER BY
                COALESCE(updated_at, '') DESC,
                COALESCE(last_modified, '') DESC,
                title ASC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])
        async with self.db.execute(query, params) as cur:
            return [dict(row) for row in await cur.fetchall()]

    async def count(self, project_id: str, filters: dict | None = None) -> int:
        where_sql, params = self._build_where_clause(project_id, filters)
        query = f"SELECT COUNT(*) AS total FROM documents WHERE {where_sql}"
        async with self.db.execute(query, params) as cur:
            row = await cur.fetchone()
            return int(row[0] if row else 0)

    async def list_all(self, project_id: str | None = None) -> list[dict]:
        if project_id:
            return await self.list_paginated(project_id, 0, 1_000_000, {})
        async with self.db.execute("SELECT * FROM documents ORDER BY title") as cur:
            return [dict(row) for row in await cur.fetchall()]

    async def get_catalog_facets(self, project_id: str, filters: dict | None = None) -> dict:
        where_sql, params = self._build_where_clause(project_id, filters)
        facets: dict[str, dict[str, int] | int] = {
            "total": 0,
            "root_kind": {},
            "doc_subtype": {},
            "doc_type": {},
            "category": {},
            "status": {},
            "feature": {},
            "phase": {},
            "has_frontmatter": {},
        }

        async with self.db.execute(f"SELECT COUNT(*) FROM documents WHERE {where_sql}", params) as cur:
            row = await cur.fetchone()
            facets["total"] = int(row[0] if row else 0)

        field_queries = {
            "root_kind": "root_kind",
            "doc_subtype": "doc_subtype",
            "doc_type": "doc_type",
            "category": "category",
            "status": "status_normalized",
            "feature": "feature_slug_canonical",
            "phase": "phase_token",
            "has_frontmatter": "CAST(has_frontmatter AS TEXT)",
        }

        for facet_name, column_name in field_queries.items():
            query = f"""
                SELECT {column_name} AS key, COUNT(*) AS count
                FROM documents
                WHERE {where_sql}
                GROUP BY {column_name}
                HAVING {column_name} IS NOT NULL AND {column_name} != ''
                ORDER BY count DESC, key ASC
            """
            async with self.db.execute(query, params) as cur:
                rows = await cur.fetchall()
            facets[facet_name] = {str(row[0]): int(row[1]) for row in rows}

        return facets

    async def delete_by_source(self, source_file: str) -> None:
        await self.db.execute("DELETE FROM documents WHERE source_file = ?", (source_file,))
        await self.db.commit()
