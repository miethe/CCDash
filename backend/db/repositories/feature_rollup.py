"""Feature session rollup aggregate repository.

Placed as a standalone module rather than on SqliteEntityLinkRepository because:
  1. It is a multi-table read aggregation (sessions, entity_links, documents,
     tasks, test_feature_mappings, test_results, commit_correlations) and
     does not conceptually belong to the entity-graph write path.
  2. Keeping it here lets the Postgres variant subclass cleanly via overrides
     without polluting the lean entity-link interface.

Both SQLite and Postgres variants live in this file as a thin separation layer;
the Postgres class overrides only the queries that differ syntactically (e.g.
GREATEST vs MAX across columns, parameter markers).

No session-log files are read.  All metrics come from the DB tables only.
"""
from __future__ import annotations

import asyncio
import subprocess
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from backend.db.repositories.feature_queries import (
    FeatureRollupBatch,
    FeatureRollupEntry,
    FeatureRollupQuery,
    RollupFreshness,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_sha_stub() -> str:
    """Return the current git HEAD SHA (first 12 chars) or a static fallback."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            capture_output=True, text=True, timeout=2,
        )
        sha = result.stdout.strip()
        return sha if sha else "unknown"
    except Exception:
        return "unknown"


def _top_n(rows: list[tuple[str, int]], n: int) -> list[dict]:
    """Convert (label, count) rows to sorted dicts, capped at n."""
    filtered = [(label, count) for label, count in rows if label]
    filtered.sort(key=lambda x: -x[1])
    return [{"label": label, "count": count} for label, count in filtered[:n]]


def _placeholders(ids: list[str]) -> str:
    return ",".join("?" * len(ids))


# ---------------------------------------------------------------------------
# SQLite implementation
# ---------------------------------------------------------------------------

class SqliteFeatureRollupRepository:
    """Compute per-feature session rollup aggregates from the DB without
    reading any session-log files.

    Usage::

        repo = SqliteFeatureRollupRepository(db)
        batch = await repo.get_feature_session_rollups(project_id, query)
    """

    def __init__(self, db: aiosqlite.Connection):
        self.db = db
        self.db.row_factory = aiosqlite.Row

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def get_feature_session_rollups(
        self, project_id: str, query: FeatureRollupQuery
    ) -> FeatureRollupBatch:
        """Return rollup aggregates for up to 100 feature IDs.

        Strategy: one concurrent GROUP BY sub-query per field group,
        gathered in parallel via asyncio.gather.  Results are merged into
        a dict[feature_id -> FeatureRollupEntry].

        The 100-ID cap is enforced by FeatureRollupQuery; we do not bypass it.
        """
        fids = query.feature_ids
        cache_version = _git_sha_stub()

        # 1. Determine which features actually exist in this project
        existing_fids = await self._existing_features(project_id, fids)
        missing = [fid for fid in fids if fid not in existing_fids]

        # Build baseline zero-entries for all existing IDs
        rollups: dict[str, FeatureRollupEntry] = {
            fid: FeatureRollupEntry(
                feature_id=fid,
                precision="eventually_consistent",
                freshness=RollupFreshness(cache_version=cache_version) if query.include_freshness else None,
            )
            for fid in existing_fids
        }

        if not existing_fids:
            return FeatureRollupBatch(
                rollups=rollups,
                missing=missing,
                generated_at=_now_iso(),
                cache_version=cache_version,
            )

        # 2. Launch sub-queries concurrently
        include = query.include_fields
        include_tests = query.include_test_metrics or ("test_metrics" in include)

        tasks_to_gather: list[Any] = []
        task_names: list[str] = []

        if "session_counts" in include or "latest_activity" in include or "token_cost_totals" in include or "model_provider_summary" in include:
            tasks_to_gather.append(self._query_session_aggregates(project_id, existing_fids))
            task_names.append("session_aggregates")
        if "doc_metrics" in include:
            tasks_to_gather.append(self._query_doc_metrics(project_id, existing_fids))
            task_names.append("doc_metrics")
        if include_tests:
            tasks_to_gather.append(self._query_test_metrics(project_id, existing_fids))
            task_names.append("test_metrics")
        if query.include_freshness:
            tasks_to_gather.append(self._query_freshness(project_id, existing_fids))
            task_names.append("freshness")

        results = await asyncio.gather(*tasks_to_gather, return_exceptions=True)
        result_map: dict[str, Any] = dict(zip(task_names, results))

        # 3. Merge sub-query results into rollup entries
        errors: dict[str, dict] = {}

        # session_aggregates
        sess_agg = result_map.get("session_aggregates")
        if isinstance(sess_agg, Exception):
            for fid in existing_fids:
                errors[fid] = {"code": "session_aggregate_unavailable", "message": str(sess_agg)}
        elif sess_agg is not None:
            for fid, agg in sess_agg.items():
                if fid in rollups:
                    e = rollups[fid]
                    if "session_counts" in include:
                        e.session_count = agg.get("session_count", 0)
                        e.primary_session_count = agg.get("primary_session_count", 0)
                        e.subthread_count = agg.get("subthread_count", 0)
                        if query.include_subthread_resolution:
                            e.unresolved_subthread_count = agg.get("unresolved_subthread_count", 0)
                    if "token_cost_totals" in include:
                        e.total_cost = agg.get("total_cost", 0.0)
                        e.display_cost = agg.get("display_cost", 0.0)
                        e.observed_tokens = agg.get("observed_tokens", 0)
                        e.model_io_tokens = agg.get("model_io_tokens", 0)
                        e.cache_input_tokens = agg.get("cache_input_tokens", 0)
                    if "latest_activity" in include:
                        e.latest_session_at = agg.get("latest_session_at")
                        e.latest_activity_at = agg.get("latest_activity_at")
                    if "model_provider_summary" in include:
                        e.model_families = agg.get("model_families", [])
                        e.providers = agg.get("providers", [])
                        e.workflow_types = agg.get("workflow_types", [])

        # doc_metrics
        doc_agg = result_map.get("doc_metrics")
        if isinstance(doc_agg, Exception):
            for fid in existing_fids:
                if fid not in errors:
                    errors[fid] = {"code": "doc_metrics_unavailable", "message": str(doc_agg)}
        elif doc_agg is not None:
            for fid, dm in doc_agg.items():
                if fid in rollups:
                    e = rollups[fid]
                    e.linked_doc_count = dm.get("linked_doc_count", 0)
                    e.linked_doc_counts_by_type = dm.get("linked_doc_counts_by_type", [])
                    e.linked_task_count = dm.get("linked_task_count", 0)
                    e.linked_commit_count = dm.get("linked_commit_count", 0)
                    e.linked_pr_count = dm.get("linked_pr_count", 0)

        # test_metrics
        test_agg = result_map.get("test_metrics")
        if isinstance(test_agg, Exception):
            for fid in existing_fids:
                # partial precision for test failure
                rollups[fid].precision = "partial"
                if fid not in errors:
                    errors[fid] = {"code": "test_metrics_unavailable", "message": str(test_agg)}
        elif test_agg is not None:
            for fid, tm in test_agg.items():
                if fid in rollups:
                    e = rollups[fid]
                    e.test_count = tm.get("test_count", 0)
                    e.failing_test_count = tm.get("failing_test_count", 0)
                    # partial if source was empty
                    if tm.get("is_partial"):
                        e.precision = "partial"

        # freshness
        fresh_agg = result_map.get("freshness")
        if query.include_freshness and isinstance(fresh_agg, dict):
            for fid, fr in fresh_agg.items():
                if fid in rollups and rollups[fid].freshness is not None:
                    rollups[fid].freshness = fr

        return FeatureRollupBatch(
            rollups=rollups,
            missing=missing,
            errors=errors,
            generated_at=_now_iso(),
            cache_version=cache_version,
        )

    # ------------------------------------------------------------------
    # Sub-queries
    # ------------------------------------------------------------------

    async def _existing_features(self, project_id: str, fids: list[str]) -> list[str]:
        """Return those feature IDs that actually exist in the features table."""
        ph = _placeholders(fids)
        async with self.db.execute(
            f"SELECT id FROM features WHERE project_id = ? AND id IN ({ph})",
            [project_id, *fids],
        ) as cur:
            rows = await cur.fetchall()
        return [row[0] for row in rows]

    async def _query_session_aggregates(
        self, project_id: str, fids: list[str]
    ) -> dict[str, dict]:
        """Main session aggregate: counts, tokens, cost, activity, model breakdown.

        Uses entity_links (source_type='feature', target_type='session') joined
        to sessions table.  Runs three coordinated queries:
          1. Per-feature scalar aggregates (session counts, token sums, max dates).
          2. Per-feature model GROUP BY for model_families/providers.
          3. Per-feature thread_kind GROUP BY for workflow_types.
        """
        ph = _placeholders(fids)
        results: dict[str, dict] = {fid: {} for fid in fids}

        # --- Query 1: scalar aggregates per feature ---
        scalar_sql = f"""
        SELECT
            el.source_id                                   AS feature_id,
            COUNT(DISTINCT el.target_id)                   AS session_count,
            COUNT(DISTINCT CASE WHEN s.parent_session_id IS NULL OR s.parent_session_id = ''
                               THEN el.target_id END)      AS primary_session_count,
            COUNT(DISTINCT CASE WHEN s.parent_session_id IS NOT NULL AND s.parent_session_id != ''
                               THEN el.target_id END)      AS subthread_count,
            SUM(COALESCE(s.total_cost, 0))                 AS total_cost,
            SUM(COALESCE(s.display_cost_usd,
                         s.total_cost, 0))                 AS display_cost,
            SUM(COALESCE(s.observed_tokens, 0))            AS observed_tokens,
            SUM(COALESCE(s.model_io_tokens, 0))            AS model_io_tokens,
            SUM(COALESCE(s.cache_input_tokens, 0))         AS cache_input_tokens,
            MAX(s.started_at)                              AS latest_session_at,
            MAX(CASE
                WHEN s.updated_at > s.started_at THEN s.updated_at
                ELSE s.started_at
            END)                                           AS latest_activity_at
        FROM entity_links el
        JOIN sessions s ON s.id = el.target_id AND s.project_id = ?
        WHERE el.source_type = 'feature'
          AND el.target_type = 'session'
          AND el.source_id IN ({ph})
        GROUP BY el.source_id
        """
        async with self.db.execute(scalar_sql, [project_id, *fids]) as cur:
            rows = await cur.fetchall()

        for row in rows:
            fid = row[0]
            results[fid] = {
                "session_count": int(row[1] or 0),
                "primary_session_count": int(row[2] or 0),
                "subthread_count": int(row[3] or 0),
                "total_cost": float(row[4] or 0.0),
                "display_cost": float(row[5] or 0.0),
                "observed_tokens": int(row[6] or 0),
                "model_io_tokens": int(row[7] or 0),
                "cache_input_tokens": int(row[8] or 0),
                "latest_session_at": row[9] or None,
                "latest_activity_at": row[10] or None,
                "unresolved_subthread_count": None,
                "model_families": [],
                "providers": [],
                "workflow_types": [],
            }

        # --- Query 2: model GROUP BY ---
        model_sql = f"""
        SELECT
            el.source_id  AS feature_id,
            s.model       AS model,
            COUNT(*)      AS cnt
        FROM entity_links el
        JOIN sessions s ON s.id = el.target_id AND s.project_id = ?
        WHERE el.source_type = 'feature'
          AND el.target_type = 'session'
          AND el.source_id IN ({ph})
          AND s.model IS NOT NULL AND s.model != ''
        GROUP BY el.source_id, s.model
        ORDER BY el.source_id, cnt DESC
        """
        async with self.db.execute(model_sql, [project_id, *fids]) as cur:
            model_rows = await cur.fetchall()

        # Accumulate raw model names per feature; derive family/provider at merge
        model_counts: dict[str, dict[str, int]] = {}
        for row in model_rows:
            fid, model, cnt = row[0], row[1] or "", int(row[2] or 0)
            model_counts.setdefault(fid, {})
            model_counts[fid][model] = model_counts[fid].get(model, 0) + cnt

        for fid, mc in model_counts.items():
            if fid not in results:
                continue
            family_agg: dict[str, int] = {}
            provider_agg: dict[str, int] = {}
            for model, cnt in mc.items():
                fam = _derive_model_family(model)
                prov = _derive_provider(model)
                family_agg[fam] = family_agg.get(fam, 0) + cnt
                provider_agg[prov] = provider_agg.get(prov, 0) + cnt
            results[fid]["model_families"] = _top_n(list(family_agg.items()), 5)
            results[fid]["providers"] = _top_n(list(provider_agg.items()), 5)

        # --- Query 3: thread_kind GROUP BY (workflow_types proxy) ---
        wf_sql = f"""
        SELECT
            el.source_id    AS feature_id,
            COALESCE(NULLIF(s.thread_kind, ''), 'primary')  AS workflow_type,
            COUNT(*)        AS cnt
        FROM entity_links el
        JOIN sessions s ON s.id = el.target_id AND s.project_id = ?
        WHERE el.source_type = 'feature'
          AND el.target_type = 'session'
          AND el.source_id IN ({ph})
        GROUP BY el.source_id, workflow_type
        ORDER BY el.source_id, cnt DESC
        """
        async with self.db.execute(wf_sql, [project_id, *fids]) as cur:
            wf_rows = await cur.fetchall()

        wf_counts: dict[str, list[tuple[str, int]]] = {}
        for row in wf_rows:
            fid, wtype, cnt = row[0], row[1] or "primary", int(row[2] or 0)
            wf_counts.setdefault(fid, [])
            wf_counts[fid].append((wtype, cnt))

        for fid, wc in wf_counts.items():
            if fid in results:
                results[fid]["workflow_types"] = _top_n(wc, 5)

        return results

    async def _query_doc_metrics(
        self, project_id: str, fids: list[str]
    ) -> dict[str, dict]:
        """Count linked docs (by type), tasks, commits, PRs per feature."""
        ph = _placeholders(fids)
        results: dict[str, dict] = {
            fid: {
                "linked_doc_count": 0,
                "linked_doc_counts_by_type": [],
                "linked_task_count": 0,
                "linked_commit_count": 0,
                "linked_pr_count": 0,
            }
            for fid in fids
        }

        # Linked documents (via entity_links → documents)
        doc_sql = f"""
        SELECT
            el.source_id                  AS feature_id,
            COUNT(DISTINCT el.target_id)  AS doc_count,
            d.doc_type                    AS doc_type,
            COUNT(DISTINCT el.target_id)  AS type_count
        FROM entity_links el
        LEFT JOIN documents d ON d.id = el.target_id AND d.project_id = ?
        WHERE el.source_type = 'feature'
          AND el.target_type = 'document'
          AND el.source_id IN ({ph})
        GROUP BY el.source_id, d.doc_type
        """
        async with self.db.execute(doc_sql, [project_id, *fids]) as cur:
            doc_rows = await cur.fetchall()

        doc_totals: dict[str, int] = {}
        doc_by_type: dict[str, dict[str, int]] = {}
        for row in doc_rows:
            fid, dtype, tcount = row[0], row[2] or "unknown", int(row[3] or 0)
            doc_totals[fid] = doc_totals.get(fid, 0) + tcount
            doc_by_type.setdefault(fid, {})
            doc_by_type[fid][dtype] = doc_by_type[fid].get(dtype, 0) + tcount

        for fid in fids:
            if fid in doc_totals:
                results[fid]["linked_doc_count"] = doc_totals[fid]
                results[fid]["linked_doc_counts_by_type"] = [
                    {"doc_type": dt, "count": cnt}
                    for dt, cnt in sorted(doc_by_type.get(fid, {}).items(), key=lambda x: -x[1])
                ][:8]

        # Linked tasks (via entity_links → task)
        task_sql = f"""
        SELECT
            el.source_id                  AS feature_id,
            COUNT(DISTINCT el.target_id)  AS task_count
        FROM entity_links el
        WHERE el.source_type = 'feature'
          AND el.target_type = 'task'
          AND el.source_id IN ({ph})
        GROUP BY el.source_id
        """
        async with self.db.execute(task_sql, fids) as cur:
            task_rows = await cur.fetchall()

        for row in task_rows:
            fid, cnt = row[0], int(row[1] or 0)
            if fid in results:
                results[fid]["linked_task_count"] = cnt

        # Linked commits (via commit_correlations.feature_id)
        commit_sql = f"""
        SELECT
            feature_id,
            COUNT(DISTINCT commit_hash) AS commit_count
        FROM commit_correlations
        WHERE project_id = ?
          AND feature_id IN ({ph})
        GROUP BY feature_id
        """
        async with self.db.execute(commit_sql, [project_id, *fids]) as cur:
            commit_rows = await cur.fetchall()

        for row in commit_rows:
            fid, cnt = row[0], int(row[1] or 0)
            if fid in results:
                results[fid]["linked_commit_count"] = cnt

        # PR count: sessions linked to feature may have git_commit_hash but there's
        # no PR table in the current schema.  Return 0 as a safe default.
        # TODO: wire to a PR table when it lands.

        return results

    async def _query_test_metrics(
        self, project_id: str, fids: list[str]
    ) -> dict[str, dict]:
        """Count total and failing tests for each feature via test_feature_mappings."""
        ph = _placeholders(fids)
        results: dict[str, dict] = {}

        # Check if test_feature_mappings table exists (opt-in source may not be populated)
        try:
            async with self.db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='test_feature_mappings'"
            ) as cur:
                exists = await cur.fetchone()
        except Exception:
            exists = None

        if not exists:
            return {fid: {"test_count": 0, "failing_test_count": 0, "is_partial": True} for fid in fids}

        # Latest test result per (feature, test)
        test_sql = f"""
        SELECT
            tfm.feature_id,
            COUNT(DISTINCT tfm.test_id)                          AS test_count,
            COUNT(DISTINCT CASE WHEN tr.status = 'failed'
                               THEN tfm.test_id END)              AS failing_count,
            (MAX(tr.created_at) IS NULL)                         AS is_partial
        FROM test_feature_mappings tfm
        LEFT JOIN (
            SELECT tr2.test_id, tr2.status, tr2.created_at
            FROM test_results tr2
            INNER JOIN (
                SELECT test_id, MAX(created_at) AS max_at
                FROM test_results
                GROUP BY test_id
            ) latest ON tr2.test_id = latest.test_id AND tr2.created_at = latest.max_at
        ) tr ON tr.test_id = tfm.test_id
        WHERE tfm.project_id = ?
          AND tfm.feature_id IN ({ph})
        GROUP BY tfm.feature_id
        """
        try:
            async with self.db.execute(test_sql, [project_id, *fids]) as cur:
                rows = await cur.fetchall()
        except Exception:
            return {fid: {"test_count": 0, "failing_test_count": 0, "is_partial": True} for fid in fids}

        for row in rows:
            fid = row[0]
            results[fid] = {
                "test_count": int(row[1] or 0),
                "failing_test_count": int(row[2] or 0),
                "is_partial": bool(row[3]),
            }

        # Zero-fill features with no test mappings
        for fid in fids:
            if fid not in results:
                results[fid] = {"test_count": 0, "failing_test_count": 0, "is_partial": True}

        return results

    async def _query_freshness(
        self, project_id: str, fids: list[str]
    ) -> dict[str, RollupFreshness]:
        """Collect per-feature freshness timestamps from session syncs and links."""
        ph = _placeholders(fids)
        cache_version = _git_sha_stub()
        results: dict[str, RollupFreshness] = {
            fid: RollupFreshness(cache_version=cache_version) for fid in fids
        }

        # session_sync_at = MAX(s.updated_at) for linked sessions
        sync_sql = f"""
        SELECT
            el.source_id          AS feature_id,
            MAX(s.updated_at)     AS session_sync_at
        FROM entity_links el
        JOIN sessions s ON s.id = el.target_id AND s.project_id = ?
        WHERE el.source_type = 'feature'
          AND el.target_type = 'session'
          AND el.source_id IN ({ph})
        GROUP BY el.source_id
        """
        async with self.db.execute(sync_sql, [project_id, *fids]) as cur:
            for row in await cur.fetchall():
                fid, sync_at = row[0], row[1]
                if fid in results:
                    results[fid] = RollupFreshness(
                        session_sync_at=sync_at or None,
                        cache_version=cache_version,
                    )

        # links_updated_at = MAX(el.created_at) for feature entity links
        links_sql = f"""
        SELECT
            source_id               AS feature_id,
            MAX(created_at)         AS links_updated_at
        FROM entity_links
        WHERE source_type = 'feature'
          AND source_id IN ({ph})
        GROUP BY source_id
        """
        async with self.db.execute(links_sql, fids) as cur:
            for row in await cur.fetchall():
                fid, links_at = row[0], row[1]
                if fid in results:
                    results[fid] = RollupFreshness(
                        session_sync_at=results[fid].session_sync_at,
                        links_updated_at=links_at or None,
                        test_health_at=results[fid].test_health_at,
                        cache_version=cache_version,
                    )

        return results


# ---------------------------------------------------------------------------
# Model family / provider derivation helpers (no external deps)
# ---------------------------------------------------------------------------

def _derive_model_family(model: str) -> str:
    """Map a raw model name string to a normalized family label."""
    m = model.lower()
    if "claude" in m:
        # e.g. claude-opus-4, claude-sonnet-4-5, claude-haiku-3
        for tier in ("opus", "sonnet", "haiku"):
            if tier in m:
                # extract major version if present
                import re
                ver = re.search(r"(\d+)", m.split(tier)[-1])
                v = ver.group(1) if ver else ""
                return f"claude-{tier}{'-' + v if v else ''}"
        return "claude"
    if "gpt" in m:
        import re
        ver = re.search(r"gpt[-\s]?(\S+)", m)
        return f"gpt-{ver.group(1)}" if ver else "gpt"
    if "gemini" in m:
        return "gemini"
    if "llama" in m:
        return "llama"
    if "mistral" in m:
        return "mistral"
    return model.split("/")[-1].split(":")[0] or "unknown"


def _derive_provider(model: str) -> str:
    """Derive the provider label from a model string."""
    m = model.lower()
    if "claude" in m or "anthropic" in m:
        return "anthropic"
    if "gpt" in m or "openai" in m or "o1" in m or "o3" in m:
        return "openai"
    if "gemini" in m or "google" in m:
        return "google"
    if "llama" in m or "meta" in m:
        return "meta"
    if "mistral" in m:
        return "mistral"
    if "/" in model:
        return model.split("/")[0].lower()
    return "unknown"


# ---------------------------------------------------------------------------
# Postgres variant
# ---------------------------------------------------------------------------

class PostgresFeatureRollupRepository(SqliteFeatureRollupRepository):
    """Postgres override: uses $N parameter markers and asyncpg cursor interface.

    Only methods with SQLite-specific syntax are overridden.  The base class
    asyncio.gather orchestration is reused unchanged.
    """

    def __init__(self, db: Any):  # asyncpg Connection or pool
        self.db = db

    async def _existing_features(self, project_id: str, fids: list[str]) -> list[str]:
        rows = await self.db.fetch(
            "SELECT id FROM features WHERE project_id = $1 AND id = ANY($2::text[])",
            project_id, fids,
        )
        return [row["id"] for row in rows]

    async def _query_session_aggregates(
        self, project_id: str, fids: list[str]
    ) -> dict[str, dict]:
        """Postgres version using $1/$2 markers and asyncpg .fetch()."""
        results: dict[str, dict] = {fid: {} for fid in fids}

        scalar_sql = """
        SELECT
            el.source_id                                                 AS feature_id,
            COUNT(DISTINCT el.target_id)                                 AS session_count,
            COUNT(DISTINCT CASE WHEN (s.parent_session_id IS NULL OR s.parent_session_id = '')
                               THEN el.target_id END)                    AS primary_session_count,
            COUNT(DISTINCT CASE WHEN (s.parent_session_id IS NOT NULL AND s.parent_session_id != '')
                               THEN el.target_id END)                    AS subthread_count,
            SUM(COALESCE(s.total_cost, 0))                               AS total_cost,
            SUM(COALESCE(s.display_cost_usd, s.total_cost, 0))           AS display_cost,
            SUM(COALESCE(s.observed_tokens, 0))                          AS observed_tokens,
            SUM(COALESCE(s.model_io_tokens, 0))                          AS model_io_tokens,
            SUM(COALESCE(s.cache_input_tokens, 0))                       AS cache_input_tokens,
            MAX(s.started_at)                                            AS latest_session_at,
            GREATEST(MAX(s.updated_at), MAX(s.started_at))               AS latest_activity_at
        FROM entity_links el
        JOIN sessions s ON s.id = el.target_id AND s.project_id = $1
        WHERE el.source_type = 'feature'
          AND el.target_type = 'session'
          AND el.source_id = ANY($2::text[])
        GROUP BY el.source_id
        """
        rows = await self.db.fetch(scalar_sql, project_id, fids)
        for row in rows:
            fid = row["feature_id"]
            results[fid] = {
                "session_count": int(row["session_count"] or 0),
                "primary_session_count": int(row["primary_session_count"] or 0),
                "subthread_count": int(row["subthread_count"] or 0),
                "total_cost": float(row["total_cost"] or 0.0),
                "display_cost": float(row["display_cost"] or 0.0),
                "observed_tokens": int(row["observed_tokens"] or 0),
                "model_io_tokens": int(row["model_io_tokens"] or 0),
                "cache_input_tokens": int(row["cache_input_tokens"] or 0),
                "latest_session_at": row["latest_session_at"] or None,
                "latest_activity_at": row["latest_activity_at"] or None,
                "unresolved_subthread_count": None,
                "model_families": [],
                "providers": [],
                "workflow_types": [],
            }

        # model breakdown
        model_sql = """
        SELECT el.source_id AS feature_id, s.model, COUNT(*) AS cnt
        FROM entity_links el
        JOIN sessions s ON s.id = el.target_id AND s.project_id = $1
        WHERE el.source_type = 'feature'
          AND el.target_type = 'session'
          AND el.source_id = ANY($2::text[])
          AND s.model IS NOT NULL AND s.model <> ''
        GROUP BY el.source_id, s.model
        ORDER BY el.source_id, cnt DESC
        """
        model_rows = await self.db.fetch(model_sql, project_id, fids)
        model_counts: dict[str, dict[str, int]] = {}
        for row in model_rows:
            fid, model, cnt = row["feature_id"], row["model"] or "", int(row["cnt"] or 0)
            model_counts.setdefault(fid, {})
            model_counts[fid][model] = model_counts[fid].get(model, 0) + cnt

        for fid, mc in model_counts.items():
            if fid not in results:
                continue
            family_agg: dict[str, int] = {}
            provider_agg: dict[str, int] = {}
            for model, cnt in mc.items():
                fam = _derive_model_family(model)
                prov = _derive_provider(model)
                family_agg[fam] = family_agg.get(fam, 0) + cnt
                provider_agg[prov] = provider_agg.get(prov, 0) + cnt
            results[fid]["model_families"] = _top_n(list(family_agg.items()), 5)
            results[fid]["providers"] = _top_n(list(provider_agg.items()), 5)

        # workflow types via thread_kind
        wf_sql = """
        SELECT
            el.source_id AS feature_id,
            COALESCE(NULLIF(s.thread_kind, ''), 'primary') AS workflow_type,
            COUNT(*) AS cnt
        FROM entity_links el
        JOIN sessions s ON s.id = el.target_id AND s.project_id = $1
        WHERE el.source_type = 'feature'
          AND el.target_type = 'session'
          AND el.source_id = ANY($2::text[])
        GROUP BY el.source_id, workflow_type
        ORDER BY el.source_id, cnt DESC
        """
        wf_rows = await self.db.fetch(wf_sql, project_id, fids)
        wf_counts: dict[str, list[tuple[str, int]]] = {}
        for row in wf_rows:
            fid, wtype, cnt = row["feature_id"], row["workflow_type"] or "primary", int(row["cnt"] or 0)
            wf_counts.setdefault(fid, [])
            wf_counts[fid].append((wtype, cnt))

        for fid, wc in wf_counts.items():
            if fid in results:
                results[fid]["workflow_types"] = _top_n(wc, 5)

        return results

    async def _query_doc_metrics(
        self, project_id: str, fids: list[str]
    ) -> dict[str, dict]:
        results: dict[str, dict] = {
            fid: {
                "linked_doc_count": 0,
                "linked_doc_counts_by_type": [],
                "linked_task_count": 0,
                "linked_commit_count": 0,
                "linked_pr_count": 0,
            }
            for fid in fids
        }

        doc_sql = """
        SELECT
            el.source_id,
            COALESCE(d.doc_type, 'unknown') AS doc_type,
            COUNT(DISTINCT el.target_id) AS type_count
        FROM entity_links el
        LEFT JOIN documents d ON d.id = el.target_id AND d.project_id = $1
        WHERE el.source_type = 'feature'
          AND el.target_type = 'document'
          AND el.source_id = ANY($2::text[])
        GROUP BY el.source_id, doc_type
        """
        doc_rows = await self.db.fetch(doc_sql, project_id, fids)
        doc_totals: dict[str, int] = {}
        doc_by_type: dict[str, dict[str, int]] = {}
        for row in doc_rows:
            fid, dtype, tcount = row["source_id"], row["doc_type"] or "unknown", int(row["type_count"] or 0)
            doc_totals[fid] = doc_totals.get(fid, 0) + tcount
            doc_by_type.setdefault(fid, {})
            doc_by_type[fid][dtype] = doc_by_type[fid].get(dtype, 0) + tcount

        for fid in fids:
            if fid in doc_totals:
                results[fid]["linked_doc_count"] = doc_totals[fid]
                results[fid]["linked_doc_counts_by_type"] = [
                    {"doc_type": dt, "count": cnt}
                    for dt, cnt in sorted(doc_by_type.get(fid, {}).items(), key=lambda x: -x[1])
                ][:8]

        task_sql = """
        SELECT source_id AS feature_id, COUNT(DISTINCT target_id) AS task_count
        FROM entity_links
        WHERE source_type = 'feature'
          AND target_type = 'task'
          AND source_id = ANY($1::text[])
        GROUP BY source_id
        """
        task_rows = await self.db.fetch(task_sql, fids)
        for row in task_rows:
            fid, cnt = row["feature_id"], int(row["task_count"] or 0)
            if fid in results:
                results[fid]["linked_task_count"] = cnt

        commit_sql = """
        SELECT feature_id, COUNT(DISTINCT commit_hash) AS commit_count
        FROM commit_correlations
        WHERE project_id = $1 AND feature_id = ANY($2::text[])
        GROUP BY feature_id
        """
        commit_rows = await self.db.fetch(commit_sql, project_id, fids)
        for row in commit_rows:
            fid, cnt = row["feature_id"], int(row["commit_count"] or 0)
            if fid in results:
                results[fid]["linked_commit_count"] = cnt

        return results

    async def _query_test_metrics(
        self, project_id: str, fids: list[str]
    ) -> dict[str, dict]:
        results: dict[str, dict] = {}
        test_sql = """
        SELECT
            tfm.feature_id,
            COUNT(DISTINCT tfm.test_id)                                     AS test_count,
            COUNT(DISTINCT CASE WHEN tr.status = 'failed' THEN tfm.test_id END) AS failing_count,
            (MAX(tr.created_at) IS NULL)                                    AS is_partial
        FROM test_feature_mappings tfm
        LEFT JOIN (
            SELECT DISTINCT ON (test_id) test_id, status, created_at
            FROM test_results
            ORDER BY test_id, created_at DESC
        ) tr ON tr.test_id = tfm.test_id
        WHERE tfm.project_id = $1
          AND tfm.feature_id = ANY($2::text[])
        GROUP BY tfm.feature_id
        """
        try:
            rows = await self.db.fetch(test_sql, project_id, fids)
        except Exception:
            return {fid: {"test_count": 0, "failing_test_count": 0, "is_partial": True} for fid in fids}

        for row in rows:
            fid = row["feature_id"]
            results[fid] = {
                "test_count": int(row["test_count"] or 0),
                "failing_test_count": int(row["failing_count"] or 0),
                "is_partial": bool(row["is_partial"]),
            }
        for fid in fids:
            if fid not in results:
                results[fid] = {"test_count": 0, "failing_test_count": 0, "is_partial": True}
        return results

    async def _query_freshness(
        self, project_id: str, fids: list[str]
    ) -> dict[str, RollupFreshness]:
        cache_version = _git_sha_stub()
        results: dict[str, RollupFreshness] = {
            fid: RollupFreshness(cache_version=cache_version) for fid in fids
        }

        sync_sql = """
        SELECT el.source_id AS feature_id, MAX(s.updated_at) AS session_sync_at
        FROM entity_links el
        JOIN sessions s ON s.id = el.target_id AND s.project_id = $1
        WHERE el.source_type = 'feature'
          AND el.target_type = 'session'
          AND el.source_id = ANY($2::text[])
        GROUP BY el.source_id
        """
        rows = await self.db.fetch(sync_sql, project_id, fids)
        for row in rows:
            fid = row["feature_id"]
            if fid in results:
                results[fid] = RollupFreshness(
                    session_sync_at=str(row["session_sync_at"]) if row["session_sync_at"] else None,
                    cache_version=cache_version,
                )

        links_sql = """
        SELECT source_id AS feature_id, MAX(created_at) AS links_updated_at
        FROM entity_links
        WHERE source_type = 'feature'
          AND source_id = ANY($1::text[])
        GROUP BY source_id
        """
        rows = await self.db.fetch(links_sql, fids)
        for row in rows:
            fid = row["feature_id"]
            if fid in results:
                results[fid] = RollupFreshness(
                    session_sync_at=results[fid].session_sync_at,
                    links_updated_at=str(row["links_updated_at"]) if row["links_updated_at"] else None,
                    test_health_at=results[fid].test_health_at,
                    cache_version=cache_version,
                )

        return results
