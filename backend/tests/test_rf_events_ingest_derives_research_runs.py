"""Service-layer regression: live rf-events ingest derives research_runs + correlation.

Phase 2 reviewer fix (research-foundry-run-telemetry-v1): prior to this test,
``RfEventsIngestService.process()`` persisted only to ``rf_events`` and
advanced the ``ingest_cursors`` watermark — it never called
``ResearchRunsRepository.upsert_from_event`` or
``EntityLinkRepository.correlate_research_run``, so ``research_runs`` was
only ever populated by test fixtures / the manual
``backfill_from_rf_events`` recovery path, never by real
``POST /api/v1/ingest/rf-events`` traffic.

This test exercises the *service* layer directly (one level below the HTTP
contract test in ``test_rf_events_ingest_to_research_runs_smoke.py``) against
a real in-memory SQLite DB migrated via ``run_migrations``, proving:

  1. A genuinely new event with a ``run_id`` derives/upserts exactly one
     ``research_runs`` row (direct ``SELECT`` assertion, not just a
     return-value check).
  2. When a correlated session exists (overlapping time window + matching
     project_id), an ``entity_links`` row is written linking the derived
     run to that session — the live path exercises the same
     ``correlate_research_run`` contract as
     ``test_entity_graph_research_run_correlation.py``.
  3. A duplicate re-POST of the same ``event_id`` does not re-fold into the
     SUMMED ``research_runs`` columns (``event_count`` stays at 1, never 2).
  4. The derive/correlate step is optional and best-effort: omitting
     ``research_runs_repo``/``entity_link_repo`` (the constructor default)
     leaves ``process()`` behaving exactly as before this fix, and a
     failure raised by either repo is swallowed rather than propagated —
     the ``rf_events`` row (AC-1) must never be lost to a rollup failure.

Run as a named module (full collection can hang):
    backend/.venv/bin/python -m pytest backend/tests/test_rf_events_ingest_derives_research_runs.py -v
"""
from __future__ import annotations

import unittest
import uuid
from datetime import datetime, timedelta, timezone

import aiosqlite

from backend.application.models.ingest import RfEventPayload
from backend.application.services.ingest.rf_events_ingest import RfEventsIngestService
from backend.db.repositories.entity_graph import SqliteEntityLinkRepository
from backend.db.repositories.ingest_cursors import SqliteIngestCursorRepository
from backend.db.repositories.research_runs import SqliteResearchRunsRepository
from backend.db.repositories.rf_events import SqliteRfEventsRepository
from backend.db.sqlite_migrations import run_migrations

_PROJECT_ID = "proj-rf-derive"


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _event(run_id: str, event_id: str | None = None, **extra) -> RfEventPayload:
    base = datetime(2026, 7, 21, 10, 0, 0, tzinfo=timezone.utc)
    obj: dict = {
        "event_id": event_id or str(uuid.uuid4()),
        "timestamp": _iso(base),
        "project": "research-foundry",
        "run_id": run_id,
        "metrics": {
            "claims_total": 10,
            "claims_supported": 8,
            "cost_estimated_usd": 0.42,
        },
    }
    obj.update(extra)
    return RfEventPayload.model_validate(obj)


