"""PostgreSQL implementation of DocumentRepository."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import asyncpg

from backend.document_linking import (
    canonical_slug,
    normalize_doc_status,
    normalize_doc_subtype,
    normalize_doc_type,
    normalize_ref_path,
)


class PostgresDocumentRepository:
    """Postgres-backed document storage with typed metadata and refs."""

    def __init__(self, db: asyncpg.Connection):
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
            if kind in {"feature", "feature_ref", "feature_slug", "lineage_parent", "lineage_child", "lineage_family"}:
                norm = canonical_slug(norm)
            refs.append((kind, raw, norm, source_field))

        for value in frontmatter.get("linkedFeatures", []) or []:
            if isinstance(value, str):
                add("feature", value, "linkedFeatures")
        for value in frontmatter.get("linkedSessions", []) or []:
            if isinstance(value, str):
                add("session", value, "linkedSessions")
        lineage_parent = frontmatter.get("lineageParent")
        if isinstance(lineage_parent, str):
            add("lineage_parent", lineage_parent, "lineageParent")
            add("feature", lineage_parent, "lineageParent")
        lineage_family = frontmatter.get("lineageFamily")
        if isinstance(lineage_family, str):
            add("lineage_family", lineage_family, "lineageFamily")
        for value in frontmatter.get("lineageChildren", []) or []:
            if isinstance(value, str):
                add("lineage_child", value, "lineageChildren")
                add("feature", value, "lineageChildren")
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
        clauses = ["project_id = $1"]
        params: list[Any] = [project_id]

        def add_param(value: Any) -> str:
            params.append(value)
            return f"${len(params)}"

        include_progress = filters.get("include_progress")
        if include_progress is False:
            clauses.append("root_kind != 'progress'")

        if filters.get("root_kind"):
            clauses.append(f"root_kind = {add_param(str(filters['root_kind']))}")
        if filters.get("doc_subtype"):
            doc_subtype = normalize_doc_subtype(str(filters["doc_subtype"]))
            clauses.append(f"doc_subtype = {add_param(doc_subtype)}")
        if filters.get("doc_type"):
            clauses.append(f"doc_type = {add_param(normalize_doc_type(str(filters['doc_type'])))}")
        if filters.get("category"):
            clauses.append(f"category = {add_param(str(filters['category']))}")
        if filters.get("status"):
            status = normalize_doc_status(str(filters["status"]))
            p1 = add_param(status)
            p2 = add_param(status)
            clauses.append(f"(status_normalized = {p1} OR status = {p2})")
        if filters.get("feature"):
            token = canonical_slug(str(filters["feature"]).strip().lower())
            p1 = add_param(token)
            p2 = add_param(token)
            p3 = add_param(token)
            clauses.append(
                f"""
                (
                    feature_slug_canonical = {p1}
                    OR feature_slug_hint = {p2}
                    OR EXISTS (
                        SELECT 1 FROM document_refs dr
                        WHERE dr.document_id = documents.id
                          AND dr.ref_kind IN ('feature', 'feature_ref', 'feature_slug', 'prd')
                          AND dr.ref_value_norm = {p3}
                    )
                )
                """
            )
        if filters.get("prd"):
            token = str(filters["prd"]).strip().lower()
            p1 = add_param(token)
            p2 = add_param(token)
            clauses.append(
                f"""
                (
                    lower(prd_ref) = {p1}
                    OR EXISTS (
                        SELECT 1 FROM document_refs dr
                        WHERE dr.document_id = documents.id
                          AND dr.ref_kind = 'prd'
                          AND dr.ref_value_norm = {p2}
                    )
                )
                """
            )
        if filters.get("phase"):
            phase_token = str(filters["phase"]).strip()
            p1 = add_param(phase_token)
            p2 = add_param(phase_token)
            clauses.append(f"(phase_token = {p1} OR CAST(phase_number AS TEXT) = {p2})")
        if filters.get("has_frontmatter") is not None:
            clauses.append(f"has_frontmatter = {add_param(1 if filters['has_frontmatter'] else 0)}")
        if filters.get("q"):
            needle = f"%{str(filters['q']).strip().lower()}%"
            p = [add_param(needle) for _ in range(12)]
            clauses.append(
                f"""
                (
                    lower(title) LIKE {p[0]}
                    OR lower(file_path) LIKE {p[1]}
                    OR lower(canonical_path) LIKE {p[2]}
                    OR lower(author) LIKE {p[3]}
                    OR lower(status_normalized) LIKE {p[4]}
                    OR lower(feature_slug_hint) LIKE {p[5]}
                    OR lower(feature_slug_canonical) LIKE {p[6]}
                    OR lower(prd_ref) LIKE {p[7]}
                    OR lower(frontmatter_json) LIKE {p[8]}
                    OR lower(metadata_json) LIKE {p[9]}
                    OR EXISTS (
                        SELECT 1 FROM document_refs dr
                        WHERE dr.document_id = documents.id
                          AND (lower(dr.ref_value) LIKE {p[10]} OR lower(dr.ref_value_norm) LIKE {p[11]})
                    )
                )
                """
            )

        return " AND ".join(clauses), params

    async def upsert(self, doc_data: dict, project_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        created_at = doc_data.get("createdAt", "") or now
        updated_at = doc_data.get("updatedAt", "") or doc_data.get("lastModified", "") or now
        frontmatter = doc_data.get("frontmatter", {})
        raw_metadata = doc_data.get("metadata", {})
        metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
        metadata_payload = dict(metadata)
        if isinstance(doc_data.get("dates"), dict) and doc_data.get("dates"):
            metadata_payload["dates"] = doc_data.get("dates")
        if isinstance(doc_data.get("timeline"), list) and doc_data.get("timeline"):
            metadata_payload["timeline"] = doc_data.get("timeline")
        fm_json = json.dumps(frontmatter if isinstance(frontmatter, dict) else {})
        metadata_json = json.dumps(metadata_payload)

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

        query = """
            INSERT INTO documents (
                id, project_id, title, file_path, canonical_path, root_kind, doc_subtype,
                file_name, file_stem, file_dir, has_frontmatter, frontmatter_type,
                status, status_normalized, author, content, doc_type, category,
                feature_slug_hint, feature_slug_canonical, prd_ref,
                phase_token, phase_number, overall_progress,
                total_tasks, completed_tasks, in_progress_tasks, blocked_tasks,
                metadata_json, parent_doc_id, created_at, updated_at, last_modified,
                frontmatter_json, source_file
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7,
                $8, $9, $10, $11, $12,
                $13, $14, $15, $16, $17, $18,
                $19, $20, $21,
                $22, $23, $24,
                $25, $26, $27, $28,
                $29, $30, $31, $32, $33,
                $34, $35
            )
            ON CONFLICT(id) DO UPDATE SET
                title=EXCLUDED.title,
                file_path=EXCLUDED.file_path,
                canonical_path=EXCLUDED.canonical_path,
                root_kind=EXCLUDED.root_kind,
                doc_subtype=EXCLUDED.doc_subtype,
                file_name=EXCLUDED.file_name,
                file_stem=EXCLUDED.file_stem,
                file_dir=EXCLUDED.file_dir,
                has_frontmatter=EXCLUDED.has_frontmatter,
                frontmatter_type=EXCLUDED.frontmatter_type,
                status=EXCLUDED.status,
                status_normalized=EXCLUDED.status_normalized,
                author=EXCLUDED.author,
                content=EXCLUDED.content,
                doc_type=EXCLUDED.doc_type,
                category=EXCLUDED.category,
                feature_slug_hint=EXCLUDED.feature_slug_hint,
                feature_slug_canonical=EXCLUDED.feature_slug_canonical,
                prd_ref=EXCLUDED.prd_ref,
                phase_token=EXCLUDED.phase_token,
                phase_number=EXCLUDED.phase_number,
                overall_progress=EXCLUDED.overall_progress,
                total_tasks=EXCLUDED.total_tasks,
                completed_tasks=EXCLUDED.completed_tasks,
                in_progress_tasks=EXCLUDED.in_progress_tasks,
                blocked_tasks=EXCLUDED.blocked_tasks,
                metadata_json=EXCLUDED.metadata_json,
                parent_doc_id=EXCLUDED.parent_doc_id,
                updated_at=EXCLUDED.updated_at,
                last_modified=EXCLUDED.last_modified,
                frontmatter_json=EXCLUDED.frontmatter_json,
                source_file=EXCLUDED.source_file
        """
        await self.db.execute(
            query,
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
            created_at,
            updated_at,
            doc_data.get("lastModified", ""),
            fm_json,
            doc_data.get("sourceFile", file_path),
        )

        await self.db.execute("DELETE FROM document_refs WHERE document_id = $1", doc_data["id"])
        rows = self._extract_document_refs(doc_data, project_id)
        if rows:
            await self.db.executemany(
                """
                INSERT INTO document_refs (document_id, project_id, ref_kind, ref_value, ref_value_norm, source_field)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT(document_id, ref_kind, ref_value_norm, source_field) DO NOTHING
                """,
                [(doc_data["id"], project_id, kind, raw, norm, source_field) for kind, raw, norm, source_field in rows],
            )

    async def get_by_id(self, doc_id: str) -> dict | None:
        row = await self.db.fetchrow("SELECT * FROM documents WHERE id = $1", doc_id)
        return dict(row) if row else None

    async def get_by_path(self, project_id: str, canonical_path: str) -> dict | None:
        row = await self.db.fetchrow(
            "SELECT * FROM documents WHERE project_id = $1 AND canonical_path = $2 LIMIT 1",
            project_id,
            normalize_ref_path(canonical_path),
        )
        return dict(row) if row else None

    async def list_paginated(self, project_id: str, offset: int, limit: int, filters: dict | None = None) -> list[dict]:
        where_sql, params = self._build_where_clause(project_id, filters)
        params_with_page = [*params, limit, offset]
        query = f"""
            SELECT * FROM documents
            WHERE {where_sql}
            ORDER BY
                COALESCE(updated_at, '') DESC,
                COALESCE(last_modified, '') DESC,
                title ASC
            LIMIT ${len(params_with_page) - 1} OFFSET ${len(params_with_page)}
        """
        rows = await self.db.fetch(query, *params_with_page)
        return [dict(row) for row in rows]

    async def count(self, project_id: str, filters: dict | None = None) -> int:
        where_sql, params = self._build_where_clause(project_id, filters)
        row = await self.db.fetchrow(f"SELECT COUNT(*) AS total FROM documents WHERE {where_sql}", *params)
        return int(row["total"] if row else 0)

    async def list_all(self, project_id: str | None = None) -> list[dict]:
        if project_id:
            return await self.list_paginated(project_id, 0, 1_000_000, {})
        rows = await self.db.fetch("SELECT * FROM documents ORDER BY title")
        return [dict(row) for row in rows]

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

        total_row = await self.db.fetchrow(f"SELECT COUNT(*) AS total FROM documents WHERE {where_sql}", *params)
        facets["total"] = int(total_row["total"] if total_row else 0)

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
            rows = await self.db.fetch(query, *params)
            facets[facet_name] = {str(row["key"]): int(row["count"]) for row in rows}

        return facets

    async def delete_by_source(self, source_file: str) -> None:
        await self.db.execute("DELETE FROM documents WHERE source_file = $1", source_file)