async def _insert_session(
    db: aiosqlite.Connection,
    *,
    session_id: str,
    project_id: str,
    started_at: datetime,
    ended_at: datetime,
) -> None:
    now = _iso(datetime.now(timezone.utc))
    await db.execute(
        """INSERT INTO sessions (id, project_id, started_at, ended_at, created_at, updated_at, source_file)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (session_id, project_id, _iso(started_at), _iso(ended_at), now, now, f"{session_id}.jsonl"),
    )
    await db.commit()


class _RaisingResearchRunsRepo:
    """Duck-typed research_runs repo whose upsert_from_event always raises."""

    async def upsert_from_event(self, *args, **kwargs):  # noqa: D401
        raise RuntimeError("simulated research_runs upsert failure")

    async def get_by_run_id(self, *args, **kwargs):
        return None


class RfEventsIngestDerivesResearchRunsTests(unittest.IsolatedAsyncioTestCase):
    """Live ingest -> research_runs derivation + run<->session correlation."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.rf_events_repo = SqliteRfEventsRepository(self.db)
        self.cursor_repo = SqliteIngestCursorRepository(self.db)
        self.research_runs_repo = SqliteResearchRunsRepository(self.db)
        self.entity_link_repo = SqliteEntityLinkRepository(self.db)
        self.service = RfEventsIngestService(
            self.rf_events_repo,
            self.cursor_repo,
            research_runs_repo=self.research_runs_repo,
            entity_link_repo=self.entity_link_repo,
        )

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def _research_runs_row(self, run_id: str) -> dict | None:
        cursor = await self.db.execute(
            "SELECT * FROM research_runs WHERE run_id = ?", (run_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def _entity_links_for(self, run_id: str) -> list[dict]:
        return await self.entity_link_repo.get_links_for("research_run", run_id, link_type="research_run")

    # ------------------------------------------------------------------
    # 1. New event -> derived research_runs row
    # ------------------------------------------------------------------

    async def test_new_event_derives_research_runs_row(self) -> None:
        event = _event("run-derive-1")
        was_new, _ = await self.service.process(event, project_id=_PROJECT_ID)
        self.assertTrue(was_new)

        from backend.db.repositories.research_runs import resolve_run_id

        canonical_run_id, _ = resolve_run_id(
            "run-derive-1", workspace_id="default-local", project_id=_PROJECT_ID
        )
        row = await self._research_runs_row(canonical_run_id)
        self.assertIsNotNone(row, "a live ingest POST must derive a research_runs row")
        self.assertEqual(row["project_id"], _PROJECT_ID)
        self.assertEqual(row["event_count"], 1)
        self.assertEqual(row["total_claims_total"], 10)

    # ------------------------------------------------------------------
    # 2. Correlated session -> entity_links row written
    # ------------------------------------------------------------------

    async def test_new_event_correlates_to_overlapping_session(self) -> None:
        base = datetime(2026, 7, 21, 10, 0, 0, tzinfo=timezone.utc)
        await _insert_session(
            self.db,
            session_id="sess-derive-1",
            project_id=_PROJECT_ID,
            started_at=base - timedelta(minutes=2),
            ended_at=base + timedelta(minutes=10),
        )

        event = _event("run-derive-2")
        await self.service.process(event, project_id=_PROJECT_ID)

        from backend.db.repositories.research_runs import resolve_run_id

        canonical_run_id, _ = resolve_run_id(
            "run-derive-2", workspace_id="default-local", project_id=_PROJECT_ID
        )
        links = await self._entity_links_for(canonical_run_id)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["target_id"], "sess-derive-1")
        self.assertEqual(links[0]["target_type"], "session")

    # ------------------------------------------------------------------
    # 3. Duplicate re-POST must not double-fold research_runs sums
    # ------------------------------------------------------------------

    async def test_duplicate_event_does_not_double_count_research_runs(self) -> None:
        event = _event("run-derive-3", event_id=str(uuid.uuid4()))

        await self.service.process(event, project_id=_PROJECT_ID)
        await self.service.process(event, project_id=_PROJECT_ID)  # re-POST, same event_id

        from backend.db.repositories.research_runs import resolve_run_id

        canonical_run_id, _ = resolve_run_id(
            "run-derive-3", workspace_id="default-local", project_id=_PROJECT_ID
        )
        row = await self._research_runs_row(canonical_run_id)
        self.assertIsNotNone(row)
        self.assertEqual(
            row["event_count"], 1, "a duplicate event_id must never re-fold into research_runs"
        )
        self.assertEqual(row["total_claims_total"], 10)

    # ------------------------------------------------------------------
    # 4. Backward compatibility: repos omitted -> no derivation, no crash
    # ------------------------------------------------------------------

    async def test_omitted_repos_skip_derivation_without_error(self) -> None:
        service = RfEventsIngestService(self.rf_events_repo, self.cursor_repo)
        event = _event("run-derive-4")
        was_new, _ = await service.process(event, project_id=_PROJECT_ID)
        self.assertTrue(was_new)

        from backend.db.repositories.research_runs import resolve_run_id

        canonical_run_id, _ = resolve_run_id(
            "run-derive-4", workspace_id="default-local", project_id=_PROJECT_ID
        )
        self.assertIsNone(await self._research_runs_row(canonical_run_id))

    # ------------------------------------------------------------------
    # 5. Best-effort: a research_runs failure never blocks rf_events persistence
    # ------------------------------------------------------------------

    async def test_research_runs_failure_does_not_block_rf_events_persistence(self) -> None:
        service = RfEventsIngestService(
            self.rf_events_repo,
            self.cursor_repo,
            research_runs_repo=_RaisingResearchRunsRepo(),
            entity_link_repo=self.entity_link_repo,
        )
        event = _event("run-derive-5")
        was_new, event_id = await service.process(event, project_id=_PROJECT_ID)  # must not raise
        self.assertTrue(was_new)
        self.assertEqual(event_id, event.event_id)

        cursor = await self.db.execute(
            "SELECT COUNT(*) FROM rf_events WHERE event_id = ?", (event.event_id,)
        )
        (count,) = await cursor.fetchone()
        self.assertEqual(count, 1, "rf_events persistence must survive a research_runs failure")


if __name__ == "__main__":
    unittest.main()
